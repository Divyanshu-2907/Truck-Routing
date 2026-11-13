"""Tests for the Open-Meteo forecast service, with HTTP replaced by a fake.

The risky parts here are unit handling (snowfall can arrive in centimetres),
picking the forecast hour closest to an arrival time, and the batching and
caching that keep a 250-checkpoint trip fast.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

import requests

from routing.services.geo import Coordinate
from routing.services.http_client import ExternalServiceError
from routing.services.weather import (
    CHUNK_SIZE,
    SHARED_WINDOW_HOURS,
    HourlyForecast,
    _hour_window,
    fetch_hourly,
    forecast_horizon,
    forecast_window,
)

START = datetime(2026, 1, 2, 6, 0, tzinfo=UTC)
END = START + timedelta(hours=6)


def hourly_block(
    hours: int = 12, *, snow_unit: str = "inch", snow_values: list[float] | None = None
) -> dict[str, Any]:
    """One location's forecast, counting wind up by one mph each hour."""
    times = [
        (START + timedelta(hours=offset)).strftime("%Y-%m-%dT%H:%M") for offset in range(hours)
    ]
    return {
        "hourly_units": {"wind_speed_10m": "mp/h", "rain": "inch", "snowfall": snow_unit},
        "hourly": {
            "time": times,
            "wind_speed_10m": [float(offset) for offset in range(hours)],
            "rain": [0.05] * hours,
            "showers": [0.0] * hours,
            "snowfall": snow_values if snow_values is not None else [0.0] * hours,
        },
    }


class FakeResponse:
    def __init__(self, payload: Any) -> None:
        self._payload = payload
        self.status_code = 200

    def json(self) -> Any:
        return self._payload


class WeatherTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def fake_get(self, payload_for_chunk):
        """A ``requests.get`` stand-in that builds a payload per request."""

        def _get(url: str, params: Any = None, headers: Any = None, timeout: Any = None):
            self.calls.append(params or {})
            count = len(str(params.get("latitude", "")).split(","))
            return FakeResponse(payload_for_chunk(count))

        return _get


class NearestHourTests(unittest.TestCase):
    """Each checkpoint uses the forecast hour closest to its arrival time."""

    def setUp(self) -> None:
        self.forecast = HourlyForecast(
            times=tuple(START + timedelta(hours=offset) for offset in range(4)),
            wind_mph=(10.0, 20.0, 30.0, 40.0),
            rain_in=(0.0, 0.1, 0.2, 0.3),
            snow_in=(0.0, 0.0, 0.0, 0.0),
        )

    def test_exact_hour(self) -> None:
        self.assertEqual(self.forecast.nearest(START + timedelta(hours=2)).wind_mph, 30.0)

    def test_rounds_down_before_the_half_hour(self) -> None:
        sample = self.forecast.nearest(START + timedelta(hours=1, minutes=20))
        self.assertEqual(sample.wind_mph, 20.0)

    def test_rounds_up_after_the_half_hour(self) -> None:
        sample = self.forecast.nearest(START + timedelta(hours=1, minutes=40))
        self.assertEqual(sample.wind_mph, 30.0)

    def test_times_outside_the_window_clamp_to_the_ends(self) -> None:
        self.assertEqual(self.forecast.nearest(START - timedelta(days=1)).wind_mph, 10.0)
        self.assertEqual(self.forecast.nearest(START + timedelta(days=1)).wind_mph, 40.0)


class UnitConversionTests(WeatherTestCase):
    """Snowfall must end up in inches per hour whatever Open-Meteo sends."""

    def test_centimetres_are_converted_to_inches(self) -> None:
        payload = hourly_block(snow_unit="cm", snow_values=[2.54] * 12)
        with patch.object(requests, "get", self.fake_get(lambda count: [payload] * count)):
            forecast = fetch_hourly([(-96.8, 32.8)], START, END)[0]

        self.assertAlmostEqual(forecast.snow_in[0], 1.0, places=3)

    def test_inches_are_left_alone(self) -> None:
        payload = hourly_block(snow_unit="inch", snow_values=[1.5] * 12)
        with patch.object(requests, "get", self.fake_get(lambda count: [payload] * count)):
            forecast = fetch_hourly([(-96.8, 32.8)], START, END)[0]

        self.assertAlmostEqual(forecast.snow_in[0], 1.5, places=6)

    def test_missing_values_are_treated_as_zero(self) -> None:
        payload = hourly_block()
        payload["hourly"]["rain"] = [None] * 12
        with patch.object(requests, "get", self.fake_get(lambda count: [payload] * count)):
            forecast = fetch_hourly([(-96.8, 32.8)], START, END)[0]

        self.assertEqual(forecast.rain_in[0], 0.0)

    def test_units_are_requested_in_mph_inches_and_gmt(self) -> None:
        payload = hourly_block()
        with patch.object(requests, "get", self.fake_get(lambda count: [payload] * count)):
            fetch_hourly([(-96.8, 32.8)], START, END)

        params = self.calls[0]
        self.assertEqual(params["wind_speed_unit"], "mph")
        self.assertEqual(params["precipitation_unit"], "inch")
        self.assertEqual(params["timezone"], "GMT")
        self.assertEqual(params["hourly"], "wind_speed_10m,rain,showers,snowfall")


