import L from 'leaflet';
import { memo, useMemo } from 'react';
import { Marker, Popup } from 'react-leaflet';

import { COLORS } from '../../theme';
import type { Place } from '../../types';

/** A chequered flag, drawn small enough to read at 18px. */
const FLAG_SVG =
  '<svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true">' +
  '<rect x="0" y="0" width="3" height="3"/><rect x="6" y="0" width="3" height="3"/>' +
  '<rect x="3" y="3" width="3" height="3"/><rect x="9" y="3" width="3" height="3"/>' +
  '<rect x="0" y="6" width="3" height="3"/><rect x="6" y="6" width="3" height="3"/>' +
  '<rect x="3" y="9" width="3" height="3"/><rect x="9" y="9" width="3" height="3"/>' +
  '</svg>';

/**
 * The two ends of the trip, as flat amber plates.
 *
 * Drawn as HTML rather than images: Leaflet's default marker builds its icon
 * URLs at runtime, which bundlers cannot follow and which ends in missing
 * images. A div icon sidesteps that and needs no asset files.
 *
 * The origin is a plain square and the destination carries a chequered flag,
 * so the two are told apart by shape rather than only by colour.
 */
function endpointIcon(kind: 'origin' | 'destination'): L.DivIcon {
  const inner =
    kind === 'destination'
      ? `<span style="fill:${COLORS.onAccent};display:flex">${FLAG_SVG}</span>`
      : `<span style="width:8px;height:8px;background:${COLORS.onAccent};display:block"></span>`;

  return L.divIcon({
    className: '',
    html:
      `<div style="background:${COLORS.accent};width:20px;height:20px;` +
      `border:1px solid ${COLORS.onAccent};` +
      'display:flex;align-items:center;justify-content:center">' +
      `${inner}</div>`,
    iconSize: [20, 20],
    iconAnchor: [10, 10],
  });
}

interface Props {
  place: Place;
  kind: 'origin' | 'destination';
}

/** The origin and destination plates. */
function EndpointMarkerView({ place, kind }: Props) {
  const icon = useMemo(() => endpointIcon(kind), [kind]);

  return (
    <Marker position={[place.lat, place.lon]} icon={icon}>
      <Popup>
        <strong>{kind === 'origin' ? 'ORIGIN' : 'DESTINATION'}</strong>
        <br />
        {place.label}
      </Popup>
    </Marker>
  );
}

/** Memoised so that moving the forecast slider, which re-renders the app, skips it. */
export const EndpointMarker = memo(EndpointMarkerView);
