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

export const fetchBacktests = (): Promise<BacktestRun[]> => get('/backtests');

export const fetchEquityCurve = (runId: string): Promise<EquityCurve> =>
	get(`/backtests/${runId}/equity`);
