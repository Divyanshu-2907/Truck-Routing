import Autocomplete from '@mui/material/Autocomplete';
import CircularProgress from '@mui/material/CircularProgress';
import TextField from '@mui/material/TextField';
import { useEffect, useState } from 'react';

import { searchPlaces } from '../api/client';
import type { Place } from '../types';

/** Wait this long after the last keystroke before searching. */
const DEBOUNCE_MS = 400;

/** Nominatim is rate limited, so do not search for one or two letters. */
const MIN_QUERY_LENGTH = 3;

interface Props {
  label: string;
  value: Place | null;
  onChange: (place: Place | null) => void;
  error?: string | undefined;
}

/**
 * A place search box.
 *
 * Typing is debounced and the previous request is aborted, so a driver
 * typing "Dallas, TX" causes one search rather than ten.
 */
export function PlaceAutocomplete({ label, value, onChange, error }: Props) {
  const [query, setQuery] = useState('');
  const [options, setOptions] = useState<Place[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const text = query.trim();
    // Nothing to do while the box is short, or when it just shows the
    // place the driver already picked. Any request already in flight is
    // aborted by the cleanup below, which clears the spinner on its own.
    if (text.length < MIN_QUERY_LENGTH || text === value?.label) {
      return;
    }

    const controller = new AbortController();
    const timer = window.setTimeout(() => {
      setLoading(true);
      searchPlaces(text, controller.signal)
        .then((places) => setOptions(places))
        .catch(() => setOptions([]))
        .finally(() => setLoading(false));
    }, DEBOUNCE_MS);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [query, value]);

  return (
    <Autocomplete
      value={value}
      options={options}
      loading={loading}
      onChange={(_event, place) => onChange(place)}
      onInputChange={(_event, text) => setQuery(text)}
      getOptionLabel={(place) => place.label}
      isOptionEqualToValue={(option, selected) =>
        option.lat === selected.lat && option.lon === selected.lon
      }
      // The backend has already ranked the matches; do not re-filter them.
      filterOptions={(places) => places}
      noOptionsText={
        query.trim().length < MIN_QUERY_LENGTH
          ? `Type at least ${MIN_QUERY_LENGTH} characters`
          : 'No matching place'
      }
      autoComplete
      size="small"
      renderInput={(params) => (
        <TextField
          {...params}
          label={label}
          error={Boolean(error)}
          helperText={error}
          slotProps={{
            ...params.slotProps,
            input: {
              ...params.slotProps.input,
              endAdornment: (
                <>
                  {loading ? <CircularProgress size={16} /> : null}
                  {params.slotProps.input.endAdornment}
                </>
              ),
            },
          }}
        />
      )}
    />
  );
}
