"""Tests for the plain-word description of a checkpoint's weather.

Each threshold is checked on both sides, and the precedence between them is
checked directly, because the order the rules are tested in is the whole
behaviour: a snowy, windy checkpoint should say "Snow".
"""

import unittest

from routing.services.conditions import (
    CLEAR_CONDITION,
    CONDITION_THRESHOLDS,
    describe_conditions,
)

CALM = {"wind_mph": 0.0, "rain_in": 0.0, "snow_in": 0.0}


def describe(**overrides: float) -> str:
    return describe_conditions(**{**CALM, **overrides})


class ThresholdTests(unittest.TestCase):
    """Every boundary, on both sides."""

    def test_snow(self) -> None:
        self.assertEqual(describe(snow_in=0.09), CLEAR_CONDITION)
        self.assertEqual(describe(snow_in=0.1), "Snow")
        self.assertEqual(describe(snow_in=4.0), "Snow")

    def test_rain(self) -> None:
        self.assertEqual(describe(rain_in=0.009), CLEAR_CONDITION)
        self.assertEqual(describe(rain_in=0.01), "Rain")
        self.assertEqual(describe(rain_in=0.249), "Rain")
        self.assertEqual(describe(rain_in=0.25), "Heavy rain")
        self.assertEqual(describe(rain_in=2.0), "Heavy rain")

    def test_wind(self) -> None:
        self.assertEqual(describe(wind_mph=19.9), CLEAR_CONDITION)
        self.assertEqual(describe(wind_mph=20.0), "Breezy")
        self.assertEqual(describe(wind_mph=34.9), "Breezy")
        self.assertEqual(describe(wind_mph=35.0), "High wind")
        self.assertEqual(describe(wind_mph=90.0), "High wind")

    def test_nothing_happening(self) -> None:
        self.assertEqual(describe(), CLEAR_CONDITION)


class PrecedenceTests(unittest.TestCase):
    """The first matching rule wins, in the order they are listed."""

    def test_snow_outranks_everything(self) -> None:
        self.assertEqual(
            describe(snow_in=0.2, rain_in=1.0, wind_mph=60.0),
            "Snow",
        )

    def test_heavy_rain_outranks_light_rain_and_wind(self) -> None:
        self.assertEqual(describe(rain_in=0.3, wind_mph=60.0), "Heavy rain")

    def test_rain_outranks_wind(self) -> None:
        # Deliberate: a driver wants to know it is raining even in a gale,
        # and the gale is already carried by the risk level beside it.
        self.assertEqual(describe(rain_in=0.02, wind_mph=60.0), "Rain")

    def test_wind_is_described_when_it_is_dry(self) -> None:
        self.assertEqual(describe(wind_mph=40.0), "High wind")
        self.assertEqual(describe(wind_mph=25.0), "Breezy")


class ConstantTests(unittest.TestCase):
    """The thresholds live in one place, and that place is what runs."""

    def test_every_rule_is_reachable(self) -> None:
        # Feeding each rule exactly its own threshold, with everything else
        # calm, must produce that rule's word. A rule that can never be
        # reached - shadowed by an earlier one - fails here.
        for factor, threshold, word in CONDITION_THRESHOLDS:
            argument = "wind_mph" if factor == "wind" else f"{factor}_in"
            with self.subTest(word=word):
                self.assertEqual(describe(**{argument: threshold}), word)

    def test_the_rules_are_ordered_strongest_first_within_a_factor(self) -> None:
        for factor in ("rain", "wind", "snow"):
            limits = [limit for name, limit, _ in CONDITION_THRESHOLDS if name == factor]
            self.assertEqual(limits, sorted(limits, reverse=True))
