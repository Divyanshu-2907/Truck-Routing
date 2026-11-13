"""Turning a typed place name into coordinates, using Nominatim.

Nominatim is free but asks two things of callers: send a real User-Agent
that identifies the app, and make at most one request per second. Both are
handled here - the throttle below simply waits if the last request was too
recent, and results are cached so repeated searches never hit the network.

Searches are biased towards the United States, since this is a US trucking
tool and "Springfield" should find the American one. Towns and cities are
ranked above everything else, and labelled "City, ST", because a driver
planning a trip means the place, not the county or the business sharing its
name.
"""

from __future__ import annotations

import os
import threading
import time
from collections import Counter
from dataclasses import dataclass
from typing import Any

from .http_client import Cache, fetch_json, make_cache_key

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"

SERVICE_NAME = "The place search service"

#: Place names and their coordinates almost never change, so cache for a day.
GEOCODE_CACHE_SECONDS = 24 * 60 * 60

DEFAULT_RESULT_LIMIT = 5

#: More results are fetched than are shown, so there is something to rank:
#: a search for "Dallas" comes back with one city and five counties.
SEARCH_FETCH_LIMIT = 10

#: Nominatim's ``addresstype`` values that mean "somewhere people live".
#: Note that its ``featureType=settlement`` parameter does not do this job -
#: asked for "Dallas" with it set, Nominatim still returns the counties.
SETTLEMENT_TYPES = frozenset({"city", "town", "village", "hamlet", "municipality", "borough"})

#: Nominatim's usage policy: at most one request per second.
MIN_SECONDS_BETWEEN_REQUESTS = 1.0

#: Nominatim requires an identifying User-Agent with a way to make contact.
USER_AGENT = os.environ.get(
    "NOMINATIM_USER_AGENT",
    "WeatherAwareTruckRouting/1.0 (truck routing take-home project)",
)

_throttle_lock = threading.Lock()
_last_request_at = 0.0


@dataclass(frozen=True)
class Place:
    """A place the driver can pick as an origin or destination."""

    label: str
    lat: float
    lon: float


def geocode(
    query: str,
    *,
    limit: int = DEFAULT_RESULT_LIMIT,
    cache: Cache | None = None,
) -> list[Place]:
    """Look up matching US places for a typed search, best match first."""
    cleaned = query.strip()
    if not cleaned:
        return []

    cache_key = make_cache_key("geocode", cleaned.lower(), limit)
    if cache is not None:
        cached = cache.get(cache_key)
        if cached is not None:
            return [Place(**item) for item in cached]

    _wait_for_rate_limit()
    payload = fetch_json(
        NOMINATIM_URL,
        {
            "q": cleaned,
            "format": "jsonv2",
            "limit": SEARCH_FETCH_LIMIT,
            "countrycodes": "us",
            # Needed for the state code in the label, and for the address
            # type the ranking below sorts on.
            "addressdetails": 1,
        },
        service_name=SERVICE_NAME,
        headers={"User-Agent": USER_AGENT},
    )

    places = _parse_places(payload)[:limit]
    if cache is not None:
        cache.set(cache_key, [place.__dict__ for place in places], GEOCODE_CACHE_SECONDS)
    return places


def _parse_places(payload: Any) -> list[Place]:
    """Read the results, settlements first, each labelled City, ST."""
    if not isinstance(payload, list):
        return []

    settlements: list[_Candidate] = []
    others: list[_Candidate] = []

    for item in payload:
        candidate = _read_candidate(item)
        if candidate is None:
            continue
        if item.get("addresstype") in SETTLEMENT_TYPES:
            settlements.append(candidate)
        else:
            others.append(candidate)

    # Each group keeps Nominatim's own relevance order; only the two groups
    # are swapped, so the city beats the county of the same name.
    return _disambiguate(settlements + others)


@dataclass(frozen=True)
class _Candidate:
    """One result, ready to label.

    The county is kept aside in case it is needed to tell two same-named
    places apart.
    """

    place: Place
    county: str


def _read_candidate(item: Any) -> _Candidate | None:
    """Turn one Nominatim result into a candidate, or None if unusable."""
    if not isinstance(item, dict):
        return None
    try:
        lat = float(item["lat"])
        lon = float(item["lon"])
    except (KeyError, TypeError, ValueError):
        return None

    label = _label_for(item)
    if not label:
        return None

    address = item.get("address") or {}
    county = address.get("county")
    return _Candidate(
        place=Place(label=label, lat=lat, lon=lon),
        county=str(county) if county else "",
    )


def _label_for(item: dict[str, Any]) -> str:
    """Build a Dallas, TX style label, falling back to the full display name."""
    name = item.get("name")
    state = _state_code(item.get("address") or {})
    if name and state:
        return f"{name}, {state}"
    display = item.get("display_name")
    return str(display) if display else ""


def _state_code(address: dict[str, Any]) -> str:
    """The two-letter state from Nominatim's ISO code, e.g. "US-TX" -> "TX"."""
    iso = address.get("ISO3166-2-lvl4")
    if isinstance(iso, str) and iso.startswith("US-") and len(iso) == 5:
        return iso[3:]
    return ""


def _disambiguate(candidates: list[_Candidate]) -> list[Place]:
    """Add the county to labels that would otherwise look identical.

    Two different Springfields in the same state would both read
    "Springfield, IL", leaving the driver to pick blind. Each candidate
    carries its own county, so the pair can be told apart.
    """
    repeated = Counter(candidate.place.label for candidate in candidates)

    places: list[Place] = []
    for candidate in candidates:
        place = candidate.place
        if repeated[place.label] > 1 and candidate.county:
            name, _, state = place.label.rpartition(", ")
            places.append(
                Place(label=f"{name}, {candidate.county}, {state}", lat=place.lat, lon=place.lon)
            )
        else:
            places.append(place)
    return places


def _wait_for_rate_limit() -> None:
    """Hold the next request back until a full second has passed."""
    global _last_request_at
    with _throttle_lock:
        elapsed = time.monotonic() - _last_request_at
        if elapsed < MIN_SECONDS_BETWEEN_REQUESTS:
            time.sleep(MIN_SECONDS_BETWEEN_REQUESTS - elapsed)
        _last_request_at = time.monotonic()
