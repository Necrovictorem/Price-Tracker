"""SQLite schema and helpers. One observation row per item/source/day."""

import sqlite3
from datetime import date, datetime
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "prices.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS observations (
    id INTEGER PRIMARY KEY,
    item_id TEXT NOT NULL,
    observed_on DATE NOT NULL,
    source TEXT NOT NULL,
    price_total REAL NOT NULL,
    currency TEXT NOT NULL,
    listing_url TEXT,
    listing_title TEXT,
    listings_seen INTEGER NOT NULL,
    listings_kept INTEGER NOT NULL,
    UNIQUE (item_id, source, observed_on)
);
CREATE TABLE IF NOT EXISTS runs (
    id INTEGER PRIMARY KEY,
    started_at TEXT NOT NULL,
    source TEXT NOT NULL,
    item_id TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT
);
"""


def connect(path: Path | str = DEFAULT_PATH) -> sqlite3.Connection:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.executescript(SCHEMA)
    return conn


def save_observation(
    conn: sqlite3.Connection,
    *,
    item_id: str,
    source: str,
    price_total: float,
    currency: str,
    listing_url: str,
    listing_title: str,
    listings_seen: int,
    listings_kept: int,
    observed_on: date | None = None,
) -> None:
    """Insert today's row, or replace it if this item/source already ran today."""
    observed_on = observed_on or date.today()
    conn.execute(
        """
        INSERT INTO observations (item_id, observed_on, source, price_total, currency,
                                  listing_url, listing_title, listings_seen, listings_kept)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (item_id, source, observed_on) DO UPDATE SET
            price_total = excluded.price_total,
            currency = excluded.currency,
            listing_url = excluded.listing_url,
            listing_title = excluded.listing_title,
            listings_seen = excluded.listings_seen,
            listings_kept = excluded.listings_kept
        """,
        (item_id, observed_on.isoformat(), source, price_total, currency,
         listing_url, listing_title, listings_seen, listings_kept),
    )
    conn.commit()


def log_run(conn: sqlite3.Connection, *, source: str, item_id: str, status: str, message: str = "") -> None:
    conn.execute(
        "INSERT INTO runs (started_at, source, item_id, status, message) VALUES (?, ?, ?, ?, ?)",
        (datetime.now().isoformat(timespec="seconds"), source, item_id, status, message),
    )
    conn.commit()
