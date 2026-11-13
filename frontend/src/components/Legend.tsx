import Box from '@mui/material/Box';
import Paper from '@mui/material/Paper';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { memo } from 'react';

import { METRICS, scaleTicks, type HeatmapMetric } from '../heatmapMetrics';
import { RISK_COLORS, RISK_LABELS, RISK_LEVELS, RISK_OUTLINE } from '../riskScale';
import { MAP_CARD } from '../styles';
import { COLORS, FONT_CONDENSED, LABEL_SX, MONO_SX } from '../theme';

/**
 * The risk colour key, in the top right of the map.
 *
 * Below 1200px the analysis panel collapses into a button in that same
 * corner, so the legend drops below it rather than moving somewhere less
 * expected.
 */
interface Props {
  /** Which metric the heatmap is drawing, so the key matches it. */
  metric: HeatmapMetric;
  /** With the heatmap off, only the checkpoint colours need explaining. */
  heatmapVisible: boolean;
}

function LegendView({ metric, heatmapVisible }: Props) {
  const showMetricScale = heatmapVisible && metric !== 'risk';
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
        {showMetricScale ? METRICS[metric].label : 'Risk'}
      </Typography>

      {showMetricScale ? (
        <MetricScale metric={metric} />
      ) : (
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
      )}
    </Paper>
  );
}

/**
 * The heat ramp for a raw reading, with what it is worth in real units.
 *
 * The scale tops out where that factor alone would stop travel - 55 mph,
 * 1.00 in/hr of rain, 3.0 in/hr of snow - so the darkest heat always means
 * the same thing whichever metric is on show.
 */
function MetricScale({ metric }: { metric: HeatmapMetric }) {
  const ticks = scaleTicks(metric);
  const unit = METRICS[metric].unit;

  return (
    <Box sx={{ width: 104 }}>
      <Box
        sx={{
          height: 8,
          border: `1px solid ${RISK_OUTLINE}`,
          background: `linear-gradient(90deg, ${RISK_COLORS[1]} 0%, ${RISK_COLORS[2]} 45%, ${RISK_COLORS[3]} 70%, ${RISK_COLORS[4]} 100%)`,
        }}
      />
      <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 0.25 }}>
        {ticks.map((tick) => (
          <Typography key={tick} sx={{ ...MONO_SX, fontSize: 8.5, color: COLORS.textSecondary }}>
            {tick}
          </Typography>
        ))}
      </Box>
      {unit ? (
        <Typography sx={{ ...MONO_SX, fontSize: 8.5, color: COLORS.textSecondary }}>
          {unit}
        </Typography>
      ) : null}
    </Box>
  );
}

/** Only re-renders when the metric or the heatmap's visibility changes. */
export const Legend = memo(LegendView);
