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
