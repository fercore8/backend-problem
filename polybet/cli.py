"""Command-line entrypoints.

    python -m polybet backtest            # run the offline edge demo + report
    python -m polybet backtest --no-edge  # control run: signal as noisy as market
    python -m polybet paper               # paper-trade live Polymarket data (needs requests)

The CLI wires the standard stack: ExternalOdds + Consensus -> ShrinkageEnsemble
-> edge gate -> fractional Kelly -> risk engine -> paper fills.
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
    print(
        "Paper trading against live data needs (a) the 'requests' package and\n"
        "(b) a real signal source wired into ExternalOddsModel.\n\n"
        "The plumbing is ready in polybet/data/polymarket_client.py and the\n"
        "engine; supply probabilities for live markets and call TradingEngine.step\n"
        "on each polled snapshot. See docs/PLAN.md 'Phase 3'."
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

    pa = sub.add_parser("paper", help="paper-trade live data (needs requests + signal)")
    pa.set_defaults(func=cmd_paper)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
