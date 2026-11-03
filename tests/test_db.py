from datetime import date

from price_tracker import db


def save(conn, price, day):
    db.save_observation(
        conn, item_id="epyc-7b13", source="ebay", price_total=price, currency="USD",
        listing_url="u", listing_title="t", listings_seen=10, listings_kept=3, observed_on=day,
    )


def test_same_day_updates_next_day_adds(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    save(conn, 1500.0, date(2026, 11, 3))
    save(conn, 1400.0, date(2026, 11, 3))
    rows = conn.execute("SELECT observed_on, price_total FROM observations").fetchall()
    assert rows == [("2026-11-03", 1400.0)]

    save(conn, 1350.0, date(2026, 11, 4))
    rows = conn.execute("SELECT observed_on, price_total FROM observations ORDER BY observed_on").fetchall()
    assert rows == [("2026-11-03", 1400.0), ("2026-11-04", 1350.0)]


def test_log_run(tmp_path):
    conn = db.connect(tmp_path / "test.db")
    db.log_run(conn, source="ebay", item_id="epyc-7b13", status="empty", message="0 passed")
    assert conn.execute("SELECT status, message FROM runs").fetchall() == [("empty", "0 passed")]
