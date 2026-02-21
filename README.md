# Flight Finder

A Claude Code skill for searching and ranking flights through Google Flights. Tell it where you want to go and what matters most, and it finds and ranks your options.

## Usage

Run `/search-flights` in Claude Code to start an interactive flight search. Claude will ask for:

- **Origin and destination** — city names or IATA codes (e.g. "DC area" resolves to DCA, IAD, BWI)
- **Dates** — specific dates or relative ("next Friday")
- **What matters most** — price, duration, fewest stops, or a balanced mix

From there it searches Google Flights, ranks the results based on your priorities, and presents a table with the top options. It also generates a Google Flights link so you can verify prices directly.

After results are shown you can ask it to refine — try different dates, nonstop only, a different airport, re-rank with different weights, or drill into more options.

**Example prompts:**
```
/search-flights IAD to LAX, March 15, returning March 20
/search-flights cheapest round trip from DC to Miami this weekend
/search-flights one-way NYC to London next Thursday, business class
```

## Lakers Flights

`/lakers-flights` is a specialized version for finding flights from the DC area to upcoming Lakers games. It reads a schedule CSV with game dates, locations, and estimated ticket prices, searches all three DC-area airports (DCA, IAD, BWI) for each game, and ranks everything by **total cost (flight + ticket)**.

It's smart about trip windows — for a good destination city it'll suggest arriving the day before and staying two days after; for a quick trip it'll tighten the window. Budget cap is $500 for round-trip flights.

```
/lakers-flights
/lakers-flights March games only
/lakers-flights away games, nonstop only
```

## How It Works

The scraper fetches results from Google Flights via the `fast-flights` library. Requests are rate-limited (1.5s between calls) and retried with exponential backoff on failure. Flights are ranked by a weighted score across price, duration, and stops — weights are set based on what you tell it matters most.

## Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

All tests mock the network layer — no live requests are made.
