from polybet.config import Settings
from polybet.engine import TradingEngine
from polybet.execution.paper import PaperExecutor
from polybet.models import Level, Market, OrderBook, Side
from polybet.portfolio import Portfolio
from polybet.valuation.models import ExternalOddsModel, ShrinkageEnsemble


def _market(mid_id="m1"):
    book = OrderBook(
        bids=[Level(0.49, 200), Level(0.48, 200)],
        asks=[Level(0.51, 200), Level(0.52, 200)],
    )
    return Market(id=mid_id, question="q", book=book)


def test_full_loop_places_and_settles_winning_bet():
    s = Settings(bankroll=1000, min_edge=0.03, slippage=0.0,
                 kelly_fraction=0.25, model_confidence=1.0, max_position_fraction=0.1)
    m = _market()
    model = ShrinkageEnsemble([(ExternalOddsModel({"m1": 0.80}), 1.0)], confidence=1.0)
    pf = Portfolio(cash=1000)
    eng = TradingEngine(s, model, PaperExecutor(), pf)

    eng.step([m])
    assert eng.state.n_bets == 1
    assert "m1" in pf.positions and pf.positions["m1"].side == Side.YES
    assert pf.cash < 1000  # capital deployed

    pnl = eng.settle("m1", resolved_yes=True)
    assert pnl > 0
    assert pf.equity() > 1000  # we won


def test_walks_book_for_slippage():
    # An order bigger than top level should average across levels.
    s = Settings(bankroll=1_000_000, min_edge=0.01, slippage=0.0,
                 kelly_fraction=1.0, model_confidence=1.0,
                 max_position_fraction=1.0, max_total_exposure=1.0,
                 max_book_participation=1.0)
    m = _market("big")
    model = ShrinkageEnsemble([(ExternalOddsModel({"big": 0.95}), 1.0)], confidence=1.0)
    pf = Portfolio(cash=1_000_000)
    eng = TradingEngine(s, model, PaperExecutor(), pf)
    eng.step([m])
    pos = pf.positions["big"]
    # consumed into the 0.52 level, so avg price should exceed best ask 0.51
    assert pos.avg_price > 0.51
