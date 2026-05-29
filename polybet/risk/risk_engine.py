"""The risk engine: a hard gate between a sized idea and an actual order.

Edge tells us *which way* to bet and Kelly tells us *how much we'd like to* bet.
The risk engine decides how much we are *allowed* to bet, enforcing caps that no
single signal can override:

    * per-market cap        — no one market can sink us
    * aggregate exposure    — keep dry powder, stay diversified
    * open-position count    — operational sanity
    * book participation    — don't take so much we move the price against us
    * drawdown kill switch  — stop trading after a bad run, reassess the model

Sizing requests are *reduced* to fit caps where possible, and rejected outright
when a hard limit (drawdown, position count) is hit.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings
from ..models import Market, Signal
from ..portfolio import Portfolio


@dataclass
class RiskDecision:
    approved: bool
    shares: float
    notional: float
    reason: str = "ok"


class RiskEngine:
    def __init__(self, settings: Settings):
        self.s = settings

    def evaluate(
        self,
        signal: Signal,
        market: Market,
        portfolio: Portfolio,
        mark_prices: dict[str, float] | None = None,
    ) -> RiskDecision:
        s = self.s

        # --- hard stop: drawdown kill switch ---
        if portfolio.drawdown(mark_prices) >= s.max_drawdown:
            return RiskDecision(False, 0.0, 0.0, "drawdown kill-switch engaged")

        # --- hard stop: too many open positions (new markets only) ---
        is_new = signal.market_id not in portfolio.positions
        if is_new and len(portfolio.positions) >= s.max_open_positions:
            return RiskDecision(False, 0.0, 0.0, "max open positions reached")

        equity = portfolio.equity(mark_prices)
        if equity <= 0:
            return RiskDecision(False, 0.0, 0.0, "no equity")

        # --- desired notional from fractional Kelly ---
        desired = signal.kelly_fraction * s.kelly_fraction * equity

        # --- cap: per-market fraction of bankroll ---
        per_market_cap = s.max_position_fraction * equity
        desired = min(desired, per_market_cap)

        # --- cap: aggregate exposure ---
        room = s.max_total_exposure * equity - portfolio.open_exposure()
        if room <= 0:
            return RiskDecision(False, 0.0, 0.0, "aggregate exposure cap reached")
        desired = min(desired, room)

        # --- cap: book participation (don't eat more than X% of resting depth) ---
        side_levels = "asks" if signal.side.value == "YES" else "bids"
        book_shares = market.book.depth(side_levels)
        max_shares_by_book = s.max_book_participation * book_shares
        max_notional_by_book = max_shares_by_book * signal.price

        notional = min(desired, max_notional_by_book)
        if notional < signal.price or notional <= 0:  # can't afford even ~1 share
            return RiskDecision(False, 0.0, 0.0, "sized below one share after caps")

        shares = notional / signal.price
        return RiskDecision(True, shares, notional, "ok")
