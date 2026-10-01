import copy
import json
from decimal import Decimal as D
from typer.testing import CliRunner
from trading_bot.cli import app
from trading_bot.backtest_engine import run_backtest
from trading_bot.backtest_models import BacktestBundle,CoverageStatus
from trading_bot.backtest_reporting import build_backtest_result,load_backtest_result
from test_backtest_inputs import raw_bundle,FIXTURE


def test_complete_short_window_and_incomplete_three_year_default():
    raw=raw_bundle()
    for r in raw['cost_rules']+raw['tick_rules']:
        r.update(synthetic=False,source='https://example.org/TEST-ONLY-reviewed-rule')
    b=BacktestBundle.model_validate(raw)
    result=build_backtest_result(run_backtest(b,b.calendar[5].session,b.calendar[9].session))
    assert result.run.final_coverage is CoverageStatus.COMPLETE
    default=build_backtest_result(run_backtest(b))
    assert default.run.final_coverage is CoverageStatus.INCOMPLETE
    assert 'REQUESTED_COVERAGE_MISSING' in default.run.limitations


def test_end_to_end_baseline_stress_and_output_location_independence(tmp_path):
    runner=CliRunner();ids=[]
    for parent in ['a','b']:
        f=tmp_path/parent/'result.json'
        out=runner.invoke(app,['backtest','run',str(FIXTURE),'--start','2023-01-09','--output',str(f)])
        assert out.exit_code==0,out.output
        ids.append(load_backtest_result(f).result_id)
    assert ids[0]==ids[1]
    f=tmp_path/'stress.json'
    assert runner.invoke(app,['backtest','run',str(FIXTURE),'--start','2023-01-09','--profile','stress','--output',str(f)]).exit_code==0
    stress=load_backtest_result(f);baseline=load_backtest_result(tmp_path/'a/result.json')
    assert stress.run.manifest['scenario_group']==baseline.run.manifest['scenario_group']
    assert stress.result_id!=baseline.result_id


def test_share_split_dividend_partial_expiry_and_suspended_held_review():
    raw=raw_bundle();raw['policy']['buy_cash_fraction']='0.5'
    b=BacktestBundle.model_validate(raw);r=run_backtest(b,b.calendar[5].session,b.calendar[-1].session)
    assert any(f.reason=='PARTIAL' for f in r.fills)
    assert any(e['remaining_quantity'] for e in r.expiries)
    split=next(a for a in b.corporate_actions if a.kind=='SPLIT')
    before=next(s for s in r.sessions if s.session==b.calendar[21].session)
    after=next(s for s in r.sessions if s.session==split.effective)
    old=next(h for h in before.holdings if h.ticker=='005930');new=next(h for h in after.holdings if h.ticker=='005930')
    assert new.quantity==old.quantity*2 and new.average_price==old.average_price/2
    assert any(e['kind']=='DIVIDEND' for e in r.cash_events)
    assert any(d.ticker=='000660' and d.reason=='OBSERVATION_UNAVAILABLE' for d in r.decisions)
    assert build_backtest_result(r).metrics.slippage_drag>0


def test_risk_exit_is_next_session_and_no_same_day_sale_funding():
    raw=raw_bundle();raw['policy']['initial_cash']='0';raw['policy']['initial_positions']=[{'ticker':'005930','quantity':20,'average_price':'90','known_at':'2022-01-01T00:00:00+00:00'}]
    # Valid signal creates risk SELL; subsequent opening gap up can meet sell limit.
    day=raw['calendar'][6]['session'];bar=next(b for b in raw['bars'] if b['ticker']=='005930' and b['session']==day)
    bar.update(open='108',high='110')
    b=BacktestBundle.model_validate(raw);r=run_backtest(b,b.calendar[5].session,b.calendar[9].session)
    risk=next(d for d in r.decisions if d.risk_override)
    fill=next(f for f in r.fills if f.intent_id==risk.intent_id)
    assert fill.session>risk.session and fill.quantity>0
    session=next(s for s in r.sessions if s.session==fill.session)
    assert session.pending_cash>0 and session.settled_cash==0
    assert not any(d.action=='BUY' for d in r.decisions if d.session==fill.session)
