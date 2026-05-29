"""Kelly position sizing for binary $1-settling shares.

For a share bought at price ``p`` that pays $1 with our estimated win
probability ``q`` (and 0 otherwise), the bet wins ``(1 - p)`` and loses ``p``.
The growth-optimal fraction of bankroll to stake is::

    f* = (q - p) / (1 - p)

Derivation: net decimal odds ``b = (1 - p) / p``; Kelly ``f* = q - (1 - q)/b``
``= q - (1 - q) * p / (1 - p) = (q - p) / (1 - p)``.

Full Kelly maximises long-run log-growth but is violently volatile and assumes
your probabilities are exactly right.  We always apply a fractional multiplier
(see Settings.kelly_fraction) and clamp to non-negative.
"""

from __future__ import annotations


def kelly_fraction(win_prob: float, price: float) -> float:
    """Full-Kelly bankroll fraction for buying a $1 share at ``price``.

    Returns 0 when there is no positive edge or the price is degenerate.
    Works for either side: for NO, pass win_prob = P(NO) and price = NO price.
    """
    if not 0 < price < 1:
        return 0.0
    f = (win_prob - price) / (1.0 - price)
    return max(0.0, f)
