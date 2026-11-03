import httpx
import respx

from price_tracker.collectors import reddit
from price_tracker.items import EPYC_7B13

# Three posts chosen to exercise each filter in parse_listings:
#   abc123 - a real sell post, should be kept
#   wtb456 - a "looking to buy" post (item only named after "[W]"), should be dropped
#   nop789 - a sell post with no price in the title, should be dropped
SAMPLE = {
    "data": {
        "children": [
            {
                "data": {
                    "id": "abc123",
                    "title": "[USA-CA][H] AMD EPYC 7B13 64-core $1200 shipped [W] PayPal",
                    "permalink": "/r/hardwareswap/comments/abc123/epyc_7b13/",
                }
            },
            {
                "data": {
                    "id": "wtb456",
                    "title": "[USA-NY][H] PayPal $1000 [W] EPYC 7B13",
                    "permalink": "/r/hardwareswap/comments/wtb456/looking_for_epyc/",
                }
            },
            {
                "data": {
                    "id": "nop789",
                    "title": "[USA-TX][H] EPYC 7B13 [W] PayPal",
                    "permalink": "/r/hardwareswap/comments/nop789/epyc_no_price/",
                }
            },
        ]
    }
}


def test_parse_listings_keeps_only_priced_sell_posts():
    listings = reddit.parse_listings(SAMPLE, EPYC_7B13)
    assert len(listings) == 1
    assert listings[0].item_id == "abc123"
    assert listings[0].price == 1200.0
    assert listings[0].url == "https://www.reddit.com/r/hardwareswap/comments/abc123/epyc_7b13/"


@respx.mock
def test_token_and_search():
    respx.post(reddit.TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "tok"}))
    search = respx.get(reddit.SEARCH_URL).mock(return_value=httpx.Response(200, json=SAMPLE))
    with httpx.Client() as client:
        token = reddit.get_token(client, "id", "secret", "price-tracker/0.1 test")
        listings = reddit.search(client, token, "price-tracker/0.1 test", EPYC_7B13)
    assert token == "tok"
    assert len(listings) == 1
    req = search.calls.last.request
    assert req.headers["Authorization"] == "Bearer tok"
    assert req.headers["User-Agent"] == "price-tracker/0.1 test"
