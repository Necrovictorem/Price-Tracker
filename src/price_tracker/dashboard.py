"""Read-only local dashboard: one page, one chart per item, no forms or
buttons that change anything. Binds to 127.0.0.1 only -- phone access goes
through `tailscale serve`, never by exposing this to the LAN or internet.

Uses only the standard library (http.server + hand-drawn SVG), on purpose:
no new dependency, no CDN script to load, works fully offline.
"""

import html
import http.server
import sqlite3
from datetime import date, timedelta

from . import db
from .items import ITEMS

# Pixel dimensions of every chart on the page. CHART_PAD is the blank margin
# left around the edges so axis labels have somewhere to sit without being
# cut off or overlapping the lines themselves.
CHART_WIDTH = 600
CHART_HEIGHT = 160
CHART_PAD = 30

# Items are ranked by how much their price moved over roughly this many
# days, so the biggest movers sit at the top of the page.
CHANGE_WINDOW_DAYS = 7

# Colors used for each line on a chart, in order. If an item somehow has
# more than 4 sources, the 5th line just reuses the 1st color (see the "% "
# in the loop below) -- unlikely today since only "ebay"/"ebay-sandbox" exist,
# but cheap insurance against a crash if that ever changes.
LINE_COLORS = ["#2563eb", "#dc2626", "#059669", "#d97706"]

# Inline CSS for the whole page. Inline (not a separate .css file) so the
# page is a single self-contained response -- no second request needed,
# nothing that could 404 if a path is ever wrong.
STYLE = """
body { font-family: sans-serif; max-width: 700px; margin: 2rem auto; color: #1e293b; }
h1 { margin-bottom: 0.2rem; }
.note { color: #64748b; font-size: 0.9rem; }
section.item { border-top: 1px solid #e2e8f0; padding: 1rem 0; }
section.item h2 { margin: 0 0 0.3rem; font-size: 1.1rem; }
.legend { font-size: 0.85rem; color: #475569; }
.review { color: #b45309; font-size: 0.85rem; }
.change { font-size: 0.85rem; font-weight: normal; margin-left: 0.5rem; }
.down { color: #059669; }  /* cheaper: good news for a buyer */
.up { color: #dc2626; }
.flat { color: #94a3b8; }
"""


def _escape(text: str) -> str:
    """HTML-escape any text that ultimately comes from an eBay listing
    (titles, source names) before it goes into the page -- per CLAUDE.md,
    those are free text from strangers and must never be trusted as-is.
    `quote=True` also escapes quote characters, so the same helper is safe
    to use both inside normal text AND inside an HTML attribute like href=."""
    return html.escape(text, quote=True)


def _safe_link(url: str, text: str) -> str:
    """Render `text` as a clickable link to `url`, but ONLY if `url` looks
    like a real http(s) link. A listing's URL is also untrusted stranger
    data -- without this check, a crafted "javascript:" URL could run in
    your browser when clicked. Anything else just prints as escaped text,
    so the page degrades to "not a link" instead of "unsafe link"."""
    # Escape the visible text first -- this happens whether or not we end up
    # wrapping it in a link, since it's rendered either way.
    safe_text = _escape(text)
    if url and (url.startswith("http://") or url.startswith("https://")):
        # The URL itself also gets escaped before going inside the href="" attribute,
        # in case it contains a stray quote character that could break out of it.
        # target="_blank" opens it in a new tab; rel="noopener noreferrer" stops that
        # new tab from being able to reach back into this page via window.opener.
        return f'<a href="{_escape(url)}" target="_blank" rel="noopener noreferrer">{safe_text}</a>'
    return safe_text


def _history(conn: sqlite3.Connection, item_id: str) -> dict[str, list[tuple[str, float]]]:
    """Every day's price for one item, grouped by source (e.g. "ebay" vs
    "ebay-sandbox" stay on separate lines so test data never blends into
    real history). Returns {source: [(observed_on, price_total), ...]}."""
    # One query gets every observation ever recorded for this item, across
    # every source, oldest first. ORDER BY here (rather than sorting in
    # Python later) keeps each source's own list already in date order.
    rows = conn.execute(
        "SELECT source, observed_on, price_total FROM observations WHERE item_id = ? ORDER BY observed_on",
        (item_id,),
    ).fetchall()

    # Now split that flat list of rows into one list per source. setdefault
    # creates the list the first time a given source is seen, and just
    # appends to it on every later row for that same source.
    by_source: dict[str, list[tuple[str, float]]] = {}
    for source, day, price in rows:
        by_source.setdefault(source, []).append((day, price))
    return by_source