class BatchingTests(WeatherTestCase):
    """Many checkpoints are fetched in a few batched requests, not one each."""

    def test_points_are_sent_in_one_request_per_chunk(self) -> None:
        points: list[Coordinate] = [(-96.0 - index * 0.1, 32.0) for index in range(250)]
        payload = hourly_block()
        with patch.object(requests, "get", self.fake_get(lambda count: [payload] * count)):
            forecasts = fetch_hourly(points, START, END)

        self.assertEqual(len(forecasts), 250)
        self.assertEqual(len(self.calls), 3)  # 100 + 100 + 50
        self.assertEqual(len(self.calls[0]["latitude"].split(",")), CHUNK_SIZE)

    def test_nearby_points_share_one_lookup(self) -> None:
        # Three points within a few hundred feet round to the same coordinate.
        points: list[Coordinate] = [(-96.800, 32.800), (-96.8001, 32.8002), (-96.8, 32.8)]
        payload = hourly_block()
        with patch.object(requests, "get", self.fake_get(lambda count: [payload] * count)):
            forecasts = fetch_hourly(points, START, END)

        self.assertEqual(len(forecasts), 3)
        self.assertEqual(len(self.calls[0]["latitude"].split(",")), 1)

    def test_forecasts_come_back_in_the_order_the_points_were_given(self) -> None:
        points: list[Coordinate] = [(-96.0, 32.0), (-97.0, 33.0)]

        def payload_for(count: int) -> list[dict[str, Any]]:
            # Give the two locations different winds so they can be told apart.
            return [hourly_block(snow_values=[float(index)] * 12) for index in range(count)]

        with patch.object(requests, "get", self.fake_get(payload_for)):
            forecasts = fetch_hourly(points, START, END)

        self.assertEqual(forecasts[0].snow_in[0], 0.0)
        self.assertEqual(forecasts[1].snow_in[0], 1.0)

    def test_no_points_means_no_requests(self) -> None:
        with patch.object(requests, "get", self.fake_get(lambda count: [])):
            self.assertEqual(fetch_hourly([], START, END), [])
        self.assertEqual(self.calls, [])


class CachingTests(WeatherTestCase):
    class DictCache:
        def __init__(self) -> None:
            self.store: dict[str, Any] = {}

        def get(self, key: str) -> Any:
            return self.store.get(key)

        def set(self, key: str, value: Any, timeout: int | None = None) -> None:
            self.store[key] = value

    def test_a_second_lookup_uses_the_cache(self) -> None:
        cache = self.DictCache()
        payload = hourly_block()
        with patch.object(requests, "get", self.fake_get(lambda count: [payload] * count)):
            fetch_hourly([(-96.8, 32.8)], START, END, cache=cache)
            fetch_hourly([(-96.8, 32.8)], START, END, cache=cache)

        self.assertEqual(len(self.calls), 1)

    def test_only_the_uncached_points_are_fetched(self) -> None:
        cache = self.DictCache()
        payload = hourly_block()
        with patch.object(requests, "get", self.fake_get(lambda count: [payload] * count)):
            fetch_hourly([(-96.8, 32.8)], START, END, cache=cache)
            fetch_hourly([(-96.8, 32.8), (-97.9, 33.9)], START, END, cache=cache)

        self.assertEqual(len(self.calls[1]["latitude"].split(",")), 1)


class ErrorTests(WeatherTestCase):
    def test_an_empty_forecast_is_reported_clearly(self) -> None:
        payload = hourly_block()
        payload["hourly"]["time"] = []
        with patch.object(requests, "get", self.fake_get(lambda count: [payload] * count)):
            with self.assertRaises(ExternalServiceError) as caught:
                fetch_hourly([(-96.8, 32.8)], START, END)

        self.assertIn("16 days", str(caught.exception))

    def test_a_short_response_is_rejected(self) -> None:
        with patch.object(requests, "get", self.fake_get(lambda count: [])):
            with self.assertRaises(ExternalServiceError):
                fetch_hourly([(-96.8, 32.8)], START, END)


