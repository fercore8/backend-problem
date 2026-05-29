import os
import tempfile

from polybet.config import Settings
from polybet.data.repository import Repository
from polybet.data.sample import generate_scenario
from polybet.runner import PaperTrader, SyntheticMarketSource
from polybet.valuation.models import ConsensusModel, ExternalOddsModel, ShrinkageEnsemble


def _settings():
    return Settings(
        bankroll=1000.0,
        min_edge=0.02,
        slippage=0.003,
        kelly_fraction=0.25,
        model_confidence=0.6,
        max_position_fraction=0.05,
    )


def _edge_model(scenario):
    return ShrinkageEnsemble(
        [(ExternalOddsModel(scenario.external_probs), 1.0)], confidence=0.6
    )


def test_synthetic_source_opens_then_resolves_everything():
    scenario = generate_scenario(n_markets=50, seed=1, signal_sigma=0.03)
    src = SyntheticMarketSource(scenario, batch_size=10)
    seen, resolved = set(), set()
    # Drive it manually to confirm the open-then-resolve cadence.
    while not src.done():
        for m in src.poll():
            seen.add(m.id)
        resolved |= set(src.drain_resolutions())
    resolved |= set(src.drain_resolutions())
    assert seen == {m.id for m in scenario.markets}
    assert resolved == seen  # every opened market eventually resolves


def test_paper_run_scores_model_against_consensus():
    scenario = generate_scenario(n_markets=400, seed=2, signal_sigma=0.03)
    trader = PaperTrader(_settings(), _edge_model(scenario), SyntheticMarketSource(scenario))
    report = trader.run()
    assert report.n_bets > 0
    assert report.n_resolved > 0
    # A genuine signal should be better calibrated than the market consensus.
    assert report.model_brier < report.consensus_brier
    assert report.beats_baseline


def test_consensus_model_places_no_bets_in_paper():
    scenario = generate_scenario(n_markets=200, seed=3, signal_sigma=0.03)
    trader = PaperTrader(_settings(), ConsensusModel(), SyntheticMarketSource(scenario))
    report = trader.run()
    assert report.n_bets == 0


def test_paper_run_persists_audit_trail():
    scenario = generate_scenario(n_markets=200, seed=4, signal_sigma=0.03)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "audit.db")
        repo = Repository(path)
        trader = PaperTrader(_settings(), _edge_model(scenario), SyntheticMarketSource(scenario), repo)
        report = trader.run()

        # Re-score calibration straight from the persisted rows.
        from polybet.metrics import brier_score

        preds, outs = repo.calibration_data()
        cons, _ = repo.consensus_calibration_data()
        assert len(preds) == report.n_resolved
        assert len(cons) == report.n_resolved
        # Persisted forecasts reproduce the in-memory Brier (within rounding).
        assert abs(brier_score(preds, outs) - report.model_brier) < 1e-9


def test_repository_migrates_old_db_without_consensus():
    import sqlite3

    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "old.db")
        # Simulate a pre-Phase-2 settlements table (no consensus column).
        con = sqlite3.connect(path)
        con.execute(
            "CREATE TABLE settlements (id INTEGER PRIMARY KEY, market_id TEXT,"
            " resolved_yes INTEGER, pnl REAL, fair_prob REAL)"
        )
        con.commit()
        con.close()

        repo = Repository(path)  # should add the consensus column, not crash
        repo.record_settlement("m1", True, 1.0, 0.7, 0.6)
        cons, outs = repo.consensus_calibration_data()
        assert cons == [0.6] and outs == [1]
