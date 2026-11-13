import Box from '@mui/material/Box';
import { memo, useMemo } from 'react';
import { MapContainer, TileLayer } from 'react-leaflet';

import { COLORS } from '../theme';
import type { HeatmapResponse, PlanResponse, Place } from '../types';
import type { HeatmapMetric } from '../heatmapMetrics';
import { HeatmapLayer } from './HeatmapLayer';
import { Legend } from './Legend';
import { CheckpointMarker } from './map/CheckpointMarkers';
import { EndpointMarker } from './map/EndpointMarker';
import { FitToPlan, FlyToFocus, type MapFocus } from './map/MapEffects';
import { RouteSegments } from './map/RouteSegments';
import { UnselectedRoute } from './map/UnselectedRoute';
import { nearestCheckpointMile } from './map/truckPosition';

/** Centre and zoom that frame the continental United States. */
const USA_CENTER: [number, number] = [39.5, -98.35];
const USA_ZOOM = 4;

/**
 * Background map tiles: Esri's World Dark Gray Base, with its matching
 * World Dark Gray Reference layer on top for the labels.
 *
 * The base layer is deliberately unlabelled - checked at zoom 6, 8 and 10
 * over Dallas, it draws terrain, water and road geometry but no place names
 * at all. Esri publishes the labels as a separate transparent layer, which
 * is what the reference layer below supplies. Without it the driver sees a
 * route crossing an anonymous grey field.
 *
 * CARTO's dark basemap was the first choice and had to be rejected: it now
 * answers every tile request with an "API KEY REQUIRED" image, and serves it
 * with HTTP 200, so it fails silently rather than erroring. This app is
 * meant to run without any keys.
 *
 * OpenStreetMap's own tiles are deliberately avoided too: those servers are
 * run by volunteers for the OSM project and answer with a "403 Access
 * blocked" tile once an app asks for too many.
 */
const ESRI_CANVAS = 'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas';
const TILE_URL = `${ESRI_CANVAS}/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}`;
const LABEL_TILE_URL = `${ESRI_CANVAS}/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}`;
const TILE_ATTRIBUTION =
  'Tiles &copy; <a href="https://www.esri.com/">Esri</a> &mdash; map data ' +
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

/**
 * Esri's canvas is cached to zoom 16. Ask for 17 and the service answers
 * 200 with a pale "Map data not yet available" placeholder rather than a
 * 404, so Leaflet would happily draw it over the map.
 *
 * `maxNativeZoom` records where the real tiles stop, and the map's own
 * `maxZoom` is held at the same level so nothing is ever stretched: at 16
 * individual streets are already visible, which is as close as a route
 * checkpoint needs.
 */
/**
 * Both tile layers share Leaflet's tilePane, and these order them inside
 * it: the labels sit above the base tiles. The whole tilePane is painted
 * below the overlay pane, which holds the heatmap canvas and the route
 * lines, and below the marker pane - so place names never cover a route,
 * a checkpoint or the heat.
 */
const BASE_TILE_Z_INDEX = 1;
const LABEL_TILE_Z_INDEX = 2;

const TILE_MAX_NATIVE_ZOOM = 16;
const MAP_MAX_ZOOM = 16;
const MAP_MIN_ZOOM = 3;

interface Props {
  plan: PlanResponse | null;
  selectedIndex: number;
  onSelectRoute: (index: number) => void;
  origin: Place | null;
  destination: Place | null;
  heatmap: HeatmapResponse | null;
  hourIndex: number;
  heatmapVisible: boolean;
  heatmapMetric: HeatmapMetric;
  focus: MapFocus | null;
}

/**
 * The map: every route is drawn, the selected one in risk colours, its
 * checkpoints as circles, and the corridor heatmap underneath for the hour
 * the slider is on.
 *
 * The map is created with `preferCanvas`, so thousands of route points and
 * checkpoint circles are painted onto one canvas instead of becoming
 * thousands of SVG elements. That is what keeps panning smooth.
 */
