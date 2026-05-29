"""Strategy: convert a fair value into a sized, cost-aware trade idea."""

from .kelly import kelly_fraction
from .edge import CostModel, build_signal
from .arbitrage import ArbOpportunity, find_dutch_book

__all__ = [
    "kelly_fraction",
    "CostModel",
    "build_signal",
    "ArbOpportunity",
    "find_dutch_book",
]
