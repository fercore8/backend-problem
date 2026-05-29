"""Performance & calibration metrics.

Two questions decide whether this is a money machine or a money furnace:

  1. Are our probabilities *calibrated*?  (Brier score, log loss.)  If we say
     70% and those events happen ~70% of the time, we have genuine edge.  This is
     the gate that must be passed in backtest/paper before any live capital.
  2. Did the bankroll actually grow, risk-adjusted?  (ROI, max drawdown, Sharpe.)

Pure stdlib — no numpy required.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def brier_score(predictions: list[float], outcomes: list[int]) -> float:
    """Mean squared error of probabilistic forecasts. Lower is better (0..1)."""
    if not predictions:
        return float("nan")
    return sum((p - o) ** 2 for p, o in zip(predictions, outcomes)) / len(predictions)


def log_loss(predictions: list[float], outcomes: list[int], eps: float = 1e-9) -> float:
    """Negative log-likelihood. Punishes confident wrong calls hard."""
    if not predictions:
        return float("nan")
    total = 0.0
    for p, o in zip(predictions, outcomes):
        p = min(1 - eps, max(eps, p))
        total += -(o * math.log(p) + (1 - o) * math.log(1 - p))
    return total / len(predictions)


@dataclass
class CalibrationBin:
    lo: float
    hi: float
    count: int
    avg_prediction: float
    observed_rate: float


def calibration_bins(
    predictions: list[float], outcomes: list[int], n_bins: int = 10
) -> list[CalibrationBin]:
    """Reliability-diagram data: predicted vs observed frequency per bucket."""
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(n_bins)]
    for p, o in zip(predictions, outcomes):
        idx = min(n_bins - 1, int(p * n_bins))
        buckets[idx].append((p, o))

    out: list[CalibrationBin] = []
    for i, b in enumerate(buckets):
        lo, hi = i / n_bins, (i + 1) / n_bins
        if not b:
            out.append(CalibrationBin(lo, hi, 0, float("nan"), float("nan")))
            continue
        avg_p = sum(p for p, _ in b) / len(b)
        rate = sum(o for _, o in b) / len(b)
        out.append(CalibrationBin(lo, hi, len(b), avg_p, rate))
    return out


def roi(start_equity: float, end_equity: float) -> float:
    if start_equity <= 0:
        return float("nan")
    return (end_equity - start_equity) / start_equity


def max_drawdown(equity_curve: list[float]) -> float:
    """Largest peak-to-trough fractional decline over the curve (0..1)."""
    peak = float("-inf")
    mdd = 0.0
    for eq in equity_curve:
        peak = max(peak, eq)
        if peak > 0:
            mdd = max(mdd, (peak - eq) / peak)
    return mdd


def sharpe(equity_curve: list[float], periods_per_year: int = 252) -> float:
    """Annualised Sharpe of per-step returns. Needs >= 2 points."""
    if len(equity_curve) < 2:
        return float("nan")
    rets = []
    for a, b in zip(equity_curve, equity_curve[1:]):
        if a > 0:
            rets.append((b - a) / a)
    if len(rets) < 2:
        return float("nan")
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    sd = math.sqrt(var)
    if sd == 0:
        return float("nan")
    return (mean / sd) * math.sqrt(periods_per_year)


@dataclass
class RunReport:
    start_equity: float
    end_equity: float
    n_bets: int
    n_resolved: int
    brier: float
    logloss: float
    roi: float
    max_drawdown: float
    sharpe: float

    def render(self) -> str:
        return (
            "─── polybet run report ───\n"
            f"  bets placed     : {self.n_bets}\n"
            f"  markets resolved: {self.n_resolved}\n"
            f"  start equity    : ${self.start_equity:,.2f}\n"
            f"  end equity      : ${self.end_equity:,.2f}\n"
            f"  ROI             : {self.roi:+.2%}\n"
            f"  max drawdown    : {self.max_drawdown:.2%}\n"
            f"  Sharpe (ann.)   : {self.sharpe:.2f}\n"
            f"  Brier score     : {self.brier:.4f}  (lower is better)\n"
            f"  log loss        : {self.logloss:.4f}\n"
            "──────────────────────────"
        )
