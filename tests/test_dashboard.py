import urllib.error
import urllib.request
from datetime import date

from price_tracker import dashboard, db
from price_tracker.items import ITEMS


def test_escape_blocks_script_tags():
    # A listing title with HTML in it must come back as harmless text, not a real tag.
    assert dashboard._escape("<script>bad()</script>") == "&lt;script&gt;bad()&lt;/script&gt;"


def test_safe_link_rejects_non_http_schemes():
    # A crafted "javascript:" URL must never become a clickable href --
    # check there's no <a> tag at all, just the plain escaped text.
    result = dashboard._safe_link("javascript:alert(1)", "click me")
    assert "<a" not in result
    assert "click me" in result


def test_safe_link_renders_http_as_anchor():
    # A normal https:// URL, on the other hand, should become a real link.
    result = dashboard._safe_link("https://ebay.com/itm/1", "A CPU")
    assert '<a href="https://ebay.com/itm/1"' in result
    assert "A CPU" in result


def test_svg_chart_empty_returns_placeholder():
    # No history at all for this item yet -- should fall back to plain text, not a broken/empty chart.
    assert "No price history" in dashboard._svg_chart({})


def test_svg_chart_with_data_returns_svg_and_legend():
    # One source, two data points -- should produce a real <svg> element and name that source in the legend.
    result = dashboard._svg_chart({"ebay": [("2026-11-04", 1000.0), ("2026-11-05", 900.0)]})
    assert "<svg" in result
    assert "ebay" in result


def test_render_page_escapes_listing_title(tmp_path):
    # A real DB round-trip: save a listing with an HTML-injection-looking
    # title, render the full page, and confirm it never appears unescaped.
    conn = db.connect(tmp_path / "t.db")
    db.save_observation(
        conn, item_id=ITEMS[0].id, source="ebay", price_total=100.0, currency="USD",
        listing_url="https://ebay.com/itm/1", listing_title="<script>bad()</script>",
        listings_seen=1, listings_kept=1, observed_on=date(2026, 11, 5),
    )
    page = dashboard.render_page(conn)
    assert "<script>bad()</script>" not in page   # the raw, dangerous form must not be present
    assert "&lt;script&gt;" in page                # the escaped, harmless form must be present instead


def test_server_routes_root_and_404s_everything_else(tmp_path, monkeypatch):
    # A full round-trip through the REAL HTTP handler, talking over an
    # actual (loopback-only) socket -- not just calling render_page()
    # directly -- so this also exercises do_GET's routing and headers.
    db_path = tmp_path / "t.db"
    real_connect = db.connect  # save this BEFORE patching -- `db` and `dashboard.db` are
    real_connect(db_path)      # the same module object, so patching one patches both.

    # dashboard.py's handler calls db.connect() with no arguments, which
    # would otherwise open the real data/prices.db. Point that at our
    # throwaway file instead -- but still open a FRESH connection on every
    # call (exactly like the real handler does), rather than sharing one
    # connection object across threads: sqlite3 connections can only be
    # used by the thread that created them, and the server below handles
    # each request on its own background thread.
    monkeypatch.setattr(dashboard.db, "connect", lambda *a, **k: real_connect(db_path))

    # port=0 tells the OS "pick any free port for me" -- avoids ever
    # colliding with a port something else on the machine is already using.
    server = dashboard.make_server(port=0)

    # serve_forever() blocks, so it has to run on a background thread while
    # the test itself makes requests from the main thread. daemon=True means
    # this thread won't keep the test process alive if something goes wrong.
    import threading
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        # Now that the server is listening, ask it which port it actually got.
        port = server.server_address[1]

        # Request 1: the real page. Should succeed and contain the title.
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/") as resp:
            assert resp.status == 200
            assert b"Price Tracker" in resp.read()

        # Request 2: anything else should 404. urllib raises HTTPError for
        # non-2xx responses instead of just returning it, so the check has
        # to happen inside a try/except.
        try:
            urllib.request.urlopen(f"http://127.0.0.1:{port}/nope")
            assert False, "expected a 404"
        except urllib.error.HTTPError as e:
            assert e.code == 404
    finally:
        # Always shut the server down and wait for its thread to actually
        # exit, even if one of the assertions above failed -- otherwise a
        # failed test would leave a server thread running in the background.
        server.shutdown()
        thread.join(timeout=2)
