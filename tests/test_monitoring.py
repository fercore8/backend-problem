from polybet.config import Settings
from polybet.monitoring import Thresholds, compute_health
from polybet.monitoring.dashboard import render_html, render_terminal
from polybet.monitoring.health import AlertLevel


def _settings(**kw):
    base = dict(bankroll=1000.0, max_drawdown=0.20)
    base.update(kw)
    return Settings(**base)


def _series(rows):
    """rows: list of (pnl, fair, consensus, outcome)."""
    return list(rows)


def test_empty_series_is_info_not_crash():
    r = compute_health([], _settings())
    assert r.n_resolved == 0
    assert r.equity == 1000.0
    assert r.status == AlertLevel.INFO
    assert any(a.code == "no_data" for a in r.alerts)


def test_equity_curve_and_pnl_reconstructed():
    series = _series([(10.0, 0.7, 0.6, 1), (-5.0, 0.3, 0.4, 0), (20.0, 0.8, 0.7, 1)])
    r = compute_health(series, _settings())
    assert r.realized_pnl == 25.0
    assert r.equity == 1025.0
    assert r.equity_curve == [1000.0, 1010.0, 1005.0, 1025.0]


def test_low_sample_warns_but_not_critical():
    series = _series([(1.0, 0.7, 0.6, 1)] * 5)
    r = compute_health(series, _settings(), thresholds=Thresholds(min_sample=30))
    assert any(a.code == "low_sample" for a in r.alerts)
    # No edge alert fires below min_sample even if calibration looks off.
    assert not any(a.code == "no_edge" for a in r.alerts)


def test_no_edge_is_critical_with_enough_sample():
    # Model forecasts are worse (further from outcome) than consensus.
    series = _series([(0.0, 0.5, 0.9, 1)] * 40 + [(0.0, 0.5, 0.1, 0)] * 40)
    r = compute_health(series, _settings(), thresholds=Thresholds(min_sample=30))
    assert not r.beats_baseline_all
    assert any(a.code == "no_edge" for a in r.alerts)
    assert r.status == AlertLevel.CRITICAL


def test_edge_decay_warns_when_recent_trails_but_alltime_leads():
    # Early: model far better than market. Recent: model worse than market.
    good = [(0.0, 0.95, 0.6, 1)] * 80   # model close to outcome=1, market less so
    bad = [(0.0, 0.5, 0.95, 1)] * 20    # recent: market closer to outcome than model
    r = compute_health(_series(good + bad), _settings(),
                       thresholds=Thresholds(min_sample=30, rolling_window=20))
    assert r.beats_baseline_all          # all-time still leads
    assert not r.beats_baseline_recent   # but lately it doesn't
    assert any(a.code == "edge_decay" for a in r.alerts)
    assert r.status == AlertLevel.WARN


def test_drawdown_warn_and_critical_tiers():
    s = _settings(max_drawdown=0.20)
    # Climb to 1200, then draw down. 0.5*20% = 10% warn, 0.9*20% = 18% crit.
    up = [(200.0, 0.7, 0.6, 1)]
    # drop 132 from peak 1200 -> 11% drawdown -> WARN tier
    warn = compute_health(_series(up + [(-132.0, 0.3, 0.4, 0)]), s,
                          thresholds=Thresholds(min_sample=1))
    assert any(a.code == "drawdown_elevated" for a in warn.alerts)

    # drop 230 from peak 1200 -> 19.2% -> within 90% of kill-switch -> CRITICAL
    crit = compute_health(_series(up + [(-230.0, 0.3, 0.4, 0)]), s,
                          thresholds=Thresholds(min_sample=1))
    assert any(a.code == "drawdown_near_kill" for a in crit.alerts)


def test_kill_switch_engaged_when_drawdown_exceeds_limit():
    s = _settings(max_drawdown=0.20)
    series = _series([(200.0, 0.7, 0.6, 1), (-260.0, 0.3, 0.4, 0)])  # 1200 -> 940 = 21.7%
    r = compute_health(series, s, thresholds=Thresholds(min_sample=1))
    assert r.kill_switch_engaged
    assert any(a.code == "kill_switch" for a in r.alerts)
    assert r.status == AlertLevel.CRITICAL


def test_status_is_worst_alert_level():
    series = _series([(0.0, 0.5, 0.9, 1)] * 40 + [(0.0, 0.5, 0.1, 0)] * 40)
    r = compute_health(series, _settings(), thresholds=Thresholds(min_sample=30))
    assert r.status == max(a.level for a in r.alerts)


def test_renderers_produce_output():
    series = _series([(10.0, 0.7, 0.6, 1)] * 40)
    r = compute_health(series, _settings(), thresholds=Thresholds(min_sample=30))
    term = render_terminal(r)
    assert "ops dashboard" in term
    assert "Calibration" in term
    html = render_html(r, predictions=[0.7] * 40, outcomes=[1] * 40)
    assert html.startswith("<!doctype html>")
    assert "Reliability diagram" in html


def test_compute_health_from_real_paper_run():
    """End-to-end: a real paper run's DB feeds the monitor and shows edge."""
    import os
    import tempfile

    from polybet.data.repository import Repository
    from polybet.data.sample import generate_scenario
    from polybet.runner import PaperTrader, SyntheticMarketSource
    from polybet.valuation.models import ExternalOddsModel, ShrinkageEnsemble

    scenario = generate_scenario(n_markets=400, seed=2, signal_sigma=0.03)
    model = ShrinkageEnsemble([(ExternalOddsModel(scenario.external_probs), 1.0)], 0.6)
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "run.db")
        repo = Repository(path)
        PaperTrader(_settings(min_edge=0.02), model, SyntheticMarketSource(scenario), repo).run()

        r = compute_health(repo.settlement_series(), _settings(), n_bets=repo.bet_count())
        assert r.n_resolved > 0
        assert r.beats_baseline_all  # genuine signal beats the market baseline
