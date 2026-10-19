<script lang="ts">
	import CandleChart from '#lib/CandleChart.svelte';
	import { fetchCandles, TIMEFRAMES, type Candle, type Timeframe } from '#lib/api.ts';

	let timeframe = $state<Timeframe>('1h');
	let candles = $state.raw<Candle[]>([]);
	let loading = $state(false);
	let error = $state<string | null>(null);

	$effect(() => {
		const wanted = timeframe;
		loading = true;
		error = null;
		fetchCandles(wanted)
			.then((result) => {
				if (wanted === timeframe) candles = result;
			})
			.catch((reason: unknown) => {
				if (wanted === timeframe) error = reason instanceof Error ? reason.message : String(reason);
			})
			.finally(() => {
				if (wanted === timeframe) loading = false;
			});
	});

	const utc = (seconds: number) => new Date(seconds * 1000).toISOString().slice(0, 16) + 'Z';
</script>

<svelte:head>
	<title>TradingBot: XBTUSD candles</title>
</svelte:head>

<main>
	<header>
		<h1>Kraken spot XBTUSD</h1>
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
		<p class="status">
			{#if loading}
				Loading {timeframe} candles…
			{:else if error}
				<span class="error">{error}</span>
			{:else if candles.length === 0}
				No candles stored yet. Run <code>tradingbot import</code> or <code>tradingbot catch-up</code>.
			{:else}
				{candles.length.toLocaleString()} candles, {utc(candles[0].time)} to {utc(
					candles[candles.length - 1].time
				)}
			{/if}
		</p>
	</header>
	<CandleChart {candles} />
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
	.status {
		margin: 0;
		color: #666;
		font-size: 0.9rem;
	}
	.error {
		color: #c62828;
	}
</style>
