import Box from '@mui/material/Box';
import Tooltip from '@mui/material/Tooltip';

import { RISK_COLORS, RISK_LABELS, RISK_LEVELS, milesAt } from '../riskScale';
import { COLORS } from '../theme';
import type { ByLevel } from '../types';

interface Props {
  milesByLevel: ByLevel;
}

/**
 * A one-line stacked bar showing how the route's miles split across the risk
 * levels. It is the quickest way to compare two routes at a glance.
 */
export function RiskBar({ milesByLevel }: Props) {
  const total = RISK_LEVELS.reduce<number>(
    (sum, level) => sum + milesAt(milesByLevel, level),
    0,
  );
  if (total <= 0) {
    return null;
  }

  return (
    <Box
      sx={{
        display: 'flex',
        height: 8,
        overflow: 'hidden',
        bgcolor: COLORS.background,
        border: `1px solid ${COLORS.border}`,
      }}
    >
      {RISK_LEVELS.map((level) => {
        const miles = milesAt(milesByLevel, level);
        if (miles <= 0) {
          return null;
        }
        return (
          <Tooltip
            key={level}
            title={`${RISK_LABELS[level]}: ${Math.round(miles).toLocaleString()} mi`}
            arrow
          >
            <Box
              sx={{
                width: `${(miles / total) * 100}%`,
                bgcolor: RISK_COLORS[level],
              }}
            />
          </Tooltip>
        );
      })}
    </Box>
  );
}
