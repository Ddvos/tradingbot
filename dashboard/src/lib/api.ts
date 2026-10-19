import { PUBLIC_API_URL } from '$app/env/public';

export type Timeframe = '1h' | '4h' | '1d';
export const TIMEFRAMES: Timeframe[] = ['1h', '4h', '1d'];

export type Kind = 'top' | 'bottom';

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

/** A top or a bottom found in hindsight, on the candle of the requested timeframe. */
export interface TurningPoint {
	kind: Kind;
	time: number;
	/** The extreme: the hourly high for a top, the hourly low for a bottom. */
	price: number;
	/** Start time of the candle whose reversal confirmed it. */
	confirmed_at: number;
}

/** A detector's mark and what became of it. */
export interface MarkOutcome {
	kind: Kind;
	time: number;
	/** The close of the candle the mark was placed on. */
	price: number;
	hit: boolean;
	/** Time of the turning point this mark is the hit of, if any. */
	turning_point: number | null;
	/** Candles late (positive) or early (negative), for a hit. */
	timing: number | null;
	/** Percent between the turning point's extreme and the close, for a hit. */
	give_up: number | null;
	/** Start time of the first candle from which the outcome can no longer change. */
	settled_at: number;
}

export interface Score {
	turning_points: number;
	marks: number;
	hits: number;
	false_marks: number;
	hit_rate: number;
	false_mark_rate: number;
	median_timing: number | null;
	median_give_up: number | null;
}

export interface Replay {
	detector: string;
	/** The hourly candles of the development period, oldest first. */
	candles: Candle[];
	turning_points: TurningPoint[];
	marks: MarkOutcome[];
	score: Score;
}

export const DETECTORS = ['floor'];

// Declared in src/env.ts; set PUBLIC_API_URL in dashboard/.env to read from somewhere else.
const API_URL = PUBLIC_API_URL;

async function get<T>(path: string): Promise<T> {
	const response = await fetch(`${API_URL}${path}`);
	if (!response.ok) {
		throw new Error(`GET ${path} answered ${response.status}`);
	}
	return (await response.json()) as T;
}

/** All stored development candles of one timeframe, oldest first. */
export async function fetchCandles(timeframe: Timeframe): Promise<Candle[]> {
	const body = await get<{ candles: Candle[] }>(`/candles?timeframe=${timeframe}`);
	return body.candles;
}

/** The hindsight turning points of the development period, on the timeframe's candles. */
export async function fetchTurningPoints(timeframe: Timeframe): Promise<TurningPoint[]> {
	const body = await get<{ turning_points: TurningPoint[] }>(
		`/turning-points?timeframe=${timeframe}`
	);
	return body.turning_points;
}

/** The development period replayed through a detector: candles, marks, outcomes, score. */
export async function fetchReplay(detector: string): Promise<Replay> {
	return get<Replay>(`/replay?detector=${encodeURIComponent(detector)}`);
}
