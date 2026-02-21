"""Price parsing and flight ranking with multi-factor scoring."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from fast_flights import Flight


def parse_price(price_str: str) -> int | None:
    """Parse a price string like '$1,234' into integer dollars.

    Returns None for unavailable prices ('$0', '0', empty string).
    """
    if not price_str:
        return None
    cleaned = price_str.replace("$", "").replace(",", "").strip()
    if not cleaned:
        return None
    try:
        value = int(cleaned)
    except ValueError:
        return None
    if value == 0:
        return None
    return value


def parse_duration(duration_str: str) -> int | None:
    """Parse a duration string like '8 hr 12 min' or '17h 15m' into total minutes.

    Returns None if unparseable.
    """
    if not duration_str:
        return None
    # Match patterns like "8 hr 12 min", "17h 15m", "5h", "30 min", "2 hr"
    match = re.match(r"(?:(\d+)\s*(?:hr|h))?\s*(?:(\d+)\s*(?:min|m))?", duration_str.strip())
    if not match or (match.group(1) is None and match.group(2) is None):
        return None
    hours = int(match.group(1)) if match.group(1) else 0
    minutes = int(match.group(2)) if match.group(2) else 0
    total = hours * 60 + minutes
    return total if total > 0 else None


@dataclass
class RankingWeights:
    """Configurable weights for multi-factor flight ranking.

    Higher weight = more influence on the score. All weights should be >= 0.
    """
    price: float = 1.0
    duration: float = 0.3
    stops: float = 0.2


@dataclass
class RankedFlight:
    """A flight with parsed attributes and composite score."""

    flight: Flight
    price_dollars: int | None
    duration_minutes: int | None = None
    score: float = 0.0
    rank: int = 0


def rank_flights(
    flights: list[Flight],
    weights: RankingWeights | None = None,
) -> list[RankedFlight]:
    """Rank flights using weighted multi-factor scoring.

    Dimensions: price (dollars), duration (minutes), stops (count).
    Each dimension is min-max normalized to [0, 1]. Lower raw values are better.
    Flights missing a dimension value get a penalty score of 1.0 for that dimension.
    Final score = weighted sum of normalized values. Lower score = better.
    """
    if weights is None:
        weights = RankingWeights()

    ranked = [
        RankedFlight(
            flight=f,
            price_dollars=parse_price(f.price),
            duration_minutes=parse_duration(f.duration),
        )
        for f in flights
    ]

    if not ranked:
        return ranked

    # Collect valid values for min-max normalization
    prices = [r.price_dollars for r in ranked if r.price_dollars is not None]
    durations = [r.duration_minutes for r in ranked if r.duration_minutes is not None]
    stops_vals = [r.flight.stops for r in ranked if isinstance(r.flight.stops, int)]

    for r in ranked:
        r.score = _compute_score(r, weights, prices, durations, stops_vals)

    ranked.sort(key=lambda r: r.score)
    for i, r in enumerate(ranked):
        r.rank = i + 1
    return ranked


def _normalize(value: float, min_val: float, max_val: float) -> float:
    """Min-max normalize a value to [0, 1]. Returns 0 if range is zero."""
    if max_val == min_val:
        return 0.0
    return (value - min_val) / (max_val - min_val)


def _compute_score(
    r: RankedFlight,
    weights: RankingWeights,
    prices: list[int],
    durations: list[int],
    stops_vals: list[int],
) -> float:
    """Compute weighted composite score for a single flight."""
    score = 0.0
    total_weight = weights.price + weights.duration + weights.stops

    if total_weight == 0:
        return 0.0

    # Price dimension
    if prices:
        if r.price_dollars is not None:
            score += weights.price * _normalize(r.price_dollars, min(prices), max(prices))
        else:
            score += weights.price  # Penalty: worst possible
    # Duration dimension
    if durations:
        if r.duration_minutes is not None:
            score += weights.duration * _normalize(r.duration_minutes, min(durations), max(durations))
        else:
            score += weights.duration
    # Stops dimension
    if stops_vals:
        stops = r.flight.stops if isinstance(r.flight.stops, int) else max(stops_vals)
        score += weights.stops * _normalize(stops, min(stops_vals), max(stops_vals))

    return score
