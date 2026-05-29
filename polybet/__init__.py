"""polybet — a wise, modular base for placing bets on Polymarket.

Design goals (see docs/PLAN.md):
  * Edge first.  We only bet when our fair-value estimate diverges from the
    market price by more than the cost of trading.
  * Survive first.  Fractional-Kelly sizing + a hard risk engine keep us alive
    through variance so the edge has time to compound.
  * Prove before you pay.  Backtest -> paper-trade -> live, gated on calibration.

The package is pure standard library so it runs anywhere with zero install.
Live data / on-chain execution live behind optional dependencies (requests).
"""

__version__ = "0.1.0"
