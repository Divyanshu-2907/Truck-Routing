/**
 * Example trips offered on the empty state.
 *
 * Their coordinates are built in, so clicking one plans straight away
 * without waiting on a place search.
 */

import type { Place } from './types';

export interface ExampleTrip {
  label: string;
  origin: Place;
  destination: Place;
}

export const EXAMPLE_TRIPS: ExampleTrip[] = [
  {
    label: 'Denver → Chicago',
    origin: { label: 'Denver, CO', lat: 39.7392, lon: -104.9903 },
    destination: { label: 'Chicago, IL', lat: 41.8781, lon: -87.6298 },
  },
  {
    label: 'Seattle → Salt Lake City',
    origin: { label: 'Seattle, WA', lat: 47.6062, lon: -122.3321 },
    destination: { label: 'Salt Lake City, UT', lat: 40.7608, lon: -111.891 },
  },
  {
    label: 'Dallas → Denver',
    origin: { label: 'Dallas, TX', lat: 32.7767, lon: -96.797 },
    destination: { label: 'Denver, CO', lat: 39.7392, lon: -104.9903 },
  },
];
