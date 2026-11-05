import httpx
import respx

from price_tracker.collectors import ebay
from price_tracker.items import EPYC_7B13

SAMPLE = {
    "itemSummaries": [
        {
            "itemId": "v1|111|0",
            "title": "AMD EPYC 7B13 64-Core CPU Unlocked",
            "price": {"value": "1250.00", "currency": "USD"},
            "shippingOptions": [{"shippingCost": {"value": "15.00", "currency": "USD"}}],
            "itemWebUrl": "https://www.ebay.com/itm/111",
            "condition": "Used",
        },
        {
            "itemId": "v1|222|0",
            "title": "EPYC 7B13 free shipping",
            "price": {"value": "1300.00", "currency": "USD"},
            "itemWebUrl": "https://www.ebay.com/itm/222",
        },
        {"itemId": "v1|333|0", "title": "no price listing"},
    ]
}


def test_parse_listings():
    listings = ebay.parse_listings(SAMPLE)
    assert len(listings) == 2
    assert listings[0].total == 1265.00
    assert listings[1].shipping == 0.0
    assert listings[0].url == "https://www.ebay.com/itm/111"


@respx.mock
def test_token_and_search():
    respx.post(ebay.PROD_TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "tok"}))
    search = respx.get(ebay.PROD_SEARCH_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    with httpx.Client() as client:
        token = ebay.get_token(client, "id", "secret")
        listings = ebay.search(client, token, EPYC_7B13)
    assert token == "tok"
    assert len(listings) == 2
    req = search.calls.last.request
    assert req.headers["Authorization"] == "Bearer tok"
    assert "conditions%3A%7BUSED%7D" in str(req.url) or "conditions:{USED}" in str(req.url)


@respx.mock
def test_sandbox_uses_sandbox_urls():
    respx.post(ebay.SANDBOX_TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "tok"}))
    respx.get(ebay.SANDBOX_SEARCH_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    with httpx.Client() as client:
        token = ebay.get_token(client, "id", "secret", sandbox=True)
        listings = ebay.search(client, token, EPYC_7B13, sandbox=True)
    assert token == "tok"
    assert len(listings) == 2
