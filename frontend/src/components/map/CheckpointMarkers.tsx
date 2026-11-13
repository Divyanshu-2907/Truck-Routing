import type { PathOptions } from 'leaflet';
import { memo } from 'react';
import { CircleMarker, Popup, Tooltip } from 'react-leaflet';

import { formatCheckpointTime } from '../../format';
import { RISK_COLORS, RISK_OUTLINE } from '../../riskScale';
import { COLORS, FONT_MONO } from '../../theme';
import type { Checkpoint, RiskLevel } from '../../types';

/**
 * Style objects are made once, not on every render. react-leaflet restyles a
 * shape whenever it is handed a new style object, so an inline object here
 * would restyle every checkpoint each time the forecast slider moves.
 */
const MARKER_STYLES = Object.fromEntries(
  ([0, 1, 2, 3, 4] as RiskLevel[]).map((level) => [
    level,
    // Outlined in near-black, not white: it separates the Moderate yellow
    // from the amber accent and keeps every dot legible on pale terrain.
    { color: RISK_OUTLINE, weight: 1.5, fillColor: RISK_COLORS[level], fillOpacity: 1 },
  ]),
) as Record<RiskLevel, PathOptions>;

/** The truck's position at the current forecast hour: an amber ring. */
const TRUCK_RING_STYLE: PathOptions = { color: COLORS.accent, weight: 2, fill: false };

interface Props {
  checkpoint: Checkpoint;
  isTruckHere: boolean;
}

/**
 * One checkpoint: a circle coloured by its risk, with the weather behind
 * that verdict in its popup. The one the truck has reached at the current
 * forecast hour gets a ring around it.
 */
function CheckpointMarkerView({ checkpoint, isTruckHere }: Props) {
  return (
    <>
      {isTruckHere ? (
        <CircleMarker
          center={[checkpoint.lat, checkpoint.lon]}
          radius={14}
          pathOptions={TRUCK_RING_STYLE}
          interactive={false}
        />
      ) : null}

      <CircleMarker
        center={[checkpoint.lat, checkpoint.lon]}
        radius={isTruckHere ? 8 : 6}
        pathOptions={MARKER_STYLES[checkpoint.level]}
      >
        {isTruckHere ? (
          <Tooltip permanent direction="top" offset={[0, -14]}>
            Truck here
          </Tooltip>
        ) : null}

        <Popup>
          <strong style={{ fontFamily: FONT_MONO }}>
            MM {Math.round(checkpoint.mile).toLocaleString()}
          </strong>{' '}
          · {checkpoint.condition} · {checkpoint.level_label}
          <br />
          Arrives {formatCheckpointTime(checkpoint.eta, checkpoint.lat, checkpoint.lon)}
          <br />
          Wind {checkpoint.wind_mph.toFixed(1)} mph · Rain {checkpoint.rain_in.toFixed(2)} in/hr ·
          Snow {checkpoint.snow_in.toFixed(2)} in/hr
          <br />
          <em>{checkpoint.reason}</em>
        </Popup>
      </CircleMarker>
    </>
  );
}

/**
 * Memoised so a slider move re-renders only the checkpoints whose "truck here"
 * state actually changes - usually two of them - not every circle on the route.
 */
export const CheckpointMarker = memo(CheckpointMarkerView);
