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

from trading_bot.backtest_models import CoverageStatus, content_hash


def test_equivalent_ordered_inputs_and_independent_profiles():
    raw=raw_bundle();a=run(raw)
    raw['bars'].reverse(); raw['membership'].reverse()
    b=run(raw)
    assert content_hash(a)==content_hash(b)
    stress=run(raw,'stress')
    assert stress.manifest['scenario_group']==a.manifest['scenario_group']
    assert content_hash(stress)!=content_hash(a)
    assert sum(f.quantity for f in stress.fills)<=sum(f.quantity for f in a.fills)


def test_unknown_held_mark_is_null_not_zero_and_blocks_new_buy():
    raw=raw_bundle();raw['policy']['initial_positions']=[{'ticker':'005930','quantity':10,'average_price':'90','known_at':'2022-01-01T00:00:00+00:00'}]
    s=raw['calendar'][5]['session'];raw['bars']=[b for b in raw['bars'] if not (b['ticker']=='005930' and b['session']==s)]
    r=run(raw)
    assert r.sessions[0].net_equity is None and r.sessions[0].holdings
    assert r.final_coverage is CoverageStatus.INCOMPLETE
    assert not any(d.action=='BUY' for d in r.decisions if d.session.isoformat()==s)


def test_gross_attribution_reconciles_same_fill_path():
    r=run();drag=D('0')
    for session in r.sessions:
        for f in r.fills:
            if f.session==session.session:drag+=f.commission+f.sell_tax+f.surtax+f.slippage_drag
        if session.net_equity is not None: assert session.gross_equity-session.net_equity==drag
    assert r.final_coverage is CoverageStatus.INCOMPLETE
    assert 'SYNTHETIC_MARKET_RULES' in r.limitations


def test_canonical_decimal_spelling_is_normalized():
    raw=raw_bundle();a=BacktestBundle.model_validate(raw)
    raw['policy']['initial_cash']='10000.00'
    assert content_hash(a)==content_hash(BacktestBundle.model_validate(raw))


def test_future_retroactive_action_does_not_leak_into_prior_decisions():
    raw=raw_bundle();first=run(raw)
    raw['corporate_actions'].append({'action_id':'future-discovery','ticker':'005930','kind':'SPLIT','effective':raw['calendar'][5]['session'],'known_at':'2025-01-01T00:00:00+00:00','ratio':'2'})
    second=run(raw)
    assert first.decisions==second.decisions
    assert first.sessions==second.sessions


def test_historical_gap_is_visible_and_blocks_new_buy():
    raw=raw_bundle();s=raw['calendar'][2]['session']
    raw['bars']=[b for b in raw['bars'] if not(b['ticker']=='000660' and b['session']==s)]
    r=run(raw)
    assert 'HISTORY_GAP:000660' in r.sessions[0].unknowns
    assert not any(d.action=='BUY' for d in r.decisions)


def test_malformed_held_signal_does_not_bypass_shipped_parse_failure_order():
    raw=raw_bundle();raw['policy']['initial_positions']=[{'ticker':'005930','quantity':10,'average_price':'90','known_at':'2022-01-01T00:00:00+00:00'}]
    raw['signals'][0]['raw']='malformed'
    result=run(raw)
    first=next(d for d in result.decisions if d.session.isoformat()==raw['calendar'][5]['session'] and d.ticker=='005930')
    assert first.action=='HOLD' and not first.risk_override
    assert first.reason=='MISSING_OR_MALFORMED_SIGNAL'


def test_low_confidence_signals_cannot_buy():
    raw=raw_bundle()
    for signal in raw['signals']:signal['raw']='{"decision":"BUY","confidence":0.79,"reason":"fixture"}'
    assert not any(d.action=='BUY' for d in run(raw).decisions)


def test_value_observer_is_frozen_and_does_not_mutate_ledger():
    from pydantic import ValidationError
    b=BacktestBundle.model_validate(raw_bundle());seen=[]
    run_backtest(b,b.calendar[5].session,decision_observer=seen.append)
    with pytest.raises(ValidationError): seen[0].available_cash=D('0')
