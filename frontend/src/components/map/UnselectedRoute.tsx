import type { PathOptions } from 'leaflet';
import { memo, useState } from 'react';
import { Polyline, Tooltip } from 'react-leaflet';

/**
 * The routes the driver is not looking at.
 *
 * A pale dashed line on its own disappears against grey terrain, so each
 * one is drawn over a dark casing - the same trick the selected route uses.
 * The casing is also the wider of the two shapes and the only interactive
 * one, which gives the thin dashed line a 6px target to be clicked on.
 */
const CASING: PathOptions = { color: '#000000', opacity: 0.6, weight: 6, lineCap: 'round' };
const CASING_HOVER: PathOptions = { ...CASING, opacity: 0.75, weight: 8 };

const LINE: PathOptions = {
  color: '#cbd5e1',
  opacity: 0.85,
  weight: 3.5,
  dashArray: '7 5',
};
/** Hover fills the dashes in and brightens the line, without using the
    amber that marks the selected route. */
const LINE_HOVER: PathOptions = {
  color: '#ffffff',
  opacity: 1,
  weight: 4.5,
  dashArray: undefined,
};

interface Props {
  positions: [number, number][];
  onSelect: () => void;
  label: string;
}

function UnselectedRouteView({ positions, onSelect, label }: Props) {
  const [hovered, setHovered] = useState(false);

  return (
    <>
      <Polyline
        positions={positions}
        pathOptions={hovered ? CASING_HOVER : CASING}
        eventHandlers={{
          click: onSelect,
          mouseover: () => setHovered(true),
          mouseout: () => setHovered(false),
        }}
      >
        {/* Names the route under the cursor, so the highlight is not the
            only clue about which line is which. */}
        <Tooltip sticky>{label}</Tooltip>
      </Polyline>
      <Polyline
        positions={positions}
        pathOptions={hovered ? LINE_HOVER : LINE}
        interactive={false}
      />
    </>
  );
}

export const UnselectedRoute = memo(UnselectedRouteView);
