"""Tests for scraper retry logic and rate limiting."""

from dataclasses import dataclass
from unittest.mock import patch

import pytest

from flight_finder.scraper import FlightSearchParams, RateLimiter, search_flights


@dataclass
class FakeFlight:
    name: str = "TestAir"
    price: str = "$200"
    departure: str = "10:00 AM"
    arrival: str = "1:00 PM"
    arrival_time_ahead: str = ""
    duration: str = "3h 0m"
    stops: int = 0
    delay: str | None = None
    is_best: bool = False


@dataclass
class FakeResult:
    current_price: str = "typical"
    flights: list = None

    def __post_init__(self):
        if self.flights is None:
            self.flights = [FakeFlight()]


PARAMS = FlightSearchParams(
    origin="IAD",
    destination="LAX",
    departure_date="2026-04-01",
    return_date="2026-04-07",
)

NO_DELAY_LIMITER = RateLimiter(0)


class TestSearchFlightsRetry:
    """Tests for retry logic in search_flights."""

    @patch("flight_finder.scraper.get_flights")
    def test_success_on_first_attempt(self, mock_gf):
        mock_gf.return_value = FakeResult()
        result = search_flights(PARAMS, rate_limiter=NO_DELAY_LIMITER)
        assert mock_gf.call_count == 1
        assert len(result.flights) == 1

    @patch("flight_finder.scraper.get_flights")
    @patch("flight_finder.scraper._backoff_sleep")
    def test_retry_on_assertion_error(self, mock_sleep, mock_gf):
        mock_gf.side_effect = [AssertionError("503"), FakeResult()]
        result = search_flights(PARAMS, rate_limiter=NO_DELAY_LIMITER)
        assert mock_gf.call_count == 2
        assert len(result.flights) == 1
        mock_sleep.assert_called_once()

    @patch("flight_finder.scraper.get_flights")
    @patch("flight_finder.scraper._backoff_sleep")
    def test_retry_on_runtime_error(self, mock_sleep, mock_gf):
        mock_gf.side_effect = [RuntimeError("No flights found"), FakeResult()]
        result = search_flights(PARAMS, rate_limiter=NO_DELAY_LIMITER)
        assert mock_gf.call_count == 2
        assert len(result.flights) == 1

    @patch("flight_finder.scraper.get_flights")
    @patch("flight_finder.scraper._backoff_sleep")
    def test_max_retries_exhausted(self, mock_sleep, mock_gf):
        mock_gf.side_effect = AssertionError("503")
        with pytest.raises(AssertionError, match="503"):
            search_flights(PARAMS, max_retries=3, rate_limiter=NO_DELAY_LIMITER)
        assert mock_gf.call_count == 3

    @patch("flight_finder.scraper.get_flights")
    def test_non_retryable_type_error(self, mock_gf):
        mock_gf.side_effect = TypeError("bad type")
        with pytest.raises(TypeError, match="bad type"):
            search_flights(PARAMS, rate_limiter=NO_DELAY_LIMITER)
        assert mock_gf.call_count == 1

    @patch("flight_finder.scraper.get_flights")
    def test_non_retryable_value_error(self, mock_gf):
        mock_gf.side_effect = ValueError("bad value")
        with pytest.raises(ValueError, match="bad value"):
            search_flights(PARAMS, rate_limiter=NO_DELAY_LIMITER)
        assert mock_gf.call_count == 1

    @patch("flight_finder.scraper.get_flights")
    @patch("flight_finder.scraper._backoff_sleep")
    def test_none_return_triggers_retry(self, mock_sleep, mock_gf):
        mock_gf.side_effect = [None, FakeResult()]
        result = search_flights(PARAMS, rate_limiter=NO_DELAY_LIMITER)
        assert mock_gf.call_count == 2
        assert len(result.flights) == 1

    @patch("flight_finder.scraper.get_flights")
    @patch("flight_finder.scraper._backoff_sleep")
    def test_none_return_all_retries_exhausted(self, mock_sleep, mock_gf):
        mock_gf.return_value = None
        with pytest.raises(RuntimeError, match="get_flights returned None"):
            search_flights(PARAMS, max_retries=2, rate_limiter=NO_DELAY_LIMITER)
        assert mock_gf.call_count == 2

    @patch("flight_finder.scraper.get_flights")
    @patch("flight_finder.scraper._backoff_sleep")
    def test_backoff_called_between_retries(self, mock_backoff, mock_gf):
        """Verify _backoff_sleep is called for each retry (not after last attempt)."""
        mock_gf.side_effect = [
            AssertionError("fail1"),
            AssertionError("fail2"),
            AssertionError("fail3"),
        ]
        with pytest.raises(AssertionError):
            search_flights(PARAMS, max_retries=3, base_delay=2.0, rate_limiter=NO_DELAY_LIMITER)
        # Backoff called after attempt 1 and 2, not after 3
        assert mock_backoff.call_count == 2
        mock_backoff.assert_any_call(1, 2.0)
        mock_backoff.assert_any_call(2, 2.0)


