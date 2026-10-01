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

from trading_bot.backtest_ledger import Lot
from trading_bot.backtest_models import CorporateAction
from trading_bot.backtest_fills import opening_cutoff


def test_sale_proceeds_T_plus_two_holiday_not_calendar_days():
    b,l=ledger_fixture('0');l.holdings['005930']=Lot(20,D('100'))
    # Friday before Monday holiday; next two KRX sessions are Tuesday/Wednesday.
    ix=next(i for i,s in enumerate(b.calendar) if s.session.isoformat()=='2023-01-20')
    sell=make_intent(b,side='SELL',quantity=10,limit='100').model_copy(update={'decision_session':b.calendar[ix-1].session,'eligible_session':b.calendar[ix].session})
    sell=l.reserve(sell,cost_profile('baseline'));f=model_session_fills(b,b.calendar[ix].session,(sell,),'baseline')[0]
    l.apply_fill(f);l.expire(sell.intent_id)
    assert l.available_cash==0 and l.pending_cash>0
    l.start_session(b.calendar[ix+1].session);assert l.available_cash==0
    l.start_session(b.calendar[ix+2].session);assert l.available_cash>0 and l.pending_cash==0
    assert b.calendar[ix+2].session.isoformat()=='2023-01-25'


def test_split_conserves_cost_basis_and_dividend_payable_timing():
    b,l=ledger_fixture();l.holdings['005930']=Lot(10,D('100'))
    split=next(a for a in b.corporate_actions if a.kind=='SPLIT')
    l.apply_corporate_action(split,split.effective,opening_cutoff(split.effective))
    assert l.holdings['005930']==Lot(20,D('50'))
    dividend=next(a for a in b.corporate_actions if a.kind=='DIVIDEND')
    l.apply_corporate_action(dividend,dividend.effective,opening_cutoff(dividend.effective))
    assert l.action_cash==0
    l.apply_corporate_action(dividend,dividend.payable_session,opening_cutoff(dividend.payable_session))
    assert l.action_cash==20
    l.apply_corporate_action(dividend,dividend.payable_session,opening_cutoff(dividend.payable_session))
    assert l.action_cash==20


def test_unresolved_delist_preserves_inventory_and_unknown_valuation():
    b,l=ledger_fixture();l.holdings['005930']=Lot(10,D('100'))
    a=CorporateAction(action_id='delist',ticker='005930',kind='DELIST',effective=b.calendar[6].session,known_at=b.calendar[0].close_at)
    l.apply_corporate_action(a,a.effective,opening_cutoff(a.effective))
    assert l.holdings['005930'].quantity==10
    assert 'DELIST_DISPOSITION_UNKNOWN:005930' in l.unknowns
    assert l.snapshot({})[1] is None


def test_fractional_split_requires_terms():
    b,l=ledger_fixture();l.holdings['005930']=Lot(1,D('100'))
    a=CorporateAction(action_id='fraction',ticker='005930',kind='SPLIT',effective=b.calendar[6].session,known_at=b.calendar[0].close_at,ratio=D('0.5'))
    l.apply_corporate_action(a,a.effective,opening_cutoff(a.effective))
    assert l.holdings['005930']==Lot(1,D('100')) and l.unknowns
