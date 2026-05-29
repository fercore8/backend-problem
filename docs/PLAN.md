# polybet — The Plan

A staged plan for turning a Polymarket account into a disciplined,
edge-driven betting operation. The guiding principle is boring on purpose:

> **You do not make money by betting a lot. You make money by betting only when
> your probability estimate is better than the market's, sizing so variance
> can't kill you, and letting a small edge compound.**

Everything in this repo serves that sentence.

---

## 0. Honest expectations (read this first)

There is no "money-making machine" that prints risk-free returns. Polymarket is
a competitive market; the price already reflects a lot of smart money. We make
money **only** to the extent that, on average, our probability estimates are
*more accurate* than the market price, by *more than* the cost of trading.

So this project is really two problems:

1. **Generate edge** — produce better-calibrated probabilities than the market.
   This is the hard, never-finished part. The machinery here cannot create edge;
   it can only *harvest* it once you have it.
2. **Harvest edge without blowing up** — sizing, risk limits, execution,
   accounting. This is largely a solved engineering problem, and it is what this
   codebase implements end-to-end.

The plan below is sequenced so we **prove the edge with fake money before risking
real money.** If the edge isn't real, the most important feature of this system
is that it tells you so cheaply.

---

## 1. How the money is actually made

For a binary market, a YES share costs `p` and pays `$1` if the event happens.
`p` is the market's implied probability. Suppose our model says the true
probability is `q`.

- If `q > p` by more than costs → YES is underpriced → **buy YES**.
- If `q < p` by more than costs → YES is overpriced → **buy NO**.

Expected profit per share (the **edge**) is `q - p_effective`, where
`p_effective` folds in the spread we cross, slippage, fees and gas. We only act
when `edge ≥ min_edge`. (`polybet/strategy/edge.py`)

Three repeatable sources of edge, in increasing difficulty:

| # | Source | Why it exists | Status in repo |
|---|--------|---------------|----------------|
| 1 | **Dutch-book / mutual-exclusivity arb** — YES prices of an exhaustive set should sum to 1; when asks sum to < 1 you buy the whole set for a guaranteed payout. | Liquidity is fragmented across legs; bots are imperfect. | Implemented: `strategy/arbitrage.py` |
| 2 | **Cross-venue de-vig** — Kalshi, sportsbooks, Manifold price the same event; remove their vig and you get an independent probability. | Audiences and liquidity differ across venues. | Hook ready: `valuation/models.py::devig` + `ExternalOddsModel` |
| 3 | **Fundamental modeling** — polls, base rates, news, LLM research → your own forecast. | Hard, but the deepest and most durable edge. | Pluggable: implement a `FairValueModel` |

The `ShrinkageEnsemble` blends these and **shrinks toward the market price** by a
confidence factor, so a noisy model stays humble until it has earned trust.

---

## 2. The math we rely on

**Edge (per share).** `edge = q − p_effective`, where
`p_effective = quoted · (1 + fee) + slippage`.

**Kelly sizing.** For a `$1` share bought at price `p` with win probability `q`,
the growth-optimal bankroll fraction is

```
f* = (q − p) / (1 − p)
```

We always stake a **fraction** of `f*` (default ¼-Kelly). Full Kelly maximizes
long-run growth but is wildly volatile and assumes your probabilities are exactly
right — they never are. Fractional Kelly trades a little growth for a lot of
survival. (`polybet/strategy/kelly.py`)

**De-vig.** Given two-way decimal odds, normalize the raw implied probabilities
so they sum to 1, recovering an unbiased `P(YES)`. (`valuation/models.py::devig`)

**Calibration.** The whole thesis lives or dies on whether our probabilities are
*calibrated*: when we say 70%, does it happen ~70% of the time? We score this
continuously with **Brier score**, **log loss**, and reliability bins.
(`polybet/metrics.py`)

---

## 3. Staying alive: the risk engine

Edge tells us *which way*; Kelly tells us *how much we'd like to*; the risk
engine decides how much we are *allowed* to. No single signal can override it.
(`polybet/risk/risk_engine.py`)

- **Per-market cap** (default 5% of bankroll) — no one market can sink us.
- **Aggregate exposure cap** (default 50%) — keep dry powder, stay diversified.
- **Open-position cap** — operational sanity.
- **Book-participation cap** (default 25% of resting depth) — don't move the
  price against ourselves; respects real liquidity.
- **Drawdown kill switch** (default −20% from peak) — stop and reassess the model
  after a bad run instead of doubling down.

Sizes are *reduced* to fit soft caps and *rejected* on hard limits.

---

## 4. Architecture at a glance

```
data → valuation → strategy → risk → execution → portfolio → metrics
 │         │          │         │        │            │          │
 Gamma/   fair      edge gate  caps &  paper or     cash &     Brier,
 CLOB or  P(YES)    + Kelly    kill-   live fills    P&L,       ROI,
 synthetic          sizing     switch  (same API)    equity     drawdown
```

The same engine spine (`engine.py`) runs **backtest, paper, and live** — only
the injected `Executor` changes. That is what lets us validate the *exact* code
path with fake money first. Full detail in [ARCHITECTURE.md](ARCHITECTURE.md).

---

## 5. Roadmap

### Phase 1 — Research & backtest  ✅ (scaffolded in this repo)
- Domain models, edge gate, Kelly, risk engine, paper executor, metrics.
- Synthetic scenario generator with a *known* ground truth, plus a **no-edge
  control** so we can confirm profit comes from signal, not from a bug.
