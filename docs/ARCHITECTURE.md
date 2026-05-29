# Architecture

The system is a linear pipeline with a single orchestration spine. The same
spine runs backtest, paper, and live; only the injected `Executor` changes.

```
                         ┌─────────────────────────────────────────┐
                         │              TradingEngine               │
                         │              (engine.py)                 │
   data source  ───────► │  for each live market:                  │
   (sample.py /          │    1. model.estimate(market)  → fair q  │
    PolymarketClient)    │    2. build_signal(...)        → edge    │ ──► PaperExecutor
                         │    3. risk.evaluate(...)       → size    │     or LiveExecutor
                         │    4. executor.execute(order)  → fill    │ ◄──  (execution/)
                         │    5. portfolio.apply_fill(...)          │
                         │  on resolution: portfolio.settle(...)    │ ──► Portfolio
                         └─────────────────────────────────────────┘     (portfolio.py)
                                                                            │
                                                                            ▼
                                                                   metrics.py / Repository
```

## Layers

| Layer | Module | Responsibility |
|-------|--------|----------------|
| Domain | `models.py` | `Market`, `OrderBook`, `Signal`, `Order`, `Fill`, `Position`, `Side` |
| Config | `config.py` | One `Settings` dataclass; every risk/sizing/cost dial, env-overridable |
| Data | `data/sample.py` | Synthetic markets with known ground truth (+ no-edge control) |
| Data | `data/polymarket_client.py` | Read-only Gamma + CLOB client (optional `requests`) |
| Data | `data/repository.py` | SQLite audit trail of bets/settlements; calibration replay |
| Valuation | `valuation/` | `FairValueModel` interface; consensus, external-odds, shrinkage ensemble; `devig` |
| Strategy | `strategy/edge.py` | Cost-aware edge gate, picks YES/NO side |
| Strategy | `strategy/kelly.py` | Fractional-Kelly sizing |
| Strategy | `strategy/arbitrage.py` | Dutch-book detection across mutually-exclusive groups |
| Risk | `risk/risk_engine.py` | Position/exposure/participation caps + drawdown kill switch |
| Execution | `execution/paper.py` | Simulated fills by walking the book (honest slippage) |
| Execution | `execution/live.py` | Guarded stub for real CLOB trading |
| Accounting | `portfolio.py` | Cash, positions, P&L, peak-tracking equity curve |
| Analytics | `metrics.py` | Brier, log loss, calibration bins, ROI, drawdown, Sharpe |
| Orchestration | `engine.py` | The spine; mode-agnostic |
| Harness | `backtest.py`, `cli.py` | Run it |

## Key design decisions

- **Everything in YES terms.** A NO bet is modeled as buying at `1 − bid`, so the
  whole system reasons about a single probability `P(YES)`. Less surface area,
  fewer sign-error bugs.
- **Executor is the only seam between fake and real money.** Valuation →
  strategy → risk are byte-for-byte identical across modes. What you validate is
  what you trade.
- **Pure-stdlib core.** No numpy/pandas/requests needed to run or test the brain.
  Networked/heavy deps live only on the live path (`pip install .[live]`).
- **Humble by default.** `model_confidence` shrinks signals toward the market,
  and fractional Kelly shrinks bet size. Both default conservative; you turn
  them up only as calibration earns it.

## Extending it

- **New signal?** Implement `FairValueModel.estimate(market) -> float|None` and
  add it to the `ShrinkageEnsemble` with a weight.
- **Go live?** Implement `LiveExecutor.execute` against `py-clob-client`, then
  inject it into `TradingEngine` instead of `PaperExecutor`. Nothing else
  changes.
- **Real backtest data?** Feed historical order-book snapshots into the same
  `engine.step()` loop; replace `data/sample.py` as the source.