class TestBackoffSleep:
    """Test _backoff_sleep delay calculations directly."""

    @patch("flight_finder.scraper.random.uniform", return_value=0.5)
    @patch("flight_finder.scraper.time.sleep")
    def test_backoff_attempt_1(self, mock_sleep, mock_rand):
        from flight_finder.scraper import _backoff_sleep
        _backoff_sleep(1, 2.0)
        mock_sleep.assert_called_once_with(2.5)  # 2 * 2^0 + 0.5

    @patch("flight_finder.scraper.random.uniform", return_value=0.5)
    @patch("flight_finder.scraper.time.sleep")
    def test_backoff_attempt_2(self, mock_sleep, mock_rand):
        from flight_finder.scraper import _backoff_sleep
        _backoff_sleep(2, 2.0)
        mock_sleep.assert_called_once_with(4.5)  # 2 * 2^1 + 0.5

    @patch("flight_finder.scraper.random.uniform", return_value=0.5)
    @patch("flight_finder.scraper.time.sleep")
    def test_backoff_attempt_3(self, mock_sleep, mock_rand):
        from flight_finder.scraper import _backoff_sleep
        _backoff_sleep(3, 2.0)
        mock_sleep.assert_called_once_with(8.5)  # 2 * 2^2 + 0.5


class TestRateLimiter:
    """Tests for RateLimiter."""

    @patch("flight_finder.scraper.time.sleep")
    @patch("flight_finder.scraper.time.monotonic")
    def test_no_delay_on_first_call(self, mock_mono, mock_sleep):
        limiter = RateLimiter(min_interval=1.5)
        mock_mono.return_value = 100.0
        limiter.wait()
        mock_sleep.assert_not_called()

    @patch("flight_finder.scraper.time.sleep")
    @patch("flight_finder.scraper.time.monotonic")
    def test_delay_on_rapid_calls(self, mock_mono, mock_sleep):
        limiter = RateLimiter(min_interval=1.5)
        # First call at t=100
        mock_mono.return_value = 100.0
        limiter.wait()
        # Second call at t=100.5 (only 0.5s later, need to wait 1.0s)
        mock_mono.return_value = 100.5
        limiter.wait()
        mock_sleep.assert_called_once_with(1.0)

    def test_zero_interval_no_delay(self):
        limiter = RateLimiter(min_interval=0)
        # Should not raise or sleep
        limiter.wait()
        limiter.wait()


class TestFlightSearchParams:
    """Tests for FlightSearchParams.build_flight_data."""

    def test_round_trip_builds_two_legs(self):
        params = FlightSearchParams(
            origin="IAD",
            destination="LAX",
            departure_date="2026-04-01",
            return_date="2026-04-07",
            trip_type="round-trip",
        )
        legs = params.build_flight_data()
        assert len(legs) == 2
        assert legs[0].from_airport == "IAD"
        assert legs[0].to_airport == "LAX"
        assert legs[1].from_airport == "LAX"
        assert legs[1].to_airport == "IAD"

    def test_one_way_builds_one_leg(self):
        params = FlightSearchParams(
            origin="IAD",
            destination="LAX",
            departure_date="2026-04-01",
            trip_type="one-way",
        )
        legs = params.build_flight_data()
        assert len(legs) == 1
        assert legs[0].from_airport == "IAD"
        assert legs[0].to_airport == "LAX"
