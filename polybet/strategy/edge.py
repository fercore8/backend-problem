"""Edge detection: the gate that decides whether a market is worth trading.

Given our fair P(YES) and the live book, we evaluate both sides net of costs and
emit a Signal only when the edge clears the minimum threshold.  Buying the wrong
side, or buying a real edge that is smaller than the spread we cross, is how
prediction-market accounts quietly bleed out — so this module is deliberately
conservative.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ..config import Settings
from ..models import Market, Side, Signal
from .kelly import kelly_fraction


@dataclass
class CostModel:
    """All-in cost of crossing the spread to take liquidity, per share."""

    taker_fee: float = 0.0
    slippage: float = 0.005

    def effective_buy_price(self, quoted: float) -> float:
        """Price we actually expect to pay for a marketable buy."""
        return quoted * (1.0 + self.taker_fee) + self.slippage

    def worst_quote_for_edge(self, win_prob: float, min_edge: float) -> float:
        """Worst raw quote we can pay and still clear ``min_edge``.

        Inverts ``effective_buy_price``: solve win_prob - effective(q) >= min_edge
        for q. This is the order's limit price, so a marketable order may walk
        into book depth yet every filled share still beats the edge gate.
        """
        return (win_prob - min_edge - self.slippage) / (1.0 + self.taker_fee)


def build_signal(
    market: Market,
    fair_prob: float,
    settings: Settings,
    cost: Optional[CostModel] = None,
) -> Optional[Signal]:
    """Return the best actionable Signal for a market, or None.

    We consider buying YES (when we think it's underpriced) and buying NO (when
    we think YES is overpriced), pick the larger edge, and require it to beat
    ``settings.min_edge`` after costs.
    """
    cost = cost or CostModel(taker_fee=settings.taker_fee, slippage=settings.slippage)
    book = market.book

    candidates: list[Signal] = []

    # --- Buy YES: pay the ask, win if event resolves YES ---
    if book.best_ask is not None:
        buy_price = cost.effective_buy_price(book.best_ask)
        edge = fair_prob - buy_price  # expected $ profit per share
        if 0 < buy_price < 1 and edge >= settings.min_edge:
            candidates.append(
                Signal(
                    market_id=market.id,
                    side=Side.YES,
                    fair_prob=fair_prob,
                    price=buy_price,
                    edge=edge,
                    kelly_fraction=kelly_fraction(fair_prob, buy_price),
                    limit_price=cost.worst_quote_for_edge(fair_prob, settings.min_edge),
                )
            )

    # --- Buy NO: NO ask = 1 - YES bid; win if event resolves NO ---
    if book.best_bid is not None:
        no_quote = 1.0 - book.best_bid
        buy_price = cost.effective_buy_price(no_quote)
        no_prob = 1.0 - fair_prob
        edge = no_prob - buy_price
        if 0 < buy_price < 1 and edge >= settings.min_edge:
            candidates.append(
                Signal(
                    market_id=market.id,
                    side=Side.NO,
                    fair_prob=fair_prob,
                    price=buy_price,
                    edge=edge,
                    kelly_fraction=kelly_fraction(no_prob, buy_price),
                    limit_price=cost.worst_quote_for_edge(no_prob, settings.min_edge),
                )
            )

    if not candidates:
        return None
    return max(candidates, key=lambda s: s.edge)
