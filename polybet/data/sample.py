"""Synthetic market generator — lets the whole system run & be tested offline.

It encodes the *only* assumption under which a prediction-market bot can make
money: that our signal is better calibrated than the market price.  Each market
has a hidden ``true_prob``; the market mid is a noisy read of it, and our
external signal is a *less* noisy read.  Bet that informational edge through the
full pipeline and the bankroll should grow — if it doesn't, a bug or a too-timid
config is the reason, and you'll see it here before risking a cent.

Set ``signal_sigma == market_sigma`` to simulate *having no edge*: a correct
system should then roughly break even minus costs.  This is your control.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from ..models import Level, Market, OrderBook


def _clamp(x: float, lo: float = 0.02, hi: float = 0.98) -> float:
    return max(lo, min(hi, x))


def _make_book(mid: float, spread: float, depth_shares: float, levels: int = 5) -> OrderBook:
    half = spread / 2.0
    bids, asks = [], []
    for i in range(levels):
        bid_p = _clamp(mid - half - i * spread, 0.01, 0.99)
        ask_p = _clamp(mid + half + i * spread, 0.01, 0.99)
        size = depth_shares * (0.6 ** i)  # liquidity thins as you go deeper
        bids.append(Level(round(bid_p, 4), round(size, 2)))
        asks.append(Level(round(ask_p, 4), round(size, 2)))
    return OrderBook(bids=bids, asks=asks)


@dataclass
class Scenario:
    markets: list[Market]
    external_probs: dict[str, float]   # feed to ExternalOddsModel
    outcomes: dict[str, bool]          # ground truth for settlement
    true_probs: dict[str, float] = field(default_factory=dict)


def generate_scenario(
    n_markets: int = 200,
    seed: int = 7,
    market_sigma: float = 0.08,   # how noisy the market price is vs truth
    signal_sigma: float = 0.04,   # how noisy *our* signal is (smaller = real edge)
    spread: float = 0.02,
    depth_shares: float = 500.0,
) -> Scenario:
    """Generate independent binary markets with a known ground truth."""
    rng = random.Random(seed)
    markets: list[Market] = []
    external: dict[str, float] = {}
    outcomes: dict[str, bool] = {}
    truths: dict[str, float] = {}

    for i in range(n_markets):
        mid = i  # placeholder for type checkers; reassigned below
        true_p = rng.uniform(0.1, 0.9)
        mkt_mid = _clamp(true_p + rng.gauss(0, market_sigma))
        signal = _clamp(true_p + rng.gauss(0, signal_sigma))
        book = _make_book(mkt_mid, spread, depth_shares)

        mid = f"m{i:04d}"
        markets.append(
            Market(
                id=mid,
                question=f"Synthetic market #{i}: will event {i} happen?",
                book=book,
                liquidity_usd=depth_shares * mkt_mid * 2,
            )
        )
        external[mid] = signal
        outcomes[mid] = rng.random() < true_p
        truths[mid] = true_p

    return Scenario(markets=markets, external_probs=external, outcomes=outcomes, true_probs=truths)
