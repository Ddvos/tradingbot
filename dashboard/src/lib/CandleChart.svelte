<script lang="ts">
	import { onMount } from 'svelte';
	import {
		CandlestickSeries,
		createChart,
		createSeriesMarkers,
		type IChartApi,
		type ISeriesApi,
		type ISeriesMarkersPluginApi,
		type ITimeScaleApi,
		type SeriesMarker,
		type Time,
		type UTCTimestamp
	} from 'lightweight-charts';
	import type { Candle, TurningPoint } from '#lib/api.ts';
	import { sameMarkers, toMarkers, type ChartLine, type ChartMark } from '#lib/chart.ts';
	import { LinesPrimitive } from '#lib/lines.ts';

	let {
		candles,
		visible,
		start = 0,
		turningPoints = [],
		lines = [],
		marks = []
	}: {
		candles: Candle[];
		/** How many candles to show, oldest first; all of them when omitted. */
		visible?: number;
		/** The index of the candle at the start date; 0 without one. Without `visible` the view
		 * runs from this candle to the last one; with it, the latest shown candle sits at the right
		 * edge, as a replay does, so the candles just before the start date stay in view. */
		start?: number;
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
	let shownStart = 0;
	// Draws every line in one pass; see lines.ts for why not one line series per line.
	const linesPrimitive = new LinesPrimitive();

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
			// The default keeps two candles per pixel at most, which cannot fit years of hourly
			// candles on one screen; the hindsight view from a start date to the end needs to.
			timeScale: { timeVisible: true, secondsVisible: false, minBarSpacing: 0.001 },
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
		series.attachPrimitive(linesPrimitive);
		return () => chart?.remove();
	});

	/** Where the view begins once the data was replaced: everything fitted without a start
	 * date; else from the start candle on, or, in a replay, ending at the latest shown candle. */
	function position(scale: ITimeScaleApi<Time>) {
		if (start === 0) {
			scale.fitContent();
		} else if (visible === undefined) {
			const first = Math.min(start, candles.length - 1);
			scale.setVisibleLogicalRange({ from: first - 0.5, to: candles.length - 0.5 });
		} else {
			scale.scrollToPosition(0, false);
		}
	}

	$effect(() => {
		if (!chart || !series) return;
		const count = Math.min(visible ?? candles.length, candles.length);
		// A new series, a restart or a jump to another start date replaces the data; from
		// then on, each further visible candle is one `update`.
		if (candles !== shownCandles || count < shownCount || start !== shownStart) {
			series.setData(candles.slice(0, count).map(toCandlestick));
			shownCandles = candles;
			shownCount = count;
			shownStart = start;
			position(chart.timeScale());
			return;
		}
		for (let i = shownCount; i < count; i++) {
			series.update(toCandlestick(candles[i]));
		}
		shownCount = count;
	});

	// The markers last set, so a step that confirms no turning point, places no mark and
	// settles none sets nothing: every call re-indexes thousands of markers.
	let shownMarkers: SeriesMarker<Time>[] = [];

	$effect(() => {
		const wanted = toMarkers(turningPoints, marks);
		if (!markers || sameMarkers(wanted, shownMarkers)) return;
		markers.setMarkers(wanted);
		shownMarkers = wanted;
	});

	$effect(() => {
		linesPrimitive.setLines(lines);
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
