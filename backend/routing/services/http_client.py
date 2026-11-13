"""One place where this app talks to the outside world.

Every call to OSRM, Nominatim and Open-Meteo goes through ``fetch_json``,
which gives all of them the same behaviour: a timeout, one retry, an
optional cache, and a single ``ExternalServiceError`` carrying a message
that is safe and useful to show to the driver.

The cache is passed in rather than imported, so this module stays free of
Django. Django's own ``django.core.cache.cache`` object already matches the
``Cache`` protocol below, so the views can hand it straight over.
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Protocol

import requests

#: How long to wait for an external API before giving up, in seconds.
DEFAULT_TIMEOUT_SECONDS = 10.0

#: How many times to try again after a failure.
DEFAULT_RETRIES = 1

#: How long to wait before retrying, in seconds.
RETRY_BACKOFF_SECONDS = 0.5

#: The status a service sends when it is rate limiting us.
HTTP_TOO_MANY_REQUESTS = 429


def make_cache_key(prefix: str, *parts: Any) -> str:
    """Build a cache key that is safe for any cache backend.

    The parts are hashed, so keys never contain spaces or punctuation that
    backends such as memcached reject, and never grow too long.
    """
    joined = "|".join(str(part) for part in parts)
    digest = hashlib.blake2s(joined.encode("utf-8"), digest_size=16).hexdigest()
    return f"{prefix}:{digest}"


class ExternalServiceError(RuntimeError):
    """An external API was unreachable, too slow, or returned something unusable."""


class Cache(Protocol):
    """The small slice of Django's cache API that this module needs."""

    def get(self, key: str) -> Any:
        """Return the value stored under a key, or None if there is none."""
        ...

    def set(self, key: str, value: Any, timeout: int | None = None) -> None:  # noqa: A003
        """Store a value under a key for ``timeout`` seconds."""
        ...


def fetch_json(
    url: str,
    params: dict[str, Any] | None = None,
    *,
    service_name: str,
    headers: dict[str, str] | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    retries: int = DEFAULT_RETRIES,
    cache: Cache | None = None,
    cache_key: str | None = None,
    cache_timeout: int | None = None,
) -> Any:
    """GET a URL and return the parsed JSON body.

    ``service_name`` is only used in error messages ("the routing service"),
    so the driver is told which part of the trip planning failed. When a
    ``cache`` and ``cache_key`` are given, a hit is returned without any
    network call and a successful response is stored.
    """
    if cache is not None and cache_key is not None:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached

    payload = _get_with_retries(
        url,
        params,
        service_name=service_name,
        headers=headers,
        timeout=timeout,
        retries=retries,
    )

    if cache is not None and cache_key is not None:
        cache.set(cache_key, payload, cache_timeout)
    return payload


def _get_with_retries(
    url: str,
    params: dict[str, Any] | None,
    *,
    service_name: str,
    headers: dict[str, str] | None,
    timeout: float,
    retries: int,
) -> Any:
    """Try the request, then try it once more before reporting a failure."""
    last_error = ""

    for attempt in range(retries + 1):
        if attempt:
            time.sleep(RETRY_BACKOFF_SECONDS)
        try:
            response = requests.get(url, params=params, headers=headers, timeout=timeout)
        except requests.Timeout:
            last_error = f"{service_name} took longer than {timeout:.0f} seconds to answer"
            continue
        except requests.RequestException:
            last_error = f"{service_name} could not be reached"
            continue

        if response.status_code >= 500:
            last_error = f"{service_name} reported a server error ({response.status_code})"
            continue
        if response.status_code == HTTP_TOO_MANY_REQUESTS:
            # Rate limited: unlike other client errors this one can pass,
            # so it is worth the same single retry as a server error.
            last_error = f"{service_name} is receiving too many requests right now"
            continue
        if response.status_code >= 400:
            # A client error will fail the same way on a retry, so stop now.
            raise ExternalServiceError(
                f"{service_name} rejected the request ({response.status_code})."
            )

        try:
            return response.json()
        except ValueError as error:
            raise ExternalServiceError(
                f"{service_name} returned a response that could not be read."
            ) from error

    raise ExternalServiceError(f"{last_error}. Please try again in a moment.")
