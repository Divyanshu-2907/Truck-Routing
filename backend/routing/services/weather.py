"""Hourly forecasts for every checkpoint, from one of two services.

**Open-Meteo** is the first choice. It takes many coordinates in a single
call, so a whole trip costs a handful of requests.

**MET Norway** is the fallback, used only when Open-Meteo refuses. On free
hosting the outbound IP is shared with every other app on the box, and
Open-Meteo counts its free quota per IP: the quota can already be spent by
strangers before this app makes its first call of the day. One service
being rate limited should not stop a driver planning a trip, so the same
request is made again against MET Norway.

The two differ in shape. Open-Meteo answers for many places at once and
reports rain and snow separately. MET Norway answers for one place per
request and reports a single precipitation figure, so snow has to be
inferred from the temperature. Both are normalised to the same hourly
series - wind in mph, rain and snow in inches per hour - so nothing
downstream knows or cares which one answered.

Whichever service is used, lookups are snapped to a shared grid and cached,
so points that sit near each other cost one lookup between them.
"""

from __future__ import annotations

import logging
import os
import time
from bisect import bisect_left
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from typing import Any, Literal

from .geo import Coordinate
from .http_client import (
    Cache,
    ExternalServiceError,
    RateLimitedError,
    ServiceUnreachableError,
    fetch_json,
    fetch_json_result,
    make_cache_key,
)

logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"

MET_NORWAY_URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact"

SERVICE_NAME = "The weather service"

MET_SERVICE_NAME = "The backup weather service"

#: Which service a set of forecasts came from.
ProviderName = Literal["open-meteo", "met-norway"]

#: MET Norway requires a descriptive User-Agent naming the application and
#: a way to reach whoever runs it. Point this at the project's repository.
MET_NORWAY_USER_AGENT = os.environ.get(
    "MET_NORWAY_USER_AGENT",
    "WeatherAwareTruckRouting/1.0 (+https://github.com/Divyanshu-2907/Truck-Routing)",
)

#: MET Norway answers one location per request, so they go out in parallel.
#: Their guidance is to stay well under 20 requests a second; eight at a
#: time with a round trip each keeps us an order of magnitude below that.
MET_PARALLEL_REQUESTS = 8

#: How long a MET Norway entry is kept so a conditional request can reuse
#: it. The forecast inside may be stale; the Expires header decides when it
#: has to be revalidated, and a 304 then refreshes it without a download.
MET_CACHE_SECONDS = 6 * 60 * 60

#: Used when MET Norway does not send a usable Expires header.
MET_DEFAULT_FRESH_SECONDS = 30 * 60

#: Stands in for a missing temperature reading: warm enough that the
#: precipitation is treated as rain rather than invented snow.
ABOVE_FREEZING_C = 99.0

#: Precipitation falls as snow at or below this air temperature.
#:
#: An approximation. Real snow depends on the whole temperature profile
#: between cloud and ground, not just the air at two metres, so wet snow
#: near freezing will be called snow here and sleet may be miscalled either
#: way. It is the best that can be done from a single temperature.
SNOW_TEMPERATURE_C = 0.0

#: Inches of snow per inch of melted water.
#:
#: Also an approximation. The real ratio runs from about 5:1 for heavy wet
#: snow to 20:1 for dry powder; 10:1 is the convention when nothing better
#: is known. Open-Meteo reports snowfall directly and needs none of this.
SNOW_TO_LIQUID_RATIO = 10.0

#: Millimetres to inches, for MET Norway's precipitation.
MM_PER_INCH = 25.4

#: Metres per second to miles per hour, for MET Norway's wind.
MPH_PER_METRE_PER_SECOND = 2.236936

#: Set ``WEATHER_FORCE_FALLBACK=1`` to skip Open-Meteo and use MET Norway
#: for everything. Off by default; it exists so the fallback can be seen
#: working locally without waiting for a real quota refusal.
FORCE_FALLBACK_VARIABLE = "WEATHER_FORCE_FALLBACK"

#: How long to stop trying Open-Meteo after it has refused.
#:
#: Without this every request would spend a failed round trip rediscovering
#: the same rate limit before falling back.
PROVIDER_COOLDOWN_SECONDS = 15 * 60

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


@dataclass(frozen=True)
class WeatherBatch:
    """Forecasts for the points asked for, and which service supplied them."""

    forecasts: list[HourlyForecast]
    source: ProviderName


def fetch_hourly(
    points: Sequence[Coordinate],
    start_utc: datetime,
    end_utc: datetime,
    *,
    cache: Cache | None = None,
) -> WeatherBatch:
    """Forecasts for every point, in the same order the points were given.

    ``start_utc`` and ``end_utc`` bracket the trip. Points are snapped to a
    shared grid first, so near neighbours cost one lookup between them, and
    the result is expanded back out to one forecast per point given.
    """
    if not points:
        return WeatherBatch(forecasts=[], source="open-meteo")

    window = _hour_window(start_utc, end_utc, forecast_horizon(datetime.now(UTC)))
    rounded = [_round_coordinate(point) for point in points]
    cells = list(dict.fromkeys(rounded))  # unique, keeping the original order

    found, source = _fetch_cells(cells, window, cache)
    return WeatherBatch(forecasts=[found[point] for point in rounded], source=source)


