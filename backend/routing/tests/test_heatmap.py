"""Tests for the corridor heatmap grid.

The grid is what the 48 hour slider scrubs through, so the shape of the
result matters as much as the numbers in it: 49 rows, one value per point
in every row, and the same point order throughout.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta, timezone
from typing import Any
from unittest.mock import patch

from routing.services import heatmap as heatmap_module
from routing.services.geo import Coordinate, haversine_miles, point_at_bearing
from routing.services.heatmap import (
    CORRIDOR_OFFSET_MILES,
    FORECAST_HOURS,
    build_heatmap,
    corridor_points,
)
from routing.services.weather import HourlyForecast

DEPARTURE = datetime(2026, 1, 2, 6, 30, tzinfo=UTC)
DALLAS: Coordinate = (-96.7970, 32.7767)


def north_line(total_miles: float, steps: int = 20) -> list[Coordinate]:
    """A route heading due north out of Dallas, of an exact length."""
    return [point_at_bearing(DALLAS, 0.0, total_miles * step / steps) for step in range(steps + 1)]


def forecast_of(
    wind_mph: float, hours: int = 60, rain_in: float = 0.0, snow_in: float = 0.0
) -> HourlyForecast:
    """A flat forecast, so any hour of the grid has the same weather."""
    start = DEPARTURE.replace(minute=0)
    times = tuple(start + timedelta(hours=offset) for offset in range(hours))
    return HourlyForecast(
        times=times,
        wind_mph=tuple(wind_mph for _ in times),
        rain_in=tuple(rain_in for _ in times),
        snow_in=tuple(snow_in for _ in times),
    )


class CorridorPointsTests(unittest.TestCase):
    def test_every_sample_has_a_left_and_a_right_point(self) -> None:
        # 100 miles sampled every 25 gives 5 samples, each with 2 neighbours.
        points = corridor_points([north_line(100.0)])
        self.assertEqual(len(points), 15)

    def test_side_points_sit_beside_the_road(self) -> None:
        points = corridor_points([north_line(100.0)])
        centre, left, right = points[0], points[1], points[2]

        self.assertAlmostEqual(haversine_miles(centre, left), CORRIDOR_OFFSET_MILES, delta=1.0)
        self.assertAlmostEqual(haversine_miles(centre, right), CORRIDOR_OFFSET_MILES, delta=1.0)
        # A route heading north has its neighbours to the west and the east.
        self.assertLess(left[0], centre[0])
        self.assertGreater(right[0], centre[0])

    def test_routes_that_run_together_share_points(self) -> None:
        line = north_line(100.0)
        one_route = corridor_points([line])
        same_route_twice = corridor_points([line, line])

        self.assertEqual(one_route, same_route_twice)

    def test_the_grid_is_capped(self) -> None:
        # A 3,000 mile route would otherwise produce 360 points per route.
        points = corridor_points([north_line(3_000.0, steps=400)] * 3, max_points=50)
        self.assertEqual(len(points), 50)

    def test_a_capped_grid_still_spans_the_whole_route(self) -> None:
        line = north_line(1_000.0, steps=200)
        capped = corridor_points([line], max_points=20)

        northernmost = max(lat for _, lat in capped)
        self.assertGreater(northernmost - DALLAS[1], 10.0)

    def test_empty_and_degenerate_lines_are_ignored(self) -> None:
        self.assertEqual(corridor_points([]), [])
        self.assertEqual(corridor_points([[DALLAS]]), [])


class BuildHeatmapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.line = north_line(100.0)

    def build(self, wind_mph: float, load_lb: float) -> Any:
        def fake_fetch(points, start, end, cache=None):
            return [forecast_of(wind_mph) for _ in points]

        with patch.object(heatmap_module, "fetch_hourly", fake_fetch):
            return build_heatmap([self.line], DEPARTURE, load_lb)

    def test_grid_has_one_row_per_hour_including_the_departure_hour(self) -> None:
        grid = self.build(wind_mph=5.0, load_lb=10_000)

        self.assertEqual(len(grid.times), FORECAST_HOURS + 1)
        self.assertEqual(len(grid.values), FORECAST_HOURS + 1)

    def test_every_row_has_one_value_per_point(self) -> None:
        grid = self.build(wind_mph=5.0, load_lb=10_000)

        for row in grid.values:
            self.assertEqual(len(row), len(grid.points))

    def test_frame_zero_is_the_departure_to_the_minute(self) -> None:
        # DEPARTURE is 06:30, so flooring to the hour would show 06:00.
        grid = self.build(wind_mph=5.0, load_lb=10_000)

        self.assertEqual(grid.times[0], DEPARTURE)
        self.assertEqual(grid.times[1] - grid.times[0], timedelta(hours=1))
        self.assertEqual(grid.times[-1] - grid.times[0], timedelta(hours=FORECAST_HOURS))

    def test_frame_zero_is_the_departure_in_any_timezone(self) -> None:
        # 12:00 in India is 06:30 UTC: the same instant as DEPARTURE.
        india = timezone(timedelta(hours=5, minutes=30))

        def fake_fetch(points, start, end, cache=None):
            return [forecast_of(5.0) for _ in points]

        with patch.object(heatmap_module, "fetch_hourly", fake_fetch):
            grid = build_heatmap([self.line], DEPARTURE.astimezone(india), 10_000)

        self.assertEqual(grid.times[0], DEPARTURE)

    def test_frames_past_the_forecast_horizon_are_left_out(self) -> None:
        horizon = DEPARTURE + timedelta(hours=10, minutes=15)

        def fake_fetch(points, start, end, cache=None):
            return [forecast_of(5.0) for _ in points]

        with patch.object(heatmap_module, "fetch_hourly", fake_fetch):
            grid = build_heatmap([self.line], DEPARTURE, 10_000, horizon=horizon)

        self.assertEqual(len(grid.times), 11)  # +0h to +10h
        self.assertLessEqual(grid.times[-1], horizon)
        self.assertEqual(len(grid.values), 11)

    def test_calm_weather_scores_zero_everywhere(self) -> None:
        grid = self.build(wind_mph=5.0, load_lb=10_000)
        self.assertEqual(set(grid.values[0]), {0})

    def test_values_are_risk_levels(self) -> None:
        grid = self.build(wind_mph=38.0, load_lb=10_000)
        self.assertEqual(set(grid.values[0]), {2})  # High

    def test_the_load_weight_is_applied_to_the_grid(self) -> None:
        light = self.build(wind_mph=48.0, load_lb=20_000)
        heavy = self.build(wind_mph=48.0, load_lb=45_000)

        self.assertEqual(set(light.values[0]), {3})  # Severe
        self.assertEqual(set(heavy.values[0]), {4})  # No Travel

    def test_one_weather_lookup_covers_every_hour(self) -> None:
        calls: list[int] = []

        def counting_fetch(points, start, end, cache=None):
            calls.append(len(points))
            return [forecast_of(5.0) for _ in points]

        with patch.object(heatmap_module, "fetch_hourly", counting_fetch):
            build_heatmap([self.line], DEPARTURE, 10_000)

        self.assertEqual(len(calls), 1)

    def test_a_trip_with_no_geometry_still_returns_a_usable_grid(self) -> None:
        grid = build_heatmap([], DEPARTURE, 10_000)

        self.assertEqual(grid.points, [])
        self.assertEqual(len(grid.values), FORECAST_HOURS + 1)
        self.assertEqual(grid.values[0], [])


class RawReadingTests(unittest.TestCase):
    """The raw weather travels with the risk, as whole numbers."""

    def setUp(self) -> None:
        self.line = north_line(100.0)

    def build(self, wind_mph: float, rain_in: float, snow_in: float) -> Any:
        def fake_fetch(points, start, end, cache=None):
            return [forecast_of(wind_mph, rain_in=rain_in, snow_in=snow_in) for _ in points]

        with patch.object(heatmap_module, "fetch_hourly", fake_fetch):
            return build_heatmap([self.line], DEPARTURE, 10_000)

    def test_every_grid_has_the_same_shape_as_the_risk_grid(self) -> None:
        grid = self.build(12.0, 0.2, 0.4)

        for readings in (grid.wind, grid.rain, grid.snow):
            self.assertEqual(len(readings), len(grid.values))
            self.assertEqual(len(readings[0]), len(grid.points))

    def test_wind_is_whole_miles_per_hour(self) -> None:
        self.assertEqual(set(self.build(12.4, 0.0, 0.0).wind[0]), {12})
        self.assertEqual(set(self.build(12.6, 0.0, 0.0).wind[0]), {13})

    def test_rain_is_hundredths_of_an_inch(self) -> None:
        self.assertEqual(set(self.build(0.0, 0.25, 0.0).rain[0]), {25})
        self.assertEqual(set(self.build(0.0, 1.0, 0.0).rain[0]), {100})

    def test_snow_is_tenths_of_an_inch(self) -> None:
        self.assertEqual(set(self.build(0.0, 0.0, 1.5).snow[0]), {15})
        self.assertEqual(set(self.build(0.0, 0.0, 3.0).snow[0]), {30})

    def test_the_readings_match_the_risk_they_produced(self) -> None:
        # 48 mph with a light load is Severe; the raw wind says why.
        grid = self.build(48.0, 0.0, 0.0)

        self.assertEqual(set(grid.values[0]), {3})
        self.assertEqual(set(grid.wind[0]), {48})

    def test_a_trip_with_no_geometry_returns_empty_grids(self) -> None:
        grid = build_heatmap([], DEPARTURE, 10_000)

        self.assertEqual(grid.wind[0], [])
        self.assertEqual(grid.rain[0], [])
        self.assertEqual(grid.snow[0], [])
