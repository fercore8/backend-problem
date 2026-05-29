from polybet.config import Settings
from polybet.models import Level, Market, OrderBook, Side
from polybet.strategy.edge import CostModel, build_signal


def _market(bid, ask):
    book = OrderBook(bids=[Level(bid, 100)], asks=[Level(ask, 100)])
    return Market(id="m1", question="q", book=book)


def test_buys_yes_when_underpriced():
    s = Settings(min_edge=0.03, slippage=0.0, taker_fee=0.0)
    m = _market(0.49, 0.51)
    sig = build_signal(m, fair_prob=0.70, settings=s)
    assert sig is not None and sig.side == Side.YES
    assert abs(sig.edge - (0.70 - 0.51)) < 1e-9


def test_buys_no_when_overpriced():
    s = Settings(min_edge=0.03, slippage=0.0, taker_fee=0.0)
    m = _market(0.49, 0.51)
    sig = build_signal(m, fair_prob=0.20, settings=s)
    assert sig is not None and sig.side == Side.NO
    # NO price = 1 - bid = 0.51; edge = (1-0.20) - 0.51 = 0.29
    assert abs(sig.edge - 0.29) < 1e-9


def test_no_trade_inside_threshold():
    s = Settings(min_edge=0.05, slippage=0.0, taker_fee=0.0)
    m = _market(0.49, 0.51)
    assert build_signal(m, fair_prob=0.53, settings=s) is None


def test_costs_can_kill_a_thin_edge():
    s = Settings(min_edge=0.03, slippage=0.05, taker_fee=0.0)
    m = _market(0.49, 0.51)
    # raw edge 0.04 but 0.05 slippage pushes effective edge negative
    assert build_signal(m, fair_prob=0.55, settings=s) is None
