from datetime import date

import httpx
import respx

from price_tracker import alerts, db
from price_tracker.items import Item

ITEM = Item(id="epyc-7b13", query="x")
ITEM_WITH_TARGET = Item(id="epyc-7b13", query="x", target=1200.0)


def save(conn, price, day):
    # Helper: write one historical observation row, like a real run would.
    db.save_observation(
        conn, item_id="epyc-7b13", source="ebay", price_total=price, currency="USD",
        listing_url="u", listing_title="t", listings_seen=10, listings_kept=3, observed_on=day,
    )


def test_no_history_no_alerts(tmp_path):
    # First-ever observation for an item: nothing to compare against, so no alerts at all.
    conn = db.connect(tmp_path / "t.db")
    assert alerts.check(conn, ITEM, "ebay", 1500.0, date(2026, 11, 5)) == []


def test_below_target_fires_only_with_a_target(tmp_path):
    # Same price, same day: no target set -> nothing; target set and price at/under it -> alert.
    conn = db.connect(tmp_path / "t.db")
    assert alerts.check(conn, ITEM, "ebay", 1000.0, date(2026, 11, 5)) == []
    result = alerts.check(conn, ITEM_WITH_TARGET, "ebay", 1000.0, date(2026, 11, 5))
    assert [a.kind for a in result] == ["below_target"]


def test_new_low_requires_being_strictly_lower_than_history(tmp_path):
    # Matching the old low doesn't count as a new one; beating it does.
    conn = db.connect(tmp_path / "t.db")
    save(conn, 1500.0, date(2026, 11, 3))
    assert [a.kind for a in alerts.check(conn, ITEM, "ebay", 1500.0, date(2026, 11, 4))] == []
    assert [a.kind for a in alerts.check(conn, ITEM, "ebay", 1400.0, date(2026, 11, 4))] == ["new_low"]


def test_sharp_drop_uses_closest_observation_at_or_before_the_window(tmp_path):
    # A >=15% drop from the ~7-day-old price fires; this one is 16%. It also
    # happens to be below that same single history point, so new_low fires too.
    conn = db.connect(tmp_path / "t.db")
    save(conn, 1000.0, date(2026, 10, 29))  # exactly 7 days before the check below
    result = alerts.check(conn, ITEM, "ebay", 840.0, date(2026, 11, 5))
    assert {a.kind for a in result} == {"new_low", "sharp_drop"}


def test_small_drop_does_not_fire(tmp_path):
    # Only a 5% drop -- below the 15% sharp-drop threshold, so that rule stays
    # quiet. It's still a new low, since it's under the only history point.
    conn = db.connect(tmp_path / "t.db")
    save(conn, 1000.0, date(2026, 10, 29))
    assert [a.kind for a in alerts.check(conn, ITEM, "ebay", 950.0, date(2026, 11, 5))] == ["new_low"]


@respx.mock
def test_send_posts_one_combined_message(tmp_path):
    # With NTFY_TOPIC set, send() should make exactly one HTTP POST to that topic.
    route = respx.post("https://ntfy.sh/test-topic").mock(return_value=httpx.Response(200))
    import os
    os.environ["NTFY_TOPIC"] = "test-topic"
    try:
        with httpx.Client() as client:
            alerts.send(client, [alerts.Alert("x", "new_low", "x: 100 is a new low")])
        assert route.called
    finally:
        del os.environ["NTFY_TOPIC"]  # don't leak this into other tests


def test_send_prints_each_alert_without_a_topic(capsys):
    # No NTFY_TOPIC configured -- send() should print every alert's message
    # (not just a count), and make no network call.
    with httpx.Client() as client:
        alerts.send(client, [alerts.Alert("x", "new_low", "x: 100 is a new low")])
    assert "x: 100 is a new low" in capsys.readouterr().out
