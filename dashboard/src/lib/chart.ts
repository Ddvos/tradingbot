import type { SeriesMarker, Time, UTCTimestamp } from 'lightweight-charts';
import type { Kind, Level, SwingExtreme, TurningPoint } from '#lib/api.ts';

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

/** A horizontal line as the chart draws it, over the candles that have seen it so far: a level
 * the detector sees, or the swing extreme it reads. */
export interface ChartLine {
	/** Identifies the line from one render to the next. */
	key: string;
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
	false: '#c62828'
};

/** Whether a level or a swing extreme is seen on the candle starting at `now`. */
const seenAt = (span: { active_from: number; active_until: number | null }, now: number) =>
	span.active_from <= now && (span.active_until === null || now <= span.active_until);

/** The levels the detector sees at the latest shown candle, each drawn up to that candle. */
export function levelLines(levels: Level[], now: number): ChartLine[] {
	return levels
		.filter((l) => seenAt(l, now))
		.map((l) => ({
			key: `level:${l.kind}@${l.time}`,
			price: l.price,
			from: l.active_from,
			to: now,
			color: COLORS.level
		}));
}

/** The swing extremes the detector reads at the latest shown candle, drawn from the candle it
 * first read each on up to that candle. */
export function swingExtremeLines(extremes: SwingExtreme[], now: number): ChartLine[] {
	return extremes
		.filter((e) => seenAt(e, now))
		.map((e) => ({
			key: `extreme:${e.kind}@${e.time}`,
			price: e.price,
			from: e.active_from,
			to: now,
			color: COLORS.swingExtreme
		}));
}

/** Turning points as blue dots on their extreme, marks as arrows coloured by outcome. */
export function toMarkers(
	turningPoints: TurningPoint[],
	marks: ChartMark[]
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
	return [...points, ...arrows].sort((a, b) => (a.time as number) - (b.time as number));
}
