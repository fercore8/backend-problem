"""Core domain models.

We model a Polymarket binary market as a single tradeable YES share that pays
$1 if the event resolves YES and $0 otherwise.  The NO side is the mirror image
(buying NO == selling YES), so every decision can be expressed in YES terms:

    * Buy YES at the ask  -> profit if our P(YES) is higher than the ask.
    * Buy NO  at (1-bid)  -> profit if our P(YES) is lower than the bid.

Prices are probabilities in [0, 1].  Sizes are in *shares* (each settling to $1).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Side(str, Enum):
    YES = "YES"
    NO = "NO"


@dataclass(frozen=True)
class Level:
    """One price level of an order book."""

    price: float
    size: float  # shares available at this price


@dataclass
class OrderBook:
    """Top-of-book first.  bids descending by price, asks ascending by price."""

    bids: list[Level] = field(default_factory=list)
    asks: list[Level] = field(default_factory=list)

    @property
    def best_bid(self) -> Optional[float]:
        return self.bids[0].price if self.bids else None

    @property
    def best_ask(self) -> Optional[float]:
        return self.asks[0].price if self.asks else None

    @property
    def mid(self) -> Optional[float]:
        if self.best_bid is None or self.best_ask is None:
            return None
        return (self.best_bid + self.best_ask) / 2.0

    @property
    def spread(self) -> Optional[float]:
        if self.best_bid is None or self.best_ask is None:
            return None
        return self.best_ask - self.best_bid

    def depth(self, side: str) -> float:
        """Total shares resting on a side ('bids' or 'asks')."""
        levels = self.bids if side == "bids" else self.asks
        return sum(lv.size for lv in levels)


@dataclass
class Market:
    """A single binary market keyed on its YES token."""

    id: str
    question: str
    book: OrderBook
    end_date: Optional[str] = None        # ISO date, when the market resolves
    liquidity_usd: float = 0.0            # rough resting liquidity, for sanity caps
    group_id: Optional[str] = None        # mutually-exclusive set (e.g. one election)
    resolved: Optional[bool] = None       # True/False once settled; None while live

    @property
    def market_price(self) -> Optional[float]:
        """Best single-number read of the market's implied P(YES)."""
        return self.book.mid


@dataclass
class Signal:
    """A trade idea produced by the strategy layer (before risk sizing)."""

    market_id: str
    side: Side
    fair_prob: float       # our estimate of P(YES)
    price: float           # best-of-book price we'd pay for the chosen side
    edge: float            # expected profit per share at `price`, net of costs
    kelly_fraction: float  # fraction of bankroll Kelly suggests (pre risk caps)
    limit_price: float = 1.0  # worst price still clearing min_edge (book-walk cap)

    @property
    def is_actionable(self) -> bool:
        return self.edge > 0 and self.kelly_fraction > 0


@dataclass
class Order:
    market_id: str
    side: Side
    shares: float
    limit_price: float  # max price for a buy


@dataclass
class Fill:
    market_id: str
    side: Side
    shares: float        # shares actually filled
    avg_price: float     # volume-weighted fill price
    cost: float          # shares * avg_price

    @property
    def filled(self) -> bool:
        return self.shares > 0


@dataclass
class Position:
    market_id: str
    side: Side
    shares: float
    avg_price: float

    @property
    def cost_basis(self) -> float:
        return self.shares * self.avg_price
