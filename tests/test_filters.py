from price_tracker.filters import Listing, classify, is_valid, lowest_valid, review_candidates
from price_tracker.items import (
    DDR4_512GB_KIT,
    DDR4_64GB_RDIMM,
    DDR5_64GB_RDIMM,
    EPYC_7713,
    EPYC_7B13,
    H12SSL,
    RTX_3090,
    RTX_5090,
    RTX_PRO_4500,
)


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


def test_mining_rejected_but_never_mined_allowed():
    assert not is_valid(RTX_3090, listing("RTX 3090 24GB used for ETH mining"))
    assert not is_valid(RTX_3090, listing("RTX 3090 from crypto rig"))
    assert is_valid(RTX_3090, listing("RTX 3090 24GB Never Mined, gaming only"))


def test_previous_generation_ada_rejected():
    assert not is_valid(RTX_PRO_4500, listing("NVIDIA RTX 4500 Ada Generation 24GB"))
    assert is_valid(RTX_PRO_4500, listing("New NVIDIA RTX PRO 4500 Blackwell 32GB GDDR7 (OEM)"))


def test_prebuilt_pc_rejected():
    assert not is_valid(RTX_5090, listing("Gaming PC i9 RTX 5090 64GB RAM"))
    assert is_valid(RTX_5090, listing("ASUS ROG Astral RTX 5090 32GB triple fan"))


def test_gb_spacing_normalized():
    assert is_valid(DDR5_64GB_RDIMM, listing("Samsung 64 GB DDR5-4800 RDIMM 2Rx4"))
    assert not is_valid(DDR5_64GB_RDIMM, listing("8x 64GB DDR5 RDIMM kit"))


def test_ddr4_speed_wildcard():
    assert is_valid(DDR4_64GB_RDIMM, listing("Samsung 64GB 2Rx4 PC4-3200AA-R DDR4 RDIMM"))
    assert is_valid(DDR4_64GB_RDIMM, listing("Micron 64 GB DDR4 3200MHz ECC Registered"))
    assert not is_valid(DDR4_64GB_RDIMM, listing("Samsung 64GB DDR4 2933 RDIMM"))


def test_ddr4_single_stick_rejects_kits():
    assert not is_valid(DDR4_64GB_RDIMM, listing("2x64GB DDR4-3200 RDIMM"))


def test_ddr4_512gb_kit_must_be_eight_sticks():
    assert is_valid(DDR4_512GB_KIT, listing("512GB (8x64GB) DDR4-3200 RDIMM Server Memory"))
    assert not is_valid(DDR4_512GB_KIT, listing("512GB (4x128GB) DDR4-3200 LRDIMM"))
    assert not is_valid(DDR4_512GB_KIT, listing("512GB 16x32GB DDR4 3200 RDIMM"))


def test_7713_and_board_variants():
    assert is_valid(EPYC_7713, listing("AMD EPYC 7713 64 Core 2.0GHz Unlocked"))
    assert is_valid(H12SSL, listing("Supermicro H12SSL-i ATX SP3 motherboard"))
    assert is_valid(H12SSL, listing("Supermicro H12SSL-NT 10GbE"))


def test_board_combo_flagged_for_review_not_tracked():
    combo = listing("Supermicro H12SSL-i ATX Server Motherboard + EPYC 7502 CPU Combo")
    assert classify(H12SSL, combo) == "review"
    assert not is_valid(H12SSL, combo)

    board_only = listing("Supermicro H12SSL-i ATX SP3 motherboard")
    assert classify(H12SSL, board_only) == "valid"


def test_review_candidates_excluded_from_lowest_valid():
    combo = listing("Supermicro H12SSL-i Motherboard + EPYC 7502 CPU Bundle", price=200)
    board = listing("Supermicro H12SSL-i ATX SP3 motherboard", price=500)
    best, kept = lowest_valid(H12SSL, [combo, board])
    assert best is board  # the cheaper combo is never picked as the tracked price
    assert kept == 1
    assert review_candidates(H12SSL, [combo, board]) == [combo]
