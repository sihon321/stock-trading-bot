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
    settings,config=configured(tmp_path,clock=lambda:NOW)
    from trading_bot.alert_config import ObserverSettings
    from trading_bot.web_config import ResourceDescriptor
    observer=ObserverSettings(operational_db_path=tmp_path/'observer'/'observer.db',
        expectation_service_config_path=config,registered_resources=tuple(ResourceDescriptor(
            id=owner,path=path,owner=owner,account_hash=settings.registered_scopes[0].account_scope_hash,target='mock')
            for owner,path in [('service',settings.service_db_path),('control',settings.control_db_path)]))
    with NoExternalCapabilities() as external,patch('trading_bot.service_store.ServiceJournal',side_effect=AssertionError('general journal')):
        from tests.service_fixtures import FakeOwnerLoginProbe
        producer=build_expectation_producer(observer,service_config=config,clock=lambda:NOW,
            login_probe=FakeOwnerLoginProbe(clock=lambda:NOW))
        assert producer.writer.__slots__==('__journal',)
        before=settings.control_db_path.read_bytes()
        records=producer.publish()
        assert len(records)==3 and all(r.state=='UNKNOWN' for r in records)
        assert settings.control_db_path.read_bytes()==before and not external.attempts


def test_actual_runtime_tick_crash_retains_unexpected_generation_and_budget(tmp_path):
    from trading_bot.service_launchd import launch_worker
    from trading_bot.service_store import ServiceJournal
    from tests.test_service_recovery import runtime_fixture
    clock=FakeServiceClock()
    initial,*_=runtime_fixture(tmp_path,clock=clock)
    settings=initial.settings;count=[]
    def factory(settings):
        runtime=initial.successor()
        runtime.tick=lambda:(_ for _ in ()).throw(RuntimeError('OFFLINE_TICK_CRASH'))
        count.append(runtime)
        return runtime
    for _ in range(4):
        with pytest.raises(RuntimeError,match='OFFLINE_TICK_CRASH'):
            launch_worker(settings,runtime_factory=factory,clock=clock,offline_authority=initial.offline_authority)
        clock.advance(10)
    assert launch_worker(settings,runtime_factory=factory,clock=clock,offline_authority=initial.offline_authority)=='MANUAL_ATTENTION'
    assert len(count)==4
    with ServiceJournal(settings).connection() as conn:
        generations=conn.execute("SELECT state,stopped_at FROM service_generations WHERE state='UNEXPECTED_EXIT'").fetchall()
        assert len(generations)==4 and all(g['state']=='UNEXPECTED_EXIT' and g['stopped_at'] is None for g in generations)
        assert conn.execute('SELECT COUNT(*) FROM service_restart_attempts').fetchone()[0]==3


def test_narrow_expectation_writer_denies_all_other_table_writes(tmp_path):
    import sqlite3
    from trading_bot.service_store import expectation_writer_from_settings
    settings,_=configured(tmp_path)
    writer=expectation_writer_from_settings(settings,clock=lambda:NOW)
    owner=writer._ExpectationWriter__journal
    with owner.connection() as conn:
        with pytest.raises(sqlite3.DatabaseError):conn.execute('DELETE FROM service_jobs')
        with pytest.raises(sqlite3.DatabaseError):conn.execute("INSERT INTO service_attention_events(state,reason_code,observed_at) VALUES('RESET','FAKE',0)")
        with pytest.raises(sqlite3.DatabaseError):conn.execute('CREATE TABLE arbitrary(value TEXT)')
    assert not hasattr(writer,'initialize') and not hasattr(writer,'reserve_restart')


def test_observer_cli_explicit_expectation_config_status_never_probes(tmp_path):
    from typer.testing import CliRunner
    from trading_bot.alert_cli import app
    settings,config=configured(tmp_path)
    observer=tmp_path/'registration'/'observer.json'
    observer.write_text(json.dumps({'operational_db_path':str(tmp_path/'observer'/'operations.db'),
        'expectation_service_config_path':str(config),'registered_resources':[
            {'id':owner,'owner':owner,'path':str(path),'account_hash':settings.registered_scopes[0].account_scope_hash,'target':'mock'}
            for owner,path in [('service',settings.service_db_path),('control',settings.control_db_path)]]}));observer.chmod(0o600)
    with patch('trading_bot.alert_cli.build_expectation_producer',side_effect=AssertionError('status probe')):
        result=CliRunner().invoke(app,['--config',str(observer),'--expectation-service-config',str(config),'status'])
    assert result.exit_code==0,result.output