def _fetch_cells(
    cells: list[Coordinate],
    window: tuple[datetime, datetime],
    cache: Cache | None,
) -> tuple[dict[Coordinate, HourlyForecast], ProviderName]:
    """Ask Open-Meteo, and fall back to MET Norway only if it refuses."""
    if _force_fallback():
        logger.info("%s is set: using MET Norway for everything", FORCE_FALLBACK_VARIABLE)
        return _met_norway_cells(cells, window, cache), "met-norway"

    if not _recently_refused(cache):
        try:
            return _open_meteo_cells(cells, window, cache), "open-meteo"
        except (RateLimitedError, ServiceUnreachableError) as refusal:
            # The quota on free hosting is shared with every other app on
            # the same outbound address, so a refusal says nothing about
            # our own usage and is worth answering with the other service.
            logger.warning("falling back to MET Norway: %s", refusal)
            _remember_refusal(cache)

    return _met_norway_cells(cells, window, cache), "met-norway"


def _force_fallback() -> bool:
    """Whether the environment says to use the fallback for everything."""
    raw = os.environ.get(FORCE_FALLBACK_VARIABLE, "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _refusal_key() -> str:
    return make_cache_key("weather-provider", "open-meteo-refused")


def _recently_refused(cache: Cache | None) -> bool:
    return cache is not None and cache.get(_refusal_key()) is not None


def _remember_refusal(cache: Cache | None) -> None:
    if cache is not None:
        cache.set(_refusal_key(), True, PROVIDER_COOLDOWN_SECONDS)


# ---------------------------------------------------------------------------
# Open-Meteo: many locations per request.
# ---------------------------------------------------------------------------


def _open_meteo_cells(
    cells: list[Coordinate],
    window: tuple[datetime, datetime],
    cache: Cache | None,
) -> dict[Coordinate, HourlyForecast]:
    """Forecasts for every cell, in chunks, several chunks at a time."""
    found: dict[Coordinate, HourlyForecast] = {}
    missing: list[Coordinate] = []
    for cell in cells:
        cached = cache.get(_cache_key(cell, window)) if cache is not None else None
        if isinstance(cached, HourlyForecast):
            found[cell] = cached
        else:
            missing.append(cell)

    logger.info(
        "weather open-meteo: %d locations (%d cached, %d to fetch) for %s to %s",
        len(cells),
        len(found),
        len(missing),
        window[0].isoformat(timespec="hours"),
        window[1].isoformat(timespec="hours"),
    )
    if not missing:
        return found

    chunks = [missing[index : index + CHUNK_SIZE] for index in range(0, len(missing), CHUNK_SIZE)]
    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_REQUESTS) as pool:
        payloads = list(pool.map(lambda chunk: _request_chunk(chunk, window), chunks))

    for chunk, payload in zip(chunks, payloads, strict=False):
        forecasts = _parse_payload(payload, expected=len(chunk))
        for cell, forecast in zip(chunk, forecasts, strict=False):
            found[cell] = forecast
            if cache is not None:
                cache.set(_cache_key(cell, window), forecast, WEATHER_CACHE_SECONDS)

    return found


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


# ---------------------------------------------------------------------------
# MET Norway: one location per request, with conditional revalidation.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _MetEntry:
    """A MET Norway forecast, kept with what is needed to revalidate it."""

    forecast: HourlyForecast
    last_modified: str
    #: ``time.time()`` after which the copy has to be checked again.
    fresh_until: float


def _met_norway_cells(
    cells: list[Coordinate],
    _window: tuple[datetime, datetime],
    cache: Cache | None,
) -> dict[Coordinate, HourlyForecast]:
    """Forecasts for every cell, one request each, eight at a time.

    The window is accepted to match the other provider but goes unused:
    MET Norway returns its whole forecast for a place whatever hours are
    asked for, so entries are cached per cell and serve any window - which
    makes the heatmap free wherever the plan has already been.
    """
    fresh: dict[Coordinate, HourlyForecast] = {}
    stale: dict[Coordinate, _MetEntry] = {}
    to_fetch: list[Coordinate] = []
    now = time.time()

    for cell in cells:
        entry = cache.get(_met_cache_key(cell)) if cache is not None else None
        if isinstance(entry, _MetEntry) and now < entry.fresh_until:
            fresh[cell] = entry.forecast
            continue
        if isinstance(entry, _MetEntry):
            stale[cell] = entry
        to_fetch.append(cell)

    logger.info(
        "weather met-norway: %d locations (%d fresh, %d to revalidate, %d new)",
        len(cells),
        len(fresh),
        len(stale),
        len(to_fetch) - len(stale),
    )
    if not to_fetch:
        return fresh

    with ThreadPoolExecutor(max_workers=MET_PARALLEL_REQUESTS) as pool:
        entries = list(pool.map(lambda cell: _met_cell(cell, stale.get(cell)), to_fetch))

    for cell, entry in zip(to_fetch, entries, strict=True):
        fresh[cell] = entry.forecast
        if cache is not None:
            cache.set(_met_cache_key(cell), entry, MET_CACHE_SECONDS)

    return fresh