def _recent_change(points: list[tuple[str, float]]) -> tuple[float, str] | None:
    """How much one source's price moved: the latest price compared with the
    price about CHANGE_WINDOW_DAYS earlier. Returns (fraction, reference_day),
    e.g. (-0.12, "2026-10-29") means 12% cheaper than on Oct 29. None if
    there's only one day of history, since there's nothing to compare yet."""
    # Need at least two days to measure any change at all.
    if len(points) < 2:
        return None
    latest_day, latest_price = points[-1]
    # The cutoff date: CHANGE_WINDOW_DAYS before the latest observation.
    cutoff = (date.fromisoformat(latest_day) - timedelta(days=CHANGE_WINDOW_DAYS)).isoformat()
    # Prefer the newest point at or before the cutoff (same idea as alerts.py's
    # sharp-drop rule). If history doesn't reach back that far yet, use the
    # oldest point we have, so a young tracker still gets a ranking.
    older = [(d, p) for d, p in points[:-1] if d <= cutoff]
    ref_day, ref_price = older[-1] if older else points[0]
    # Guard against dividing by zero, which would crash the whole page.
    if ref_price <= 0:
        return None
    return (latest_price - ref_price) / ref_price, ref_day


def _sort_key(change: tuple[float, str] | None, has_data: bool) -> tuple[int, float]:
    """Page order: biggest price move first (up OR down), then items with
    only one day of data, then items that have never had a price."""
    if change is not None:
        return (0, -abs(change[0]))  # minus sign: bigger move sorts earlier
    return (1, 0.0) if has_data else (2, 0.0)


def _change_label(change: tuple[float, str] | None) -> str:
    """Small colored note next to the item's name, e.g. "▼ 12% since 2026-10-29".
    The date comes from our own database, not from eBay, so it's safe as-is."""
    if change is None:
        return ""
    fraction, since = change
    # Anything under half a percent rounds to 0%, so call it flat.
    if abs(fraction) < 0.005:
        return f'<span class="change flat">no change since {since}</span>'
    arrow, css = ("▼", "down") if fraction < 0 else ("▲", "up")
    return f'<span class="change {css}">{arrow} {abs(fraction):.0%} since {since}</span>'


