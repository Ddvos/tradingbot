<script lang="ts">
	import { goto } from '$app/navigation';
	import { page } from '$app/state';
	import CandleChart from '#lib/CandleChart.svelte';
	import ScoreTable, { type Cell, type Row } from '#lib/ScoreTable.svelte';
	import {
		DETECTORS,
		fetchCandles,
		fetchReplay,
		fetchTurningPoints,
		STRATEGIES,
		TIMEFRAMES,
		type Candle,
		type Replay,
		type Score,
		type StrategyScore,
		type Backtest,
		type CostModelScore,
		type Era,
		type TradeGroup,
		type Timeframe,
		type TurningPoint
	} from '#lib/api.ts';
	import {
		COLORS,
		startIndex,
		toLines,
		type ChartFill,
		type ChartLine,
		type ChartMark
	} from '#lib/chart.ts';

	type Mode = 'hindsight' | 'replay';
	const SPEEDS = [1, 10, 100, 1000];
	/** The first stored day and the last development day, the day before the out-of-sample
	 * boundary of 2025-01-01 (ADR-0009): the limits of the start-date picker. */
	const FIRST_DAY = '2013-10-06';
	const LAST_DAY = '2024-12-31';

	const isDay = (value: string) =>
		/^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(Date.parse(`${value}T00:00:00Z`));

	let mode = $state<Mode>('hindsight');
	// The start date, a calendar day in UTC as the picker holds it ('' for the first stored
	// candle), shared by both modes and kept in the page address as `?from=`. It moves where
	// you start watching, never what a detector reads.
	const requested = page.url.searchParams.get('from') ?? '';
	let from = $state(isDay(requested) ? requested : '');
	/** Midnight UTC of the start date in Unix seconds; null without one. */
	const fromTime = $derived(from === '' ? null : Date.parse(`${from}T00:00:00Z`) / 1000);
	let timeframe = $state<Timeframe>('1h');
	let detector = $state(DETECTORS[0]);
	/** The strategy walked over the replay, drawn and scored next to the detector; '' for none. */
	let strategy = $state('');
	let loading = $state(false);
	let error = $state<string | null>(null);

	// Hindsight: the whole development period with its true tops and bottoms, at the reversal
	// size the API answered (8%: a picker is a later issue).
	let candles = $state.raw<Candle[]>([]);
	let turningPoints = $state.raw<TurningPoint[]>([]);
	let hindsightReversal = $state(0.08);

	// Replay: the candles of the detector's timeframe handed to it one at a time, over the
	// scoring period. `cursor` is how many candles have been shown; it only ever grows,
	// except on a restart or a new start date, which puts it back at `start`.
	let replay = $state.raw<Replay | null>(null);
	let cursor = $state(0);
	let playing = $state(false);
	let speed = $state(100);

	$effect(() => {
		const wanted = { mode, timeframe, detector, strategy };
		const current = () =>
			wanted.mode === mode &&
			wanted.timeframe === timeframe &&
			wanted.detector === detector &&
			wanted.strategy === strategy;
		loading = true;
		error = null;
		pause();
		const load =
			mode === 'hindsight'
				? Promise.all([fetchCandles(timeframe), fetchTurningPoints(timeframe)]).then(
						([c, p]) => {
							if (!current()) return;
							candles = c;
							turningPoints = p.turning_points;
							hindsightReversal = p.reversal;
						}
					)
				: fetchReplay(detector, strategy === '' ? null : strategy).then((r) => {
						if (!current()) return;
						replay = r;
						cursor = start;
					});
		load
			.catch((reason: unknown) => {
				if (current()) error = reason instanceof Error ? reason.message : String(reason);
			})
			.finally(() => {
				if (current()) loading = false;
			});
	});

	const total = $derived(replay?.candles.length ?? 0);
	/** Hindsight: the candle the view begins at. */
	const hindsightStart = $derived(startIndex(candles, fromTime));
	/** Replay: how many candles are shown at the start date, the first one on or after it
	 * being the next to appear. The detector has read them all: the replay jumps to the date
	 * with everything up to it shown as it stood then. */
	const start = $derived(replay ? startIndex(replay.candles, fromTime) : 0);
	const finished = $derived(replay !== null && cursor >= total);
	/** Start time of the latest shown candle; nothing later than this is visible. */
	const now = $derived(replay && cursor > 0 ? replay.candles[cursor - 1].time : -Infinity);
	const shownPoints = $derived(replay ? replay.turning_points.filter((p) => p.confirmed_at <= now) : []);
	/** The levels the detector sees at the latest shown candle, drawn up to that candle. */
	const shownLevels = $derived<ChartLine[]>(
		replay ? toLines(replay.levels, now, COLORS.level) : []
	);
	/** The swing extremes the detector reads at the latest shown candle, drawn likewise. */
	const shownExtremes = $derived<ChartLine[]>(
		replay ? toLines(replay.swing_extremes, now, COLORS.swingExtreme) : []
	);
	const shownMarks = $derived<ChartMark[]>(
		replay
			? replay.marks
					.filter((m) => m.time <= now)
					.map((m) => ({
						kind: m.kind,
						time: m.time,
						price: m.price,
						timing: m.timing,
						state: !m.scored
							? 'unscored'
							: m.settled_at <= now
								? m.hit
									? 'hit'
									: 'false'
								: 'pending'
					}))
			: []
	);
	/** The strategy's fills up to the latest shown candle, each on the candle it filled on. */
	const shownFills = $derived<ChartFill[]>(
		replay?.backtest
			? replay.backtest.fills
					.filter((f) => f.time <= now)
					.map((f) => ({ side: f.side, time: f.time, price: f.price }))
			: []
	);
	/** What the status line counts: only what came on or after the start date, so it tells
	 * what you are watching; the score below stays the whole scoring period's. */
	const since = (time: number) => fromTime === null || time >= fromTime;
	const watchedPoints = $derived(shownPoints.filter((p) => since(p.confirmed_at)));
	const watchedMarks = $derived(shownMarks.filter((m) => since(m.time)));
	const watchedFills = $derived(shownFills.filter((f) => since(f.time)));
	const tally = $derived({
		hits: watchedMarks.filter((m) => m.state === 'hit').length,
		false: watchedMarks.filter((m) => m.state === 'false').length,
		pending: watchedMarks.filter((m) => m.state === 'pending').length,
		unscored: watchedMarks.filter((m) => m.state === 'unscored').length
	});

	let frame: number | undefined;
	let lastTick = 0;
	let carry = 0;

	function tick(time: number) {
		if (!playing || !replay) return;
		carry += ((time - lastTick) / 1000) * speed;
		lastTick = time;
		const steps = Math.floor(carry);
		carry -= steps;
		if (steps > 0) cursor = Math.min(total, cursor + steps);
		if (cursor >= total) {
			playing = false;
			return;
		}
		frame = requestAnimationFrame(tick);
	}

	function play() {
		if (!replay || finished || playing) return;
		playing = true;
		lastTick = performance.now();
		carry = 0;
		frame = requestAnimationFrame(tick);
	}

	function pause() {
		playing = false;
		if (frame !== undefined) cancelAnimationFrame(frame);
		frame = undefined;
	}

	function step() {
		pause();
		if (replay && !finished) cursor += 1;
	}

	function restart() {
		pause();
		cursor = start;
	}

	/** A date picked (or cleared): keep it in the page address and start watching there. */
	function chooseFrom(value: string) {
		from = isDay(value) ? value : '';
		const url = new URL(page.url.href);
		if (from === '') url.searchParams.delete('from');
		else url.searchParams.set('from', from);
		void goto(url, { shallow: true, replace: true });
		restart();
	}

	const utc = (seconds: number) => new Date(seconds * 1000).toISOString().slice(0, 16) + 'Z';
	const percent = (fraction: number) => `${(fraction * 100).toFixed(1)}%`;
	/** A reversal size as the batch commands print it: 8%, 16%, 12.5%. */
	const reversalText = (fraction: number) => `${parseFloat((fraction * 100).toPrecision(4))}%`;
	/** The reversal size of the turning points on the chart: the detector's family's in
	 * Replay, the hindsight route's in Hindsight. */
	const shownReversal = $derived(
		mode === 'replay' && replay ? replay.reversal : hindsightReversal
	);
	const signed = (candles: number) => (candles > 0 ? `+${candles}` : `${candles}`);
	/** A growth as the batch command prints it: three significant figures after a times sign. */
	const growth = (value: number | null) =>
		value === null
			? 'n/a'
			: value >= 100
				? `×${value.toFixed(0)}`
				: value >= 10
					? `×${value.toFixed(1)}`
					: value >= 1
						? `×${value.toFixed(2)}`
						: `×${parseFloat(value.toPrecision(3))}`;
	const pct = (value: number | null) => (value === null ? 'n/a' : `${value.toFixed(1)}%`);
	const money = (value: number) =>
		value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
	const signedPct = (value: number) => `${value >= 0 ? '+' : ''}${value.toFixed(2)}%`;
	const plural = (n: number, word: string) => `${n} ${word}${n === 1 ? '' : 's'}`;

	/** The columns of every score table: the eras, then the whole period last. */
	const columns = (eras: { era: Era }[]) => [...eras.map((e) => e.era.name), 'whole period'];

	/** The detector's score as rows, one cell per era and one for the period, the turning
	 * points those of the detector's reversal size. The hit rate reads green at or above the
	 * 80% bar of ADR-0005 and red below it. */
	function detectorRows(score: Score, reversal: number): Row[] {
		const scores = [...score.eras.map((e) => e.score), score];
		const row = (
			label: string,
			title: string,
			text: (s: Score) => string,
			tone?: (s: Score) => Cell['tone']
		): Row => ({ label, title, cells: scores.map((s) => ({ text: text(s), tone: tone?.(s) })) });
		return [
			row(
				'turning points',
				`Tops and bottoms found in hindsight: the extreme before the market moved at least ${reversalText(reversal)}, the reversal size of the detector's family, the other way.`,
				(s) => String(s.turning_points)
			),
			row('marks', "The detector's claims, at most one per candle.", (s) => String(s.marks)),
			row(
				'hit rate',
				'Hits over turning points. The bar: at least 80% in every era (ADR-0005).',
				(s) => percent(s.hit_rate),
				(s) => (s.turning_points === 0 ? undefined : s.hit_rate >= 0.8 ? 'above' : 'below')
			),
			row('false-mark rate', 'False marks over marks.', (s) => percent(s.false_mark_rate)),
			row(
				'false marks per hit',
				'False marks over hits; reported, no bar (ADR-0007).',
				(s) => (s.marks > 0 && s.hits === 0 ? 'n/a' : s.false_marks_per_hit.toFixed(1))
			),
			row(
				'median timing',
				'Hourly candles a hit is early (negative) or late (positive) relative to its turning point.',
				(s) => (s.median_timing === null ? 'no hits' : `${signed(s.median_timing)} candles`)
			),
			row(
				'median give-up',
				"Percent from the turning point's extreme to the hit's close.",
				(s) => (s.median_give_up === null ? 'no hits' : `${s.median_give_up.toFixed(2)}%`)
			)
		];
	}

	/** Green when the span's growth is at least the benchmark's, red below: the bar of
	 * ADR-0008, judged per era under the perpetual. */
	const vsBenchmark = (s: StrategyScore): Cell['tone'] =>
		s.growth === null || s.benchmark_growth === null
			? undefined
			: s.growth >= s.benchmark_growth
				? 'above'
				: 'below';

	/** A strategy's score under one cost model as rows. Growth reads green at or above the
	 * benchmark's and red below it: the bar of ADR-0008, judged per era under the perpetual. */
	function strategyRows(score: StrategyScore): Row[] {
		const scores = [...score.eras.map((e) => e.score), score];
		const row = (
			label: string,
			title: string,
			text: (s: StrategyScore) => string,
			options: { tone?: (s: StrategyScore) => Cell['tone']; group?: boolean } = {}
		): Row => ({
			label,
			title,
			group: options.group,
			cells: scores.map((s) => ({ text: text(s), tone: options.tone?.(s) }))
		});
		const outcome = (hit: boolean) => (hit ? 'hit' : 'false');
		const groupCell = (s: StrategyScore, i: number) => {
			const g = s.groups[i];
			return g === undefined || g.trades === 0 || g.mean === null
				? '0'
				: `${g.trades} · ${signedPct(g.mean)}`;
		};
		const groupRow = (g: TradeGroup, i: number) =>
			row(
				`${outcome(g.opened_on_hit)} → ${outcome(g.closed_on_hit)}`,
				`Trades opened on a ${g.opened_on_hit ? 'hit' : 'false mark'} and closed on a ${g.closed_on_hit ? 'hit' : 'false mark'}: how many, and their mean result in percent of the account's value at entry.`,
				(s) => groupCell(s, i),
				{ group: i === 0 }
			);
		return [
			row(
				'growth',
				"The account's value at the period's last close over its value before the period. The bar: at least the benchmark's in every era under the perpetual cost model (ADR-0008).",
				(s) => growth(s.growth),
				{ tone: vsBenchmark }
			),
			row(
				'benchmark growth',
				'Buying Bitcoin once at the first candle of the scoring period with one spot fill, and holding.',
				(s) => growth(s.benchmark_growth)
			),
			row(
				'worst drawdown',
				"The largest fall of the account's value from an earlier peak within the period, in percent of that peak.",
				(s) => pct(s.worst_drawdown)
			),
			row('benchmark worst drawdown', 'The same, for the benchmark.', (s) =>
				pct(s.benchmark_worst_drawdown)
			),
			row('trades', 'Round trips opened in the period.', (s) => String(s.trades), { group: true }),
			row('fees (USD)', 'Taker fees paid on every fill.', (s) => money(s.fees)),
			row('funding (USD)', 'Funding paid at every hourly close while long; none under spot.', (s) =>
				money(s.funding)
			),
			row(
				'time long',
				"The share of the period's candles whose close found the account long.",
				(s) => percent(s.share_long)
			),
			...score.groups.map(groupRow),
			row(
				'20% halt, first',
				'The day a 20% drawdown halt would first have fired; reported, never applied.',
				(s) => (s.halt_at === null ? 'never' : utc(s.halt_at).slice(0, 10)),
				{ group: true }
			),
			row(
				'20% halt, episodes',
				'How many separate times the halt would have fired; a new episode needs a new peak first.',
				(s) => String(s.halt_episodes)
			)
		];
	}

	const day = (seconds: number) => utc(seconds).slice(0, 10);
	/** Dollars as a person reads them: whole dollars from 100 up, cents below. */
	const dollars = (value: number) =>
		value >= 100
			? value.toLocaleString('en-US', { maximumFractionDigits: 0 })
			: value.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
	/** A growth as the change it is: ×0.82 is −18%, ×2.43 is +143%. */
	const change = (growth: number | null) =>
		growth === null
			? 'n/a'
			: `${growth >= 1 ? '+' : '−'}${Math.abs((growth - 1) * 100).toFixed(0)}%`;
	/** The value of a series at the last hourly close before `end`; null when there is none. */
	function valueBefore(times: number[], values: number[], end: number): number | null {
		let low = 0;
		let high = times.length;
		while (low < high) {
			const mid = (low + high) >> 1;
			if (times[mid] < end) low = mid + 1;
			else high = mid;
		}
		return low === 0 ? null : values[low - 1];
	}
	/** Whether the detector's hit rate is at least 80% in every era (ADR-0005). */
	const detectorPasses = (score: Score) =>
		score.eras.length > 0 && score.eras.every((e) => e.score.hit_rate >= 0.8);
	const giveUp = (score: Score) =>
		score.median_give_up === null ? '' : `, its hits a median ${score.median_give_up.toFixed(2)}% from the extreme`;

	/** What the 500 USD became: the account under each cost model and the benchmark at the
	 * last hourly close of every era and of the period, with the change over that span, then
	 * the trades and what they cost. The short view; the full tables sit behind it. */
	function summaryRows(backtest: Backtest): Row[] {
		const { times, benchmark, accounts } = backtest.values;
		const spans = (score: StrategyScore) => [
			...score.eras.map((e) => ({ end: e.era.end, score: e.score })),
			{ end: Infinity, score }
		];
		const money = (values: number[], end: number, growth: number | null) => {
			const value = valueBefore(times, values, end);
			return value === null ? 'n/a' : `${dollars(value)} USD · ${change(growth)}`;
		};
		const rows: Row[] = perpetualFirst(backtest.scores).map((scored) => ({
			label: `account, ${scored.model}`,
			title:
				`What the 500 USD became under the ${scored.model} cost model at the end of each era and of the period, and the change over that span. ` +
				(scored.model === 'perpetual'
					? 'Green: at least what holding gave over the span, the bar of ADR-0008; red: less.'
					: 'Reported next to the perpetual; the bar is not judged under spot.'),
			cells: spans(scored.score).map(({ end, score }) => ({
				text: money(accounts[scored.model], end, score.growth),
				tone: vsBenchmark(score)
			}))
		}));
		const first = backtest.scores[0].score;
		rows.push({
			label: 'holding Bitcoin instead',
			title:
				'The benchmark: 500 USD of Bitcoin bought at the first candle of the scoring period with one spot fill and held.',
			cells: spans(first).map(({ end, score }) => ({
				text: money(benchmark, end, score.benchmark_growth)
			}))
		});
		rows.push({
			label: 'trades',
			title: 'Round trips opened in the span.',
			cells: spans(first).map(({ score }) => ({ text: String(score.trades) })),
			group: true
		});
		const perpetual = backtest.scores.find((s) => s.model === 'perpetual');
		if (perpetual !== undefined) {
			rows.push({
				label: 'fees and funding, perpetual',
				title: 'What those trades cost under the perpetual cost model, in USD.',
				cells: spans(perpetual.score).map(({ score }) => ({
					text: `${dollars(score.fees + score.funding)} USD`
				}))
			});
		}
		return rows;
	}

	/** The perpetual's table first, since the bar is judged under it. */
	const perpetualFirst = (scores: CostModelScore[]) => [
		...scores.filter((s) => s.model === 'perpetual'),
		...scores.filter((s) => s.model !== 'perpetual')
	];

	/** The bar of ADR-0008 as the batch command prints it: pass, or fail with the eras that
	 * fell short under the perpetual cost model. */
	function verdict(backtest: Backtest): string {
		if (backtest.passes) return 'pass';
		const perpetual = backtest.scores.find((s) => s.model === 'perpetual');
		const short = (perpetual?.score.eras ?? []).filter(
			(e) =>
				e.score.growth !== null &&
				e.score.benchmark_growth !== null &&
				e.score.growth < e.score.benchmark_growth
		);
		const detail = short.map((e) => e.era.name).join(', ');
		return detail === '' ? 'fail' : `fail: below holding in ${detail}`;
	}
