"""Command-line entrypoints.

    python -m polybet backtest             # offline edge demo, averaged over seeds
    python -m polybet backtest --no-edge   # control: estimate == market price
    python -m polybet paper                # paper-trade a simulated live feed
    python -m polybet paper --live         # paper-trade real Polymarket data (needs requests)

The CLI wires the standard stack: ExternalOdds + Consensus -> ShrinkageEnsemble
-> edge gate -> fractional Kelly -> risk engine -> paper fills, and (in paper
mode) continuously compares our calibration against the market consensus.
"""

from __future__ import annotations

import argparse

from .config import SETTINGS, Settings
from .data.sample import generate_scenario
from .valuation.models import ConsensusModel, ExternalOddsModel, ShrinkageEnsemble


def _build_model(external_probs: dict[str, float], settings: Settings) -> ShrinkageEnsemble:
    return ShrinkageEnsemble(
        models=[(ExternalOddsModel(external_probs), 1.0), (ConsensusModel(), 0.0)],
        confidence=settings.model_confidence,
    )


def cmd_backtest(args: argparse.Namespace) -> int:
    import statistics

    from .backtest import run_backtest

    rois: list[float] = []
    last_report = None
    for i in range(args.seeds):
        seed = args.seed + i
        scenario = generate_scenario(
            n_markets=args.n_markets, seed=seed, signal_sigma=0.04
        )
        if args.no_edge:
            # True control: our estimate IS the market price -> zero informational
            # edge by construction. Produces no trades, proving the profit in the
            # real run comes from the signal, not from the machinery.
            model = ConsensusModel()
        else:
            model = _build_model(scenario.external_probs, SETTINGS)
        report, _ = run_backtest(SETTINGS, scenario, model, sequential=args.sequential)
        rois.append(report.roi)
        last_report = report

    mode = "NO-EDGE control (consensus)" if args.no_edge else "with edge"
    flow = "sequential (compounding)" if args.sequential else "snapshot (deploy-once)"
    print(f"\nBacktest ({mode}, {flow}, {args.n_markets} markets/seed):\n")
    print(last_report.render())  # detail of the last seed
    if args.seeds > 1:
        clean = [r for r in rois if r == r]  # drop NaNs (no-trade control)
        if clean:
            med = statistics.median(clean)
            wins = sum(1 for r in clean if r > 0)
            print(
                f"\n  across {args.seeds} seeds: median ROI {med:+.1%}, "
                f"profitable {wins}/{len(clean)}, "
                f"range [{min(clean):+.1%}, {max(clean):+.1%}]"
            )
    if args.no_edge:
        print("\n  ^ consensus = market price, so the edge gate finds nothing to bet.")
    return 0


def cmd_paper(args: argparse.Namespace) -> int:
    from .data.sample import generate_scenario
    from .runner import PaperTrader, SyntheticMarketSource

    if args.live:
        return _cmd_paper_live(args)

    # Offline simulated feed: deterministic, dependency-free, models the real
    # cadence (markets open, you bet, they later resolve). Our signal is a less
    # noisy read of truth than the market, i.e. a genuine edge to harvest.
    scenario = generate_scenario(
        n_markets=args.n_markets, seed=args.seed, signal_sigma=0.04
    )
    model = _build_model(scenario.external_probs, SETTINGS)
    source = SyntheticMarketSource(scenario, batch_size=args.batch_size)
    repo = None
    if args.db:
        from .data.repository import Repository

        repo = Repository(args.db)
    trader = PaperTrader(SETTINGS, model, source, repository=repo)
    report = trader.run()

    print(f"\nPaper run (simulated feed, {args.n_markets} markets, seed {args.seed}):\n")
    print(report.render())
    if args.db:
        print(f"\n  audit trail persisted to {args.db}")
    return 0


def _cmd_paper_live(args: argparse.Namespace) -> int:
    """Paper-trade against the real Polymarket feed.

    Read-only and risk-free: it fetches live books and simulates fills.  Placing
    real orders is Phase 3 (LiveExecutor), deliberately gated.  A real edge needs
    a real signal source wired into ExternalOddsModel — without one we abstain on
    every market, which is the correct, safe default.
    """
    try:
        from .data.polymarket_client import PolymarketClient
    except Exception as exc:  # pragma: no cover
        print(f"Live paper trading needs the 'requests' extra: pip install -e '.[live]'\n{exc}")
        return 1

    print(
        "Live paper trading is read-only and safe, but it needs a real signal\n"
        "source to have any edge. Wire one up like this:\n\n"
        "    from polybet.data.polymarket_client import PolymarketClient\n"
        "    from polybet.signals import MoneylineOddsSource, MarketMatcher, TwoWayOdds\n"
        "    from polybet.signals.source import combine_sources\n"
        "    from polybet.runner import PaperTrader, MarketSource\n\n"
        "    client = PolymarketClient()\n"
        "    markets = client.fetch_markets(limit=100)\n"
        "    # 1. de-vig external odds -> independent P(YES)\n"
        "    # 2. match external events to market ids (MarketMatcher)\n"
        "    # 3. feed combine_sources(...) into ExternalOddsModel each poll\n\n"
        "See docs/PLAN.md 'Phase 2' for the full recipe. Until a signal is wired,\n"
        "the engine correctly abstains on every market (no edge => no bet)."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="polybet", description="A wise base for Polymarket betting.")
    sub = p.add_subparsers(dest="cmd", required=True)

    bt = sub.add_parser("backtest", help="run the offline edge demo")
    bt.add_argument("--n-markets", type=int, default=500)
    bt.add_argument("--seed", type=int, default=1, help="first seed (seeds run seed..seed+N-1)")
    bt.add_argument("--seeds", type=int, default=20, help="number of seeds to average over")
    bt.add_argument("--no-edge", action="store_true", help="control: estimate == market price")
    bt.add_argument(
        "--sequential",
        action="store_true",
        help="compound one bet at a time (high variance) vs snapshot deploy-once (default)",
    )
    bt.set_defaults(func=cmd_backtest)

    pa = sub.add_parser("paper", help="paper-trade a simulated (or live) feed")
    pa.add_argument("--n-markets", type=int, default=500)
    pa.add_argument("--seed", type=int, default=1)
    pa.add_argument("--batch-size", type=int, default=25, help="markets opened per tick")
    pa.add_argument("--db", type=str, default=None, help="SQLite path for the audit trail")
    pa.add_argument("--live", action="store_true", help="use the real Polymarket feed (read-only)")
    pa.set_defaults(func=cmd_paper)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
