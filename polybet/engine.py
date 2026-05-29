"""The orchestration loop: ingest -> value -> decide -> risk -> execute -> record.

This is the spine that every mode (backtest, paper, live) shares.  Keeping it in
one place means the logic that makes money is identical regardless of whether the
fills are simulated or real — only the Executor injected at construction differs.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import Settings
from .execution.base import Executor
from .models import Market, Order
from .portfolio import Portfolio
from .risk.risk_engine import RiskEngine
from .strategy.edge import CostModel, build_signal
from .valuation.base import FairValueModel


@dataclass
class EngineState:
    n_bets: int = 0
    # (market_id, fair_prob) recorded when we take a position, scored at settle.
    open_predictions: dict[str, float] = field(default_factory=dict)
    resolved_predictions: list[float] = field(default_factory=list)
    resolved_outcomes: list[int] = field(default_factory=list)


class TradingEngine:
    def __init__(
        self,
        settings: Settings,
        model: FairValueModel,
        executor: Executor,
        portfolio: Portfolio,
    ):
        self.s = settings
        self.model = model
        self.executor = executor
        self.portfolio = portfolio
        self.risk = RiskEngine(settings)
        self.cost = CostModel(taker_fee=settings.taker_fee, slippage=settings.slippage)
        self.state = EngineState()

    def step(self, markets: list[Market]) -> None:
        """Evaluate a snapshot of live markets and place any approved bets."""
        mark_prices = {
            m.id: m.market_price for m in markets if m.market_price is not None
        }

        for market in markets:
            if market.resolved is not None:  # skip already-settled markets
                continue
            fair = self.model.estimate(market)
            if fair is None:
                continue

            signal = build_signal(market, fair, self.s, self.cost)
            if signal is None or not signal.is_actionable:
                continue

            decision = self.risk.evaluate(signal, market, self.portfolio, mark_prices)
            if not decision.approved:
                continue

            order = Order(
                market_id=signal.market_id,
                side=signal.side,
                shares=decision.shares,
                limit_price=signal.price,
            )
            fill = self.executor.execute(order, market)
            if fill.filled:
                self.portfolio.apply_fill(fill)
                self.state.n_bets += 1
                self.state.open_predictions[market.id] = fair

        self.portfolio.mark(mark_prices)

    def settle(self, market_id: str, resolved_yes: bool) -> float:
        """Resolve a market: realise P&L and record the forecast for calibration."""
        pnl = self.portfolio.settle(market_id, resolved_yes)
        fair = self.state.open_predictions.pop(market_id, None)
        if fair is not None:
            self.state.resolved_predictions.append(fair)
            self.state.resolved_outcomes.append(1 if resolved_yes else 0)
        return pnl
