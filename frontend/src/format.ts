/**
 * Small display helpers.
 *
 * Times from the API are UTC. Everything shown to the driver is converted to
 * the browser's timezone, and every time carries that zone's short name
 * ("CST", "IST"). A long trip crosses time zones, and someone checking a
 * route from another country would otherwise misread every ETA.
 */

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
