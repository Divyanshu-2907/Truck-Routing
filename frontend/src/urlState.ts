/**
 * Keeping the trip in the address bar.
 *
 * After a plan is made the inputs are written to the query string, so the
 * link can be shared or bookmarked and opens on the same trip. Nothing is
 * stored on the server; the URL carries everything.
 */

import type { PlanRequest } from './types';

const SAMPLING_INTERVALS = [10, 25, 50];

/** Put the trip in the address bar without adding a browser history entry. */
export function writeTripToUrl(trip: PlanRequest): void {
  const params = new URLSearchParams({
    from: trip.origin.label,
    from_at: `${trip.origin.lat},${trip.origin.lon}`,
    to: trip.destination.label,
    to_at: `${trip.destination.lat},${trip.destination.lon}`,
    departure: trip.departure,
    load: String(trip.load_lb),
    interval: String(trip.interval_miles),
  });

  window.history.replaceState(null, '', `?${params.toString()}`);
}

/** Read a shared link back into a trip, or null if the link has no trip in it. */
export function readTripFromUrl(): PlanRequest | null {
  const params = new URLSearchParams(window.location.search);

  const origin = readPlace(params.get('from'), params.get('from_at'));
  const destination = readPlace(params.get('to'), params.get('to_at'));
  const departure = params.get('departure');
  const load = Number(params.get('load'));
  const interval = Number(params.get('interval'));

  if (!origin || !destination || !departure || Number.isNaN(Date.parse(departure))) {
    return null;
  }
  if (!Number.isFinite(load) || load < 1 || !SAMPLING_INTERVALS.includes(interval)) {
    return null;
  }

  return {
    origin,
    destination,
    departure,
    load_lb: load,
    interval_miles: interval,
  };
}

function readPlace(label: string | null, coordinates: string | null) {
  if (!label || !coordinates) {
    return null;
  }

  const [lat, lon] = coordinates.split(',').map(Number);
  if (lat === undefined || lon === undefined || Number.isNaN(lat) || Number.isNaN(lon)) {
    return null;
  }

  return { label, lat, lon };
}
