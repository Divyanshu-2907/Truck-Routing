import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';
import { useState } from 'react';

import { formatCheckpointTime } from '../format';
import { RISK_COLORS, RISK_OUTLINE, RISK_TINTS } from '../riskScale';
import { COLORS, LABEL_SX, MONO_SX, TRANSITION } from '../theme';
import type { Checkpoint, PlannedRoute } from '../types';

/** How many rows to show before the "show all" button. */
const COLLAPSED_COUNT = 8;

interface Props {
  route: PlannedRoute;
  onFocusCheckpoint: (checkpoint: Checkpoint) => void;
}

/**
 * Every checkpoint on the selected route, with the weather behind its level.
 *
 * A 10 mile interval on a long trip produces hundreds of rows, so only the
 * first few are rendered until the driver asks for the rest. That keeps the
 * panel light without hiding anything.
 */
export function CheckpointList({ route, onFocusCheckpoint }: Props) {
  const [expanded, setExpanded] = useState(false);
  const checkpoints = route.checkpoints;
  const shown = expanded ? checkpoints : checkpoints.slice(0, COLLAPSED_COUNT);
  const hidden = checkpoints.length - shown.length;

  return (
    <Box>
      <Typography sx={{ ...LABEL_SX, fontSize: 11, display: 'block', mb: 1 }}>
        Checkpoints
      </Typography>

      <Stack spacing={0.5}>
        {shown.map((checkpoint) => (
          <Row
            key={checkpoint.mile}
            checkpoint={checkpoint}
            onClick={() => onFocusCheckpoint(checkpoint)}
          />
        ))}
      </Stack>

      {hidden > 0 ? (
        <Button size="small" onClick={() => setExpanded(true)} sx={{ mt: 1 }}>
          Show all {checkpoints.length} checkpoints
        </Button>
      ) : null}
      {expanded && checkpoints.length > COLLAPSED_COUNT ? (
        <Button size="small" onClick={() => setExpanded(false)} sx={{ mt: 1 }}>
          Show fewer
        </Button>
      ) : null}
    </Box>
  );
}

function Row({ checkpoint, onClick }: { checkpoint: Checkpoint; onClick: () => void }) {
  return (
    <Box
      role="button"
      onClick={onClick}
      sx={{
        p: 1,
        border: `1px solid ${COLORS.border}`,
        cursor: 'pointer',
        transition: TRANSITION,
        '&:hover': { borderColor: COLORS.muted, backgroundColor: COLORS.raised },
      }}
    >
      <Stack
        direction="row"
        spacing={1}
        sx={{ alignItems: 'center', justifyContent: 'space-between' }}
      >
        <Stack direction="row" spacing={1} sx={{ alignItems: 'baseline', minWidth: 0 }}>
          <Typography sx={{ ...MONO_SX, fontSize: 12.5 }}>
            MM {Math.round(checkpoint.mile).toLocaleString()}
          </Typography>
          <Typography
            sx={{ ...LABEL_SX, fontSize: 10, color: COLORS.text, whiteSpace: 'nowrap' }}
          >
            {checkpoint.condition}
          </Typography>
        </Stack>
        <Chip
          size="small"
          label={checkpoint.level_label.toUpperCase()}
          sx={{
            height: 18,
            fontSize: 10,
            backgroundColor: RISK_TINTS[checkpoint.level],
            color: RISK_COLORS[checkpoint.level],
            border: `1px solid ${RISK_COLORS[checkpoint.level]}`,
            outline: `1px solid ${RISK_OUTLINE}`,
          }}
        />
      </Stack>

      <Typography sx={{ ...MONO_SX, fontSize: 10, color: COLORS.textSecondary, display: 'block' }}>
        {formatCheckpointTime(checkpoint.eta, checkpoint.lat, checkpoint.lon)}
      </Typography>
      <Typography sx={{ ...MONO_SX, fontSize: 10, color: COLORS.textSecondary }}>
        {checkpoint.wind_mph.toFixed(0).padStart(2, '0')} MPH · {checkpoint.rain_in.toFixed(2)} IN/HR
        RAIN · {checkpoint.snow_in.toFixed(2)} IN/HR SNOW
      </Typography>
    </Box>
  );
}
