from polybet.models import Level, Market, OrderBook
from polybet.strategy.arbitrage import find_dutch_book
from polybet.strategy.edge import CostModel


def _leg(mid, ask, group):
    book = OrderBook(bids=[Level(ask - 0.02, 100)], asks=[Level(ask, 100)])
    return Market(id=mid, question="q", book=book, group_id=group)


def test_detects_underpriced_complete_set():
    legs = [_leg("a", 0.30, "elec"), _leg("b", 0.30, "elec"), _leg("c", 0.30, "elec")]
    opps = find_dutch_book(legs, cost=CostModel(slippage=0.0), min_profit=0.01)
    assert len(opps) == 1
    assert opps[0].profit_per_set > 0.05  # ~1 - 0.90


def test_no_arb_when_sum_exceeds_one():
    legs = [_leg("a", 0.40, "elec"), _leg("b", 0.40, "elec"), _leg("c", 0.40, "elec")]
    assert find_dutch_book(legs, cost=CostModel(slippage=0.0)) == []


def test_ignores_single_leg_groups():
    legs = [_leg("a", 0.30, "solo")]
    assert find_dutch_book(legs, cost=CostModel(slippage=0.0)) == []
