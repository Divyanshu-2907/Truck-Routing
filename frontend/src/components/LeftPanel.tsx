import LocalShippingIcon from '@mui/icons-material/LocalShipping';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Divider from '@mui/material/Divider';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { memo } from 'react';

import type { ExampleTrip } from '../exampleTrips';
import { COLORS, FONT_CONDENSED, MONO_SX } from '../theme';
import type { PlanRequest } from '../types';
import { ApiStatusChip } from './ApiStatusChip';
import { EmptyState } from './EmptyState';
import { PlanForm } from './PlanForm';

interface Props {
  onSubmit: (request: PlanRequest) => void;
  onPickExample: (trip: ExampleTrip) => void;
  loading: boolean;
  error: string | null;
  initial: PlanRequest | null;
  autoSubmit: boolean;
  /** Example chips only make sense before the first plan. */
  showExamples: boolean;
}

/** The planning panel: what the trip is. No navigation, because there is none. */
function LeftPanelView({
  onSubmit,
  onPickExample,
  loading,
  error,
  initial,
  autoSubmit,
  showExamples,
}: Props) {
  return (
    <Stack sx={{ height: '100%', width: '100%' }}>
      <Box sx={{ px: 2, pt: 1.5, pb: 1.25 }}>
        <Stack direction="row" spacing={1.25} sx={{ alignItems: 'center' }}>
          {/* A flat amber plate, like a sign blank with a symbol stamped on it. */}
          <Box
            sx={{
              width: 30,
              height: 30,
              display: 'grid',
              placeItems: 'center',
              backgroundColor: COLORS.accent,
              flexShrink: 0,
            }}
          >
            <LocalShippingIcon sx={{ fontSize: 19, color: COLORS.onAccent }} />
          </Box>

          <Typography
            sx={{
              fontFamily: FONT_CONDENSED,
              fontWeight: 700,
              fontSize: 15,
              lineHeight: 1.1,
              letterSpacing: '0.03em',
              textTransform: 'uppercase',
              // The name is the one thing that must not wrap; the status
              // and the data sources sit on their own line below.
              whiteSpace: 'nowrap',
            }}
          >
            Weather-Aware Truck Routing
          </Typography>
        </Stack>

        <Stack
          direction="row"
          spacing={1}
          sx={{ alignItems: 'center', justifyContent: 'space-between', mt: 0.75 }}
        >
          {/* Naming the services is a fair claim about where the data
              comes from, and useful to anyone reviewing the app. */}
          <Typography
            sx={{
              ...MONO_SX,
              fontSize: 9,
              color: COLORS.textSecondary,
              lineHeight: 1.5,
              whiteSpace: 'nowrap',
            }}
          >
            WEATHER: OPEN-METEO · ROUTING: OSRM
          </Typography>

          <ApiStatusChip />
        </Stack>
      </Box>
      <Divider />

      <Box sx={{ flex: 1, overflowY: 'auto', px: 2, py: 1.5 }}>
        <Stack spacing={1.5}>
          <PlanForm
            onSubmit={onSubmit}
            loading={loading}
            initial={initial}
            autoSubmit={autoSubmit}
          />

          {error ? <Alert severity="error">{error}</Alert> : null}

          {showExamples ? <EmptyState onPick={onPickExample} /> : null}
        </Stack>
      </Box>
    </Stack>
  );
}

/**
 * Memoised so that moving the forecast slider, which re-renders the app, skips it.
 */
export const LeftPanel = memo(LeftPanelView);
