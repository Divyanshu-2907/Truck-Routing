/**
 * The shapes the Django API sends and receives.
 *
 * These mirror `backend/routing/serializers.py` exactly. Keeping them in one
 * file means a change to the API shows up as a TypeScript error everywhere
 * it matters, rather than as a blank panel at runtime.
 */

/** 0 = Low through 4 = No Travel, matching the backend's RiskLevel enum. */
export type RiskLevel = 0 | 1 | 2 | 3 | 4;

/** The JSON-friendly names the backend uses as object keys. */
export type LevelKey = 'low' | 'moderate' | 'high' | 'severe' | 'no_travel';

/** A number per risk level, used for both miles and checkpoint counts. */
export type ByLevel = Record<LevelKey, number>;

/** A place returned by the search box. */
export interface Place {
  label: string;
  lat: number;
  lon: number;
}

/** One weather sampling point along a route. */
export interface Checkpoint {
  mile: number;
  /** Miles of road this checkpoint stands for, until the next one. */
  covered_miles: number;
  lat: number;
  lon: number;
  /** ISO timestamp of when the truck is expected to arrive here. */
  eta: string;
  wind_mph: number;
  rain_in: number;
  snow_in: number;
  level: RiskLevel;
  level_label: string;
  reason: string;
}

/** The whole-route picture shown on a route card. */
export interface RouteSummary {
  distance_miles: number;
  duration_s: number;
  duration_text: string;
  average_risk: number;
  max_level: RiskLevel;
  max_level_label: string;
  miles_by_level: ByLevel;
  checkpoints_by_level: ByLevel;
  checkpoint_count: number;
}

/** Where a route came from: an OSRM alternative, or one we built ourselves. */
export type RouteSource = 'osrm-alternative' | 'detour';

export interface PlannedRoute {
  label: string;
  source: RouteSource;
  /** Map shape as [latitude, longitude] pairs, ready for Leaflet. */
  geometry: [number, number][];
  summary: RouteSummary;
  checkpoints: Checkpoint[];
}

/** Which ranking rule decided the recommendation. */
export type DecidingCriterion =
  | 'no_travel'
  | 'severe'
  | 'high'
  | 'average_risk'
  | 'duration'
  | 'tie'
  | 'only_route';

export interface PlanResponse {
  routes: PlannedRoute[];
  recommended_index: number;
  recommendation_reason: string;
  deciding_criterion: DecidingCriterion;
  generated_at: string;
}

export interface PlanRequest {
  origin: Place;
  destination: Place;
  /** ISO timestamp including a timezone offset. */
  departure: string;
  load_lb: number;
  interval_miles: number;
}

/**
 * The corridor heatmap: a grid of risk levels over 49 hourly steps.
 *
 * It is deliberately compact. `values[hour][point]` is a risk level from 0
 * to 4, so all 49 frames arrive in one small response and the slider never
 * has to call the server.
 */
export interface HeatmapResponse {
  /** 49 ISO timestamps: the departure hour, then the next 48. */
  times: string[];
  /** Grid positions as [latitude, longitude]. */
  points: [number, number][];
  /** values[hour][point] = risk level 0-4. */
  values: number[][];
}

export interface HeatmapRequest {
  origin: Place;
  destination: Place;
  departure: string;
  load_lb: number;
}
