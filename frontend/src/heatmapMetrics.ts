/**
 * What the heatmap can draw, and how each reading becomes a heat value.
 *
 * The backend sends four grids on the same points and hours: the scored
 * risk, and the raw wind, rain and snow behind it. Switching between them
 * is a local change of which grid is read, so it costs no network call and
 * the slider keeps working the same way.
 *
 * Readings arrive as whole numbers to keep the payload small. `divisor`
 * turns them back into real units, and `max` is the value the colour scale
 * tops out at: for each factor that is the point at which it alone would
 * stop travel, so the darkest heat always means the same thing.
 */

import type { HeatmapResponse } from './types';

export type HeatmapMetric = 'risk' | 'wind' | 'rain' | 'snow';

export interface MetricSpec {
  label: string;
  unit: string;
  /** Divide a raw grid value by this to get real units. */
  divisor: number;
  /** The reading the colour scale tops out at, in real units. */
  max: number;
  /** Decimal places to show in the legend. */
  decimals: number;
}

export const METRICS: Record<HeatmapMetric, MetricSpec> = {
  risk: { label: 'Risk', unit: '', divisor: 1, max: 4, decimals: 0 },
  wind: { label: 'Wind', unit: 'mph', divisor: 1, max: 55, decimals: 0 },
  rain: { label: 'Rain', unit: 'in/hr', divisor: 100, max: 1, decimals: 2 },
  snow: { label: 'Snow', unit: 'in/hr', divisor: 10, max: 3, decimals: 1 },
};

export const METRIC_ORDER: HeatmapMetric[] = ['risk', 'wind', 'rain', 'snow'];

/** The grid a metric reads from. */
export function gridFor(heatmap: HeatmapResponse, metric: HeatmapMetric): number[][] {
  switch (metric) {
    case 'wind':
      return heatmap.wind;
    case 'rain':
      return heatmap.rain;
    case 'snow':
      return heatmap.snow;
    default:
      return heatmap.values;
  }
}

/** A raw grid value as a 0..1 heat intensity, or 0 when there is nothing to show. */
export function intensityOf(rawValue: number, metric: HeatmapMetric): number {
  if (rawValue <= 0) {
    return 0;
  }
  const spec = METRICS[metric];
  return Math.min(rawValue / spec.divisor / spec.max, 1);
}

/** The three labels under the legend's gradient: nothing, halfway, and the top. */
export function scaleTicks(metric: HeatmapMetric): string[] {
  const spec = METRICS[metric];
  const show = (value: number): string => value.toFixed(spec.decimals);
  return [show(0), show(spec.max / 2), `${show(spec.max)}+`];
}
