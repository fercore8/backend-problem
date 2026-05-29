from polybet.config import Settings
from polybet.models import Level, Market, OrderBook, Side, Signal
from polybet.portfolio import Portfolio
from polybet.risk.risk_engine import RiskEngine


def _signal(kelly=1.0, side=Side.YES, price=0.5):
    return Signal("m1", side, fair_prob=0.7, price=price, edge=0.2, kelly_fraction=kelly)


def _market(depth=1000.0):
    book = OrderBook(bids=[Level(0.49, depth)], asks=[Level(0.51, depth)])
    return Market(id="m1", question="q", book=book)


def test_per_market_cap_limits_size():
    s = Settings(bankroll=1000, kelly_fraction=1.0, max_position_fraction=0.05,
                 max_total_exposure=1.0, max_book_participation=1.0)
    pf = Portfolio(cash=1000)
    dec = RiskEngine(s).evaluate(_signal(kelly=1.0), _market(), pf)
    assert dec.approved
    assert dec.notional <= 0.05 * 1000 + 1e-6


def test_drawdown_kill_switch():
    s = Settings(bankroll=1000, max_drawdown=0.20)
    pf = Portfolio(cash=1000)
    pf._peak = 1000
    pf.cash = 700  # 30% below peak
    dec = RiskEngine(s).evaluate(_signal(), _market(), pf)
    assert not dec.approved and "drawdown" in dec.reason


def test_aggregate_exposure_cap():
    s = Settings(bankroll=1000, kelly_fraction=1.0, max_position_fraction=1.0,
                 max_total_exposure=0.10, max_book_participation=1.0)
    pf = Portfolio(cash=1000)
    dec = RiskEngine(s).evaluate(_signal(kelly=1.0), _market(), pf)
    assert dec.approved and dec.notional <= 0.10 * 1000 + 1e-6


def test_book_participation_cap():
    s = Settings(bankroll=100000, kelly_fraction=1.0, max_position_fraction=1.0,
                 max_total_exposure=1.0, max_book_participation=0.25)
    pf = Portfolio(cash=100000)
    m = _market(depth=100)  # only 100 shares on the ask
    dec = RiskEngine(s).evaluate(_signal(kelly=1.0, price=0.51), m, pf)
    assert dec.approved
    assert dec.shares <= 0.25 * 100 + 1e-6


def test_max_open_positions():
    s = Settings(bankroll=1000, max_open_positions=0)
    pf = Portfolio(cash=1000)
    dec = RiskEngine(s).evaluate(_signal(), _market(), pf)
    assert not dec.approved and "open positions" in dec.reason