</script>

<svelte:head>
	<title>TradingBot: XBTUSD turning points</title>
</svelte:head>

<main>
	<header>
		<h1>Kraken spot XBTUSD</h1>
		<div class="switch" role="group" aria-label="Mode">
			<button
				type="button"
				class:active={mode === 'hindsight'}
				aria-pressed={mode === 'hindsight'}
				onclick={() => (mode = 'hindsight')}
			>
				Hindsight
			</button>
			<button
				type="button"
				class:active={mode === 'replay'}
				aria-pressed={mode === 'replay'}
				onclick={() => (mode = 'replay')}
			>
				Replay
			</button>
		</div>
		<label>
			From
			<input
				type="date"
				min={FIRST_DAY}
				max={LAST_DAY}
				value={from}
				onchange={(event) => chooseFrom(event.currentTarget.value)}
			/>
		</label>
		{#if mode === 'hindsight'}
			<div class="switch" role="group" aria-label="Timeframe">
				{#each TIMEFRAMES as option (option)}
					<button
						type="button"
						class:active={option === timeframe}
						aria-pressed={option === timeframe}
						onclick={() => (timeframe = option)}
					>
						{option}
					</button>
				{/each}
			</div>
		{:else}
			<label>
				Detector
				<select bind:value={detector}>
					{#each DETECTORS as option (option)}
						<option value={option}>{option}</option>
					{/each}
				</select>
			</label>
			<label>
				Strategy
				<select bind:value={strategy}>
					<option value="">none</option>
					{#each STRATEGIES as option (option)}
						<option value={option}>{option}</option>
					{/each}
				</select>
			</label>
			<div class="controls" role="group" aria-label="Replay">
				{#if playing}
					<button type="button" onclick={pause}>Pause</button>
				{:else}
					<button type="button" onclick={play} disabled={!replay || finished}>Play</button>
				{/if}
				<button type="button" onclick={step} disabled={!replay || finished || playing}>Step</button>
				<label>
					Speed
					<select bind:value={speed}>
						{#each SPEEDS as option (option)}
							<option value={option}>{option} candles/s</option>
						{/each}
					</select>
				</label>
				<button type="button" onclick={restart} disabled={!replay || cursor === start}>Restart</button>
			</div>
		{/if}
		<p class="status">
			{#if loading}
				Loading…
			{:else if error}
				<span class="error">{error}</span>
			{:else if mode === 'hindsight'}
				{#if candles.length === 0}
					No {timeframe} candles in the development period (before 2025-01-01). Import an
					archive that covers it.
				{:else}
					{candles.length.toLocaleString()} {timeframe} candles from {utc(candles[0].time)} to {utc(
						candles[candles.length - 1].time
					)}, {turningPoints.length} turning points
				{/if}
			{:else if replay}
				{#if total === 0}
					No {replay.timeframe} candles in the development period (before 2025-01-01). Import an
					archive that covers it.
				{:else}
					{replay.timeframe} candle {cursor.toLocaleString()} of {total.toLocaleString()}{cursor > 0
						? `, ${utc(now)}`
						: ''}: {watchedPoints.length} turning points confirmed, {shownLevels.length} levels active,
					{shownExtremes.length} swing extremes standing, {watchedMarks.length} marks placed, {tally.hits} hits, {tally.false} false, {tally.pending} pending, {tally.unscored} before the scoring period{replay.backtest
						? `, ${watchedFills.length} fills`
						: ''}
				{/if}
			{/if}
		</p>
	</header>
	{#if mode === 'replay' && replay && total > 0}
		<div class="score">
			<p class="summary">
				<strong>{replay.detector}</strong> (reversal size {reversalText(replay.reversal)}) found {replay
					.score.hits} of {replay.score.turning_points}
				turning points ({percent(replay.score.hit_rate)}; per era {replay.score.eras
					.map((e) => percent(e.score.hit_rate))
					.join(', ')}) and placed {replay.score.false_marks_per_hit.toFixed(1)} false marks for every
				hit{giveUp(replay.score)}. <strong>Bar (ADR-0005)</strong>, at least 80% in every era:
				<strong class={detectorPasses(replay.score) ? 'pass' : 'fail'}
					>{detectorPasses(replay.score) ? 'pass' : 'fail'}</strong
				>
			</p>
			{#if replay.backtest}
				<p class="summary">
					<strong>{replay.backtest.strategy}</strong> on {replay.backtest.detector}: 500 USD from
					{day(replay.backtest.scored_from)} to {day(
						replay.backtest.values.times[replay.backtest.values.times.length - 1]
					)}, where the stored development data ends (later candles are kept for out-of-sample
					checks). <strong>Bar (ADR-0008)</strong>, at least what holding gave in every era under the
					perpetual cost model:
					<strong class={replay.backtest.passes ? 'pass' : 'fail'}>{verdict(replay.backtest)}</strong>
				</p>
				<div class="tables">
					<ScoreTable
						caption="what the 500 USD became"
						columns={columns(replay.backtest.scores[0].score.eras)}
						rows={summaryRows(replay.backtest)}
					/>
				</div>
			{/if}
			<details>
				<summary>every number, as the batch commands print them</summary>
				<div class="tables">
					<ScoreTable
						caption="{replay.detector} on {replay.timeframe} candles over the scoring period, turning points at {reversalText(
							replay.reversal
						)}"
						columns={columns(replay.score.eras)}
						rows={detectorRows(replay.score, replay.reversal)}
					/>
				</div>
				{#if replay.backtest}
					<div class="tables">
						{#each perpetualFirst(replay.backtest.scores) as scored (scored.model)}
							<ScoreTable
								caption="under the {scored.model} cost model{scored.model === 'perpetual'
									? ' (the bar)'
									: ' (reported, no bar)'}"
								columns={columns(scored.score.eras)}
								rows={strategyRows(scored.score)}
							/>
						{/each}
					</div>
				{/if}
			</details>
		</div>
	{/if}
	{#if mode === 'hindsight'}
		<CandleChart {candles} start={hindsightStart} {turningPoints} />
	{:else}
		<CandleChart
			candles={replay?.candles ?? []}
			visible={cursor}
			{start}
			turningPoints={shownPoints}
			lines={[...shownLevels, ...shownExtremes]}
			marks={shownMarks}
			fills={shownFills}
		/>
	{/if}
	<p class="legend">
		<span class="dot"></span> turning point ({reversalText(shownReversal)} reversal, in hindsight)
		{#if mode === 'replay' && replay && !loading}
			{#if replay.levels.length > 0}
				· <span class="level">orange line</span> level the detector sees (zone within 1%)
			{/if}
			{#if replay.swing_extremes.length > 0}
				· <span class="extreme">purple line</span> swing extreme the detector reads (a mark on the
				first candle short of it, once the swing is {reversalText(replay.reversal)})
			{/if}
			· <span class="arrow">▼</span> top mark · <span class="arrow">▲</span> bottom mark ·
			<span class="unscored">light grey</span> before the scoring period (2016) ·
			<span class="pending">grey</span> pending · <span class="hit">green</span> hit ·
			<span class="false">red</span> false mark
			{#if replay.backtest}
				· <span class="buy">■</span> buy · <span class="sell">■</span> sell, each on the candle it
				filled on (the next candle's open after the mark)
			{/if}
		{/if}
	</p>
</main>

<style>
	:global(body) {
		margin: 0;
		font-family: system-ui, sans-serif;
		color: #222;
		background: #fff;
	}
	main {
		padding: 16px;
	}
	header {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 16px;
		margin-bottom: 12px;
	}
	h1 {
		font-size: 1.25rem;
		margin: 0;
	}
	.switch {
		display: inline-flex;
		border: 1px solid #ccc;
		border-radius: 6px;
		overflow: hidden;
	}
	.switch button {
		border: 0;
		background: #fff;
		padding: 6px 14px;
		font: inherit;
		cursor: pointer;
	}
	.switch button + button {
		border-left: 1px solid #ccc;
	}
	.switch button.active {
		background: #222;
		color: #fff;
	}
	.controls {
		display: inline-flex;
		align-items: center;
		gap: 8px;
	}
	.controls button {
		border: 1px solid #ccc;
		border-radius: 6px;
		background: #fff;
		padding: 6px 14px;
		font: inherit;
		cursor: pointer;
	}
	.controls button:disabled {
		color: #999;
		cursor: default;
	}
	label {
		font-size: 0.9rem;
		color: #444;
	}
	select,
	input {
		font: inherit;
		margin-left: 4px;
	}
	.status,
	.score,
	.legend {
		margin: 0;
		color: #666;
		font-size: 0.9rem;
	}
	.score {
		margin-bottom: 12px;
	}
	.tables {
		display: flex;
		flex-wrap: wrap;
		gap: 8px 32px;
		align-items: flex-start;
	}
	.summary {
		margin: 0 0 6px;
		color: #333;
	}
	details {
		margin-top: 6px;
	}
	summary {
		cursor: pointer;
		color: #666;
	}
	details .tables {
		margin-top: 8px;
	}
	.pass {
		color: #2e7d32;
	}
	.fail {
		color: #c62828;
	}
	.legend {
		margin-top: 8px;
	}
	.error {
		color: #c62828;
	}
	.dot {
		display: inline-block;
		width: 10px;
		height: 10px;
		border-radius: 50%;
		background: #2962ff;
		vertical-align: middle;
	}
	.arrow {
		color: #444;
	}
	.level {
		color: #ff9800;
	}
	.extreme {
		color: #8e24aa;
	}
	.unscored {
		color: #bdbdbd;
	}
	.pending {
		color: #9e9e9e;
	}
	.hit {
		color: #2e7d32;
	}
	.false {
		color: #c62828;
	}
	.buy {
		color: #00838f;
	}
	.sell {
		color: #ad1457;
	}
</style>
