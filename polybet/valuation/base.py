"""The valuation interface.

A FairValueModel maps a Market (plus any side information) to our best estimate
of P(YES).  This is the *only* source of edge in the system: if our estimates
are no better than the market's, we cannot win after costs.  Everything else
(sizing, risk, execution) is about converting a real edge into compounding
bankroll growth without blowing up.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from ..models import Market


class FairValueModel(ABC):
    """Estimate P(YES) for a market.  Return None to abstain."""

    name: str = "base"

    @abstractmethod
    def estimate(self, market: Market) -> Optional[float]:
        ...
