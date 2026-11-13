"""Tests for the fallback weather service and when it is reached for.

The payloads below are trimmed copies of a real MET Norway response, so the
parsing is tested against the shape the service actually returns.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

import requests

from routing.services import weather as weather_module
from routing.services.geo import Coordinate
from routing.services.http_client import ExternalServiceError
from routing.services.weather import (
    MM_PER_INCH,
    MPH_PER_METRE_PER_SECOND,
    PROVIDER_COOLDOWN_SECONDS,
    SNOW_TO_LIQUID_RATIO,
    fetch_hourly,
)

DALLAS: Coordinate = (-96.8, 32.8)
START = datetime(2026, 1, 2, 6, 0, tzinfo=UTC)
END = START + timedelta(hours=6)


def met_entry(
    hour: int,
    *,
    wind_ms: float = 0.0,
    temperature_c: float = 10.0,
    precipitation_mm: float = 0.0,
    block: str = "next_1_hours",
) -> dict[str, Any]:
    moment = START + timedelta(hours=hour)
    return {
        "time": moment.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data": {
            "instant": {
                "details": {"air_temperature": temperature_c, "wind_speed": wind_ms},
            },
            block: {"details": {"precipitation_amount": precipitation_mm}},
        },
    }


def met_payload(*entries: dict[str, Any]) -> dict[str, Any]:
    return {"properties": {"timeseries": list(entries)}}


class FakeResponse:
    def __init__(
        self,
        payload: Any,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("no body")
        return self._payload


class MetTestCase(unittest.TestCase):
    """Sends every request to MET Norway by failing Open-Meteo first."""

    def setUp(self) -> None:
        self.urls: list[str] = []
        self.sent_headers: list[dict[str, str]] = []
        sleeping = patch.object(weather_module.time, "sleep", lambda _seconds: None)
        sleeping.start()
        self.addCleanup(sleeping.stop)

    def fake_get(self, met_responses: list[Any], open_meteo_status: int = 429):
        """Open-Meteo refuses; MET Norway replies with the given responses."""
        remaining = list(met_responses)

        def _get(url: str, params: Any = None, headers: Any = None, timeout: Any = None):
            self.urls.append(url)
            self.sent_headers.append(dict(headers or {}))
            if "open-meteo" in url:
                return FakeResponse({"error": True, "reason": "limit"}, open_meteo_status)
            return remaining.pop(0) if remaining else FakeResponse(met_payload(met_entry(0)))

        return _get

    def met_calls(self) -> list[str]:
        return [url for url in self.urls if "met.no" in url]


class FallbackTests(MetTestCase):
    """Open-Meteo is tried first, and only a refusal moves us across."""

    def test_a_429_falls_back_and_says_so(self) -> None:
        payload = met_payload(met_entry(0, wind_ms=10.0))
        with patch.object(requests, "get", self.fake_get([FakeResponse(payload)])):
            batch = fetch_hourly([DALLAS], START, END)

        self.assertEqual(batch.source, "met-norway")
        self.assertEqual(len(batch.forecasts), 1)
        self.assertEqual(len(self.met_calls()), 1)

    def test_being_unreachable_also_falls_back(self) -> None:
        def _get(url: str, params: Any = None, headers: Any = None, timeout: Any = None):
            self.urls.append(url)
            if "open-meteo" in url:
                raise requests.ConnectionError
            return FakeResponse(met_payload(met_entry(0)))

        with patch.object(requests, "get", _get):
            batch = fetch_hourly([DALLAS], START, END)

        self.assertEqual(batch.source, "met-norway")

    def test_a_working_open_meteo_is_left_alone(self) -> None:
        open_meteo = {
            "hourly_units": {"snowfall": "inch"},
            "hourly": {
                "time": ["2026-01-02T06:00"],
                "wind_speed_10m": [5.0],
                "rain": [0.0],
                "showers": [0.0],
                "snowfall": [0.0],
            },
        }

        def _get(url: str, params: Any = None, headers: Any = None, timeout: Any = None):
            self.urls.append(url)
            return FakeResponse([open_meteo])

        with patch.object(requests, "get", _get):
            batch = fetch_hourly([DALLAS], START, END)

        self.assertEqual(batch.source, "open-meteo")
        self.assertEqual(self.met_calls(), [])

    def test_a_bad_request_is_not_papered_over_by_the_fallback(self) -> None:
        # A 400 means our own request was wrong. Falling back would hide it.
        with patch.object(requests, "get", self.fake_get([], open_meteo_status=400)):
            with self.assertRaises(ExternalServiceError):
                fetch_hourly([DALLAS], START, END)

        self.assertEqual(self.met_calls(), [])

    def test_an_identifying_user_agent_is_sent(self) -> None:
        with patch.object(
            requests, "get", self.fake_get([FakeResponse(met_payload(met_entry(0)))])
        ):
            fetch_hourly([DALLAS], START, END)

        agent = self.sent_headers[-1]["User-Agent"]
        self.assertIn("WeatherAwareTruckRouting", agent)
        self.assertIn("github.com", agent)

    def test_coordinates_are_sent_to_four_decimals(self) -> None:
        captured: list[dict[str, Any]] = []

        def _get(url: str, params: Any = None, headers: Any = None, timeout: Any = None):
            self.urls.append(url)
            if "open-meteo" in url:
                return FakeResponse({"error": True, "reason": "limit"}, 429)
            captured.append(dict(params or {}))
            return FakeResponse(met_payload(met_entry(0)))

        with patch.object(requests, "get", _get):
            fetch_hourly([DALLAS], START, END)

        self.assertEqual(captured[0], {"lat": "32.8000", "lon": "-96.8000"})


class ConversionTests(MetTestCase):
    """MET Norway's units are not ours."""

    def forecast(self, entry: dict[str, Any]):
        with patch.object(requests, "get", self.fake_get([FakeResponse(met_payload(entry))])):
            return fetch_hourly([DALLAS], START, END).forecasts[0]

    def test_wind_goes_from_metres_per_second_to_mph(self) -> None:
        forecast = self.forecast(met_entry(0, wind_ms=10.0))

        self.assertAlmostEqual(forecast.wind_mph[0], 10.0 * MPH_PER_METRE_PER_SECOND, places=4)
        self.assertAlmostEqual(forecast.wind_mph[0], 22.37, places=2)

    def test_rain_goes_from_millimetres_to_inches_per_hour(self) -> None:
        forecast = self.forecast(met_entry(0, precipitation_mm=25.4, temperature_c=10.0))

        self.assertAlmostEqual(forecast.rain_in[0], 1.0, places=6)
        self.assertEqual(forecast.snow_in[0], 0.0)

    def test_a_six_hour_block_is_spread_over_its_hours(self) -> None:
        # 6 mm over six hours is 1 mm an hour, not 6.
        forecast = self.forecast(
            met_entry(0, precipitation_mm=6.0, block="next_6_hours", temperature_c=10.0)
        )

        self.assertAlmostEqual(forecast.rain_in[0], 1.0 / MM_PER_INCH, places=6)

    def test_a_missing_reading_does_not_invent_weather(self) -> None:
        bare = {"time": "2026-01-02T06:00:00Z", "data": {"instant": {"details": {}}}}
        forecast = self.forecast(bare)

        self.assertEqual(forecast.wind_mph[0], 0.0)
        self.assertEqual(forecast.rain_in[0], 0.0)
        self.assertEqual(forecast.snow_in[0], 0.0)


