import json
from pathlib import Path
import pytest
from typer.testing import CliRunner
from trading_bot.cli import app
from trading_bot.report_cli import report_app
from trading_bot.shadow_models import canonical_json,load_shadow_manifest
from test_shadow_models import variant,pricing
from test_backtest_inputs import FIXTURE
from test_shadow_reporting import result


def prepare_args(tmp_path):
    v=tmp_path/'variants.json';p=tmp_path/'pricing.json';out=tmp_path/'manifest.json'
    v.write_text(canonical_json([variant().model_dump(mode="json")]));p.write_text(canonical_json([pricing().model_dump(mode="json")]))
    return ['shadow','prepare',str(FIXTURE),'--variants',str(v),'--pricing',str(p),'--start','2023-01-09','--sample-limit','3','--output',str(out)],out


def test_prepare_and_standalone_report_have_no_live_capabilities(monkeypatch,tmp_path):
    import trading_bot.cli as cli
    import trading_bot.shadow_providers as providers
    import httpx
    import dotenv
    def forbidden(*a,**k):pytest.fail('live capability forbidden')
    for name in ('Settings','build_kis_broker','build_llm_provider','acquire_mutation_lease','run_intraday_watch','connect_soak_store'):
        monkeypatch.setattr(cli,name,forbidden)
    monkeypatch.setattr(httpx.Client,'request',forbidden);monkeypatch.setattr(dotenv,'load_dotenv',forbidden)
    monkeypatch.setattr(providers.ShadowCredentials,'load',forbidden)
    args,path=prepare_args(tmp_path);runner=CliRunner()
    first=runner.invoke(app,args);assert first.exit_code==0,first.output
    assert runner.invoke(app,args).exit_code==0
    assert len(load_shadow_manifest(path).snapshots)==3
    r=result(tmp_path);evidence=tmp_path/'result.json';evidence.write_text(canonical_json(r))
    out=tmp_path/'report.md';read=runner.invoke(report_app,['shadow',str(evidence),'--output',str(out)])
    assert read.exit_code==0,read.output
    assert read.output==out.read_text() and '수동 결정' in read.output


def test_mocked_paid_run_and_partial_exit_preserve_artifacts(monkeypatch,tmp_path):
    from trading_bot import shadow_cli
    from trading_bot.shadow_runner import run_shadow
    from test_shadow_runner import Fake
    args,path=prepare_args(tmp_path);runner=CliRunner();assert runner.invoke(app,args).exit_code==0
    called=[]
    def fake(m,j):
        called.append('run');return run_shadow(m,j,provider_factory=lambda v,p:Fake([]))
    monkeypatch.setattr(shadow_cli,'run_shadow',fake)
    output=tmp_path/'result.json';j=tmp_path/'run.sqlite'
    run=runner.invoke(app,['shadow','run',str(path),'--journal',str(j),'--output',str(output)])
    assert run.exit_code==0,run.output
    assert called==['run'] and output.exists()
    conflict=runner.invoke(app,['shadow','run',str(path),'--output',str(output)])
    assert conflict.exit_code==2 and called==['run']


def test_invalid_and_unsupported_preflight_have_zero_calls(tmp_path):
    args,path=prepare_args(tmp_path);runner=CliRunner();assert runner.invoke(app,args).exit_code==0
    run=runner.invoke(app,['shadow','run',str(path),'--journal',str(tmp_path/'s.sqlite')])
    assert run.exit_code==2 and 'UNREVIEWED' in run.output
    bad=tmp_path/'bad.json';bad.write_text('{"secret":"NEVER_PRINT"}')
    run=runner.invoke(app,['shadow','run',str(bad)])
    assert run.exit_code==2 and 'NEVER_PRINT' not in run.output
    for args in (['shadow','--help'],['report','shadow','--help']):
        assert runner.invoke(app,args).exit_code==0