def test_attention_reset_requires_elapsed_window_and_fresh_owned_recovery(tmp_path):
    from dataclasses import replace
    from tests.test_service_cli import production_fixture
    from trading_bot.service_cli import build_production_runtime,attention_request_path,attention_history_path
    from trading_bot.service_launchd import _consume_attention_request
    from trading_bot.service_store import ServiceJournal
    from trading_bot.control_store import ControlStore
    settings,reader,composition,calendar,now=production_fixture(tmp_path)
    clock=FakeServiceClock(now);journal=ServiceJournal(settings,clock=clock)
    for number in range(3): assert journal.reserve_restart(f'restart-{number}',reason='UNEXPECTED_EXIT')
    assert not journal.reserve_restart('denied',reason='UNEXPECTED_EXIT')
    config=tmp_path/'registration'/'service.json';config.parent.mkdir(mode=0o700)
    config.write_text(settings.model_dump_json());config.chmod(0o600)
    calls=[]
    def fresh_composition(settings,**kwargs):
        built=composition(settings,**kwargs);original=built.read_portfolio
        return replace(built,read_portfolio=lambda request:replace(original(request),observed_at=clock()))
    def factory(settings):
        calls.append('fresh-recovery');return build_production_runtime(settings)
    with NoExternalCapabilities() as external,patch('trading_bot.service_cli.clock',clock), \
            patch('trading_bot.service_cli.acceptance_reader',return_value=reader), \
            patch('trading_bot.service_composition.build_service_composition',side_effect=fresh_composition), \
            patch('trading_bot.data_source.ObservedKRXCalendar',calendar), \
            patch('trading_bot.pykrx_adapter.PykrxOhlcvAdapter',return_value=object()):
        result=invoke(config,'reset-attention','--request-id','explicit-reset','--expected-revision','0')
        assert result.exit_code==0,result.output
        clock.advance(599)
        assert not _consume_attention_request(settings,journal,factory,clock=clock) and not calls
        clock.advance(2)
        assert _consume_attention_request(settings,journal,factory,clock=clock)
        assert len(calls)==1 and not external.attempts
        assert not attention_request_path(settings).exists()
        assert attention_history_path(settings,'explicit-reset').exists()
        # Same consumed ID cannot enqueue another reset in a subsequent episode.
        replay=invoke(config,'reset-attention','--request-id','explicit-reset','--expected-revision','0')
        assert replay.exit_code==0 and not attention_request_path(settings).exists()
        assert ControlStore(settings).reader().effective_state().mode=='PAUSED'
        with journal.connection() as conn:
            assert conn.execute('SELECT state FROM service_attention_events ORDER BY event_id DESC LIMIT 1').fetchone()[0]=='RESET'
            assert conn.execute('SELECT COUNT(*) FROM service_restart_attempts').fetchone()[0]==3


def test_reset_validation_failure_exits_clean_without_restart_loop(tmp_path):
    from trading_bot.service_launchd import launch_worker
    from trading_bot.service_cli import attention_request_path
    settings,_=configured(tmp_path)
    settings=settings.model_copy(update={'mode':'KIS_MOCK','service_enabled':True})
    attention_request_path(settings).write_text('{"malformed":"untrusted"}');attention_request_path(settings).chmod(0o600)
    assert launch_worker(settings,runtime_factory=lambda _:pytest.fail('unapproved reset'))=='MANUAL_ATTENTION'
    assert launch_worker(settings,runtime_factory=lambda _:pytest.fail('unapproved reset'))=='MANUAL_ATTENTION'


def test_registered_observer_produces_midnight_without_trading_or_general_writes(tmp_path):
    from trading_bot.alert_cli import build_expectation_producer
    from trading_bot.alert_config import ObserverSettings
    from trading_bot.web_config import ResourceDescriptor
    from trading_bot.service_store import ServiceJournal
    from tests.service_fixtures import FakeOwnerLoginProbe
    from datetime import datetime,timezone
    settings,config=configured(tmp_path)
    observer=ObserverSettings(operational_db_path=tmp_path/'observer'/'observer.db',
        expectation_service_config_path=config,registered_resources=tuple(ResourceDescriptor(
            id=owner,path=path,owner=owner,account_hash=settings.registered_scopes[0].account_scope_hash,target='mock')
            for owner,path in [('service',settings.service_db_path),('control',settings.control_db_path)]))
    clock=FakeServiceClock(datetime(2026,10,5,14,59,tzinfo=timezone.utc))
    journal=ServiceJournal(settings)
    def general_rows():
        with journal.connection() as conn:
            return {table:tuple(tuple(r) for r in conn.execute(f'SELECT * FROM {table}')) for table in
                ('service_generations','service_jobs','service_restart_attempts','service_attention_events','service_provider_admissions')}
    before=general_rows();control_before=settings.control_db_path.read_bytes()
    with NoExternalCapabilities() as external,patch('trading_bot.service_store.ServiceJournal',side_effect=AssertionError('general journal')):
        producer=build_expectation_producer(observer,service_config=config,clock=clock,
            login_probe=FakeOwnerLoginProbe(clock=clock))
        first=producer.publish();clock.advance(120);second=producer.publish()
        assert first[0].trading_date_kst!=second[0].trading_date_kst and not external.attempts
    assert general_rows()==before and settings.control_db_path.read_bytes()==control_before
    with journal.connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM service_expectations').fetchone()[0]==6
        assert conn.execute('SELECT COUNT(*) FROM service_expectation_health').fetchone()[0]>=2


