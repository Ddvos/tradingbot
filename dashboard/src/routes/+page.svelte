<script lang="ts">
	import CandleChart from '#lib/CandleChart.svelte';
	import {
		DETECTORS,
		fetchCandles,
		fetchReplay,
		fetchTurningPoints,
		TIMEFRAMES,
		type Candle,
		type Replay,
		type Score,
		type Timeframe,
		type TurningPoint
	} from '#lib/api.ts';
	import type { ChartLevel, ChartMark } from '#lib/chart.ts';

	type Mode = 'hindsight' | 'replay';
	const SPEEDS = [1, 10, 100, 1000];

	let mode = $state<Mode>('hindsight');
	let timeframe = $state<Timeframe>('1h');
	let detector = $state(DETECTORS[0]);
	let loading = $state(false);
	let error = $state<string | null>(null);

	// Hindsight: the whole development period with its true tops and bottoms.
	let candles = $state.raw<Candle[]>([]);
	let turningPoints = $state.raw<TurningPoint[]>([]);

	// Replay: the same hourly candles handed to the detector one at a time. `cursor` is how
	// many candles have been shown; it only ever grows, except on a restart to zero.
	let replay = $state.raw<Replay | null>(null);
	let cursor = $state(0);
	let playing = $state(false);
	let speed = $state(100);

	$effect(() => {
		const wanted = { mode, timeframe, detector };
		const current = () =>
			wanted.mode === mode && wanted.timeframe === timeframe && wanted.detector === detector;
		loading = true;
		error = null;
		pause();
		const load =
			mode === 'hindsight'
				? Promise.all([fetchCandles(timeframe), fetchTurningPoints(timeframe)]).then(
						([c, p]) => {
							if (!current()) return;
							candles = c;
							turningPoints = p;
						}
					)
				: fetchReplay(detector).then((r) => {
						if (!current()) return;
						replay = r;
						cursor = 0;
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
	const finished = $derived(replay !== null && cursor >= total);
	/** Start time of the latest shown candle; nothing later than this is visible. */
	const now = $derived(replay && cursor > 0 ? replay.candles[cursor - 1].time : -Infinity);
	const shownPoints = $derived(replay ? replay.turning_points.filter((p) => p.confirmed_at <= now) : []);
	/** The levels the detector sees at the latest shown candle, drawn up to that candle. */
	const shownLevels = $derived<ChartLevel[]>(
		replay
			? replay.levels
					.filter((l) => l.active_from <= now && (l.active_until === null || now <= l.active_until))
					.map((l) => ({ kind: l.kind, time: l.time, price: l.price, from: l.active_from, to: now }))
			: []
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
						state: m.settled_at <= now ? (m.hit ? 'hit' : 'false') : 'pending'
					}))
			: []
	);
	const tally = $derived({
		hits: shownMarks.filter((m) => m.state === 'hit').length,
		false: shownMarks.filter((m) => m.state === 'false').length,
		pending: shownMarks.filter((m) => m.state === 'pending').length
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
		cursor = 0;
	}

	const utc = (seconds: number) => new Date(seconds * 1000).toISOString().slice(0, 16) + 'Z';
	const percent = (fraction: number) => `${(fraction * 100).toFixed(1)}%`;
	const signed = (candles: number) => (candles > 0 ? `+${candles}` : `${candles}`);

	function describe(score: Score): string {
		const timing =
			score.median_timing === null
				? 'no hits'
				: `median timing ${signed(score.median_timing)} candles, median give-up ${score.median_give_up?.toFixed(2)}%`;
		return (
			`${score.turning_points} turning points, ${score.marks} marks, ` +
			`hit rate ${percent(score.hit_rate)}, false-mark rate ${percent(score.false_mark_rate)}, ${timing}`
		);
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
				<button type="button" onclick={restart} disabled={!replay || cursor === 0}>Restart</button>
			</div>
		{/if}
		<p class="status">
			{#if loading}
				Loading…
			{:else if error}
				<span class="error">{error}</span>
			{:else if mode === 'hindsight'}
				{#if candles.length === 0}
					No candles in the development period (before 2024-10-19). Import an archive that
					covers it.
				{:else}
					{candles.length.toLocaleString()} candles from {utc(candles[0].time)} to {utc(
						candles[candles.length - 1].time
					)}, {turningPoints.length} turning points
				{/if}
			{:else if replay}
				{#if total === 0}
					No candles in the development period (before 2024-10-19). Import an archive that
					covers it.
				{:else}
					Candle {cursor.toLocaleString()} of {total.toLocaleString()}{cursor > 0
						? `, ${utc(now)}`
						: ''}: {shownPoints.length} turning points confirmed, {shownLevels.length} levels active,
					{shownMarks.length} marks placed, {tally.hits} hits, {tally.false} false, {tally.pending} pending
				{/if}
			{/if}
		</p>
	</header>
	{#if mode === 'replay' && replay && total > 0}
		<p class="score">
			<strong>{replay.detector}</strong> over the development period: {describe(replay.score)}
		</p>
	{/if}
	{#if mode === 'hindsight'}
		<CandleChart {candles} {turningPoints} />
	{:else}
		<CandleChart
			candles={replay?.candles ?? []}
			visible={cursor}
			turningPoints={shownPoints}
			levels={shownLevels}
			marks={shownMarks}
		/>
	{/if}
	<p class="legend">
		<span class="dot"></span> turning point (8% reversal, in hindsight) · <span class="level"
			>orange line</span
		> level the detector sees (zone within 1%) · <span class="arrow">▼</span> top mark ·
		<span class="arrow">▲</span> bottom mark · <span class="pending">grey</span> pending ·
		<span class="hit">green</span> hit · <span class="false">red</span> false mark
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
	select {
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
	.pending {
		color: #9e9e9e;
	}
	.hit {
		color: #2e7d32;
	}
	.false {
		color: #c62828;
	}
</style>
