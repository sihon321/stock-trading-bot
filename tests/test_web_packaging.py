"""Offline wheel installation, without editable checkout import fallbacks."""
from pathlib import Path
import json
import os
import shutil
import site
import subprocess
import sys


def installed_wheel_probe(tmp_path):
    checkout=Path(__file__).resolve().parents[1]
    source=tmp_path/'build-source'
    source.mkdir()
    shutil.copytree(checkout/'trading_bot',source/'trading_bot',ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copy2(checkout/'pyproject.toml',source/'pyproject.toml')
    (source/'.planning').mkdir()
    shutil.copy2(checkout/'.planning/PROJECT.md',source/'.planning/PROJECT.md')
    output=tmp_path/'wheels'
    target=tmp_path/'installed'
    roots=[str(Path(p).resolve()) for p in [*site.getsitepackages(),site.getusersitepackages()]
        if Path(p).is_dir()]
    env={k:v for k,v in os.environ.items() if not any(s in k.upper() for s in ('KIS','OPENAI','ANTHROPIC','DISCORD','BOT_WEB','BOT_ALERTS'))}
    env.update(PIP_NO_INDEX='1',PIP_DISABLE_PIP_VERSION_CHECK='1',PYTHONDONTWRITEBYTECODE='1')
    pip_script="""import json,sys
sys.path.extend(json.loads(sys.argv[1]))
def audit(event,args):
    if event.startswith('socket.'):
        raise AssertionError('packaging attempted network access: '+event)
sys.addaudithook(audit)
from pip._internal.cli.main import main
raise SystemExit(main(sys.argv[2:]))
"""
    def pip(args):
        result=subprocess.run([sys.executable,'-I','-S','-c',pip_script,json.dumps(roots),*args],
            cwd=source,env=env,capture_output=True,text=True,timeout=45)
        assert result.returncode==0,result.stdout+'\n'+result.stderr
    pip(['wheel','--no-index','--no-deps','--no-build-isolation','.', '--wheel-dir',str(output)])
    wheels=list(output.glob('*.whl'))
    assert len(wheels)==1
    pip(['install','--no-index','--no-deps','--target',str(target),str(wheels[0])])
    manifest=sorted(str(p.relative_to(checkout/'trading_bot')) for root in ('templates','static')
        for p in (checkout/'trading_bot'/root).rglob('*') if p.is_file())
    payload=dict(target=str(target),roots=roots,checkout=str(checkout),manifest=manifest,runtime=str(tmp_path/'runtime'))
    child=subprocess.run([sys.executable,'-I','-S','-c',INSTALLED,json.dumps(payload)],cwd=tmp_path,
        env=env,capture_output=True,text=True,timeout=30)
    assert child.returncode==0,child.stdout+'\n'+child.stderr
    return json.loads(child.stdout)


INSTALLED=r'''
import json,sys,os,importlib.abc,importlib.metadata,platform
from pathlib import Path
payload=json.loads(sys.argv[1])
sys.path[:0]=[payload['target'],*payload['roots']]
assert not any(Path(p).resolve()==Path(payload['checkout']) for p in sys.path if p)
network_calls=0
def audit(event,args):
    global network_calls
    if event.startswith('socket.'):
        network_calls+=1
        raise AssertionError('installed runtime attempted network')
    if event=='open' and isinstance(args[0],str) and Path(args[0]).name=='.env':
        raise AssertionError('installed runtime read dotenv')
sys.addaudithook(audit)
class Deny(importlib.abc.MetaPathFinder):
    def find_spec(self,name,path=None,target=None):
        prefixes=('trading_bot.cli','trading_bot.config','trading_bot.runtime','trading_bot.kis_',
            'trading_bot.llm_provider','trading_bot.portfolio_store','trading_bot.mutation_lease',
            'trading_bot.soak_store','trading_bot.sqlite_audit','trading_bot.backtest_engine',
            'trading_bot.shadow_runner','trading_bot.shadow_inputs','anthropic','openai','pykis')
        if any(name==p or name.startswith(p+'.') or (p.endswith('_') and name.startswith(p)) for p in prefixes):
            raise AssertionError('installed forbidden import: '+name)
sys.meta_path.insert(0,Deny())
import trading_bot
assert Path(trading_bot.__file__).is_relative_to(payload['target'])
resources=Path(trading_bot.__file__).parent
for relative in payload['manifest']:
    assert (resources/relative).is_file(),relative
distribution=next(d for d in importlib.metadata.distributions(path=[payload['target']])
    if d.metadata['Name']=='stock-trading-bot')
entries={e.name:e for e in distribution.entry_points if e.group=='console_scripts'}
assert entries['bot-web'].value=='trading_bot.web_cli:app'
assert entries['bot-alerts'].value=='trading_bot.alert_cli:app'
from typer.testing import CliRunner
runner=CliRunner()
for name in ('bot-web','bot-alerts'):
    reply=runner.invoke(entries[name].load(),['--help'])
    assert reply.exit_code==0,reply.exception
root=Path(payload['runtime']);root.mkdir(mode=0o700)
config=root/'config';config.mkdir(mode=0o700)
web=config/'web.json'
web.write_text(json.dumps(dict(operational_db_path=str(root/'operations'/'operator.db'),
    artifact_root=str(root/'artifacts'),registered_resources=[])))
web.chmod(0o600)
reply=runner.invoke(entries['bot-web'].load(),['setup','--config',str(web),'--username','owner'],
    input='synthetic-password\nsynthetic-password\n')
assert reply.exit_code==0,reply.output
alerts=config/'alerts.json'
alerts.write_text(json.dumps(dict(operational_db_path=str(root/'operations'/'operator.db'),registered_resources=[])))
alerts.chmod(0o600)
reply=runner.invoke(entries['bot-alerts'].load(),['--config',str(alerts),'status'])
assert reply.exit_code==0 and 'NOT_STARTED' in reply.output
from trading_bot.web_cli import load_settings
from trading_bot.web_app import create_app
from trading_bot.web_evidence import OperatorEvidenceService
from trading_bot.web_reports import SavedReportService
from trading_bot.web_store import WebStore
from trading_bot.alert_store import AlertStore
from datetime import datetime,timezone
clock=lambda:datetime(2026,10,2,1,tzinfo=timezone.utc)
settings=load_settings(web)
store=WebStore(settings)
incidents=AlertStore(settings.operational_db_path,clock=clock);incidents.initialize()
app=create_app(settings,evidence_service=OperatorEvidenceService(settings,clock=clock),
    report_service=SavedReportService(settings,store=store,clock=clock),alert_store=incidents,clock=clock)
client=app.test_client()
token=app.extensions['web_auth'].authenticate('owner','synthetic-password','127.0.0.1')
assert token
with client.session_transaction() as session:session['operator_token']=token
for path in ('/','/reports','/alerts','/validation/replay','/static/operator.css','/static/operator.js'):
    response=client.get(path)
    assert response.status_code==200,(path,response.status_code)
    assert response.data
for template in app.jinja_env.list_templates():
    assert template.startswith('operator/')
    app.jinja_env.get_template(template)
print(json.dumps(dict(python=platform.python_version(),resource_count=len(payload['manifest']),
    help_commands=['bot-web','bot-alerts'],rendered=True,source_checkout_absent=True,network_calls=network_calls)))
'''


def test_phase14_runbook_matches_local_private_and_observer_contract():
    text=Path('docs/operator-runbook.md').read_text()
    for required in ('## Phase 14 운영자 웹과 독립 알림 관찰','bot-web setup --config',
        'bot-web reset-password --config','bot-web serve --config','bot-alerts --config',
        'trusted_proxies','allowed_origin','UNKNOWN','SIGINT','SIGTERM','StrEnum','3.14.3',
        'mobile data','source_observed_at','query_at','30분','수식','phase14_web_metadata'):
        assert required in text,required


def test_offline_installed_wheel_has_native_resources_independent_entrypoints_and_render(tmp_path):
    proof=installed_wheel_probe(tmp_path)
    assert proof['python']==sys.version.split()[0]
    assert proof['resource_count']>=10
    assert proof['help_commands']==['bot-web','bot-alerts']
    assert proof['rendered'] and proof['source_checkout_absent'] and proof['network_calls']==0
