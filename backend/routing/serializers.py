"""Validating the plan request and shaping the plan response.

The request serializers reject bad input before any external API is called,
so a typo never costs the driver a slow round trip. The response builders
turn the service dataclasses into plain JSON.

Map geometry and checkpoints are sent as ``[latitude, longitude]``, which is
the order Leaflet expects, so the frontend can hand them straight to the map.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from rest_framework import serializers

from .services.conditions import describe_conditions
from .services.geo import haversine_miles
from .services.heatmap import HeatmapGrid
from .services.planner import ScoredRoute, format_duration
from .services.risk import RiskLevel
from .services.trip import TripPlan
from .services.weather import MAX_FORECAST_DAYS, forecast_horizon

MIN_LOAD_LB = 1
MAX_LOAD_LB = 80_000
SAMPLING_INTERVALS = (10, 25, 50)

#: Origins and destinations closer than this are treated as the same place.
MIN_TRIP_MILES = 1.0

#: How far in the past a departure may be. A little slack covers a driver who
#: is already on the road, or a clock that is a few minutes out.
PAST_DEPARTURE_GRACE = timedelta(hours=1)

#: An ISO 8601 timestamp has to end with Z or an offset such as -06:00.
TIMEZONE_SUFFIX = re.compile(r"(Z|z|[+-]\d{2}:?\d{2})$")

#: JSON-friendly names for the risk levels, used as object keys.
LEVEL_KEYS = {
    RiskLevel.LOW: "low",
    RiskLevel.MODERATE: "moderate",
    RiskLevel.HIGH: "high",
    RiskLevel.SEVERE: "severe",
    RiskLevel.NO_TRAVEL: "no_travel",
}


class PointSerializer(serializers.Serializer):
    """An origin or destination the driver picked from the search box."""

    lat = serializers.FloatField(min_value=-90, max_value=90)
    lon = serializers.FloatField(min_value=-180, max_value=180)
    label = serializers.CharField(max_length=300)


class TripSerializer(serializers.Serializer):
    """The fields shared by the plan and the heatmap requests."""

    origin = PointSerializer()
    destination = PointSerializer()
    departure = serializers.DateTimeField()
    load_lb = serializers.FloatField(min_value=MIN_LOAD_LB, max_value=MAX_LOAD_LB)

    def validate_departure(self, value: datetime) -> datetime:
        """Insist on a timezone, and on a date the forecast can actually reach."""
        raw = self.initial_data.get("departure")
        if isinstance(raw, str) and not TIMEZONE_SUFFIX.search(raw.strip()):
            raise serializers.ValidationError(
                "Include a timezone offset, for example 2026-11-13T08:00:00-06:00."
            )
        now = datetime.now(UTC)
        if value < now - PAST_DEPARTURE_GRACE:
            raise serializers.ValidationError(
                "That departure time has already passed. Choose a time from now onwards."
            )
        if value > forecast_horizon(now):
            raise serializers.ValidationError(
                f"Weather forecasts only reach {MAX_FORECAST_DAYS} days ahead. "
                "Choose a departure time within that window."
            )
        return value

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        """Refuse a trip that starts and ends in the same place.

        Without this the routing service returns a route of zero miles, and
        the detour search then invents two round trips out of nothing.
        """
        origin = attrs["origin"]
        destination = attrs["destination"]
        miles = haversine_miles(
            (origin["lon"], origin["lat"]), (destination["lon"], destination["lat"])
        )
        if miles < MIN_TRIP_MILES:
            raise serializers.ValidationError(
                "Origin and destination are the same place. Choose two different places."
            )
        return attrs


class PlanRequestSerializer(TripSerializer):
    """The trip the driver is asking about, plus how finely to sample it."""

    interval_miles = serializers.ChoiceField(choices=SAMPLING_INTERVALS)


class HeatmapRequestSerializer(TripSerializer):
    """The same trip, for the corridor heatmap. Sampling interval is fixed."""


def heatmap_to_dict(grid: HeatmapGrid) -> dict[str, Any]:
    """The compact grid sent to the browser.

    Everything goes out as small integers rather than objects: the whole
    48 hour grid is then a few tens of kilobytes, small enough for the
    frontend to hold every frame in memory and never call back while the
    driver drags the slider or switches between risk, wind, rain and snow.

    Units follow ``HeatmapGrid``: wind in mph, rain in hundredths of an
    inch per hour, snow in tenths.
    """
    return {
        "times": [moment.isoformat() for moment in grid.times],
        "points": [[round(lat, 4), round(lon, 4)] for lon, lat in grid.points],
        "values": grid.values,
        "weather_source": grid.source,
        "wind": grid.wind,
        "rain": grid.rain,
        "snow": grid.snow,
    }


def plan_to_dict(plan: TripPlan) -> dict[str, Any]:
    """The full JSON body returned by POST /api/plan."""
    return {
        "routes": [_route_to_dict(route) for route in plan.routes],
        "recommended_index": plan.recommended_index,
        "recommendation_reason": plan.recommendation_reason,
        "deciding_criterion": plan.deciding_criterion,
        "weather_source": plan.weather_source,
        "generated_at": plan.generated_at.isoformat(),
    }


def _route_to_dict(scored: ScoredRoute) -> dict[str, Any]:
    route = scored.route
    return {
        "label": route.label,
        "source": route.source,
        "geometry": [[lat, lon] for lon, lat in route.geometry],
        "summary": _summary_to_dict(scored),
        "checkpoints": [_checkpoint_to_dict(point) for point in scored.checkpoints],
    }


def _summary_to_dict(scored: ScoredRoute) -> dict[str, Any]:
    summary = scored.summary
    return {
        "distance_miles": round(summary.distance_miles, 1),
        "duration_s": round(summary.duration_s),
        "duration_text": format_duration(summary.duration_s),
        "average_risk": round(summary.average_risk, 3),
        "max_level": int(summary.max_level),
        "max_level_label": summary.max_level.label,
        "miles_by_level": {
            key: round(summary.miles_by_level[level], 1) for level, key in LEVEL_KEYS.items()
        },
        "checkpoints_by_level": {
            key: summary.checkpoints_by_level[level] for level, key in LEVEL_KEYS.items()
        },
        "checkpoint_count": len(scored.checkpoints),
    }


def _checkpoint_to_dict(point: Any) -> dict[str, Any]:
    return {
        "mile": round(point.mile, 1),
        # How much road this checkpoint stands for, which is what weights it
        # in the scoring and what sizes its segment in the risk profile.
        # Three decimals, not one: every checkpoint covers almost the same
        # distance, so rounding each to a tenth would push the total off in
        # one direction - by miles on a long trip.
        "covered_miles": round(point.covered_miles, 3),
        "lat": round(point.lat, 5),
        "lon": round(point.lon, 5),
        "eta": point.eta.isoformat(),
        "wind_mph": round(point.wind_mph, 1),
        "rain_in": round(point.rain_in, 3),
        "snow_in": round(point.snow_in, 3),
        "level": int(point.level),
        "level_label": point.level.label,
        "reason": point.reason,
        "condition": describe_conditions(point.wind_mph, point.rain_in, point.snow_in),
    }
