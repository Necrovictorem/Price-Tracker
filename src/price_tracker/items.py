"""What to watch. Rules are data so filters.py can stay generic."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Item:
    id: str
    query: str
    # Every term must appear in the title (whole-word, case-insensitive; "*" suffix allows trailing letters).
    require: list[str] = field(default_factory=list)
    # Any of these terms in the title rejects the listing.
    exclude: list[str] = field(default_factory=list)
    # Any of these terms flags the listing for manual review instead of excluding or tracking it.
    review: list[str] = field(default_factory=list)
    # Phrases removed from the title before matching (e.g. "never mined").
    ignore: list[str] = field(default_factory=list)
    conditions: str = "USED"


CPU_EXCLUDE = [
    "lock", "locked", "vendor lock", "vendor locked",
    "dell", "lenovo", "hp", "hpe",
    "for parts", "parts only", "parts or repair", "not working", "non-working", "non working", "broken",
    "lot", "x2", "2x", "pair", "qty",
    "engineering sample", "es", "qs",
]

BOARD_EXCLUDE = [
    "for parts", "parts only", "parts or repair", "not working", "non-working", "non working", "broken",
    "as is", "bent pins", "lot",
    # Accessories that mention the board model name
    "riser", "i/o shield", "bios chip", "cooler", "rdimm", "memory", "heat sink", "heatsink",
]

RAM_EXCLUDE = [
    "udimm", "sodimm", "so-dimm", "laptop", "desktop",
    "for parts", "not working", "non-working", "non working",
]

GPU_EXCLUDE = [
    # Not a working card
    "for parts", "parts only", "parts or repair", "not working", "non-working", "non working",
    "broken", "as is", "untested", "no display", "artifacts", "no gpu",
    "no core", "no vram",
    # Not a single card
    "lot", "bundle", "x2", "2x", "pair",
    # Accessories that mention the model name
    "box only", "empty box", "packaging only", "waterblock", "water block", "block",
    "backplate", "bracket", "shroud", "heatsink", "enclosure", "connector", "case for",
    # Mining history
    "mining", "mined", "miner", "crypto", "eth", "ethereum", "hashrate", "rig",
]

GPU_IGNORE = ["never mined", "not mined", "no mining", "non mining", "non-mining"]

# Whole computers that contain the GPU
PREBUILT = ["pc", "desktop", "computer", "system", "laptop", "notebook", "zbook", "ryzen", "intel core"]


# Path A: Milan + DDR4 (8 channels, ~205 GB/s)
EPYC_7B13 = Item(id="epyc-7b13", query="EPYC 7B13", require=["7B13"], exclude=CPU_EXCLUDE)

EPYC_7713 = Item(id="epyc-7713", query="EPYC 7713", require=["7713"], exclude=CPU_EXCLUDE)

EPYC_7543 = Item(id="epyc-7543", query="EPYC 7543", require=["7543"], exclude=CPU_EXCLUDE)

H12SSL = Item(
    id="h12ssl",
    query="Supermicro H12SSL",
    require=["h12ssl"],
    exclude=BOARD_EXCLUDE,
    review=["combo*", "bundle*"],
    conditions="NEW|USED",
)

DDR4_64GB_RDIMM = Item(
    id="ddr4-64gb-rdimm",
    query="64GB DDR4 3200 RDIMM",
    require=["64gb", "ddr4", "3200*"],
    exclude=RAM_EXCLUDE + ["kit", "lot", "pack", "2x", "4x", "8x"],
    conditions="NEW|USED",
)

DDR4_512GB_KIT = Item(
    id="ddr4-512gb-kit",
    query="512GB DDR4 3200 RDIMM 8x64GB",
    require=["512gb", "ddr4", "3200*"],
    exclude=RAM_EXCLUDE + ["4x", "16x", "128gb", "32gb"],
    conditions="NEW|USED",
)

# Path B: Genoa + DDR5 (12 channels, ~461 GB/s)
EPYC_9354 = Item(id="epyc-9354", query="EPYC 9354", require=["9354"], exclude=CPU_EXCLUDE)

H13SSL_N = Item(
    id="h13ssl-n",
    query="Supermicro H13SSL-N",
    require=["h13ssl"],
    exclude=BOARD_EXCLUDE,
    review=["combo*", "bundle*"],
    conditions="NEW|USED",
)

DDR5_64GB_RDIMM = Item(
    id="ddr5-64gb-rdimm",
    query="64GB DDR5 RDIMM",
    require=["64gb", "ddr5"],
    exclude=RAM_EXCLUDE + ["kit", "lot", "pack", "2x", "4x", "8x", "12x"],
    conditions="NEW|USED",
)

# GPUs
RTX_PRO_4500 = Item(
    id="rtx-pro-4500",
    query="RTX PRO 4500 Blackwell",
    require=["4500", "blackwell"],
    exclude=GPU_EXCLUDE + PREBUILT + ["ada"],
    ignore=GPU_IGNORE,
    conditions="NEW|USED",
)

RTX_PRO_5000 = Item(
    id="rtx-pro-5000",
    query="RTX PRO 5000 Blackwell",
    require=["5000", "blackwell"],
    exclude=GPU_EXCLUDE + PREBUILT + ["ada"],
    ignore=GPU_IGNORE,
    conditions="NEW|USED",
)

RTX_PRO_6000 = Item(
    id="rtx-pro-6000",
    query="RTX PRO 6000 Blackwell",
    require=["6000", "blackwell"],
    exclude=GPU_EXCLUDE + PREBUILT + ["ada"],
    ignore=GPU_IGNORE,
    conditions="NEW|USED",
)

RTX_5090 = Item(
    id="rtx-5090",
    query="RTX 5090",
    require=["5090"],
    exclude=GPU_EXCLUDE + PREBUILT + ["workstation"],
    ignore=GPU_IGNORE,
    conditions="NEW|USED",
)

RTX_3090 = Item(
    id="rtx-3090",
    query="RTX 3090",
    require=["3090"],
    exclude=GPU_EXCLUDE + PREBUILT + ["ti", "workstation"],
    ignore=GPU_IGNORE,
)

ITEMS = [
    # Path A: Milan + DDR4 (8 channels, ~205 GB/s)
    EPYC_7B13, EPYC_7713, EPYC_7543, H12SSL, DDR4_64GB_RDIMM, DDR4_512GB_KIT,
    # Path B: Genoa + DDR5 (12 channels, ~461 GB/s)
    EPYC_9354, H13SSL_N, DDR5_64GB_RDIMM,
    # GPUs
    RTX_PRO_4500, RTX_PRO_5000, RTX_PRO_6000, RTX_5090, RTX_3090,
]
