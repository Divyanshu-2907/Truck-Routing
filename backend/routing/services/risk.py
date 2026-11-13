"""Weather risk rules for one checkpoint.

Each checkpoint on a route has a wind speed, a rain rate and a snow rate.
This module turns those three numbers plus the truck's load weight into a
single risk level, and explains which factor caused it.

Two rules decide the outcome:

1. The checkpoint's level is the *worst* of the wind, rain and snow levels.
2. Heavy loads make strong wind worse (see ``assess``), because a loaded
   trailer is far easier to blow over.

Thresholds use a lower-bound-inclusive convention: a wind of exactly 25 mph
is Moderate, rain of exactly 0.25 in/hr is High. The two "No Travel" rows
that the brief writes as strictly greater than (rain > 1.00 in/hr and snow
> 3.0 in/hr) keep that strict comparison, so rain of exactly 1.00 in/hr is
Severe and snow of exactly 3.0 in/hr is Severe.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from typing import Literal

#: A load above this weight turns Severe wind (45-54 mph) into No Travel.
SEVERE_WIND_LOAD_LIMIT_LB = 30_000

#: A load above this weight turns High wind (35-44 mph) into at least Severe.
HIGH_WIND_LOAD_LIMIT_LB = 40_000

RiskFactor = Literal["wind", "rain", "snow", "load"]


class RiskLevel(IntEnum):
    """How dangerous a checkpoint is. Ordered, so ``max()`` picks the worst."""

    LOW = 0
    MODERATE = 1
    HIGH = 2
    SEVERE = 3
    NO_TRAVEL = 4

    @property
    def label(self) -> str:
        """Human-readable name, e.g. ``RiskLevel.NO_TRAVEL.label == "No Travel"``."""
        return _LEVEL_LABELS[self]


_LEVEL_LABELS: dict[RiskLevel, str] = {
    RiskLevel.LOW: "Low",
    RiskLevel.MODERATE: "Moderate",
    RiskLevel.HIGH: "High",
    RiskLevel.SEVERE: "Severe",
    RiskLevel.NO_TRAVEL: "No Travel",
}


def wind_level(mph: float) -> RiskLevel:
    """Risk from wind speed in miles per hour."""
    if mph >= 55:
        return RiskLevel.NO_TRAVEL
    if mph >= 45:
        return RiskLevel.SEVERE
    if mph >= 35:
        return RiskLevel.HIGH
    if mph >= 25:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def rain_level(inches_per_hour: float) -> RiskLevel:
    """Risk from rainfall rate in inches per hour."""
    if inches_per_hour > 1.00:
        return RiskLevel.NO_TRAVEL
    if inches_per_hour >= 0.50:
        return RiskLevel.SEVERE
    if inches_per_hour >= 0.25:
        return RiskLevel.HIGH
    if inches_per_hour >= 0.10:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


def snow_level(inches_per_hour: float) -> RiskLevel:
    """Risk from snowfall rate in inches per hour."""
    if inches_per_hour > 3.0:
        return RiskLevel.NO_TRAVEL
    if inches_per_hour >= 2.0:
        return RiskLevel.SEVERE
    if inches_per_hour >= 1.0:
        return RiskLevel.HIGH
    if inches_per_hour >= 0.5:
        return RiskLevel.MODERATE
    return RiskLevel.LOW


@dataclass(frozen=True)
class RiskAssessment:
    """The risk verdict for one checkpoint, with its reasoning."""

    level: RiskLevel
    wind: RiskLevel
    rain: RiskLevel
    snow: RiskLevel
    driver: RiskFactor
    reason: str


def assess(
    wind_mph: float,
    rain_in: float,
    snow_in: float,
    load_lb: float,
) -> RiskAssessment:
    """Score one checkpoint from its weather and the truck's load weight.

    The worst of the wind, rain and snow levels wins. On top of that, three
    load rules apply:

    * wind >= 55 mph is No Travel for any load (already in the wind table);
    * wind 45-54 mph with a load over 30,000 lb becomes No Travel;
    * wind 35-44 mph with a load over 40,000 lb becomes at least Severe.

    ``driver`` names the factor that produced the final level, and is
    ``"load"`` only when a load rule made the result worse than the weather
    alone would have been.
    """
    wind = wind_level(wind_mph)
    rain = rain_level(rain_in)
    snow = snow_level(snow_in)

    weather_level, weather_driver = _worst_weather_factor(wind, rain, snow)
    load_level = _load_rule_level(wind_mph, load_lb)

    if load_level > weather_level:
        level: RiskLevel = load_level
        driver: RiskFactor = "load"
        reason = f"Wind {_number(wind_mph)} mph + {load_lb:,.0f} lb load -> {level.label}"
    else:
        level = weather_level
        driver = weather_driver
        measurement = _weather_measurement(weather_driver, wind_mph, rain_in, snow_in)
        reason = f"{measurement} -> {level.label}"

    return RiskAssessment(
        level=level, wind=wind, rain=rain, snow=snow, driver=driver, reason=reason
    )


def _worst_weather_factor(
    wind: RiskLevel, rain: RiskLevel, snow: RiskLevel
) -> tuple[RiskLevel, RiskFactor]:
    """Pick the worst of the three weather levels; ties go to wind, then rain."""
    candidates: tuple[tuple[RiskLevel, RiskFactor], ...] = (
        (wind, "wind"),
        (rain, "rain"),
        (snow, "snow"),
    )
    return max(candidates, key=lambda candidate: candidate[0])


def _load_rule_level(wind_mph: float, load_lb: float) -> RiskLevel:
    """The floor that the load rules put under the final level."""
    if wind_mph >= 55:
        return RiskLevel.NO_TRAVEL
    if wind_mph >= 45 and load_lb > SEVERE_WIND_LOAD_LIMIT_LB:
        return RiskLevel.NO_TRAVEL
    if wind_mph >= 35 and load_lb > HIGH_WIND_LOAD_LIMIT_LB:
        return RiskLevel.SEVERE
    return RiskLevel.LOW


def _number(value: float) -> str:
    """Format a measurement without trailing zeros: 47.0 -> "47", 1.40 -> "1.4"."""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return text if text not in {"", "-0"} else "0"


def _weather_measurement(
    factor: RiskFactor, wind_mph: float, rain_in: float, snow_in: float
) -> str:
    """The measurement to quote in the reason string, e.g. "Snow 1.4 in/hr"."""
    if factor == "wind":
        return f"Wind {_number(wind_mph)} mph"
    if factor == "rain":
        return f"Rain {_number(rain_in)} in/hr"
    return f"Snow {_number(snow_in)} in/hr"
