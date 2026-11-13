import Box from '@mui/material/Box';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useEffect, useState } from 'react';

import { getHealth } from '../api/client';
import { RISK_COLORS } from '../riskScale';
import { COLORS, LABEL_SX } from '../theme';

type Status = 'checking' | 'online' | 'offline';

const LABELS: Record<Status, string> = {
  checking: 'Checking',
  online: 'API Online',
  offline: 'API Offline',
};

const LIGHTS: Record<Status, string> = {
  checking: COLORS.textSecondary,
  // The same green and red the risk scale uses for Low and Severe.
  online: RISK_COLORS[0],
  offline: RISK_COLORS[3],
};

/**
 * Whether the backend is reachable, as a square status light and a word.
 *
 * "API offline" tells someone running this locally that the Django server
 * is not up, which is the usual reason nothing happens on Plan route.
 */
export function ApiStatusChip() {
  const [status, setStatus] = useState<Status>('checking');

  useEffect(() => {
    let cancelled = false;

    getHealth()
      .then((health) => {
        if (!cancelled) {
          setStatus(health.status === 'ok' ? 'online' : 'offline');
        }
      })
      .catch(() => {
        if (!cancelled) {
          setStatus('offline');
        }
      });

    // StrictMode mounts effects twice in development; ignore the stale result.
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <Stack
      direction="row"
      spacing={0.625}
      sx={{
        alignItems: 'center',
        border: `1px solid ${COLORS.border}`,
        backgroundColor: COLORS.raised,
        px: 0.75,
        py: 0.375,
        flexShrink: 0,
      }}
    >
      <Box
        aria-hidden
        sx={{ width: 7, height: 7, backgroundColor: LIGHTS[status], flexShrink: 0 }}
      />
      <Typography sx={{ ...LABEL_SX, fontSize: 10, color: COLORS.text, whiteSpace: 'nowrap' }}>
        {LABELS[status]}
      </Typography>
    </Stack>
  );
}
