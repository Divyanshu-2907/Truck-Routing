"""The weather heatmap for the whole trip corridor, hour by hour.

The map's heatmap answers a different question from the checkpoints. A
checkpoint says "this is the weather when the truck gets here". The heatmap
says "this is the weather across the whole corridor at 3pm", so the driver
can scrub through 48 hours and see a storm move across the route.

To do that we need weather away from the road as well as on it, so the grid
is built from three lines: the routes themselves, and two more about 30
miles out to either side. Points are sampled every 25 miles, rounded so that
neighbouring routes share points, and capped so a coast-to-coast trip cannot
turn into thousands of requests.

The result is deliberately compact - risk levels as small integers in an
array per hour - because the frontend holds all 49 hours in memory at once
so the slider never has to ask the server for anything.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .geo import (
    DISTANCE_EPSILON_MILES,
    Coordinate,
    cumulative_miles,
    initial_bearing,
    interpolate_point,
    point_at_bearing,
)
from .http_client import Cache
from .risk import assess
from .weather import fetch_hourly, forecast_window

#: How far apart corridor samples are along each route.
CORRIDOR_SPACING_MILES = 50.0

#: How far out to either side of the road the corridor reaches. Wider than
#: the spacing, so the band still has shape with fewer points in it.
CORRIDOR_OFFSET_MILES = 40.0

#: Upper limit on grid points.
#:
#: The weather quota counts locations, not requests, so this is the single
#: biggest lever on what a trip costs. A heatmap is read as a wash of
#: colour over a corridor hundreds of miles long; at this spacing it still
#: reads that way, and a coast-to-coast trip cannot run the quota down on
#: its own.
MAX_CORRIDOR_POINTS = 120

#: The forecast slider covers the departure hour plus the next 48 hours.
FORECAST_HOURS = 48

#: Grid points are rounded to this many decimals, matching the weather cache.
GRID_PRECISION = 2

#: Rain is sent as hundredths of an inch per hour and snow as tenths, which
#: is finer than any threshold in the risk table and keeps them integers.
RAIN_SCALE = 100
SNOW_SCALE = 10


@dataclass(frozen=True)
class HeatmapGrid:
    """Conditions across the corridor, for every hour of the slider.

    Every grid is indexed ``[hour][point]``. The raw readings sit alongside
    the risk so the map can show what the weather is doing, not only how
    dangerous it is, without asking the server again when the driver
    switches metric.

    They are whole numbers on purpose: the grid is 49 hours by a few hundred
    points, and sending it as integers rather than floats keeps the response
    small enough to hold every frame in the browser.
    """

    times: list[datetime]
    points: list[Coordinate]
    #: Risk level from 0 (Low) to 4 (No Travel).
    values: list[list[int]]
    #: Wind in whole miles per hour.
    wind: list[list[int]]
    #: Rain in hundredths of an inch per hour, so 0.25 in/hr is 25.
    rain: list[list[int]]
    #: Snow in tenths of an inch per hour, so 1.5 in/hr is 15.
    snow: list[list[int]]


def corridor_points(
    geometries: Sequence[Sequence[Coordinate]],
    *,
    spacing_miles: float = CORRIDOR_SPACING_MILES,
    offset_miles: float = CORRIDOR_OFFSET_MILES,
    max_points: int = MAX_CORRIDOR_POINTS,
) -> list[Coordinate]:
    """Points covering the band of land the routes run through.

    For every sample along a route we also take a point to its left and to
    its right, so the heatmap has width and a storm beside the road is still
    visible.
    """
    points: list[Coordinate] = []

    for line in geometries:
        if len(line) < 2:
            continue

        shape = list(line)
        cumulative = cumulative_miles(shape)
        total_miles = cumulative[-1]

        for mile in _sample_miles(total_miles, spacing_miles):
            centre = interpolate_point(shape, cumulative, mile)
            heading = _heading_at(shape, cumulative, mile, total_miles)
            points.append(centre)
            points.append(point_at_bearing(centre, heading - 90, offset_miles))
            points.append(point_at_bearing(centre, heading + 90, offset_miles))

    return _dedupe_and_cap(points, max_points)


def build_heatmap(
    geometries: Sequence[Sequence[Coordinate]],
    departure: datetime,
    load_lb: float,
    *,
    hours: int = FORECAST_HOURS,
    horizon: datetime | None = None,
    now: datetime | None = None,
    cache: Cache | None = None,
) -> HeatmapGrid:
    """Score the corridor for every hour from departure to ``hours`` later.

    Frame 0 is the departure itself, to the minute, and each frame after it
    is one hour later, so the slider's "+6h" really means six hours after
    leaving. Each frame takes the forecast hour nearest to it.

    Frames past ``horizon`` - the last hour the forecast covers - are left
    out rather than filled with the wrong weather, so a trip departing near
    the end of the forecast gets a shorter slider.

    The weather is fetched once for the whole window, then scored in memory,
    so the frames cost one round of requests rather than one each.
    """
    points = corridor_points(geometries)
    start = departure.astimezone(UTC).replace(second=0, microsecond=0)
    times = [start + timedelta(hours=step) for step in range(hours + 1)]
    if horizon is not None:
        times = [moment for moment in times if moment <= horizon] or [start]

    if not points:
        empty: list[list[int]] = [[] for _ in times]
        return HeatmapGrid(
            times=times,
            points=[],
            values=empty,
            wind=[list(row) for row in empty],
            rain=[list(row) for row in empty],
            snow=[list(row) for row in empty],
        )

    # The same window the plan asked for, so every point it already looked
    # up is served from the cache instead of being charged again.
    window = forecast_window(departure, times[-1], now or datetime.now(UTC))
    forecasts = fetch_hourly(points, window[0], window[1], cache=cache)

    values = [[0] * len(points) for _ in times]
    wind = [[0] * len(points) for _ in times]
    rain = [[0] * len(points) for _ in times]
    snow = [[0] * len(points) for _ in times]

    for point_index, forecast in enumerate(forecasts):
        for hour_index, moment in enumerate(times):
            sample = forecast.nearest(moment)
            verdict = assess(sample.wind_mph, sample.rain_in, sample.snow_in, load_lb)
            values[hour_index][point_index] = int(verdict.level)
            wind[hour_index][point_index] = round(sample.wind_mph)
            rain[hour_index][point_index] = round(sample.rain_in * RAIN_SCALE)
            snow[hour_index][point_index] = round(sample.snow_in * SNOW_SCALE)

    return HeatmapGrid(times=times, points=points, values=values, wind=wind, rain=rain, snow=snow)


def _sample_miles(total_miles: float, spacing_miles: float) -> list[float]:
    """Mile markers every ``spacing_miles``, always including the destination."""
    miles: list[float] = []
    mile = 0.0
    while mile < total_miles - DISTANCE_EPSILON_MILES:
        miles.append(mile)
        mile += spacing_miles
    miles.append(total_miles)
    return miles


def _heading_at(
    line: list[Coordinate], cumulative: list[float], mile: float, total_miles: float
) -> float:
    """Which way the road points at this mile, used to offset sideways."""
    here = interpolate_point(line, cumulative, mile)
    ahead = interpolate_point(line, cumulative, min(mile + 1.0, total_miles))
    if ahead == here:
        # At the very end of the route, look backwards instead.
        behind = interpolate_point(line, cumulative, max(mile - 1.0, 0.0))
        return initial_bearing(behind, here) if behind != here else 0.0
    return initial_bearing(here, ahead)


def _dedupe_and_cap(points: list[Coordinate], max_points: int) -> list[Coordinate]:
    """Round points onto a grid, drop repeats, and thin out if there are too many.

    Rounding is what makes the three routes share points where they run
    together, which cuts both the request count and the cache misses.
    """
    rounded = [(round(lon, GRID_PRECISION), round(lat, GRID_PRECISION)) for lon, lat in points]
    unique = list(dict.fromkeys(rounded))

    if len(unique) <= max_points:
        return unique

    # Keep an evenly spread subset rather than the first N, so the thinned
    # grid still covers the whole trip instead of just its first half.
    stride = len(unique) / max_points
    return [unique[int(index * stride)] for index in range(max_points)]
