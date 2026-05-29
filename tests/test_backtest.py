"""End-to-end sanity: a real signal edge should beat the no-edge control.

This is the test that encodes the whole thesis. If it ever fails, either the
pipeline regressed or the edge is illusory — exactly what we want to catch
before risking money.
"""

from polybet.config import Settings
from polybet.backtest import run_backtest
from polybet.data.sample import generate_scenario
from polybet.valuation.models import ConsensusModel, ExternalOddsModel, ShrinkageEnsemble


def _run(signal_sigma: float) -> float:
    s = Settings(bankroll=1000.0, min_edge=0.02, slippage=0.003,
                 kelly_fraction=0.25, model_confidence=0.6)
    scenario = generate_scenario(n_markets=400, seed=11, signal_sigma=signal_sigma)
    model = ShrinkageEnsemble(
        [(ExternalOddsModel(scenario.external_probs), 1.0)],
        confidence=s.model_confidence,
    )
    report, _ = run_backtest(s, scenario, model, sequential=True)
    return report.roi


def test_edge_beats_no_edge_control():
    edge_roi = _run(signal_sigma=0.03)        # we are better informed
    control_roi = _run(signal_sigma=0.08)     # as noisy as the market: no edge
    assert edge_roi > control_roi


def test_edge_run_is_profitable():
    assert _run(signal_sigma=0.03) > 0.0


def test_calibration_is_recorded():
    s = Settings(bankroll=1000.0, min_edge=0.02)
    scenario = generate_scenario(n_markets=200, seed=5, signal_sigma=0.03)
    model = ShrinkageEnsemble([(ExternalOddsModel(scenario.external_probs), 1.0)], 0.6)
    report, engine = run_backtest(s, scenario, model)
    assert report.n_resolved > 0
    assert 0.0 <= report.brier <= 1.0
