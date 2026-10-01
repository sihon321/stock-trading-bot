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


def test_partial_run_resume_and_intentional_retry_handlers(monkeypatch,tmp_path):
    from trading_bot import shadow_cli
    from trading_bot.shadow_runner import run_shadow,resume_shadow,request_shadow_retry
    from trading_bot.shadow_models import ShadowManifest,ShadowLimits
    from test_shadow_runner import Fake
    args,path=prepare_args(tmp_path);runner=CliRunner();assert runner.invoke(app,args).exit_code==0
    m=load_shadow_manifest(path);m=ShadowManifest.model_validate({**m.model_dump(),'limits':{**m.limits.model_dump(),'max_attempts':1},'spec_id':''});path.write_text(canonical_json(m))
    monkeypatch.setattr(shadow_cli,'run_shadow',lambda m,j:run_shadow(m,j,provider_factory=lambda v,p:Fake([],status='MALFORMED')))
    monkeypatch.setattr(shadow_cli,'resume_shadow',lambda m,j:resume_shadow(m,j,provider_factory=lambda v,p:Fake([])))
    monkeypatch.setattr(shadow_cli,'request_shadow_retry',lambda m,j,a:request_shadow_retry(m,j,a,provider_factory=lambda v,p:Fake([])))
    journal=tmp_path/'s.sqlite';output=tmp_path/'partial.json'
    r=runner.invoke(app,['shadow','run',str(path),'--journal',str(journal),'--output',str(output)])
    assert r.exit_code==1 and output.exists(),r.output
    from trading_bot.shadow_reporting import load_shadow_result
    saved=load_shadow_result(output);attempt=saved.observations[0].attempt_id
    for mode,extra in [('resume',[]),('retry',['--attempt',attempt])]:
        out=tmp_path/(mode+'.json')
        r=runner.invoke(app,['shadow',mode,str(path),'--journal',str(journal),'--output',str(out),*extra])
        assert r.exit_code==1 and out.exists(),r.output
        assert load_shadow_result(out).observations[0]==saved.observations[0]


def test_foreign_journal_and_live_write_tripwires(monkeypatch,tmp_path):
    from trading_bot import shadow_cli,sqlite_audit,soak_store,portfolio_store
    from trading_bot.shadow_runner import run_shadow
    from test_shadow_runner import Fake
    import sqlite3
    def forbidden(*a,**k):pytest.fail('live store write forbidden')
    monkeypatch.setattr(sqlite_audit,'connect',forbidden)
    monkeypatch.setattr(soak_store,'connect_soak_store',forbidden)
    monkeypatch.setattr(portfolio_store,'migrate_portfolio',forbidden)
    args,path=prepare_args(tmp_path);runner=CliRunner();assert runner.invoke(app,args).exit_code==0
    calls=[];monkeypatch.setattr(shadow_cli,'run_shadow',lambda m,j:run_shadow(m,j,provider_factory=lambda v,p:Fake(calls)))
    foreign=tmp_path/'audit.sqlite';c=sqlite3.connect(foreign);c.execute('CREATE TABLE runs (id TEXT)');c.close();before=foreign.read_bytes()
    r=runner.invoke(app,['shadow','run',str(path),'--journal',str(foreign),'--output',str(tmp_path/'result.json')])
    assert r.exit_code==2 and calls==[] and before==foreign.read_bytes()


def test_installed_bot_offline_prepare_and_report(tmp_path):
    import os,subprocess
    root=Path(__file__).resolve().parents[1];executable=root/'.python-userbase/bin/bot'
    if not executable.exists():pytest.skip('installed bot console script required for packaging smoke')
    env={k:v for k,v in os.environ.items() if not any(s in k for s in ('KIS','API_KEY','AUTH_TOKEN'))}
    env['PYTHONUSERBASE']=str(root/'.python-userbase')
    args,path=prepare_args(tmp_path)
    p=subprocess.run([str(executable),*args],cwd=tmp_path,env=env,text=True,capture_output=True,timeout=30)
    assert p.returncode==0,p.stdout+p.stderr
    saved=result(tmp_path);evidence=tmp_path/'result.json';evidence.write_text(canonical_json(saved));out=tmp_path/'report.md'
    p=subprocess.run([str(executable),'report','shadow',str(evidence),'--output',str(out)],cwd=tmp_path,env=env,text=True,capture_output=True,timeout=30)
    assert p.returncode==0 and out.read_text()==p.stdout,p.stdout+p.stderr
