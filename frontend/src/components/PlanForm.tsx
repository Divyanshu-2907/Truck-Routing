import SearchIcon from '@mui/icons-material/Search';
import SwapVertIcon from '@mui/icons-material/SwapVert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import FormHelperText from '@mui/material/FormHelperText';
import IconButton from '@mui/material/IconButton';
import InputAdornment from '@mui/material/InputAdornment';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Tooltip from '@mui/material/Tooltip';
import Typography from '@mui/material/Typography';
import { useEffect, useRef, useState, type FormEvent } from 'react';

import { BROWSER_TIME_ZONE, nextFullHour, toDateTimeLocalValue } from '../format';
import { COLORS, LABEL_SX } from '../theme';
import type { PlanRequest, Place } from '../types';
import { PlaceAutocomplete } from './PlaceAutocomplete';

const MAX_LOAD_LB = 80_000;

/** Matches the server: a departure up to an hour ago is still accepted. */
const PAST_DEPARTURE_GRACE_MS = 60 * 60 * 1000;
const SAMPLING_INTERVALS = [10, 25, 50];

interface Props {
  onSubmit: (plan: PlanRequest) => void;
  loading: boolean;
  /** Values to start from: a shared link, or an example trip. */
  initial?: PlanRequest | null;
  /** Plan straight away with those values, without waiting for a click. */
  autoSubmit?: boolean;
}

interface Errors {
  origin?: string;
  destination?: string;
  departure?: string;
  load?: string;
}

/** The trip form: where, when, how heavy, and how finely to sample the weather. */
export function PlanForm({ onSubmit, loading, initial = null, autoSubmit = false }: Props) {
  const [origin, setOrigin] = useState<Place | null>(initial?.origin ?? null);
  const [destination, setDestination] = useState<Place | null>(initial?.destination ?? null);
  const [departure, setDeparture] = useState(() =>
    toDateTimeLocalValue(initial ? new Date(initial.departure) : nextFullHour()),
  );
  const [load, setLoad] = useState(initial ? String(initial.load_lb) : '40000');
  const [interval, setInterval] = useState(initial?.interval_miles ?? 25);
  const [errors, setErrors] = useState<Errors>({});

  // A shared link or an example chip plans immediately. The ref makes sure
  // that happens once, not again on every render.
  const submitted = useRef(false);
  useEffect(() => {
    if (autoSubmit && initial && !submitted.current) {
      submitted.current = true;
      onSubmit(initial);
    }
  }, [autoSubmit, initial, onSubmit]);

  function handleSwap(): void {
    setOrigin(destination);
    setDestination(origin);
  }

  function handleSubmit(event: FormEvent): void {
    event.preventDefault();

    const found = validate({ origin, destination, departure, load });
    setErrors(found);
    if (Object.keys(found).length > 0 || !origin || !destination) {
      return;
    }

    onSubmit({
      origin,
      destination,
      // datetime-local has no timezone, so read it as local time and send
      // it as UTC. Without this every ETA would be out by the driver's offset.
      departure: new Date(departure).toISOString(),
      load_lb: Number(load),
      interval_miles: interval,
    });
  }

  return (
    <Stack component="form" spacing={1.5} onSubmit={handleSubmit} noValidate>
      <Box sx={{ position: 'relative' }}>
        <Stack spacing={1.25}>
          <PlaceAutocomplete
            label="Origin"
            value={origin}
            onChange={setOrigin}
            error={errors.origin}
          />
          <PlaceAutocomplete
            label="Destination"
            value={destination}
            onChange={setDestination}
            error={errors.destination}
          />
        </Stack>

        {/* Sits between the two boxes, where the swap it performs happens. */}
        <Tooltip title="Swap origin and destination" arrow>
          <span>
            <IconButton
              size="small"
              onClick={handleSwap}
              disabled={!origin && !destination}
              aria-label="Swap origin and destination"
              sx={{
                position: 'absolute',
                right: 8,
                // The first field is 40px tall and the gap below it is 10px,
                // so its centre is 45px down whatever happens underneath.
                top: 45,
                transform: 'translateY(-50%)',
                zIndex: 2,
                border: `1px solid ${COLORS.border}`,
                borderRadius: 1,
                backgroundColor: COLORS.raised,
                '&:hover': { backgroundColor: COLORS.raised, borderColor: COLORS.accent },
              }}
            >
              <SwapVertIcon fontSize="small" />
            </IconButton>
          </span>
        </Tooltip>
      </Box>

      <TextField
        label="Departure"
        type="datetime-local"
        size="small"
        value={departure}
        onChange={(event) => setDeparture(event.target.value)}
        error={Boolean(errors.departure)}
        helperText={errors.departure ?? `Your time · ${BROWSER_TIME_ZONE}`}
        slotProps={{ inputLabel: { shrink: true } }}
      />

      <TextField
        label="Load weight"
        type="number"
        size="small"
        value={load}
        onChange={(event) => setLoad(event.target.value)}
        error={Boolean(errors.load)}
        helperText={errors.load ?? 'Gross weight. Heavy loads raise wind risk.'}
        slotProps={{
          input: { endAdornment: <InputAdornment position="end">lb</InputAdornment> },
          htmlInput: { min: 1, max: MAX_LOAD_LB, step: 1000 },
        }}
      />

      <Stack spacing={0.5}>
        <Typography sx={{ ...LABEL_SX, fontSize: 11 }}>Checkpoint spacing</Typography>
        <ToggleButtonGroup
          exclusive
          fullWidth
          size="small"
          value={interval}
          onChange={(_event, next: number | null) => {
            if (next !== null) {
              setInterval(next);
            }
          }}
        >
          {SAMPLING_INTERVALS.map((miles) => (
            <ToggleButton key={miles} value={miles}>
              {miles} mi
            </ToggleButton>
          ))}
        </ToggleButtonGroup>
        <FormHelperText sx={{ mt: 0.25 }}>Shorter spacing, more detail.</FormHelperText>
      </Stack>

      <Button
        type="submit"
        variant="contained"
        size="large"
        loading={loading}
        loadingPosition="start"
        startIcon={<SearchIcon />}
        sx={{ py: 1 }}
      >
        Plan route
      </Button>
    </Stack>
  );
}

function validate(input: {
  origin: Place | null;
  destination: Place | null;
  departure: string;
  load: string;
}): Errors {
  const errors: Errors = {};

  if (!input.origin) {
    errors.origin = 'Choose where the trip starts.';
  }
  if (!input.destination) {
    errors.destination = 'Choose where the trip ends.';
  }
  const departure = new Date(input.departure).getTime();
  if (!input.departure || Number.isNaN(departure)) {
    errors.departure = 'Choose a departure date and time.';
  } else if (departure < Date.now() - PAST_DEPARTURE_GRACE_MS) {
    errors.departure = 'That time has already passed. Choose a time from now onwards.';
  }

  const pounds = Number(input.load);
  if (!input.load || Number.isNaN(pounds) || pounds < 1 || pounds > MAX_LOAD_LB) {
    errors.load = `Enter a load between 1 and ${MAX_LOAD_LB.toLocaleString()} lb.`;
  }

  return errors;
}
