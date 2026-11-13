import Box from '@mui/material/Box';
import Typography from '@mui/material/Typography';
import { useMemo } from 'react';

import { summariseWeather } from '../routeWeather';
import { COLORS, MONO_SX } from '../theme';
import type { PlannedRoute } from '../types';

interface Props {
  route: PlannedRoute;
}

/**
 * The worst readings on a route, in one line.
 *
 * Two routes can share a risk score and still be very different drives.
 * This says which one has the gale and roughly where, so the comparison
 * is about weather rather than only about a number.
 */
export function RouteWeatherLine({ route }: Props) {
  const weather = useMemo(() => summariseWeather(route), [route]);

  const atMile =
    weather.peakWindMph > 0 ? ` @ MM ${Math.round(weather.peakWindMile).toLocaleString()}` : '';

  const readings = [
    `WIND ${weather.peakWindMph.toFixed(0)} MPH${atMile}`,
    `RAIN ${weather.peakRainIn.toFixed(2)} IN/HR`,
    `SNOW ${weather.peakSnowIn.toFixed(2)} IN/HR`,
  ];

  return (
    <Typography
      component="div"
      sx={{ ...MONO_SX, fontSize: 10, color: COLORS.textSecondary, lineHeight: 1.6 }}
    >
      {readings.join(' · ')} ·{' '}
      <Box component="span" sx={{ color: weather.aboveLow > 0 ? COLORS.text : 'inherit' }}>
        {weather.aboveLow}/{weather.total} ABOVE LOW
      </Box>
    </Typography>
  );
}
