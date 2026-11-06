"""Below-target, new-low, and sharp-drop alerts, sent to ntfy once per run.

Read-only with respect to collection: it only looks at what's already in
`observations` plus the price just saved, and never fetches or filters
anything itself.
"""

import os
import sqlite3
from dataclasses import dataclass
from datetime import date, timedelta

import httpx

from .items import Item

SHARP_DROP_PCT = 0.15           # 15% drop triggers a "sharp drop" alert
SHARP_DROP_WINDOW_DAYS = 7      # ...measured against price roughly 7 days ago


@dataclass
class Alert:
    item_id: str
    kind: str      # "below_target" | "new_low" | "sharp_drop" -- which rule fired
    message: str    # human-readable line, goes straight into the ntfy push


def check(conn: sqlite3.Connection, item: Item, source: str, price_total: float, observed_on: date) -> list[Alert]:
    """Compare today's saved price for one item/source against its history
    and return every alert rule it triggers (zero, one, or more than one).
    Called once right after `db.save_observation` for that item/source."""
    alerts = []

    # Pull every prior day's price for this exact item+source, oldest first.
    # "< observed_on" so today's own row (already saved) isn't counted as history.
    history = conn.execute(
        "SELECT observed_on, price_total FROM observations WHERE item_id = ? AND source = ? AND observed_on < ?"
        " ORDER BY observed_on",
        (item.id, source, observed_on.isoformat()),
    ).fetchall()

    # Rule 1: below target. Only fires if you've set a target for this item.
    if item.target is not None and price_total <= item.target:
        alerts.append(Alert(item.id, "below_target",
                             f"{item.id}: {price_total:,.2f} is at or under your target of {item.target:,.2f}"))

    # Rule 2: new low. Only meaningful once there's at least one prior day to compare against.
    if history and price_total < min(p for _, p in history):
        alerts.append(Alert(item.id, "new_low", f"{item.id}: {price_total:,.2f} is the lowest seen yet"))

    # Rule 3: sharp drop. Find the most recent observation that's at least
    # SHARP_DROP_WINDOW_DAYS old (approximate "a week ago" -- a run can be
    # missing an exact day), then compare today's price to it.
    cutoff = (observed_on - timedelta(days=SHARP_DROP_WINDOW_DAYS)).isoformat()
    older = [p for d, p in history if d <= cutoff]
    if older:
        reference = older[-1]  # closest one to, but not after, the cutoff
        drop = (reference - price_total) / reference
        if drop >= SHARP_DROP_PCT:
            alerts.append(Alert(item.id, "sharp_drop",
                                 f"{item.id}: down {drop:.0%} from {reference:,.2f}"
                                 f" ~{SHARP_DROP_WINDOW_DAYS}d ago to {price_total:,.2f}"))
    return alerts


def send(client: httpx.Client, alerts: list[Alert]) -> None:
    """Send every alert collected during this run as ONE ntfy push (not one
    push per alert), so a run with several triggers is a single notification.
    Does nothing if there are no alerts, or if NTFY_TOPIC isn't configured."""
    if not alerts:
        return
    topic = os.getenv("NTFY_TOPIC")
    if not topic:
        # Alerts still "happened" -- print each one so they're not silently
        # lost just because ntfy isn't configured yet.
        print(f"  {len(alerts)} alert(s) triggered (NTFY_TOPIC isn't set, see .env.example):")
        for a in alerts:
            print(f"    - {a.message}")
        return
    server = os.getenv("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    body = "\n".join(a.message for a in alerts)  # one line per alert in the push body
    try:
        # ntfy's API is just: POST the message body to https://<server>/<topic>.
        client.post(f"{server}/{topic}", content=body.encode("utf-8"),
                     headers={"Title": "Price Tracker"}, timeout=10)
    except httpx.HTTPError as e:
        print(f"  ntfy send failed: {e}")
