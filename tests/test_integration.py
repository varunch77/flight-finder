"""End-to-end pipeline test with mocked API."""

from dataclasses import dataclass
from unittest.mock import patch

from flight_finder.ranking import RankingWeights, rank_flights
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
            self.flights = []


def make_realistic_result() -> FakeResult:
    """Build a realistic 6-flight result set."""
    return FakeResult(
        current_price="low",
        flights=[
            FakeFlight(name="United Airlines", price="$287", duration="5h 15m", stops=0),
            FakeFlight(name="American Airlines", price="$312", duration="5h 30m", stops=0),
            FakeFlight(name="Spirit Airlines", price="$149", duration="8h 45m", stops=1),
            FakeFlight(name="Delta Air Lines", price="$299", duration="5h 20m", stops=0),
            FakeFlight(name="Southwest Airlines", price="$225", duration="7h 10m", stops=1),
            FakeFlight(name="Frontier Airlines", price="$189", duration="9h 30m", stops=2),
        ],
    )


@patch("flight_finder.scraper.get_flights")
def test_full_pipeline_price_only(mock_gf):
    """search_flights -> rank_flights by price produces correct order."""
    mock_gf.return_value = make_realistic_result()

    params = FlightSearchParams(
        origin="IAD",
        destination="LAX",
        departure_date="2026-04-01",
        return_date="2026-04-07",
    )
    result = search_flights(params, rate_limiter=RateLimiter(0))
    ranked = rank_flights(result.flights, weights=RankingWeights(price=1.0, duration=0.0, stops=0.0))

    # All 6 flights present
    assert len(ranked) == 6

    # Cheapest first (Spirit at $149)
    assert ranked[0].flight.name == "Spirit Airlines"
    assert ranked[0].price_dollars == 149
    assert ranked[0].rank == 1

    # Prices are monotonically non-decreasing
    prices = [r.price_dollars for r in ranked]
    for i in range(len(prices) - 1):
        assert prices[i] <= prices[i + 1]

    # Verify full order
    expected_order = [
        ("Spirit Airlines", 149),
        ("Frontier Airlines", 189),
        ("Southwest Airlines", 225),
        ("United Airlines", 287),
        ("Delta Air Lines", 299),
        ("American Airlines", 312),
    ]
    for ranked_flight, (name, price) in zip(ranked, expected_order):
        assert ranked_flight.flight.name == name
        assert ranked_flight.price_dollars == price


@patch("flight_finder.scraper.get_flights")
def test_full_pipeline_convenience_weights(mock_gf):
    """With convenience weights (duration+stops heavy), nonstop short flights rank higher."""
    mock_gf.return_value = make_realistic_result()

    params = FlightSearchParams(
        origin="IAD",
        destination="LAX",
        departure_date="2026-04-01",
        return_date="2026-04-07",
    )
    result = search_flights(params, rate_limiter=RateLimiter(0))
    ranked = rank_flights(result.flights, weights=RankingWeights(price=0.1, duration=1.0, stops=1.0))

    # Top flights should be nonstop with short durations
    # United (5h15m, 0 stops), Delta (5h20m, 0 stops), American (5h30m, 0 stops)
    top_3_names = {r.flight.name for r in ranked[:3]}
    assert "United Airlines" in top_3_names
    assert "Delta Air Lines" in top_3_names
    assert "American Airlines" in top_3_names

    # Spirit (8h45m, 1 stop) and Frontier (9h30m, 2 stops) should rank lower
    assert ranked[-1].flight.name == "Frontier Airlines"  # worst: longest + most stops
