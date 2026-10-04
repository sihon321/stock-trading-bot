from datetime import timedelta
import json
import os
from pathlib import Path
import plistlib
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from tests.service_fixtures import FakeServiceClock, NOW, NoExternalCapabilities
from tests.test_service_cli import configured,invoke


def test_plists_fixed_independent_labels_absolute_paths_and_zero_os(tmp_path):
    from trading_bot.service_launchd import render_launchagents
    settings,config=configured(tmp_path)
    with NoExternalCapabilities() as external:
        rendered=render_launchagents(settings,config_path=config)
        assert not external.attempts
    assert set(rendered)=={'com.stock-trading-bot.service','com.stock-trading-bot.alerts'}
    for label,payload in rendered.items():
        value=plistlib.loads(payload)
        assert value['Label']==label and value['RunAtLoad']
        assert value['KeepAlive']=={'SuccessfulExit':False}
        assert value['ThrottleInterval']==10 and value['ExitTimeOut']==30
        assert Path(value['ProgramArguments'][0]).is_absolute()
        assert Path(value['WorkingDirectory']).is_absolute()
        assert Path(value['StandardErrorPath']).is_absolute()
        assert 'EnvironmentVariables' not in value
        assert value['ProgramArguments'][1]=='-m'
    observer=plistlib.loads(rendered['com.stock-trading-bot.alerts'])['ProgramArguments']
    assert observer[2]=='trading_bot.alert_cli' and '--expectation-service-config' in observer
    assert 'launch' not in observer and 'watch' in observer


def test_durable_restart_admission_counts_factory_crash_before_work(tmp_path):
    from trading_bot.service_launchd import launch_worker
    from trading_bot.service_store import ServiceJournal
    settings,_=configured(tmp_path)
    from trading_bot.service_activation import OfflineActivationAuthority
    offline=OfflineActivationAuthority(tmp_path)
    clock=FakeServiceClock(); calls=[]
    def crash(settings):
        calls.append('factory');raise RuntimeError('OFFLINE_FACTORY_CRASH')
    for attempt in range(4):
        with pytest.raises(RuntimeError): launch_worker(settings,runtime_factory=crash,clock=clock,offline_authority=offline)
        clock.advance(10)
    assert launch_worker(settings,runtime_factory=crash,clock=clock,offline_authority=offline)=='MANUAL_ATTENTION'
    assert len(calls)==4
    with ServiceJournal(settings).connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM service_restart_attempts').fetchone()[0]==3
        assert conn.execute('SELECT state FROM service_attention_events ORDER BY event_id DESC LIMIT 1').fetchone()[0]=='MANUAL_ATTENTION'
    clock.advance(601)
    assert launch_worker(settings,runtime_factory=crash,clock=clock,offline_authority=offline)=='MANUAL_ATTENTION'
    assert len(calls)==4


def test_clock_reversal_and_disabled_no_construction(tmp_path):
    from trading_bot.service_launchd import launch_worker
    settings,_=configured(tmp_path);clock=FakeServiceClock()
    from trading_bot.service_activation import OfflineActivationAuthority
    offline=OfflineActivationAuthority(tmp_path)
    with NoExternalCapabilities() as external:
        assert launch_worker(settings,runtime_factory=lambda _:pytest.fail('disabled worker'))=='DISABLED'
        assert not external.attempts
    def crash(_):raise RuntimeError('CRASH')
    with pytest.raises(RuntimeError):launch_worker(settings,runtime_factory=crash,clock=clock,offline_authority=offline)
    clock.advance(-1,monotonic_seconds=0)
    assert launch_worker(settings,runtime_factory=lambda _:pytest.fail('rollback worker'),clock=clock,offline_authority=offline)=='MANUAL_ATTENTION'