- Test suite encoding the thesis: *edge run must beat the no-edge control.*
- **Exit criteria:** `python -m polybet backtest` shows positive ROI with the
  signal and ~break-even with the control; tests green.

### Phase 2 — Paper-trading loop & calibration scoring  ✅ (built in this repo)
- **Paper runner** (`runner.py`): polls a `MarketSource` on a cadence, runs the
  shared engine, settles resolved markets, and **scores our forecasts against the
  market consensus every run** — the `beats baseline` verdict is the gate to real
  money. Same loop runs on a simulated feed (offline, deterministic) or live data.
- **Signal layer** (`signals/`): `SignalSource` interface, cross-venue **de-vig**
  source (`MoneylineOddsSource`), an explicit `MarketMatcher` (wrong matches bet
  the wrong side, so matching is auditable, never magic), and `combine_sources`
  to blend several signals by confidence.
- **Persistence** (`Repository`): every bet + settlement is logged to SQLite
  with *both* our forecast and the consensus, so calibration can be re-scored
  and the model improved offline. Additive auto-migration keeps old DBs working.
- **Exit criteria (met on the simulated feed):** `python -m polybet paper` shows
  model Brier < market Brier (`beats baseline ✅`) and positive P&L across
  hundreds of resolved markets.
- **Still to do for live data:** wire a real signal source (de-vigged sportsbook
  / Kalshi odds) into `ExternalOddsModel` and build the reviewed `MarketMatcher`
  mapping, then run `python -m polybet paper --live` for a sustained period
  before advancing. Until a signal is wired, the engine correctly abstains.

### Phase 3 — Live, small  (gated)
- Implement `LiveExecutor` against `py-clob-client` (EIP-712 signing, USDC
  allowances, GTC/FOK orders, WebSocket fill reconciliation).
- Trade with a deliberately tiny bankroll. Keep `model_confidence` low and
  `kelly_fraction` at ¼ or less.
- **Exit criteria:** live fills reconcile to paper expectations; realized
  calibration matches backtest within tolerance.

### Phase 4 — Scale & harden  🔨 (monitoring & ops built)
- **Monitoring & ops dashboard** ✅ (`monitoring/`): reads the audit trail and
  computes operational health — rolling vs all-time calibration against the
  market baseline, **model-drift / edge-decay detection**, drawdown vs the
  kill-switch, and tiered alerts (INFO/WARN/CRITICAL). `python -m polybet monitor`
  renders a terminal panel or a self-contained HTML page (`--html`), and exits
  non-zero on CRITICAL so it doubles as a health check / CI gate.
- Still ahead: more signals, automated research pipeline, parameter sweeps in
  backtest; secrets management; continuous (scheduled) monitoring + paging.

---

## 6. KPIs (watch these, not your gut)

| Metric | What it tells you | Gate to advance |
|--------|-------------------|-----------------|
| Brier score vs consensus | Are we better calibrated than the market? | Must beat baseline |
| Log loss | Are we confidently wrong anywhere? | Trending down |
| ROI / CAGR | Is the bankroll growing? | Positive, net of costs |
| Max drawdown | Can we stomach the variance? | Within risk budget |
| Sharpe | Risk-adjusted return | Positive & stable |
| Fill quality (paper vs live) | Is our cost model honest? | Live ≈ paper |

---

## 7. Go-live checklist (do not skip)

- [ ] Backtest: signal beats no-edge control across multiple seeds.
- [ ] Paper on **live** data: Brier beats consensus over ≥ N resolved markets.
- [ ] Cost model validated against real spreads/slippage.
- [ ] `LiveExecutor` reconciles fills to the portfolio on testnet/small size.
- [ ] Risk caps and drawdown kill switch verified to actually halt trading.
- [ ] Secrets in env/secret store, never in code; `POLYBET_ENABLE_LIVE` flipped
      deliberately.
- [ ] Funded with money you can afford to lose entirely.

---

## 8. Risks & failure modes (eyes open)

- **No real edge.** The likeliest outcome for most people. The control run and
  calibration metrics exist to catch this *before* it costs money.
- **Resolution / oracle risk.** Markets resolve via UMA's optimistic oracle;
  disputes and ambiguous wording happen. Read resolution criteria.
- **Liquidity & slippage.** Thin books mean your fill is worse than the screen
  price — the book-participation cap and book-walking paper fills model this.
- **Correlated bets.** Many "independent" markets share a driver (one election,
  one macro event). Treat correlated exposure as one bet; group via `group_id`.
- **Overfitting the backtest.** Synthetic/known-outcome data flatters you. Trust
  *out-of-sample live paper* calibration over any backtest number.
- **Legal/compliance.** Polymarket access is restricted in some jurisdictions
  (incl. parts of the US). Confirm it's lawful for you before trading real money.

---

## 9. Why this design is "simple yet effective"

- **Pure standard library core** — runs and is testable anywhere, zero install.
  Heavy/networked dependencies are isolated to the live path.
- **One engine spine** for backtest/paper/live — no divergence between what you
  test and what you trade.
- **Every dial in one `Settings`** — tunable and backtest-sweepable.
- **The thesis is a test** — `tests/test_backtest.py` fails if the edge ever
  becomes illusory.