class ShowersTests(WeatherTestCase):
    """Thunderstorm rain arrives as "showers" and must count as rain."""

    def test_showers_are_added_to_rain(self) -> None:
        payload = hourly_block()
        payload["hourly"]["rain"] = [0.0] * 12
        payload["hourly"]["showers"] = [0.6] * 12
        with patch.object(requests, "get", self.fake_get(lambda count: [payload] * count)):
            forecast = fetch_hourly([(-96.8, 32.8)], START, END)[0]

        # 0.6 in/hr of convective rain is Severe; reading "rain" alone gave 0.
        self.assertAlmostEqual(forecast.rain_in[0], 0.6, places=6)

    def test_rain_and_showers_together(self) -> None:
        payload = hourly_block()
        payload["hourly"]["rain"] = [0.2] * 12
        payload["hourly"]["showers"] = [0.15] * 12
        with patch.object(requests, "get", self.fake_get(lambda count: [payload] * count)):
            forecast = fetch_hourly([(-96.8, 32.8)], START, END)[0]

        self.assertAlmostEqual(forecast.rain_in[0], 0.35, places=6)

    def test_a_missing_showers_series_is_treated_as_zero(self) -> None:
        payload = hourly_block()
        del payload["hourly"]["showers"]
        with patch.object(requests, "get", self.fake_get(lambda count: [payload] * count)):
            forecast = fetch_hourly([(-96.8, 32.8)], START, END)[0]

        self.assertAlmostEqual(forecast.rain_in[0], 0.05, places=6)


class ForecastHorizonTests(unittest.TestCase):
    """The limit Open-Meteo enforces, measured against the live service."""

    def test_counts_whole_days_from_midnight_utc(self) -> None:
        # Asked at 14:44 on the 12th, Open-Meteo accepts up to 23:00 on the 27th.
        now = datetime(2026, 11, 12, 14, 44, tzinfo=UTC)
        self.assertEqual(forecast_horizon(now), datetime(2026, 11, 27, 23, 0, tzinfo=UTC))

    def test_is_the_same_whatever_the_callers_timezone(self) -> None:
        india = timezone(timedelta(hours=5, minutes=30))
        now = datetime(2026, 11, 12, 14, 44, tzinfo=UTC)
        self.assertEqual(forecast_horizon(now.astimezone(india)), forecast_horizon(now))

    def test_the_request_window_never_passes_the_horizon(self) -> None:
        horizon = datetime(2026, 11, 27, 23, 0, tzinfo=UTC)
        start = datetime(2026, 11, 27, 10, 0, tzinfo=UTC)
        end = datetime(2026, 11, 27, 22, 40, tzinfo=UTC)

        _window_start, window_end = _hour_window(start, end, horizon)

        # Without the clamp the hour of slack would ask for 23:00 + 1h.
        self.assertEqual(window_end, horizon)


class ArrivalTimeTests(unittest.TestCase):
    """The forecast hour used must be the one nearest the truck's arrival."""

    def test_an_india_timed_departure_reads_the_right_utc_hour(self) -> None:
        # A forecast whose wind equals its UTC hour, so the pick is visible.
        base = datetime(2026, 1, 2, 0, 0, tzinfo=UTC)
        forecast = HourlyForecast(
            times=tuple(base + timedelta(hours=h) for h in range(24)),
            wind_mph=tuple(float(h) for h in range(24)),
            rain_in=(0.0,) * 24,
            snow_in=(0.0,) * 24,
        )
        india = timezone(timedelta(hours=5, minutes=30))
        # 20:10 in India is 14:40 UTC, so the nearest forecast hour is 15:00.
        arrival = datetime(2026, 1, 2, 20, 10, tzinfo=india)

        self.assertEqual(forecast.nearest(arrival).wind_mph, 15.0)


