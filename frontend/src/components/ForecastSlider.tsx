import PauseIcon from '@mui/icons-material/Pause';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import Box from '@mui/material/Box';
import CircularProgress from '@mui/material/CircularProgress';
import FormControlLabel from '@mui/material/FormControlLabel';
import IconButton from '@mui/material/IconButton';
import Paper from '@mui/material/Paper';
import Slider from '@mui/material/Slider';
import Stack from '@mui/material/Stack';
import Switch from '@mui/material/Switch';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Typography from '@mui/material/Typography';
import { useEffect } from 'react';

import { formatCheckpointTime, formatLocalDateTime } from '../format';
import { METRICS, METRIC_ORDER, type HeatmapMetric } from '../heatmapMetrics';
import { MAP_CARD } from '../styles';
import { COLORS, LABEL_SX, MONO_SX } from '../theme';
import type { HeatmapResponse, Place } from '../types';

/** How long each hour is shown for while playing. */
const FRAME_MS = 400;

interface Props {
  heatmap: HeatmapResponse | null;
  /** The trip's origin, whose local time the forecast hours are read in. */
  origin: Place | null;
  metric: HeatmapMetric;
  onMetricChange: (metric: HeatmapMetric) => void;
  loading: boolean;
  hourIndex: number;
  onHourChange: (hour: number) => void;
  playing: boolean;
  onPlayingChange: (playing: boolean) => void;
  visible: boolean;
  onVisibleChange: (visible: boolean) => void;
}

/**
 * The forecast controls that float over the bottom of the map: a 0-48 hour
 * slider, a play button that steps through the hours, and a switch to hide
 * the heatmap.
 */
export function ForecastSlider({
  heatmap,
  origin,
  metric,
  onMetricChange,
  loading,
  hourIndex,
  onHourChange,
  playing,
  onPlayingChange,
  visible,
  onVisibleChange,
}: Props) {
  const hourCount = heatmap ? heatmap.times.length : 0;

  // Playing simply moves the slider; everything else reacts to that.
  useEffect(() => {
    if (!playing || hourCount === 0) {
      return;
    }
    const timer = window.setInterval(() => {
      onHourChange((hourIndex + 1) % hourCount);
    }, FRAME_MS);

    return () => window.clearInterval(timer);
  }, [playing, hourIndex, hourCount, onHourChange]);

  // Nothing to scrub through until the heatmap arrives.
  useEffect(() => {
    if (hourCount === 0 && playing) {
      onPlayingChange(false);
    }
  }, [hourCount, playing, onPlayingChange]);

  const currentTime = heatmap?.times[hourIndex];

  return (
    <Paper
      elevation={0}
      sx={{
        ...MAP_CARD,
        position: 'absolute',
        left: '50%',
        transform: 'translateX(-50%)',
        // Sits above the drawer button on a phone, clear of the legend on a laptop.
        bottom: { xs: 64, md: 24 },
        zIndex: 1000, // Above Leaflet's own panes.
        width: { xs: 'calc(100% - 24px)', md: 'min(760px, calc(100% - 220px))' },
        px: 2,
        py: 1,
      }}
    >
      <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>
        <IconButton
          size="small"
          color="primary"
          disabled={!heatmap}
          onClick={() => onPlayingChange(!playing)}
          aria-label={playing ? 'Pause forecast' : 'Play forecast'}
        >
          {playing ? <PauseIcon /> : <PlayArrowIcon />}
        </IconButton>

        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Stack
            direction="row"
            spacing={1}
            sx={{ alignItems: 'baseline', justifyContent: 'space-between' }}
          >
            <Typography sx={{ ...MONO_SX, fontSize: 12, whiteSpace: 'nowrap' }}>
              <Box component="span" sx={{ color: COLORS.accent }}>
                {hourIndex === 0 ? 'DEPARTURE' : `+${String(hourIndex).padStart(2, '0')}H`}
              </Box>
              {currentTime ? `  ${formatForecastTime(currentTime, origin)}` : ''}
            </Typography>
            {loading ? (
              <Stack direction="row" spacing={0.75} sx={{ alignItems: 'center' }}>
                <CircularProgress size={12} />
                <Typography sx={{ ...LABEL_SX, fontSize: 10 }}>Loading forecast</Typography>
              </Stack>
            ) : heatmap ? null : (
              // The plan is still good without it, so this is a note, not an error.
              <Typography sx={{ ...LABEL_SX, fontSize: 10 }}>Forecast unavailable</Typography>
            )}
          </Stack>

          <Slider
            size="small"
            min={0}
            max={Math.max(hourCount - 1, 0)}
            step={1}
            value={hourIndex}
            disabled={!heatmap}
            marks={hourCount > 0 ? HOUR_MARKS.filter((mark) => mark.value < hourCount) : false}
            valueLabelDisplay="auto"
            valueLabelFormat={(hour: number) => `+${hour}h`}
            onChange={(_event, value) => {
              onPlayingChange(false);
              onHourChange(value as number);
            }}
            sx={{ mt: -0.5 }}
          />
        </Box>

        <Stack direction="row" spacing={0.75} sx={{ alignItems: 'center' }}>
          {/* Which reading the heat shows. All four grids arrive with the
              forecast, so switching costs no request. */}
          <ToggleButtonGroup
            exclusive
            size="small"
            value={metric}
            disabled={!heatmap || !visible}
            onChange={(_event, next: HeatmapMetric | null) => {
              if (next !== null) {
                onMetricChange(next);
              }
            }}
          >
            {METRIC_ORDER.map((option) => (
              <ToggleButton key={option} value={option} sx={{ px: 1, py: 0.25, fontSize: 10 }}>
                {METRICS[option].label}
              </ToggleButton>
            ))}
          </ToggleButtonGroup>

          <FormControlLabel
            control={
              <Switch
                size="small"
                checked={visible}
                onChange={(event) => onVisibleChange(event.target.checked)}
              />
            }
            label={
              <Typography sx={{ ...LABEL_SX, fontSize: 10, whiteSpace: 'nowrap' }}>
                Heat
              </Typography>
            }
            sx={{ mr: 0 }}
          />
        </Stack>
      </Stack>
    </Paper>
  );
}

/**
 * Tick marks every twelve hours. Only the ones inside the slider's range are
 * shown: a trip leaving near the end of the forecast gets fewer hours.
 */
const HOUR_MARKS = [0, 12, 24, 36, 48].map((hour) => ({
  value: hour,
  label: hour === 0 ? '0' : `${hour}h`,
}));

/**
 * A forecast hour in the origin's local time.
 *
 * The slider is read against the checkpoint ETAs beside it, and those are
 * in local time along the route, so a browser-clock reading here would
 * invite the two to be compared wrongly. Before a trip is planned there is
 * no origin, and the browser's own zone is used.
 */
function formatForecastTime(iso: string, origin: Place | null): string {
  if (!origin) {
    return formatLocalDateTime(iso);
  }
  return formatCheckpointTime(iso, origin.lat, origin.lon);
}
