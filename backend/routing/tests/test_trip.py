"""Tests for the end-to-end planning pipeline, with the network replaced."""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

from routing.services import trip as trip_module
from routing.services.trip import PlanningError, plan_trip
from routing.tests.fakes import DALLAS, calm_weather, fake_routes

DESTINATION = (-96.797, 34.2)
NOW = datetime(2026, 1, 1, 10, 0, tzinfo=UTC)


def run_plan(departure: datetime, interval: float = 25):
    with (
        patch.object(trip_module, "get_routes", fake_routes),
        patch.object(trip_module, "fetch_hourly", calm_weather),
    ):
        return plan_trip(DALLAS, DESTINATION, departure, 20_000, interval, now=NOW)


class CheckpointScaleTests(unittest.TestCase):
    """Every figure the driver sees agrees with the route's reported distance."""

    def test_last_checkpoint_is_at_the_reported_distance(self) -> None:
        plan = run_plan(NOW + timedelta(hours=2))
        last = plan.routes[0].checkpoints[-1]

        self.assertAlmostEqual(last.mile, 101.0, places=6)

    def test_covered_miles_add_up_to_the_reported_distance(self) -> None:
        plan = run_plan(NOW + timedelta(hours=2))
        covered = sum(point.covered_miles for point in plan.routes[0].checkpoints)

        self.assertAlmostEqual(covered, 101.0, places=6)

    def test_arrival_is_departure_plus_driving_time(self) -> None:
        departure = NOW + timedelta(hours=2)
        plan = run_plan(departure)

        self.assertEqual(plan.routes[0].checkpoints[-1].eta, departure + timedelta(hours=2))
        self.assertEqual(plan.routes[1].checkpoints[-1].eta, departure + timedelta(hours=3))


class ForecastHorizonTests(unittest.TestCase):
    """A trip must finish inside the forecast, not just start inside it."""

    def test_arrival_after_the_forecast_ends_is_refused_clearly(self) -> None:
        # The forecast asked for at NOW runs to 23:00 on 16 Jan. Leaving at
        # 21:30 on the 16th, the three-hour route arrives after that.
        departure = datetime(2026, 1, 16, 21, 30, tzinfo=UTC)

        with self.assertRaises(PlanningError) as caught:
            run_plan(departure)

        self.assertIn("earlier departure", str(caught.exception))

    def test_a_trip_that_finishes_in_time_is_planned(self) -> None:
        departure = datetime(2026, 1, 16, 18, 0, tzinfo=UTC)

        plan = run_plan(departure)

        self.assertEqual(len(plan.routes), 2)

    def test_departure_after_the_forecast_ends_is_refused(self) -> None:
        with self.assertRaises(PlanningError):
            run_plan(datetime(2026, 1, 17, 1, 0, tzinfo=UTC))


class RecommendationTests(unittest.TestCase):
    def test_equal_weather_recommends_the_quicker_route(self) -> None:
        plan = run_plan(NOW + timedelta(hours=2))

        self.assertEqual(plan.routes[plan.recommended_index].route.label, "Route A")
        self.assertEqual(plan.deciding_criterion, "duration")


if __name__ == "__main__":
    unittest.main()
