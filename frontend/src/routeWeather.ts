/**
 * The worst weather on a route, read off its checkpoints.
 *
 * Nothing here is new information: these are the highest readings the
 * backend already returned, picked out so a route can be judged without
 * opening its checkpoint list. The mile marker comes with the peak wind
 * because "38 mph somewhere" and "38 mph at MM 210" are different facts.
 */

import type { PlannedRoute } from './types';

export interface RouteWeather {
  /** Highest wind on the route, with the mile marker it occurs at. */
  peakWindMph: number;
  peakWindMile: number;
  peakRainIn: number;
  peakSnowIn: number;
  /** Checkpoints scoring worse than Low, out of every checkpoint sampled. */
  aboveLow: number;
  total: number;
}

export function summariseWeather(route: PlannedRoute): RouteWeather {
  let peakWindMph = 0;
  let peakWindMile = 0;
  let peakRainIn = 0;
  let peakSnowIn = 0;
  let aboveLow = 0;

  for (const checkpoint of route.checkpoints) {
    if (checkpoint.wind_mph > peakWindMph) {
      peakWindMph = checkpoint.wind_mph;
      peakWindMile = checkpoint.mile;
    }
    peakRainIn = Math.max(peakRainIn, checkpoint.rain_in);
    peakSnowIn = Math.max(peakSnowIn, checkpoint.snow_in);
    if (checkpoint.level > 0) {
      aboveLow += 1;
    }
  }

  return {
    peakWindMph,
    peakWindMile,
    peakRainIn,
    peakSnowIn,
    aboveLow,
    total: route.checkpoints.length,
  };
}
