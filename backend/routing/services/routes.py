"""Getting route options between two points from OSRM.

OSRM is asked for alternative routes, but on many trips it only finds one
sensible way to drive. When that happens this module builds its own
alternatives: it takes the middle of the main route, pushes a waypoint out
sideways (left and right), and asks OSRM to route through that waypoint.
That produces genuinely different corridors, which is the whole point -
three routes down the same road would all have the same weather.

Routes that end up too similar to one we already have are thrown away, so
the app never shows the same road twice under two different names.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal

from .geo import (
    Coordinate,
    cumulative_miles,
    initial_bearing,
    interpolate_point,
    point_at_bearing,
)
from .http_client import (
    DEFAULT_RETRIES,
    Cache,
    ExternalServiceError,
    fetch_json,
    make_cache_key,
)

OSRM_BASE_URL = "https://router.project-osrm.org"

SERVICE_NAME = "The routing service"

#: OSRM responses are cached for half an hour; roads do not move.
ROUTE_CACHE_SECONDS = 30 * 60

#: Labels handed out to the routes, in the order they are kept.
ROUTE_LABELS = ("Route A", "Route B", "Route C")

MAX_ROUTES = 3

METERS_PER_MILE = 1609.344

#: How far sideways a detour waypoint is pushed, as a share of trip length.
#: The offset scales with the trip so a detour stays in proportion: a fixed
#: minimum of 20 miles turned a 32 mile trip's detour into a 65 mile one.
DETOUR_OFFSET_FRACTION = 0.10

#: The offset is kept between these. The floor keeps very short trips from
#: getting a waypoint so close it lands on the same street; the ceiling
#: keeps coast-to-coast trips from being sent hundreds of miles out of the way.
MIN_DETOUR_OFFSET_MILES = 3.0
MAX_DETOUR_OFFSET_MILES = 150.0

#: Where along the main route detour waypoints are anchored, in the order
#: they are tried: halfway first, then a third and two thirds of the way.
DETOUR_ANCHORS = (0.5, 1 / 3, 2 / 3)

#: Most detour requests made for one trip, whatever the outcome.
MAX_DETOUR_ATTEMPTS = 4

#: Two routes count as the same when they share this much geometry *and*
#: their distance and duration are within the same fraction of each other.
SIMILARITY_THRESHOLD = 0.10

#: Grid size used to compare route shapes, roughly 0.7 miles of latitude.
GEOMETRY_GRID_DEGREES = 0.01

RouteSource = Literal["osrm-alternative", "detour"]


@dataclass(frozen=True)
class RouteOption:
    """One way to drive from the origin to the destination."""

    label: str
    distance_miles: float
    duration_s: float
    geometry: list[Coordinate]
    source: RouteSource

    @property
    def duration_hours(self) -> float:
        """Driving time in hours, for display."""
        return self.duration_s / 3600


def get_routes(
    origin: Coordinate,
    destination: Coordinate,
    *,
    cache: Cache | None = None,
) -> list[RouteOption]:
    """Return up to three meaningfully different routes, labelled A, B and C."""
    payload = _request_osrm([origin, destination], alternatives=MAX_ROUTES, cache=cache)
    candidates = _parse_routes(payload, source="osrm-alternative")
    if not candidates:
        raise ExternalServiceError("No road route could be found between those two places.")

    kept: list[RouteOption] = []
    for candidate in candidates:
        if len(kept) < MAX_ROUTES and _is_distinct(candidate, kept):
            kept.append(candidate)

    if len(kept) < MAX_ROUTES:
        kept.extend(_detour_routes(origin, destination, kept, cache=cache))

    return [
        RouteOption(
            label=ROUTE_LABELS[index],
            distance_miles=route.distance_miles,
            duration_s=route.duration_s,
            geometry=route.geometry,
            source=route.source,
        )
        for index, route in enumerate(kept[:MAX_ROUTES])
    ]


def checkpoint_eta(
    departure: datetime, duration_s: float, mile: float, total_miles: float
) -> datetime:
    """When the truck reaches a checkpoint, assuming a steady pace along the route.

    The share of the trip already driven is applied to the total driving
    time, so a checkpoint halfway along a six hour trip is reached three
    hours after departure.
    """
    if total_miles <= 0:
        return departure
    fraction = min(max(mile / total_miles, 0.0), 1.0)
    return departure + timedelta(seconds=duration_s * fraction)


def _detour_routes(
    origin: Coordinate,
    destination: Coordinate,
    existing: list[RouteOption],
    *,
    cache: Cache | None,
) -> list[RouteOption]:
    """Build alternatives by routing through waypoints beside the main route.

    "Beside" means perpendicular to the trip as a whole - the straight line
    from origin to destination. The road's own heading at a single point is
    no use for this: at a city interchange it can point anywhere, and a
    waypoint pushed "sideways" from it can land back on the same highway.

    The halfway point is tried first, on both sides. If that does not give
    enough distinct routes, points a third and two thirds of the way along
    are tried too, up to a fixed number of attempts so a stubborn trip
    cannot keep the driver waiting.
    """
    main_route = existing[0]
    offset_miles = _detour_offset_miles(main_route.distance_miles)
    trip_heading = initial_bearing(origin, destination)
    cumulative = cumulative_miles(main_route.geometry)

    found: list[RouteOption] = []
    attempts = 0
    for share in DETOUR_ANCHORS:
        anchor = interpolate_point(main_route.geometry, cumulative, cumulative[-1] * share)
        for turn in (-90.0, 90.0):
            if len(existing) + len(found) >= MAX_ROUTES or attempts >= MAX_DETOUR_ATTEMPTS:
                return found
            attempts += 1

            waypoint = point_at_bearing(anchor, trip_heading + turn, offset_miles)
            try:
                payload = _request_osrm(
                    [origin, waypoint, destination], alternatives=0, cache=cache, retries=0
                )
            except ExternalServiceError:
                # A detour is a nice-to-have: if it fails, keep the routes we have.
                continue

            for candidate in _parse_routes(payload, source="detour"):
                if _is_distinct(candidate, existing + found):
                    found.append(candidate)
                    break

    return found


def _detour_offset_miles(trip_miles: float) -> float:
    """How far sideways to push a detour waypoint, clamped to sensible limits."""
    offset = trip_miles * DETOUR_OFFSET_FRACTION
    return min(max(offset, MIN_DETOUR_OFFSET_MILES), MAX_DETOUR_OFFSET_MILES)


def _request_osrm(
    waypoints: list[Coordinate],
    *,
    alternatives: int,
    cache: Cache | None,
    retries: int = DEFAULT_RETRIES,
) -> Any:
    """Ask OSRM to drive through the given waypoints and return the raw payload.

    Detours pass ``retries=0``: they are optional, so a slow one is dropped
    rather than retried, which keeps the worst case for a whole plan well
    inside the server's request timeout.
    """
    path = ";".join(f"{lon:.6f},{lat:.6f}" for lon, lat in waypoints)
    url = f"{OSRM_BASE_URL}/route/v1/driving/{path}"
    params: dict[str, Any] = {
        "alternatives": alternatives if alternatives else "false",
        "geometries": "geojson",
        "overview": "full",
    }

    payload = fetch_json(
        url,
        params,
        service_name=SERVICE_NAME,
        cache=cache,
        cache_key=make_cache_key("osrm", path, alternatives),
        cache_timeout=ROUTE_CACHE_SECONDS,
        retries=retries,
    )

    if not isinstance(payload, dict) or payload.get("code") != "Ok":
        raise ExternalServiceError("No road route could be found between those two places.")
    return payload


def _parse_routes(payload: Any, *, source: RouteSource) -> list[RouteOption]:
    """Turn an OSRM payload into route objects, skipping anything malformed."""
    routes: list[RouteOption] = []
    for raw in payload.get("routes", []):
        geometry = [
            (float(lon), float(lat)) for lon, lat in raw.get("geometry", {}).get("coordinates", [])
        ]
        if len(geometry) < 2:
            continue
        routes.append(
            RouteOption(
                label="",  # Labels are assigned once the final set is chosen.
                distance_miles=float(raw["distance"]) / METERS_PER_MILE,
                duration_s=float(raw["duration"]),
                geometry=geometry,
                source=source,
            )
        )
    return routes


def _is_distinct(candidate: RouteOption, existing: list[RouteOption]) -> bool:
    """Is this route different enough from the ones already chosen?

    A route counts as different when it either follows a noticeably
    different path or has a noticeably different distance or driving time.
    """
    for route in existing:
        shares_path = _shared_fraction(candidate, route) > 1 - SIMILARITY_THRESHOLD
        similar_cost = (
            _relative_difference(candidate.distance_miles, route.distance_miles)
            < SIMILARITY_THRESHOLD
            and _relative_difference(candidate.duration_s, route.duration_s) < SIMILARITY_THRESHOLD
        )
        if shares_path and similar_cost:
            return False
    return True


def _shared_fraction(candidate: RouteOption, other: RouteOption) -> float:
    """Roughly what share of the candidate's path also belongs to the other route.

    Both shapes are snapped onto a coarse grid first, so two routes down the
    same road still match even though their shape points differ slightly.
    """
    candidate_cells = {_grid_cell(point) for point in candidate.geometry}
    other_cells = {_grid_cell(point) for point in other.geometry}
    if not candidate_cells:
        return 1.0
    return len(candidate_cells & other_cells) / len(candidate_cells)


def _grid_cell(point: Coordinate) -> tuple[int, int]:
    lon, lat = point
    return (round(lon / GEOMETRY_GRID_DEGREES), round(lat / GEOMETRY_GRID_DEGREES))


def _relative_difference(first: float, second: float) -> float:
    """How far apart two numbers are, as a share of the larger one."""
    largest = max(abs(first), abs(second))
    if largest == 0:
        return 0.0
    return abs(first - second) / largest
