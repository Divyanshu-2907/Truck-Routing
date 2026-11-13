import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Divider from '@mui/material/Divider';
import Skeleton from '@mui/material/Skeleton';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { lazy, memo, Suspense } from 'react';

import { formatLocalTime } from '../format';
import {
  LOAD_RULES,
  RISK_COLORS,
  RISK_LABELS,
  RISK_LEVELS,
  RISK_OUTLINE,
  RISK_THRESHOLDS,
} from '../riskScale';
import { COLORS, LABEL_SX, MONO_SX } from '../theme';
import type { Checkpoint, PlanResponse } from '../types';
import { CheckpointList } from './CheckpointList';
import { RouteComparison } from './RouteComparison';
import { RouteWeatherLine } from './RouteWeatherLine';
import { StatTiles } from './StatTiles';
import { WhyThisRoute } from './WhyThisRoute';

/**
 * The chart is the only part of the app that needs Recharts, which is a
 * large library. Loading it separately keeps it out of the first download:
 * the map and the recommendation appear without waiting for a chart that is
 * further down the panel.
 */
const RiskChart = lazy(() => import('./RiskChart'));

/** Reserves the chart's space while its code is on the way. */
const CHART_HEIGHT = 186;

interface Props {
  plan: PlanResponse | null;
  selectedIndex: number;
  onSelectRoute: (index: number) => void;
  onFocusCheckpoint: (checkpoint: Checkpoint) => void;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
}

/**
 * Everything the driver needs after the routes are drawn: the numbers for
 * the route they are looking at, how the three compare, and why one of them
 * is recommended.
 */
function RightPanelView({
  plan,
  selectedIndex,
  onSelectRoute,
  onFocusCheckpoint,
  loading,
  error,
  onRetry,
}: Props) {
  const route = plan?.routes[selectedIndex];

  return (
    <Stack sx={{ height: '100%', width: '100%' }}>
      <Box sx={{ px: 2, py: 1.75 }}>
        <Typography sx={{ ...LABEL_SX, fontSize: 12, color: COLORS.text, display: 'block' }}>
          Route analysis
        </Typography>
        <Typography sx={{ ...MONO_SX, fontSize: 10.5, color: COLORS.textSecondary }}>
          {route ? route.label.toUpperCase() : 'NO ROUTE SELECTED'}
        </Typography>
      </Box>
      <Divider />

      <Box sx={{ flex: 1, overflowY: 'auto', p: 2 }}>
        {error ? (
          <Alert
            severity="error"
            action={
              <Button color="inherit" size="small" onClick={onRetry}>
                Retry
              </Button>
            }
          >
            {error}
          </Alert>
        ) : loading ? (
          <PanelSkeleton />
        ) : plan && route ? (
          <Stack spacing={2.5}>
            <Box>
              <StatTiles route={route} />
              <Box sx={{ mt: 1 }}>
                <RouteWeatherLine route={route} />
              </Box>
            </Box>

            <Divider />
            <Box>
              <Typography sx={{ ...LABEL_SX, fontSize: 11, display: 'block', mb: 1 }}>
                Compare routes
              </Typography>
              <RouteComparison
                plan={plan}
                selectedIndex={selectedIndex}
                onSelect={onSelectRoute}
              />
            </Box>

            <Divider />
            <Suspense fallback={<Skeleton variant="rounded" height={CHART_HEIGHT} />}>
              <RiskChart route={route} onFocusCheckpoint={onFocusCheckpoint} />
            </Suspense>

            <Divider />
            <WhyThisRoute plan={plan} />

            <Divider />
            <CheckpointList route={route} onFocusCheckpoint={onFocusCheckpoint} />

            <Typography sx={{ ...MONO_SX, fontSize: 10, color: COLORS.textSecondary }}>
              FORECAST CHECKED {formatLocalTime(plan.generated_at)}
            </Typography>
          </Stack>
        ) : (
          <EmptyPanel />
        )}
      </Box>
    </Stack>
  );
}

/** Placeholders in the shape of the real content, so nothing jumps. */
function PanelSkeleton() {
  return (
    <Stack spacing={2}>
      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 1 }}>
        {[0, 1, 2, 3].map((index) => (
          <Skeleton key={index} variant="rounded" height={64} />
        ))}
        <Skeleton variant="rounded" height={64} sx={{ gridColumn: 'span 2' }} />
      </Box>
      <Skeleton variant="text" width={140} />
      {[0, 1, 2].map((index) => (
        <Skeleton key={index} variant="rounded" height={104} />
      ))}
      <Skeleton variant="rounded" height={CHART_HEIGHT} />
    </Stack>
  );
}

/**
 * Before the first trip the panel states the rules it will be applying,
 * rather than showing an empty box: the thresholds are the whole basis of
 * the recommendation, and this is the one moment there is room to read them.
 */
function EmptyPanel() {
  return (
    <Stack spacing={2}>
      <Box sx={{ border: `1px solid ${COLORS.border}`, p: 1.25 }}>
        <Typography sx={{ ...MONO_SX, fontSize: 12, color: COLORS.accent }}>
          AWAITING TRIP
        </Typography>
        <Typography sx={{ ...MONO_SX, fontSize: 11, color: COLORS.textSecondary, mt: 0.25 }}>
          Enter origin and destination
        </Typography>
      </Box>

      <Box>
        <Typography sx={{ ...LABEL_SX, fontSize: 11, display: 'block', mb: 1 }}>
          Risk scale
        </Typography>

        <Box sx={{ display: 'flex', height: 6, mb: 1 }}>
          {RISK_LEVELS.map((level) => (
            <Box
              key={level}
              sx={{
                flex: 1,
                backgroundColor: RISK_COLORS[level],
                border: `1px solid ${RISK_OUTLINE}`,
              }}
            />
          ))}
        </Box>

        <Stack spacing={0.75}>
          {RISK_LEVELS.map((level) => (
            <Stack key={level} direction="row" spacing={1}>
              <Box
                sx={{
                  width: 8,
                  height: 8,
                  mt: 0.5,
                  flexShrink: 0,
                  backgroundColor: RISK_COLORS[level],
                  border: `1px solid ${RISK_OUTLINE}`,
                }}
              />
              <Box sx={{ minWidth: 0 }}>
                <Typography sx={{ ...LABEL_SX, fontSize: 10, color: COLORS.text }}>
                  {RISK_LABELS[level]}
                </Typography>
                <Typography
                  sx={{ ...MONO_SX, fontSize: 9, color: COLORS.textSecondary, lineHeight: 1.5 }}
                >
                  {RISK_THRESHOLDS[level]}
                </Typography>
              </Box>
            </Stack>
          ))}
        </Stack>

        <Typography sx={{ fontSize: 11, color: COLORS.textSecondary, mt: 1.25 }}>
          A checkpoint takes the worst of its wind, rain and snow.
        </Typography>

        <Typography sx={{ ...LABEL_SX, fontSize: 10, display: 'block', mt: 1.5, mb: 0.5 }}>
          Load rules
        </Typography>
        <Stack spacing={0.25}>
          {LOAD_RULES.map((rule) => (
            <Typography
              key={rule}
              sx={{ ...MONO_SX, fontSize: 9.5, color: COLORS.textSecondary }}
            >
              {rule}
            </Typography>
          ))}
        </Stack>
      </Box>
    </Stack>
  );
}

/**
 * Memoised so that moving the forecast slider, which re-renders the app, skips it.
 * Its chart and lists only need to change when the plan or the selected route does.
 */
export const RightPanel = memo(RightPanelView);
