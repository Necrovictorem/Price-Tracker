"""eBay Browse API collector (official API, app-level OAuth; no user login)."""

import base64

import httpx

from ..filters import Listing
from ..items import Item

PROD_TOKEN_URL = "https://api.ebay.com/identity/v1/oauth2/token"
PROD_SEARCH_URL = "https://api.ebay.com/buy/browse/v1/item_summary/search"
SANDBOX_TOKEN_URL = "https://api.sandbox.ebay.com/identity/v1/oauth2/token"
SANDBOX_SEARCH_URL = "https://api.sandbox.ebay.com/buy/browse/v1/item_summary/search"
SCOPE = "https://api.ebay.com/oauth/api_scope"


def get_token(client: httpx.Client, client_id: str, client_secret: str, *, sandbox: bool = False) -> str:
    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    resp = client.post(
        SANDBOX_TOKEN_URL if sandbox else PROD_TOKEN_URL,
        headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
        data={"grant_type": "client_credentials", "scope": SCOPE},
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def parse_listings(payload: dict) -> list[Listing]:
    listings = []
    for s in payload.get("itemSummaries", []):
        price = s.get("price")
        if not price:
            continue
        shipping = 0.0
        options = s.get("shippingOptions") or []
        if options and options[0].get("shippingCost"):
            shipping = float(options[0]["shippingCost"]["value"])
        listings.append(Listing(
            item_id=s.get("itemId", ""),
            title=s.get("title", ""),
            price=float(price["value"]),
            shipping=shipping,
            currency=price.get("currency", "USD"),
            url=s.get("itemWebUrl", ""),
            condition=s.get("condition", ""),
        ))
    return listings


def search(client: httpx.Client, token: str, item: Item, *, sandbox: bool = False, limit: int = 200) -> list[Listing]:
    resp = client.get(
        SANDBOX_SEARCH_URL if sandbox else PROD_SEARCH_URL,
        headers={"Authorization": f"Bearer {token}", "X-EBAY-C-MARKETPLACE-ID": "EBAY_US"},
        params={
            "q": item.query,
            "filter": f"buyingOptions:{{FIXED_PRICE}},conditions:{{{item.conditions}}},deliveryCountry:US",
            "limit": str(limit),
        },
    )
    resp.raise_for_status()
    return parse_listings(resp.json())
