import * as publicEnv from '$app/env/public';

export type Timeframe = '1h' | '4h' | '1d';
export const TIMEFRAMES: Timeframe[] = ['1h', '4h', '1d'];

export interface Candle {
	/** Unix seconds, UTC, at the start of the period. */
	time: number;
	open: number;
	high: number;
	low: number;
	close: number;
	volume: number;
	trades: number;
}

// Set PUBLIC_API_URL in dashboard/.env to read from somewhere else.
const API_URL =
	(publicEnv as Record<string, string | undefined>).PUBLIC_API_URL ?? 'http://localhost:8000';

/** All stored candles of one timeframe, oldest first. */
export async function fetchCandles(timeframe: Timeframe): Promise<Candle[]> {
	const response = await fetch(`${API_URL}/candles?timeframe=${timeframe}`);
	if (!response.ok) {
		throw new Error(`GET /candles?timeframe=${timeframe} answered ${response.status}`);
	}
	const body: { candles: Candle[] } = await response.json();
	return body.candles;
}
