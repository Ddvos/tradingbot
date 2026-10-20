<script lang="ts">
	import { onMount } from 'svelte';
	import {
		CandlestickSeries,
		createChart,
		createSeriesMarkers,
		LineSeries,
		type IChartApi,
		type ISeriesApi,
		type ISeriesMarkersPluginApi,
		type Time,
		type UTCTimestamp
	} from 'lightweight-charts';
	import type { Candle, TurningPoint } from '#lib/api.ts';
	import { toMarkers, type ChartLine, type ChartMark } from '#lib/chart.ts';

	let {
		candles,
		visible,
		turningPoints = [],
		lines = [],
		marks = []
	}: {
		candles: Candle[];
		/** How many candles to show, oldest first; all of them when omitted. */
		visible?: number;
		turningPoints?: TurningPoint[];
		/** The lines to draw, levels and swing extremes, each from its first candle to its latest. */
		lines?: ChartLine[];
		marks?: ChartMark[];
	} = $props();

	let container: HTMLDivElement;
	let chart: IChartApi | undefined = $state.raw();
	let series: ISeriesApi<'Candlestick'> | undefined = $state.raw();
	let markers: ISeriesMarkersPluginApi<Time> | undefined = $state.raw();

	// What the series currently holds, so that one more visible candle is one `update`,
	// not a full `setData`: replay appends thousands of candles per second.
	let shownCandles: Candle[] | undefined;
	let shownCount = 0;
	// One line series per line drawn, by its key, added when the line first appears
	// and removed when it is no longer in `lines`.
	const lineSeries = new Map<string, ISeriesApi<'Line'>>();

	const toCandlestick = (c: Candle) => ({
		time: c.time as UTCTimestamp,
		open: c.open,
		high: c.high,
		low: c.low,
		close: c.close
	});

	onMount(() => {
		chart = createChart(container, {
			autoSize: true,
			layout: { background: { color: '#ffffff' }, textColor: '#333333' },
			grid: { vertLines: { color: '#eeeeee' }, horzLines: { color: '#eeeeee' } },
			timeScale: { timeVisible: true, secondsVisible: false },
			rightPriceScale: { borderVisible: false }
		});
		series = chart.addSeries(CandlestickSeries, {
			upColor: '#26a69a',
			downColor: '#ef5350',
			borderVisible: false,
			wickUpColor: '#26a69a',
			wickDownColor: '#ef5350'
		});
		markers = createSeriesMarkers(series, []);
		return () => chart?.remove();
	});

	$effect(() => {
		if (!chart || !series) return;
		const count = Math.min(visible ?? candles.length, candles.length);
		if (candles !== shownCandles || count < shownCount) {
			series.setData(candles.slice(0, count).map(toCandlestick));
			shownCandles = candles;
			shownCount = count;
			chart.timeScale().fitContent();
			return;
		}
		for (let i = shownCount; i < count; i++) {
			series.update(toCandlestick(candles[i]));
		}
		shownCount = count;
	});

	$effect(() => {
		markers?.setMarkers(toMarkers(turningPoints, marks));
	});

	$effect(() => {
		if (!chart) return;
		const wanted = new Map(lines.map((line) => [line.key, line]));
		for (const [key, series] of lineSeries) {
			if (!wanted.has(key)) {
				chart.removeSeries(series);
				lineSeries.delete(key);
			}
		}
		for (const [key, line] of wanted) {
			let series = lineSeries.get(key);
			if (!series) {
				series = chart.addSeries(LineSeries, {
					color: line.color,
					lineWidth: 1,
					priceLineVisible: false,
					lastValueVisible: false,
					crosshairMarkerVisible: false,
					// The price scale follows the candles; a line far from the price stays off screen.
					autoscaleInfoProvider: () => null
				});
				lineSeries.set(key, series);
			}
			const start = { time: line.from as UTCTimestamp, value: line.price };
			const end = { time: line.to as UTCTimestamp, value: line.price };
			series.setData(line.to > line.from ? [start, end] : [start]);
		}
	});
</script>

<div class="chart" bind:this={container}></div>

<style>
	.chart {
		width: 100%;
		height: 70vh;
		min-height: 320px;
	}
</style>
