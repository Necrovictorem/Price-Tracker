"""Generic include/exclude matching and lowest-price selection."""

import re
from dataclasses import dataclass

from .items import Item


@dataclass(frozen=True)
class Listing:
    item_id: str  # source's own listing id
    title: str
    price: float
    shipping: float
    currency: str
    url: str
    condition: str = ""

    @property
    def total(self) -> float:
        return round(self.price + self.shipping, 2)


def _has_term(title: str, term: str) -> bool:
    # Whole-word match, so "unlocked" doesn't hit "locked" and "series" doesn't hit "es".
    # A trailing "*" lets letters follow: "3200*" matches "3200", "3200aa", "3200mhz" but not "32000".
    if term.endswith("*"):
        pattern = rf"(?<![a-z0-9]){re.escape(term[:-1].lower())}(?![0-9])"
    else:
        pattern = rf"(?<![a-z0-9]){re.escape(term.lower())}(?![a-z0-9])"
    return re.search(pattern, title.lower()) is not None


def _normalize(item: Item, title: str) -> str:
    title = title.lower()
    # "64 GB" and "64GB" should match the same rule.
    title = re.sub(r"(\d+)\s+gb\b", r"\1gb", title)
    # "8x64GB" -> "8x 64gb", so the stick count and the stick size can be matched separately.
    title = re.sub(r"(\d+x)(\d)", r"\1 \2", title)
    # Phrases like "never mined" must not trip the "mined" exclude rule.
    for phrase in item.ignore:
        title = title.replace(phrase.lower(), " ")
    return title


def is_valid(item: Item, listing: Listing) -> bool:
    title = _normalize(item, listing.title)
    if not all(_has_term(title, t) for t in item.require):
        return False
    return not any(_has_term(title, t) for t in item.exclude)


def lowest_valid(item: Item, listings: list[Listing]) -> tuple[Listing | None, int]:
    """Return the cheapest valid listing (price + shipping) and how many passed the filter."""
    kept = [l for l in listings if is_valid(item, l)]
    if not kept:
        return None, 0
    return min(kept, key=lambda l: l.total), len(kept)
