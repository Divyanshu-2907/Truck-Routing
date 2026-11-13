import InsightsIcon from '@mui/icons-material/Insights';
import TuneIcon from '@mui/icons-material/Tune';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Drawer from '@mui/material/Drawer';
import useMediaQuery from '@mui/material/useMediaQuery';
import { useTheme } from '@mui/material/styles';
import { useCallback, useRef, useState } from 'react';

import { ApiError, fetchHeatmap, planTrip } from './api/client';
import { ForecastSlider } from './components/ForecastSlider';
import { LeftPanel } from './components/LeftPanel';
import { MapView } from './components/MapView';
import { RightPanel } from './components/RightPanel';
import { RoutePills } from './components/RoutePills';
import type { MapFocus } from './components/map/MapEffects';
import type { ExampleTrip } from './exampleTrips';
import { nextFullHour } from './format';
import type { HeatmapMetric } from './heatmapMetrics';
import type { Checkpoint, HeatmapResponse, PlanRequest, PlanResponse, Place } from './types';
import { COLORS } from './theme';
import { readTripFromUrl, writeTripToUrl } from './urlState';

const LEFT_PANEL_WIDTH = 340;
const RIGHT_PANEL_WIDTH = 360;

/**
 * Holds the state the whole app shares: the current plan, which route the
 * driver is looking at, and where the forecast slider is.
 */
