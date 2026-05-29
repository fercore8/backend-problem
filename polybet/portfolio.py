"""Bankroll & position accounting.

Tracks cash, open positions, realised P&L and a peak-tracking equity curve.  The
equity curve is what the risk engine watches for drawdown, and what the metrics
module turns into ROI / Sharpe / max-drawdown after a run.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .models import Fill, Position, Side


@dataclass
class Portfolio:
    cash: float
    positions: dict[str, Position] = field(default_factory=dict)
    realized_pnl: float = 0.0
    equity_curve: list[float] = field(default_factory=list)
    _peak: float = field(default=0.0, init=False)

    def __post_init__(self) -> None:
        self._peak = self.cash
        self.equity_curve.append(self.cash)

    # --- mutations ----------------------------------------------------------
    def apply_fill(self, fill: Fill) -> None:
        """Apply a buy fill: cash decreases, a position is opened/averaged up.

        Positions are keyed by market id; we assume one side per market at a time
        (the strategy never simultaneously holds YES and NO in the same market).
        """
        if not fill.filled:
            return
        self.cash -= fill.cost
        existing = self.positions.get(fill.market_id)
        if existing is None or existing.side != fill.side:
            self.positions[fill.market_id] = Position(
                market_id=fill.market_id,
                side=fill.side,
                shares=fill.shares,
                avg_price=fill.avg_price,
            )
        else:
            total_shares = existing.shares + fill.shares
            existing.avg_price = (
                existing.cost_basis + fill.cost
            ) / total_shares
            existing.shares = total_shares

    def settle(self, market_id: str, resolved_yes: bool) -> float:
        """Resolve a position to its $1/$0 outcome and book realised P&L."""
        pos = self.positions.pop(market_id, None)
        if pos is None:
            return 0.0
        won = (pos.side == Side.YES and resolved_yes) or (
            pos.side == Side.NO and not resolved_yes
        )
        payout = pos.shares if won else 0.0
        self.cash += payout
        pnl = payout - pos.cost_basis
        self.realized_pnl += pnl
        return pnl

    # --- valuation ----------------------------------------------------------
    def open_exposure(self) -> float:
        """Cost basis tied up in open positions (capital at risk)."""
        return sum(p.cost_basis for p in self.positions.values())

    def equity(self, mark_prices: dict[str, float] | None = None) -> float:
        """Cash plus marked value of open positions.

        ``mark_prices`` maps market_id -> current P(YES).  Absent a mark we fall
        back to cost basis (conservative: assume no paper gain yet).
        """
        mark_prices = mark_prices or {}
        value = self.cash
        for pos in self.positions.values():
            p_yes = mark_prices.get(pos.market_id)
            if p_yes is None:
                value += pos.cost_basis
                continue
            unit = p_yes if pos.side == Side.YES else (1.0 - p_yes)
            value += pos.shares * unit
        return value

    def mark(self, mark_prices: dict[str, float] | None = None) -> float:
        """Snapshot equity onto the curve and update the peak. Returns equity."""
        eq = self.equity(mark_prices)
        self._peak = max(self._peak, eq)
        self.equity_curve.append(eq)
        return eq

    @property
    def peak_equity(self) -> float:
        return self._peak

    def drawdown(self, mark_prices: dict[str, float] | None = None) -> float:
        """Current fractional drawdown from peak equity (0..1)."""
        eq = self.equity(mark_prices)
        if self._peak <= 0:
            return 0.0
        return max(0.0, (self._peak - eq) / self._peak)
