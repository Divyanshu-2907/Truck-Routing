"""A command-line way to check the routing pipeline against the real APIs.

Example::

    python manage.py try_routes "Dallas, TX" "Denver, CO"
    python manage.py try_routes "Dallas, TX" "Denver, CO" --interval 10

It geocodes both places, fetches the route options and samples checkpoints,
then prints a short summary of each route. Handy for a quick sanity check
without opening the browser.
"""

from __future__ import annotations

from typing import Any

from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError

from routing.services.geo import sample_checkpoints
from routing.services.geocode import geocode
from routing.services.http_client import ExternalServiceError
from routing.services.routes import get_routes

SAMPLING_INTERVALS = (10, 25, 50)


class Command(BaseCommand):
    """Print a route summary for two place names."""

    help = "Look up two places, fetch the route options and print a summary."

    def add_arguments(self, parser: Any) -> None:
        """Declare the command line arguments."""
        parser.add_argument("origin", help='Where the trip starts, e.g. "Dallas, TX"')
        parser.add_argument("destination", help='Where the trip ends, e.g. "Denver, CO"')
        parser.add_argument(
            "--interval",
            type=int,
            default=25,
            choices=SAMPLING_INTERVALS,
            help="Miles between weather checkpoints (default: 25).",
        )

    def handle(self, *_args: Any, **options: Any) -> None:
        """Run the lookup and print one line per route."""
        origin_name: str = options["origin"]
        destination_name: str = options["destination"]
        interval: int = options["interval"]

        try:
            origin = self._find_place(origin_name)
            destination = self._find_place(destination_name)
            routes = get_routes(
                (origin.lon, origin.lat), (destination.lon, destination.lat), cache=cache
            )
        except ExternalServiceError as error:
            raise CommandError(str(error)) from error

        self.stdout.write(f"From: {origin.label}")
        self.stdout.write(f"To:   {destination.label}")
        self.stdout.write(f"Checkpoints every {interval} miles\n")

        for route in routes:
            checkpoints = sample_checkpoints(route.geometry, interval)
            self.stdout.write(
                f"{route.label}: "
                f"{route.distance_miles:,.0f} miles, "
                f"{route.duration_hours:.1f} hours, "
                f"{len(checkpoints)} checkpoints "
                f"[{route.source}]"
            )

    def _find_place(self, query: str) -> Any:
        """Geocode a place name, failing loudly when nothing matches."""
        matches = geocode(query, cache=cache)
        if not matches:
            raise CommandError(f'No place in the US matched "{query}".')
        return matches[0]
