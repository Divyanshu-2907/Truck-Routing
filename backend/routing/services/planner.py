"""Scoring routes and choosing the one to recommend.

Each checkpoint is scored on its own by ``risk.assess``. This module turns
those per-checkpoint verdicts into a per-route picture, and then picks a
winner.

A checkpoint stands for the stretch of road from itself until the next
checkpoint, so its risk is weighted by those miles. The last checkpoint is
the destination and covers no miles. That is why a 10 mile sampling
interval and a 50 mile one give similar totals: the miles are the same, only
the resolution changes.

Routes are ranked in this order, each criterion only breaking ties left by
the one above it:

0. fewest No Travel miles
1. fewest Severe miles
2. fewest High miles
3. lowest mile-weighted average risk
4. shortest driving time

Criterion 0 is not in the original brief; it was added so that a route the
driver is not allowed to take can never be recommended, even if it is the
quickest. Without it, a route with a short stretch of 60 mph wind could win
on travel time alone.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

from .geo import Checkpoint
from .risk import RiskLevel, assess
from .routes import RouteOption, checkpoint_eta
from .weather import WeatherSample

#: Which rule separated the winner from the runner-up. ``tie`` means every
#: criterion matched; ``only_route`` means there was nothing to compare.
RankingCriterion = Literal[
    "no_travel", "severe", "high", "average_risk", "duration", "tie", "only_route"
]

#: The three mileage criteria, in ranking order, with their wording.
MILEAGE_CRITERIA: tuple[tuple[RiskLevel, RankingCriterion, str], ...] = (
    (RiskLevel.NO_TRAVEL, "no_travel", "no-travel"),
    (RiskLevel.SEVERE, "severe", "severe"),
    (RiskLevel.HIGH, "high", "high-risk"),
)

#: Differences smaller than these count as "the same" when explaining a
#: choice, so the reason given is the criterion that genuinely separated
#: the routes rather than a rounding artefact.
MILES_TOLERANCE = 0.5
AVERAGE_RISK_TOLERANCE = 0.01
DURATION_TOLERANCE_SECONDS = 60.0


@dataclass(frozen=True)
class CheckpointRisk:
    """One scored checkpoint: where, when, what the weather is, and how risky."""

    mile: float
    lat: float
    lon: float
    eta: datetime
    covered_miles: float
    wind_mph: float
    rain_in: float
    snow_in: float
    level: RiskLevel
    reason: str


@dataclass(frozen=True)
class RouteSummary:
    """The whole-route picture used for ranking and for the sidebar."""

    distance_miles: float
    duration_s: float
    miles_by_level: dict[RiskLevel, float]
    checkpoints_by_level: dict[RiskLevel, int]
    average_risk: float
    max_level: RiskLevel

    def miles_at(self, level: RiskLevel) -> float:
        """Miles spent at one risk level, or 0.0 if the route never hit it."""
        return self.miles_by_level.get(level, 0.0)


@dataclass(frozen=True)
class ScoredRoute:
    """A route together with its scored checkpoints and its summary."""

    route: RouteOption
    checkpoints: list[CheckpointRisk]
    summary: RouteSummary


def score_route(
    route: RouteOption,
    checkpoints: Sequence[Checkpoint],
    samples: Sequence[WeatherSample],
    departure: datetime,
    load_lb: float,
) -> ScoredRoute:
    """Score every checkpoint on a route and summarise the result.

    ``samples`` is the forecast for each checkpoint at its own arrival time,
    in the same order as ``checkpoints``.
    """
    if len(checkpoints) != len(samples):
        raise ValueError("Every checkpoint needs exactly one weather sample.")

    total_miles = route.distance_miles
    scored: list[CheckpointRisk] = []

    for index, (checkpoint, sample) in enumerate(zip(checkpoints, samples, strict=False)):
        is_last = index == len(checkpoints) - 1
        covered = 0.0 if is_last else checkpoints[index + 1].mile - checkpoint.mile
        verdict = assess(sample.wind_mph, sample.rain_in, sample.snow_in, load_lb)

        scored.append(
            CheckpointRisk(
                mile=checkpoint.mile,
                lat=checkpoint.lat,
                lon=checkpoint.lon,
                eta=checkpoint_eta(departure, route.duration_s, checkpoint.mile, total_miles),
                covered_miles=covered,
                wind_mph=sample.wind_mph,
                rain_in=sample.rain_in,
                snow_in=sample.snow_in,
                level=verdict.level,
                reason=verdict.reason,
            )
        )

    return ScoredRoute(route=route, checkpoints=scored, summary=summarise(route, scored))


def summarise(route: RouteOption, checkpoints: Sequence[CheckpointRisk]) -> RouteSummary:
    """Add the checkpoints up into miles per risk level and an average risk."""
    miles_by_level = {level: 0.0 for level in RiskLevel}
    checkpoints_by_level = {level: 0 for level in RiskLevel}
    weighted_total = 0.0
    covered_total = 0.0

    for checkpoint in checkpoints:
        miles_by_level[checkpoint.level] += checkpoint.covered_miles
        checkpoints_by_level[checkpoint.level] += 1
        weighted_total += int(checkpoint.level) * checkpoint.covered_miles
        covered_total += checkpoint.covered_miles

    average_risk = weighted_total / covered_total if covered_total > 0 else 0.0
    max_level = max((checkpoint.level for checkpoint in checkpoints), default=RiskLevel.LOW)

    return RouteSummary(
        distance_miles=route.distance_miles,
        duration_s=route.duration_s,
        miles_by_level=miles_by_level,
        checkpoints_by_level=checkpoints_by_level,
        average_risk=average_risk,
        max_level=max_level,
    )


def rank_routes(scored: Sequence[ScoredRoute]) -> list[int]:
    """Positions of the routes, best first, using the ranking order above.

    Indexes are returned rather than routes so the caller can keep showing
    the routes in their original A, B, C order while still knowing which
    one is recommended.
    """
    return sorted(range(len(scored)), key=lambda index: _ranking_key(scored[index]))


def _ranking_key(scored: ScoredRoute) -> tuple[float, float, float, float, float]:
    """The sort key that puts the safest route first; ties fall through to time."""
    summary = scored.summary
    return (
        summary.miles_at(RiskLevel.NO_TRAVEL),
        summary.miles_at(RiskLevel.SEVERE),
        summary.miles_at(RiskLevel.HIGH),
        summary.average_risk,
        summary.duration_s,
    )


def deciding_criterion(winner: ScoredRoute, runner_up: ScoredRoute | None) -> RankingCriterion:
    """The first ranking rule on which the winner actually beat the runner-up.

    The ranking walks the criteria in order, so the first one with a real
    difference is the one that decided the recommendation. Everything below
    it never came into play.
    """
    if runner_up is None:
        return "only_route"

    best = winner.summary
    other = runner_up.summary

    for level, criterion, _wording in MILEAGE_CRITERIA:
        if _differ(best.miles_at(level), other.miles_at(level), MILES_TOLERANCE):
            return criterion

    if _differ(best.average_risk, other.average_risk, AVERAGE_RISK_TOLERANCE):
        return "average_risk"
    if _differ(best.duration_s, other.duration_s, DURATION_TOLERANCE_SECONDS):
        return "duration"
    return "tie"


def build_reason(winner: ScoredRoute, runner_up: ScoredRoute | None) -> str:
    """Explain the recommendation using the criterion that separated the routes."""
    criterion = deciding_criterion(winner, runner_up)
    if runner_up is None:
        return f"{winner.route.label} is the only route available for this trip."

    best = winner.summary
    other = runner_up.summary
    names = (winner.route.label, runner_up.route.label)

    for level, mileage_criterion, wording in MILEAGE_CRITERIA:
        if criterion == mileage_criterion:
            return _miles_reason(names, wording, best.miles_at(level), other.miles_at(level))

    if criterion == "average_risk":
        return (
            f"{names[0]} and {names[1]} have the same severe and high-risk mileage, "
            f"but {names[0]} has a lower average risk along the way "
            f"({best.average_risk:.2f} vs {other.average_risk:.2f})."
        )

    if criterion == "duration":
        return (
            f"All routes are equally safe, so {names[0]} wins on time: "
            f"{format_duration(best.duration_s)} vs {format_duration(other.duration_s)}."
        )

    return (
        f"{names[0]} and {names[1]} are equally safe and take the same time; "
        f"{names[0]} is recommended as the first of them."
    )


def _miles_reason(
    names: tuple[str, str], wording: str, winner_miles: float, runner_up_miles: float
) -> str:
    """Wording for the three mileage criteria, including the happy 'none at all' case."""
    if winner_miles < MILES_TOLERANCE:
        return (
            f"{names[0]} avoids {wording} conditions entirely, while "
            f"{names[1]} has {runner_up_miles:,.0f} miles of them."
        )
    return (
        f"{names[0]} has {winner_miles:,.0f} {wording} miles "
        f"vs {runner_up_miles:,.0f} on {names[1]}."
    )


def format_duration(seconds: float) -> str:
    """Driving time as the driver would say it: ``9h 10m``."""
    total_minutes = int(round(seconds / 60))
    return f"{total_minutes // 60}h {total_minutes % 60:02d}m"


def _differ(first: float, second: float, tolerance: float) -> bool:
    return abs(first - second) >= tolerance
