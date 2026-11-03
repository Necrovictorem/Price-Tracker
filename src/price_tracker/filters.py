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
    return re.search(rf"(?<![a-z0-9]){re.escape(term.lower())}(?![a-z0-9])", title.lower()) is not None


def is_valid(item: Item, listing: Listing) -> bool:
    if not all(_has_term(listing.title, t) for t in item.require):
        return False
    return not any(_has_term(listing.title, t) for t in item.exclude)


def lowest_valid(item: Item, listings: list[Listing]) -> tuple[Listing | None, int]:
    """Return the cheapest valid listing (price + shipping) and how many passed the filter."""
    kept = [l for l in listings if is_valid(item, l)]
    if not kept:
        return None, 0
    return min(kept, key=lambda l: l.total), len(kept)
