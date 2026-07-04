<script lang="ts">
	import { AreaSeries, createChart, type UTCTimestamp } from 'lightweight-charts';
	import type { EquityPoint } from '$lib/api';

	let { points }: { points: EquityPoint[] } = $props();

	let container = $state<HTMLDivElement>();

	$effect(() => {
		if (!container || points.length === 0) return;

		// Explicit initial size: autoSize measures asynchronously, and
		// fitContent() below is a no-op while the chart still has width 0.
		// minBarSpacing: the default (0.5px/bar) caps fitContent at ~1800
		// visible bars — a multi-year hourly curve needs far less per bar.
		const chart = createChart(container, {
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
		const series = chart.addSeries(AreaSeries, {
			lineColor: '#2563eb',
			topColor: 'rgba(37, 99, 235, 0.25)',
			bottomColor: 'rgba(37, 99, 235, 0.02)',
			lineWidth: 2
		});
		series.setData(points.map((p) => ({ time: p.time as UTCTimestamp, value: p.value })));
		chart.timeScale().fitContent();

		return () => chart.remove();
	});
</script>

<div bind:this={container} class="h-96 w-full"></div>
