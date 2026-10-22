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

export type Side = 'buy' | 'sell';

/** What one fill did to the account under one cost model. */
export interface FillCost {
	model: string;
	/** Bitcoin bought or sold. */
	size: number;
	/** The fee paid, in USD. */
	fee: number;
	/** The account's value right after the fill, at the fill price. */
	after: number;
}

/** One market order filled: a buy or a sell on the candle it filled on, at its open. */
export interface Fill {
	side: Side;
	time: number;
	/** That open moved 0.05% against the bot. */
	price: number;
	/** Time of the mark that caused the order; null when none had been placed yet. */
	mark: number | null;
	costs: FillCost[];
}

/** The trades opened on a mark of one outcome and closed on a mark of another. */
export interface TradeGroup {
	opened_on_hit: boolean;
	closed_on_hit: boolean;
	trades: number;
	/** Mean result in percent of the account's value at entry; null without trades. */
	mean: number | null;
	median: number | null;
}

/** How a strategy did over a period under one cost model (ADR-0008). */
export interface StrategyScore {
	/** The value at the period's last close over its value before the period; null without candles. */
	growth: number | null;
	benchmark_growth: number | null;
	/** In percent of the peak; null without candles. */
	worst_drawdown: number | null;
	benchmark_worst_drawdown: number | null;
	trades: number;
	fees: number;
	funding: number;
	/** The share of the period's candles whose close found the account long. */
	share_long: number;
	/** Four groups: hit→hit, hit→false, false→hit, false→false (opened on → closed on). */
	groups: TradeGroup[];
	/** The first close at which a 20% drawdown halt would have fired; null when never. */
	halt_at: number | null;
	halt_episodes: number;
	eras: EraStrategyScore[];
}

export interface EraStrategyScore {
	era: Era;
	score: StrategyScore;
}

export interface ModelScore {
	model: string;
	score: StrategyScore;
}

export interface CostModel {
	name: string;
	fee: number;
	funding: number;
}

/** The account's value at every hourly close under each cost model, and the benchmark's. */
export interface ValueSeries {
	times: number[];
	benchmark: number[];
	accounts: Record<string, number[]>;
}

/** A strategy's backtest on the replay: its fills and its score under both cost models. */
export interface Backtest {
	detector: string;
	strategy: string;
	timeframe: Timeframe;
	/** The first candle of the scoring period: when the account starts. */
	scored_from: number;
	cost_models: CostModel[];
	fills: Fill[];
	values: ValueSeries;
	scores: ModelScore[];
	/** The bar of ADR-0008: growth at least the benchmark's in every era under the perpetual. */
	passes: boolean;
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
	/** The strategy's backtest when one was asked for; null otherwise. */
	backtest: Backtest | null;
}

export const DETECTORS = ['floor', 'one', 'two', 'three'];
export const STRATEGIES = ['flip'];

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

/** The development period replayed through a detector, scored over the scoring period: candles, levels, swing extremes, marks, outcomes, score per era; with a strategy, its fills and score too. */
export async function fetchReplay(detector: string, strategy: string | null = null): Promise<Replay> {
	const query = `detector=${encodeURIComponent(detector)}`;
	const withStrategy = strategy === null ? query : `${query}&strategy=${encodeURIComponent(strategy)}`;
	return get<Replay>(`/replay?${withStrategy}`);
}
