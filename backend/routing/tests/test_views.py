"""Tests for the HTTP endpoints: validation, error mapping and response shape.

The services are tested on their own elsewhere. These check the contract the
frontend relies on: bad input is a 400, an outage is a 502, both carry one
readable ``error`` sentence, and a good request returns the fields the UI
reads.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

from django.test import SimpleTestCase

from routing import views
from routing.services import heatmap as heatmap_module
from routing.services import trip as trip_module
from routing.services.http_client import ExternalServiceError
from routing.services.trip import PlanningError
from routing.tests.fakes import calm_weather, fake_routes

DALLAS = {"lat": 32.7767, "lon": -96.797, "label": "Dallas, TX"}
DENVER = {"lat": 39.7392, "lon": -104.9903, "label": "Denver, CO"}


def soon() -> str:
    return (datetime.now(UTC) + timedelta(hours=2)).isoformat()


def trip(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "origin": DALLAS,
        "destination": DENVER,
        "departure": soon(),
        "load_lb": 40_000,
        "interval_miles": 25,
    }
    body.update(overrides)
    return body


def heatmap_trip() -> dict[str, Any]:
    body = trip()
    del body["interval_miles"]
    return body


class ApiTestCase(SimpleTestCase):
    """Runs every request with the network replaced by the offline fakes."""

    def setUp(self) -> None:
        self.patches = [
            patch.object(trip_module, "get_routes", fake_routes),
            patch.object(trip_module, "fetch_hourly", calm_weather),
            patch.object(heatmap_module, "fetch_hourly", calm_weather),
        ]
        for active in self.patches:
            active.start()

    def tearDown(self) -> None:
        for active in self.patches:
            active.stop()

    def post(self, path: str, body: dict[str, Any]) -> Any:
        return self.client.post(path, data=json.dumps(body), content_type="application/json")


class HealthAndGeocodeTests(ApiTestCase):
    def test_health(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_a_too_short_search_is_a_400(self) -> None:
        response = self.client.get("/api/geocode", {"q": "D"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("at least", response.json()["error"])

    def test_a_search_service_outage_is_a_502(self) -> None:
        def broken(*_args: object, **_kwargs: object) -> None:
            raise ExternalServiceError("The place search service could not be reached.")

        with patch.object(views, "geocode", broken):
            response = self.client.get("/api/geocode", {"q": "Dallas"})

        self.assertEqual(response.status_code, 502)
        self.assertIn("could not be reached", response.json()["error"])


class PlanValidationTests(ApiTestCase):
    """Bad input is refused before any external service is called."""

    def assert_rejected(self, body: dict[str, Any], words: str) -> None:
        response = self.post("/api/plan", body)
        self.assertEqual(response.status_code, 400)
        self.assertIn(words, response.json()["error"])

    def test_departure_without_a_timezone(self) -> None:
        self.assert_rejected(trip(departure="2026-11-13T08:00:00"), "timezone offset")

    def test_departure_in_the_past(self) -> None:
        past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
        self.assert_rejected(trip(departure=past), "already passed")

    def test_departure_a_few_minutes_ago_is_allowed(self) -> None:
        recent = (datetime.now(UTC) - timedelta(minutes=20)).isoformat()
        response = self.post("/api/plan", trip(departure=recent))
        self.assertEqual(response.status_code, 200)

    def test_departure_past_the_forecast(self) -> None:
        later = (datetime.now(UTC) + timedelta(days=17)).isoformat()
        self.assert_rejected(trip(departure=later), "16 days")

    def test_origin_and_destination_the_same(self) -> None:
        self.assert_rejected(trip(destination=DALLAS), "same place")

    def test_load_out_of_range_or_not_a_number(self) -> None:
        self.assert_rejected(trip(load_lb=0), "load_lb")
        self.assert_rejected(trip(load_lb=80_001), "load_lb")
        self.assert_rejected(trip(load_lb="heavy"), "load_lb")

    def test_interval_must_be_one_of_the_three(self) -> None:
        self.assert_rejected(trip(interval_miles=30), "interval_miles")

    def test_missing_destination(self) -> None:
        body = trip()
        del body["destination"]
        self.assert_rejected(body, "destination")


class PlanErrorMappingTests(ApiTestCase):
    def test_a_trip_that_cannot_be_planned_as_asked_is_a_400(self) -> None:
        def refuse(*_args: object, **_kwargs: object) -> None:
            raise PlanningError("Choose an earlier departure.")

        with patch.object(views, "plan_trip", refuse):
            response = self.post("/api/plan", trip())

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json(), {"error": "Choose an earlier departure."})

    def test_an_external_outage_is_a_502(self) -> None:
        def outage(*_args: object, **_kwargs: object) -> None:
            raise ExternalServiceError("The routing service could not be reached.")

        with patch.object(views, "plan_trip", outage):
            response = self.post("/api/plan", trip())

        self.assertEqual(response.status_code, 502)
        self.assertIn("could not be reached", response.json()["error"])


class PlanResponseShapeTests(ApiTestCase):
    """The fields the frontend's types.ts expects are all present."""

    def test_a_good_request_returns_the_full_plan(self) -> None:
        response = self.post("/api/plan", trip())

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(
            set(body),
            {
                "routes",
                "recommended_index",
                "recommendation_reason",
                "deciding_criterion",
                "generated_at",
                "weather_source",
            },
        )
        self.assertEqual(body["weather_source"], "open-meteo")
        route = body["routes"][0]
        self.assertEqual(set(route), {"label", "source", "geometry", "summary", "checkpoints"})
        self.assertEqual(
            set(route["checkpoints"][0]),
            {
                "mile",
                "covered_miles",
                "lat",
                "lon",
                "eta",
                "wind_mph",
                "rain_in",
                "snow_in",
                "level",
                "level_label",
                "reason",
                "condition",
            },
        )


