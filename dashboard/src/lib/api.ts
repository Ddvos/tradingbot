import { PUBLIC_API_URL } from '$app/env/public';

export type Timeframe = '15m' | '1h' | '4h' | '1d';
export const TIMEFRAMES: Timeframe[] = ['15m', '1h', '4h', '1d'];

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

/** A level as the detector read it, with the span of candles that saw it. */
export interface Level {
	kind: Kind;
	price: number;
	/** Start time of the turning point's candle. */
	time: number;
	/** Start time of the candle that confirmed the turning point: the first to see the level. */
	active_from: number;
	/** Start time of the last candle that sees the level; null when it never expires. */
	active_until: number | null;
}

/** A swing extreme as detector three read it, with the span of candles that read it. */
export interface SwingExtreme {
	/** 'top' for the extreme of an up-swing, a possible top; 'bottom' for a down-swing's. */
	kind: Kind;
	price: number;
	/** Start time of the fifteen-minute candle holding the extreme. */
	time: number;
	/** Start time of the first candle the detector read it on. */
	active_from: number;
	/** Start time of the last candle that read it; null when it still stands at the end. */
	active_until: number | null;
}

/** A detector's mark and what became of it. */
export interface MarkOutcome {
	kind: Kind;
	time: number;
	/** The close of the candle the mark was placed on. */
	price: number;
	/** Whether the mark falls in the scored period; an unscored mark is neither a hit nor a false mark. */
	scored: boolean;
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

/** A fixed block of years within the scoring period; `start` inclusive, `end` exclusive. */
export interface Era {
	name: string;
	start: number;
	end: number;
}

export interface EraScore {
	era: Era;
	score: Score;
}

export interface Score {
	turning_points: number;
	marks: number;
	hits: number;
	false_marks: number;
	hit_rate: number;
	false_mark_rate: number;
	/** False marks divided by hits (ADR-0007); 0 without hits. */
	false_marks_per_hit: number;
	/** Median timing of the hits in hourly candles; null without hits. */
	median_timing: number | null;
	median_give_up: number | null;
	/** The same numbers per era, in era order; empty for a score without eras. */
	eras: EraScore[];
}

export interface Replay {
	detector: string;
	/** The timeframe of `candles`: what the detector read. */
	timeframe: Timeframe;
	/** Start of the scored period; marks before it are unscored. */
	scored_from: number | null;
	/** Every candle the detector read, oldest first: the whole development period. */
	candles: Candle[];
	turning_points: TurningPoint[];
	/** The levels the detector read; empty for a detector that reads none. */
	levels: Level[];
	/** The swing extremes the detector read; empty for a detector that tracks no swing. */
	swing_extremes: SwingExtreme[];
	marks: MarkOutcome[];
	score: Score;
}

export const DETECTORS = ['floor', 'one', 'two', 'three'];

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

/** The development period replayed through a detector, scored over the scoring period: candles, levels, swing extremes, marks, outcomes, score per era. */
export async function fetchReplay(detector: string): Promise<Replay> {
	return get<Replay>(`/replay?detector=${encodeURIComponent(detector)}`);
}
