"""Entry point: python -m price_tracker run"""

import os
import sys

import httpx
from dotenv import load_dotenv

from . import db
from .collectors import ebay, reddit
from .filters import lowest_valid
from .items import ITEMS


def _save_result(conn, source: str, item, listings) -> None:
    # Shared by both sources: apply this item's filter rules, then either log
    # that nothing survived, or save the cheapest valid listing for today.
    best, kept = lowest_valid(item, listings)
    if best is None:
        db.log_run(conn, source=source, item_id=item.id, status="empty",
                   message=f"{len(listings)} seen, 0 passed filters")
        print(f"{item.id} [{source}]: {len(listings)} listings seen, none passed the filters")
        return

    db.save_observation(
        conn, item_id=item.id, source=source, price_total=best.total, currency=best.currency,
        listing_url=best.url, listing_title=best.title,
        listings_seen=len(listings), listings_kept=kept,
    )
    db.log_run(conn, source=source, item_id=item.id, status="ok")
    print(f"{item.id} [{source}]: {len(listings)} seen, {kept} kept, lowest {best.currency} {best.total:,.2f}")
    print(f"  {best.title}")
    print(f"  {best.url}")


def run() -> int:
    load_dotenv()  # reads .env into this process's environment; does nothing if it's missing.

    # Check every credential up front so a missing Reddit key doesn't let the
    # run get halfway through before failing.
    creds = {
        "EBAY_CLIENT_ID": os.getenv("EBAY_CLIENT_ID"),
        "EBAY_CLIENT_SECRET": os.getenv("EBAY_CLIENT_SECRET"),
        "REDDIT_CLIENT_ID": os.getenv("REDDIT_CLIENT_ID"),
        "REDDIT_CLIENT_SECRET": os.getenv("REDDIT_CLIENT_SECRET"),
        "REDDIT_USER_AGENT": os.getenv("REDDIT_USER_AGENT"),
    }
    missing = [name for name, value in creds.items() if not value]
    if missing:
        print(f"Missing {', '.join(missing)}. Copy .env.example to .env and fill them in.")
        return 1

    conn = db.connect()
    failures = 0

    # One httpx.Client for the whole run: it reuses the underlying TCP connection
    # instead of opening a new one for every request.
    with httpx.Client(timeout=30) as client:
        # Each source needs only one auth token per run, not one per item.
        ebay_token = ebay.get_token(client, creds["EBAY_CLIENT_ID"], creds["EBAY_CLIENT_SECRET"])
        reddit_token = reddit.get_token(
            client, creds["REDDIT_CLIENT_ID"], creds["REDDIT_CLIENT_SECRET"], creds["REDDIT_USER_AGENT"]
        )

        for item in ITEMS:
            # eBay: if the request itself fails (timeout, bad response, etc.),
            # log it and keep going — one bad item shouldn't stop the whole run.
            try:
                listings = ebay.search(client, ebay_token, item)
            except httpx.HTTPError as e:
                db.log_run(conn, source="ebay", item_id=item.id, status="error", message=str(e))
                print(f"{item.id} [ebay]: error {e}")
                failures += 1
            else:
                _save_result(conn, "ebay", item, listings)

            # Same pattern for Reddit, logged under its own source name so the
            # two sources never collide in the observations table.
            try:
                listings = reddit.search(client, reddit_token, creds["REDDIT_USER_AGENT"], item)
            except httpx.HTTPError as e:
                db.log_run(conn, source="hardwareswap", item_id=item.id, status="error", message=str(e))
                print(f"{item.id} [hardwareswap]: error {e}")
                failures += 1
            else:
                _save_result(conn, "hardwareswap", item, listings)

    # Exit code convention: 0 = everything ran clean, 1 = at least one source/item errored.
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["run"]:
        return run()
    print("usage: python -m price_tracker run")
    return 2
