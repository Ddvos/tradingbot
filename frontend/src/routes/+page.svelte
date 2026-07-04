<script lang="ts">
	import {
		fetchBacktests,
		fetchEquityCurve,
		fetchWalkforwardDetail,
		fetchWalkforwardEquity,
		fetchWalkforwardRuns,
		type BacktestRun,
		type EquityPoint,
		type WalkforwardDetail,
		type WalkforwardRun
	} from '$lib/api';
	import EquityChart from '$lib/EquityChart.svelte';

	let runs = $state<BacktestRun[]>([]);
	let selected = $state<BacktestRun | null>(null);
	let points = $state<EquityPoint[]>([]);
	let error = $state<string | null>(null);
	let loaded = $state(false);

	let wfRuns = $state<WalkforwardRun[]>([]);
	let wfDetail = $state<WalkforwardDetail | null>(null);
	let wfPoints = $state<EquityPoint[]>([]);
	let wfError = $state<string | null>(null);
	let wfLoaded = $state(false);

	$effect(() => {
		fetchBacktests()
			.then((result) => {
				runs = result;
				loaded = true;
				const first = result[0];
				if (first) void selectRun(first);
			})
			.catch(() => {
				error =
					'Cannot reach the API. Start it from backend/ with: uv run uvicorn tradingbot.api.app:app --reload';
				loaded = true;
			});
	});

	$effect(() => {
		fetchWalkforwardRuns()
			.then((result) => {
				wfRuns = result;
				wfLoaded = true;
				const first = result[0];
				if (first) void selectWfRun(first);
			})
			.catch(() => {
				wfLoaded = true; // the backtests effect already reports API-down
			});
	});

	async function selectRun(run: BacktestRun): Promise<void> {
		selected = run;
		try {
			points = (await fetchEquityCurve(run.id)).points;
			error = null;
		} catch {
			points = [];
			error = `Could not load the equity curve for ${run.strategy} (is the Parquet file still there?).`;
		}
	}

	async function selectWfRun(run: WalkforwardRun): Promise<void> {
		try {
			[wfDetail, wfPoints] = await Promise.all([
				fetchWalkforwardDetail(run.symbol, run.run),
				fetchWalkforwardEquity(run.symbol, run.run).then((curve) => curve.points)
			]);
			wfError = null;
		} catch {
			wfDetail = null;
			wfPoints = [];
			wfError = `Could not load walk-forward run ${run.run} (are its Parquet files still there?).`;
		}
	}

	const pct = (x: number): string => `${(x * 100).toFixed(1)}%`;
	const money = (x: string): string =>
		Number(x).toLocaleString('en-US', { maximumFractionDigits: 2 });
	const day = (iso: string): string => iso.slice(0, 10);
	const fixed = (x: number | null, digits = 2): string => (x === null ? 'n/a' : x.toFixed(digits));
	const pctOrNa = (x: number | null): string => (x === null ? 'n/a' : pct(x));
</script>

<svelte:head>
	<title>TradingBot dashboard</title>
</svelte:head>

