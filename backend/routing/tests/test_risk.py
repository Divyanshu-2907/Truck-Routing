"""Tests for the per-checkpoint risk rules.

Every threshold in the brief's table is checked on both sides of its
boundary, because an off-by-a-hair mistake here would silently change which
route the app recommends.
"""

import unittest

from routing.services.risk import (
    RiskLevel,
    assess,
    rain_level,
    snow_level,
    wind_level,
)

CALM_WIND = 0.0
NO_RAIN = 0.0
NO_SNOW = 0.0
LIGHT_LOAD = 10_000.0


class WindLevelTests(unittest.TestCase):
    """Wind: <25 Low, 25-34 Moderate, 35-44 High, 45-54 Severe, >=55 No Travel."""

    def test_boundaries(self) -> None:
        cases: list[tuple[float, RiskLevel]] = [
            (0.0, RiskLevel.LOW),
            (24.9, RiskLevel.LOW),
            (25.0, RiskLevel.MODERATE),
            (34.9, RiskLevel.MODERATE),
            (35.0, RiskLevel.HIGH),
            (44.9, RiskLevel.HIGH),
            (45.0, RiskLevel.SEVERE),
            (54.9, RiskLevel.SEVERE),
            (55.0, RiskLevel.NO_TRAVEL),
            (120.0, RiskLevel.NO_TRAVEL),
        ]
        for mph, expected in cases:
            with self.subTest(mph=mph):
                self.assertEqual(wind_level(mph), expected)


class RainLevelTests(unittest.TestCase):
    """Rain: <0.10 Low, 0.10-0.25 Moderate, 0.25-0.50 High, 0.50-1.00 Severe, >1.00 No Travel."""

    def test_boundaries(self) -> None:
        cases: list[tuple[float, RiskLevel]] = [
            (0.0, RiskLevel.LOW),
            (0.099, RiskLevel.LOW),
            (0.10, RiskLevel.MODERATE),
            (0.249, RiskLevel.MODERATE),
            (0.25, RiskLevel.HIGH),
            (0.499, RiskLevel.HIGH),
            (0.50, RiskLevel.SEVERE),
            (1.00, RiskLevel.SEVERE),
            (1.01, RiskLevel.NO_TRAVEL),
            (3.0, RiskLevel.NO_TRAVEL),
        ]
        for inches, expected in cases:
            with self.subTest(inches=inches):
                self.assertEqual(rain_level(inches), expected)


class SnowLevelTests(unittest.TestCase):
    """Snow: <0.5 Low, 0.5-1.0 Moderate, 1.0-2.0 High, 2.0-3.0 Severe, >3.0 No Travel."""

    def test_boundaries(self) -> None:
        cases: list[tuple[float, RiskLevel]] = [
            (0.0, RiskLevel.LOW),
            (0.49, RiskLevel.LOW),
            (0.5, RiskLevel.MODERATE),
            (0.99, RiskLevel.MODERATE),
            (1.0, RiskLevel.HIGH),
            (1.99, RiskLevel.HIGH),
            (2.0, RiskLevel.SEVERE),
            (3.0, RiskLevel.SEVERE),
            (3.01, RiskLevel.NO_TRAVEL),
            (8.0, RiskLevel.NO_TRAVEL),
        ]
        for inches, expected in cases:
            with self.subTest(inches=inches):
                self.assertEqual(snow_level(inches), expected)


class WorstFactorWinsTests(unittest.TestCase):
    """The checkpoint level is the worst of the three weather factors."""

    def test_rain_beats_calmer_wind_and_snow(self) -> None:
        result = assess(wind_mph=10.0, rain_in=0.60, snow_in=0.2, load_lb=LIGHT_LOAD)
        self.assertEqual(result.level, RiskLevel.SEVERE)
        self.assertEqual(result.driver, "rain")
        self.assertEqual(result.reason, "Rain 0.6 in/hr -> Severe")

    def test_snow_beats_calmer_wind_and_rain(self) -> None:
        result = assess(wind_mph=26.0, rain_in=0.15, snow_in=1.4, load_lb=LIGHT_LOAD)
        self.assertEqual(result.level, RiskLevel.HIGH)
        self.assertEqual(result.driver, "snow")
        self.assertEqual(result.reason, "Snow 1.4 in/hr -> High")

    def test_wind_beats_calmer_rain_and_snow(self) -> None:
        result = assess(wind_mph=47.0, rain_in=0.05, snow_in=0.0, load_lb=LIGHT_LOAD)
        self.assertEqual(result.level, RiskLevel.SEVERE)
        self.assertEqual(result.driver, "wind")
        self.assertEqual(result.reason, "Wind 47 mph -> Severe")

    def test_one_no_travel_factor_makes_the_checkpoint_no_travel(self) -> None:
        result = assess(wind_mph=10.0, rain_in=0.0, snow_in=4.0, load_lb=LIGHT_LOAD)
        self.assertEqual(result.level, RiskLevel.NO_TRAVEL)
        self.assertEqual(result.driver, "snow")

    def test_per_factor_levels_are_reported_individually(self) -> None:
        result = assess(wind_mph=36.0, rain_in=0.30, snow_in=0.6, load_lb=LIGHT_LOAD)
        self.assertEqual(result.wind, RiskLevel.HIGH)
        self.assertEqual(result.rain, RiskLevel.HIGH)
        self.assertEqual(result.snow, RiskLevel.MODERATE)
        self.assertEqual(result.level, RiskLevel.HIGH)

    def test_all_factors_calm_is_low(self) -> None:
        result = assess(CALM_WIND, NO_RAIN, NO_SNOW, LIGHT_LOAD)
        self.assertEqual(result.level, RiskLevel.LOW)
        self.assertEqual(result.reason, "Wind 0 mph -> Low")


