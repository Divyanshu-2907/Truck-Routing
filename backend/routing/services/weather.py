"""Hourly forecasts for every checkpoint, from Open-Meteo.

A single trip can have 250 checkpoints across three routes, and asking for
them one at a time would be far too slow. Open-Meteo lets many coordinates
be requested in one call, so points are sent in chunks of 100, and the
chunks are fetched in parallel.

Two more things keep this fast and polite:

* coordinates are rounded to two decimal places (about 0.7 miles) before
  being looked up, so checkpoints that sit near each other - including on
  different routes - share one forecast and one cache entry;
* every forecast is cached for half an hour against its rounded position
  and the hour window it covers.

Units are requested in mph and inches, but the snowfall unit is checked on
every response and converted if Open-Meteo answers in centimetres.
"""

from __future__ import annotations

import logging
from bisect import bisect_left
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from .geo import Coordinate
from .http_client import Cache, ExternalServiceError, fetch_json, make_cache_key

logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

SERVICE_NAME = "The weather service"

#: How far ahead Open-Meteo's forecast reaches.
MAX_FORECAST_DAYS = 16

#: Coordinates are requested in chunks of this many.
CHUNK_SIZE = 100

#: How many chunks to fetch at the same time.
MAX_PARALLEL_REQUESTS = 4

#: Forecasts are refreshed every hour.
WEATHER_CACHE_SECONDS = 60 * 60

#: Lookups are snapped to a tenth of a degree, about 7 miles.
#:
#: The free tier counts every location in a request as a call, so the
#: number of distinct points is what has to come down. Snapping finer than
#: this buys nothing anyway: Open-Meteo's models run on a grid of roughly
#: 11 km, so two points inside one cell return the same forecast.
COORDINATE_PRECISION = 1

#: Both the plan and the heatmap ask for at least this many hours, so they
#: land on the same cache entries and the second of the two is mostly free.
SHARED_WINDOW_HOURS = 48

#: Multipliers that bring Open-Meteo's snowfall units to inches per hour.
SNOWFALL_TO_INCHES = {"inch": 1.0, "in": 1.0, "cm": 0.393_700_787, "mm": 0.039_370_079}


@dataclass(frozen=True)
class WeatherSample:
    """The forecast for one place at one hour."""

    time: datetime
    wind_mph: float
    rain_in: float
    snow_in: float


@dataclass(frozen=True)
class HourlyForecast:
    """Hour-by-hour forecast for one place over the trip's time window."""

    times: tuple[datetime, ...]
    wind_mph: tuple[float, ...]
    rain_in: tuple[float, ...]
    snow_in: tuple[float, ...]

    def nearest(self, when: datetime) -> WeatherSample:
        """The forecast hour closest to the given time."""
        index = self._nearest_index(when)
        return WeatherSample(
            time=self.times[index],
            wind_mph=self.wind_mph[index],
            rain_in=self.rain_in[index],
            snow_in=self.snow_in[index],
        )

    def _nearest_index(self, when: datetime) -> int:
        position = bisect_left(self.times, when)
        if position == 0:
            return 0
        if position >= len(self.times):
            return len(self.times) - 1

        before = self.times[position - 1]
        after = self.times[position]
        return position if (after - when) < (when - before) else position - 1


def forecast_window(
    departure: datetime, latest_needed: datetime, now: datetime
) -> tuple[datetime, datetime]:
    """The hours to ask for, the same for the plan and for the heatmap.

    Both always cover at least the slider's 48 hours, even when the drive
    is shorter, so the two requests produce identical cache keys and the
    heatmap costs nothing for any point the plan already looked up. Hours
    are free - the quota counts locations - so asking for more of them is
    the cheapest way to make that sharing work.

    A drive longer than 48 hours extends the window, and only then do the
    two stop lining up.
    """
    start = departure.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    # Both ends land on whole hours, so two callers reaching the same hour
    # by different arithmetic still produce the same cache key.
    needed = latest_needed.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    end = max(start + timedelta(hours=SHARED_WINDOW_HOURS), needed)
    return start, min(end, forecast_horizon(now))


def forecast_horizon(now: datetime) -> datetime:
    """The last hour Open-Meteo will return a forecast for.

    The limit is counted in whole days from midnight UTC, not from the
    current moment: asked on the 12th, it accepts hours up to 23:00 on the
    27th and rejects anything later. Measuring from "now" instead would let
    through departures that then fail at the weather service.
    """
    midnight = now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return midnight + timedelta(days=MAX_FORECAST_DAYS) - timedelta(hours=1)


def fetch_hourly(
    points: Sequence[Coordinate],
    start_utc: datetime,
    end_utc: datetime,
    *,
    cache: Cache | None = None,
) -> list[HourlyForecast]:
    """Forecasts for every point, in the same order the points were given.

    ``start_utc`` and ``end_utc`` bracket the trip; the forecast is fetched
    for whole hours covering that window.
    """
    if not points:
        return []

    window = _hour_window(start_utc, end_utc, forecast_horizon(datetime.now(UTC)))
    rounded = [_round_coordinate(point) for point in points]

    found: dict[Coordinate, HourlyForecast] = {}
    missing: list[Coordinate] = []
    for point in dict.fromkeys(rounded):  # unique, keeping the original order
        cached = cache.get(_cache_key(point, window)) if cache is not None else None
        if isinstance(cached, HourlyForecast):
            found[point] = cached
        else:
            missing.append(point)

    logger.info(
        "weather: %d points -> %d locations (%d cached, %d fetched) for %s to %s",
        len(points),
        len(found) + len(missing),
        len(found),
        len(missing),
        window[0].isoformat(timespec="hours"),
        window[1].isoformat(timespec="hours"),
    )

    if missing:
        _fetch_missing(missing, window, found, cache)

    return [found[point] for point in rounded]


