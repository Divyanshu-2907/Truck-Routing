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
import logging
import time
from typing import Any, Protocol

import requests

logger = logging.getLogger(__name__)

#: How long to wait for an external API before giving up, in seconds.
DEFAULT_TIMEOUT_SECONDS = 10.0

#: How many times to try again after a failure.
DEFAULT_RETRIES = 1

#: How long to wait before retrying, in seconds.
RETRY_BACKOFF_SECONDS = 0.5

#: The status a service sends when it is rate limiting us.
HTTP_TOO_MANY_REQUESTS = 429

#: Extra attempts allowed specifically for rate limiting, on top of the
#: ordinary retry. A limit measured per minute often clears within seconds.
RATE_LIMIT_RETRIES = 2

#: The longest this will ever sit waiting out a rate limit, in seconds.
#: A planned trip makes several of these calls at once and the server gives
#: up on the whole request after 120 seconds, so the waiting has to stay
#: well inside that.
MAX_RATE_LIMIT_WAIT_SECONDS = 10.0

#: Words in a rate-limit reply that mean waiting will not help today.
DAILY_LIMIT_MARKERS = ("daily",)


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
    """Try the request, retrying the failures that a retry can actually fix."""
    last_error = ""
    attempts_left = retries
    # Rate limits get their own budget: they are worth waiting out, but only
    # for a few seconds, and only when retrying was wanted at all.
    rate_limit_attempts_left = RATE_LIMIT_RETRIES if retries > 0 else 0
    waited = 0.0

    while True:
        try:
            response = requests.get(url, params=params, headers=headers, timeout=timeout)
        except requests.Timeout:
            last_error = f"{service_name} took longer than {timeout:.0f} seconds to answer"
            response = None
        except requests.RequestException:
            last_error = f"{service_name} could not be reached"
            response = None

        if response is not None:
            if response.status_code == HTTP_TOO_MANY_REQUESTS:
                reason = _rate_limit_reason(response)
                retry_after = _retry_after_seconds(response)
                logger.warning(
                    "%s rate limited (429): retry_after=%s reason=%s",
                    service_name,
                    retry_after if retry_after is not None else "none",
                    reason or "none given",
                )

                if _is_daily_limit(reason):
                    # Waiting cannot fix a quota that resets tomorrow.
                    raise ExternalServiceError(
                        f"{service_name} has used up its daily free quota. " "Try again later."
                    )

                wait = retry_after if retry_after is not None else RETRY_BACKOFF_SECONDS * 2
                # A service asking for longer than the budget allows is not
                # worth waiting on: the wait would run out and the retry
                # would fail anyway, so the driver is told now instead.
                if rate_limit_attempts_left > 0 and waited + wait <= MAX_RATE_LIMIT_WAIT_SECONDS:
                    rate_limit_attempts_left -= 1
                    waited += wait
                    time.sleep(wait)
                    continue

                raise ExternalServiceError(
                    f"{service_name} is receiving too many requests right now. "
                    "Please try again in a moment."
                )

            if response.status_code >= 500:
                last_error = f"{service_name} reported a server error ({response.status_code})"
            elif response.status_code >= 400:
                # A client error will fail the same way on a retry, so stop now.
                raise ExternalServiceError(
                    f"{service_name} rejected the request ({response.status_code})."
                )
            else:
                try:
                    return response.json()
                except ValueError as error:
                    raise ExternalServiceError(
                        f"{service_name} returned a response that could not be read."
                    ) from error

        if attempts_left <= 0:
            raise ExternalServiceError(f"{last_error}. Please try again in a moment.")
        attempts_left -= 1
        time.sleep(RETRY_BACKOFF_SECONDS)


def _rate_limit_reason(response: Any) -> str:
    """The explanation a rate-limited service gives, if it gives one.

    Open-Meteo answers with ``{"error": true, "reason": "..."}`` naming the
    limit that was hit - minutely, hourly or daily - which is the difference
    between waiting a moment and waiting until tomorrow.
    """
    try:
        body = response.json()
    except ValueError:
        return str(getattr(response, "text", ""))[:200]
    if isinstance(body, dict):
        return str(body.get("reason") or body.get("error") or "")[:200]
    return str(body)[:200]


def _is_daily_limit(reason: str) -> bool:
    return any(marker in reason.lower() for marker in DAILY_LIMIT_MARKERS)


def _retry_after_seconds(response: Any) -> float | None:
    """The Retry-After header in seconds, when the service sends a usable one."""
    headers = getattr(response, "headers", None) or {}
    raw = headers.get("Retry-After")
    if raw is None:
        return None
    try:
        seconds = float(str(raw).strip())
    except ValueError:
        # The header may be an HTTP date; the fixed backoff covers that.
        return None
    if seconds < 0:
        return None
    # Returned as given: the caller decides whether it fits in the budget.
    return seconds
