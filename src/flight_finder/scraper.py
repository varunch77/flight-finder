"""Flight search with retry logic and rate limiting."""

from __future__ import annotations

import logging
import random
import time
from dataclasses import dataclass, field

from fast_flights import FlightData, Passengers, Result, get_flights

logger = logging.getLogger(__name__)

# Exceptions that indicate a transient failure worth retrying
_RETRYABLE_EXCEPTIONS = (AssertionError, RuntimeError, ConnectionError, TimeoutError, OSError)

# Exceptions that should never be retried
_NON_RETRYABLE_EXCEPTIONS = (ValueError, TypeError, KeyboardInterrupt)


class RateLimiter:
    """Enforces a minimum interval between requests."""

    def __init__(self, min_interval: float = 1.5) -> None:
        self.min_interval = min_interval
        self._last_request: float = 0.0

    def wait(self) -> None:
        """Sleep if needed to enforce the minimum interval."""
        if self.min_interval <= 0:
            return
        now = time.monotonic()
        elapsed = now - self._last_request
        if self._last_request > 0 and elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self._last_request = time.monotonic()


@dataclass
class FlightSearchParams:
    """Parameters for a flight search."""

    origin: str
    destination: str
    departure_date: str  # YYYY-MM-DD
    return_date: str | None = None  # None for one-way
    trip_type: str = "round-trip"  # "round-trip", "one-way", "multi-city"
    seat: str = "economy"
    adults: int = 1
    children: int = 0
    infants_in_seat: int = 0
    infants_on_lap: int = 0
    max_stops: int | None = None

    def build_flight_data(self) -> list[FlightData]:
        """Build FlightData list for get_flights()."""
        legs = [
            FlightData(
                date=self.departure_date,
                from_airport=self.origin,
                to_airport=self.destination,
                max_stops=self.max_stops,
            )
        ]
        if self.trip_type == "round-trip" and self.return_date:
            legs.append(
                FlightData(
                    date=self.return_date,
                    from_airport=self.destination,
                    to_airport=self.origin,
                    max_stops=self.max_stops,
                )
            )
        return legs


def search_flights(
    params: FlightSearchParams,
    *,
    max_retries: int = 3,
    base_delay: float = 2.0,
    rate_limiter: RateLimiter | None = None,
) -> Result:
    """Search for flights with retry logic and rate limiting.

    Raises the last exception if all retries are exhausted.
    """
    if rate_limiter is None:
        rate_limiter = RateLimiter()

    flight_data = params.build_flight_data()
    last_exception: Exception | None = None

    for attempt in range(1, max_retries + 1):
        rate_limiter.wait()
        try:
            logger.info("Attempt %d/%d: searching %s → %s", attempt, max_retries, params.origin, params.destination)
            result = get_flights(
                flight_data=flight_data,
                trip=params.trip_type,
                adults=params.adults,
                children=params.children,
                infants_in_seat=params.infants_in_seat,
                infants_on_lap=params.infants_on_lap,
                seat=params.seat,
                fetch_mode="common",
                max_stops=params.max_stops,
            )
            if result is None:
                logger.warning("Attempt %d/%d: get_flights returned None", attempt, max_retries)
                last_exception = RuntimeError("get_flights returned None")
                if attempt < max_retries:
                    _backoff_sleep(attempt, base_delay)
                continue
            logger.info("Success on attempt %d: found %d flights", attempt, len(result.flights))
            return result
        except _NON_RETRYABLE_EXCEPTIONS:
            raise
        except _RETRYABLE_EXCEPTIONS as exc:
            last_exception = exc
            logger.warning("Attempt %d/%d failed (%s): %s", attempt, max_retries, type(exc).__name__, exc)
            if attempt < max_retries:
                _backoff_sleep(attempt, base_delay)

    raise last_exception  # type: ignore[misc]


def _backoff_sleep(attempt: int, base_delay: float) -> None:
    """Sleep with exponential backoff + random jitter."""
    delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 1)
    logger.info("Backing off for %.1fs before retry", delay)
    time.sleep(delay)
