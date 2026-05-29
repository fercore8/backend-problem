"""Operational health: rolling calibration, drift, drawdown, and alerts.

The philosophy mirrors the rest of the system — *survive first*. These checks
exist to catch a decaying edge or a runaway drawdown **before** they cost real
money, and to make the kill-switch state visible at a glance.

Everything is computed from the persisted settlement series (pnl + forecast +
consensus + outcome, time-ordered), so the same code monitors a live run, a
finished paper run, or a historical DB. Pure stdlib.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum

from ..config import Settings
from ..metrics import brier_score, max_drawdown


class AlertLevel(IntEnum):
    """Ordered so we can take the max severity across alerts."""

    OK = 0
    INFO = 1
    WARN = 2
    CRITICAL = 3

    @property
    def label(self) -> str:
        return {0: "OK", 1: "INFO", 2: "WARN", 3: "CRITICAL"}[int(self)]


@dataclass
class Alert:
    level: AlertLevel
    code: str
    message: str


@dataclass
class Thresholds:
    """Tunable trip-wires for the monitoring layer (separate from trading config).

    Defaults are deliberately conservative: we'd rather a human glance at a
    healthy system than miss a real problem.
    """

    # Minimum resolved markets before calibration verdicts are trustworthy.
    min_sample: int = 30
    # Window (most-recent N settlements) for the "lately" calibration read.
    rolling_window: int = 100
    # Edge is "decaying" if recent Brier is worse than the market's by this much.
    drift_brier_margin: float = 0.0
    # Drawdown alerting, as a *fraction of the kill-switch* (Settings.max_drawdown).
    drawdown_warn_ratio: float = 0.5   # half-way to the kill-switch -> WARN
    drawdown_crit_ratio: float = 0.9   # almost at the kill-switch -> CRITICAL


@dataclass
class HealthReport:
    n_resolved: int = 0
    n_bets: int = 0

    # P&L / equity
    start_equity: float = 0.0
    equity: float = 0.0
    realized_pnl: float = 0.0
    drawdown: float = 0.0          # current fractional drawdown from peak
    max_drawdown: float = 0.0      # worst over the whole run
    kill_switch: float = 0.20      # the configured hard stop, for context
    kill_switch_engaged: bool = False

    # Calibration: model vs the consensus baseline it must beat
    brier_model_all: float = float("nan")
    brier_market_all: float = float("nan")
    brier_model_recent: float = float("nan")
    brier_market_recent: float = float("nan")

    alerts: list[Alert] = field(default_factory=list)
    equity_curve: list[float] = field(default_factory=list)

    @property
    def beats_baseline_all(self) -> bool:
        if self.brier_market_all != self.brier_market_all:  # NaN
            return False
        return self.brier_model_all < self.brier_market_all

    @property
    def beats_baseline_recent(self) -> bool:
        if self.brier_market_recent != self.brier_market_recent:  # NaN
            return False
        return self.brier_model_recent < self.brier_market_recent

    @property
    def status(self) -> AlertLevel:
        """Worst alert level present (OK if none)."""
        return max((a.level for a in self.alerts), default=AlertLevel.OK)


def compute_health(
    settlement_series: list[tuple[float, float | None, float | None, int]],
    settings: Settings,
    n_bets: int = 0,
    thresholds: Thresholds | None = None,
) -> HealthReport:
    """Build a HealthReport from the time-ordered settlement series.

    Each row is ``(pnl, fair_prob, consensus, outcome)``. We reconstruct the
    equity curve from cumulative realized P&L, score calibration overall and on
    the most-recent window, and emit alerts for low sample size, decaying edge,
    and proximity to the drawdown kill-switch.
    """
    t = thresholds or Thresholds()
    start = settings.bankroll

    report = HealthReport(
        n_resolved=len(settlement_series),
        n_bets=n_bets,
        start_equity=start,
        kill_switch=settings.max_drawdown,
    )

    if not settlement_series:
        report.equity = start
        report.equity_curve = [start]
        report.alerts.append(
            Alert(AlertLevel.INFO, "no_data", "No resolved markets yet — nothing to score.")
        )
        return report

    # --- Equity curve from cumulative realized P&L ---
    equity = start
    curve = [start]
    for pnl, _, _, _ in settlement_series:
        equity += pnl
        curve.append(equity)
    report.equity = equity
    report.realized_pnl = equity - start
    report.equity_curve = curve

    # --- Drawdown (current + worst) ---
    peak = max(curve)
    report.max_drawdown = max_drawdown(curve)
    report.drawdown = (peak - equity) / peak if peak > 0 else 0.0
    report.kill_switch_engaged = report.drawdown >= settings.max_drawdown

    # --- Calibration, all-time and rolling ---
    preds = [p for _, p, _, _ in settlement_series if p is not None]
    pred_outs = [o for _, p, _, o in settlement_series if p is not None]
    cons = [c for _, _, c, _ in settlement_series if c is not None]
    cons_outs = [o for _, _, c, o in settlement_series if c is not None]

    report.brier_model_all = brier_score(preds, pred_outs)
    report.brier_market_all = brier_score(cons, cons_outs)

    w = t.rolling_window
    report.brier_model_recent = brier_score(preds[-w:], pred_outs[-w:])
    report.brier_market_recent = brier_score(cons[-w:], cons_outs[-w:])

    report.alerts = _build_alerts(report, settings, t)
    return report


def _build_alerts(report: HealthReport, settings: Settings, t: Thresholds) -> list[Alert]:
    alerts: list[Alert] = []

    # 1. Sample size — calibration verdicts are noise below this.
    if report.n_resolved < t.min_sample:
        alerts.append(
            Alert(
                AlertLevel.INFO,
                "low_sample",
                f"Only {report.n_resolved} resolved markets (< {t.min_sample}); "
                "calibration verdicts are not yet reliable.",
            )
        )

    # 2. Drawdown proximity to the hard kill-switch.
    ks = settings.max_drawdown
    if report.kill_switch_engaged:
        alerts.append(
            Alert(
                AlertLevel.CRITICAL,
                "kill_switch",
                f"Drawdown {report.drawdown:.1%} ≥ kill-switch {ks:.0%}: "
                "new trading is halted. Reassess the model before resuming.",
            )
        )
    elif report.drawdown >= ks * t.drawdown_crit_ratio:
        alerts.append(
            Alert(
                AlertLevel.CRITICAL,
                "drawdown_near_kill",
                f"Drawdown {report.drawdown:.1%} is within {t.drawdown_crit_ratio:.0%} "
                f"of the {ks:.0%} kill-switch.",
            )
        )
    elif report.drawdown >= ks * t.drawdown_warn_ratio:
        alerts.append(
            Alert(
                AlertLevel.WARN,
                "drawdown_elevated",
                f"Drawdown {report.drawdown:.1%} is over halfway to the {ks:.0%} kill-switch.",
            )
        )

    # 3. Edge decay — only meaningful once we have a reliable sample.
    if report.n_resolved >= t.min_sample:
        if not report.beats_baseline_all:
            alerts.append(
                Alert(
                    AlertLevel.CRITICAL,
                    "no_edge",
                    f"All-time Brier {report.brier_model_all:.4f} does not beat market "
                    f"{report.brier_market_all:.4f}: no demonstrated edge. Do not risk capital.",
                )
            )
        elif not report.beats_baseline_recent:
            # We beat the market overall but not lately -> the edge may be decaying.
            margin = report.brier_model_recent - report.brier_market_recent
            if margin > t.drift_brier_margin:
                alerts.append(
                    Alert(
                        AlertLevel.WARN,
                        "edge_decay",
                        f"Recent Brier {report.brier_model_recent:.4f} trails market "
                        f"{report.brier_market_recent:.4f} even though all-time still leads: "
                        "edge may be decaying — investigate the signal.",
                    )
                )

    if not alerts:
        alerts.append(Alert(AlertLevel.OK, "healthy", "All checks passing."))
    return alerts
