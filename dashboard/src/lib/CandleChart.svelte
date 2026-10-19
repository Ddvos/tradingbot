<script lang="ts">
	import { onMount } from 'svelte';
	import {
		CandlestickSeries,
		createChart,
		createSeriesMarkers,
		type IChartApi,
		type ISeriesApi,
		type ISeriesMarkersPluginApi,
		type Time,
		type UTCTimestamp
	} from 'lightweight-charts';
	import type { Candle, TurningPoint } from '#lib/api.ts';
	import { toMarkers, type ChartMark } from '#lib/chart.ts';

	let {
		candles,
		visible,
		turningPoints = [],
		marks = []
	}: {
		candles: Candle[];
		/** How many candles to show, oldest first; all of them when omitted. */
		visible?: number;
		turningPoints?: TurningPoint[];
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

	const toBar = (c: Candle) => ({
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
			series.setData(candles.slice(0, count).map(toBar));
			shownCandles = candles;
			shownCount = count;
			chart.timeScale().fitContent();
			return;
		}
		for (let i = shownCount; i < count; i++) {
			series.update(toBar(candles[i]));
		}
		shownCount = count;
	});

	$effect(() => {
		markers?.setMarkers(toMarkers(turningPoints, marks));
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
