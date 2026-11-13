import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';

import { formatLocalDateTime } from '../format';
import { RISK_COLORS, RISK_LABELS, riskScore, riskScoreLevel } from '../riskScale';
import { COLORS, LABEL_SX, MONO_SX } from '../theme';
import type { PlannedRoute } from '../types';

interface Props {
  route: PlannedRoute;
}

/**
 * The headline numbers for the selected route.
 *
 * Every tile is a figure the backend returned; the only arithmetic here is
 * turning the mile-weighted average risk (0-4) into a 0-100 score, which is
 * easier to compare at a glance than a number out of four.
 */
export function StatTiles({ route }: Props) {
  const { summary } = route;
  const arrival = route.checkpoints.at(-1)?.eta;
  const score = riskScore(summary.average_risk);
  const scoreLevel = riskScoreLevel(summary.average_risk);

  return (
    <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 1 }}>
      <Tile label="Distance" value={Math.round(summary.distance_miles).toLocaleString()} unit="mi" />
      <Tile label="Drive time" value={summary.duration_text} />
      <Tile
        label="Risk score"
        value={String(score)}
        unit="/100"
        note={RISK_LABELS[scoreLevel]}
        color={RISK_COLORS[scoreLevel]}
      />
      <Tile
        label="Worst conditions"
        value={summary.max_level_label.toUpperCase()}
        color={RISK_COLORS[summary.max_level]}
        small
      />
      <Tile
        label="Arrival"
        value={arrival ? formatLocalDateTime(arrival) : '—'}
        note={`${summary.checkpoint_count} checkpoints sampled`}
        span={2}
        small
      />
    </Box>
  );
}

interface TileProps {
  label: string;
  value: string;
  unit?: string;
  note?: string;
  color?: string;
  span?: number;
  /** Text values need a smaller size than figures to fit the tile. */
  small?: boolean;
}

function Tile({ label, value, unit, note, color, span, small }: TileProps) {
  return (
    <Box
      sx={{
        p: 1,
        gridColumn: span ? `span ${span}` : undefined,
        border: `1px solid ${COLORS.border}`,
        backgroundColor: COLORS.raised,
      }}
    >
      <Typography sx={{ ...LABEL_SX, fontSize: 10, display: 'block', mb: 0.375 }}>
        {label}
      </Typography>
      <Typography
        component="div"
        sx={{
          ...MONO_SX,
          fontSize: small ? 13 : 19,
          fontWeight: 500,
          lineHeight: 1.2,
          color: color ?? COLORS.text,
        }}
      >
        {value}
        {unit ? (
          <Box component="span" sx={{ fontSize: 11, color: COLORS.textSecondary, ml: 0.5 }}>
            {unit}
          </Box>
        ) : null}
      </Typography>
      {note ? (
        <Typography sx={{ ...MONO_SX, fontSize: 10, color: COLORS.textSecondary, mt: 0.25 }}>
          {note}
        </Typography>
      ) : null}
    </Box>
  );
}
