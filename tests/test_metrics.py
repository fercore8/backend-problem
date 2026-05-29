from polybet.metrics import brier_score, log_loss, max_drawdown, roi, sharpe


def test_brier_perfect_vs_worst():
    assert brier_score([1.0, 0.0], [1, 0]) == 0.0
    assert brier_score([0.0, 1.0], [1, 0]) == 1.0


def test_log_loss_penalizes_confident_wrong():
    good = log_loss([0.9], [1])
    bad = log_loss([0.1], [1])
    assert bad > good


def test_roi():
    assert abs(roi(1000, 1200) - 0.2) < 1e-9


def test_max_drawdown():
    curve = [100, 120, 90, 110]
    # peak 120 -> trough 90 => 25%
    assert abs(max_drawdown(curve) - 0.25) < 1e-9


def test_sharpe_positive_for_steady_growth():
    curve = [100, 101, 102, 103, 104]
    assert sharpe(curve) > 0
