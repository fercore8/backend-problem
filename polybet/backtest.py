"""Backtest harness — prove the edge before paying for it.

Runs the full engine over a Scenario and produces a RunReport (P&L *and*
calibration).  Two modes:

  * sequential (default): markets are bet then resolved one after another, so
    capital recycles and compounds — a clean read on whether the edge grows the
    bankroll over a long series of one-shot bets.
  * snapshot: bet across all markets at once under the live exposure caps, then
    resolve.  Closer to "how much can I deploy right now", limited by risk caps.

Real production backtests should replay overlapping historical order-book
snapshots over time; this harness keeps the same interfaces so swapping the data
source is all that changes.
"""

from __future__ import annotations

from .config import Settings
from .data.sample import Scenario
from .engine import TradingEngine
from .execution.paper import PaperExecutor
from .metrics import RunReport, brier_score, log_loss, max_drawdown, roi, sharpe
from .portfolio import Portfolio
from .valuation.base import FairValueModel


def run_backtest(
    settings: Settings,
    scenario: Scenario,
    model: FairValueModel,
    sequential: bool = True,
) -> tuple[RunReport, TradingEngine]:
    portfolio = Portfolio(cash=settings.bankroll)
    engine = TradingEngine(settings, model, PaperExecutor(), portfolio)

    if sequential:
        for market in scenario.markets:
            engine.step([market])
            engine.settle(market.id, scenario.outcomes[market.id])
    else:
        engine.step(scenario.markets)
        for market in scenario.markets:
            engine.settle(market.id, scenario.outcomes[market.id])

    end_equity = portfolio.equity()
    st = engine.state
    report = RunReport(
        start_equity=settings.bankroll,
        end_equity=end_equity,
        n_bets=st.n_bets,
        n_resolved=len(st.resolved_outcomes),
        brier=brier_score(st.resolved_predictions, st.resolved_outcomes),
        logloss=log_loss(st.resolved_predictions, st.resolved_outcomes),
        roi=roi(settings.bankroll, end_equity),
        max_drawdown=max_drawdown(portfolio.equity_curve),
        sharpe=sharpe(portfolio.equity_curve),
    )
    return report, engine
