from decimal import Decimal as D
import pytest
from trading_bot.backtest_fills import model_session_fills
from trading_bot.backtest_models import BacktestBundle, OpenIntent
from test_backtest_inputs import raw_bundle


def make_intent(b,id='a',side='BUY',quantity=20,limit='110'):
    return OpenIntent(intent_id=id,ticker='005930',side=side,quantity=quantity,remaining_quantity=quantity,limit_price=D(limit),decision_session=b.calendar[5].session,eligible_session=b.calendar[6].session)


def test_aggregate_partial_capacity_and_stable_allocation():
    b=BacktestBundle.model_validate(raw_bundle());a=make_intent(b);z=make_intent(b,'z')
    x=model_session_fills(b,b.calendar[6].session,(z,a),'baseline')
    assert [f.quantity for f in x]==[10,0]
    assert x[0].reason=='PARTIAL' and x[1].reason=='CAPACITY_EXHAUSTED'
    assert x==model_session_fills(b,b.calendar[6].session,(a,z),'baseline')
    assert model_session_fills(b,b.calendar[6].session,(a,),'stress')[0].quantity==5


def test_no_same_session_fill_and_no_range_touch_fiction():
    b=BacktestBundle.model_validate(raw_bundle());a=make_intent(b)
    assert model_session_fills(b,a.decision_session,(a,),'baseline')[0].reason=='NOT_YET_ELIGIBLE'
    a=make_intent(b,limit='104')
    f=model_session_fills(b,b.calendar[6].session,(a,),'baseline')[0]
    assert f.reason=='OPENING_LIMIT_NOT_MET' and f.quantity==0 # low touches 104, opening adverse 106

@pytest.mark.parametrize('change,reason',[(dict(volume=0),'ZERO_VOLUME'),(dict(open='106',high='106',low='106',close='106'),'LIMIT_LOCK_UNPROVEN')])
def test_no_unproven_volume_or_limit_lock(change,reason):
    raw=raw_bundle();s=raw['calendar'][6]['session']
    next(x for x in raw['bars'] if x['ticker']=='005930' and x['session']==s).update(change)
    b=BacktestBundle.model_validate(raw)
    assert model_session_fills(b,b.calendar[6].session,(make_intent(b),),'baseline')[0].reason==reason


def test_suspension_and_sell_adverse_slippage():
    raw=raw_bundle();raw['trading_status'][0]['state']='SUSPENDED';b=BacktestBundle.model_validate(raw)
    assert model_session_fills(b,b.calendar[6].session,(make_intent(b),),'baseline')[0].reason=='NOT_TRADABLE'
    b=BacktestBundle.model_validate(raw_bundle())
    f=model_session_fills(b,b.calendar[6].session,(make_intent(b,side='SELL',limit='100'),),'baseline')[0]
    assert f.executed_price<D('105') and f.sell_tax>0
