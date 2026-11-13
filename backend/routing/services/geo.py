"""Geometry helpers for working with a route line.

A route arrives from OSRM as a GeoJSON ``LineString``: a list of
``(longitude, latitude)`` pairs. Everything here speaks that same order, so
coordinates can be passed straight through without being flipped around.

The important job of this module is ``sample_checkpoints``: walking along a
route and dropping a checkpoint every N miles, which is where the app later
looks up the weather.
"""

from __future__ import annotations

import math
from bisect import bisect_right
from dataclasses import dataclass

#: A point on the map as ``(longitude, latitude)``, matching GeoJSON order.
Coordinate = tuple[float, float]

#: Mean radius of the Earth in miles.
EARTH_RADIUS_MILES = 3958.7613

#: Distances below this are treated as the same spot (about 5 feet).
DISTANCE_EPSILON_MILES = 1e-3


@dataclass(frozen=True)
class Checkpoint:
    """One weather sampling point: how far along the route it is, and where."""

    mile: float
    lat: float
    lon: float


def haversine_miles(start: Coordinate, end: Coordinate) -> float:
    """Great-circle distance in miles between two ``(lon, lat)`` points."""
    start_lon, start_lat = start
    end_lon, end_lat = end

    lat1 = math.radians(start_lat)
    lat2 = math.radians(end_lat)
    delta_lat = math.radians(end_lat - start_lat)
    delta_lon = math.radians(end_lon - start_lon)

    a = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    )
    return 2 * EARTH_RADIUS_MILES * math.asin(math.sqrt(a))


def cumulative_miles(line: list[Coordinate]) -> list[float]:
    """Distance from the start of the line to each of its points.

    The result is the same length as ``line`` and starts at 0.0, so
    ``cumulative_miles(line)[-1]`` is the total length of the line.
    """
    if not line:
        return []

    distances = [0.0]
    for previous, current in zip(line, line[1:], strict=False):
        distances.append(distances[-1] + haversine_miles(previous, current))
    return distances


def interpolate_point(line: list[Coordinate], cumulative: list[float], mile: float) -> Coordinate:
    """The ``(lon, lat)`` point that sits ``mile`` miles along the line.

    Points between two shape points are interpolated in a straight line.
    Route shape points are only a mile or two apart, so the error is tiny.
    Values before the start or past the end clamp to the endpoints.
    """
    if not line:
        raise ValueError("Cannot interpolate a point on an empty line.")
    if len(line) == 1 or mile <= 0:
        return line[0]
    if mile >= cumulative[-1]:
        return line[-1]

    # The first shape point at or past `mile`, so the segment is index-1 -> index.
    index = bisect_right(cumulative, mile)
    index = min(index, len(line) - 1)

    segment_start = cumulative[index - 1]
    segment_length = cumulative[index] - segment_start
    if segment_length <= 0:
        return line[index]

    fraction = (mile - segment_start) / segment_length
    start_lon, start_lat = line[index - 1]
    end_lon, end_lat = line[index]
    return (
        start_lon + (end_lon - start_lon) * fraction,
        start_lat + (end_lat - start_lat) * fraction,
    )


def sample_checkpoints(line: list[Coordinate], interval_miles: float) -> list[Checkpoint]:
    """Drop a checkpoint at the origin, every ``interval_miles``, and at the destination.

    The final checkpoint is always the destination, even when the route length
    is not a whole number of intervals. If the destination happens to land on
    an interval it is not added twice.
    """
    if interval_miles <= 0:
        raise ValueError("The sampling interval must be greater than zero.")
    if not line:
        raise ValueError("Cannot sample checkpoints on an empty line.")

    cumulative = cumulative_miles(line)
    total_miles = cumulative[-1]

    miles: list[float] = []
    mile = 0.0
    while mile < total_miles - DISTANCE_EPSILON_MILES:
        miles.append(mile)
        mile += interval_miles
    miles.append(total_miles)

    checkpoints: list[Checkpoint] = []
    for position in miles:
        lon, lat = interpolate_point(line, cumulative, position)
        checkpoints.append(Checkpoint(mile=position, lat=lat, lon=lon))
    return checkpoints


def rescale_checkpoints(checkpoints: list[Checkpoint], total_miles: float) -> list[Checkpoint]:
    """Stretch mile markers so the last one lands exactly on ``total_miles``.

    Checkpoints are placed by measuring the drawn route line, but the routing
    service reports its own distance for the same route, and the two differ
    by a fraction of a percent. Rescaling keeps every figure the driver sees
    - the coverage per risk level, the arrival time, the distance - in
    agreement with each other. Positions on the map are unchanged.
    """
    measured = checkpoints[-1].mile if checkpoints else 0.0
    if measured <= 0 or total_miles <= 0:
        return checkpoints
    scale = total_miles / measured
    return [
        Checkpoint(mile=checkpoint.mile * scale, lat=checkpoint.lat, lon=checkpoint.lon)
        for checkpoint in checkpoints
    ]


def initial_bearing(start: Coordinate, end: Coordinate) -> float:
    """Compass bearing in degrees (0 = north) when heading from start to end."""
    start_lon, start_lat = start
    end_lon, end_lat = end

    lat1 = math.radians(start_lat)
    lat2 = math.radians(end_lat)
    delta_lon = math.radians(end_lon - start_lon)

    y = math.sin(delta_lon) * math.cos(lat2)
    x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(delta_lon)
    return math.degrees(math.atan2(y, x)) % 360


def point_at_bearing(
    start: Coordinate, bearing_degrees: float, distance_miles: float
) -> Coordinate:
    """The ``(lon, lat)`` point reached by travelling a bearing for a distance."""
    angular_distance = distance_miles / EARTH_RADIUS_MILES
    bearing = math.radians(bearing_degrees)
    start_lon, start_lat = start
    lat1 = math.radians(start_lat)
    lon1 = math.radians(start_lon)

    lat2 = math.asin(
        math.sin(lat1) * math.cos(angular_distance)
        + math.cos(lat1) * math.sin(angular_distance) * math.cos(bearing)
    )
    lon2 = lon1 + math.atan2(
        math.sin(bearing) * math.sin(angular_distance) * math.cos(lat1),
        math.cos(angular_distance) - math.sin(lat1) * math.sin(lat2),
    )
    return (math.degrees(lon2), math.degrees(lat2))