class LocationCountTests(WeatherTestCase):
    """The free tier charges per location, so distinct points are the cost."""

    def test_points_in_one_grid_cell_are_charged_once(self) -> None:
        # A tenth of a degree is about 7 miles. Checkpoints every mile along
        # a road therefore share a handful of lookups, not one each.
        points: list[Coordinate] = [(-96.80 + index * 0.014, 32.80) for index in range(20)]
        payload = hourly_block()
        with patch.object(requests, "get", self.fake_get(lambda count: [payload] * count)):
            forecasts = fetch_hourly(points, START, END)

        asked = len(self.calls[0]["latitude"].split(","))
        self.assertEqual(len(forecasts), 20)
        self.assertLessEqual(asked, 4)

    def test_the_three_routes_share_one_lookup_where_they_run_together(self) -> None:
        shared: list[Coordinate] = [(-96.8 + index * 0.2, 32.8) for index in range(5)]
        # Three routes leaving town on the same road, then diverging.
        points = shared * 3 + [(-100.0, 35.0), (-100.5, 35.5)]
        payload = hourly_block()
        with patch.object(requests, "get", self.fake_get(lambda count: [payload] * count)):
            fetch_hourly(points, START, END)

        self.assertEqual(len(self.calls[0]["latitude"].split(",")), 7)

    def test_every_point_still_gets_its_own_forecast_back(self) -> None:
        points: list[Coordinate] = [(-96.80, 32.80), (-96.801, 32.801), (-99.0, 35.0)]

        def payload_for(count: int) -> list[dict[str, Any]]:
            return [hourly_block(snow_values=[float(index)] * 12) for index in range(count)]

        with patch.object(requests, "get", self.fake_get(payload_for)):
            forecasts = fetch_hourly(points, START, END)

        self.assertEqual(len(forecasts), 3)
        # The first two round to the same cell, so they share a forecast.
        self.assertEqual(forecasts[0].snow_in[0], forecasts[1].snow_in[0])
        self.assertNotEqual(forecasts[0].snow_in[0], forecasts[2].snow_in[0])


class SharedWindowTests(unittest.TestCase):
    """The plan and the heatmap must ask for the same hours to share a cache."""

    def setUp(self) -> None:
        self.now = datetime(2026, 1, 2, 5, 0, tzinfo=UTC)
        self.departure = datetime(2026, 1, 2, 6, 30, tzinfo=UTC)

    def test_a_short_drive_still_asks_for_the_full_slider_window(self) -> None:
        arrival = self.departure + timedelta(hours=3)

        start, end = forecast_window(self.departure, arrival, self.now)

        self.assertEqual(start, self.departure.replace(minute=0))
        self.assertEqual(end, start + timedelta(hours=SHARED_WINDOW_HOURS))

    def test_the_plan_and_the_heatmap_agree_for_a_normal_trip(self) -> None:
        plan = forecast_window(self.departure, self.departure + timedelta(hours=14), self.now)
        heatmap = forecast_window(
            self.departure, self.departure + timedelta(hours=SHARED_WINDOW_HOURS), self.now
        )

        self.assertEqual(plan, heatmap)

    def test_a_drive_longer_than_the_window_extends_it(self) -> None:
        arrival = self.departure + timedelta(hours=58)

        _start, end = forecast_window(self.departure, arrival, self.now)

        self.assertEqual(end, arrival.replace(minute=0))

    def test_the_window_never_runs_past_the_forecast(self) -> None:
        late = forecast_horizon(self.now) - timedelta(hours=2)

        _start, end = forecast_window(late, late + timedelta(hours=40), self.now)

        self.assertEqual(end, forecast_horizon(self.now))


class CacheReuseTests(WeatherTestCase):
    """The second request of a pair should mostly be free."""

    class DictCache:
        def __init__(self) -> None:
            self.store: dict[str, Any] = {}

        def get(self, key: str) -> Any:
            return self.store.get(key)

        def set(self, key: str, value: Any, timeout: int | None = None) -> None:
            self.store[key] = value

    def test_a_later_request_only_pays_for_points_it_adds(self) -> None:
        cache = self.DictCache()
        plan_points: list[Coordinate] = [(-96.8 + index * 0.2, 32.8) for index in range(5)]
        # The heatmap covers the same road plus a band either side of it.
        heatmap_points = plan_points + [(-96.8 + index * 0.2, 33.4) for index in range(5)]
        payload = hourly_block()

        with patch.object(requests, "get", self.fake_get(lambda count: [payload] * count)):
            fetch_hourly(plan_points, START, END, cache=cache)
            fetch_hourly(heatmap_points, START, END, cache=cache)

        self.assertEqual(len(self.calls[0]["latitude"].split(",")), 5)
        # Only the five new cells are charged for the second time round.
        self.assertEqual(len(self.calls[1]["latitude"].split(",")), 5)

    def test_a_different_window_cannot_reuse_the_cache(self) -> None:
        cache = self.DictCache()
        points: list[Coordinate] = [(-96.8, 32.8)]
        payload = hourly_block()

        with patch.object(requests, "get", self.fake_get(lambda count: [payload] * count)):
            fetch_hourly(points, START, END, cache=cache)
            fetch_hourly(
                points, START + timedelta(hours=12), END + timedelta(hours=12), cache=cache
            )

        # Which is exactly why both callers ask for the same hours.
        self.assertEqual(len(self.calls), 2)
