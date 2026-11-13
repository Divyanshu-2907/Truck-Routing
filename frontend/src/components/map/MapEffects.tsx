import L from 'leaflet';
import { useEffect } from 'react';
import { useMap } from 'react-leaflet';

import type { PlanResponse } from '../../types';

/** How far in the map zooms when a risk-profile segment is clicked. */
const FOCUS_ZOOM = 8;

/** A place to move the map to, set by clicking the risk profile strip. */
export interface MapFocus {
  lat: number;
  lon: number;
  /** Bumped on every click, so clicking the same segment twice still pans. */
  nonce: number;
}

/**
 * These components render nothing. They exist because Leaflet's map object
 * is only reachable through `useMap`, which works inside `MapContainer`
 * and nowhere else, so anything that commands the map has to be a child.
 */

/** Zooms the map to show the whole plan once one arrives. */
export function FitToPlan({ plan }: { plan: PlanResponse | null }) {
  const map = useMap();

  useEffect(() => {
    if (!plan || plan.routes.length === 0) {
      return;
    }
    const points = plan.routes.flatMap((route) => route.geometry);
    map.fitBounds(L.latLngBounds(points), { padding: [40, 40] });
  }, [plan, map]);

  return null;
}

/** Moves the map to a checkpoint picked from the risk profile strip. */
export function FlyToFocus({ focus }: { focus: MapFocus | null }) {
  const map = useMap();

  useEffect(() => {
    if (focus) {
      // Never past the map's own maximum, which is where real tiles stop.
      const zoom = Math.min(Math.max(map.getZoom(), FOCUS_ZOOM), map.getMaxZoom());
      map.flyTo([focus.lat, focus.lon], zoom, {
        duration: 0.6,
      });
    }
    // The nonce is what makes clicking the same segment twice pan again.
  }, [focus, map]);

  return null;
}
