# Flight Finder

## Build & Test Commands
- Install: `pip install -e ".[dev]"`
- Run all tests: `pytest tests/ -v`
- Run single test file: `pytest tests/test_ranking.py -v`
- Run live demo: `python -m flight_finder.cli`

## Project Structure
- `src/flight_finder/` — main package (src layout)
- `tests/` — unit and integration tests (all mock `fast_flights.get_flights`)
- Dependencies: `fast-flights` (local at `/Users/varun/Projects/flights`)

## Key Notes
- `fast-flights` is installed from local path, not PyPI
- All tests mock `flight_finder.scraper.get_flights` — no network calls
- Rate limiter uses 1.5s minimum interval between requests
- Retry uses exponential backoff: 2s, 4s, 8s + random jitter
