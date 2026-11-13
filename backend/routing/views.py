"""HTTP endpoints for the routing app.

Views stay thin: they read the request, call the pure services in
``routing/services/`` and serialise the result. All business logic lives in
those services so it can be unit tested without Django.

Failures from an external API come back as ``ExternalServiceError`` and are
turned into ``{"error": "..."}`` with status 502. A trip that cannot be
planned as asked - say, one that would still be driving after the forecast
ends - is a ``PlanningError`` and becomes a 400, because the driver can fix
it. Both arrive in the frontend as one Alert.
"""

import logging
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.http import FileResponse, HttpRequest, HttpResponse, HttpResponseNotFound
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from .serializers import (
    HeatmapRequestSerializer,
    PlanRequestSerializer,
    heatmap_to_dict,
    plan_to_dict,
)
from .services.geocode import geocode
from .services.http_client import ExternalServiceError
from .services.trip import PlanningError, plan_trip, trip_heatmap

logger = logging.getLogger(__name__)

MIN_QUERY_LENGTH = 2


@api_view(["GET"])
def health(_request: Request) -> Response:
    """Report that the API is reachable; used by the frontend status chip."""
    return Response({"status": "ok"})


@api_view(["GET"])
def geocode_search(request: Request) -> Response:
    """Search for US places matching ``?q=``, for the origin and destination boxes."""
    query = request.query_params.get("q", "").strip()
    if len(query) < MIN_QUERY_LENGTH:
        return Response(
            {"error": f"Type at least {MIN_QUERY_LENGTH} characters to search for a place."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        places = geocode(query, cache=cache)
    except ExternalServiceError as error:
        return Response({"error": str(error)}, status=status.HTTP_502_BAD_GATEWAY)

    return Response(
        [{"label": place.label, "lat": place.lat, "lon": place.lon} for place in places]
    )


@api_view(["POST"])
def plan(request: Request) -> Response:
    """Plan a trip: build the route options, score the weather risk, recommend one."""
    form = PlanRequestSerializer(data=request.data)
    if not form.is_valid():
        return Response(
            {"error": _first_error(form.errors), "details": form.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    trip = form.validated_data
    try:
        result = plan_trip(
            origin=(trip["origin"]["lon"], trip["origin"]["lat"]),
            destination=(trip["destination"]["lon"], trip["destination"]["lat"]),
            departure=trip["departure"],
            load_lb=trip["load_lb"],
            interval_miles=trip["interval_miles"],
            cache=cache,
        )
    except PlanningError as error:
        return Response({"error": str(error)}, status=status.HTTP_400_BAD_REQUEST)
    except ExternalServiceError as error:
        return Response({"error": str(error)}, status=status.HTTP_502_BAD_GATEWAY)

    timings = result.timings
    logger.info(
        "plan %s -> %s: total=%.0fms (routing=%.0fms weather=%.0fms scoring=%.0fms) "
        "routes=%d checkpoints=%d",
        trip["origin"]["label"],
        trip["destination"]["label"],
        timings.total_ms,
        timings.routes_ms,
        timings.weather_ms,
        timings.scoring_ms,
        len(result.routes),
        sum(len(route.checkpoints) for route in result.routes),
    )

    return Response(plan_to_dict(result))


def _first_error(errors: Any) -> str:
    """Pull one readable sentence out of DRF's nested error structure."""
    if isinstance(errors, dict):
        for field, value in errors.items():
            message = _first_error(value)
            return message if field == "non_field_errors" else f"{field}: {message}"
    if isinstance(errors, list) and errors:
        return _first_error(errors[0])
    return str(errors)


@api_view(["POST"])
def heatmap(request: Request) -> Response:
    """The 48 hour corridor heatmap for a trip the driver has just planned."""
    form = HeatmapRequestSerializer(data=request.data)
    if not form.is_valid():
        return Response(
            {"error": _first_error(form.errors), "details": form.errors},
            status=status.HTTP_400_BAD_REQUEST,
        )

    trip = form.validated_data
    try:
        grid = trip_heatmap(
            origin=(trip["origin"]["lon"], trip["origin"]["lat"]),
            destination=(trip["destination"]["lon"], trip["destination"]["lat"]),
            departure=trip["departure"],
            load_lb=trip["load_lb"],
            cache=cache,
        )
    except PlanningError as error:
        return Response({"error": str(error)}, status=status.HTTP_400_BAD_REQUEST)
    except ExternalServiceError as error:
        return Response({"error": str(error)}, status=status.HTTP_502_BAD_GATEWAY)

    return Response(heatmap_to_dict(grid))


def spa_index(_request: HttpRequest) -> HttpResponse:
    """Serve the React app for any address that is not part of the API.

    WhiteNoise already serves the built files, so this only catches
    addresses it does not recognise - someone opening a bookmarked link, for
    instance. Returning the app lets the browser sort the address out.
    """
    index = settings.FRONTEND_INDEX
    if not index.is_file():
        return HttpResponseNotFound(
            "The React app has not been built. Run the Vite dev server, "
            "or build the Docker image which builds it for you."
        )
    return FileResponse(index.open("rb"), content_type="text/html")
