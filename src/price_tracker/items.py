"""What to watch. Rules are data so filters.py can stay generic."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Item:
    id: str
    query: str
    # Every term must appear in the title (whole-word, case-insensitive).
    require: list[str] = field(default_factory=list)
    # Any of these terms in the title rejects the listing.
    exclude: list[str] = field(default_factory=list)
    conditions: str = "USED"


EPYC_7B13 = Item(
    id="epyc-7b13",
    query="EPYC 7B13",
    require=["7B13"],
    exclude=[
        "lock", "locked", "vendor lock", "vendor locked",
        "dell", "lenovo", "hp", "hpe",
        "for parts", "not working", "broken",
        "lot", "x2", "2x", "pair", "qty",
        "engineering sample", "es", "qs",
    ],
)

ITEMS = [EPYC_7B13]