class SnowSplitTests(MetTestCase):
    """MET Norway reports one precipitation figure; snow is inferred."""

    def forecast(self, **kwargs: Any):
        entry = met_entry(0, **kwargs)
        with patch.object(requests, "get", self.fake_get([FakeResponse(met_payload(entry))])):
            return fetch_hourly([DALLAS], START, END).forecasts[0]

    def test_above_freezing_it_is_all_rain(self) -> None:
        forecast = self.forecast(precipitation_mm=25.4, temperature_c=0.1)

        self.assertAlmostEqual(forecast.rain_in[0], 1.0, places=6)
        self.assertEqual(forecast.snow_in[0], 0.0)

    def test_at_freezing_it_is_all_snow(self) -> None:
        forecast = self.forecast(precipitation_mm=25.4, temperature_c=0.0)

        self.assertEqual(forecast.rain_in[0], 0.0)
        self.assertAlmostEqual(forecast.snow_in[0], SNOW_TO_LIQUID_RATIO, places=6)

    def test_below_freezing_uses_the_snow_to_liquid_ratio(self) -> None:
        # 2.54 mm of melted water is 0.1 inch, which is an inch of snow.
        forecast = self.forecast(precipitation_mm=2.54, temperature_c=-5.0)

        self.assertAlmostEqual(forecast.snow_in[0], 1.0, places=6)
        self.assertEqual(forecast.rain_in[0], 0.0)

    def test_cold_and_dry_produces_neither(self) -> None:
        forecast = self.forecast(precipitation_mm=0.0, temperature_c=-5.0)

        self.assertEqual(forecast.snow_in[0], 0.0)
        self.assertEqual(forecast.rain_in[0], 0.0)


