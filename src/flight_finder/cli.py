"""Demo CLI: search IAD -> LAX flights and display top 5."""

from __future__ import annotations

import logging
import sys

from flight_finder.ranking import rank_flights
from flight_finder.scraper import FlightSearchParams, search_flights


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    params = FlightSearchParams(
        origin="IAD",
        destination="LAX",
        departure_date="2026-04-01",
        return_date="2026-04-07",
        trip_type="round-trip",
        seat="economy",
        adults=1,
    )

    print(f"\nSearching flights: {params.origin} -> {params.destination}")
    print(f"Dates: {params.departure_date} to {params.return_date}")
    print(f"Seat: {params.seat}, Adults: {params.adults}\n")

    try:
        result = search_flights(params)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        sys.exit(1)

    ranked = rank_flights(result.flights)
    top_n = ranked[:5]

    print(f"Price trend: {result.current_price}")
    print(f"Found {len(result.flights)} flights, showing top {len(top_n)}:\n")
    print(f"{'#':<4} {'Airline':<25} {'Price':<10} {'Duration':<12} {'Stops':<8} {'Departure':<15} {'Arrival'}")
    print("-" * 95)

    for rf in top_n:
        f = rf.flight
        price_str = f"${rf.price_dollars}" if rf.price_dollars else "N/A"
        if isinstance(f.stops, int) and f.stops == 0:
            stops_str = "Nonstop"
        elif isinstance(f.stops, int):
            stops_str = f"{f.stops} stop{'s' if f.stops > 1 else ''}"
        else:
            stops_str = str(f.stops)
        print(f"{rf.rank:<4} {f.name:<25} {price_str:<10} {f.duration:<12} {stops_str:<8} {f.departure:<15} {f.arrival}")

    print()


if __name__ == "__main__":
    main()
