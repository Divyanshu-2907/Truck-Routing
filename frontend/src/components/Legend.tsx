import Box from '@mui/material/Box';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { memo } from 'react';

import { RISK_COLORS, RISK_LABELS, RISK_LEVELS, RISK_OUTLINE } from '../riskScale';
import { MAP_CARD } from '../styles';
import { FONT_CONDENSED, LABEL_SX } from '../theme';

/**
 * The risk colour key, in the top right of the map.
 *
 * Below 1200px the analysis panel collapses into a button in that same
 * corner, so the legend drops below it rather than moving somewhere less
 * expected.
 */
function LegendView() {
  return (
    <Paper
      elevation={0}
      sx={{
        ...MAP_CARD,
        position: 'absolute',
        right: 12,
        top: 12,
        '@media (max-width: 1200px)': { top: 60 },
        zIndex: 1000, // Above Leaflet's own panes.
        px: 1,
        py: 0.75,
      }}
    >
      <Typography sx={{ ...LABEL_SX, fontSize: 10, display: 'block', mb: 0.5 }}>
        Risk
      </Typography>
      <Stack spacing={0.25}>
        {RISK_LEVELS.map((level) => (
          <Stack key={level} direction="row" spacing={0.75} sx={{ alignItems: 'center' }}>
            <Box
              sx={{
                width: 9,
                height: 9,
                bgcolor: RISK_COLORS[level],
                border: `1px solid ${RISK_OUTLINE}`,
                flexShrink: 0,
              }}
            />
            <Typography
              sx={{
                fontFamily: FONT_CONDENSED,
                fontWeight: 600,
                fontSize: 12,
                lineHeight: 1.45,
                letterSpacing: '0.04em',
                textTransform: 'uppercase',
                whiteSpace: 'nowrap',
              }}
            >
              {RISK_LABELS[level]}
            </Typography>
          </Stack>
        ))}
      </Stack>
    </Paper>
  );
}

/** The legend never changes, so it never needs to re-render. */
export const Legend = memo(LegendView);
