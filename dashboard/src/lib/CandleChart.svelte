<script lang="ts">
	import { onMount } from 'svelte';
	import {
		CandlestickSeries,
		createChart,
		type IChartApi,
		type ISeriesApi,
		type UTCTimestamp
	} from 'lightweight-charts';
	import type { Candle } from '#lib/api.ts';

	let { candles }: { candles: Candle[] } = $props();

	let container: HTMLDivElement;
	let chart: IChartApi | undefined = $state.raw();
	let series: ISeriesApi<'Candlestick'> | undefined = $state.raw();

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
		return () => chart?.remove();
	});

	$effect(() => {
		if (!chart || !series) return;
		series.setData(
			candles.map((c) => ({
				time: c.time as UTCTimestamp,
				open: c.open,
				high: c.high,
				low: c.low,
				close: c.close
			}))
		);
		chart.timeScale().fitContent();
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
