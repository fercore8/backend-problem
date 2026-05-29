"""Dutch-book / mutual-exclusivity arbitrage.

When a single event is split across mutually-exclusive markets (e.g. one market
per election candidate, exactly one of which resolves YES), the YES prices must
sum to ~1.  If the *asks* sum to materially less than 1 we can buy every YES and
be guaranteed a $1 payout for less than $1 — a model-free, near-riskless edge
(subject to resolution risk and execution).

This is the closest thing to free money on Polymarket and is worth scanning for
continuously.
"""

from __future__ import annotations

from dataclasses import dataclass

from .edge import CostModel
from ..models import Market


@dataclass
class ArbOpportunity:
    group_id: str
    market_ids: list[str]
    total_cost: float       # sum of effective YES ask prices
    guaranteed_payout: float = 1.0

    @property
    def profit_per_set(self) -> float:
        return self.guaranteed_payout - self.total_cost


def find_dutch_book(
    markets: list[Market],
    cost: CostModel | None = None,
    min_profit: float = 0.01,
) -> list[ArbOpportunity]:
    """Find mutually-exclusive groups whose YES asks sum to < 1 - min_profit.

    Markets are grouped by ``group_id``; only complete-looking groups (>= 2
    legs, all with a live ask) are considered.
    """
    cost = cost or CostModel()
    groups: dict[str, list[Market]] = {}
    for m in markets:
        if m.group_id:
            groups.setdefault(m.group_id, []).append(m)

    opps: list[ArbOpportunity] = []
    for gid, legs in groups.items():
        if len(legs) < 2:
            continue
        if any(m.book.best_ask is None for m in legs):
            continue
        total = sum(cost.effective_buy_price(m.book.best_ask) for m in legs)
        if total <= 1.0 - min_profit:
            opps.append(
                ArbOpportunity(
                    group_id=gid,
                    market_ids=[m.id for m in legs],
                    total_cost=total,
                )
            )
    return sorted(opps, key=lambda o: o.profit_per_set, reverse=True)