class SevereWindLoadRuleTests(unittest.TestCase):
    """Wind 45-54 mph with a load over 30,000 lb becomes No Travel."""

    def test_at_the_limit_stays_severe(self) -> None:
        result = assess(wind_mph=47.0, rain_in=NO_RAIN, snow_in=NO_SNOW, load_lb=30_000.0)
        self.assertEqual(result.level, RiskLevel.SEVERE)
        self.assertEqual(result.driver, "wind")

    def test_one_pound_over_the_limit_is_no_travel(self) -> None:
        result = assess(wind_mph=47.0, rain_in=NO_RAIN, snow_in=NO_SNOW, load_lb=30_001.0)
        self.assertEqual(result.level, RiskLevel.NO_TRAVEL)
        self.assertEqual(result.driver, "load")

    def test_reason_names_wind_and_load(self) -> None:
        result = assess(wind_mph=47.0, rain_in=NO_RAIN, snow_in=NO_SNOW, load_lb=38_000.0)
        self.assertEqual(result.reason, "Wind 47 mph + 38,000 lb load -> No Travel")

    def test_rule_does_not_apply_below_45_mph(self) -> None:
        result = assess(wind_mph=44.9, rain_in=NO_RAIN, snow_in=NO_SNOW, load_lb=30_001.0)
        self.assertEqual(result.level, RiskLevel.HIGH)

    def test_rule_applies_across_the_whole_severe_band(self) -> None:
        for mph in (45.0, 54.9):
            with self.subTest(mph=mph):
                result = assess(mph, NO_RAIN, NO_SNOW, load_lb=30_001.0)
                self.assertEqual(result.level, RiskLevel.NO_TRAVEL)


class HighWindLoadRuleTests(unittest.TestCase):
    """Wind 35-44 mph with a load over 40,000 lb becomes at least Severe."""

    def test_at_the_limit_stays_high(self) -> None:
        result = assess(wind_mph=38.0, rain_in=NO_RAIN, snow_in=NO_SNOW, load_lb=40_000.0)
        self.assertEqual(result.level, RiskLevel.HIGH)
        self.assertEqual(result.driver, "wind")

    def test_one_pound_over_the_limit_is_severe(self) -> None:
        result = assess(wind_mph=38.0, rain_in=NO_RAIN, snow_in=NO_SNOW, load_lb=40_001.0)
        self.assertEqual(result.level, RiskLevel.SEVERE)
        self.assertEqual(result.driver, "load")
        self.assertEqual(result.reason, "Wind 38 mph + 40,001 lb load -> Severe")

    def test_rule_does_not_apply_below_35_mph(self) -> None:
        result = assess(wind_mph=34.9, rain_in=NO_RAIN, snow_in=NO_SNOW, load_lb=45_000.0)
        self.assertEqual(result.level, RiskLevel.MODERATE)

    def test_rule_applies_across_the_whole_high_band(self) -> None:
        for mph in (35.0, 44.9):
            with self.subTest(mph=mph):
                result = assess(mph, NO_RAIN, NO_SNOW, load_lb=40_001.0)
                self.assertEqual(result.level, RiskLevel.SEVERE)

    def test_worse_weather_still_wins_over_the_load_floor(self) -> None:
        # The load rule only sets a floor of Severe; No Travel rain beats it.
        result = assess(wind_mph=38.0, rain_in=1.5, snow_in=NO_SNOW, load_lb=45_000.0)
        self.assertEqual(result.level, RiskLevel.NO_TRAVEL)
        self.assertEqual(result.driver, "rain")


class NoTravelWindTests(unittest.TestCase):
    """Wind of 55 mph or more is No Travel whatever the truck is carrying."""

    def test_no_travel_for_every_load(self) -> None:
        for load_lb in (0.0, 30_000.0, 80_000.0):
            with self.subTest(load_lb=load_lb):
                result = assess(55.0, NO_RAIN, NO_SNOW, load_lb)
                self.assertEqual(result.level, RiskLevel.NO_TRAVEL)
                self.assertEqual(result.driver, "wind")


class RiskLevelTests(unittest.TestCase):
    """The enum is ordered worst-last so that max() finds the worst level."""

    def test_order(self) -> None:
        self.assertLess(RiskLevel.LOW, RiskLevel.MODERATE)
        self.assertLess(RiskLevel.MODERATE, RiskLevel.HIGH)
        self.assertLess(RiskLevel.HIGH, RiskLevel.SEVERE)
        self.assertLess(RiskLevel.SEVERE, RiskLevel.NO_TRAVEL)

    def test_labels(self) -> None:
        self.assertEqual(RiskLevel.LOW.label, "Low")
        self.assertEqual(RiskLevel.MODERATE.label, "Moderate")
        self.assertEqual(RiskLevel.HIGH.label, "High")
        self.assertEqual(RiskLevel.SEVERE.label, "Severe")
        self.assertEqual(RiskLevel.NO_TRAVEL.label, "No Travel")
