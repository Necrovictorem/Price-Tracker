"""r/hardwareswap collector via Reddit's official API (app-only OAuth; no user login).

Status: written and tested, but not currently wired into cli.py. Reddit declined
the Data API access request on 2026-11-04 (generic "not in compliance with
Responsible Builder Policy and/or lacks necessary details" — no specifics given).
See the commented-out block in cli.py's run() for how to re-enable this if
access is ever granted on a future request.
"""

import re

import httpx

from ..filters import Listing
from ..items import Item

# "Application only" OAuth: the app proves who it is with client_id/secret,
# but no human account logs in and no browsing session is created.
TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
SEARCH_URL = "https://oauth.reddit.com/r/hardwareswap/search"

# Matches a dollar amount like "$1,200" or "$1200.00" and captures the digits
# (with any comma separators, stripped later before converting to float).
PRICE_RE = re.compile(r"\$\s?(\d[\d,]*(?:\.\d{2})?)")


def get_token(client: httpx.Client, client_id: str, client_secret: str, user_agent: str) -> str:
    # httpx's `auth=(id, secret)` sends an HTTP Basic Authorization header for us,
    # the same mechanism eBay's collector builds by hand with base64.
    resp = client.post(
        TOKEN_URL,
        auth=(client_id, client_secret),
        headers={"User-Agent": user_agent},  # Reddit rejects requests with no/generic User-Agent.
        data={"grant_type": "client_credentials"},
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def _have_section(title: str) -> str:
    # hardwareswap titles look like "[USA-CA][H] <item> [W] <what they want>".
    # Everything before "[W]" is what the poster is selling; everything after is
    # what they want in return. A post that only names the item after "[W]" is
    # someone looking to BUY it, not a price we should record.
    match = re.search(r"\[w\]", title, re.IGNORECASE)
    return title[: match.start()] if match else title


def parse_listings(payload: dict, item: Item) -> list[Listing]:
    listings = []
    for child in payload.get("data", {}).get("children", []):
        post = child.get("data", {})
        title = post.get("title", "")

        # Gate 1: the item must be named on the "have" side, not just the "want" side.
        have = _have_section(title)
        if not any(term.rstrip("*").lower() in have.lower() for term in item.require):
            continue

        # Gate 2: subreddit rules require a price in the title. If there isn't one,
        # we have no reliable number to record, so skip rather than guess.
        price_match = PRICE_RE.search(title)
        if not price_match:
            continue

        listings.append(Listing(
            item_id=post.get("id", ""),
            title=title,
            price=float(price_match.group(1).replace(",", "")),
            shipping=0.0,  # hardwareswap prices are usually quoted "shipped"; no separate field.
            currency="USD",
            url="https://www.reddit.com" + post.get("permalink", ""),
            condition="Used",  # hardwareswap is person-to-person; treat everything as used.
        ))
    return listings


def search(client: httpx.Client, token: str, user_agent: str, item: Item, limit: int = 50) -> list[Listing]:
    resp = client.get(
        SEARCH_URL,
        headers={"Authorization": f"Bearer {token}", "User-Agent": user_agent},
        params={
            "q": item.query,
            "restrict_sr": "1",  # search only within r/hardwareswap, not all of Reddit.
            "sort": "new",
            "limit": str(limit),
        },
    )
    resp.raise_for_status()
    return parse_listings(resp.json(), item)
