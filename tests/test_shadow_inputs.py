import pytest
from trading_bot.backtest_models import BacktestBundle, content_hash
from trading_bot.backtest_engine import run_backtest, project_backtest_action
from trading_bot.shadow_inputs import collect_shadow_snapshots
from test_backtest_inputs import raw_bundle


def bundle(): return BacktestBundle.model_validate(raw_bundle())


def test_observer_preserves_exact_replay_and_reservations():
    b=bundle(); seen=[]
    ordinary=run_backtest(b,b.calendar[5].session)
    observed=run_backtest(b,b.calendar[5].session,decision_observer=seen.append)
    assert content_hash(ordinary)==content_hash(observed)
    assert seen and len({s.unit_id for s in seen})==len(seen)
    assert any(s.reserved_cash>0 for s in seen)
    assert any(s.quantity>0 for s in seen)
    for s in seen:
        if s.baseline_reason!='SCREENER_EXCLUDED':
            p=project_backtest_action(s,s.fixture_raw)
            assert (p.action,p.quantity)==(s.baseline_action,s.baseline_quantity)
        assert s.available_cash+s.reserved_cash==s.settled_cash


def test_baseline_reconciles_and_is_immutable():
    b=bundle(); snapshots,baseline=collect_shadow_snapshots(b,start=b.calendar[5].session)
    original=content_hash(baseline)
    again,saved=collect_shadow_snapshots(b,baseline)
    assert again==snapshots and content_hash(saved)==original
    with pytest.raises(ValueError,match='BASELINE_INPUT_MISMATCH'):
        raw=raw_bundle(); raw['policy']['initial_cash']='12345'
        collect_shadow_snapshots(BacktestBundle.model_validate(raw),baseline)


def test_missing_held_price_is_explicit():
    raw=raw_bundle();day=raw['calendar'][5]['session']
    raw['policy']['initial_positions']=[{'ticker':'005930','quantity':10,'average_price':'90','known_at':'2022-01-01T00:00:00+00:00'}]
    raw['bars']=[b for b in raw['bars'] if not(b['ticker']=='005930' and b['session']==day)]
    b=BacktestBundle.model_validate(raw);snaps,_=collect_shadow_snapshots(b,start=b.calendar[5].session)
    s=next(s for s in snaps if s.session.isoformat()==day and s.ticker=='005930')
    assert s.quantity==10 and not s.eligible and s.price is None