class FakeLaunchctl:
    def __init__(self):self.calls=[];self.installed={}
    def __call__(self,args,**kwargs):
        self.calls.append((args,kwargs))
        command=args[1]
        if command=='print':
            if args[2].startswith('gui/') and args[2].count('/')==1:
                return SimpleNamespace(returncode=0,stdout=f'{args[2]} = {{ type = Login; session = 123; user = {os.getuid()}; }}',stderr='')
            value=self.installed.get(args[2])
            return SimpleNamespace(returncode=0 if value else 113,stdout=value or '',stderr='')
        if command=='bootstrap':
            value=plistlib.loads(Path(args[3]).read_bytes())
            self.installed[f'{args[2]}/{value["Label"]}']=f'path = {args[3]}\n'
        elif command=='bootout':self.installed.pop(args[2],None)
        return SimpleNamespace(returncode=0,stdout='',stderr='')


def test_explicit_lifecycle_collision_refusal_and_preserved_stores(tmp_path):
    from trading_bot.service_launchd import lifecycle_command
    settings,config=configured(tmp_path);agents=tmp_path/'LaunchAgents';agents.mkdir(mode=0o700)
    fake=FakeLaunchctl();before=settings.control_db_path.read_bytes()
    assert lifecycle_command(settings,config_path=config,command='render',agents_dir=agents,runner=fake)
    assert not fake.calls and not list(agents.iterdir())
    lifecycle_command(settings,config_path=config,command='install',agents_dir=agents,runner=fake)
    assert len(fake.installed)==2
    lifecycle_command(settings,config_path=config,command='start',agents_dir=agents,runner=fake)
    assert all('-k' not in args for args,_ in fake.calls)
    lifecycle_command(settings,config_path=config,command='stop',agents_dir=agents,runner=fake)
    lifecycle_command(settings,config_path=config,command='remove',agents_dir=agents,runner=fake)
    assert settings.control_db_path.read_bytes()==before and config.exists()
    assert not list(agents.iterdir())
    collision=agents/'com.stock-trading-bot.service.plist';collision.write_bytes(b'unrelated');collision.chmod(0o600)
    with pytest.raises(ValueError):lifecycle_command(settings,config_path=config,command='install',agents_dir=agents,runner=fake)
    assert collision.read_bytes()==b'unrelated'


def test_owner_gui_probe_requires_explicit_registration_and_unknown_failure(tmp_path):
    from trading_bot.service_launchd import gui_login_probe
    settings,config=configured(tmp_path);fake=FakeLaunchctl()
    probe=gui_login_probe(config,clock=lambda:NOW,runner=fake)
    assert not fake.calls
    assert probe.observe_owner_gui().state=='CONFIRMED'
    args,kwargs=fake.calls[0]
    assert args==['/bin/launchctl','print',f'gui/{os.getuid()}'] and kwargs['timeout']==1
    failed=lambda *a,**k:SimpleNamespace(returncode=113,stdout='',stderr='')
    assert gui_login_probe(config,clock=lambda:NOW,runner=failed).observe_owner_gui().state=='UNKNOWN'


def test_narrow_observer_factory_never_constructs_general_service_or_trading(tmp_path):
    from trading_bot.alert_cli import build_expectation_producer
    settings,config=configured(tmp_path)
    from trading_bot.alert_config import ObserverSettings
    from trading_bot.web_config import ResourceDescriptor
    observer=ObserverSettings(operational_db_path=tmp_path/'observer'/'observer.db',
        expectation_service_config_path=config,registered_resources=tuple(ResourceDescriptor(
            id=owner,path=path,owner=owner,account_hash=settings.registered_scopes[0].account_scope_hash,target='mock')
            for owner,path in [('service',settings.service_db_path),('control',settings.control_db_path)]))
    with NoExternalCapabilities() as external,patch('trading_bot.service_store.ServiceJournal',side_effect=AssertionError('general journal')):
        producer=build_expectation_producer(observer,service_config=config,clock=lambda:NOW,
            login_probe=SimpleNamespace(observe_owner_gui=lambda:__import__('tests.service_fixtures',fromlist=['']).owner_login_evidence()))
        assert producer.writer.__slots__==('__journal',)
        before=settings.control_db_path.read_bytes()
        records=producer.publish()
        assert len(records)==3 and all(r.state=='UNKNOWN' for r in records)
        assert settings.control_db_path.read_bytes()==before and not external.attempts
