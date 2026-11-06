"""Entry point: python -m price_tracker run"""

import os
import sys

import httpx
from dotenv import load_dotenv

from . import db, llm_review
from .collectors import ebay
# from .collectors import reddit  # dormant — see collectors/reddit.py's module docstring
from .filters import lowest_valid, review_candidates
from .items import ITEMS


def _save_result(conn, source: str, item, listings, verdict_by_listing: dict) -> None:
    # Ambiguous listings (bundles, etc.): an LLM "standalone" verdict promotes
    # one back into price comparison below; everything else is logged for
    # Antonio to look at, never counted as the tracked price.
    reviews = review_candidates(item, listings)
    promoted = []
    for r in reviews:
        verdict = verdict_by_listing.get(r)
        if verdict and verdict["verdict"] == "standalone":
            promoted.append(r)
        else:
            db.save_review_listing(
                conn, item_id=item.id, source=source, price_total=r.total, currency=r.currency,
                listing_url=r.url, listing_title=r.title,
                verdict=verdict["verdict"] if verdict else None,
                confidence=verdict["confidence"] if verdict else None,
                reason=verdict["reason"] if verdict else None,
            )

    # Shared by both sources: apply this item's filter rules, add back any
    # LLM-promoted listings, then either log that nothing survived, or save
    # the cheapest of the two pools as today's price.
    kw_best, kw_kept = lowest_valid(item, listings)
    candidates = ([kw_best] if kw_best else []) + promoted
    if not candidates:
        db.log_run(conn, source=source, item_id=item.id, status="empty",
                   message=f"{len(listings)} seen, 0 passed filters")
        print(f"{item.id} [{source}]: {len(listings)} listings seen, none passed the filters")
    else:
        best = min(candidates, key=lambda l: l.total)
        kept = kw_kept + len(promoted)
        db.save_observation(
            conn, item_id=item.id, source=source, price_total=best.total, currency=best.currency,
            listing_url=best.url, listing_title=best.title,
            listings_seen=len(listings), listings_kept=kept,
            price_source="llm" if best in promoted else "keyword",
        )
        db.log_run(conn, source=source, item_id=item.id, status="ok")
        print(f"{item.id} [{source}]: {len(listings)} seen, {kept} kept, lowest {best.currency} {best.total:,.2f}")
        print(f"  {best.title}")
        print(f"  {best.url}")
        if best in promoted:
            print(f"  (LLM-promoted from review: {verdict_by_listing[best]['reason']})")

    still_in_review = len(reviews) - len(promoted)
    if still_in_review:
        print(f"  ({still_in_review} listing(s) flagged for review, not counted — see `view --review`)")