def _svg_chart(by_source: dict[str, list[tuple[str, float]]]) -> str:
    """Draw a simple line chart: one polyline per source, sharing one
    x-axis (every date seen, across all sources) and one y-axis (the
    lowest and highest price seen, across all sources), so the lines
    stay comparable. Returns a placeholder paragraph if there's no data."""
    if not by_source:
        # Nothing has ever been observed for this item yet -- draw text, not an empty chart.
        return "<p>No price history yet.</p>"

    # Step 1: figure out the shared axes.
    # all_days: every date that appears in ANY source's history, deduplicated
    # and sorted. This becomes the x-axis -- every line is plotted against
    # these same positions, even if one source has fewer data points.
    all_days = sorted({day for points in by_source.values() for day, _ in points})
    # all_prices: every price from every source, just to find the overall
    # lowest and highest value so the y-axis scale fits every line.
    all_prices = [price for points in by_source.values() for _, price in points]
    # x_for_day maps each date to its position in the sorted list (0, 1, 2, ...)
    # -- e.g. the oldest date is 0, the next is 1, and so on.
    x_for_day = {day: i for i, day in enumerate(all_days)}
    lo, hi = min(all_prices), max(all_prices)

    def x_pos(day: str) -> float:
        # Converts a date's index (0, 1, 2, ...) into an actual pixel x
        # coordinate, spread evenly across the chart's width (minus padding
        # on both sides). `span` is "how many steps between the first and
        # last date" -- max(..., 1) just avoids dividing by zero when there's
        # only a single date (span would otherwise be 0).
        span = max(len(all_days) - 1, 1)
        return CHART_PAD + (CHART_WIDTH - 2 * CHART_PAD) * (x_for_day[day] / span)

    def y_pos(price: float) -> float:
        # Converts a price into a pixel y coordinate. SVG's y-axis grows
        # DOWNWARD (0 is the top of the chart), which is the opposite of how
        # we think about price -- so a HIGHER price needs a SMALLER y value.
        # That's what "1 - ..." does: it flips the direction.
        if hi == lo:
            # Every price seen so far is identical (e.g. only one data point,
            # or the price genuinely hasn't moved) -- there's no range to
            # scale against, so just draw a flat line through the middle.
            return CHART_HEIGHT / 2
        return CHART_PAD + (CHART_HEIGHT - 2 * CHART_PAD) * (1 - (price - lo) / (hi - lo))

    # Step 2: build one polyline (the connected line) plus one small circle
    # per data point (so individual days are visible, not just the line
    # between them), for every source.
    shapes = []
    legend = []
    for i, (source, points) in enumerate(sorted(by_source.items())):
        # Cycle through LINE_COLORS by index, so each source gets a
        # consistent, distinct color.
        color = LINE_COLORS[i % len(LINE_COLORS)]
        points = sorted(points)  # oldest to newest, left to right on the chart
        # SVG's <polyline> wants one long string of "x,y x,y x,y" pairs.
        line = " ".join(f"{x_pos(d):.1f},{y_pos(p):.1f}" for d, p in points)
        shapes.append(f'<polyline points="{line}" fill="none" stroke="{color}" stroke-width="2" />')
        # One small filled circle at every actual data point, on top of the line.
        for d, p in points:
            shapes.append(f'<circle cx="{x_pos(d):.1f}" cy="{y_pos(p):.1f}" r="3" fill="{color}" />')
        # Legend entry: a colored bullet (● is "●") plus the source name.
        legend.append(f'<span style="color:{color}">●</span> {_escape(source)}')

    # Step 3: axis labels. Keeping this minimal on purpose -- just the two
    # end dates (oldest/newest) and the two end prices (lowest/highest) is
    # enough to read the chart at a glance, without cluttering it.
    labels = (
        f'<text x="{CHART_PAD}" y="{CHART_HEIGHT - 5}" font-size="10">{all_days[0]}</text>'
        f'<text x="{CHART_WIDTH - CHART_PAD - 70}" y="{CHART_HEIGHT - 5}" font-size="10">{all_days[-1]}</text>'
        f'<text x="2" y="{CHART_PAD}" font-size="10">{hi:,.0f}</text>'
        f'<text x="2" y="{CHART_HEIGHT - CHART_PAD}" font-size="10">{lo:,.0f}</text>'
    )

    # Step 4: assemble the actual <svg> element. viewBox lets the browser
    # scale the chart to fit width="100%" of its container while keeping
    # everything inside it (the polylines, circles, text) in the same fixed
    # coordinate space we did all the math in above.
    svg = (
        f'<svg viewBox="0 0 {CHART_WIDTH} {CHART_HEIGHT}" width="100%" height="{CHART_HEIGHT}">'
        f"{labels}{''.join(shapes)}</svg>"
    )
    # The legend goes right under the chart, as plain HTML (not part of the SVG).
    return svg + f'<div class="legend">{" &nbsp; ".join(legend)}</div>'


