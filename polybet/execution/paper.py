"""Paper executor: realistic simulated fills by walking the order book.

A marketable buy consumes the relevant side level-by-level, so larger orders pay
progressively worse prices — the same slippage you'd feel live.  This makes
paper P&L honest: a strategy that only "works" because it assumes infinite
top-of-book liquidity will be exposed here, not after you've funded a wallet.
"""

from __future__ import annotations

from ..models import Fill, Market, Order, Side
from .base import Executor


class PaperExecutor(Executor):
    def execute(self, order: Order, market: Market) -> Fill:
        book = market.book
        # Buying YES consumes asks; buying NO consumes the YES bids (selling YES).
        if order.side == Side.YES:
            levels = book.asks
            def unit_price(level_price: float) -> float:
                return level_price
            def acceptable(level_price: float) -> bool:
                return level_price <= order.limit_price
        else:
            levels = book.bids
            def unit_price(level_price: float) -> float:
                return 1.0 - level_price  # NO price
            def acceptable(level_price: float) -> bool:
                return (1.0 - level_price) <= order.limit_price

        remaining = order.shares
        filled = 0.0
        spent = 0.0
        for lv in levels:
            if remaining <= 0 or not acceptable(lv.price):
                break
            take = min(remaining, lv.size)
            price = unit_price(lv.price)
            filled += take
            spent += take * price
            remaining -= take

        avg = spent / filled if filled > 0 else 0.0
        return Fill(
            market_id=order.market_id,
            side=order.side,
            shares=filled,
            avg_price=avg,
            cost=spent,
        )
