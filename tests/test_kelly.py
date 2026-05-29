from polybet.strategy.kelly import kelly_fraction


def test_no_edge_means_no_bet():
    assert kelly_fraction(0.5, 0.5) == 0.0


def test_negative_edge_clamped_to_zero():
    assert kelly_fraction(0.4, 0.6) == 0.0


def test_positive_edge_formula():
    # f* = (q - p) / (1 - p) = (0.6 - 0.5)/0.5 = 0.2
    assert abs(kelly_fraction(0.6, 0.5) - 0.2) < 1e-9


def test_certain_win_scales_up():
    # very high conviction at a cheap price -> large fraction
    assert kelly_fraction(0.99, 0.5) > kelly_fraction(0.6, 0.5)


def test_degenerate_prices():
    assert kelly_fraction(0.9, 0.0) == 0.0
    assert kelly_fraction(0.9, 1.0) == 0.0
