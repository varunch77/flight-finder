---
name: search-flights
description: Search for flights interactively. Prompts for origin, destination, dates, budget, and priorities. Use when the user wants to find or compare flights.
user-invocable: true
---

# Search Flights Skill

You are helping the user find flights. This is an interactive workflow — gather parameters, ask about priorities, search, rank, and present results. Nothing is hardcoded; every value is gathered fresh each invocation.

## Step 1: Parse $ARGUMENTS and gather missing parameters

Check if `$ARGUMENTS` provides any of these parameters. For anything not provided, ask the user:

**Required:**
- **Origin airport(s)** — IATA code(s) (e.g., IAD, DCA). If user says a city/region like "DC area", resolve to relevant airports (IAD, DCA, BWI) and search the best one or ask which.
- **Destination airport(s)** — IATA code(s) or city name (resolve to IATA).
- **Departure date** — specific date in YYYY-MM-DD. If user gives relative ("next Friday"), resolve using today's date.

**Optional (use defaults if not specified):**
- **Return date** — YYYY-MM-DD, or omit for one-way. Default: assume round-trip; ask if not clear.
- **Seat class** — economy (default), premium-economy, business, first
- **Passengers** — adults=1 (default), children=0, infants=0
- **Max stops** — None (any), 0 (nonstop only), 1, 2
- **Budget** — max price per person in USD, or no budget
- **Time preferences** — e.g., "no redeyes", "morning only", "evening departures"

Use `AskUserQuestion` to gather missing required parameters. You can batch related questions together. If `$ARGUMENTS` covers everything, skip straight to priorities.

## Step 2: Ask about ranking priorities

**Always ask this, even if arguments are complete.** Priorities change per search. Ask something like:

> What matters most for this trip?
> - Cheapest price
> - Shortest flight time
> - Fewest stops / nonstop preferred
> - Best balance of all factors

Translate the user's answer into `RankingWeights`:
- **Cheapest price**: `RankingWeights(price=1.0, duration=0.1, stops=0.1)`
- **Shortest flight**: `RankingWeights(price=0.2, duration=1.0, stops=0.3)`
- **Fewest stops**: `RankingWeights(price=0.2, duration=0.3, stops=1.0)`
- **Balanced**: `RankingWeights(price=0.6, duration=0.3, stops=0.3)` (default)

## Step 3: Execute the search

Run this Python code using the Bash tool (with the project venv):

```python
source .venv/bin/activate && python3 -c "
import json
from flight_finder.scraper import FlightSearchParams, search_flights
from flight_finder.ranking import RankingWeights, rank_flights
from fast_flights import FlightData, Passengers
from fast_flights.filter import TFSData

params = FlightSearchParams(
    origin='<ORIGIN>',
    destination='<DESTINATION>',
    departure_date='<YYYY-MM-DD>',
    return_date='<YYYY-MM-DD or None>',    # Set to None for one-way
    trip_type='<round-trip or one-way>',
    seat='<economy>',
    adults=<1>,
    max_stops=<None or int>,
)

result = search_flights(params)
weights = RankingWeights(price=<P>, duration=<D>, stops=<S>)
ranked = rank_flights(result.flights, weights=weights)

# Build Google Flights URL for validation
flight_data_list = params.build_flight_data()
tfs = TFSData.from_interface(
    flight_data=flight_data_list,
    trip=params.trip_type,
    passengers=Passengers(adults=params.adults),
    seat=params.seat,
    max_stops=params.max_stops,
)
google_flights_url = f'https://www.google.com/travel/flights?tfs={tfs.as_b64().decode()}&hl=en&tfu=EgQIABABIgA'

# Output as JSON for parsing
output = {
    'current_price': result.current_price,
    'total_flights': len(result.flights),
    'google_flights_url': google_flights_url,
    'flights': []
}
for rf in ranked[:15]:
    f = rf.flight
    output['flights'].append({
        'rank': rf.rank,
        'name': f.name,
        'price': rf.price_dollars,
        'duration': f.duration,
        'duration_min': rf.duration_minutes,
        'stops': f.stops,
        'departure': f.departure,
        'arrival': f.arrival,
        'arrival_ahead': f.arrival_time_ahead,
        'is_best': f.is_best,
        'score': round(rf.score, 4),
    })
print(json.dumps(output, indent=2))
"
```

Adjust the parameters in the script based on what the user specified. If the search fails after retries, report the error and suggest trying again or adjusting parameters.

## Step 4: Present results

Format the results as a clear table. Include:

| # | Airline | Price | Duration | Stops | Departure | Arrival | Score |
|---|---------|-------|----------|-------|-----------|---------|-------|

After the table, include:
- **Google Flights link**: Always include the `google_flights_url` from the search output as a clickable markdown link (e.g., `[View on Google Flights](url)`). This lets the user verify results directly. If presenting multiple searches, include a link for each one.
- **Price trend**: whether current prices are "low", "typical", or "high"
- **Total flights found** vs how many are shown
- Brief note on why the top result ranked well (e.g., "Cheapest nonstop option" or "Best balance of price and duration")

If the user specified a **budget**, highlight which flights are within budget and which exceed it.

If the user specified **time preferences**, note any flights that don't meet them (e.g., redeye departures when user said no redeyes).

## Step 5: Offer follow-ups

After presenting results, offer options like:
- "Want me to search nonstop only?" (if results included connections)
- "Try different dates?"
- "Compare with a different airport?"
- "Show more results?"
- "Re-rank with different priorities?"

If the user wants to refine, loop back to the relevant step. No need to re-ask parameters that haven't changed.

## Important Notes

- Always activate the venv: `source .venv/bin/activate`
- The scraper has built-in retry (3 attempts with exponential backoff). If it still fails, it's likely a temporary Google Flights issue.
- Rate limiting (1.5s between requests) is built in — no need to add delays.
- For round-trip, both `departure_date` and `return_date` are required.
- Airport codes must be valid IATA codes (3 letters, uppercase).
