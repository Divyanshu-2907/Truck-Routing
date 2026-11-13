"""Tests for route scoring, ranking and the recommendation wording.

Routes here are made up rather than fetched, so each test can set up one
precise situation: two routes identical except for the thing being tested.
That is the only way to prove each ranking criterion is really used, and
used in the right order.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta

from routing.services.geo import Checkpoint
from routing.services.planner import (
    RouteSummary,
    ScoredRoute,
    build_reason,
    deciding_criterion,
    format_duration,
    rank_routes,
    score_route,
)
from routing.services.risk import RiskLevel
from routing.services.routes import RouteOption
from routing.services.weather import WeatherSample

DEPARTURE = datetime(2026, 1, 2, 6, 0, tzinfo=UTC)
LIGHT_LOAD = 10_000.0

CALM = WeatherSample(time=DEPARTURE, wind_mph=5.0, rain_in=0.0, snow_in=0.0)
MODERATE_WIND = WeatherSample(time=DEPARTURE, wind_mph=28.0, rain_in=0.0, snow_in=0.0)
HIGH_WIND = WeatherSample(time=DEPARTURE, wind_mph=38.0, rain_in=0.0, snow_in=0.0)
SEVERE_WIND = WeatherSample(time=DEPARTURE, wind_mph=48.0, rain_in=0.0, snow_in=0.0)
NO_TRAVEL_WIND = WeatherSample(time=DEPARTURE, wind_mph=60.0, rain_in=0.0, snow_in=0.0)


def fake_route(label: str, miles: float = 100.0, hours: float = 2.0) -> RouteOption:
    """A route with a straight two-point shape; only its numbers matter here."""
    return RouteOption(
        label=label,
        distance_miles=miles,
        duration_s=hours * 3600,
        geometry=[(-96.8, 32.8), (-97.8, 33.8)],
        source="osrm-alternative",
    )


def even_checkpoints(miles: float, count: int) -> list[Checkpoint]:
    """``count`` checkpoints spread evenly from mile 0 to the destination."""
    step = miles / (count - 1)
    return [Checkpoint(mile=step * index, lat=32.8, lon=-96.8) for index in range(count)]


def build_route(
    label: str,
    samples: list[WeatherSample],
    miles: float = 100.0,
    hours: float = 2.0,
    load_lb: float = LIGHT_LOAD,
) -> ScoredRoute:
    """Score a made-up route whose checkpoints have exactly these forecasts."""
    route = fake_route(label, miles, hours)
    checkpoints = even_checkpoints(miles, len(samples))
    return score_route(route, checkpoints, samples, DEPARTURE, load_lb)


class CoveredMilesTests(unittest.TestCase):
    """Each checkpoint owns the road until the next one; the last owns none."""

    def test_covered_miles_split_the_route(self) -> None:
        scored = build_route("Route A", [CALM] * 5)  # 0, 25, 50, 75, 100
        covered = [point.covered_miles for point in scored.checkpoints]

        self.assertEqual(covered, [25.0, 25.0, 25.0, 25.0, 0.0])
        self.assertAlmostEqual(sum(covered), 100.0, places=6)

    def test_miles_are_credited_to_the_right_level(self) -> None:
        scored = build_route("Route A", [CALM, SEVERE_WIND, CALM, CALM, CALM])
        summary = scored.summary

        self.assertAlmostEqual(summary.miles_at(RiskLevel.SEVERE), 25.0, places=6)
        self.assertAlmostEqual(summary.miles_at(RiskLevel.LOW), 75.0, places=6)

    def test_a_last_checkpoint_storm_adds_no_miles(self) -> None:
        scored = build_route("Route A", [CALM, CALM, CALM, CALM, NO_TRAVEL_WIND])

        self.assertAlmostEqual(scored.summary.miles_at(RiskLevel.NO_TRAVEL), 0.0, places=6)
        self.assertEqual(scored.summary.checkpoints_by_level[RiskLevel.NO_TRAVEL], 1)
        # It still counts as the worst weather seen on the route.
        self.assertEqual(scored.summary.max_level, RiskLevel.NO_TRAVEL)

    def test_checkpoint_counts_per_level(self) -> None:
        scored = build_route("Route A", [CALM, HIGH_WIND, HIGH_WIND, SEVERE_WIND, CALM])
        counts = scored.summary.checkpoints_by_level

        self.assertEqual(counts[RiskLevel.LOW], 2)
        self.assertEqual(counts[RiskLevel.HIGH], 2)
        self.assertEqual(counts[RiskLevel.SEVERE], 1)


class AverageRiskTests(unittest.TestCase):
    """Average risk is weighted by miles, not by number of checkpoints."""

    def test_all_calm_is_zero(self) -> None:
        self.assertEqual(build_route("Route A", [CALM] * 5).summary.average_risk, 0.0)

    def test_half_moderate_is_half_a_point(self) -> None:
        scored = build_route("Route A", [MODERATE_WIND, MODERATE_WIND, CALM, CALM, CALM])
        # 50 miles at Moderate (1), 50 at Low (0) -> 0.5
        self.assertAlmostEqual(scored.summary.average_risk, 0.5, places=6)

    def test_weighting_follows_the_miles(self) -> None:
        route = fake_route("Route A", miles=100.0)
        # The first checkpoint covers 90 miles, the second only 10.
        checkpoints = [
            Checkpoint(mile=0.0, lat=32.8, lon=-96.8),
            Checkpoint(mile=90.0, lat=32.8, lon=-96.8),
            Checkpoint(mile=100.0, lat=32.8, lon=-96.8),
        ]
        scored = score_route(route, checkpoints, [CALM, SEVERE_WIND, CALM], DEPARTURE, LIGHT_LOAD)
        # 90 miles at Low (0) and 10 at Severe (3) -> 0.3
        self.assertAlmostEqual(scored.summary.average_risk, 0.3, places=6)


class EtaTests(unittest.TestCase):
    def test_checkpoint_etas_follow_the_route_duration(self) -> None:
        scored = build_route("Route A", [CALM] * 5, miles=100.0, hours=4.0)
        etas = [point.eta for point in scored.checkpoints]

        self.assertEqual(etas[0], DEPARTURE)
        self.assertEqual(etas[2], DEPARTURE + timedelta(hours=2))
        self.assertEqual(etas[-1], DEPARTURE + timedelta(hours=4))


class RankingOrderTests(unittest.TestCase):
    """Each criterion is only reached when the ones above it are tied."""

    def test_fewest_severe_miles_wins(self) -> None:
        risky = build_route("Route A", [SEVERE_WIND, CALM, CALM, CALM, CALM], hours=1.0)
        safe = build_route("Route B", [CALM] * 5, hours=9.0)

        # Route A is eight hours quicker and still loses.
        self.assertEqual(rank_routes([risky, safe]), [1, 0])

    def test_severe_miles_outrank_high_miles(self) -> None:
        some_severe = build_route("Route A", [SEVERE_WIND, CALM, CALM, CALM, CALM])
        lots_of_high = build_route("Route B", [HIGH_WIND] * 4 + [CALM])

        self.assertEqual(rank_routes([some_severe, lots_of_high]), [1, 0])

    def test_fewest_high_miles_wins_when_severe_is_tied(self) -> None:
        more_high = build_route("Route A", [HIGH_WIND, HIGH_WIND, CALM, CALM, CALM], hours=1.0)
        less_high = build_route("Route B", [HIGH_WIND, CALM, CALM, CALM, CALM], hours=9.0)

        self.assertEqual(rank_routes([more_high, less_high]), [1, 0])

    def test_average_risk_breaks_a_tie_on_severe_and_high(self) -> None:
        # Neither route has Severe or High miles, so the moderate stretches decide.
        windier = build_route("Route A", [MODERATE_WIND] * 4 + [CALM], hours=1.0)
        calmer = build_route("Route B", [MODERATE_WIND, CALM, CALM, CALM, CALM], hours=9.0)

        self.assertEqual(rank_routes([windier, calmer]), [1, 0])

    def test_time_breaks_a_tie_on_risk(self) -> None:
        slow = build_route("Route A", [CALM] * 5, hours=9.75)
        quick = build_route("Route B", [CALM] * 5, hours=9.17)

        self.assertEqual(rank_routes([slow, quick]), [1, 0])

    def test_identical_routes_keep_their_original_order(self) -> None:
        first = build_route("Route A", [CALM] * 5)
        second = build_route("Route B", [CALM] * 5)

        self.assertEqual(rank_routes([first, second]), [0, 1])


class NoTravelTests(unittest.TestCase):
    """A route the driver is not allowed to take must never be recommended."""

    def test_no_travel_route_loses_to_a_severe_one(self) -> None:
        blocked = build_route("Route A", [NO_TRAVEL_WIND, CALM, CALM, CALM, CALM], hours=1.0)
        severe = build_route("Route B", [SEVERE_WIND] * 4 + [CALM], hours=12.0)

        self.assertEqual(rank_routes([blocked, severe]), [1, 0])

    def test_no_travel_route_loses_however_quick_it_is(self) -> None:
        blocked = build_route("Route A", [NO_TRAVEL_WIND, CALM, CALM, CALM, CALM], hours=0.5)
        usable = build_route("Route B", [HIGH_WIND] * 4 + [CALM], hours=20.0)

        self.assertEqual(rank_routes([blocked, usable]), [1, 0])

    def test_the_least_blocked_route_wins_when_all_are_blocked(self) -> None:
        worse = build_route("Route A", [NO_TRAVEL_WIND, NO_TRAVEL_WIND, CALM, CALM, CALM])
        better = build_route("Route B", [NO_TRAVEL_WIND, CALM, CALM, CALM, CALM])

        self.assertEqual(rank_routes([worse, better]), [1, 0])


class LoadRuleIntegrationTests(unittest.TestCase):
    """The load weight reaches the scoring, not just the single-checkpoint rules."""

    def test_a_heavy_load_turns_severe_wind_into_no_travel_miles(self) -> None:
        light = build_route("Route A", [SEVERE_WIND, CALM, CALM, CALM, CALM], load_lb=20_000)
        heavy = build_route("Route B", [SEVERE_WIND, CALM, CALM, CALM, CALM], load_lb=45_000)

        self.assertAlmostEqual(light.summary.miles_at(RiskLevel.SEVERE), 25.0, places=6)
        self.assertAlmostEqual(light.summary.miles_at(RiskLevel.NO_TRAVEL), 0.0, places=6)
        self.assertAlmostEqual(heavy.summary.miles_at(RiskLevel.NO_TRAVEL), 25.0, places=6)


class ReasonTextTests(unittest.TestCase):
    """The explanation names the first criterion that actually separated them."""

    def test_no_travel_is_mentioned_first(self) -> None:
        winner = build_route("Route B", [SEVERE_WIND] * 4 + [CALM])
        loser = build_route("Route A", [NO_TRAVEL_WIND] * 2 + [CALM] * 3)

        reason = build_reason(winner, loser)
        self.assertIn("no-travel", reason)
        self.assertIn("Route B avoids", reason)
        self.assertIn("50 miles", reason)

    def test_severe_miles_are_quoted_for_both_routes(self) -> None:
        winner = build_route("Route B", [CALM] * 5)
        loser = build_route("Route A", [SEVERE_WIND, SEVERE_WIND, CALM, CALM, CALM])

        reason = build_reason(winner, loser)
        self.assertIn("severe", reason)
        self.assertIn("50 miles", reason)
        self.assertIn("Route A", reason)

    def test_high_miles_are_used_when_severe_is_tied(self) -> None:
        winner = build_route("Route B", [HIGH_WIND, CALM, CALM, CALM, CALM])
        loser = build_route("Route A", [HIGH_WIND] * 3 + [CALM] * 2)

        reason = build_reason(winner, loser)
        self.assertIn("high-risk", reason)
        self.assertIn("25 high-risk miles", reason)
        self.assertIn("75 on Route A", reason)

    def test_average_risk_is_used_when_the_mileages_tie(self) -> None:
        winner = build_route("Route B", [MODERATE_WIND, CALM, CALM, CALM, CALM])
        loser = build_route("Route A", [MODERATE_WIND] * 4 + [CALM])

        reason = build_reason(winner, loser)
        self.assertIn("average risk", reason)
        self.assertIn("0.25", reason)
        self.assertIn("1.00", reason)

    def test_time_is_used_when_everything_else_ties(self) -> None:
        winner = build_route("Route A", [CALM] * 5, hours=9.17)
        loser = build_route("Route B", [CALM] * 5, hours=9.75)

        reason = build_reason(winner, loser)
        self.assertEqual(
            reason,
            "All routes are equally safe, so Route A wins on time: 9h 10m vs 9h 45m.",
        )

    def test_a_dead_heat_is_explained_honestly(self) -> None:
        winner = build_route("Route A", [CALM] * 5, hours=4.0)
        loser = build_route("Route B", [CALM] * 5, hours=4.0)

        self.assertIn("equally safe and take the same time", build_reason(winner, loser))

    def test_a_single_route_says_so(self) -> None:
        only = build_route("Route A", [CALM] * 5)
        self.assertEqual(
            build_reason(only, None), "Route A is the only route available for this trip."
        )


class FormatDurationTests(unittest.TestCase):
    def test_formats_hours_and_minutes(self) -> None:
        self.assertEqual(format_duration(9 * 3600 + 10 * 60), "9h 10m")
        self.assertEqual(format_duration(3600), "1h 00m")
        self.assertEqual(format_duration(0), "0h 00m")
        self.assertEqual(format_duration(59), "0h 01m")


class SummaryTests(unittest.TestCase):
    def test_miles_at_defaults_to_zero_for_unseen_levels(self) -> None:
        summary = RouteSummary(
            distance_miles=10.0,
            duration_s=600.0,
            miles_by_level={},
            checkpoints_by_level={},
            average_risk=0.0,
            max_level=RiskLevel.LOW,
        )
        self.assertEqual(summary.miles_at(RiskLevel.SEVERE), 0.0)


class ScoreRouteValidationTests(unittest.TestCase):
    def test_mismatched_samples_are_rejected(self) -> None:
        route = fake_route("Route A")
        with self.assertRaises(ValueError):
            score_route(route, even_checkpoints(100.0, 5), [CALM], DEPARTURE, LIGHT_LOAD)


class DecidingCriterionTests(unittest.TestCase):
    """The UI highlights this row, so it must match the reason wording."""

    def test_no_travel_comes_first(self) -> None:
        winner = build_route("Route B", [SEVERE_WIND] * 4 + [CALM])
        loser = build_route("Route A", [NO_TRAVEL_WIND] * 2 + [CALM] * 3)

        self.assertEqual(deciding_criterion(winner, loser), "no_travel")

    def test_severe_then_high(self) -> None:
        winner = build_route("Route B", [CALM] * 5)
        loser = build_route("Route A", [SEVERE_WIND, CALM, CALM, CALM, CALM])
        self.assertEqual(deciding_criterion(winner, loser), "severe")

        winner = build_route("Route B", [HIGH_WIND, CALM, CALM, CALM, CALM])
        loser = build_route("Route A", [HIGH_WIND] * 3 + [CALM] * 2)
        self.assertEqual(deciding_criterion(winner, loser), "high")

    def test_average_risk_then_duration(self) -> None:
        winner = build_route("Route B", [MODERATE_WIND, CALM, CALM, CALM, CALM])
        loser = build_route("Route A", [MODERATE_WIND] * 4 + [CALM])
        self.assertEqual(deciding_criterion(winner, loser), "average_risk")

        winner = build_route("Route A", [CALM] * 5, hours=9.17)
        loser = build_route("Route B", [CALM] * 5, hours=9.75)
        self.assertEqual(deciding_criterion(winner, loser), "duration")

    def test_a_dead_heat_and_a_lone_route(self) -> None:
        first = build_route("Route A", [CALM] * 5, hours=4.0)
        second = build_route("Route B", [CALM] * 5, hours=4.0)

        self.assertEqual(deciding_criterion(first, second), "tie")
        self.assertEqual(deciding_criterion(first, None), "only_route")

    def test_it_agrees_with_the_reason_sentence(self) -> None:
        winner = build_route("Route B", [CALM] * 5)
        loser = build_route("Route A", [SEVERE_WIND, SEVERE_WIND, CALM, CALM, CALM])

        self.assertEqual(deciding_criterion(winner, loser), "severe")
        self.assertIn("severe", build_reason(winner, loser))
