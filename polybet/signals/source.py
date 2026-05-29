"""Signal sources and the matching layer.

Two real-world problems live here:

1. **De-vig.**  A sportsbook quoting a two-way market builds in a margin (the
   "vig"), so its raw implied probabilities sum to > 1.  Removing it recovers an
   unbiased probability that is *independent* of Polymarket — the raw material of
   cross-venue edge.

2. **Matching.**  The external venue and Polymarket name the same event
   differently ("Will the Lakers win?" vs "Lakers vs Celtics — LAL ML").  We need
   a deliberate map from external keys to Polymarket market ids.  Bad matches are
   a classic way to bet confidently on the wrong thing, so matching is explicit
   and auditable rather than magic.

Everything here is pure stdlib and offline-testable; a live source just fills the
same interfaces from the network.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Iterable, Optional

from ..models import Market
from ..valuation.models import devig


class SignalSource(ABC):
    """Produce P(YES) for some subset of the given markets.  Abstain by omission.

    Returning a partial dict is expected and fine: we only bet markets we have an
    independent read on.
    """

    name: str = "signal"

    @abstractmethod
    def probabilities(self, markets: Iterable[Market]) -> dict[str, float]:
        ...


class StaticProbabilitySource(SignalSource):
    """A fixed map of probabilities — handy for tests and manual overrides."""

    name = "static"

    def __init__(self, probabilities: dict[str, float]):
        self._probs = probabilities

    def probabilities(self, markets: Iterable[Market]) -> dict[str, float]:
        ids = {m.id for m in markets}
        return {mid: p for mid, p in self._probs.items() if mid in ids}


@dataclass
class TwoWayOdds:
    """Decimal odds for the two outcomes of an external two-way market."""

    yes: float
    no: float

    def fair_probability(self) -> float:
        """De-vigged P(YES)."""
        return devig(self.yes, self.no)


class MarketMatcher:
    """Maps external event keys to Polymarket market ids.

    Kept explicit on purpose: a wrong match silently bets the wrong side.  Build
    it from a reviewed mapping (manual, or a fuzzy matcher whose output a human
    signs off on) — never guess at trade time.
    """

    def __init__(self, external_to_market: dict[str, str]):
        self._map = dict(external_to_market)

    def market_id_for(self, external_key: str) -> Optional[str]:
        return self._map.get(external_key)

    def __len__(self) -> int:
        return len(self._map)


class MoneylineOddsSource(SignalSource):
    """Cross-venue signal: de-vig external two-way odds, then map onto markets.

    Feed it ``{external_key: TwoWayOdds}`` and a ``MarketMatcher``.  This is the
    first *real* edge source in the system: an independent, vig-free probability
    for each event we can match to a Polymarket market.
    """

    name = "moneyline-devig"

    def __init__(self, odds: dict[str, TwoWayOdds], matcher: MarketMatcher):
        self._odds = odds
        self._matcher = matcher

    def probabilities(self, markets: Iterable[Market]) -> dict[str, float]:
        ids = {m.id for m in markets}
        out: dict[str, float] = {}
        for external_key, odds in self._odds.items():
            market_id = self._matcher.market_id_for(external_key)
            if market_id is None or market_id not in ids:
                continue
            try:
                out[market_id] = odds.fair_probability()
            except ValueError:
                # Malformed odds (<= 1.0): skip rather than bet on garbage.
                continue
        return out


def combine_sources(
    sources: list[tuple[SignalSource, float]],
    markets: Iterable[Market],
) -> dict[str, float]:
    """Weighted-average several sources into one ``{market_id: probability}`` map.

    Markets covered by more than one source get a confidence-weighted blend;
    markets covered by none are simply absent (we abstain).
    """
    markets = list(markets)
    num: dict[str, float] = {}
    den: dict[str, float] = {}
    for source, weight in sources:
        for mid, p in source.probabilities(markets).items():
            num[mid] = num.get(mid, 0.0) + weight * p
            den[mid] = den.get(mid, 0.0) + weight
    return {mid: num[mid] / den[mid] for mid in num if den[mid] > 0}
