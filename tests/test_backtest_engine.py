from decimal import Decimal as D
import pytest
from trading_bot.backtest_engine import run_backtest, checked_float
from trading_bot.backtest_models import BacktestBundle
from test_backtest_inputs import raw_bundle


def run(raw=None,profile='baseline'):
    b=BacktestBundle.model_validate(raw or raw_bundle())
    return run_backtest(b,b.calendar[5].session,b.calendar[-1].session,profile)


def test_chronological_shared_ledger_and_next_session():
    r=run()
    assert any(f.quantity>0 for f in r.fills)
    by_id={d.intent_id:d for d in r.decisions if d.intent_id}
    for f in r.fills: assert f.session>by_id[f.intent_id].session
    assert all(s.reserved_cash<=s.settled_cash for s in r.sessions)
    assert any(s.holdings for s in r.sessions)


def test_missing_malformed_and_confidence_safe_hold():
    raw=raw_bundle();raw['signals'][0]['raw']='not-json'
    r=run(raw)
    assert any(d.reason=='MISSING_OR_MALFORMED_SIGNAL' and d.action=='HOLD' for d in r.decisions)


def test_existing_daily_risk_override_valid_signal():
    raw=raw_bundle();raw['policy']['initial_positions']=[{'ticker':'005930','quantity':10,'average_price':'90','known_at':'2022-01-01T00:00:00+00:00'}]
    r=run(raw)
    assert any(d.action=='SELL' and d.risk_override for d in r.decisions)


def test_future_execution_volume_cannot_change_prior_decision():
    raw=raw_bundle();first=run(raw)
    raw['bars'][-1]['volume']=10
    second=run(raw)
    assert first.decisions[:10]==second.decisions[:10]


def test_money_bridge_is_finite():
    assert checked_float(D('123.25'))==123.25
