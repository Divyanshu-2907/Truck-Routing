"""Tests for the place search, with Nominatim replaced by prepared payloads.

The payloads below are trimmed copies of real Nominatim responses, so the
ranking and labelling are tested against the shape the service actually
returns rather than an invented one.
"""

from __future__ import annotations

import unittest
from typing import Any
from unittest.mock import patch

import requests

from routing.services.geocode import SEARCH_FETCH_LIMIT, geocode


def entry(
    name: str,
    addresstype: str,
    state_code: str,
    lat: float,
    lon: float,
    county: str | None = None,
) -> dict[str, Any]:
    address: dict[str, Any] = {"ISO3166-2-lvl4": f"US-{state_code}"}
    if county:
        address["county"] = county
    return {
        "name": name,
        "addresstype": addresstype,
        "lat": str(lat),
        "lon": str(lon),
        "display_name": f"{name}, {county or 'Somewhere'} County, {state_code}, United States",
        "address": address,
    }


class FakeResponse:
    def __init__(self, payload: Any) -> None:
        self._payload = payload
        self.status_code = 200

    def json(self) -> Any:
        return self._payload


class GeocodeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.params: list[dict[str, Any]] = []
        # The real service waits a second between calls; these tests do not
        # touch the network, so that wait is not needed.
        throttle = patch("routing.services.geocode._wait_for_rate_limit")
        throttle.start()
        self.addCleanup(throttle.stop)

    def fake_get(self, payload: Any):
        def _get(url: str, params: Any = None, headers: Any = None, timeout: Any = None):
            self.params.append(params or {})
            return FakeResponse(payload)

        return _get

    def search(self, payload: Any, query: str = "Dallas", **kwargs: Any):
        with patch.object(requests, "get", self.fake_get(payload)):
            return geocode(query, **kwargs)


class RankingTests(GeocodeTestCase):
    """A search for a town should find the town, not the county."""

    def test_settlements_come_before_counties(self) -> None:
        # Nominatim's own order for "Dallas": the city, then five counties.
        payload = [
            entry("Dallas County", "county", "TX", 32.8, -96.8),
            entry("Dallas", "city", "TX", 32.7767, -96.797),
            entry("Dallas County", "county", "IA", 41.7, -94.0),
        ]
        places = self.search(payload)

        self.assertEqual(places[0].label, "Dallas, TX")
        self.assertEqual(
            [place.label for place in places[1:]], ["Dallas County, TX", "Dallas County, IA"]
        )

    def test_towns_and_villages_count_as_settlements(self) -> None:
        payload = [
            entry("Springfield", "county", "KY", 37.6, -85.2),
            entry("Springfield", "village", "WI", 43.0, -89.5),
            entry("Springfield", "town", "VT", 43.2, -72.4),
        ]
        places = self.search(payload, "Springfield")

        self.assertEqual(
            [place.label for place in places[:2]], ["Springfield, WI", "Springfield, VT"]
        )

    def test_relevance_order_is_kept_inside_each_group(self) -> None:
        payload = [
            entry("Springfield", "city", "IL", 39.8, -89.6),
            entry("Springfield", "city", "MA", 42.1, -72.6),
            entry("Springfield", "city", "MO", 37.2, -93.3),
        ]
        places = self.search(payload, "Springfield")

        self.assertEqual(
            [place.label for place in places],
            ["Springfield, IL", "Springfield, MA", "Springfield, MO"],
        )

    def test_a_place_with_no_settlement_at_all_still_returns_results(self) -> None:
        payload = [entry("Dallas Love Field", "aerodrome", "TX", 32.84, -96.85)]
        places = self.search(payload, "Dallas Love Field")

        self.assertEqual([place.label for place in places], ["Dallas Love Field, TX"])


class LabelTests(GeocodeTestCase):
    def test_labels_are_city_and_state_code(self) -> None:
        payload = [entry("Fort Worth", "city", "TX", 32.7555, -97.3308)]
        self.assertEqual(self.search(payload, "Fort Worth")[0].label, "Fort Worth, TX")

    def test_a_missing_state_falls_back_to_the_full_display_name(self) -> None:
        payload = [
            {
                "name": "Nowhere",
                "addresstype": "city",
                "lat": "40.0",
                "lon": "-100.0",
                "display_name": "Nowhere, United States",
                "address": {},
            }
        ]
        self.assertEqual(self.search(payload, "Nowhere")[0].label, "Nowhere, United States")

    def test_same_name_in_the_same_state_is_disambiguated_by_county(self) -> None:
        payload = [
            entry("Springfield", "village", "WI", 43.0, -89.5, county="Dane"),
            entry("Springfield", "village", "WI", 44.5, -88.0, county="Marquette"),
        ]
        places = self.search(payload, "Springfield")

        self.assertEqual(
            [place.label for place in places],
            ["Springfield, Dane, WI", "Springfield, Marquette, WI"],
        )

    def test_entries_without_coordinates_are_skipped(self) -> None:
        payload = [
            {"name": "Broken", "addresstype": "city", "address": {"ISO3166-2-lvl4": "US-TX"}},
            entry("Dallas", "city", "TX", 32.7767, -96.797),
        ]
        self.assertEqual([place.label for place in self.search(payload)], ["Dallas, TX"])


class RequestTests(GeocodeTestCase):
    def test_more_results_are_fetched_than_shown_so_there_is_something_to_rank(self) -> None:
        payload = [
            entry(f"Place {index}", "city", "TX", 32.0 + index, -96.0) for index in range(10)
        ]
        places = self.search(payload, "Place", limit=5)

        self.assertEqual(self.params[0]["limit"], SEARCH_FETCH_LIMIT)
        self.assertEqual(len(places), 5)

    def test_address_details_are_requested(self) -> None:
        self.search([entry("Dallas", "city", "TX", 32.7767, -96.797)])

        self.assertEqual(self.params[0]["addressdetails"], 1)
        self.assertEqual(self.params[0]["countrycodes"], "us")

    def test_an_identifying_user_agent_is_sent(self) -> None:
        sent: dict[str, Any] = {}

        def _get(url: str, params: Any = None, headers: Any = None, timeout: Any = None):
            sent.update(headers or {})
            return FakeResponse([entry("Dallas", "city", "TX", 32.7767, -96.797)])

        with patch.object(requests, "get", _get):
            geocode("Dallas")

        self.assertIn("WeatherAwareTruckRouting", sent["User-Agent"])