class CachingTests(MetTestCase):
    """Their terms ask for caching and conditional requests; we do both."""

    class DictCache:
        def __init__(self) -> None:
            self.store: dict[str, Any] = {}

        def get(self, key: str) -> Any:
            return self.store.get(key)

        def set(self, key: str, value: Any, timeout: int | None = None) -> None:
            self.store[key] = value

    def test_a_fresh_entry_is_not_asked_for_again(self) -> None:
        cache = self.DictCache()
        fresh = FakeResponse(
            met_payload(met_entry(0)),
            headers={"Expires": "Fri, 13 Nov 2099 07:54:17 GMT", "Last-Modified": "then"},
        )
        with patch.object(requests, "get", self.fake_get([fresh])):
            fetch_hourly([DALLAS], START, END, cache=cache)
            fetch_hourly([DALLAS], START, END, cache=cache)

        self.assertEqual(len(self.met_calls()), 1)

    def test_a_stale_entry_is_revalidated_and_reused_on_304(self) -> None:
        cache = self.DictCache()
        # Already expired, so the second lookup has to check with them.
        first = FakeResponse(
            met_payload(met_entry(0, wind_ms=10.0)),
            headers={"Expires": "Fri, 13 Nov 2000 07:54:17 GMT", "Last-Modified": "then"},
        )
        not_modified = FakeResponse(None, status_code=304, headers={})

        with patch.object(requests, "get", self.fake_get([first, not_modified])):
            fetch_hourly([DALLAS], START, END, cache=cache)
            batch = fetch_hourly([DALLAS], START, END, cache=cache)

        self.assertEqual(len(self.met_calls()), 2)
        self.assertEqual(self.sent_headers[-1]["If-Modified-Since"], "then")
        # The forecast survives the 304 rather than being lost.
        self.assertAlmostEqual(
            batch.forecasts[0].wind_mph[0], 10.0 * MPH_PER_METRE_PER_SECOND, places=4
        )

    def test_open_meteo_is_not_retried_while_it_is_known_to_be_refusing(self) -> None:
        cache = self.DictCache()
        open_meteo = lambda: len([url for url in self.urls if "open-meteo" in url])  # noqa: E731

        with patch.object(requests, "get", self.fake_get([])):
            fetch_hourly([DALLAS], START, END, cache=cache)
            after_first = open_meteo()
            fetch_hourly([(-99.0, 35.0)], START, END, cache=cache)

        # The first trip discovers the refusal; the second does not pay to
        # rediscover it, and goes straight to the fallback.
        self.assertGreater(after_first, 0)
        self.assertEqual(open_meteo(), after_first)

    def test_the_cooldown_is_not_forever(self) -> None:
        cache = self.DictCache()
        with patch.object(requests, "get", self.fake_get([])):
            fetch_hourly([DALLAS], START, END, cache=cache)

        stored = [value for key, value in cache.store.items() if "weather-provider" in key]
        self.assertEqual(stored, [True])
        self.assertLessEqual(PROVIDER_COOLDOWN_SECONDS, 60 * 60)
