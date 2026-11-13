import Chip from '@mui/material/Chip';
import Stack from '@mui/material/Stack';
import Typography from '@mui/material/Typography';

import { EXAMPLE_TRIPS, type ExampleTrip } from '../exampleTrips';
import { LABEL_SX } from '../theme';

interface Props {
  onPick: (trip: ExampleTrip) => void;
}

/** Example trips offered below the form before the first plan. */
export function EmptyState({ onPick }: Props) {
  return (
    <Stack spacing={1}>
      <Typography sx={{ ...LABEL_SX, fontSize: 10 }}>Or try an example trip</Typography>

      <Stack direction="row" spacing={1} sx={{ flexWrap: 'wrap', gap: 1 }}>
        {EXAMPLE_TRIPS.map((trip) => (
          <Chip
            key={trip.label}
            label={trip.label}
            variant="outlined"
            color="primary"
            onClick={() => onPick(trip)}
          />
        ))}
      </Stack>
    </Stack>
  );
}
