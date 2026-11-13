"""Tests for the OSRM route service.

No real HTTP happens here: ``requests.get`` is replaced with a fake that
returns prepared OSRM payloads. That makes the tests fast and lets us set
up situations that are hard to trigger on purpose against the real server,
such as OSRM finding only one route.
"""

from __future__ import annotations

import unittest
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch

import requests

from routing.services.geo import (
    Coordinate,
    cumulative_miles,
    initial_bearing,
    interpolate_point,
    point_at_bearing,
)
from routing.services.http_client import ExternalServiceError
from routing.services.routes import (
    DETOUR_ANCHORS,
    MAX_DETOUR_ATTEMPTS,
    METERS_PER_MILE,
    RouteOption,
    _detour_offset_miles,
    checkpoint_eta,
    get_routes,
)

DALLAS: Coordinate = (-96.7970, 32.7767)
DENVER: Coordinate = (-104.9903, 39.7392)


def line_between(start: Coordinate, end: Coordinate, steps: int = 20) -> list[list[float]]:
    """A straight GeoJSON coordinate list from start to end."""
    start_lon, start_lat = start
    end_lon, end_lat = end
    return [
        [
            start_lon + (end_lon - start_lon) * step / steps,
            start_lat + (end_lat - start_lat) * step / steps,
        ]
        for step in range(steps + 1)
    ]


def osrm_route(miles: float, hours: float, geometry: list[list[float]]) -> dict[str, Any]:
    """One entry of an OSRM ``routes`` array."""
    return {
        "distance": miles * METERS_PER_MILE,
        "duration": hours * 3600,
        "geometry": {"type": "LineString", "coordinates": geometry},
    }


def osrm_payload(*routes: dict[str, Any]) -> dict[str, Any]:
    return {"code": "Ok", "routes": list(routes)}


