<script lang="ts">
	import {
		demoteLive,
		fetchLiveStatus,
		fetchLiveTrades,
		fetchStrategies,
		pauseLive,
		promoteStrategy,
		resumeLive,
		type LiveState,
		type LiveStatus,
		type PaperTrade,
		type StrategyConfig
	} from '$lib/api';

	let status = $state<LiveStatus | null>(null);
	let trades = $state<PaperTrade[]>([]);
	let strategies = $state<StrategyConfig[]>([]);
	let error = $state<string | null>(null);
	let loaded = $state(false);
	let busy = $state(false);
	let selectedName = $state('');

	$effect(() => {
		void load();
	});

	async function load(): Promise<void> {
		try {
			[status, trades, strategies] = await Promise.all([
				fetchLiveStatus(),
				fetchLiveTrades(),
				fetchStrategies()
			]);
			error = null;
		} catch {
			error =
				'Cannot reach the live API. Start the runner and API from backend/, or check that /live endpoints are up.';
		} finally {
			loaded = true;
		}
	}

	// Run a control action, refresh trades on success, and surface any API error
	// the same way the rest of the dashboard does. Buttons stay disabled while busy.
	async function run(action: () => Promise<LiveStatus>): Promise<void> {
		busy = true;
		try {
			status = await action();
			trades = await fetchLiveTrades();
			error = null;
		} catch (e) {
			error = e instanceof Error ? e.message : 'Action failed';
		} finally {
			busy = false;
		}
	}

	function promote(): void {
		if (selectedName === '') return;
		void run(() => promoteStrategy(selectedName));
	}

	const money = (x: string | number | null): string =>
		x === null || x === ''
			? 'n/a'
			: Number(x).toLocaleString('en-US', { maximumFractionDigits: 2 });
	const qty = (x: string | number): string =>
		Number(x).toLocaleString('en-US', { maximumFractionDigits: 6 });
	const dateTime = (iso: string | null): string =>
		iso === null ? 'n/a' : iso.slice(0, 16).replace('T', ' ');

	const stateBadge = (state: LiveState): string => {
		switch (state) {
			case 'running':
				return 'bg-green-100 text-green-800';
			case 'paused':
				return 'bg-amber-100 text-amber-800';
			default:
				return 'bg-gray-100 text-gray-600';
		}
	};

	const pnlClass = (x: string | number): string =>
		Number(x) >= 0 ? 'text-green-700' : 'text-red-700';
	const sideLabel = (side: 'buy' | 'sell'): string => (side === 'buy' ? 'Long' : 'Short');
	const reasonLabel: Record<PaperTrade['exit_reason'], string> = {
		signal: 'Signal',
		stop_loss: 'Stop loss',
		take_profit: 'Take profit',
		time: 'Time'
	};

	const isPromoted = $derived(status !== null && status.state !== 'idle');
</script>

