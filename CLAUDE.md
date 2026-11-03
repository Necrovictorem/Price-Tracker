# Price Tracker

A Python service that checks prices for the Build Fund items once a day, stores the lowest valid price per item per day in SQLite, and (later) alerts on buy targets. See `plan.md` for the full design and phases.

## Rules
- Never buy anything or automate checkout.
- Nothing behind a login (no personal Amazon/eBay account access).
- Prefer official APIs; parse web pages only where no API exists, and check the site's terms first.
- At most one request per item per source per day.
- Secrets live in `.env` (see `.env.example`); never commit or print them.
- Store one row per item/source/day: the lowest valid price after filtering.
- Filter rules are data in `items.py`; the engine in `filters.py` stays generic.

## Layout
- `src/price_tracker/items.py` — item definitions (search query + filter rules)
- `src/price_tracker/filters.py` — include/exclude matching and lowest-price selection
- `src/price_tracker/collectors/` — one module per source (`ebay.py` so far)
- `src/price_tracker/db.py` — SQLite schema and helpers (`data/prices.db`)
- `src/price_tracker/cli.py` — entry point

## Commands (Windows, PowerShell)
```
py -m venv .venv
.venv\Scripts\python -m pip install -e .[dev]
.venv\Scripts\python -m pytest
.venv\Scripts\python -m price_tracker run
```

Tests must not hit the network; mock HTTP with `respx`.
