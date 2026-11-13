"""Planning one trip from end to end.

This is the only module that knows the whole story, and it reads like the
steps a dispatcher would take:

1. ask OSRM for up to three route options;
2. drop a checkpoint every N miles along each route;
3. work out when the truck reaches each checkpoint;
4. fetch the forecast for every checkpoint, for all routes at once;
5. score each route and pick the one to recommend.

Step 4 matters for speed: every checkpoint on every route goes into a
single batched weather lookup, so three routes cost one round of requests
rather than three.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from time import perf_counter

from .geo import Checkpoint, Coordinate, rescale_checkpoints, sample_checkpoints
from .heatmap import HeatmapGrid, build_heatmap
from .http_client import Cache
from .planner import (
    RankingCriterion,
    ScoredRoute,
    build_reason,
    deciding_criterion,
    rank_routes,
    score_route,
)
from .routes import RouteOption, checkpoint_eta, get_routes
from .weather import (
    MAX_FORECAST_DAYS,
    WeatherSample,
    fetch_hourly,
    forecast_horizon,
    forecast_window,
)


class PlanningError(ValueError):
    """The trip as asked cannot be planned, and the driver can fix that.

    Unlike ``ExternalServiceError`` this is not an outage: the request needs
    to change, for example to an earlier departure.
    """


@dataclass(frozen=True)
class TripTimings:
    """How long each stage of planning took, in milliseconds.

    Planning a trip is mostly waiting on two external services, so these
    numbers are what to look at when a request feels slow: they say whether
    the routing service or the weather service was responsible.
    """

    routes_ms: float
    weather_ms: float
    scoring_ms: float
    total_ms: float


@dataclass(frozen=True)
class TripPlan:
    """Everything the frontend needs to draw and explain the trip."""

    routes: list[ScoredRoute]
    recommended_index: int
    recommendation_reason: str
    #: Which ranking rule decided it, so the UI can highlight that row.
    deciding_criterion: RankingCriterion
    generated_at: datetime
    timings: TripTimings


def plan_trip(
    origin: Coordinate,
    destination: Coordinate,
    departure: datetime,
    load_lb: float,
    interval_miles: float,
    *,
    cache: Cache | None = None,
    now: datetime | None = None,
) -> TripPlan:
    """Build, score and rank the route options for one trip."""
    moment = now or datetime.now(UTC)
    _check_departure_is_forecastable(departure, moment)

    started = perf_counter()
    routes = get_routes(origin, destination, cache=cache)
    checkpoints_per_route = [
        rescale_checkpoints(
            sample_checkpoints(route.geometry, interval_miles), route.distance_miles
        )
        for route in routes
    ]
    arrivals_per_route = _arrival_times(routes, checkpoints_per_route, departure)
    _check_trip_is_forecastable(arrivals_per_route, moment)

    after_routes = perf_counter()
    samples_per_route = _fetch_weather(
        checkpoints_per_route, arrivals_per_route, departure, moment, cache
    )
    after_weather = perf_counter()

    scored = [
        score_route(route, checkpoints, samples, departure, load_lb)
        for route, checkpoints, samples in zip(
            routes, checkpoints_per_route, samples_per_route, strict=True
        )
    ]

    order = rank_routes(scored)
    best = order[0]
    runner_up = scored[order[1]] if len(order) > 1 else None
    finished = perf_counter()

    return TripPlan(
        routes=scored,
        recommended_index=best,
        recommendation_reason=build_reason(scored[best], runner_up),
        deciding_criterion=deciding_criterion(scored[best], runner_up),
        generated_at=moment,
        timings=TripTimings(
            routes_ms=_ms(started, after_routes),
            weather_ms=_ms(after_routes, after_weather),
            scoring_ms=_ms(after_weather, finished),
            total_ms=_ms(started, finished),
        ),
    )


def _ms(start: float, end: float) -> float:
    """Milliseconds between two ``perf_counter`` readings."""
    return (end - start) * 1000


def _arrival_times(
    routes: Sequence[RouteOption],
    checkpoints_per_route: Sequence[Sequence[Checkpoint]],
    departure: datetime,
) -> list[list[datetime]]:
    """When the truck reaches each checkpoint, route by route."""
    return [
        [
            checkpoint_eta(departure, route.duration_s, checkpoint.mile, route.distance_miles)
            for checkpoint in checkpoints
        ]
        for route, checkpoints in zip(routes, checkpoints_per_route, strict=True)
    ]


def _fetch_weather(
    checkpoints_per_route: Sequence[Sequence[Checkpoint]],
    arrivals_per_route: Sequence[Sequence[datetime]],
    departure: datetime,
    now: datetime,
    cache: Cache | None,
) -> list[list[WeatherSample]]:
    """One batched forecast lookup covering every checkpoint of every route."""
    points = [
        (checkpoint.lon, checkpoint.lat)
        for checkpoints in checkpoints_per_route
        for checkpoint in checkpoints
    ]
    arrivals = [moment for arrivals in arrivals_per_route for moment in arrivals]

    window = forecast_window(departure, max(arrivals), now)
    forecasts = fetch_hourly(points, window[0], window[1], cache=cache)

    # Hand each route back the slice of forecasts belonging to its checkpoints.
    samples_per_route: list[list[WeatherSample]] = []
    position = 0
    for checkpoints in checkpoints_per_route:
        samples = [
            forecasts[position + offset].nearest(arrivals[position + offset])
            for offset in range(len(checkpoints))
        ]
        samples_per_route.append(samples)
        position += len(checkpoints)

    return samples_per_route


def _check_departure_is_forecastable(departure: datetime, now: datetime) -> None:
    """Refuse departures the weather service cannot see yet."""
    if departure > forecast_horizon(now):
        raise PlanningError(
            f"Weather forecasts only reach {MAX_FORECAST_DAYS} days ahead. "
            "Choose a departure time within that window."
        )


def _check_trip_is_forecastable(arrivals_per_route: list[list[datetime]], now: datetime) -> None:
    """Refuse trips that would still be driving after the forecast runs out.

    A departure can be inside the forecast window while the arrival is not.
    Scoring those checkpoints against the last forecast hour would quietly
    use the wrong weather, so the driver is asked to leave earlier instead.
    """
    horizon = forecast_horizon(now)
    latest = max(arrival for arrivals in arrivals_per_route for arrival in arrivals)
    if latest > horizon:
        raise PlanningError(
            "This trip would still be on the road after the weather forecast ends "
            f"({horizon.strftime('%a %d %b, %H:%M')} UTC). Choose an earlier departure."
        )


def trip_heatmap(
    origin: Coordinate,
    destination: Coordinate,
    departure: datetime,
    load_lb: float,
    *,
    cache: Cache | None = None,
    now: datetime | None = None,
) -> HeatmapGrid:
    """The corridor heatmap for a trip that has just been planned.

    This asks OSRM for the routes again rather than having the frontend send
    the shapes back. The routes were cached moments earlier by ``plan_trip``,
    so the lookup is free, and the browser avoids uploading a megabyte of
    geometry it already has.
    """
    moment = now or datetime.now(UTC)
    _check_departure_is_forecastable(departure, moment)
    routes = get_routes(origin, destination, cache=cache)
    return build_heatmap(
        [route.geometry for route in routes],
        departure,
        load_lb,
        horizon=forecast_horizon(moment),
        now=moment,
        cache=cache,
    )
