"""Central configuration.

Every knob that controls how aggressively we bet lives here so it can be tuned,
versioned and (later) swept in backtests.  Values are read from the environment
with safe, conservative defaults.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _f(name: str, default: float) -> float:
    return float(os.environ.get(name, default))


def _i(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


@dataclass
class Settings:
    # --- Bankroll -----------------------------------------------------------
    bankroll: float = _f("POLYBET_BANKROLL", 1_000.0)

    # --- Edge gate ----------------------------------------------------------
    # Minimum edge (expected $ profit per $1 share) required before we trade.
    # This must clear spread + slippage + gas, otherwise we are paying to lose.
    min_edge: float = _f("POLYBET_MIN_EDGE", 0.03)

    # --- Cost model ---------------------------------------------------------
    # Polymarket currently charges no maker/taker fee on most markets, but we
    # still pay the spread, slippage and (small) gas.  Modeled conservatively.
    taker_fee: float = _f("POLYBET_TAKER_FEE", 0.0)
    slippage: float = _f("POLYBET_SLIPPAGE", 0.005)
    gas_usd: float = _f("POLYBET_GAS_USD", 0.02)

    # --- Sizing -------------------------------------------------------------
    # Fraction of full Kelly to use.  Full Kelly is theoretically growth-optimal
    # but brutally volatile and unforgiving of model error; 1/4 Kelly is the
    # pragmatic default.
    kelly_fraction: float = _f("POLYBET_KELLY_FRACTION", 0.25)

    # --- Risk caps ----------------------------------------------------------
    max_position_fraction: float = _f("POLYBET_MAX_POSITION_FRACTION", 0.05)  # per market
    max_total_exposure: float = _f("POLYBET_MAX_TOTAL_EXPOSURE", 0.50)        # of bankroll
    max_open_positions: int = _i("POLYBET_MAX_OPEN_POSITIONS", 25)
    # Never take more than this fraction of the resting book (avoid moving price).
    max_book_participation: float = _f("POLYBET_MAX_BOOK_PARTICIPATION", 0.25)
    # Hard stop: halt all new trades if equity falls this far below its peak.
    max_drawdown: float = _f("POLYBET_MAX_DRAWDOWN", 0.20)

    # --- Valuation ----------------------------------------------------------
    # Shrink our raw signal toward the market price to stay humble.  fair =
    # mid + confidence * (signal - mid).  1.0 = fully trust our model, 0.0 = pure
    # market consensus (no edge).
    model_confidence: float = _f("POLYBET_MODEL_CONFIDENCE", 0.5)

    # --- Live trading guard -------------------------------------------------
    # Live execution refuses to run unless this is explicitly enabled.
    enable_live: bool = os.environ.get("POLYBET_ENABLE_LIVE", "false").lower() == "true"

    def __post_init__(self) -> None:
        if not 0 < self.kelly_fraction <= 1:
            raise ValueError("kelly_fraction must be in (0, 1]")
        if not 0 <= self.model_confidence <= 1:
            raise ValueError("model_confidence must be in [0, 1]")


SETTINGS = Settings()
