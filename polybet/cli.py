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
    from .backtest import run_backtest

    scenario = generate_scenario(
        n_markets=args.n_markets, seed=args.seed, signal_sigma=0.04
    )
    if args.no_edge:
        # True control: our estimate IS the market price -> zero informational
        # edge by construction. Should produce ~no trades / ~break-even, proving
        # the profit in the real run comes from the signal, not the machinery.
        model = ConsensusModel()
    else:
        model = _build_model(scenario.external_probs, SETTINGS)
    report, _ = run_backtest(SETTINGS, scenario, model, sequential=not args.snapshot)

    mode = "NO-EDGE control (consensus)" if args.no_edge else "with edge"
    print(f"\nBacktest ({mode}, {args.n_markets} markets, seed {args.seed}):\n")
    print(report.render())
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
    bt.add_argument("--n-markets", type=int, default=300)
    bt.add_argument("--seed", type=int, default=7)
    bt.add_argument("--no-edge", action="store_true", help="control: no informational edge")
    bt.add_argument("--snapshot", action="store_true", help="bet all at once vs sequentially")
    bt.set_defaults(func=cmd_backtest)

    pa = sub.add_parser("paper", help="paper-trade live data (needs requests + signal)")
    pa.set_defaults(func=cmd_paper)

    args = p.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
