// Typed client for the tradingbot API (FastAPI backend).
// Decimal fields arrive as strings — convert with Number() for display only.

import { env } from '$env/dynamic/public';

const BASE_URL = env.PUBLIC_API_URL ?? 'http://localhost:8000';

export interface BacktestRun {
	id: string;
	strategy: string;
	symbol: string;
	timeframe: string;
	data_start: string;
	data_end: string;
	initial_capital: string;
	final_equity: string;
	sharpe: number;
	max_drawdown: number;
	n_trades: number;
	params: Record<string, string | number | boolean>;
	created_at: string;
}

export interface EquityPoint {
	time: number; // unix seconds, UTC — the format lightweight-charts expects
	value: number;
}

export interface EquityCurve {
	run_id: string;
	points: EquityPoint[];
}

async function get<T>(path: string): Promise<T> {
	const response = await fetch(`${BASE_URL}${path}`);
	if (!response.ok) {
		throw new Error(`API ${path} failed: ${response.status} ${response.statusText}`);
	}
	return response.json() as Promise<T>;
}

async function post<T>(path: string, body?: unknown): Promise<T> {
	const response = await fetch(`${BASE_URL}${path}`, {
		method: 'POST',
		headers: body === undefined ? undefined : { 'Content-Type': 'application/json' },
		body: body === undefined ? undefined : JSON.stringify(body)
	});
	if (!response.ok) {
		throw new Error(`API ${path} failed: ${response.status} ${response.statusText}`);
	}
	return response.json() as Promise<T>;
}

export interface WalkforwardRun {
	symbol: string;
	run: string; // folder name {timeframe}_{name}_{stamp} — the API identifier
	timeframe: string;
	name: string;
	created_at: string;
	n_folds: number;
	test_start: string;
	test_end: string;
	oos_sharpe: number;
	oos_max_drawdown: number;
	initial_equity: number;
	final_equity: number;
}

// Nullable metrics: a fold with zero trades has no win rate or profit factor
export interface FoldMetrics {
	fold: number;
	test_start: string;
	test_end: string;
	auc: number | null;
	ic: number | null;
	sharpe: number | null;
	max_drawdown: number | null;
	n_trades: number;
	win_rate: number | null;
	profit_factor: number | null;
}

export interface WalkforwardDetail {
	summary: WalkforwardRun;
	folds: FoldMetrics[];
	report: string;
}

export interface WalkforwardEquity {
	symbol: string;
	run: string;
	points: EquityPoint[];
}

export interface Candle {
	time: number; // unix seconds, UTC — the format lightweight-charts expects
	open: number;
	high: number;
	low: number;
	close: number;
}

// One closed round-trip; stop/take-profit are null where the rules had none
export interface TradeMark {
	entry_time: string;
	exit_time: string;
	side: string; // 'long' | 'short'
	quantity: number;
	entry_price: number;
	exit_price: number;
	stop_price: number | null;
	take_profit_price: number | null;
	pnl: number;
	fees: number;
	reason: string; // 'signal' | 'stop_loss' | 'take_profit' | 'time'
}

export interface TradesPayload {
	trades: TradeMark[];
}

export interface CandlesPayload {
	candles: Candle[];
}

export const fetchBacktests = (): Promise<BacktestRun[]> => get('/backtests');

export const fetchEquityCurve = (runId: string): Promise<EquityCurve> =>
	get(`/backtests/${runId}/equity`);

export const fetchWalkforwardRuns = (): Promise<WalkforwardRun[]> => get('/walkforward');

export const fetchWalkforwardDetail = (symbol: string, run: string): Promise<WalkforwardDetail> =>
	get(`/walkforward/${symbol}/${run}`);

export const fetchWalkforwardEquity = (symbol: string, run: string): Promise<WalkforwardEquity> =>
	get(`/walkforward/${symbol}/${run}/equity`);

export const fetchBacktestTrades = (runId: string): Promise<TradesPayload> =>
	get(`/backtests/${runId}/trades`);

export const fetchBacktestCandles = (runId: string): Promise<CandlesPayload> =>
	get(`/backtests/${runId}/candles`);

export const fetchWalkforwardTrades = (symbol: string, run: string): Promise<TradesPayload> =>
	get(`/walkforward/${symbol}/${run}/trades`);

export const fetchWalkforwardCandles = (symbol: string, run: string): Promise<CandlesPayload> =>
	get(`/walkforward/${symbol}/${run}/candles`);

// --- Paper trading (live runner) ---
// "idle" = nothing promoted. Decimal money fields arrive as strings (or numbers)
// and are null before the runner's first tick — convert with Number() for display.

export type LiveState = 'running' | 'paused' | 'idle';
export type Side = 'buy' | 'sell';
export type ExitReason = 'signal' | 'stop_loss' | 'take_profit' | 'time';

export interface LivePosition {
	strategy: string;
	symbol: string;
	side: Side;
	quantity: string | number;
	entry_price: string | number;
	entry_time: string;
	stop: string | number | null;
	take_profit: string | number | null;
	bars_held: number;
}

export interface LiveStatus {
	state: LiveState;
	promoted_strategy: string | null;
	last_tick_at: string | null;
	last_bar_time: string | null;
	cash: string | number | null;
	equity: string | number | null;
	initial_capital: string | number | null;
	position: LivePosition | null;
}

export interface PaperTrade {
	id: string;
	strategy: string;
	symbol: string;
	side: Side;
	quantity: string | number;
	entry_price: string | number;
	exit_price: string | number;
	entry_time: string;
	exit_time: string;
	pnl: string | number;
	fees: string | number;
	exit_reason: ExitReason;
}

export interface StrategyConfig {
	id: string;
	name: string;
	params: Record<string, string | number | boolean>;
	created_at: string;
}

export const fetchLiveStatus = (): Promise<LiveStatus> => get('/live/status');

export const fetchLiveTrades = (): Promise<PaperTrade[]> => get('/live/trades');

export const fetchStrategies = (): Promise<StrategyConfig[]> => get('/strategies');

export const pauseLive = (): Promise<LiveStatus> => post('/live/pause');

export const resumeLive = (): Promise<LiveStatus> => post('/live/resume');

export const demoteLive = (): Promise<LiveStatus> => post('/live/demote');

export const promoteStrategy = (name: string): Promise<LiveStatus> =>
	post('/live/promote', { name });
