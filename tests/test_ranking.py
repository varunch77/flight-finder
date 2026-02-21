"""Tests for price parsing, duration parsing, and flight ranking."""

from dataclasses import dataclass

from flight_finder.ranking import (
    RankingWeights,
    parse_duration,
    parse_price,
    rank_flights,
)


@dataclass
class FakeFlight:
    """Minimal stand-in for fast_flights.Flight in tests."""
    name: str = "TestAir"
    price: str = "$100"
    departure: str = "10:00 AM"
    arrival: str = "1:00 PM"
    arrival_time_ahead: str = ""
    duration: str = "3h 0m"
    stops: int = 0
    delay: str | None = None
    is_best: bool = False


# --- parse_price tests ---

class TestParsePrice:
    def test_simple_price(self):
        assert parse_price("$1234") == 1234

    def test_price_with_commas(self):
        assert parse_price("$1,234") == 1234

    def test_large_price_with_commas(self):
        assert parse_price("$12,345") == 12345

    def test_zero_returns_none(self):
        assert parse_price("$0") is None

    def test_bare_zero_returns_none(self):
        assert parse_price("0") is None

    def test_empty_string_returns_none(self):
        assert parse_price("") is None

    def test_no_dollar_sign(self):
        assert parse_price("500") == 500

    def test_non_numeric_returns_none(self):
        assert parse_price("N/A") is None


# --- parse_duration tests ---

class TestParseDuration:
    def test_hours_and_minutes(self):
        assert parse_duration("8 hr 12 min") == 492

    def test_compact_format(self):
        assert parse_duration("17h 15m") == 1035

    def test_hours_only(self):
        assert parse_duration("5h") == 300

    def test_hours_only_long(self):
        assert parse_duration("2 hr") == 120

    def test_minutes_only(self):
        assert parse_duration("45 min") == 45

    def test_minutes_only_compact(self):
        assert parse_duration("30m") == 30

    def test_empty_string(self):
        assert parse_duration("") is None

    def test_unparseable(self):
        assert parse_duration("N/A") is None


# --- rank_flights tests ---

class TestRankFlights:
    def test_cheapest_first_price_only(self):
        """With price-only weights, cheapest flight ranks first."""
        flights = [
            FakeFlight(name="Expensive", price="$500", duration="5h 0m", stops=0),
            FakeFlight(name="Cheap", price="$100", duration="10h 0m", stops=2),
            FakeFlight(name="Mid", price="$300", duration="7h 0m", stops=1),
        ]
        ranked = rank_flights(flights, weights=RankingWeights(price=1.0, duration=0.0, stops=0.0))
        assert ranked[0].flight.name == "Cheap"
        assert ranked[0].price_dollars == 100
        assert ranked[0].rank == 1
        assert ranked[1].flight.name == "Mid"
        assert ranked[2].flight.name == "Expensive"

    def test_shortest_first_duration_only(self):
        """With duration-only weights, shortest flight ranks first."""
        flights = [
            FakeFlight(name="Long", price="$100", duration="10h 0m", stops=0),
            FakeFlight(name="Short", price="$500", duration="3h 0m", stops=0),
            FakeFlight(name="Mid", price="$300", duration="6h 0m", stops=0),
        ]
        ranked = rank_flights(flights, weights=RankingWeights(price=0.0, duration=1.0, stops=0.0))
        assert ranked[0].flight.name == "Short"
        assert ranked[1].flight.name == "Mid"
        assert ranked[2].flight.name == "Long"

    def test_fewest_stops_first(self):
        """With stops-only weights, nonstop ranks first."""
        flights = [
            FakeFlight(name="Two", price="$100", duration="3h 0m", stops=2),
            FakeFlight(name="Nonstop", price="$500", duration="5h 0m", stops=0),
            FakeFlight(name="One", price="$300", duration="4h 0m", stops=1),
        ]
        ranked = rank_flights(flights, weights=RankingWeights(price=0.0, duration=0.0, stops=1.0))
        assert ranked[0].flight.name == "Nonstop"
        assert ranked[1].flight.name == "One"
        assert ranked[2].flight.name == "Two"

    def test_multi_factor_changes_ranking(self):
        """Different weight profiles produce different rankings."""
        flights = [
            FakeFlight(name="CheapLong", price="$100", duration="12h 0m", stops=2),
            FakeFlight(name="ExpensiveShort", price="$500", duration="3h 0m", stops=0),
        ]
        # Price-heavy → CheapLong first
        price_heavy = rank_flights(flights, weights=RankingWeights(price=1.0, duration=0.1, stops=0.1))
        assert price_heavy[0].flight.name == "CheapLong"

        # Duration-heavy → ExpensiveShort first
        dur_heavy = rank_flights(flights, weights=RankingWeights(price=0.1, duration=1.0, stops=0.5))
        assert dur_heavy[0].flight.name == "ExpensiveShort"

    def test_single_flight(self):
        flights = [FakeFlight(name="Solo", price="$250")]
        ranked = rank_flights(flights)
        assert len(ranked) == 1
        assert ranked[0].flight.name == "Solo"
        assert ranked[0].rank == 1

    def test_zero_price_sorted_last(self):
        flights = [
            FakeFlight(name="Free", price="$0", duration="5h 0m", stops=0),
            FakeFlight(name="Paid", price="$200", duration="5h 0m", stops=0),
        ]
        ranked = rank_flights(flights)
        assert ranked[0].flight.name == "Paid"
        assert ranked[1].flight.name == "Free"
        assert ranked[1].price_dollars is None

    def test_stable_order_same_price(self):
        flights = [
            FakeFlight(name="Alpha", price="$300", duration="5h 0m", stops=0),
            FakeFlight(name="Beta", price="$300", duration="5h 0m", stops=0),
            FakeFlight(name="Gamma", price="$300", duration="5h 0m", stops=0),
        ]
        ranked = rank_flights(flights)
        assert [r.flight.name for r in ranked] == ["Alpha", "Beta", "Gamma"]

    def test_empty_list(self):
        assert rank_flights([]) == []

    def test_all_unparseable(self):
        flights = [
            FakeFlight(name="A", price="", duration=""),
            FakeFlight(name="B", price="$0", duration=""),
        ]
        ranked = rank_flights(flights)
        assert len(ranked) == 2
        assert all(r.price_dollars is None for r in ranked)

    def test_default_weights(self):
        """Default weights should be price-dominant."""
        w = RankingWeights()
        assert w.price > w.duration
        assert w.price > w.stops

    def test_duration_parsed_correctly(self):
        flights = [FakeFlight(name="A", price="$300", duration="8 hr 12 min")]
        ranked = rank_flights(flights)
        assert ranked[0].duration_minutes == 492
