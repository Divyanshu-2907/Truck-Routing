import { memo, useMemo } from 'react';
import type { PathOptions } from 'leaflet';
import { Polyline } from 'react-leaflet';

import { RISK_COLORS } from '../../riskScale';
import { COLORS } from '../../theme';
import type { PlannedRoute, RiskLevel } from '../../types';

/** A stretch of road sharing one risk level. */
interface Segment {
  level: RiskLevel;
  positions: [number, number][];
}

/**
 * Splits a route's shape into one piece per checkpoint.
 *
 * Each checkpoint stands for the road from itself to the next one, which is
 * exactly how the backend weights its risk. Colouring that stretch by the
 * checkpoint's level turns the route into a readable strip: the driver sees
 * where the bad weather is, not just that it exists somewhere.
 *
 * Checkpoints carry mile markers rather than positions in the shape array,
 * so the split walks the shape once, accumulating distance, and cuts
 * wherever the next checkpoint's mile marker is passed.
 */
function buildSegments(route: PlannedRoute): Segment[] {
  const shape = route.geometry;
  const checkpoints = route.checkpoints;
  if (shape.length < 2 || checkpoints.length === 0) {
    return [];
  }

  // The shape's own length, which is what the mile markers were measured
  // along. Using the route's reported distance instead would drift, because
  // OSRM's figure and its drawn line differ by a fraction of a percent.
  const steps = cumulativeMiles(shape);
  const shapeMiles = steps[steps.length - 1] ?? 0;
  const routeMiles = checkpoints[checkpoints.length - 1]?.mile ?? shapeMiles;
  const scale = routeMiles > 0 ? shapeMiles / routeMiles : 1;

  const segments: Segment[] = [];
  let index = 0;

  for (let i = 0; i < checkpoints.length - 1; i += 1) {
    const checkpoint = checkpoints[i];
    const next = checkpoints[i + 1];
    if (!checkpoint || !next) {
      continue;
    }

    const endMiles = next.mile * scale;
    const positions: [number, number][] = [];
    const first = shape[index];
    if (first) {
      positions.push(first);
    }

    while (index < shape.length - 1 && (steps[index + 1] ?? 0) <= endMiles) {
      index += 1;
      const point = shape[index];
      if (point) {
        positions.push(point);
      }
    }

    if (positions.length >= 2) {
      segments.push({ level: checkpoint.level, positions });
    }
  }

  // Whatever is left over belongs to the last checkpoint with road ahead.
  const tail = shape.slice(index);
  const lastScored = checkpoints[checkpoints.length - 2] ?? checkpoints[0];
  if (tail.length >= 2 && lastScored) {
    segments.push({ level: lastScored.level, positions: tail });
  }

  return segments;
}

/** Running distance along the shape, in miles, using the haversine formula. */
function cumulativeMiles(shape: [number, number][]): number[] {
  const steps = [0];
  for (let i = 1; i < shape.length; i += 1) {
    const previous = shape[i - 1];
    const current = shape[i];
    if (!previous || !current) {
      steps.push(steps[i - 1] ?? 0);
      continue;
    }
    steps.push((steps[i - 1] ?? 0) + milesBetween(previous, current));
  }
  return steps;
}

const EARTH_RADIUS_MILES = 3958.7613;

function milesBetween(a: [number, number], b: [number, number]): number {
  const lat1 = (a[0] * Math.PI) / 180;
  const lat2 = (b[0] * Math.PI) / 180;
  const deltaLat = lat2 - lat1;
  const deltaLon = ((b[1] - a[1]) * Math.PI) / 180;

  const h =
    Math.sin(deltaLat / 2) ** 2 +
    Math.cos(lat1) * Math.cos(lat2) * Math.sin(deltaLon / 2) ** 2;
  return 2 * EARTH_RADIUS_MILES * Math.asin(Math.sqrt(h));
}

/**
 * The selected route is drawn in two passes, both styled once: react-leaflet
 * restyles a line whenever it is handed a new style object.
 *
 * A dark casing first, so the route still reads where it crosses a bright
 * patch of heatmap, then the risk-coloured core on top.
 */
const CASING_STYLE: PathOptions = {
  color: COLORS.routeCasing,
  opacity: 0.7,
  weight: 11,
  lineCap: 'round',
};

const SEGMENT_STYLES = Object.fromEntries(
  ([0, 1, 2, 3, 4] as RiskLevel[]).map((level) => [
    level,
    { color: RISK_COLORS[level], weight: 7, opacity: 1, lineCap: 'round' } as PathOptions,
  ]),
) as Record<RiskLevel, PathOptions>;

interface Props {
  route: PlannedRoute;
}

/**
 * The selected route, drawn as risk-coloured segments over a dark outline.
 *
 * The outline is a single wide dark line underneath, which keeps the
 * coloured strip legible wherever it crosses a pale road or a bright patch
 * of heatmap.
 */
function RouteSegmentsView({ route }: Props) {
  const segments = useMemo(() => buildSegments(route), [route]);

  return (
    <>
      <Polyline positions={route.geometry} pathOptions={CASING_STYLE} interactive={false} />
      {segments.map((segment, index) => (
        <Polyline
          key={`${segment.level}-${index}`}
          positions={segment.positions}
          pathOptions={SEGMENT_STYLES[segment.level]}
          interactive={false}
        />
      ))}
    </>
  );
}

/**
 * Memoised so that moving the forecast slider, which re-renders the app, skips it. Its segments
 * depend only on the route.
 */
export const RouteSegments = memo(RouteSegmentsView);