<section class="space-y-3">
	<h2 class="text-lg font-medium text-gray-900">Paper trading</h2>
	<p class="text-sm text-gray-500">
		The promoted strategy running live on paper — one tick per 1H bar, same code path as the
		backtest, pessimistic costs.
	</p>

	{#if error}
		<p class="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
			{error}
		</p>
	{/if}

	{#if status}
		<div class="space-y-4 rounded-lg border border-gray-200 p-4">
			<div class="flex flex-wrap items-center gap-3">
				<span
					class="rounded-full px-2.5 py-0.5 text-xs font-medium tracking-wide uppercase {stateBadge(
						status.state
					)}"
				>
					{status.state}
				</span>
				<span class="text-sm text-gray-600">
					Strategy: <span class="font-medium text-gray-900"
						>{status.promoted_strategy ?? 'none'}</span
					>
				</span>
				<span class="text-sm text-gray-500">Last tick: {dateTime(status.last_tick_at)}</span>
			</div>

			<div class="grid grid-cols-2 gap-4 sm:grid-cols-3">
				<div>
					<div class="text-xs tracking-wide text-gray-500 uppercase">Initial capital</div>
					<div class="text-gray-900 tabular-nums">{money(status.initial_capital)}</div>
				</div>
				<div>
					<div class="text-xs tracking-wide text-gray-500 uppercase">Cash</div>
					<div class="text-gray-900 tabular-nums">{money(status.cash)}</div>
				</div>
				<div>
					<div class="text-xs tracking-wide text-gray-500 uppercase">Equity</div>
					<div class="text-gray-900 tabular-nums">{money(status.equity)}</div>
				</div>
			</div>

			{#if status.position}
				{@const p = status.position}
				<div class="rounded-md border border-gray-200 bg-gray-50 p-3">
					<div class="mb-2 text-xs tracking-wide text-gray-500 uppercase">Open position</div>
					<div class="grid grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-3 lg:grid-cols-6">
						<div>
							<div class="text-xs text-gray-500">Side</div>
							<div class="font-medium {p.side === 'buy' ? 'text-green-700' : 'text-red-700'}">
								{sideLabel(p.side)}
							</div>
						</div>
						<div>
							<div class="text-xs text-gray-500">Quantity</div>
							<div class="text-gray-900 tabular-nums">{qty(p.quantity)}</div>
						</div>
						<div>
							<div class="text-xs text-gray-500">Entry</div>
							<div class="text-gray-900 tabular-nums">{money(p.entry_price)}</div>
						</div>
						<div>
							<div class="text-xs text-gray-500">Stop</div>
							<div class="text-gray-900 tabular-nums">{money(p.stop)}</div>
						</div>
						<div>
							<div class="text-xs text-gray-500">Take profit</div>
							<div class="text-gray-900 tabular-nums">{money(p.take_profit)}</div>
						</div>
						<div>
							<div class="text-xs text-gray-500">Bars held</div>
							<div class="text-gray-900 tabular-nums">{p.bars_held}</div>
						</div>
					</div>
				</div>
			{:else}
				<p class="text-sm text-gray-500">No open position.</p>
			{/if}

			<div class="flex flex-wrap items-center gap-2 border-t border-gray-100 pt-3">
				{#if status.state === 'running'}
					<button
						class="rounded-md bg-amber-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-50"
						disabled={busy}
						onclick={() => void run(pauseLive)}
					>
						Pause
					</button>
				{:else if status.state === 'paused'}
					<button
						class="rounded-md bg-green-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
						disabled={busy}
						onclick={() => void run(resumeLive)}
					>
						Resume
					</button>
				{/if}

				{#if isPromoted}
					<button
						class="rounded-md border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-50 disabled:opacity-50"
						disabled={busy}
						onclick={() => void run(demoteLive)}
					>
						Demote
					</button>
				{/if}

				<div class="ml-auto flex items-center gap-2">
					<select
						class="rounded-md border border-gray-300 px-2 py-1.5 text-sm text-gray-700 disabled:opacity-50"
						bind:value={selectedName}
						disabled={busy || strategies.length === 0}
					>
						<option value="" disabled>Select a strategy…</option>
						{#each strategies as strategy (strategy.id)}
							<option value={strategy.name}>{strategy.name}</option>
						{/each}
					</select>
					<button
						class="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
						disabled={busy || selectedName === ''}
						onclick={promote}
					>
						Promote
					</button>
				</div>
			</div>
		</div>
	{:else if loaded && !error}
		<p class="text-sm text-gray-500">No live status available yet.</p>
	{/if}

	<h3 class="text-base font-medium text-gray-900">Paper trades</h3>
	{#if trades.length === 0 && loaded}
		<p class="text-sm text-gray-500">
			No paper trades yet — they appear once the runner closes a position.
		</p>
	{:else if trades.length > 0}
		<div class="overflow-x-auto rounded-lg border border-gray-200">
			<table class="min-w-full divide-y divide-gray-200 text-sm">
				<thead class="bg-gray-50 text-left text-xs tracking-wide text-gray-500 uppercase">
					<tr>
						<th class="px-4 py-2">Exit time</th>
						<th class="px-4 py-2">Side</th>
						<th class="px-4 py-2 text-right">Quantity</th>
						<th class="px-4 py-2 text-right">Entry → Exit</th>
						<th class="px-4 py-2 text-right">P&L</th>
						<th class="px-4 py-2">Exit reason</th>
					</tr>
				</thead>
				<tbody class="divide-y divide-gray-100">
					{#each trades as trade (trade.id)}
						<tr>
							<td class="px-4 py-2 text-gray-600">{dateTime(trade.exit_time)}</td>
							<td
								class="px-4 py-2 font-medium {trade.side === 'buy'
									? 'text-green-700'
									: 'text-red-700'}"
							>
								{sideLabel(trade.side)}
							</td>
							<td class="px-4 py-2 text-right tabular-nums">{qty(trade.quantity)}</td>
							<td class="px-4 py-2 text-right text-gray-600 tabular-nums">
								{money(trade.entry_price)} → {money(trade.exit_price)}
							</td>
							<td class="px-4 py-2 text-right font-medium tabular-nums {pnlClass(trade.pnl)}">
								{money(trade.pnl)}
							</td>
							<td class="px-4 py-2 text-gray-600">{reasonLabel[trade.exit_reason]}</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</section>
