"""Concrete fair-value models and the ensemble that combines them.

The philosophy is *humble edge*: start from the market price (which aggregates
everyone else's information) and only move away from it as far as our own signal
and our confidence in it justify.  This shrinkage is what keeps a noisy model
from confidently overbetting itself into ruin.
"""

from __future__ import annotations

from typing import Optional

from ..models import Market
from .base import FairValueModel


def _clamp(p: float, lo: float = 1e-4, hi: float = 1 - 1e-4) -> float:
    return max(lo, min(hi, p))


def devig(yes_odds: float, no_odds: float) -> float:
    """Remove the bookmaker's vig from a two-way market to recover P(YES).

    `yes_odds`/`no_odds` are decimal odds (e.g. 1.91).  The raw implied
    probabilities sum to >1 because of the vig; we normalise them.
    """
    if yes_odds <= 1 or no_odds <= 1:
        raise ValueError("decimal odds must be > 1")
    raw_yes = 1.0 / yes_odds
    raw_no = 1.0 / no_odds
    return _clamp(raw_yes / (raw_yes + raw_no))


class ConsensusModel(FairValueModel):
    """Baseline: trust the market.  Produces zero edge by construction.

    Useful as a control in backtests — if a strategy can't beat this, it has no
    edge.
    """

    name = "consensus"

    def estimate(self, market: Market) -> Optional[float]:
        return market.market_price


class ExternalOddsModel(FairValueModel):
    """A signal sourced from outside Polymarket.

    In practice this is where the real work goes: de-vigged sportsbook lines,
    other prediction markets (Kalshi/Manifold), polling models, or an LLM
    research pipeline.  Here it is a simple injectable map of
    {market_id: probability} so the rest of the system can be built and tested
    against it.
    """

    name = "external"

    def __init__(self, probabilities: dict[str, float]):
        self.probabilities = probabilities

    def estimate(self, market: Market) -> Optional[float]:
        p = self.probabilities.get(market.id)
        return _clamp(p) if p is not None else None


class ShrinkageEnsemble(FairValueModel):
    """Blend several models, then shrink the result toward the market price.

        signal   = weighted average of sub-model estimates
        fair     = mid + confidence * (signal - mid)

    `confidence` in [0, 1] is the single dial for how much we trust ourselves
    over the crowd.  At 0 we are pure consensus (no edge); at 1 we fully back our
    own number.  Conservative defaults keep us near the market until the model
    has earned trust via measured calibration.
    """

    name = "ensemble"

    def __init__(
        self,
        models: list[tuple[FairValueModel, float]],
        confidence: float = 0.5,
    ):
        if not models:
            raise ValueError("ensemble needs at least one model")
        self.models = models
        self.confidence = confidence

    def estimate(self, market: Market) -> Optional[float]:
        mid = market.market_price
        if mid is None:
            return None

        num = 0.0
        den = 0.0
        for model, weight in self.models:
            est = model.estimate(market)
            if est is not None:
                num += weight * est
                den += weight
        if den == 0:
            return None

        signal = num / den
        fair = mid + self.confidence * (signal - mid)
        return _clamp(fair)
