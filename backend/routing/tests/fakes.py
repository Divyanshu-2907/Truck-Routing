"""Shared stand-ins for the external services, used by the trip and API tests.

They replace the two functions that reach the network - the route lookup and
the weather lookup - so the whole planning pipeline can run offline and give
the same answer every time.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from routing.services.geo import Coordinate, point_at_bearing
from routing.services.routes import RouteOption
from routing.services.weather import HourlyForecast, WeatherBatch

DALLAS: Coordinate = (-96.797, 32.7767)


def north_route(label: str, miles: float, hours: float, reported_miles: float) -> RouteOption:
    """A route heading due north, whose reported distance can differ from its shape."""
    shape = [point_at_bearing(DALLAS, 0.0, miles * step / 20) for step in range(21)]
    return RouteOption(
        label=label,
        distance_miles=reported_miles,
        duration_s=hours * 3600,
        geometry=shape,
        source="osrm-alternative",
    )


def fake_routes(*_args: object, **_kwargs: object) -> list[RouteOption]:
    """Two routes; Route A is quicker. The shape is 100 mi, OSRM says 101 mi."""
    return [
        north_route("Route A", miles=100.0, hours=2.0, reported_miles=101.0),
        north_route("Route B", miles=100.0, hours=3.0, reported_miles=101.0),
    ]


def calm_weather(
    points: list[Coordinate], start: datetime, end: datetime, cache: object = None
) -> WeatherBatch:
    """Five mph of wind everywhere, for every hour of the trip."""
    first = start.replace(minute=0, second=0, microsecond=0) - timedelta(hours=1)
    hours = int((end - first).total_seconds() // 3600) + 3
    times = tuple(first + timedelta(hours=offset) for offset in range(hours))
    forecast = HourlyForecast(
        times=times,
        wind_mph=(5.0,) * hours,
        rain_in=(0.0,) * hours,
        snow_in=(0.0,) * hours,
    )
    return WeatherBatch(forecasts=[forecast for _ in points], source="open-meteo")