export function MapView({
  plan,
  selectedIndex,
  onSelectRoute,
  origin,
  destination,
  heatmap,
  hourIndex,
  heatmapVisible,
  heatmapMetric,
  focus,
}: Props) {
  const currentTime = heatmap?.times[hourIndex] ?? null;

  return (
    <Box sx={{ height: '100%', width: '100%', position: 'relative' }}>
      <MapContainer
        center={USA_CENTER}
        zoom={USA_ZOOM}
        minZoom={MAP_MIN_ZOOM}
        maxZoom={MAP_MAX_ZOOM}
        scrollWheelZoom
        preferCanvas
        zoomControl={false}
        style={{ height: '100%', width: '100%', background: COLORS.background }}
      >
        <TileLayer
          url={TILE_URL}
          attribution={TILE_ATTRIBUTION}
          maxZoom={MAP_MAX_ZOOM}
          maxNativeZoom={TILE_MAX_NATIVE_ZOOM}
          zIndex={BASE_TILE_Z_INDEX}
        />
        {/* Place names: the base layer carries none of its own. */}
        <TileLayer
          url={LABEL_TILE_URL}
          maxZoom={MAP_MAX_ZOOM}
          maxNativeZoom={TILE_MAX_NATIVE_ZOOM}
          zIndex={LABEL_TILE_Z_INDEX}
        />

        <HeatmapLayer
          heatmap={heatmap}
          hourIndex={hourIndex}
          visible={heatmapVisible}
          metric={heatmapMetric}
        />

        {plan ? (
          <>
            <RouteLines plan={plan} selectedIndex={selectedIndex} onSelectRoute={onSelectRoute} />
            <CheckpointLayer plan={plan} selectedIndex={selectedIndex} currentTime={currentTime} />
          </>
        ) : null}

        {origin ? <EndpointMarker place={origin} kind="origin" /> : null}
        {destination ? <EndpointMarker place={destination} kind="destination" /> : null}

        <FitToPlan plan={plan} />
        <FlyToFocus focus={focus} />
      </MapContainer>

      <Legend metric={heatmapMetric} heatmapVisible={heatmapVisible} />
    </Box>
  );
}

interface RouteLinesProps {
  plan: PlanResponse;
  selectedIndex: number;
  onSelectRoute: (index: number) => void;
}

/**
 * The route lines. They depend only on the plan and the selection, never on
 * the forecast hour, which is why they are a separate memoised component:
 * dragging the slider leaves them alone.
 */
const RouteLines = memo(function RouteLines({
  plan,
  selectedIndex,
  onSelectRoute,
}: RouteLinesProps) {
  const selectedRoute = plan.routes[selectedIndex];

  return (
    <>
      {/* Unselected routes are drawn first so the selected one sits on top. */}
      {plan.routes.map((route, index) =>
        index === selectedIndex ? null : (
          <UnselectedRoute
            key={route.label}
            positions={route.geometry}
            label={route.label}
            onSelect={() => onSelectRoute(index)}
          />
        ),
      )}

      {selectedRoute ? <RouteSegments route={selectedRoute} /> : null}
    </>
  );
});

interface CheckpointLayerProps {
  plan: PlanResponse;
  selectedIndex: number;
  currentTime: string | null;
}

/**
 * The selected route's checkpoints. This is the one map layer the slider
 * does reach, because it moves the "truck here" ring - but each checkpoint is
 * memoised, so only the two whose ring appears or disappears re-render.
 */
function CheckpointLayer({ plan, selectedIndex, currentTime }: CheckpointLayerProps) {
  const checkpoints = useMemo(
    () => plan.routes[selectedIndex]?.checkpoints ?? [],
    [plan, selectedIndex],
  );

  // Worked out from the already-loaded ETAs: one comparison per checkpoint
  // and no network traffic.
  const truckMile = useMemo(
    () => nearestCheckpointMile(checkpoints, currentTime),
    [checkpoints, currentTime],
  );

  return (
    <>
      {checkpoints.map((checkpoint) => (
        <CheckpointMarker
          key={checkpoint.mile}
          checkpoint={checkpoint}
          isTruckHere={checkpoint.mile === truckMile}
        />
      ))}
    </>
  );
}
