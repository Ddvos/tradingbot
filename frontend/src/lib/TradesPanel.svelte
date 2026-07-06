<script lang="ts">
	import {
		CandlestickSeries,
		createChart,
		createSeriesMarkers,
		LineSeries,
		LineStyle,
		type IChartApi,
		type ISeriesApi,
		type SeriesMarker,
		type UTCTimestamp
	} from 'lightweight-charts';
	import type { Candle, TradeMark } from '$lib/api';

	let { candles, trades }: { candles: Candle[]; trades: TradeMark[] } = $props();

	let container = $state<HTMLDivElement>();
	let selected = $state<TradeMark | null>(null);

	// Chart handles live outside $state: they are imperative lightweight-charts
	// objects, not data the template renders from.
	let chart: IChartApi | undefined;
	let priceSeries: ISeriesApi<'Candlestick'> | undefined;
	let levelSeries: ISeriesApi<'Line'>[] = [];

	const toTime = (iso: string): UTCTimestamp => (Date.parse(iso) / 1000) as UTCTimestamp;

	const REASON_COLOR: Record<string, string> = {
		stop_loss: '#dc2626',
		take_profit: '#16a34a',
		time: '#6b7280',
		signal: '#2563eb'
	};

	$effect(() => {
		if (!container || candles.length === 0) return;
		selected = null;
		const chartApi = createChart(container, {
			width: container.clientWidth,
			height: container.clientHeight,
			autoSize: true,
			layout: { textColor: '#374151' },
			grid: {
				vertLines: { color: '#f3f4f6' },
				horzLines: { color: '#f3f4f6' }
			},
			timeScale: { minBarSpacing: 0.001 }
		});
		const series = chartApi.addSeries(CandlestickSeries, {
			upColor: '#16a34a',
			downColor: '#dc2626',
			borderVisible: false,
			wickUpColor: '#16a34a',
			wickDownColor: '#dc2626'
		});
		series.setData(
			candles.map((c) => ({
				time: c.time as UTCTimestamp,
				open: c.open,
				high: c.high,
				low: c.low,
				close: c.close
			}))
		);
		const markers: SeriesMarker<UTCTimestamp>[] = trades
			.flatMap((trade): SeriesMarker<UTCTimestamp>[] => [
				{
					time: toTime(trade.entry_time),
					position: trade.side === 'long' ? 'belowBar' : 'aboveBar',
					shape: trade.side === 'long' ? 'arrowUp' : 'arrowDown',
					color: trade.side === 'long' ? '#16a34a' : '#dc2626'
				},
				{
					time: toTime(trade.exit_time),
					position: 'aboveBar',
					shape: 'circle',
					color: REASON_COLOR[trade.reason] ?? '#6b7280'
				}
			])
			.sort((a, b) => (a.time as number) - (b.time as number));
		createSeriesMarkers(series, markers);
		chartApi.timeScale().fitContent();

		chart = chartApi;
		priceSeries = series;
		levelSeries = [];
		return () => {
			chart = undefined;
			priceSeries = undefined;
			levelSeries = [];
			chartApi.remove();
		};
	});

	function inspect(trade: TradeMark): void {
		selected = trade;
		if (!chart || !priceSeries) return;
		for (const level of levelSeries) chart.removeSeries(level);
		levelSeries = [];

		const from = toTime(trade.entry_time);
		// a same-bar exit (stop hit on the entry bar) needs a second point to
		// draw a visible segment — extend one bar to the right
		const barSeconds = candles.length > 1 ? candles[1].time - candles[0].time : 3600;
		const to =
			trade.exit_time === trade.entry_time
				? ((from + barSeconds) as UTCTimestamp)
				: toTime(trade.exit_time);

		const drawLevel = (value: number | null, color: string, lineStyle: LineStyle): void => {
			if (value === null || !chart) return;
			const level = chart.addSeries(LineSeries, {
				color,
				lineWidth: 1,
				lineStyle,
				priceLineVisible: false,
				lastValueVisible: false,
				crosshairMarkerVisible: false
			});
			level.setData([
				{ time: from, value },
				{ time: to, value }
			]);
			levelSeries.push(level);
		};
		drawLevel(trade.entry_price, '#6b7280', LineStyle.Solid);
		drawLevel(trade.stop_price, '#dc2626', LineStyle.Dashed);
		drawLevel(trade.take_profit_price, '#16a34a', LineStyle.Dashed);

		const pad = Math.max(to - from, barSeconds) * 4;
		chart.timeScale().setVisibleRange({
			from: (from - pad) as UTCTimestamp,
			to: (to + pad) as UTCTimestamp
		});
	}

	const stamp = (iso: string): string => iso.slice(0, 16).replace('T', ' ');
	const num = (x: number, digits = 0): string =>
		x.toLocaleString('en-US', { maximumFractionDigits: digits });
	const level = (x: number | null): string => (x === null ? '—' : num(x));
</script>

<div bind:this={container} class="h-96 w-full"></div>

<p class="text-xs text-gray-500">
	▲/▼ entry (long/short) · ● exit —
	<span class="text-red-600">stop-loss</span>,
	<span class="text-green-600">take-profit</span>,
	<span class="text-gray-500">time</span>,
	<span class="text-blue-600">signal</span>. Click a trade below to zoom in and see its entry
	(solid), stop and take-profit (dashed) levels.
</p>

{#if trades.length > 0}
	<div class="max-h-64 overflow-y-auto rounded-lg border border-gray-200">
		<table class="min-w-full divide-y divide-gray-200 text-sm">
			<thead
				class="sticky top-0 bg-gray-50 text-left text-xs tracking-wide text-gray-500 uppercase"
			>
				<tr>
					<th class="px-3 py-2">Entry</th>
					<th class="px-3 py-2">Side</th>
					<th class="px-3 py-2 text-right">Entry px</th>
					<th class="px-3 py-2 text-right">Exit px</th>
					<th class="px-3 py-2 text-right">Stop</th>
					<th class="px-3 py-2 text-right">Take profit</th>
					<th class="px-3 py-2 text-right">PnL</th>
					<th class="px-3 py-2">Exit via</th>
				</tr>
			</thead>
			<tbody class="divide-y divide-gray-100">
				{#each trades as trade (trade.entry_time + trade.exit_time)}
					<tr
						class="cursor-pointer hover:bg-blue-50 {selected === trade ? 'bg-blue-50' : ''}"
						onclick={() => inspect(trade)}
					>
						<td class="px-3 py-1.5 text-gray-600 tabular-nums">{stamp(trade.entry_time)}</td>
						<td class="px-3 py-1.5 {trade.side === 'long' ? 'text-green-700' : 'text-red-700'}">
							{trade.side}
						</td>
						<td class="px-3 py-1.5 text-right tabular-nums">{num(trade.entry_price)}</td>
						<td class="px-3 py-1.5 text-right tabular-nums">{num(trade.exit_price)}</td>
						<td class="px-3 py-1.5 text-right tabular-nums">{level(trade.stop_price)}</td>
						<td class="px-3 py-1.5 text-right tabular-nums">{level(trade.take_profit_price)}</td>
						<td
							class="px-3 py-1.5 text-right tabular-nums {trade.pnl >= 0
								? 'text-green-700'
								: 'text-red-700'}"
						>
							{num(trade.pnl, 2)}
						</td>
						<td class="px-3 py-1.5 text-gray-600">{trade.reason.replace('_', ' ')}</td>
					</tr>
				{/each}
			</tbody>
		</table>
	</div>
{:else}
	<p class="text-sm text-gray-500">This run closed no trades.</p>
{/if}
