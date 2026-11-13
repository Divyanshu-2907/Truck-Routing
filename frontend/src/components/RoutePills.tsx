import Box from '@mui/material/Box';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { memo } from 'react';

import { MAP_CARD } from '../styles';
import { COLORS, MONO_SX, TRANSITION } from '../theme';
import type { PlanResponse } from '../types';
import { RouteShield } from './RouteShield';

interface Props {
  plan: PlanResponse;
  selectedIndex: number;
  onSelect: (index: number) => void;
}

/**
 * The route switcher, floating at the top of the map.
 *
 * It sits over the map rather than in a panel because switching routes is a
 * map action: the line, the checkpoints and the analytics all change with it.
 */
function RoutePillsView({ plan, selectedIndex, onSelect }: Props) {
  return (
    <Paper
      elevation={0}
      sx={{
        ...MAP_CARD,
        position: 'absolute',
        top: 16,
        left: '50%',
        transform: 'translateX(-50%)',
        zIndex: 1000, // Above Leaflet's own panes.
        p: 0.5,
      }}
    >
      <Stack direction="row" spacing={0.5}>
        {plan.routes.map((route, index) => {
          const selected = index === selectedIndex;
          return (
            <Box
              key={route.label}
              component="button"
              type="button"
              onClick={() => onSelect(index)}
              aria-pressed={selected}
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 0.75,
                px: 1,
                py: 0.5,
                cursor: 'pointer',
                borderRadius: 1,
                transition: TRANSITION,
                font: 'inherit',
                backgroundColor: selected ? COLORS.raised : 'transparent',
                border: `1px solid ${selected ? COLORS.accent : 'transparent'}`,
                '&:hover': { backgroundColor: COLORS.raised },
              }}
            >
              <RouteShield
                label={route.label}
                recommended={index === plan.recommended_index}
                size={20}
              />
              <Typography
                sx={{
                  ...MONO_SX,
                  fontSize: 12,
                  color: selected ? COLORS.text : COLORS.textSecondary,
                  whiteSpace: 'nowrap',
                }}
              >
                {Math.round(route.summary.distance_miles).toLocaleString()} mi
              </Typography>
            </Box>
          );
        })}
      </Stack>
    </Paper>
  );
}

/** Memoised so that moving the forecast slider, which re-renders the app, skips it. */
export const RoutePills = memo(RoutePillsView);