def run() -> int:
    load_dotenv()  # reads .env into this process's environment; does nothing if it's missing.

    creds = {
        "EBAY_CLIENT_ID": os.getenv("EBAY_CLIENT_ID"),
        "EBAY_CLIENT_SECRET": os.getenv("EBAY_CLIENT_SECRET"),
    }
    missing = [name for name, value in creds.items() if not value]
    if missing:
        print(f"Missing {', '.join(missing)}. Copy .env.example to .env and fill them in.")
        return 1

    # Sandbox keys hit a separate eBay environment with fake test listings.
    # Tag sandbox-origin rows with a different `source` so they can never
    # blend into real price history, and announce the environment up front
    # so a forgotten EBAY_ENV=sandbox doesn't go unnoticed.
    sandbox = os.getenv("EBAY_ENV", "production").strip().lower() == "sandbox"
    ebay_source = "ebay-sandbox" if sandbox else "ebay"
    print(f"eBay environment: {'SANDBOX (test data only)' if sandbox else 'production'}")

    conn = db.connect()
    failures = 0
    results = []  # (item, listings) for everything that fetched successfully

    # One httpx.Client for the whole run: it reuses the underlying TCP connection
    # instead of opening a new one for every request. Also used for the local
    # Ollama calls below -- it's a plain HTTP client, not tied to eBay.
    with httpx.Client(timeout=30) as client:
        ebay_token = ebay.get_token(client, creds["EBAY_CLIENT_ID"], creds["EBAY_CLIENT_SECRET"], sandbox=sandbox)

        # --- Reddit (r/hardwareswap): dormant, see collectors/reddit.py --------
        # Uncomment this plus the `reddit` import above and the block in the
        # loop below to re-enable, once/if Reddit grants API access.
        # reddit_token = reddit.get_token(
        #     client, os.getenv("REDDIT_CLIENT_ID"), os.getenv("REDDIT_CLIENT_SECRET"),
        #     os.getenv("REDDIT_USER_AGENT"),
        # )
        # -------------------------------------------------------------------

        for item in ITEMS:
            # eBay: if the request itself fails (timeout, bad response, etc.),
            # log it and keep going — one bad item shouldn't stop the whole run.
            try:
                listings = ebay.search(client, ebay_token, item, sandbox=sandbox)
            except httpx.HTTPError as e:
                db.log_run(conn, source=ebay_source, item_id=item.id, status="error", message=str(e))
                print(f"{item.id} [{ebay_source}]: error {e}")
                failures += 1
            else:
                results.append((item, listings))

            # --- Reddit (r/hardwareswap): dormant, see note above -----------
            # try:
            #     listings = reddit.search(client, reddit_token, os.getenv("REDDIT_USER_AGENT"), item)
            # except httpx.HTTPError as e:
            #     db.log_run(conn, source="hardwareswap", item_id=item.id, status="error", message=str(e))
            #     print(f"{item.id} [hardwareswap]: error {e}")
            #     failures += 1
            # else:
            #     results.append((item, listings))  # under its own source, if ever revived
            # ------------------------------------------------------------------

        # One LLM call for every item's review-tier listings together, instead
        # of one per item -- the model cold-loads either way (it unloads after
        # ~5 min idle), so batching avoids paying that load more than once per run.
        candidates = [(item, r) for item, listings in results for r in review_candidates(item, listings)]
        verdicts = llm_review.classify(client, [r for _, r in candidates]) if candidates else {}
        if candidates:
            llm_review.unload(client)
        verdict_by_listing = {candidates[i][1]: v for i, v in verdicts.items()}

        for item, listings in results:
            _save_result(conn, ebay_source, item, listings, verdict_by_listing)

    # Exit code convention: 0 = everything ran clean, 1 = at least one source/item errored.
    return 1 if failures else 0


def view(review: bool = False) -> int:
    conn = db.connect()
    if review:
        rows = conn.execute("""
            SELECT item_id, source, observed_on, price_total, currency, listing_title, listing_url, verdict
            FROM review_listings
            ORDER BY observed_on DESC, item_id, source
        """).fetchall()
        if not rows:
            print("No review-flagged listings.")
            return 0
        print(f"{'ITEM':<18} {'SOURCE':<14} {'DATE':<11} {'PRICE':>12}  {'VERDICT':<11} TITLE")
        for item_id, source, observed_on, price_total, currency, title, url, verdict in rows:
            price = f"{currency} {price_total:,.2f}"
            short_title = title if len(title) <= 50 else title[:47] + "..."
            print(f"{item_id:<18} {source:<14} {observed_on:<11} {price:>12}  {verdict or '-':<11} {short_title}")
            print(f"  {url}")
        return 0

    # For each item/source pair, join against the max observed_on for that pair
    # so we only show the single most recent row — not every historical day.
    rows = conn.execute("""
        SELECT o.item_id, o.source, o.observed_on, o.price_total, o.currency, o.listing_title
        FROM observations o
        JOIN (
            SELECT item_id, source, MAX(observed_on) AS latest
            FROM observations
            GROUP BY item_id, source
        ) m ON o.item_id = m.item_id AND o.source = m.source AND o.observed_on = m.latest
        ORDER BY o.item_id, o.source
    """).fetchall()

    if not rows:
        print("No observations yet. Run `python -m price_tracker run` first.")
        return 0

    print(f"{'ITEM':<18} {'SOURCE':<14} {'DATE':<11} {'PRICE':>12}  TITLE")
    for item_id, source, observed_on, price_total, currency, title in rows:
        price = f"{currency} {price_total:,.2f}"
        short_title = title if len(title) <= 50 else title[:47] + "..."
        print(f"{item_id:<18} {source:<14} {observed_on:<11} {price:>12}  {short_title}")
    return 0


def main(argv: list[str] | None = None) -> int:
    # Listing titles are free text from strangers on eBay and can contain characters
    # the Windows console's default codepage can't display (emoji, symbols, etc.).
    # Replace them instead of letting print() crash the whole run.
    sys.stdout.reconfigure(errors="replace")
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["run"]:
        return run()
    if argv[:1] == ["view"]:
        return view(review="--review" in argv[1:])
    print("usage: python -m price_tracker run|view [--review]")
    return 2
