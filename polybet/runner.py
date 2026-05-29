"""Paper-trading runner — Phase 2's beating heart.

Polls a market source on an interval, runs the shared engine, persists every bet
and settlement, and continuously reports whether our forecasts are actually
beating the market consensus (the only thing that justifies risking real money).

The same loop runs on synthetic data (offline, deterministic, testable) or live
Polymarket data — only the injected ``MarketSource`` changes, mirroring how only
the ``Executor`` changes between paper and live.  What you validate here is what
you'll trade.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from .config import Settings
from .data.repository import Repository
from .data.sample import Scenario
from .engine import TradingEngine
from .execution.paper import PaperExecutor
from .metrics import brier_score, log_loss
from .models import Market
from .portfolio import Portfolio
from .valuation.base import FairValueModel


class MarketSource(ABC):
    """Supplies market snapshots and tells us which markets have resolved.

    ``poll`` returns the currently-live markets to evaluate.  ``drain_resolutions``
    returns ``{market_id: resolved_yes}`` for markets that settled since the last
    call (and clears them), so the runner can realise P&L and score forecasts.
    """

    @abstractmethod
    def poll(self) -> list[Market]:
        ...

    @abstractmethod
    def drain_resolutions(self) -> dict[str, bool]:
        ...

    def done(self) -> bool:
        """True when there is nothing left to do (lets finite sources end)."""
        return False


class SyntheticMarketSource(MarketSource):
    """Replays a Scenario as a time series: markets appear, then resolve.

    Deterministic and dependency-free, so the whole runner is unit-testable.  At
    each tick a batch of new markets becomes live; the previous batch resolves to
    its known ground truth.  This models the real cadence (you bet on open
    markets, they settle later) without any network.
    """

    def __init__(self, scenario: Scenario, batch_size: int = 25):
        self.scenario = scenario
        self.batch_size = batch_size
        self._cursor = 0
        self._live: list[Market] = []
        self._pending: dict[str, bool] = {}

    def poll(self) -> list[Market]:
        # Resolve the batch that was live, then bring the next batch online.
        for m in self._live:
            self._pending[m.id] = self.scenario.outcomes[m.id]
        start, end = self._cursor, self._cursor + self.batch_size
        self._live = self.scenario.markets[start:end]
        self._cursor = end
        return list(self._live)

    def drain_resolutions(self) -> dict[str, bool]:
        out = self._pending
        self._pending = {}
        return out

    def done(self) -> bool:
        return self._cursor >= len(self.scenario.markets) and not self._live


@dataclass
class PaperRunReport:
    ticks: int = 0
    n_bets: int = 0
    n_resolved: int = 0
    start_equity: float = 0.0
    end_equity: float = 0.0
    model_brier: float = float("nan")
    consensus_brier: float = float("nan")
    model_logloss: float = float("nan")
    consensus_logloss: float = float("nan")

    @property
    def roi(self) -> float:
        if self.start_equity <= 0:
            return float("nan")
        return (self.end_equity - self.start_equity) / self.start_equity

    @property
    def beats_baseline(self) -> bool:
        """The Phase-2 gate: are we better calibrated than the crowd?"""
        if self.consensus_brier != self.consensus_brier:  # NaN -> not enough data
            return False
        return self.model_brier < self.consensus_brier

    def render(self) -> str:
        verdict = "YES ✅" if self.beats_baseline else "not yet"
        return (
            "─── polybet paper run ───\n"
            f"  ticks           : {self.ticks}\n"
            f"  bets placed     : {self.n_bets}\n"
            f"  markets resolved: {self.n_resolved}\n"
            f"  start equity    : ${self.start_equity:,.2f}\n"
            f"  end equity      : ${self.end_equity:,.2f}\n"
            f"  ROI             : {self.roi:+.2%}\n"
            f"  Brier  (model)  : {self.model_brier:.4f}\n"
            f"  Brier  (market) : {self.consensus_brier:.4f}\n"
            f"  log loss(model) : {self.model_logloss:.4f}\n"
            f"  log loss(market): {self.consensus_logloss:.4f}\n"
            f"  beats baseline  : {verdict}\n"
            "─────────────────────────"
        )


class PaperTrader:
    """Drives the engine over a MarketSource, persisting and scoring as it goes."""

    def __init__(
        self,
        settings: Settings,
        model: FairValueModel,
        source: MarketSource,
        repository: Optional[Repository] = None,
    ):
        self.s = settings
        self.source = source
        self.repo = repository
        self.portfolio = Portfolio(cash=settings.bankroll)
        self.engine = TradingEngine(settings, model, PaperExecutor(), self.portfolio)
        self._ticks = 0

    def tick(self) -> None:
        """One poll cycle: settle what resolved, then evaluate live markets."""
        # 1. Settle anything that resolved since last poll (realise P&L + score).
        for market_id, resolved_yes in self.source.drain_resolutions().items():
            fair = self.engine.state.open_predictions.get(market_id)
            consensus = self.engine.state.open_consensus.get(market_id)
            pnl = self.engine.settle(market_id, resolved_yes)
            if self.repo is not None:
                self.repo.record_settlement(market_id, resolved_yes, pnl, fair, consensus)

        # 2. Evaluate the current snapshot and place any approved bets.
        markets = self.source.poll()
        placed = self.engine.step(markets)
        if self.repo is not None:
            for bet in placed:
                self.repo.record_bet(bet.fill, bet.fair_prob)

        self._ticks += 1

    def run(self, max_ticks: int = 10_000) -> PaperRunReport:
        """Run until the source is exhausted (or a safety cap), settling all open
        positions at the end so the calibration scoring is complete."""
        while not self.source.done() and self._ticks < max_ticks:
            self.tick()
        # Flush any final resolutions the last poll queued up.
        final = self.source.drain_resolutions()
        for market_id, resolved_yes in final.items():
            fair = self.engine.state.open_predictions.get(market_id)
            consensus = self.engine.state.open_consensus.get(market_id)
            pnl = self.engine.settle(market_id, resolved_yes)
            if self.repo is not None:
                self.repo.record_settlement(market_id, resolved_yes, pnl, fair, consensus)
        return self.report()

    def report(self) -> PaperRunReport:
        st = self.engine.state
        return PaperRunReport(
            ticks=self._ticks,
            n_bets=st.n_bets,
            n_resolved=len(st.resolved_outcomes),
            start_equity=self.s.bankroll,
            end_equity=self.portfolio.equity(),
            model_brier=brier_score(st.resolved_predictions, st.resolved_outcomes),
            consensus_brier=brier_score(st.resolved_consensus, st.resolved_outcomes),
            model_logloss=log_loss(st.resolved_predictions, st.resolved_outcomes),
            consensus_logloss=log_loss(st.resolved_consensus, st.resolved_outcomes),
        )
