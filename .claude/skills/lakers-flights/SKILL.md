---
name: lakers-flights
description: Search for flights to upcoming Lakers games from DC area. Reads the schedule CSV, finds upcoming games, searches flights with +/- 2-3 day trip windows, and ranks by total cost (flight + ticket).
user-invocable: true
---

# Lakers Flight Search

Search for flights from the DC area to upcoming Lakers games (home or away). Reads the schedule, searches flights for each game, and presents a ranked comparison.

## Fixed Parameters

These are the user's standing preferences — do NOT ask about them:

- **Origin airports:** Search all three (DCA, IAD, BWI) for each game and pick the best. DCA and IAD are preferred over BWI when all else is equal.
- **Trip style:** 3-5 day trip centered around the game. Be smart about trip windows based on game time and flight duration — e.g., for an evening game with a short flight, flying in morning-of is fine. The trip is NOT just for the game; the user wants to make a trip out of it, so allow 1-2 days on either side for exploring the city.
- **Budget:** $500 max for round-trip flights per person
- **Seat:** Economy
- **Passengers:** 1 adult
- **Ranking:** Balanced — `RankingWeights(price=0.6, duration=0.3, stops=0.3)`

## Step 1: Parse $ARGUMENTS

Check if `$ARGUMENTS` narrows the search:
- **Specific date range** (e.g., "March games only") — filter the schedule
- **Home/away preference** (e.g., "away games only") — filter accordingly
- **Specific city** (e.g., "just Denver") — search only that game
- **Different budget** — override the $500 default
- **Max games to search** — limit how many to search (default: all upcoming)

If `$ARGUMENTS` is empty, search ALL upcoming games.

## Step 2: Read and filter the schedule

Run this Python code using the Bash tool:

```python
source .venv/bin/activate && python3 -c "
import csv
import json
from datetime import datetime, date

today = date.today()
games = []
with open('lakers_schedule.csv') as f:
    reader = csv.DictReader(f)
    for row in reader:
        game_date = datetime.strptime(row['Date'].strip(), '%m/%d/%Y').date()
        if game_date > today:
            games.append({
                'date': str(game_date),
                'time': row['Game_Time'].strip(),
                'home_away': row['Home_Away'].strip(),
                'location': row['Location'].strip(),
                'ticket_price': int(row['Game_Price'].strip()),
            })
print(json.dumps(games, indent=2))
"
```

## Step 3: Search flights for each game

For each upcoming game, determine the destination airport and preferred origin using this mapping:

**City → Airport:**
- Los Angeles → LAX
- Phoenix → PHX
- San Francisco → SFO
- Denver → DEN
- Houston → IAH
- Miami → MIA
- Orlando → MCO
- Detroit → DTW
- Indianapolis → IND
- Oklahoma City → OKC
- Dallas → DFW

**Trip window:** Choose smart trip dates for each game based on context:
- **Departure:** The day before the game (D-1) is the safe default. For short flights (<3 hr) to evening games (7pm+), departing morning-of (D) is also viable.
- **Return:** 1-2 days after the game (D+1 or D+2). Use D+2 for destination cities worth exploring (LA, Miami, Denver), D+1 for smaller cities.
- The goal is a 3-5 day trip, not a rigid formula. Use your judgment.

Run the search script for each game. **Important:** If there are many games (>10), warn the user it will take a few minutes due to rate limiting, then proceed. Use a single Python script that loops through all games:

```python
source .venv/bin/activate && python3 -c "
import csv, json, sys
from datetime import datetime, date, timedelta
from flight_finder.scraper import FlightSearchParams, search_flights
from flight_finder.ranking import RankingWeights, rank_flights
from fast_flights import FlightData, Passengers
from fast_flights.filter import TFSData

# --- Config ---
CITY_TO_AIRPORT = {
    'Los Angeles': 'LAX', 'Phoenix': 'PHX', 'San Francisco': 'SFO',
    'Denver': 'DEN', 'Houston': 'IAH', 'Miami': 'MIA',
    'Orlando': 'MCO', 'Detroit': 'DTW', 'Indianapolis': 'IND',
    'Oklahoma City': 'OKC', 'Dallas': 'DFW',
}
# Cities worth extra exploration time (use D+2 for return)
BIG_DESTINATIONS = {'LAX', 'SFO', 'MIA', 'DEN'}
# Search all three DC-area airports; DCA/IAD preferred over BWI when equal
ORIGINS = ['DCA', 'IAD', 'BWI']
weights = RankingWeights(price=0.6, duration=0.3, stops=0.3)
today = date.today()

# --- Read schedule ---
games = []
with open('lakers_schedule.csv') as f:
    reader = csv.DictReader(f)
    for row in reader:
        game_date = datetime.strptime(row['Date'].strip(), '%m/%d/%Y').date()
        if game_date > today:
            city = row['Location'].strip()
            dest = CITY_TO_AIRPORT.get(city)
            if not dest:
                print(f'WARNING: Unknown city {city}, skipping', file=sys.stderr)
                continue
            games.append({
                'game_date': str(game_date),
                'game_time': row['Game_Time'].strip(),
                'home_away': row['Home_Away'].strip(),
                'city': city,
                'dest': dest,
                'ticket_price': int(row['Game_Price'].strip()),
            })

def build_gf_url(params):
    flight_data_list = params.build_flight_data()
    tfs = TFSData.from_interface(
        flight_data=flight_data_list, trip='round-trip',
        passengers=Passengers(adults=1), seat='economy',
    )
    return f'https://www.google.com/travel/flights?tfs={tfs.as_b64().decode()}&hl=en&tfu=EgQIABABIgA'

# --- Search each game from all 3 airports, keep best ---
results = []
for i, g in enumerate(games):
    gd = datetime.strptime(g['game_date'], '%Y-%m-%d').date()
    # Smart trip window: arrive day before, stay longer for big destinations
    depart = str(gd - timedelta(days=1))
    ret = str(gd + timedelta(days=2)) if g['dest'] in BIG_DESTINATIONS else str(gd + timedelta(days=1))
    label = f\"{g['city']} {g['home_away']} {g['game_date']}\"

    best_origin_result = None  # tracks the winning airport for this game

    for origin in ORIGINS:
        print(f'Searching {i+1}/{len(games)}: {label} from {origin}...', file=sys.stderr, flush=True)
        try:
            params = FlightSearchParams(
                origin=origin, destination=g['dest'],
                departure_date=depart, return_date=ret,
                trip_type='round-trip', seat='economy', adults=1, max_stops=None,
            )
            result = search_flights(params)
            ranked = rank_flights(result.flights, weights=weights)
            if not ranked:
                continue

            best_rf = ranked[0]
            best_price = best_rf.price_dollars

            # Compare with current best: pick lower price, or on tie prefer DCA/IAD over BWI
            if best_origin_result is None or best_price < best_origin_result['best_price'] or (
                best_price == best_origin_result['best_price'] and origin != 'BWI' and best_origin_result['origin'] == 'BWI'
            ):
                top3 = []
                for rf in ranked[:3]:
                    f = rf.flight
                    top3.append({
                        'airline': f.name, 'price': rf.price_dollars,
                        'duration': f.duration, 'stops': f.stops,
                        'departure': f.departure, 'arrival': f.arrival,
                        'score': round(rf.score, 4),
                    })
                best_origin_result = {
                    'origin': origin,
                    'best_price': best_price,
                    'total_flights': len(result.flights),
                    'current_price': result.current_price,
                    'google_flights_url': build_gf_url(params),
                    'best_flight': top3[0],
                    'top3': top3,
                }
        except Exception as e:
            print(f'  Error from {origin}: {e}', file=sys.stderr, flush=True)

    if best_origin_result:
        results.append({
            **g, 'origin': best_origin_result['origin'],
            'depart': depart, 'return': ret,
            'total_flights': best_origin_result['total_flights'],
            'current_price': best_origin_result['current_price'],
            'google_flights_url': best_origin_result['google_flights_url'],
            'best_flight': best_origin_result['best_flight'],
            'top3': best_origin_result['top3'],
        })
    else:
        results.append({**g, 'origin': 'N/A', 'depart': depart, 'return': ret, 'error': 'All airports failed'})

print(json.dumps(results, indent=2))
"
```

Adjust the script if `$ARGUMENTS` specified filters (date range, home/away, specific city, max games).

## Step 4: Present results

Present a **comparison table ranked by total cost** (flight + game ticket):

| # | City | Game Date | Home/Away | Flight RT | Ticket | **Total** | Airline | Duration | Stops | Route | Price Trend | Link |
|---|------|-----------|-----------|-----------|--------|-----------|---------|----------|-------|-------|-------------|------|

In the **Link** column, include `[Google Flights](url)` using the `google_flights_url` from each result.

After the table:
- **Bold the best 3 options** and explain why they stand out (cheapest total, best destination, shortest flight, etc.)
- Flag any flights **over $500 budget**
- Note any games where the search failed or returned incomplete data
- If consecutive away games exist in nearby cities, suggest a **multi-game trip** option
- Call out the **Houston back-to-back** (Mar 16 + Mar 18) if both games are upcoming — that's two games in one trip ($99 + $82 = $181 combined tickets)

## Step 5: Offer follow-ups

- "Drill into a specific trip?" (show more flight options for one game)
- "Try a shorter/longer trip window?"
- "Search nonstop only?"
- "Compare two specific games side by side?"
- "Re-run just the top 3 to check for price changes?"

## Important Notes

- Always activate the venv: `source .venv/bin/activate`
- Rate limiting is 1.5s between requests. Round-trip = 2 requests per search. With 3 airports per game, budget ~9s per game. 10 games ≈ 90s, 20 games ≈ 3 min.
- The scraper has built-in retry (3 attempts with exponential backoff). If a search fails, it's likely a temporary Google Flights issue — note it and move on.
- Schedule CSV is at `lakers_schedule.csv` with columns: `Date,Game_Time,Home_Away,Location,Game_Price`
- Some searches may return incomplete flight data (missing airline/duration). Flag these honestly rather than presenting bad data.
