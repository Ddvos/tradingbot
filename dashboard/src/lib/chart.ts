import type { SeriesMarker, Time, UTCTimestamp } from 'lightweight-charts';
import type { Kind, TurningPoint } from '#lib/api.ts';

/** A mark as the chart shows it: pending until its outcome is settled. */
export interface ChartMark {
	kind: Kind;
	time: number;
	price: number;
	state: 'pending' | 'hit' | 'false';
	/** Candles late (positive) or early (negative), shown once the mark is a hit. */
	timing: number | null;
}

export const COLORS = {
	turningPoint: '#2962ff',
	pending: '#9e9e9e',
	hit: '#2e7d32',
	false: '#c62828'
};

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
