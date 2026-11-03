"""Entry point: python -m price_tracker run"""

import os
import sys

import httpx
from dotenv import load_dotenv

from . import db
from .collectors import ebay
from .filters import lowest_valid
from .items import ITEMS


def run() -> int:
    load_dotenv()
    client_id = os.getenv("EBAY_CLIENT_ID")
    client_secret = os.getenv("EBAY_CLIENT_SECRET")
    if not client_id or not client_secret:
        print("Missing EBAY_CLIENT_ID / EBAY_CLIENT_SECRET. Copy .env.example to .env and fill them in.")
        return 1

    conn = db.connect()
    failures = 0
    with httpx.Client(timeout=30) as client:
        token = ebay.get_token(client, client_id, client_secret)
        for item in ITEMS:
            try:
                listings = ebay.search(client, token, item)
            except httpx.HTTPError as e:
                db.log_run(conn, source="ebay", item_id=item.id, status="error", message=str(e))
                print(f"{item.id}: error {e}")
                failures += 1
                continue

            best, kept = lowest_valid(item, listings)
            if best is None:
                db.log_run(conn, source="ebay", item_id=item.id, status="empty",
                           message=f"{len(listings)} seen, 0 passed filters")
                print(f"{item.id}: {len(listings)} listings seen, none passed the filters")
                continue

            db.save_observation(
                conn, item_id=item.id, source="ebay", price_total=best.total, currency=best.currency,
                listing_url=best.url, listing_title=best.title,
                listings_seen=len(listings), listings_kept=kept,
            )
            db.log_run(conn, source="ebay", item_id=item.id, status="ok")
            print(f"{item.id}: {len(listings)} seen, {kept} kept, lowest {best.currency} {best.total:,.2f}")
            print(f"  {best.title}")
            print(f"  {best.url}")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["run"]:
        return run()
    print("usage: python -m price_tracker run")
    return 2