def _fetch_missing(
    missing: list[Coordinate],
    window: tuple[datetime, datetime],
    found: dict[Coordinate, HourlyForecast],
    cache: Cache | None,
) -> None:
    """Fetch the points that were not cached, several chunks at a time."""
    chunks = [missing[index : index + CHUNK_SIZE] for index in range(0, len(missing), CHUNK_SIZE)]

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_REQUESTS) as pool:
        payloads = list(pool.map(lambda chunk: _request_chunk(chunk, window), chunks))

    for chunk, payload in zip(chunks, payloads, strict=False):
        forecasts = _parse_payload(payload, expected=len(chunk))
        for point, forecast in zip(chunk, forecasts, strict=False):
            found[point] = forecast
            if cache is not None:
                cache.set(_cache_key(point, window), forecast, WEATHER_CACHE_SECONDS)


def _request_chunk(chunk: list[Coordinate], window: tuple[datetime, datetime]) -> Any:
    """Ask Open-Meteo for one chunk of coordinates."""
    start, end = window
    return fetch_json(
        OPEN_METEO_URL,
        {
            "latitude": ",".join(f"{lat:.2f}" for _, lat in chunk),
            "longitude": ",".join(f"{lon:.2f}" for lon, _ in chunk),
            # Open-Meteo reports rain in two parts: "rain" from large weather
            # systems and "showers" from convective cells such as
            # thunderstorms. Both fall on the road, so both are rain here.
            "hourly": "wind_speed_10m,rain,showers,snowfall",
            "wind_speed_unit": "mph",
            "precipitation_unit": "inch",
            "timezone": "GMT",
            "start_hour": start.strftime("%Y-%m-%dT%H:%M"),
            "end_hour": end.strftime("%Y-%m-%dT%H:%M"),
        },
        service_name=SERVICE_NAME,
    )


def _parse_payload(payload: Any, *, expected: int) -> list[HourlyForecast]:
    """Turn one Open-Meteo response into a forecast per requested coordinate."""
    # One coordinate comes back as an object, several come back as a list.
    entries = payload if isinstance(payload, list) else [payload]
    if len(entries) != expected:
        raise ExternalServiceError(
            "The weather service returned forecasts for the wrong number of places."
        )
    return [_parse_entry(entry) for entry in entries]


def _parse_entry(entry: Any) -> HourlyForecast:
    """Read one location's hourly block, converting units where needed."""
    if not isinstance(entry, dict) or "hourly" not in entry:
        raise ExternalServiceError(
            "The weather service returned a forecast that could not be read."
        )

    hourly = entry["hourly"]
    units = entry.get("hourly_units", {})
    snow_factor = SNOWFALL_TO_INCHES.get(str(units.get("snowfall", "inch")).strip(), 1.0)

    raw_times = hourly.get("time", [])
    if not raw_times:
        raise ExternalServiceError(
            "The weather service has no forecast for that departure time. "
            "Try a departure within the next 16 days."
        )

    times = tuple(_parse_time(value) for value in raw_times)
    return HourlyForecast(
        times=times,
        wind_mph=_numbers(hourly.get("wind_speed_10m"), len(times)),
        rain_in=_sum(
            _numbers(hourly.get("rain"), len(times)),
            _numbers(hourly.get("showers"), len(times)),
        ),
        snow_in=_numbers(hourly.get("snowfall"), len(times), factor=snow_factor),
    )


def _numbers(values: Any, length: int, *, factor: float = 1.0) -> tuple[float, ...]:
    """Read a forecast series, treating gaps in the data as zero."""
    if not isinstance(values, list):
        return (0.0,) * length
    return tuple(
        float(value) * factor if isinstance(value, int | float) else 0.0 for value in values
    )


def _sum(first: tuple[float, ...], second: tuple[float, ...]) -> tuple[float, ...]:
    """Add two hourly series hour by hour."""
    return tuple(a + b for a, b in zip(first, second, strict=True))


def _parse_time(value: str) -> datetime:
    """Open-Meteo returns ``2026-11-12T15:00`` in GMT when asked for timezone=GMT."""
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def _hour_window(
    start_utc: datetime, end_utc: datetime, horizon: datetime
) -> tuple[datetime, datetime]:
    """Whole hours that cover the trip, with an hour of slack at each end.

    The slack after the trip is cut back to the forecast horizon, because
    the weather service rejects the whole request if any hour is past it.
    """
    start = start_utc.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    end = end_utc.astimezone(UTC).replace(minute=0, second=0, microsecond=0)
    if end < start:
        end = start
    padded_start = start - timedelta(hours=1)
    padded_end = min(end + timedelta(hours=1), max(horizon, start))
    return padded_start, padded_end


def _round_coordinate(point: Coordinate) -> Coordinate:
    lon, lat = point
    return (round(lon, COORDINATE_PRECISION), round(lat, COORDINATE_PRECISION))


def _cache_key(point: Coordinate, window: tuple[datetime, datetime]) -> str:
    start, end = window
    return make_cache_key("weather", point[0], point[1], start.isoformat(), end.isoformat())
