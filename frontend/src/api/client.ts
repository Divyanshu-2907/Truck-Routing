/**
 * Thin wrapper around the Django API.
 *
 * Every call goes through `request`, which turns any failure (network error,
 * non-2xx status, or the backend's own `{ "error": ... }` payload) into one
 * `ApiError` so the UI can show a single MUI Alert.
 */

import type {
  HeatmapRequest,
  HeatmapResponse,
  PlanRequest,
  PlanResponse,
  Place,
} from '../types';

export class ApiError extends Error {}

interface ErrorPayload {
  error?: string;
  detail?: string;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      headers: { 'Content-Type': 'application/json' },
      ...init,
    });
  } catch (cause) {
    // An aborted request is a cancelled search, not something to report.
    if (cause instanceof DOMException && cause.name === 'AbortError') {
      throw cause;
    }
    throw new ApiError('Could not reach the server. Is the Django API running?');
  }

  const body: unknown = await response.json().catch(() => null);

  if (!response.ok) {
    const payload = (body ?? {}) as ErrorPayload;
    throw new ApiError(
      payload.error ?? payload.detail ?? `Request failed with status ${response.status}.`,
    );
  }

  return body as T;
}

export interface HealthResponse {
  status: string;
}

/** Check that the backend is up. Used by the status chip in the sidebar. */
export function getHealth(): Promise<HealthResponse> {
  return request<HealthResponse>('/api/health');
}

/** Search for US places matching what the driver has typed so far. */
export function searchPlaces(query: string, signal?: AbortSignal): Promise<Place[]> {
  const path = `/api/geocode?q=${encodeURIComponent(query)}`;
  return request<Place[]>(path, signal ? { signal } : undefined);
}

/** Plan a trip: route options, checkpoint risk and a recommendation. */
export function planTrip(plan: PlanRequest): Promise<PlanResponse> {
  return request<PlanResponse>('/api/plan', {
    method: 'POST',
    body: JSON.stringify(plan),
  });
}

/** The 48 hour corridor heatmap for a trip that has just been planned. */
export function fetchHeatmap(heatmap: HeatmapRequest): Promise<HeatmapResponse> {
  return request<HeatmapResponse>('/api/heatmap', {
    method: 'POST',
    body: JSON.stringify(heatmap),
  });
}
