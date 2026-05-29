# polybet

A wise, modular base for placing bets on **Polymarket**.

The thesis in one sentence: *make money not by betting a lot, but by betting only
when your probability estimate beats the market's, sizing so variance can't kill
you, and letting a small edge compound.*

This repo implements the full harvesting pipeline — **edge detection → Kelly
sizing → a hard risk engine → execution → accounting → calibration metrics** —
with a synthetic data generator so the whole thing runs and is tested **offline,
zero install**. Real Polymarket data and on-chain execution live behind optional,
guarded paths.

> 📐 Strategy & roadmap: [`docs/PLAN.md`](docs/PLAN.md)
> 🏗️ Architecture: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)

## Why this is "simple yet effective"

- **Pure standard-library core** — runs anywhere; no numpy/pandas/requests to test the brain.
- **One engine spine** for backtest, paper, and live — what you validate is what you trade.
- **Every dial in one `Settings`** — tunable and backtest-sweepable.
- **The thesis is a test** — the suite fails if the edge ever becomes illusory.

## Quickstart

```bash
# No dependencies needed for the core demo.
python -m polybet backtest                 # edge run, averaged over 20 seeds
python -m polybet backtest --no-edge       # control: estimate == market price
python -m polybet paper --db audit.db      # paper-trade a simulated live feed + persist
python -m polybet paper --live             # paper-trade real Polymarket data (read-only)
python -m pytest -q                        # 40 tests, all pure-stdlib
```

The `paper` loop is the Phase-2 heartbeat: it polls markets on a cadence, bets,
settles, and — crucially — **scores our forecasts against the market consensus
every run.** The `beats baseline ✅` verdict (model Brier < market Brier) is the
gate to ever risking real money.

`--no-edge` is the honesty check: when our estimate *is* the market price, the
edge gate finds nothing to bet (0 trades, exactly 0% ROI). When we feed in a
better-informed signal, the bankroll grows in expectation — proving the profit
comes from the signal, not the machinery.

Example (offline synthetic data, default settings):

```
                 with edge          no-edge control
  median ROI     ~+8%               +0.0%
  profitable     13/20 seeds        0/20 (no bets)
  Brier          beats baseline     —
```

We aggregate over many seeds on purpose: any single betting sequence is
dominated by variance (the drawdown kill-switch can legitimately end an unlucky
run early). The *expected* behaviour is what matters, and it is positive.

> Numbers from synthetic data illustrate the mechanics — they are **not** a
> forecast of real returns. The point of Phase 1 is to prove the pipeline works
> before any real capital. See the roadmap.

## How it works (30-second tour)

1. **Valuation** (`valuation/`) — estimate `P(YES)` for each market. Start from
   the market price and move away only as far as your signal + confidence justify
   (`ShrinkageEnsemble`).
2. **Edge gate** (`strategy/edge.py`) — bet YES if `q > price`, NO if `q < price`,
   only when the edge clears spread + slippage + fees.
3. **Sizing** (`strategy/kelly.py`) — fractional Kelly: `f* = (q − p)/(1 − p)`,
   times a safety multiplier (default ¼).
4. **Risk** (`risk/`) — per-market, aggregate, and book-participation caps + a
   drawdown kill switch. No signal can override it.
5. **Execution** (`execution/`) — paper fills walk the real book (honest
   slippage); live trading is a deliberately guarded stub.
6. **Metrics** (`metrics.py`) — Brier, log loss, calibration, ROI, drawdown,
   Sharpe. Calibration is the gate to risking real money.

## Going live (later, gated)

```bash
pip install -e ".[live]"     # adds requests + py-clob-client
```

Live execution refuses to run unless `POLYBET_ENABLE_LIVE=true` *and* a signer is
wired. Complete the **go-live checklist** in `docs/PLAN.md` first.

## Status & honest disclaimer

Phase 1 (research & backtest harness) is scaffolded and green. There is no
guaranteed-profit machine — we make money only insofar as our probabilities are
better calibrated than the market's, net of costs. Prove the edge on paper before
risking a cent, and confirm Polymarket is **legal in your jurisdiction**.

---

<details>
<summary>Original repository challenge (this branch repurposes the repo)</summary>

This repository started as a generic backend coding challenge. This branch
(`claude/polymarket-betting-app-KX5RJ`) repurposes it into the Polymarket betting
base described above. The original challenge text remains in git history.

</details>
