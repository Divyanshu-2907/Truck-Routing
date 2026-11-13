import type L from 'leaflet';
import { HeatLayer, type HeatLatLng, type HeatLayerOptions } from 'leaflet.heat';
import { useEffect, useMemo, useRef } from 'react';
import { useMap } from 'react-leaflet';

import { gridFor, intensityOf, type HeatmapMetric } from '../heatmapMetrics';
import { RISK_COLORS } from '../riskScale';
import type { HeatmapResponse } from '../types';

/**
 * Heat colours by intensity. Intensity is `level / 4`, so Moderate lands on
 * 0.25 and No Travel on 1.0, which keeps the heatmap and the checkpoint
 * circles telling the same colour story.
 */
const GRADIENT = {
  0.2: RISK_COLORS[1],
  0.45: RISK_COLORS[2],
  0.7: RISK_COLORS[3],
  1.0: RISK_COLORS[4],
};

const HEAT_OPTIONS: HeatLayerOptions = {
  radius: 34,
  blur: 26,
  max: 1.0,
  minOpacity: 0.25,
  maxZoom: 9,
  gradient: GRADIENT,
};

/**
 * The heat layer, plus the two inherited methods we call on it.
 *
 * leaflet.heat 1.0 runs on Leaflet 1.9 (see its peerDependencies) but ships
 * type definitions written against Leaflet 2, whose `Layer` is generic. Those
 * do not line up with the Leaflet 1.9 types this project uses, so the
 * inherited members are lost. At runtime the class really is a Leaflet layer,
 * and this spells out the part of it we depend on.
 */
type MapHeatLayer = HeatLayer & Pick<L.Layer, 'addTo' | 'remove'>;

interface Props {
  heatmap: HeatmapResponse | null;
  hourIndex: number;
  visible: boolean;
  metric: HeatmapMetric;
}

/**
 * The corridor heatmap for one hour of the forecast.
 *
 * Two things keep the slider smooth:
 *
 * 1. every hour's point array is worked out once, when the data arrives,
 *    so dragging the slider does no arithmetic and no network calls;
 * 2. the Leaflet layer is created once and kept in a ref. Moving the slider
 *    only calls `setLatLngs`, which redraws the canvas without rebuilding
 *    the layer or touching React's tree.
 */
export function HeatmapLayer({ heatmap, hourIndex, visible, metric }: Props) {
  const map = useMap();
  const layerRef = useRef<MapHeatLayer | null>(null);

  // One ready-made array of points per hour, for the metric on show. Each
  // point carries its intensity as `alt`, which is where this plugin reads
  // it from. Points with nothing to report are left out entirely: they
  // would only wash the colours out.
  //
  // Switching metric rebuilds these once, which is the only work a toggle
  // costs. Moving the slider still just picks a different array.
  const frames = useMemo<HeatLatLng[][]>(() => {
    if (!heatmap) {
      return [];
    }
    return gridFor(heatmap, metric).map((readings) => {
      const frame: HeatLatLng[] = [];
      readings.forEach((reading, index) => {
        const point = heatmap.points[index];
        const intensity = intensityOf(reading, metric);
        if (intensity > 0 && point) {
          frame.push({ lat: point[0], lng: point[1], alt: intensity });
        }
      });
      return frame;
    });
  }, [heatmap, metric]);

  // Create the layer once, and take it down when the map goes away.
  useEffect(() => {
    const layer = new HeatLayer([], HEAT_OPTIONS) as MapHeatLayer;
    layerRef.current = layer;

    return () => {
      layer.remove();
      layerRef.current = null;
    };
  }, [map]);

  // Show or hide without destroying the layer, so toggling is instant.
  useEffect(() => {
    const layer = layerRef.current;
    if (!layer) {
      return;
    }
    if (visible && frames.length > 0) {
      layer.addTo(map);
    } else {
      layer.remove();
    }
  }, [map, visible, frames]);

  // The only thing a slider move does: hand the layer a different array.
  useEffect(() => {
    const layer = layerRef.current;
    const frame = frames[hourIndex];
    if (layer && frame) {
      layer.setLatLngs(frame);
    }
  }, [frames, hourIndex]);

  return null;
}
