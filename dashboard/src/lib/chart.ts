import type { SeriesMarker, Time, UTCTimestamp } from 'lightweight-charts';
import type { Candle, Kind, Level, Side, SwingExtreme, TurningPoint } from '#lib/api.ts';

/** The index of the first candle at or after `time`, or `candles.length` when none is; 0
 * when there is no start time. Candles are oldest first, so this is a binary search. */
export function startIndex(candles: Candle[], time: number | null): number {
	if (time === null) return 0;
	let low = 0;
	let high = candles.length;
	while (low < high) {
		const middle = (low + high) >> 1;
		if (candles[middle].time < time) low = middle + 1;
		else high = middle;
	}
	return low;
}

/** A mark as the chart shows it: unscored before the scored period, else pending until its
 * outcome is settled. */
export interface ChartMark {
	kind: Kind;
	time: number;
	price: number;
	state: 'unscored' | 'pending' | 'hit' | 'false';
	/** Candles late (positive) or early (negative), shown once the mark is a hit. */
	timing: number | null;
}

/** A fill as the chart shows it: a buy or a sell on the candle it filled on. */
export interface ChartFill {
	side: Side;
	time: number;
	price: number;
}

/** A horizontal line as the chart draws it, over the candles that have seen it so far: a level
 * the detector sees, or the swing extreme it reads. */
export interface ChartLine {
	price: number;
	/** Start time of the first candle that saw it. */
	from: number;
	/** Start time of the latest shown candle that still sees it. */
	to: number;
	color: string;
}

export const COLORS = {
	turningPoint: '#2962ff',
	level: '#ff9800',
	swingExtreme: '#8e24aa',
	unscored: '#d6d6d6',
	pending: '#9e9e9e',
	hit: '#2e7d32',
	false: '#c62828',
	buy: '#00838f',
	sell: '#ad1457'
};

/** What a level and a swing extreme share: a price with the span of candles that see it. */
type Span = Pick<Level | SwingExtreme, 'kind' | 'price' | 'time' | 'active_from' | 'active_until'>;

/** The spans seen at the latest shown candle, `now`, each drawn as a line in `color` from
 * the first candle that saw it up to that candle. */
export function toLines(spans: Span[], now: number, color: string): ChartLine[] {
	return spans
		.filter((s) => s.active_from <= now && (s.active_until === null || now <= s.active_until))
		.map((s) => ({
			price: s.price,
			from: s.active_from,
			to: now,
			color
		}));
}

/** Whether two marker lists draw the same thing, so the chart can skip setting them again. */
export function sameMarkers(a: SeriesMarker<Time>[], b: SeriesMarker<Time>[]): boolean {
	if (a.length !== b.length) return false;
	for (let i = 0; i < a.length; i++) {
		const x = a[i];
		const y = b[i];
		if (x.time !== y.time || x.color !== y.color || x.text !== y.text || x.shape !== y.shape) {
			return false;
		}
	}
	return true;
}

/** Turning points as blue dots on their extreme, marks as arrows coloured by outcome, fills as
 * squares labelled buy or sell on the candle they filled on. */
export function toMarkers(
	turningPoints: TurningPoint[],
	marks: ChartMark[],
	fills: ChartFill[] = []
): SeriesMarker<Time>[] {
	const points: SeriesMarker<Time>[] = turningPoints.map((p) => ({
		time: p.time as UTCTimestamp,
		position: 'atPriceMiddle',
		price: p.price,
		shape: 'circle',
		color: COLORS.turningPoint,
		size: 1.5
	}));
	const arrows: SeriesMarker<Time>[] = marks.map((m) => ({
		time: m.time as UTCTimestamp,
		position: m.kind === 'top' ? 'aboveBar' : 'belowBar',
		shape: m.kind === 'top' ? 'arrowDown' : 'arrowUp',
		color: COLORS[m.state],
		text: m.state === 'hit' && m.timing !== null ? (m.timing > 0 ? `+${m.timing}` : `${m.timing}`) : undefined
	}));
	const squares: SeriesMarker<Time>[] = fills.map((f) => ({
		time: f.time as UTCTimestamp,
		position: f.side === 'buy' ? 'belowBar' : 'aboveBar',
		shape: 'square',
		color: COLORS[f.side],
		text: f.side
	}));
	return [...points, ...arrows, ...squares].sort((a, b) => (a.time as number) - (b.time as number));
}
