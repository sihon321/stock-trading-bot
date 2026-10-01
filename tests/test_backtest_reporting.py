import json
import pytest
from trading_bot.backtest_reporting import build_backtest_result,load_backtest_result,write_backtest_result
from trading_bot.backtest_models import BacktestInputError,content_hash
from test_backtest_engine import run


def test_roundtrip_reconciles_and_writes_idempotently(tmp_path):
    result=build_backtest_result(run());f=tmp_path/'evidence.json'
    assert write_backtest_result(result,f)==f
    assert load_backtest_result(f)==result
    write_backtest_result(result,f)
    assert not list(tmp_path.glob('.backtest-*'))

@pytest.mark.parametrize('change',[
    lambda x:x['metrics'].update(commission='0'),
    lambda x:x['run']['manifest']['profile'].update(secret='sensitive'),
    lambda x:x['run']['sessions'][0].update(settled_cash='999'),
    lambda x:x.update(schema_version=2),
    lambda x:x['run']['fills'][0].update(quantity=99999),
])
def test_tampered_or_forged_evidence_rejected(change,tmp_path):
    raw=build_backtest_result(run()).model_dump(mode='json');change(raw)
    raw['result_id']=content_hash({k:v for k,v in raw.items() if k!='result_id'})
    f=tmp_path/'tampered.json';f.write_text(json.dumps(raw))
    with pytest.raises(BacktestInputError):load_backtest_result(f)


def test_conflict_and_symlink_never_overwrite(tmp_path):
    r=build_backtest_result(run());f=tmp_path/'existing';f.write_text('preserve')
    with pytest.raises(BacktestInputError):write_backtest_result(r,f)
    assert f.read_text()=='preserve'
    symlink=tmp_path/'link';symlink.symlink_to(f)
    with pytest.raises(BacktestInputError):write_backtest_result(r,symlink)

from decimal import Decimal as D
from trading_bot.backtest_reporting import calculate_metrics,render_backtest_report


def test_korean_report_has_metrics_unknown_benchmark_and_limitations():
    result=build_backtest_result(run());text=render_backtest_report(result)
    for label in ['모의 계산','순수익률','최대 낙폭','일별 자산','거래세','자료 부족','실거래 승인','불완전']:
        assert label in text
    assert text.endswith('\n') and '\r' not in text
    assert text==render_backtest_report(result)


def test_hand_calculated_metrics_and_same_path_cost_drag():
    r=run();m=calculate_metrics(r)
    assert m.net_return==r.sessions[-1].net_equity/r.initial_equity-1
    assert m.gross_return-m.net_return==(m.commission+m.sell_tax+m.surtax+m.slippage_drag)/r.initial_equity
    equity=[s.net_equity for s in r.sessions]
    assert m.turnover==sum((f.quantity*f.executed_price for f in r.fills),D('0'))/(sum(equity)/len(equity))


def test_unknown_valuation_invalidates_return_and_drawdown():
    r=run();first=r.sessions[0].model_copy(update={'net_equity':None,'gross_equity':None})
    metrics=calculate_metrics(r.model_copy(update={'sessions':(first,*r.sessions[1:])}))
    assert metrics.net_return is None and metrics.max_drawdown is None and metrics.exposure[0] is None


def test_rehashed_false_initial_equity_is_rejected(tmp_path):
    raw=build_backtest_result(run()).model_dump(mode='json');raw['run']['initial_equity']='20000'
    raw['result_id']=content_hash({k:v for k,v in raw.items() if k!='result_id'})
    f=tmp_path/'forged.json';f.write_text(json.dumps(raw))
    with pytest.raises(BacktestInputError,match='INVALID_INITIAL_EQUITY'):load_backtest_result(f)


def test_zero_terminal_equity_reports_total_loss_not_unknown():
    r=run();last=r.sessions[-1].model_copy(update={'net_equity':D('0'),'gross_equity':D('0'),'holdings':()})
    m=calculate_metrics(r.model_copy(update={'sessions':(*r.sessions[:-1],last)}))
    assert m.net_return==D('-1') and m.max_drawdown==D('1')
    assert m.exposure[-1] is None


def test_report_output_uses_atomic_conflict_safe_publish(tmp_path):
    from trading_bot.backtest_reporting import write_backtest_report
    path=tmp_path/'report.txt'
    write_backtest_report('모의 결과\r\n',path)
    write_backtest_report('모의 결과\n',path)
    with pytest.raises(BacktestInputError):write_backtest_report('다른 결과\n',path)
    assert path.read_bytes()=='모의 결과\n'.encode()


def test_frozen_same_period_benchmark_and_future_benchmark_rejection(tmp_path):
    from trading_bot.backtest_models import BenchmarkPoint
    r=run();points=tuple(BenchmarkPoint(session=s.session,known_at=next(c.close_at for c in r.calendar if c.session==s.session),close=D(100+i)) for i,s in enumerate(r.sessions))
    r=r.model_copy(update={'benchmark':points})
    result=build_backtest_result(r)
    assert result.metrics.benchmark_return==points[-1].close/points[0].close-1
    raw=result.model_dump(mode='json');raw['run']['benchmark'][0]['known_at']='2030-01-01T00:00:00+00:00'
    f=tmp_path/'future.json';f.write_text(json.dumps(raw))
    with pytest.raises(BacktestInputError,match='INVALID_BENCHMARK_AVAILABILITY'):load_backtest_result(f)
