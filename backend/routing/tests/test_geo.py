"""Tests for the route geometry helpers.

Distances are checked against known real-world values, and the checkpoint
sampler is checked on a line of a known length so the expected number of
checkpoints can be worked out by hand.
"""

import unittest

from routing.services.geo import (
    Coordinate,
    cumulative_miles,
    haversine_miles,
    initial_bearing,
    interpolate_point,
    point_at_bearing,
    rescale_checkpoints,
    sample_checkpoints,
)

# Roughly 69 miles per degree of latitude, so these are easy to reason about.
DALLAS: Coordinate = (-96.7970, 32.7767)
DENVER: Coordinate = (-104.9903, 39.7392)


def north_line(start: Coordinate, total_miles: float, steps: int) -> list[Coordinate]:
    """A line heading due north of an exact length, split into equal steps.

    Built with ``point_at_bearing`` so the line really is ``total_miles``
    long, which makes the expected checkpoint counts exact.
    """
    return [point_at_bearing(start, 0.0, total_miles * step / steps) for step in range(steps + 1)]


class HaversineTests(unittest.TestCase):
    def test_known_distance_dallas_to_denver(self) -> None:
        # The real great-circle distance is about 663 miles.
        self.assertAlmostEqual(haversine_miles(DALLAS, DENVER), 663, delta=5)

    def test_same_point_is_zero(self) -> None:
        self.assertEqual(haversine_miles(DALLAS, DALLAS), 0.0)

    def test_one_degree_of_latitude_is_about_69_miles(self) -> None:
        north = (DALLAS[0], DALLAS[1] + 1.0)
        self.assertAlmostEqual(haversine_miles(DALLAS, north), 69.1, delta=0.2)

    def test_distance_is_symmetric(self) -> None:
        self.assertAlmostEqual(
            haversine_miles(DALLAS, DENVER), haversine_miles(DENVER, DALLAS), places=6
        )


class CumulativeMilesTests(unittest.TestCase):
    def test_starts_at_zero_and_matches_line_length(self) -> None:
        line = north_line(DALLAS, total_miles=140.0, steps=4)
        distances = cumulative_miles(line)

        self.assertEqual(len(distances), len(line))
        self.assertEqual(distances[0], 0.0)
        self.assertAlmostEqual(distances[-1], 140.0, places=6)

    def test_is_increasing(self) -> None:
        distances = cumulative_miles(north_line(DALLAS, 140.0, 8))
        self.assertEqual(distances, sorted(distances))

    def test_empty_line(self) -> None:
        self.assertEqual(cumulative_miles([]), [])


class InterpolatePointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.line = north_line(DALLAS, total_miles=100.0, steps=2)
        self.cumulative = cumulative_miles(self.line)
        self.total = self.cumulative[-1]

    def test_start_and_end(self) -> None:
        self.assertEqual(interpolate_point(self.line, self.cumulative, 0.0), self.line[0])
        self.assertEqual(interpolate_point(self.line, self.cumulative, self.total), self.line[-1])

    def test_halfway_is_the_middle_shape_point(self) -> None:
        middle = interpolate_point(self.line, self.cumulative, self.total / 2)
        self.assertAlmostEqual(middle[0], self.line[1][0], places=4)
        self.assertAlmostEqual(middle[1], self.line[1][1], places=4)

    def test_quarter_of_the_way_along(self) -> None:
        quarter = interpolate_point(self.line, self.cumulative, 25.0)
        self.assertAlmostEqual(haversine_miles(self.line[0], quarter), 25.0, delta=0.05)

    def test_point_is_the_right_distance_from_the_start(self) -> None:
        point = interpolate_point(self.line, self.cumulative, 50.0)
        self.assertAlmostEqual(haversine_miles(self.line[0], point), 50.0, delta=0.1)

    def test_values_outside_the_line_clamp_to_the_ends(self) -> None:
        self.assertEqual(interpolate_point(self.line, self.cumulative, -10.0), self.line[0])
        self.assertEqual(
            interpolate_point(self.line, self.cumulative, self.total + 10.0), self.line[-1]
        )

    def test_empty_line_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            interpolate_point([], [], 1.0)


