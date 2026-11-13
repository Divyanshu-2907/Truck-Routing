import Box from '@mui/material/Box';

import { COLORS, FONT_CONDENSED } from '../theme';

interface Props {
  /** The route's label, e.g. "Route A". Only its last letter is shown. */
  label: string;
  /** The recommended route gets the green shield; the rest are blue. */
  recommended?: boolean;
  size?: number;
}

/**
 * A route marker shaped like an interstate shield.
 *
 * It does the same job the plain "Route A" text did, in the visual language
 * of the road: on a map full of risk colours, a shield reads as "this is a
 * route" at a glance. Green marks the recommended one, matching the US
 * convention where green signs give guidance and blue ones give services.
 */
export function RouteShield({ label, recommended = false, size = 22 }: Props) {
  const letter = label.trim().slice(-1).toUpperCase();
  const fill = recommended ? COLORS.shieldGreen : COLORS.shieldBlue;

  return (
    <Box
      component="span"
      aria-label={label}
      sx={{ position: 'relative', display: 'inline-flex', width: size, height: size * 1.08 }}
    >
      <Box
        component="svg"
        viewBox="0 0 24 26"
        aria-hidden
        sx={{ width: '100%', height: '100%', display: 'block' }}
      >
        <path
          d="M12 1C8.6 1 5.6 2.1 2 2.7v8.1c0 7.3 4.6 11.6 10 14.2 5.4-2.6 10-6.9 10-14.2V2.7C18.4 2.1 15.4 1 12 1z"
          fill={fill}
          stroke={COLORS.text}
          strokeWidth={1.5}
        />
      </Box>
      <Box
        component="span"
        sx={{
          position: 'absolute',
          inset: 0,
          display: 'grid',
          placeItems: 'center',
          fontFamily: FONT_CONDENSED,
          fontWeight: 700,
          fontSize: size * 0.55,
          lineHeight: 1,
          color: COLORS.text,
          paddingTop: `${size * 0.04}px`,
        }}
      >
        {letter}
      </Box>
    </Box>
  );
}
