from price_tracker.filters import Listing, is_valid, lowest_valid
from price_tracker.items import EPYC_7B13


def listing(title, price=1000.0, shipping=0.0):
    return Listing(item_id="x", title=title, price=price, shipping=shipping, currency="USD", url="u")


def test_clean_listing_passes():
    assert is_valid(EPYC_7B13, listing("AMD EPYC 7B13 64-Core 2.25GHz SP3 CPU Unlocked"))


def test_unlocked_is_not_mistaken_for_locked():
    assert is_valid(EPYC_7B13, listing("EPYC 7B13 unlocked tested"))


def test_series_does_not_trigger_es():
    assert is_valid(EPYC_7B13, listing("AMD EPYC 7003 Series 7B13 processor"))


def test_rejects_unwanted():
    for title in [
        "AMD EPYC 7B13 Dell vendor locked",
        "EPYC 7B13 Lenovo locked CPU",
        "Lot of 2 AMD EPYC 7B13",
        "AMD EPYC 7B13 for parts not working",
        "EPYC 7B13 ES engineering sample",
        "AMD EPYC 7713 64-core",  # wrong model
    ]:
        assert not is_valid(EPYC_7B13, listing(title)), title


def test_lowest_counts_shipping():
    a = listing("EPYC 7B13", price=1000, shipping=150)
    b = listing("EPYC 7B13", price=1100, shipping=0)
    c = listing("EPYC 7B13 Dell locked", price=500)
    best, kept = lowest_valid(EPYC_7B13, [a, b, c])
    assert best is b
    assert kept == 2


def test_no_valid_listings():
    best, kept = lowest_valid(EPYC_7B13, [listing("EPYC 7B13 for parts")])
    assert best is None and kept == 0
