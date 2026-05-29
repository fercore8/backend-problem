"""Executor interface — the seam between simulation and real money.

Everything upstream (valuation, strategy, risk) is identical whether we are
back-testing, paper-trading or trading live; only the Executor changes.  That is
what lets us validate the exact same code path with fake money before risking
real money.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from ..models import Fill, Market, Order


class Executor(ABC):
    @abstractmethod
    def execute(self, order: Order, market: Market) -> Fill:
        ...
