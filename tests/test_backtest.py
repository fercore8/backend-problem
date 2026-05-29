"""End-to-end sanity: a real signal edge must make money, and the no-edge
control must not.

This is the test that encodes the whole thesis. If it ever fails, either the
pipeline regressed or the edge is illusory — exactly what we want to catch
before risking money.

We aggregate over many seeds because a single sequence is dominated by variance
(the drawdown kill-switch can legitimately end an unlucky run early). The
*expected* behaviour, not any one path, is what must hold.
"""

import statistics

from polybet.backtest import run_backtest
from polybet.config import Settings
from polybet.data.sample import generate_scenario
from polybet.valuation.models import ConsensusModel, ExternalOddsModel, ShrinkageEnsemble

N_SEEDS = 25


def _settings() -> Settings:
    return Settings(
        bankroll=1000.0,
        min_edge=0.02,
        slippage=0.003,
        kelly_fraction=0.25,
        model_confidence=0.6,
        max_position_fraction=0.05,
    )


def _edge_roi(seed: int) -> float:
    s = _settings()
    scenario = generate_scenario(n_markets=500, seed=seed, signal_sigma=0.03)
    model = ShrinkageEnsemble(
        [(ExternalOddsModel(scenario.external_probs), 1.0)], confidence=s.model_confidence
    )
    report, _ = run_backtest(s, scenario, model, sequential=False)
    return report.roi


def _control_roi(seed: int) -> float:
    """Consensus: our estimate IS the market price -> zero edge by construction."""
    s = _settings()
    scenario = generate_scenario(n_markets=500, seed=seed, signal_sigma=0.03)
    report, _ = run_backtest(s, scenario, ConsensusModel(), sequential=False)
    return report.roi


def test_edge_is_profitable_in_expectation():
    rois = [_edge_roi(seed) for seed in range(N_SEEDS)]
    assert statistics.median(rois) > 0.0
    # The edge should win clearly more often than it loses.
    assert sum(1 for r in rois if r > 0) > N_SEEDS // 2


def test_edge_beats_no_edge_control():
    edge = statistics.median([_edge_roi(seed) for seed in range(N_SEEDS)])
    control = statistics.median([_control_roi(seed) for seed in range(N_SEEDS)])
    assert edge > control


def test_consensus_control_places_no_bets():
    """With no informational edge, the gate must find nothing to bet."""
    s = _settings()
    scenario = generate_scenario(n_markets=500, seed=3, signal_sigma=0.03)
    report, _ = run_backtest(s, scenario, ConsensusModel(), sequential=False)
    assert report.n_bets == 0
    assert report.roi == 0.0


def test_calibration_is_recorded():
    s = _settings()
    scenario = generate_scenario(n_markets=400, seed=5, signal_sigma=0.03)
    model = ShrinkageEnsemble([(ExternalOddsModel(scenario.external_probs), 1.0)], 0.6)
    report, _ = run_backtest(s, scenario, model, sequential=False)
    assert report.n_resolved > 0
    assert 0.0 <= report.brier <= 1.0
