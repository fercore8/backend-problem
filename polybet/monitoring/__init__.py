"""Monitoring & ops: turn the audit trail into operational health signals.

A betting system that you can't *watch* is a system that will quietly drift into
losing money. This package answers the questions an operator actually has:

  * Are we still better calibrated than the market, *lately* (not just overall)?
  * Has the model drifted — was our early edge real but now decaying?
  * Are we near the drawdown kill-switch?
  * Is anything off enough to warrant a human stepping in?

It reads the persisted audit trail (no live state needed), so it works on a
running system, a finished paper run, or a historical DB equally well.
"""

from .health import (
    Alert,
    AlertLevel,
    HealthReport,
    Thresholds,
    compute_health,
)

__all__ = [
    "Alert",
    "AlertLevel",
    "HealthReport",
    "Thresholds",
    "compute_health",
]