<main class="mx-auto max-w-5xl space-y-8 px-4 py-8">
	<header>
		<h1 class="text-2xl font-semibold text-gray-900">TradingBot</h1>
		<p class="text-sm text-gray-500">PF_XBTUSD backtests — honest numbers, pessimistic costs</p>
	</header>

	{#if error}
		<p class="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
			{error}
		</p>
	{/if}

	<section class="space-y-3">
		<h2 class="text-lg font-medium text-gray-900">Backtest runs</h2>
		{#if runs.length === 0 && loaded && !error}
			<p class="text-sm text-gray-500">
				No runs saved yet. Run one from backend/ with:
				<code class="rounded bg-gray-100 px-1 py-0.5"
					>uv run python scripts/backtest.py --strategy buy_and_hold --save</code
				>
			</p>
		{:else if runs.length > 0}
			<div class="overflow-x-auto rounded-lg border border-gray-200">
				<table class="min-w-full divide-y divide-gray-200 text-sm">
					<thead class="bg-gray-50 text-left text-xs tracking-wide text-gray-500 uppercase">
						<tr>
							<th class="px-4 py-2">Strategy</th>
							<th class="px-4 py-2">Timeframe</th>
							<th class="px-4 py-2">Period</th>
							<th class="px-4 py-2 text-right">Sharpe</th>
							<th class="px-4 py-2 text-right">Max DD</th>
							<th class="px-4 py-2 text-right">Final equity</th>
							<th class="px-4 py-2 text-right">Trades</th>
						</tr>
					</thead>
					<tbody class="divide-y divide-gray-100">
						{#each runs as run (run.id)}
							<tr
								class="cursor-pointer hover:bg-blue-50 {selected?.id === run.id
									? 'bg-blue-50'
									: ''}"
								onclick={() => void selectRun(run)}
							>
								<td class="px-4 py-2 font-medium text-gray-900">{run.strategy}</td>
								<td class="px-4 py-2 text-gray-600">{run.timeframe}</td>
								<td class="px-4 py-2 text-gray-600">
									{day(run.data_start)} → {day(run.data_end)}
								</td>
								<td class="px-4 py-2 text-right tabular-nums">{run.sharpe.toFixed(2)}</td>
								<td class="px-4 py-2 text-right tabular-nums">{pct(run.max_drawdown)}</td>
								<td class="px-4 py-2 text-right tabular-nums">{money(run.final_equity)}</td>
								<td class="px-4 py-2 text-right tabular-nums">{run.n_trades}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
	</section>

	{#if selected && points.length > 0}
		<section class="space-y-3">
			<h2 class="text-lg font-medium text-gray-900">
				Equity curve — {selected.strategy}
				<span class="ml-2 text-sm font-normal text-gray-500">
					{money(selected.initial_capital)} → {money(selected.final_equity)}
				</span>
			</h2>
			<div class="rounded-lg border border-gray-200 p-2">
				<EquityChart {points} />
			</div>
		</section>
	{/if}

	<section class="space-y-3">
		<h2 class="text-lg font-medium text-gray-900">Walk-forward evaluations</h2>
		<p class="text-sm text-gray-500">
			The honest ML verdicts: per-fold retraining, out-of-sample test windows only. Not comparable
			to the full-history backtests above — different periods, different procedure.
		</p>
		{#if wfError}
			<p class="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
				{wfError}
			</p>
		{/if}
		{#if wfRuns.length === 0 && wfLoaded}
			<p class="text-sm text-gray-500">
				No walk-forward runs yet. Run one from backend/ with:
				<code class="rounded bg-gray-100 px-1 py-0.5">uv run python scripts/walkforward.py</code>
			</p>
		{:else if wfRuns.length > 0}
			<div class="overflow-x-auto rounded-lg border border-gray-200">
				<table class="min-w-full divide-y divide-gray-200 text-sm">
					<thead class="bg-gray-50 text-left text-xs tracking-wide text-gray-500 uppercase">
						<tr>
							<th class="px-4 py-2">Model</th>
							<th class="px-4 py-2">Timeframe</th>
							<th class="px-4 py-2">OOS period</th>
							<th class="px-4 py-2 text-right">Folds</th>
							<th class="px-4 py-2 text-right">OOS Sharpe</th>
							<th class="px-4 py-2 text-right">Max DD</th>
							<th class="px-4 py-2 text-right">Final equity</th>
						</tr>
					</thead>
					<tbody class="divide-y divide-gray-100">
						{#each wfRuns as run (run.symbol + run.run)}
							<tr
								class="cursor-pointer hover:bg-blue-50 {wfDetail?.summary.run === run.run
									? 'bg-blue-50'
									: ''}"
								onclick={() => void selectWfRun(run)}
							>
								<td class="px-4 py-2 font-medium text-gray-900">{run.name}</td>
								<td class="px-4 py-2 text-gray-600">{run.timeframe}</td>
								<td class="px-4 py-2 text-gray-600">
									{day(run.test_start)} → {day(run.test_end)}
								</td>
								<td class="px-4 py-2 text-right tabular-nums">{run.n_folds}</td>
								<td class="px-4 py-2 text-right tabular-nums">{run.oos_sharpe.toFixed(2)}</td>
								<td class="px-4 py-2 text-right tabular-nums">{pct(run.oos_max_drawdown)}</td>
								<td class="px-4 py-2 text-right tabular-nums">
									{run.final_equity.toLocaleString('en-US', { maximumFractionDigits: 0 })}
								</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>
		{/if}
	</section>

	{#if wfDetail}
		<section class="space-y-3">
			<h2 class="text-lg font-medium text-gray-900">
				Out-of-sample equity — {wfDetail.summary.name}
				<span class="ml-2 text-sm font-normal text-gray-500">
					{wfDetail.summary.initial_equity.toLocaleString('en-US', {
						maximumFractionDigits: 0
					})} → {wfDetail.summary.final_equity.toLocaleString('en-US', {
						maximumFractionDigits: 0
					})} (test windows stitched)
				</span>
			</h2>
			{#if wfPoints.length > 0}
				<div class="rounded-lg border border-gray-200 p-2">
					<EquityChart points={wfPoints} />
				</div>
			{/if}

			<h3 class="text-base font-medium text-gray-900">Per fold</h3>
			<div class="overflow-x-auto rounded-lg border border-gray-200">
				<table class="min-w-full divide-y divide-gray-200 text-sm">
					<thead class="bg-gray-50 text-left text-xs tracking-wide text-gray-500 uppercase">
						<tr>
							<th class="px-4 py-2">Fold</th>
							<th class="px-4 py-2">Test window</th>
							<th class="px-4 py-2 text-right">AUC</th>
							<th class="px-4 py-2 text-right">IC</th>
							<th class="px-4 py-2 text-right">Sharpe</th>
							<th class="px-4 py-2 text-right">Max DD</th>
							<th class="px-4 py-2 text-right">Trades</th>
							<th class="px-4 py-2 text-right">Win</th>
							<th class="px-4 py-2 text-right">PF</th>
						</tr>
					</thead>
					<tbody class="divide-y divide-gray-100">
						{#each wfDetail.folds as fold (fold.fold)}
							<tr>
								<td class="px-4 py-2 tabular-nums">{fold.fold}</td>
								<td class="px-4 py-2 text-gray-600">
									{day(fold.test_start)} → {day(fold.test_end)}
								</td>
								<td class="px-4 py-2 text-right tabular-nums">{fixed(fold.auc, 3)}</td>
								<td class="px-4 py-2 text-right tabular-nums">{fixed(fold.ic, 3)}</td>
								<td class="px-4 py-2 text-right tabular-nums">{fixed(fold.sharpe)}</td>
								<td class="px-4 py-2 text-right tabular-nums">{pctOrNa(fold.max_drawdown)}</td>
								<td class="px-4 py-2 text-right tabular-nums">{fold.n_trades}</td>
								<td class="px-4 py-2 text-right tabular-nums">{fixed(fold.win_rate)}</td>
								<td class="px-4 py-2 text-right tabular-nums">{fixed(fold.profit_factor)}</td>
							</tr>
						{/each}
					</tbody>
				</table>
			</div>

			<h3 class="text-base font-medium text-gray-900">Report</h3>
			<pre
				class="overflow-x-auto rounded-lg border border-gray-200 bg-gray-50 p-4 text-xs leading-relaxed whitespace-pre-wrap text-gray-800">{wfDetail.report}</pre>
		</section>
	{/if}
</main>