def _met_cell(cell: Coordinate, previous: _MetEntry | None) -> _MetEntry:
    """One location from MET Norway, asking only for what has changed."""
    lon, lat = cell
    headers = {"User-Agent": MET_NORWAY_USER_AGENT}
    if previous is not None:
        # Their terms ask for conditional requests; a 304 costs them almost
        # nothing to answer and costs us no download.
        headers["If-Modified-Since"] = previous.last_modified

    result = fetch_json_result(
        MET_NORWAY_URL,
        # Their terms ask for no more than four decimal places.
        {"lat": f"{lat:.4f}", "lon": f"{lon:.4f}"},
        service_name=MET_SERVICE_NAME,
        headers=headers,
    )

    if result.not_modified and previous is not None:
        return _MetEntry(
            forecast=previous.forecast,
            last_modified=previous.last_modified,
            fresh_until=_met_fresh_until(result.headers),
        )

    return _MetEntry(
        forecast=_parse_met_payload(result.payload),
        last_modified=str(result.headers.get("Last-Modified", "")),
        fresh_until=_met_fresh_until(result.headers),
    )


def _met_fresh_until(headers: Any) -> float:
    """When MET Norway says the forecast it just gave us will be restated."""
    raw = (headers or {}).get("Expires")
    if raw:
        try:
            expires = parsedate_to_datetime(str(raw))
        except (TypeError, ValueError):
            expires = None
        if expires is not None:
            # An Expires already in the past means revalidate now, so the
            # result is allowed to be a time that has already passed.
            seconds = (expires - datetime.now(UTC)).total_seconds()
            return time.time() + min(seconds, WEATHER_CACHE_SECONDS)
    # Only when they send no usable Expires at all do we pick our own.
    return time.time() + MET_DEFAULT_FRESH_SECONDS


def _parse_met_payload(payload: Any) -> HourlyForecast:
    """Turn one MET Norway forecast into the same series Open-Meteo gives.

    Their series is hourly for roughly the first two to three days, which
    covers the 48 hour window, and coarser after that. A coarser step is
    spread evenly over the hours it stands for, and the nearest-hour lookup
    then reads it like any other entry.
    """
    series = ((payload or {}).get("properties") or {}).get("timeseries")
    if not isinstance(series, list) or not series:
        raise ExternalServiceError(
            "The backup weather service returned a forecast that could not be read."
        )

    times: list[datetime] = []
    winds: list[float] = []
    rains: list[float] = []
    snows: list[float] = []

    for entry in series:
        if not isinstance(entry, dict):
            continue
        moment = _parse_met_time(entry.get("time"))
        if moment is None:
            continue

        data = entry.get("data") or {}
        instant = (data.get("instant") or {}).get("details") or {}
        millimetres, hours = _met_precipitation(data)
        liquid_in_per_hour = millimetres / MM_PER_INCH / hours
        temperature = _as_float(instant.get("air_temperature"), default=ABOVE_FREEZING_C)
        freezing = temperature <= SNOW_TEMPERATURE_C

        times.append(moment)
        winds.append(_as_float(instant.get("wind_speed")) * MPH_PER_METRE_PER_SECOND)
        rains.append(0.0 if freezing else liquid_in_per_hour)
        snows.append(liquid_in_per_hour * SNOW_TO_LIQUID_RATIO if freezing else 0.0)

    if not times:
        raise ExternalServiceError(
            "The backup weather service returned a forecast with no hours in it."
        )

    return HourlyForecast(
        times=tuple(times),
        wind_mph=tuple(winds),
        rain_in=tuple(rains),
        snow_in=tuple(snows),
    )


def _met_precipitation(data: dict[str, Any]) -> tuple[float, float]:
    """Millimetres of precipitation, and the hours they are spread over."""
    for key, hours in (("next_1_hours", 1.0), ("next_6_hours", 6.0), ("next_12_hours", 12.0)):
        block = data.get(key)
        if isinstance(block, dict):
            details = block.get("details") or {}
            if "precipitation_amount" in details:
                return _as_float(details.get("precipitation_amount")), hours
    return 0.0, 1.0


def _parse_met_time(value: Any) -> datetime | None:
    """MET Norway stamps every entry in UTC, e.g. ``2026-11-13T07:00:00Z``."""
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except ValueError:
        return None


def _as_float(value: Any, *, default: float = 0.0) -> float:
    return float(value) if isinstance(value, int | float) else default


def _met_cache_key(cell: Coordinate) -> str:
    # No window in the key: MET Norway returns its whole forecast every
    # time, so one entry per cell serves the plan and the heatmap alike.
    return make_cache_key("met-norway", cell[0], cell[1])


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
