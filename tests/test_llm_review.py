import json

import httpx
import respx

from price_tracker import llm_review
from price_tracker.filters import Listing


def listing(title):
    return Listing(item_id="x", title=title, price=100.0, shipping=0.0, currency="USD", url="u")


@respx.mock
def test_standalone_and_bundle_verdicts():
    respx.post(llm_review.OLLAMA_CHAT_URL).mock(return_value=httpx.Response(200, json={
        "message": {"content": '[{"index": 0, "verdict": "standalone", "confidence": 0.9, "reason": "one cpu"}, '
                                 '{"index": 1, "verdict": "bundle", "confidence": 0.95, "reason": "cpu+board"}]'}
    }))
    listings = [listing("AMD EPYC 7B13 CPU"), listing("H12SSL-i + EPYC 7502 Combo")]
    with httpx.Client() as client:
        result = llm_review.classify(client, listings)
    assert result[0]["verdict"] == "standalone"
    assert result[1]["verdict"] == "bundle"


@respx.mock
def test_malformed_json_retries_then_falls_back_to_review():
    route = respx.post(llm_review.OLLAMA_CHAT_URL).mock(
        return_value=httpx.Response(200, json={"message": {"content": "not json"}})
    )
    with httpx.Client() as client:
        result = llm_review.classify(client, [listing("AMD EPYC 7B13 CPU")])
    assert result == {}  # caller's fallback: leave it in review
    assert route.call_count == 2  # retried once before giving up


@respx.mock
def test_unknown_verdict_is_dropped_not_trusted():
    respx.post(llm_review.OLLAMA_CHAT_URL).mock(return_value=httpx.Response(200, json={
        "message": {"content": '[{"index": 0, "verdict": "maybe", "confidence": 0.5, "reason": "?"}]'}
    }))
    with httpx.Client() as client:
        result = llm_review.classify(client, [listing("AMD EPYC 7B13 CPU")])
    assert result == {}


def test_empty_batch_skips_the_call():
    with httpx.Client() as client:
        assert llm_review.classify(client, []) == {}


@respx.mock
def test_unload_sends_zero_keep_alive():
    route = respx.post(llm_review.OLLAMA_GENERATE_URL).mock(return_value=httpx.Response(200, json={}))
    with httpx.Client() as client:
        llm_review.unload(client)
    sent = json.loads(route.calls.last.request.content)
    assert sent == {"model": llm_review.MODEL, "keep_alive": 0}
