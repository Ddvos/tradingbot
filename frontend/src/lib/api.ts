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

export const fetchBacktests = (): Promise<BacktestRun[]> => get('/backtests');

export const fetchEquityCurve = (runId: string): Promise<EquityCurve> =>
	get(`/backtests/${runId}/equity`);

export const fetchWalkforwardRuns = (): Promise<WalkforwardRun[]> => get('/walkforward');

export const fetchWalkforwardDetail = (symbol: string, run: string): Promise<WalkforwardDetail> =>
	get(`/walkforward/${symbol}/${run}`);

export const fetchWalkforwardEquity = (symbol: string, run: string): Promise<WalkforwardEquity> =>
	get(`/walkforward/${symbol}/${run}/equity`);
