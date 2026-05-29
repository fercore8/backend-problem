"""Live executor — a guarded stub for real on-chain Polymarket trading.

Intentionally not wired to send orders yet.  Going live is a deliberate,
checklist-gated step (see docs/PLAN.md "Go-live checklist"), not a flag someone
flips by accident.  Real implementation responsibilities:

    * Build & EIP-712 sign CLOB orders with the trading wallet's key.
    * Manage USDC allowances / approvals on Polygon for the exchange contract.
    * Submit via the official py-clob-client; handle GTC/FOK/GTD order types.
    * Reconcile fills from the WebSocket user channel back into the Portfolio.
    * Account for gas and resolution (UMA optimistic oracle) timing.

It refuses to run unless Settings.enable_live is True *and* a signer is wired,
so importing/instantiating it can never silently move money.
"""

from __future__ import annotations

from ..config import Settings
from ..execution.base import Executor
from ..models import Fill, Market, Order


class LiveExecutor(Executor):
    def __init__(self, settings: Settings, signer=None):
        if not settings.enable_live:
            raise RuntimeError(
                "Live trading disabled. Set POLYBET_ENABLE_LIVE=true and wire a "
                "signer only after passing the go-live checklist."
            )
        if signer is None:
            raise RuntimeError("LiveExecutor requires a configured CLOB signer.")
        self.settings = settings
        self.signer = signer

    def execute(self, order: Order, market: Market) -> Fill:  # pragma: no cover
        raise NotImplementedError(
            "Wire py-clob-client order submission here once the go-live "
            "checklist is complete."
        )