export function App() {
  // A shared link is read once, before the first render, so the form can
  // start filled in and plan itself.
  const [sharedTrip] = useState(() => readTripFromUrl());
  // The last trip asked for. Keeping it means the form can be rebuilt with
  // the same values when it remounts, which happens every time a drawer
  // opens or the window crosses a breakpoint.
  const [formSeed, setFormSeed] = useState<PlanRequest | null>(sharedTrip);
  const [formKey, setFormKey] = useState(0);
  // One-shot: plan without a click, for a shared link or an example chip.
  const [autoSubmit, setAutoSubmit] = useState(sharedTrip !== null);

  const [plan, setPlan] = useState<PlanResponse | null>(null);
  const [selectedIndex, setSelectedIndex] = useState(0);
  const [endpoints, setEndpoints] = useState<{ origin: Place; destination: Place } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [focus, setFocus] = useState<MapFocus | null>(null);

  const [heatmap, setHeatmap] = useState<HeatmapResponse | null>(null);
  const [heatmapLoading, setHeatmapLoading] = useState(false);
  const [hourIndex, setHourIndex] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [heatmapVisible, setHeatmapVisible] = useState(true);
  const [heatmapMetric, setHeatmapMetric] = useState<HeatmapMetric>('risk');

  const theme = useTheme();
  // Below 1200px the analytics panel folds away; below 800px so does the form.
  const hideRightPanel = useMediaQuery('(max-width:1200px)');
  const hideLeftPanel = useMediaQuery('(max-width:800px)');
  const [leftOpen, setLeftOpen] = useState(false);
  const [rightOpen, setRightOpen] = useState(false);

  // Kept so the Retry button can repeat the request that failed.
  const lastRequest = useRef<PlanRequest | null>(null);

  const handleSubmit = useCallback(async (request: PlanRequest) => {
    lastRequest.current = request;
    setLoading(true);
    setError(null);
    setHeatmap(null);
    setPlaying(false);
    setHourIndex(0);
    setFocus(null);
    setFormSeed(request);
    setAutoSubmit(false);
    setLeftOpen(false);
    // Put the trip in the address bar so the link can be shared.
    writeTripToUrl(request);

    try {
      const result = await planTrip(request);
      setPlan(result);
      // Start on the recommended route, which is the point of the app.
      setSelectedIndex(result.recommended_index);
      setEndpoints({ origin: request.origin, destination: request.destination });

      // The heatmap is fetched only once the routes are on screen. It is
      // the slower of the two calls, and the driver should not wait for a
      // 48 hour forecast before seeing which route is recommended.
      setHeatmapLoading(true);
      fetchHeatmap({
        origin: request.origin,
        destination: request.destination,
        departure: request.departure,
        load_lb: request.load_lb,
      })
        .then((grid) => setHeatmap(grid))
        // A missing heatmap is not worth an error banner over a good plan.
        .catch(() => setHeatmap(null))
        .finally(() => setHeatmapLoading(false));
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : 'Something went wrong planning this trip.',
      );
      setPlan(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const handleRetry = useCallback(() => {
    if (lastRequest.current) {
      void handleSubmit(lastRequest.current);
    }
  }, [handleSubmit]);

  // An example chip refills the form and plans it. Remounting the form with
  // a new key is the simplest way to reset every field at once.
  const handlePickExample = useCallback((trip: ExampleTrip) => {
    setFormSeed({
      origin: trip.origin,
      destination: trip.destination,
      departure: nextFullHour().toISOString(),
      load_lb: 40_000,
      interval_miles: 25,
    });
    setAutoSubmit(true);
    setFormKey((key) => key + 1);
  }, []);

  const handleFocusCheckpoint = useCallback((checkpoint: Checkpoint) => {
    setFocus((previous) => ({
      lat: checkpoint.lat,
      lon: checkpoint.lon,
      nonce: (previous?.nonce ?? 0) + 1,
    }));
  }, []);

  const leftPanel = (
    <LeftPanel
      key={formKey}
      weatherSource={plan?.weather_source ?? null}
      onSubmit={handleSubmit}
      onPickExample={handlePickExample}
      loading={loading}
      error={error}
      initial={formSeed}
      autoSubmit={autoSubmit}
      showExamples={!plan && !loading}
    />
  );

  const rightPanel = (
    <RightPanel
      plan={plan}
      selectedIndex={selectedIndex}
      onSelectRoute={setSelectedIndex}
      onFocusCheckpoint={handleFocusCheckpoint}
      loading={loading}
      error={error}
      onRetry={handleRetry}
    />
  );

  const panelStyle = { borderColor: COLORS.border, backgroundColor: COLORS.panel };

  return (
    <Box
      sx={{
        display: 'flex',
        height: '100vh',
        width: '100vw',
        overflow: 'hidden',
        backgroundColor: 'background.default',
      }}
    >
      {hideLeftPanel ? null : (
        <Box
          component="aside"
          sx={{
            ...panelStyle,
            width: LEFT_PANEL_WIDTH,
            flexShrink: 0,
            borderRight: '1px solid',
            display: 'flex',
          }}
        >
          {leftPanel}
        </Box>
      )}

      <Box component="main" sx={{ flex: 1, minWidth: 0, position: 'relative' }}>
        <MapView
          plan={plan}
          selectedIndex={selectedIndex}
          onSelectRoute={setSelectedIndex}
          origin={endpoints?.origin ?? null}
          destination={endpoints?.destination ?? null}
          heatmap={heatmap}
          hourIndex={hourIndex}
          heatmapVisible={heatmapVisible}
          heatmapMetric={heatmapMetric}
          focus={focus}
        />

        {plan ? (
          <RoutePills plan={plan} selectedIndex={selectedIndex} onSelect={setSelectedIndex} />
        ) : null}

        {plan ? (
          <ForecastSlider
            heatmap={heatmap}
            origin={endpoints?.origin ?? null}
            loading={heatmapLoading}
            hourIndex={hourIndex}
            onHourChange={setHourIndex}
            playing={playing}
            onPlayingChange={setPlaying}
            visible={heatmapVisible}
            onVisibleChange={setHeatmapVisible}
            metric={heatmapMetric}
            onMetricChange={setHeatmapMetric}
          />
        ) : null}

        {/* Buttons for whichever panels are folded away at this width. */}
        <Box
          sx={{
            position: 'absolute',
            top: 16,
            left: 16,
            right: 16,
            zIndex: 1000,
            display: 'flex',
            justifyContent: 'space-between',
            pointerEvents: 'none',
          }}
        >
          {hideLeftPanel ? (
            <Button
              variant="contained"
              size="small"
              startIcon={<TuneIcon />}
              onClick={() => setLeftOpen(true)}
              sx={{ pointerEvents: 'auto' }}
            >
              Trip
            </Button>
          ) : (
            <Box />
          )}

          {hideRightPanel && plan ? (
            <Button
              variant="contained"
              size="small"
              startIcon={<InsightsIcon />}
              onClick={() => setRightOpen(true)}
              sx={{ pointerEvents: 'auto' }}
            >
              Analysis
            </Button>
          ) : (
            <Box />
          )}
        </Box>
      </Box>

      {hideRightPanel ? null : (
        <Box
          component="aside"
          sx={{
            ...panelStyle,
            width: RIGHT_PANEL_WIDTH,
            flexShrink: 0,
            borderLeft: '1px solid',
            display: 'flex',
          }}
        >
          {rightPanel}
        </Box>
      )}

      {/* The form becomes a bottom sheet on a phone. */}
      <Drawer
        anchor="bottom"
        open={hideLeftPanel && leftOpen}
        onClose={() => setLeftOpen(false)}
        slotProps={{
          paper: {
            sx: {
              height: '82vh',
              borderTopLeftRadius: theme.shape.borderRadius,
              borderTopRightRadius: theme.shape.borderRadius,
            },
          },
        }}
      >
        {hideLeftPanel ? leftPanel : null}
      </Drawer>

      {/* The analytics become a side drawer on a narrow laptop. */}
      <Drawer
        anchor="right"
        open={hideRightPanel && rightOpen}
        onClose={() => setRightOpen(false)}
        slotProps={{ paper: { sx: { width: Math.min(RIGHT_PANEL_WIDTH, 420) } } }}
      >
        {hideRightPanel ? rightPanel : null}
      </Drawer>
    </Box>
  );
}