class SampleCheckpointsTests(unittest.TestCase):
    def setUp(self) -> None:
        # Exactly 100 miles long, so the checkpoint counts can be worked out by hand.
        self.line = north_line(DALLAS, total_miles=100.0, steps=50)
        self.total = cumulative_miles(self.line)[-1]

    def test_counts_for_each_sampling_interval(self) -> None:
        # A 100 mile trip: every 10 miles gives 0..90 plus the destination.
        expected_counts = {10: 11, 25: 5, 50: 3}
        for interval, expected in expected_counts.items():
            with self.subTest(interval=interval):
                checkpoints = sample_checkpoints(self.line, interval)
                self.assertEqual(len(checkpoints), expected)

    def test_first_checkpoint_is_the_origin(self) -> None:
        first = sample_checkpoints(self.line, 25)[0]
        self.assertEqual(first.mile, 0.0)
        self.assertAlmostEqual(first.lon, self.line[0][0], places=6)
        self.assertAlmostEqual(first.lat, self.line[0][1], places=6)

    def test_last_checkpoint_is_the_destination(self) -> None:
        for interval in (10, 25, 50):
            with self.subTest(interval=interval):
                last = sample_checkpoints(self.line, interval)[-1]
                self.assertAlmostEqual(last.mile, self.total, places=6)
                self.assertAlmostEqual(last.lon, self.line[-1][0], places=6)
                self.assertAlmostEqual(last.lat, self.line[-1][1], places=6)

    def test_checkpoints_are_evenly_spaced(self) -> None:
        checkpoints = sample_checkpoints(self.line, 25)
        self.assertEqual([point.mile for point in checkpoints[:-1]], [0.0, 25.0, 50.0, 75.0])

    def test_destination_on_an_exact_interval_is_not_duplicated(self) -> None:
        checkpoints = sample_checkpoints(self.line, self.total)
        self.assertEqual(len(checkpoints), 2)
        self.assertEqual(checkpoints[0].mile, 0.0)
        self.assertAlmostEqual(checkpoints[1].mile, self.total, places=6)

    def test_interval_longer_than_the_route_gives_origin_and_destination(self) -> None:
        checkpoints = sample_checkpoints(self.line, 500)
        self.assertEqual(len(checkpoints), 2)

    def test_bad_input_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            sample_checkpoints(self.line, 0)
        with self.assertRaises(ValueError):
            sample_checkpoints([], 25)


class BearingTests(unittest.TestCase):
    def test_due_north_is_zero_degrees(self) -> None:
        north = (DALLAS[0], DALLAS[1] + 1)
        self.assertAlmostEqual(initial_bearing(DALLAS, north), 0.0, places=6)

    def test_due_east_is_ninety_degrees(self) -> None:
        east = (DALLAS[0] + 1, DALLAS[1])
        self.assertAlmostEqual(initial_bearing(DALLAS, east), 90.0, delta=0.5)

    def test_point_at_bearing_lands_the_right_distance_away(self) -> None:
        moved = point_at_bearing(DALLAS, 90.0, 100.0)
        self.assertAlmostEqual(haversine_miles(DALLAS, moved), 100.0, delta=0.1)

    def test_point_at_bearing_goes_the_right_way(self) -> None:
        east_of_dallas = point_at_bearing(DALLAS, 90.0, 100.0)
        self.assertGreater(east_of_dallas[0], DALLAS[0])
        west_of_dallas = point_at_bearing(DALLAS, 270.0, 100.0)
        self.assertLess(west_of_dallas[0], DALLAS[0])


class RescaleCheckpointsTests(unittest.TestCase):
    """Mile markers are put on the routing service's own distance."""

    def test_last_checkpoint_lands_on_the_reported_distance(self) -> None:
        line = north_line(DALLAS, total_miles=100.0, steps=10)
        checkpoints = rescale_checkpoints(sample_checkpoints(line, 25), 101.0)

        self.assertAlmostEqual(checkpoints[-1].mile, 101.0, places=6)
        self.assertAlmostEqual(checkpoints[1].mile, 25.25, places=6)

    def test_positions_on_the_map_do_not_move(self) -> None:
        line = north_line(DALLAS, total_miles=100.0, steps=10)
        before = sample_checkpoints(line, 25)
        after = rescale_checkpoints(before, 101.0)

        self.assertEqual([(c.lat, c.lon) for c in before], [(c.lat, c.lon) for c in after])

    def test_degenerate_input_is_returned_unchanged(self) -> None:
        line = north_line(DALLAS, total_miles=100.0, steps=10)
        checkpoints = sample_checkpoints(line, 25)

        self.assertEqual(rescale_checkpoints([], 50.0), [])
        self.assertEqual(rescale_checkpoints(checkpoints, 0.0), checkpoints)