class HeatmapEndpointTests(ApiTestCase):
    def test_a_good_request_returns_the_grid(self) -> None:
        response = self.post("/api/heatmap", heatmap_trip())

        self.assertEqual(response.status_code, 200)
        grid = response.json()
        self.assertEqual(len(grid["times"]), 49)
        self.assertEqual(len(grid["values"]), 49)
        self.assertEqual(len(grid["values"][0]), len(grid["points"]))
        self.assertEqual(grid["weather_source"], "open-meteo")

        # The raw readings come back beside the risk, on the same grid, so
        # the map can switch metric without asking the server again.
        for metric in ("wind", "rain", "snow"):
            self.assertEqual(len(grid[metric]), 49, metric)
            self.assertEqual(len(grid[metric][0]), len(grid["points"]), metric)
            self.assertTrue(all(isinstance(value, int) for value in grid[metric][0]), metric)

    def test_raw_readings_use_the_documented_scales(self) -> None:
        response = self.post("/api/heatmap", heatmap_trip())
        grid = response.json()

        # The offline forecast is a flat 5 mph with no rain or snow.
        self.assertEqual(set(grid["wind"][0]), {5})
        self.assertEqual(set(grid["rain"][0]), {0})
        self.assertEqual(set(grid["snow"][0]), {0})

    def test_frame_zero_is_the_departure(self) -> None:
        body = heatmap_trip()
        departure = datetime.fromisoformat(body["departure"])

        response = self.post("/api/heatmap", body)

        first = datetime.fromisoformat(response.json()["times"][0])
        self.assertEqual(first, departure.replace(second=0, microsecond=0))

    def test_errors_are_mapped_like_the_plan(self) -> None:
        def outage(*_args: object, **_kwargs: object) -> None:
            raise ExternalServiceError("The weather service could not be reached.")

        with patch.object(views, "trip_heatmap", outage):
            response = self.post("/api/heatmap", heatmap_trip())

        self.assertEqual(response.status_code, 502)


class SinglePageAppTests(ApiTestCase):
    def test_unknown_api_paths_are_not_swallowed_by_the_app(self) -> None:
        response = self.client.get("/api/does-not-exist")
        self.assertEqual(response.status_code, 404)
