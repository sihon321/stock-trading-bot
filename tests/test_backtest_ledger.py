from decimal import Decimal as D
import pytest
from trading_bot.backtest_ledger import PortfolioLedger
from trading_bot.backtest_models import BacktestBundle, BacktestInputError
from trading_bot.backtest_costs import cost_profile
from trading_bot.backtest_fills import model_session_fills
from test_backtest_fills import make_intent
from test_backtest_inputs import raw_bundle


def ledger_fixture(cash='2000'):
    raw=raw_bundle();raw['policy']['initial_cash']=cash
    b=BacktestBundle.model_validate(raw)
    return b,PortfolioLedger(b.policy,tuple(s.session for s in b.calendar))


def test_cash_reservation_prevents_two_tickers_sharing_capital():
    b,l=ledger_fixture();a=l.reserve(make_intent(b,quantity=20),cost_profile('baseline'))
    z=make_intent(b,'z',quantity=20).model_copy(update={'ticker':'000660'})
    assert a.quantity==18
    assert l.reserve(z,cost_profile('baseline')) is None
    assert l.available_cash>=0


def test_partial_fill_then_expiry_releases_remainder_once():
    b,l=ledger_fixture('10000');a=l.reserve(make_intent(b),cost_profile('baseline'))
    f=model_session_fills(b,b.calendar[6].session,(a,),'baseline')[0]
    l.apply_fill(f)
    assert l.holdings['005930'].quantity==10 and l.reserved_cash>0
    with pytest.raises(BacktestInputError):l.apply_fill(f)
    assert l.expire(a.intent_id)==10
    assert l.reserved_cash==0
    l.reconcile()


def test_no_oversell_or_duplicate_reservation():
    b,l=ledger_fixture();sell=make_intent(b,side='SELL',quantity=1,limit='100')
    with pytest.raises(BacktestInputError):l.reserve(sell,cost_profile('baseline'))
    buy=l.reserve(make_intent(b,quantity=1),cost_profile('baseline'))
    with pytest.raises(BacktestInputError):l.reserve(buy,cost_profile('baseline'))
