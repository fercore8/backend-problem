"""SQLite persistence for an audit trail of bets, fills and settlements.

Even in paper mode, persisting every decision is what makes the system
*improvable*: you can later join recorded forecasts against realised outcomes to
re-score calibration, attribute P&L, and detect model drift.  Pure stdlib
(sqlite3), single file, safe to delete and recreate.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing

from ..models import Fill

_SCHEMA = """
CREATE TABLE IF NOT EXISTS bets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT DEFAULT CURRENT_TIMESTAMP,
    market_id   TEXT NOT NULL,
    side        TEXT NOT NULL,
    shares      REAL NOT NULL,
    avg_price   REAL NOT NULL,
    cost        REAL NOT NULL,
    fair_prob   REAL
);
CREATE TABLE IF NOT EXISTS settlements (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    ts            TEXT DEFAULT CURRENT_TIMESTAMP,
    market_id     TEXT NOT NULL,
    resolved_yes  INTEGER NOT NULL,
    pnl           REAL NOT NULL,
    fair_prob     REAL
);
"""


class Repository:
    def __init__(self, path: str = "polybet.db"):
        self.path = path
        with closing(self._conn()) as c:
            c.executescript(_SCHEMA)
            c.commit()

    def _conn(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def record_bet(self, fill: Fill, fair_prob: float | None) -> None:
        with closing(self._conn()) as c:
            c.execute(
                "INSERT INTO bets (market_id, side, shares, avg_price, cost, fair_prob)"
                " VALUES (?, ?, ?, ?, ?, ?)",
                (fill.market_id, fill.side.value, fill.shares, fill.avg_price, fill.cost, fair_prob),
            )
            c.commit()

    def record_settlement(
        self, market_id: str, resolved_yes: bool, pnl: float, fair_prob: float | None
    ) -> None:
        with closing(self._conn()) as c:
            c.execute(
                "INSERT INTO settlements (market_id, resolved_yes, pnl, fair_prob)"
                " VALUES (?, ?, ?, ?)",
                (market_id, 1 if resolved_yes else 0, pnl, fair_prob),
            )
            c.commit()

    def calibration_data(self) -> tuple[list[float], list[int]]:
        """Recorded (fair_prob, outcome) pairs for re-scoring calibration."""
        with closing(self._conn()) as c:
            rows = c.execute(
                "SELECT fair_prob, resolved_yes FROM settlements WHERE fair_prob IS NOT NULL"
            ).fetchall()
        preds = [r[0] for r in rows]
        outs = [int(r[1]) for r in rows]
        return preds, outs
