"""Signals: produce independent P(YES) estimates from outside Polymarket.

A SignalSource turns external information (sportsbook lines, Kalshi/Manifold
prices, polling models, an LLM research pipeline) into a
``{market_id: probability}`` map that feeds ``ExternalOddsModel``.  This package
is where real, durable edge is manufactured — everything else just harvests it.
"""

from .source import (
    MarketMatcher,
    MoneylineOddsSource,
    SignalSource,
    StaticProbabilitySource,
    TwoWayOdds,
)

__all__ = [
    "SignalSource",
    "StaticProbabilitySource",
    "MoneylineOddsSource",
    "TwoWayOdds",
    "MarketMatcher",
]
