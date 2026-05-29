from polybet.models import Level, Market, OrderBook
from polybet.signals.source import (
    MarketMatcher,
    MoneylineOddsSource,
    StaticProbabilitySource,
    TwoWayOdds,
    combine_sources,
)


def _market(mid):
    book = OrderBook(bids=[Level(0.49, 100)], asks=[Level(0.51, 100)])
    return Market(id=mid, question="q", book=book)


def test_two_way_odds_devig_is_unbiased():
    # Symmetric odds -> 0.5 after de-vig, regardless of the vig size.
    assert abs(TwoWayOdds(1.91, 1.91).fair_probability() - 0.5) < 1e-9


def test_two_way_odds_devig_favorite():
    # Heavy favorite: short odds on YES -> high probability, normalized to sum 1.
    p = TwoWayOdds(1.25, 4.0).fair_probability()
    raw_yes, raw_no = 1 / 1.25, 1 / 4.0
    assert abs(p - raw_yes / (raw_yes + raw_no)) < 1e-9
    assert p > 0.5


def test_static_source_filters_to_present_markets():
    src = StaticProbabilitySource({"a": 0.7, "z": 0.1})
    out = src.probabilities([_market("a"), _market("b")])
    assert out == {"a": 0.7}


def test_moneyline_source_matches_and_devigs():
    matcher = MarketMatcher({"GAME-LAL": "m1"})
    src = MoneylineOddsSource({"GAME-LAL": TwoWayOdds(1.91, 1.91)}, matcher)
    out = src.probabilities([_market("m1")])
    assert set(out) == {"m1"}
    assert abs(out["m1"] - 0.5) < 1e-9


def test_moneyline_source_skips_unmatched():
    matcher = MarketMatcher({})  # nothing matched
    src = MoneylineOddsSource({"GAME-LAL": TwoWayOdds(1.91, 1.91)}, matcher)
    assert src.probabilities([_market("m1")]) == {}


def test_moneyline_source_skips_malformed_odds():
    matcher = MarketMatcher({"X": "m1"})
    src = MoneylineOddsSource({"X": TwoWayOdds(1.0, 2.0)}, matcher)  # odds must be > 1
    assert src.probabilities([_market("m1")]) == {}


def test_combine_sources_weighted_average():
    a = StaticProbabilitySource({"m1": 0.8})
    b = StaticProbabilitySource({"m1": 0.4})
    out = combine_sources([(a, 3.0), (b, 1.0)], [_market("m1")])
    # (3*0.8 + 1*0.4) / 4 = 0.7
    assert abs(out["m1"] - 0.7) < 1e-9


def test_combine_sources_abstains_when_uncovered():
    a = StaticProbabilitySource({"m1": 0.8})
    out = combine_sources([(a, 1.0)], [_market("m1"), _market("m2")])
    assert "m2" not in out