class FakeResponse:
    """The handful of ``requests.Response`` members that ``fetch_json`` uses."""

    def __init__(self, payload: Any, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> Any:
        return self._payload


class RoutesTestCase(unittest.TestCase):
    """Base class that records every URL the service asks for."""

    def setUp(self) -> None:
        self.requested_urls: list[str] = []

    def fake_get(self, payloads: list[Any]):
        """Return a stand-in for ``requests.get`` that replays ``payloads`` in order."""
        remaining = list(payloads)

        def _get(url: str, params: Any = None, headers: Any = None, timeout: Any = None):
            self.requested_urls.append(url)
            payload = remaining.pop(0) if remaining else osrm_payload()
            if isinstance(payload, Exception):
                raise payload
            if isinstance(payload, FakeResponse):
                return payload
            return FakeResponse(payload)

        return _get


class ThreeAlternativesTests(RoutesTestCase):
    """When OSRM offers three different routes, they are used as they are."""

    def setUp(self) -> None:
        super().setUp()
        straight = line_between(DALLAS, DENVER)
        # Two detoured shapes that pass well to either side of the direct line.
        north = line_between(DALLAS, point_at_bearing(DENVER, 0.0, 120.0))
        south = line_between(DALLAS, point_at_bearing(DENVER, 180.0, 120.0))
        self.payload = osrm_payload(
            osrm_route(800, 13.0, straight),
            osrm_route(880, 14.5, north),
            osrm_route(950, 16.0, south),
        )

    def test_returns_three_labelled_routes(self) -> None:
        with patch.object(requests, "get", self.fake_get([self.payload])):
            routes = get_routes(DALLAS, DENVER)

        self.assertEqual([route.label for route in routes], ["Route A", "Route B", "Route C"])
        self.assertTrue(all(route.source == "osrm-alternative" for route in routes))

    def test_only_one_request_is_made(self) -> None:
        with patch.object(requests, "get", self.fake_get([self.payload])):
            get_routes(DALLAS, DENVER)

        self.assertEqual(len(self.requested_urls), 1)

    def test_distance_is_converted_from_metres_to_miles(self) -> None:
        with patch.object(requests, "get", self.fake_get([self.payload])):
            routes = get_routes(DALLAS, DENVER)

        self.assertAlmostEqual(routes[0].distance_miles, 800, places=6)
        self.assertAlmostEqual(routes[0].duration_s, 13 * 3600, places=6)
        self.assertAlmostEqual(routes[0].duration_hours, 13.0, places=6)


class DetourFallbackTests(RoutesTestCase):
    """When OSRM only finds one route, detour alternatives are built."""

    def setUp(self) -> None:
        super().setUp()
        self.single = osrm_payload(osrm_route(800, 13.0, line_between(DALLAS, DENVER)))
        self.left_detour = osrm_payload(
            osrm_route(900, 15.0, line_between(DALLAS, point_at_bearing(DENVER, 0.0, 150.0)))
        )
        self.right_detour = osrm_payload(
            osrm_route(960, 16.0, line_between(DALLAS, point_at_bearing(DENVER, 180.0, 150.0)))
        )

    def test_one_route_becomes_three(self) -> None:
        payloads = [self.single, self.left_detour, self.right_detour]
        with patch.object(requests, "get", self.fake_get(payloads)):
            routes = get_routes(DALLAS, DENVER)

        self.assertEqual(len(routes), 3)
        self.assertEqual([route.label for route in routes], ["Route A", "Route B", "Route C"])
        self.assertEqual(
            [route.source for route in routes],
            ["osrm-alternative", "detour", "detour"],
        )

    def test_detours_are_requested_through_a_middle_waypoint(self) -> None:
        payloads = [self.single, self.left_detour, self.right_detour]
        with patch.object(requests, "get", self.fake_get(payloads)):
            get_routes(DALLAS, DENVER)

        self.assertEqual(len(self.requested_urls), 3)
        # The first call has two waypoints, the detour calls have three.
        self.assertEqual(self.requested_urls[0].count(";"), 1)
        self.assertEqual(self.requested_urls[1].count(";"), 2)
        self.assertEqual(self.requested_urls[2].count(";"), 2)

    def test_a_detour_that_repeats_the_main_route_is_dropped(self) -> None:
        # Both detour attempts come back with the original route again.
        payloads = [self.single, self.single, self.single]
        with patch.object(requests, "get", self.fake_get(payloads)):
            routes = get_routes(DALLAS, DENVER)

        self.assertEqual(len(routes), 1)
        self.assertEqual(routes[0].label, "Route A")

    def test_a_failed_detour_leaves_the_other_routes_intact(self) -> None:
        payloads = [self.single, requests.Timeout(), self.right_detour]
        with patch.object(requests, "get", self.fake_get(payloads)):
            routes = get_routes(DALLAS, DENVER)

        self.assertEqual(len(routes), 2)
        self.assertEqual(routes[1].source, "detour")

    def test_two_alternatives_only_need_one_detour(self) -> None:
        two = osrm_payload(
            osrm_route(800, 13.0, line_between(DALLAS, DENVER)),
            osrm_route(900, 15.0, line_between(DALLAS, point_at_bearing(DENVER, 0.0, 150.0))),
        )
        with patch.object(requests, "get", self.fake_get([two, self.right_detour])):
            routes = get_routes(DALLAS, DENVER)

        self.assertEqual(len(routes), 3)
        self.assertEqual(len(self.requested_urls), 2)


class NearDuplicateTests(RoutesTestCase):
    """Alternatives that are really the same road are not shown twice."""

    def test_near_identical_alternative_is_dropped(self) -> None:
        straight = line_between(DALLAS, DENVER)
        payload = osrm_payload(
            osrm_route(800, 13.0, straight),
            osrm_route(802, 13.05, straight),  # same road, trivially different numbers
        )
        # Both detour attempts also come back as the same road.
        with patch.object(requests, "get", self.fake_get([payload, payload, payload])):
            routes = get_routes(DALLAS, DENVER)

        self.assertEqual(len(routes), 1)

    def test_same_shape_but_very_different_timing_is_kept(self) -> None:
        straight = line_between(DALLAS, DENVER)
        payload = osrm_payload(
            osrm_route(800, 13.0, straight),
            osrm_route(800, 20.0, straight),  # same road, much slower
        )
        with patch.object(requests, "get", self.fake_get([payload, payload, payload])):
            routes = get_routes(DALLAS, DENVER)

        self.assertEqual(len(routes), 2)


class ErrorHandlingTests(RoutesTestCase):
    def test_no_route_found_raises_a_clear_error(self) -> None:
        payload = {"code": "NoRoute", "routes": []}
        with patch.object(requests, "get", self.fake_get([payload])):
            with self.assertRaises(ExternalServiceError) as caught:
                get_routes(DALLAS, DENVER)

        self.assertIn("No road route", str(caught.exception))

    def test_a_timeout_is_retried_once_then_reported(self) -> None:
        payloads: list[Any] = [requests.Timeout(), requests.Timeout()]
        with patch.object(requests, "get", self.fake_get(payloads)):
            with self.assertRaises(ExternalServiceError) as caught:
                get_routes(DALLAS, DENVER)

        self.assertEqual(len(self.requested_urls), 2)
        self.assertIn("longer than", str(caught.exception))

    def test_a_retry_that_succeeds_returns_the_route(self) -> None:
        payloads: list[Any] = [
            requests.ConnectionError(),
            osrm_payload(osrm_route(800, 13.0, line_between(DALLAS, DENVER))),
        ]
        with patch.object(requests, "get", self.fake_get(payloads)):
            routes = get_routes(DALLAS, DENVER)

        self.assertEqual(routes[0].label, "Route A")

    def test_routes_without_a_usable_shape_are_ignored(self) -> None:
        payload = osrm_payload(
            {"distance": 100.0, "duration": 100.0, "geometry": {"coordinates": []}}
        )
        with patch.object(requests, "get", self.fake_get([payload])):
            with self.assertRaises(ExternalServiceError):
                get_routes(DALLAS, DENVER)


class CheckpointEtaTests(unittest.TestCase):
    """Arrival time assumes a steady pace along the route."""

    def setUp(self) -> None:
        self.departure = datetime(2026, 1, 2, 6, 0, tzinfo=UTC)
        self.duration_s = 6 * 3600.0
        self.total_miles = 300.0

    def test_origin_is_the_departure_time(self) -> None:
        eta = checkpoint_eta(self.departure, self.duration_s, 0.0, self.total_miles)
        self.assertEqual(eta, self.departure)

    def test_halfway_is_half_the_driving_time(self) -> None:
        eta = checkpoint_eta(self.departure, self.duration_s, 150.0, self.total_miles)
        self.assertEqual(eta, self.departure + timedelta(hours=3))

    def test_destination_is_the_full_driving_time(self) -> None:
        eta = checkpoint_eta(self.departure, self.duration_s, 300.0, self.total_miles)
        self.assertEqual(eta, self.departure + timedelta(hours=6))

    def test_a_quarter_of_the_way(self) -> None:
        eta = checkpoint_eta(self.departure, self.duration_s, 75.0, self.total_miles)
        self.assertEqual(eta, self.departure + timedelta(hours=1.5))

    def test_a_zero_length_route_returns_the_departure_time(self) -> None:
        self.assertEqual(checkpoint_eta(self.departure, self.duration_s, 0.0, 0.0), self.departure)


class CachingTests(RoutesTestCase):
    """A cache hit means no network call at all."""

    class DictCache:
        def __init__(self) -> None:
            self.store: dict[str, Any] = {}

        def get(self, key: str) -> Any:
            return self.store.get(key)

        def set(self, key: str, value: Any, timeout: int | None = None) -> None:
            self.store[key] = value

    def test_second_identical_request_is_served_from_the_cache(self) -> None:
        cache = self.DictCache()
        payload = osrm_payload(
            osrm_route(800, 13.0, line_between(DALLAS, DENVER)),
            osrm_route(900, 15.0, line_between(DALLAS, point_at_bearing(DENVER, 0.0, 150.0))),
            osrm_route(960, 16.0, line_between(DALLAS, point_at_bearing(DENVER, 180.0, 150.0))),
        )
        with patch.object(requests, "get", self.fake_get([payload])):
            first = get_routes(DALLAS, DENVER, cache=cache)
            second = get_routes(DALLAS, DENVER, cache=cache)

        self.assertEqual(len(self.requested_urls), 1)
        self.assertEqual(
            [route.distance_miles for route in first],
            [route.distance_miles for route in second],
        )


class RouteOptionTests(unittest.TestCase):
    def test_duration_hours_converts_from_seconds(self) -> None:
        route = RouteOption(
            label="Route A",
            distance_miles=100.0,
            duration_s=5_400.0,
            geometry=[DALLAS, DENVER],
            source="osrm-alternative",
        )
        self.assertAlmostEqual(route.duration_hours, 1.5, places=6)


def middle_waypoint(url: str) -> Coordinate:
    """The via point of an OSRM request, read back out of its URL."""
    path = url.rsplit("/", 1)[-1]
    lon, lat = path.split(";")[1].split(",")
    return (float(lon), float(lat))


class DetourDirectionTests(RoutesTestCase):
    """Detour waypoints go sideways to the trip, not along a kink in the road."""

    def test_waypoint_is_perpendicular_to_the_trip_not_the_local_road(self) -> None:
        # A trip due north whose middle has a sharp east-west jog, like a
        # highway interchange. The road's own heading there is east.
        origin: Coordinate = (-97.0, 32.0)
        destination: Coordinate = (-97.0, 36.0)
        kinked = [
            [-97.0, 32.0],
            [-97.0, 33.9],
            [-96.9, 34.0],  # the jog
            [-97.0, 34.1],
            [-97.0, 36.0],
        ]
        payloads = [osrm_payload(osrm_route(280, 4.5, kinked))]
        with patch.object(requests, "get", self.fake_get(payloads)):
            get_routes(origin, destination)

        trip_bearing = initial_bearing(origin, destination)  # ~0 degrees, north
        shape: list[Coordinate] = [(point[0], point[1]) for point in kinked]
        cumulative = cumulative_miles(shape)
        # Two attempts per anchor: left, then right.
        anchors = [
            interpolate_point(shape, cumulative, cumulative[-1] * share)
            for share in DETOUR_ANCHORS
            for _side in (0, 1)
        ]

        detour_urls = self.requested_urls[1:]
        self.assertTrue(detour_urls)
        for url, anchor in zip(detour_urls, anchors, strict=False):
            sideways = (initial_bearing(anchor, middle_waypoint(url)) - trip_bearing) % 180
            # Due east or west of its anchor: square to the trip, not the jog.
            self.assertAlmostEqual(sideways, 90.0, delta=2.0)

    def test_more_anchors_are_tried_when_the_halfway_detours_repeat_the_route(self) -> None:
        single = osrm_payload(osrm_route(800, 13.0, line_between(DALLAS, DENVER)))
        detour = osrm_payload(
            osrm_route(960, 16.0, line_between(DALLAS, point_at_bearing(DENVER, 180.0, 150.0)))
        )
        # Both halfway attempts come back as the main road; the third finds one.
        payloads = [single, single, single, detour]
        with patch.object(requests, "get", self.fake_get(payloads)):
            routes = get_routes(DALLAS, DENVER)

        self.assertEqual(len(routes), 2)
        self.assertEqual(routes[1].source, "detour")

    def test_detour_attempts_are_capped_and_not_retried(self) -> None:
        single = osrm_payload(osrm_route(800, 13.0, line_between(DALLAS, DENVER)))
        timeouts: list[Any] = [requests.Timeout()] * 10
        with patch.object(requests, "get", self.fake_get([single, *timeouts])):
            routes = get_routes(DALLAS, DENVER)

        self.assertEqual(len(routes), 1)
        # One request for the main route, then one per detour attempt. A
        # retry on each would double that and could outlast the server timeout.
        self.assertEqual(len(self.requested_urls), 1 + MAX_DETOUR_ATTEMPTS)


class RateLimitTests(RoutesTestCase):
    def test_a_429_is_retried_once(self) -> None:
        ok = osrm_payload(osrm_route(800, 13.0, line_between(DALLAS, DENVER)))
        with patch.object(requests, "get", self.fake_get([FakeResponse({}, status_code=429), ok])):
            routes = get_routes(DALLAS, DENVER)

        self.assertEqual(routes[0].label, "Route A")

    def test_a_persistent_429_says_the_service_is_busy(self) -> None:
        busy = FakeResponse({}, status_code=429)
        with patch.object(requests, "get", self.fake_get([busy, busy])):
            with self.assertRaises(ExternalServiceError) as caught:
                get_routes(DALLAS, DENVER)

        self.assertIn("too many requests", str(caught.exception))


class DetourOffsetTests(unittest.TestCase):
    """The sideways push scales with the trip, within a floor and a ceiling."""

    def test_scales_with_trip_length(self) -> None:
        self.assertAlmostEqual(_detour_offset_miles(795.0), 79.5, places=6)

    def test_short_trips_get_a_short_push(self) -> None:
        # A 32 mile trip used to be pushed a fixed 20 miles out.
        self.assertAlmostEqual(_detour_offset_miles(32.0), 3.2, places=6)
        self.assertEqual(_detour_offset_miles(10.0), 3.0)

    def test_long_trips_are_capped(self) -> None:
        self.assertEqual(_detour_offset_miles(3_300.0), 150.0)
