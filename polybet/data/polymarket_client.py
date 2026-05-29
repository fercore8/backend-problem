"""Read-only Polymarket data client (Gamma + CLOB).

Pulls live markets and order books and maps them into our domain models so the
exact same engine that ran on synthetic data can run on the real thing.  Kept
read-only on purpose — fetching data risks nothing; only the LiveExecutor moves
money, and that lives behind its own guard.

Requires the optional ``requests`` dependency.  If it's not installed the import
still succeeds; instantiation raises a clear message so offline/backtest use is
never blocked.
"""

from __future__ import annotations

from typing import Optional

from ..models import Level, Market, OrderBook

try:  # optional dependency
    import requests  # type: ignore
except Exception:  # pragma: no cover
    requests = None  # type: ignore

GAMMA_URL = "https://gamma-api.polymarket.com"
CLOB_URL = "https://clob.polymarket.com"


class PolymarketClient:
    def __init__(self, timeout: float = 10.0):
        if requests is None:
            raise RuntimeError(
                "PolymarketClient needs the 'requests' package: pip install requests"
            )
        self.timeout = timeout
        self.session = requests.Session()

    def _get(self, url: str, **params):
        r = self.session.get(url, params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def fetch_order_book(self, token_id: str) -> Optional[OrderBook]:
        """Fetch the CLOB order book for a single outcome token."""
        try:
            data = self._get(f"{CLOB_URL}/book", token_id=token_id)
        except Exception:  # pragma: no cover - network/shape variance
            return None
        bids = [Level(float(b["price"]), float(b["size"])) for b in data.get("bids", [])]
        asks = [Level(float(a["price"]), float(a["size"])) for a in data.get("asks", [])]
        # CLOB returns bids ascending / asks descending in places; normalise.
        bids.sort(key=lambda lv: lv.price, reverse=True)
        asks.sort(key=lambda lv: lv.price)
        return OrderBook(bids=bids, asks=asks)

    def fetch_markets(self, limit: int = 50, active: bool = True) -> list[Market]:
        """Fetch active markets and attach live YES-token order books."""
        rows = self._get(
            f"{GAMMA_URL}/markets",
            limit=limit,
            active=str(active).lower(),
            closed="false",
        )
        markets: list[Market] = []
        for row in rows:
            token_id = _first_yes_token(row)
            if not token_id:
                continue
            book = self.fetch_order_book(token_id)
            if book is None or book.best_ask is None:
                continue
            markets.append(
                Market(
                    id=str(row.get("id")),
                    question=row.get("question", ""),
                    book=book,
                    end_date=row.get("endDate"),
                    liquidity_usd=float(row.get("liquidityNum") or 0.0),
                )
            )
        return markets


def _first_yes_token(row: dict) -> Optional[str]:
    """Extract the YES outcome's CLOB token id from a Gamma market row."""
    import json

    raw = row.get("clobTokenIds")
    if not raw:
        return None
    try:
        ids = json.loads(raw) if isinstance(raw, str) else raw
    except Exception:
        return None
    return str(ids[0]) if ids else None
