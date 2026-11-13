"""Plain words for what the weather is doing at a checkpoint.

The risk level says how dangerous a checkpoint is; it does not say why. A
driver reading "Moderate" still has to look at three numbers to find out
whether that means wind or snow. This turns the same three numbers into one
word, so the list of checkpoints can be skimmed.

This is wording, not scoring. The risk level is decided by ``risk.py`` and
is not affected by anything here.
"""

from __future__ import annotations

from typing import Literal

Factor = Literal["wind", "rain", "snow"]

#: What to call the weather, in the order the conditions are tested.
#:
#: The first row that matches wins, so the order is the precedence: any
#: settled snow outranks rain, and rain of any note outranks wind. The
#: thresholds are far lower than the risk table's, because this answers
#: "what is happening" rather than "how dangerous is it" - 0.01 in/hr of
#: rain is harmless but it is still rain, and worth saying.
CONDITION_THRESHOLDS: tuple[tuple[Factor, float, str], ...] = (
    ("snow", 0.1, "Snow"),
    ("rain", 0.25, "Heavy rain"),
    ("rain", 0.01, "Rain"),
    ("wind", 35.0, "High wind"),
    ("wind", 20.0, "Breezy"),
)

#: Used when nothing above matches.
CLEAR_CONDITION = "Clear"


def describe_conditions(wind_mph: float, rain_in: float, snow_in: float) -> str:
    """One word for the weather, e.g. "Heavy rain" or "Breezy"."""
    readings: dict[Factor, float] = {
        "wind": wind_mph,
        "rain": rain_in,
        "snow": snow_in,
    }
    for factor, threshold, word in CONDITION_THRESHOLDS:
        if readings[factor] >= threshold:
            return word
    return CLEAR_CONDITION
