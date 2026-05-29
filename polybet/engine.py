"""The orchestration loop: ingest -> value -> decide -> risk -> execute -> record.

This is the spine that every mode (backtest, paper, live) shares.  Keeping it in
one place means the logic that makes money is identical regardless of whether the
fills are simulated or real — only the Executor injected at construction differs.

The engine also records, for every market it bets, *both* our model's forecast
and the market consensus at decision time.  At settlement we score both against
the realised outcome, which is the core Phase-2 question: **are we actually
better calibrated than the crowd?**  If our Brier doesn't beat consensus, we have
no edge and no business risking real money.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .config import Settings
from .execution.base import Executor
from .models import Fill, Market, Order
from .portfolio import Portfolio
from .risk.risk_engine import RiskEngine
from .strategy.edge import CostModel, build_signal
from .valuation.base import FairValueModel


@dataclass
class PlacedBet:
    """A fill we executed this step, plus the forecast that justified it."""

    fill: Fill
    fair_prob: float
    consensus: float  # market mid at decision time (the baseline to beat)


@dataclass
class EngineState:
    n_bets: int = 0
    # Forecasts recorded when we open a position, scored at settle.
    open_predictions: dict[str, float] = field(default_factory=dict)
    open_consensus: dict[str, float] = field(default_factory=dict)
    # Filled in at settlement, aligned by index, for calibration scoring.
    resolved_predictions: list[float] = field(default_factory=list)
    resolved_consensus: list[float] = field(default_factory=list)
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

    def step(self, markets: list[Market]) -> list[PlacedBet]:
        """Evaluate a snapshot of live markets and place any approved bets.

        Returns the bets placed this step so callers (e.g. the paper runner) can
        persist them.  The portfolio is marked-to-market once at the end.
        """
        mark_prices = {
            m.id: m.market_price for m in markets if m.market_price is not None
        }

        placed: list[PlacedBet] = []
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
                limit_price=signal.limit_price,
            )
            fill = self.executor.execute(order, market)
            if fill.filled:
                self.portfolio.apply_fill(fill)
                self.state.n_bets += 1
                consensus = market.market_price if market.market_price is not None else fair
                self.state.open_predictions[market.id] = fair
                self.state.open_consensus[market.id] = consensus
                placed.append(PlacedBet(fill=fill, fair_prob=fair, consensus=consensus))

        self.portfolio.mark(mark_prices)
        return placed

    def settle(self, market_id: str, resolved_yes: bool) -> float:
        """Resolve a market: realise P&L and record forecasts for calibration."""
        pnl = self.portfolio.settle(market_id, resolved_yes)
        fair = self.state.open_predictions.pop(market_id, None)
        consensus = self.state.open_consensus.pop(market_id, None)
        if fair is not None:
            self.state.resolved_predictions.append(fair)
            self.state.resolved_consensus.append(
                consensus if consensus is not None else fair
            )
            self.state.resolved_outcomes.append(1 if resolved_yes else 0)
        return pnl