def render_page(conn: sqlite3.Connection) -> str:
    """Build the whole dashboard as one HTML string: one <section> per item,
    each showing its latest price, its chart, and how many listings are
    sitting in `review` (see `view --review`). Items are ordered by how much
    their price moved recently (biggest move first), not by items.py order."""
    sections = []  # (sort key, section HTML) pairs, sorted before output
    for item in ITEMS:
        # The single most recent observation row for this item, across any
        # source -- "ORDER BY observed_on DESC LIMIT 1" means "the latest one".
        latest = conn.execute(
            "SELECT source, observed_on, price_total, currency, listing_title, listing_url FROM observations"
            " WHERE item_id = ? ORDER BY observed_on DESC LIMIT 1",
            (item.id,),
        ).fetchone()
        # Fetched once here because both the chart and the change label need it.
        history = _history(conn, item.id)
        change = None

        if latest:
            # fetchone() with 6 columns in the SELECT above unpacks into 6 variables, in that same order.
            source, day, price, currency, title, url = latest
            # Measure the change on the same source as the headline price, so two
            # different sources' prices are never compared with each other.
            change = _recent_change(history.get(source, []))
            latest_html = (
                f"<p><strong>{currency} {price:,.2f}</strong> on {day} ({_escape(source)})<br>"
                f"{_safe_link(url, title)}</p>"
            )
        else:
            # This item has never produced a valid price yet (e.g. everything
            # that matched also got filtered out, or the collector errored).
            latest_html = "<p>No observations yet.</p>"

        # How many listings for this item are sitting in `review_listings` --
        # ambiguous matches that llm_review.py didn't promote to standalone.
        # This is just a count for a quick "heads up" note; the actual
        # listings themselves are only in the `view --review` CLI output.
        review_count = conn.execute(
            "SELECT COUNT(*) FROM review_listings WHERE item_id = ?", (item.id,)
        ).fetchone()[0]
        review_html = f'<p class="review">{review_count} listing(s) flagged for review</p>' if review_count else ""

        # One <section> per item: its id as a heading, the latest-price
        # paragraph, the chart (built by pulling this item's full history
        # and handing it to _svg_chart), then the review note if there is one.
        section_html = (
            f'<section class="item"><h2>{_escape(item.id)}{_change_label(change)}</h2>{latest_html}'
            f"{_svg_chart(history)}{review_html}</section>"
        )
        sections.append((_sort_key(change, has_data=latest is not None), section_html))

    # Python's sort is "stable": items with equal keys keep their items.py
    # order, so the unchanged ones stay grouped Path A, Path B, GPUs.
    sections.sort(key=lambda pair: pair[0])

    # Finally, wrap every item section in one full HTML document: a <head>
    # with the inline stylesheet, a page title, a one-line explanation of
    # what this page is (and isn't -- no signals yet), then all the sections.
    return (
        f"<!doctype html><html><head><meta charset='utf-8'><title>Price Tracker</title>"
        f"<style>{STYLE}</style></head><body>"
        f"<h1>Price Tracker</h1>"
        f"<p class='note'>Read-only -- updated by the daily scheduled run. "
        f"Leading signals (GPU rental rates, DDR5/Genoa prices) aren't collected yet, "
        f"so they don't appear here. "
        f"Sorted by how much each price moved over the last ~{CHANGE_WINDOW_DAYS} days, biggest move first.</p>"
        f"{''.join(section for _, section in sections)}</body></html>"
    )


class _Handler(http.server.BaseHTTPRequestHandler):
    """Handles exactly one route: GET /. Anything else gets a 404. There is
    no POST/PUT/DELETE handling at all -- this class simply never defines
    do_POST etc., so the base class's default behavior (a 501 "not
    implemented" response) kicks in automatically for any such request."""

    def do_GET(self) -> None:
        # Only "/" is a real page on this server. Anything else (a typo,
        # a browser auto-requesting /favicon.ico, whatever) gets a plain 404
        # with no body, and we stop right there.
        if self.path != "/":
            self.send_response(404)
            self.end_headers()
            return

        # A brand-new SQLite connection for THIS request only. ThreadingHTTPServer
        # (below) runs each request in its own thread, and sqlite3 connections
        # aren't safe to share across threads -- so rather than keep one
        # connection open for the server's whole lifetime, we just open a
        # cheap new one per request and let it close when the function returns.
        conn = db.connect()

        # Build the page and turn it into raw bytes (HTTP sends bytes, not
        # Python str) using UTF-8, matching the charset declared in the HTML.
        body = render_page(conn).encode("utf-8")

        # A normal, successful HTML response: status 200, the right
        # Content-Type so the browser renders it as a web page instead of
        # downloading it, and Content-Length so the browser knows exactly
        # how many bytes to expect.
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def make_server(host: str = "127.0.0.1", port: int = 8000) -> http.server.ThreadingHTTPServer:
    """Build the server object WITHOUT starting it yet. Splitting this out
    from `serve()` below means a test can create a server, run it in a
    background thread, make a couple of requests, and shut it down again --
    `serve()` alone can't be tested that way since it blocks forever."""
    # ThreadingHTTPServer (vs. plain HTTPServer) handles each incoming
    # request on its own thread, so one slow request can't stall the whole
    # server -- overkill for a single person's dashboard, but it's a
    # one-word difference and costs nothing.
    return http.server.ThreadingHTTPServer((host, port), _Handler)


def serve(host: str = "127.0.0.1", port: int = 8000) -> None:
    """Start the dashboard and block until you press Ctrl+C. This is what
    `python -m price_tracker dashboard` actually calls."""
    # The "with" block ensures the underlying socket is closed properly even
    # if serve_forever() is interrupted (e.g. by Ctrl+C raising KeyboardInterrupt).
    with make_server(host, port) as httpd:
        print(f"Dashboard: http://{host}:{port}/ (Ctrl+C to stop)")
        httpd.serve_forever()
