/**
 * Small display helpers.
 *
 * Times from the API are UTC. Every time shown carries a zone name, because
 * a trucking app that prints a bare clock time is asking to be misread.
 *
 * There are two kinds of time here, and they use different zones on purpose:
 *
 * - Anything about a place on the route - an arrival at a checkpoint, or
 *   the hour the forecast slider is showing - is read in local time there.
 *   That is the clock the driver will actually see, and on a Dallas to
 *   Denver run it changes partway along the route.
 * - What the driver typed or did here - the departure time, the moment the
 *   forecast was fetched - stays in the browser's own timezone, because
 *   that is the clock they are reading it on.
 */

import tzLookup from 'tz-lookup';

const TIME_FORMAT = new Intl.DateTimeFormat(undefined, {
  weekday: 'short',
  hour: 'numeric',
  minute: '2-digit',
  timeZoneName: 'short',
});

const DATE_TIME_FORMAT = new Intl.DateTimeFormat(undefined, {
  weekday: 'short',
  day: 'numeric',
  month: 'short',
  hour: 'numeric',
  minute: '2-digit',
  timeZoneName: 'short',
});

/** The browser's timezone, e.g. "America/Chicago", for labelling inputs. */
export const BROWSER_TIME_ZONE = Intl.DateTimeFormat().resolvedOptions().timeZone;

/**
 * Formatters are cached per timezone. A long trip has hundreds of
 * checkpoints across two or three zones, and building an
 * Intl.DateTimeFormat is far more expensive than using one.
 */
const ZONE_FORMATTERS = new Map<string, Intl.DateTimeFormat>();

function zoneFormatter(timeZone: string): Intl.DateTimeFormat {
  const cached = ZONE_FORMATTERS.get(timeZone);
  if (cached) {
    return cached;
  }
  const formatter = new Intl.DateTimeFormat(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
    hour: 'numeric',
    minute: '2-digit',
    timeZoneName: 'short',
    timeZone,
  });
  ZONE_FORMATTERS.set(timeZone, formatter);
  return formatter;
}

/**
 * An arrival time in the local time of the place it happens, e.g.
 * "Fri 13 Nov, 9:40 PM CST".
 *
 * The timezone is looked up from the coordinates. If that fails - an
 * unmapped point at sea, say - the browser's own zone is used, so a
 * checkpoint always shows a time rather than nothing.
 */
export function formatCheckpointTime(iso: string, lat: number, lon: number): string {
  let timeZone = BROWSER_TIME_ZONE;
  try {
    timeZone = tzLookup(lat, lon);
  } catch {
    // Keep the browser's zone.
  }
  return zoneFormatter(timeZone).format(new Date(iso));
}

/** "Fri 2:19 PM CST" in the browser's timezone. */
export function formatLocalTime(iso: string): string {
  return TIME_FORMAT.format(new Date(iso));
}

/** "Fri 13 Nov, 2:19 PM CST" in the browser's timezone. */
export function formatLocalDateTime(iso: string): string {
  return DATE_TIME_FORMAT.format(new Date(iso));
}

/** "795 mi", with a thousands separator. */
export function formatMiles(miles: number): string {
  return `${Math.round(miles).toLocaleString()} mi`;
}

/** The value a datetime-local input needs: "2026-11-13T08:00". */
export function toDateTimeLocalValue(date: Date): string {
  const pad = (value: number): string => String(value).padStart(2, '0');
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

/** The next full hour, used as the default departure time. */
export function nextFullHour(from: Date = new Date()): Date {
  const next = new Date(from);
  next.setMinutes(0, 0, 0);
  next.setHours(next.getHours() + 1);
  return next;
}
