import type {
	IChartApiBase,
	IPrimitivePaneRenderer,
	IPrimitivePaneView,
	ISeriesApi,
	ISeriesPrimitive,
	Logical,
	SeriesAttachedParameter,
	SeriesType,
	Time
} from 'lightweight-charts';
import type { ChartLine } from '#lib/chart.ts';

type Target = Parameters<IPrimitivePaneRenderer['draw']>[0];

/** Draws the chart's lines, the levels and the swing extremes, in one pass over the
 * candlestick pane. One line series per line would cost a data update per line on every
 * replay step, each re-indexing every candle; drawing them here costs nothing per step
 * beyond the paint itself. The lines take no part in the price scale, so a line far from
 * the price stays off screen. */
export class LinesPrimitive implements ISeriesPrimitive<Time> {
	private lines: ChartLine[] = [];
	private chart: IChartApiBase<Time> | undefined;
	private series: ISeriesApi<SeriesType, Time> | undefined;
	private requestUpdate: (() => void) | undefined;
	private readonly renderer: IPrimitivePaneRenderer = { draw: (target) => this.draw(target) };
	private readonly view: IPrimitivePaneView = { renderer: () => this.renderer };

	attached({ chart, series, requestUpdate }: SeriesAttachedParameter<Time>): void {
		this.chart = chart;
		this.series = series;
		this.requestUpdate = requestUpdate;
	}

	detached(): void {
		this.chart = undefined;
		this.series = undefined;
		this.requestUpdate = undefined;
	}

	paneViews(): readonly IPrimitivePaneView[] {
		return [this.view];
	}

	/** The lines to draw from now on; the chart repaints. */
	setLines(lines: ChartLine[]): void {
		this.lines = lines;
		this.requestUpdate?.();
	}

	private draw(target: Target): void {
		const chart = this.chart;
		const series = this.series;
		if (!chart || !series || this.lines.length === 0) return;
		const timeScale = chart.timeScale();
		// A time's x position, also off screen; null when the chart has no such candle.
		const x = (time: number): number | null => {
			const index = timeScale.timeToIndex(time as Time, true);
			return index === null ? null : timeScale.logicalToCoordinate(index as unknown as Logical);
		};
		target.useMediaCoordinateSpace(({ context, mediaSize }) => {
			context.lineWidth = 1;
			for (const line of this.lines) {
				const y = series.priceToCoordinate(line.price);
				const from = x(line.from);
				const to = x(line.to);
				if (y === null || from === null || to === null) continue;
				if (to < 0 || from > mediaSize.width || y < 0 || y > mediaSize.height) continue;
				context.strokeStyle = line.color;
				context.beginPath();
				context.moveTo(Math.max(from, 0), y);
				context.lineTo(Math.min(to, mediaSize.width), y);
				context.stroke();
			}
		});
	}
}