def test_observer_factory_survives_missing_active_trading_sources(tmp_path):
    from trading_bot.alert_cli import build_expectation_producer
    from trading_bot.alert_config import ObserverSettings
    from tests.service_fixtures import FakeOwnerLoginProbe
    settings,config=configured(tmp_path,clock=lambda:NOW)
    active=settings.model_copy(update={'service_enabled':True,'mode':'KIS_MOCK'})
    config.write_text(active.model_dump_json())
    settings.trading_config_path.unlink()
    observer=ObserverSettings(operational_db_path=tmp_path/'observer'/'operations.db',
        expectation_service_config_path=config,registered_resources=[
            {'id':owner,'owner':owner,'path':path,'account_hash':settings.registered_scopes[0].account_scope_hash,'target':'mock'}
            for owner,path in [('service',settings.service_db_path),('control',settings.control_db_path)]])
    with NoExternalCapabilities() as external:
        producer=build_expectation_producer(observer,service_config=config,clock=lambda:NOW,
            login_probe=FakeOwnerLoginProbe(clock=lambda:NOW))
        assert len(producer.publish())==3 and not external.attempts


def test_future_control_truth_stays_unknown_while_observer_outbox_keeps_progressing(tmp_path):
    from trading_bot.alert_cli import build_expectation_producer
    from trading_bot.alert_config import ObserverSettings
    from trading_bot.alert_observer import AlertObserver
    from trading_bot.web_models import AlertSourceBatch
    from tests.service_fixtures import FakeOwnerLoginProbe
    from tests.test_alert_detector import record
    from tests.test_alert_observer import Transport
    import sqlite3

    clock=FakeServiceClock()
    future=NOW+timedelta(hours=2)
    settings,config=configured(tmp_path,clock=lambda:future)
    observer=ObserverSettings(operational_db_path=tmp_path/'observer'/'alerts.db',
        expectation_service_config_path=config,registered_resources=[
            {'id':owner,'owner':owner,'path':path,'account_hash':settings.registered_scopes[0].account_scope_hash,'target':'mock'}
            for owner,path in [('service',settings.service_db_path),('control',settings.control_db_path)]])
    with NoExternalCapabilities() as external:
        producer=build_expectation_producer(observer,service_config=config,clock=clock,
            login_probe=FakeOwnerLoginProbe(clock=clock))
        before=settings.control_db_path.read_bytes()
        assert producer.controls.effective_state().applied.applied_at==future
        records=producer.publish()
        assert len(records)==3 and all(r.state=='UNKNOWN' for r in records)
        bot=AlertObserver(observer,clock=clock,notifier=Transport(),expectation_producer=producer)
        bot.start()
        incident=bot.store.observe(bot.detector.detect(AlertSourceBatch(clock(),(record('orders',
            ticker='000660',order_intent_id='original-unknown'),)))[0])
        try:
            bot._scan(clock())
            clock.advance(1800)
            bot._scan(clock())
            assert sum('UNRESOLVED_ORDER' in text for text in bot.notifier.sent)==2
            assert bot.store.get_incident(incident.episode_id).active
            assert producer.controls.effective_state().applied.applied_at==future
            assert settings.control_db_path.read_bytes()==before
            with sqlite3.connect(settings.service_db_path) as conn:
                health=conn.execute("SELECT source_id,state,reason_code FROM service_expectation_health WHERE source_kind='CONTROL'").fetchall()
            assert health and all(row==('control-owner-setup','UNKNOWN','CONTROL_UNKNOWN') for row in health)
            assert not external.attempts
        finally:
            bot.stop()
