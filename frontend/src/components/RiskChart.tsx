import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import { useCallback, useMemo } from 'react';
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';

import { formatCheckpointTime } from '../format';
import { RISK_COLORS, RISK_LABELS } from '../riskScale';
import { COLORS, FONT_MONO, LABEL_SX, MONO_SX } from '../theme';
import type { Checkpoint, PlannedRoute, RiskLevel } from '../types';

/** Grid lines, and therefore axis ticks, every 50 miles. */
const MILE_GRID = 50;

/** One point on the chart, carrying enough to explain itself on hover. */
interface Point {
  mile: number;
  level: number;
  eta: string;
  lat: number;
  lon: number;
  condition: string;
  reason: string;
  checkpoint: Checkpoint;
}

interface Props {
  route: PlannedRoute;
  onFocusCheckpoint: (checkpoint: Checkpoint) => void;
}

/**
 * Risk level against distance, drawn as a strip chart.
 *
 * Stepped, because risk is a level held over a stretch of road rather than
 * a value sliding between checkpoints: the line should stay flat until the
 * next checkpoint and then jump. Clicking a point moves the map there.
 */
function RiskChart({ route, onFocusCheckpoint }: Props) {
  const data = useMemo<Point[]>(
    () =>
      route.checkpoints.map((checkpoint) => ({
        mile: Math.round(checkpoint.mile),
        level: checkpoint.level,
        eta: checkpoint.eta,
        lat: checkpoint.lat,
        lon: checkpoint.lon,
        condition: checkpoint.condition,
        reason: checkpoint.reason,
        checkpoint,
      })),
    [route],
  );

  // Ticks on round 50 mile marks rather than wherever a checkpoint landed,
  // so the grid reads like a distance scale.
  const ticks = useMemo(() => {
    const last = data.at(-1)?.mile ?? 0;
    const marks: number[] = [];
    for (let mile = 0; mile <= last; mile += MILE_GRID) {
      marks.push(mile);
    }
    return marks;
  }, [data]);

  // Recharts 3 hands the click the index of the active point rather than
  // the row itself, so the checkpoint is looked up in our own data.
  const handleClick = useCallback(
    (state: { activeIndex: number | string | null | undefined }) => {
      const index = Number(state.activeIndex);
      const point = Number.isFinite(index) ? data[index] : undefined;
      if (point) {
        onFocusCheckpoint(point.checkpoint);
      }
    },
    [data, onFocusCheckpoint],
  );

  if (data.length === 0) {
    return null;
  }

  return (
    <Box>
      <Typography sx={{ ...LABEL_SX, fontSize: 11, display: 'block' }}>
        Risk by mile
      </Typography>
      <Typography sx={{ fontSize: 11, color: COLORS.textSecondary }}>
        Click a point to move the map there
      </Typography>

      <Box sx={{ height: 150, mt: 1, cursor: 'pointer' }}>
        <ResponsiveContainer width="100%" height="100%">
          <AreaChart
            data={data}
            margin={{ top: 4, right: 4, bottom: 0, left: -30 }}
            onClick={handleClick}
          >
            <CartesianGrid stroke={COLORS.border} strokeDasharray="2 2" />
            <XAxis
              dataKey="mile"
              type="number"
              domain={[0, 'dataMax']}
              ticks={ticks}
              tick={{ fill: COLORS.textSecondary, fontSize: 9, fontFamily: FONT_MONO }}
              tickLine={false}
              axisLine={{ stroke: COLORS.border }}
            />
            <YAxis
              domain={[0, 4]}
              ticks={[0, 1, 2, 3, 4]}
              tick={{ fill: COLORS.textSecondary, fontSize: 9, fontFamily: FONT_MONO }}
              tickLine={false}
              axisLine={false}
              width={52}
            />
            <Tooltip content={<RiskTooltip />} cursor={{ stroke: COLORS.accent }} />
            <Area
              type="stepAfter"
              dataKey="level"
              stroke={COLORS.accent}
              strokeWidth={1.5}
              fill={COLORS.accent}
              fillOpacity={0.2}
              dot={<RiskDot />}
              activeDot={{ r: 4, fill: COLORS.accent, stroke: COLORS.background, strokeWidth: 1 }}
              isAnimationActive={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      </Box>
    </Box>
  );
}

/** Each point is a small square in its own risk colour, matching the map. */
function RiskDot(props: { cx?: number; cy?: number; payload?: Point }) {
  const { cx, cy, payload } = props;
  if (cx === undefined || cy === undefined || !payload) {
    return null;
  }
  return (
    <rect
      x={cx - 2.5}
      y={cy - 2.5}
      width={5}
      height={5}
      fill={RISK_COLORS[payload.level as RiskLevel]}
      stroke={COLORS.background}
      strokeWidth={1}
    />
  );
}

function RiskTooltip(props: { active?: boolean; payload?: { payload: Point }[] }) {
  const point = props.payload?.[0]?.payload;
  if (!props.active || !point) {
    return null;
  }

  return (
    <Box sx={{ p: 1, backgroundColor: COLORS.panel, border: `1px solid ${COLORS.border}` }}>
      <Typography sx={{ ...MONO_SX, fontSize: 11, display: 'block' }}>
        MM {point.mile.toLocaleString()}{' '}
        <Box component="span" sx={{ color: RISK_COLORS[point.level as RiskLevel] }}>
          {RISK_LABELS[point.level as RiskLevel].toUpperCase()}
        </Box>
      </Typography>
      <Typography sx={{ ...MONO_SX, fontSize: 10, color: COLORS.textSecondary, display: 'block' }}>
        {formatCheckpointTime(point.eta, point.lat, point.lon)}
      </Typography>
      <Typography sx={{ ...LABEL_SX, fontSize: 10, color: COLORS.text, display: 'block' }}>
        {point.condition}
      </Typography>
      <Typography sx={{ fontSize: 11, color: COLORS.textSecondary }}>{point.reason}</Typography>
    </Box>
  );
}

// Default export so this module, and the Recharts library it pulls in, can
// be split out of the main bundle with React.lazy.
export default RiskChart;
