import json
import os
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from tests.service_fixtures import TempServiceTopology, SCOPE, NoExternalCapabilities

RUNNER = CliRunner()


def configured(tmp_path):
    from trading_bot.control_store import ControlStore
    from trading_bot.service_store import ServiceJournal
    settings = TempServiceTopology(tmp_path).registration()
    ServiceJournal(settings).initialize()
    ControlStore(settings).initialize(actor='fixture-owner')
    config = tmp_path / 'registration' / 'service.json'
    config.parent.mkdir(mode=0o700)
    config.write_text(settings.model_dump_json())
    config.chmod(0o600)
    return settings, config


def invoke(config, *args):
    from trading_bot.service_cli import app
    return RUNNER.invoke(app, ['--config', str(config), *args])


def test_request_only_revision_replay_and_restriction(tmp_path):
    from trading_bot.control_store import ControlStore
    settings, config = configured(tmp_path)
    with NoExternalCapabilities() as external:
        for action, revision in [('pause',0), ('kill',1), ('resume',2)]:
            result = invoke(config, action, '--request-id', f'cli-{action}', '--expected-revision', str(revision))
            assert result.exit_code == 0, result.output
            assert 'REQUESTED' in result.output and 'pending' in result.output
        replay = invoke(config, 'resume', '--request-id', 'cli-resume', '--expected-revision', '2')
        assert replay.exit_code == 0
        assert not external.attempts
    current = ControlStore(settings).reader().effective_state()
    assert current.mode == 'KILLED' and current.applied.mode == 'PAUSED'
    assert current.acceptance_revision == 3
    assert invoke(config,'kill','--request-id','conflict','--expected-revision','0').exit_code == 1


def test_offline_status_disabled_run_and_missing_config(tmp_path):
    _, config = configured(tmp_path)
    with NoExternalCapabilities() as external, patch('trading_bot.service_cli.build_production_runtime', side_effect=AssertionError('trading')):
        assert invoke(config,'status').exit_code == 0
        assert invoke(config,'run').exit_code == 0
        assert invoke(config,'launch').exit_code == 0
        assert not external.attempts
    assert invoke(tmp_path/'missing.json','status').exit_code == 1
    values=json.loads(config.read_text()); values['password']='DO_NOT_ECHO'
    config.write_text(json.dumps(values))
    result=invoke(config,'status')
    assert result.exit_code == 1 and 'DO_NOT_ECHO' not in result.output


def test_disabled_setup_protected_distinct_initial_paused(tmp_path):
    config=tmp_path/'registration'/'service.json'
    with NoExternalCapabilities() as external:
        result=invoke(config,'setup-disabled','--root',str(tmp_path/'state'), '--account-scope-hash', SCOPE.account_scope_hash)
        assert result.exit_code == 0, result.output
        assert not external.attempts
    from trading_bot.service_config import load_service_settings
    from trading_bot.control_store import ControlStore
    settings=load_service_settings(config)
    assert not settings.service_enabled and settings.mode=='DISABLED'
    assert ControlStore(settings).reader().effective_state().mode=='PAUSED'
    assert not settings.acceptance_receipt_path.exists()
    assert config.stat().st_mode & 0o077 == 0
    assert invoke(config,'setup-disabled','--root',str(tmp_path/'state'), '--account-scope-hash', SCOPE.account_scope_hash).exit_code == 1


def test_receipt_capture_has_no_defaults_or_synthetic_authority(tmp_path):
    from tests.service_fixtures import ApprovalBundle
    _,config=configured(tmp_path)
    candidate=tmp_path/'registration'/'candidate.json'
    candidate.write_text(ApprovalBundle.synthetic().receipt.model_dump_json());candidate.chmod(0o600)
    result=invoke(config,'record-acceptance','--receipt-input',str(candidate),
        '--verified-task-1','--verified-task-2','--campaign-id','synthetic-campaign',
        '--profile-fingerprint','c'*64,'--source-id','synthetic-report')
    assert result.exit_code == 1 and not (config.parent/'acceptance.json').exists()
    assert invoke(config,'record-acceptance').exit_code != 0


def test_attention_reset_is_request_only_and_idempotent(tmp_path):
    settings,config=configured(tmp_path)
    result=invoke(config,'reset-attention','--request-id','manual-reset','--expected-revision','0')
    assert result.exit_code == 0, result.output
    from trading_bot.service_cli import attention_request_path
    request=json.loads(attention_request_path(settings).read_text())
    assert request['request_id']=='manual-reset' and request['action']=='RESET_ATTENTION'
    assert invoke(config,'reset-attention','--request-id','manual-reset','--expected-revision','0').exit_code==0
    assert invoke(config,'reset-attention','--request-id','different','--expected-revision','0').exit_code==1
    from trading_bot.service_store import ServiceJournal
    with ServiceJournal(settings).connection() as conn:
        assert conn.execute('SELECT COUNT(*) FROM service_attention_events').fetchone()[0]==0


def test_all_commands_and_entrypoint_registered():
    from trading_bot.service_cli import app
    result=RUNNER.invoke(app,['--help'])
    for command in ('setup-disabled','status','run','launch','dry-run','pause','resume','kill',
            'reset-attention','acceptance-status','record-acceptance','render-launchagents',
            'install-launchagents','start','stop','remove-launchagents'):
        assert command in result.output
    assert 'bot-service = "trading_bot.service_cli:app"' in Path('pyproject.toml').read_text()


def production_fixture(tmp_path):
    """Fake owned reads and fake normalized inquiries; never authentic approval evidence."""
    from dataclasses import replace
    from datetime import timedelta
    from types import SimpleNamespace
    from tests.test_service_composition import mock_fixture
    from tests.test_service_activation import activation_fixture
    from tests.test_phase11_cli import snapshot
    from tests.service_fixtures import NOW
    from trading_bot.service_activation import ReadOnlyAcceptanceEvidenceReader
    from trading_bot.service_composition import ServiceComposition
    from trading_bot.kis_broker import KISBroker
    from trading_bot.control_store import ControlStore
    from trading_bot.service_store import ServiceJournal
    from trading_bot import sqlite_audit
    from trading_bot.service_cli import owner_actor
    initial_evidence=activation_fixture(tmp_path)[-1]
    settings,receipt,_,safety,_,_=mock_fixture(tmp_path)
    evidence=initial_evidence.model_copy(update={'scope':settings.registered_scopes[0],
        'owner_actor':owner_actor()})
    receipt=receipt.model_copy(update={'evidence_class':'KIS_OBSERVED',
        'checkpoint_approvals':tuple(a.model_copy(update={'actor':owner_actor()}) for a in receipt.checkpoint_approvals)})
    settings.acceptance_receipt_path.write_text(receipt.model_dump_json());settings.acceptance_receipt_path.chmod(0o600)
    protected_reader=ReadOnlyAcceptanceEvidenceReader.__new__(ReadOnlyAcceptanceEvidenceReader)
    protected_reader._settings=settings
    protected_reader.read=lambda receipt:evidence
    protected_reader.read_freezes=lambda:()
    policy={'ohlcv_adjusted':True,'pykrx_request_timeout_seconds':10,'screener_max_candidates':20,
        'screener_markets':['KOSPI','KOSDAQ'],'screener_min_trading_value':1000000000,
        'screener_min_volume_ratio':1,'screener_excluded_states':['HALTED','DELISTING','ADMIN'],
        'naver_news_enabled':False,'naver_news_max_items':5,'naver_news_max_chars':2000,
        'buy_confidence_threshold':.8,'sell_confidence_threshold':.8,'buy_cash_fraction':.1,
        'max_position_value':1000000,'stop_loss_pct':.05,'take_profit_pct':.1,'daily_loss_threshold':500000}
    policy_path=settings.trading_config_path.parent/'service-policy.json'
    policy_path.write_text(json.dumps(policy));policy_path.chmod(0o600)
    trading=json.loads(settings.trading_config_path.read_text())
    trading.update(llm_provider='openai',openai_api_key='OFFLINE_NO_TRANSPORT')
    settings.trading_config_path.write_text(json.dumps(trading))
    settings.trading_journal_paths[0].parent.mkdir(exist_ok=True)
    conn=sqlite_audit.connect(settings.trading_journal_paths[0]);conn.close();settings.trading_journal_paths[0].chmod(0o600)
    ServiceJournal(settings).initialize();ControlStore(settings).initialize(actor=owner_actor())
    fresh=lambda:replace(snapshot(snapshot_id=__import__('uuid').uuid4().hex),
        account_scope_hash=receipt.scope.account_scope_hash,observed_at=NOW,
        trading_date=NOW.date(),previous_trading_date=NOW.date()-timedelta(days=3))
    def composition(settings,**kwargs):
        def broker(bindings):
            return KISBroker(order_adapter=SimpleNamespace(),account=SimpleNamespace(),
                evidence_sink=bindings.evidence_sink,submission_authority=bindings.submission_authority)
        from trading_bot.service_activation import ActivationVerdict
        from trading_bot.domain import Money
        return ServiceComposition(mode='KIS_MOCK',scope=receipt.scope,
            activation=ActivationVerdict(allowed=True,reason_codes=('ACCEPTANCE_VALIDATED',),authority='OWNED_KIS_OBSERVED'),
            authentication='OFFLINE_FAKE_OWNED_READS',prep_read_only=lambda:None,read_portfolio=lambda request:fresh(),
            read_quote=lambda ticker:SimpleNamespace(price=Money(100),observed_at=NOW),
            guarded_broker_builder=broker,read_freezes=lambda:(),close=lambda:None)
    class Calendar:
        def __init__(self,*args,**kwargs):pass
        def is_trading_day(self,day):return True
        def refresh(self,day):return True
        def previous_trading_day(self,day):return day-timedelta(days=3)
    return settings,protected_reader,composition,Calendar,NOW


@contextmanager
def production_root(tmp_path, *, advance=False, orders=()):
    from trading_bot.service_cli import build_production_runtime
    settings,reader,composition,calendar,now=production_fixture(tmp_path)
    from tests.service_fixtures import session_evidence
    settings.session_evidence_path.parent.mkdir(exist_ok=True)
    notice=session_evidence().model_copy(update={'source_id':'fixture-reviewed-session',
        'notice_id':'fixture-reviewed-notice','reviewer':'fixture-owner'})
    settings.session_evidence_path.write_text(notice.model_dump_json());settings.session_evidence_path.chmod(0o600)
    class Clock:
        value=now
        def __call__(self):
            if advance:self.value+=timedelta(microseconds=1)
            return self.value
    clock=Clock()
    def build(settings,**kwargs):
        result=composition(settings,**kwargs)
        original=result.read_portfolio
        return replace(result,read_portfolio=lambda request:replace(original(request),
            observed_at=clock(),orders=orders))
    with NoExternalCapabilities(), patch('trading_bot.service_cli.acceptance_reader',return_value=reader), \
            patch('trading_bot.service_cli.clock',side_effect=clock), \
            patch('trading_bot.service_composition.build_service_composition',side_effect=build), \
            patch('trading_bot.data_source.ObservedKRXCalendar',calendar), \
            patch('trading_bot.pykrx_adapter.PykrxOhlcvAdapter',return_value=object()):
        runtime=build_production_runtime(settings)
        try:yield runtime,reader,clock
        finally:runtime.stop();runtime.close_resources()


def test_production_safety_uses_observation_start_and_evaluation_end(tmp_path):
    with production_root(tmp_path,advance=True) as (runtime,reader,clock):
        verdict=runtime.activation_check()
        assert verdict.allowed, verdict.reason_codes
        assert runtime.start()=='RUNNING'
        original=reader.read
        reader.read=lambda receipt:original(receipt).model_copy(update={'reconciliation_unknown':1})
        assert not runtime.activation_check().allowed
        reader.read=original
        # Slow read retains its real observation age instead of backdating it.
        def stale(receipt):
            clock.value+=timedelta(seconds=11)
            return original(receipt)
        reader.read=stale
        assert not runtime.activation_check().allowed


import pytest


@dataclass
class GatedCollectionDataSource:
    ready: object
    release: object
    stages: Path
    stage: str = 'screen'
    forbidden_inodes: tuple = ()

    def __call__(self,policy,cutoff):
        from contextlib import ExitStack
        from tests.service_fixtures import NoExternalCapabilities
        # Tripwires apply before target adapters are imported in this interpreter.
        stack=ExitStack();stack.enter_context(NoExternalCapabilities())
        for target in ('trading_bot.config.Settings.__init__','trading_bot.soak_config.SoakSettings.__init__',
                'trading_bot.kis_order.KisOrderAccount.__init__','trading_bot.kis_order.KisOrderAdapter.__init__',
                'trading_bot.kis_broker.KISBroker.__init__','trading_bot.kis_auth.KisTokenManager.__init__',
                'trading_bot.kis_quote.KisQuoteAdapter.__init__','trading_bot.pykrx_adapter.PykrxOhlcvAdapter.__init__',
                'trading_bot.llm_provider.build_single_shot_llm_provider','sqlite3.connect',
                'dotenv.load_dotenv','dotenv.dotenv_values'):
            stack.enter_context(patch(target,side_effect=AssertionError('forbidden child constructor/store')))
        for fd in range(1024):
            try:info=os.fstat(fd)
            except OSError:continue
            assert (info.st_dev,info.st_ino) not in self.forbidden_inodes
        from types import SimpleNamespace
        from trading_bot.data_source import build_data_source
        from tests.test_data_source import (_available_ohlcv,_available_indicators,
            _available_quote,_available_news)
        from tests.test_screener import _row
        outer=self
        def record(stage):
            with outer.stages.open('a') as output:output.write(stage+'\n')
            if outer.stage==stage:
                outer.ready.set()
                if not outer.release.wait(10):raise RuntimeError('offline collection wait')
        # Prove constructor/store/network tripwires are live, rather than merely
        # observing that a fixture happened not to use them.
        from trading_bot.config import Settings
        import sqlite3,socket
        for prohibited in (lambda:Settings(),lambda:sqlite3.connect(':memory:'),
                lambda:socket.create_connection(('203.0.113.1',443))):
            try:prohibited()
            except (AssertionError,RuntimeError):pass
            else:raise AssertionError('missing child tripwire')
        record('GUARDS_AND_FDS_VERIFIED')
        class Bars:
            def fetch_market_rows(self,day):
                record('screen')
                row=_row('005930')
                row['health']=replace(row['health'],observed_date=day,expected_date=day)
                return (row,)
            def fetch_daily_ohlcv(self,ticker,day,**kwargs):
                record('context')
                result=_available_ohlcv()
                return replace(result,health=replace(result.health,observed_date=day,expected_date=day))
        def news(ticker):record('news');return _available_news()
        return build_data_source(policy,expected_date=cutoff.strftime('%Y%m%d'),ohlcv_adapter=Bars(),
            quote_adapter=SimpleNamespace(fetch_current_price=lambda ticker:_available_quote()),
            news_adapter=SimpleNamespace(fetch_news=news),indicator_fn=lambda frame,config:_available_indicators())


@pytest.mark.parametrize('stage',['screen','context','news'])
def test_production_actual_collection_spawn_is_fair_and_uses_captured_snapshot(tmp_path,stage):
    import multiprocessing,pickle,time
    from trading_bot.service_models import ControlRequest
    from trading_bot.service_activation import OfflineActivationAuthority
    from trading_bot.portfolio import PortfolioHolding
    from trading_bot.service_cli import owner_actor
    with production_root(tmp_path) as (runtime,reader,clock):
        # The real composition binder must be spawn-serializable without its
        # nested Settings/Inputs, SQLite connections, account or authority graph.
        pickle.dumps(runtime.daily_inputs)
        from trading_bot.service_collection import ProductionInputSource
        assert type(runtime.daily_inputs) is ProductionInputSource
        context=multiprocessing.get_context('spawn');ready=context.Event();release=context.Event()
        source=runtime.daily_inputs
        assert set(vars(source))=={'policy','quote','prompt','offline_factory','offline_authority'}
        encoded=pickle.dumps(source)
        assert b'00001234' not in encoded and b'OFFLINE_NO_TRANSPORT' not in encoded
        assert str(runtime.settings.trading_journal_paths[0]).encode() not in encoded
        source=replace(source,offline_factory=GatedCollectionDataSource(ready,release,tmp_path/'stages',stage),
            offline_authority=OfflineActivationAuthority(tmp_path))
        runtime.daily_inputs=source
        runtime.barrier=lambda name:(_ for _ in ()).throw(RuntimeError('before provider')) if name=='DISPATCH_COMMITTED' else None
        assert runtime.start()=='RUNNING'
        inodes=tuple((p.stat().st_dev,p.stat().st_ino) for p in
            (runtime.leader.lock_path,runtime.settings.trading_journal_paths[0]))
        runtime.daily_inputs=replace(runtime.daily_inputs,offline_factory=replace(runtime.daily_inputs.offline_factory,
            forbidden_inodes=inodes))
        original=runtime.work.snapshot_reader
        quantity=[7]
        runtime.work.snapshot_reader=lambda:replace(original(),holdings=(PortfolioHolding('035420',quantity[0],quantity[0],100),))
        clock.value+=timedelta(minutes=10)
        runtime.controls.request_writer(actor=owner_actor()).append_request(ControlRequest(request_id='resume-collect',
            actor=owner_actor(),requested_at=clock(),scope=runtime.controls.scope,action='RESUME',expected_revision=0))
        started=time.monotonic();runtime.tick()
        assert time.monotonic()-started<2
        assert runtime.controls.reader().effective_state().mode=='RUNNING', tuple((r['reason_code'],r['mode']) for r in runtime.controls.reader().list_applications())
        assert runtime.collection is not None, runtime.journal.list_events(runtime.job('DAILY')['job_id']) if runtime.job('DAILY') else runtime.state
        assert ready.wait(5)
        assert runtime.collection is not None and runtime.collection.process._start_method=='spawn'
        assert runtime.child is None and not runtime.work.conn.in_transaction
        assert not runtime.work.conn.execute("SELECT 1 FROM mutation_leases WHERE state!='RELEASED'").fetchone()
        quantity[0]=11
        clock.value+=timedelta(seconds=60);runtime.tick()
        assert runtime.journal.list_events(runtime.job('RISK')['job_id'])[-1]['reason_code']=='RISK_PROTECTED'
        assert runtime.collection is not None
        runtime.controls.request_writer(actor=owner_actor()).append_request(ControlRequest(request_id='pause-collect',
            actor=owner_actor(),requested_at=clock(),scope=runtime.controls.scope,action='PAUSE',expected_revision=1))
        runtime.tick()
        assert runtime.controls.reader().effective_state().mode=='PAUSED'
        release.set()
        deadline=time.monotonic()+5
        while runtime.collection is not None and time.monotonic()<deadline:
            time.sleep(.02);runtime.tick()
        assert runtime.collection is None
        saved=runtime.work.conn.execute('SELECT ticker,canonical_input,provenance_json FROM daily_evaluations ORDER BY started_at,rowid').fetchall()
        assert saved and saved[0]['ticker']=='035420'
        assert b'total_quantity: 7' in saved[0]['canonical_input']
        assert b'total_quantity: 11' not in saved[0]['canonical_input']
        assert json.loads(saved[0]['provenance_json'])==['HELD']
        assert runtime.child is None
        with runtime.journal.connection() as saved_journal:
            assert not saved_journal.execute('SELECT 1 FROM service_provider_admissions').fetchone()
        assert 'news' in (tmp_path/'stages').read_text()
        assert 'GUARDS_AND_FDS_VERIFIED' in (tmp_path/'stages').read_text()
        identity=tuple(tuple(row) for row in runtime.work.conn.execute(
            'SELECT evaluation_id,canonical_input_hash,provenance_json FROM daily_evaluations ORDER BY rowid'))
        stages=(tmp_path/'stages').read_text()
        runtime.stop()
        successor=runtime.successor()
        try:
            assert successor.start()=='RUNNING'
            successor.tick()
            assert successor.collection is None and successor.child is None
            assert successor.inputs[0].provenance==('HELD',)
            assert tuple(tuple(row) for row in successor.work.conn.execute(
                'SELECT evaluation_id,canonical_input_hash,provenance_json FROM daily_evaluations ORDER BY rowid'))==identity
            assert (tmp_path/'stages').read_text()==stages
        finally:successor.stop()


@pytest.mark.parametrize('failure',['cutoff','monotonic','stop','child_crash','before_spawn'])
def test_production_collection_expiry_and_recovery_never_recollect_first_inputs(tmp_path,failure):
    import multiprocessing
    from types import SimpleNamespace
    from trading_bot.domain import Money
    from trading_bot.service_models import ControlRequest
    from trading_bot.service_activation import OfflineActivationAuthority
    from trading_bot.service_cli import owner_actor
    with production_root(tmp_path) as (runtime,reader,clock):
        context=multiprocessing.get_context('spawn');ready=context.Event();release=context.Event()
        runtime.daily_inputs=replace(runtime.daily_inputs,
            offline_factory=GatedCollectionDataSource(ready,release,tmp_path/'stages'),
            offline_authority=OfflineActivationAuthority(tmp_path))
        runtime.trading=replace(runtime.trading,quote_reader=lambda ticker:SimpleNamespace(price=Money(68000),observed_at=clock()))
        assert runtime.start()=='RUNNING'
        clock.value+=timedelta(minutes=10)
        runtime.controls.request_writer(actor=owner_actor()).append_request(ControlRequest(request_id='resume',
            actor=owner_actor(),requested_at=clock(),scope=runtime.controls.scope,action='RESUME',expected_revision=0))
        if failure=='before_spawn':
            runtime.barrier=lambda name:(_ for _ in ()).throw(RuntimeError('crash after durable capture')) if name=='COLLECTION_COMMITTED' else None
        runtime.tick()
        marker=next(e for e in runtime.journal.list_events(runtime.job('DAILY')['job_id']) if e['reason_code']=='INPUT_COLLECTION_STARTED')
        snapshot_id=json.loads(marker['source_ids_json'])[0].split(':',1)[1]
        assert runtime.work.conn.execute('SELECT 1 FROM portfolio_snapshots WHERE snapshot_id=?',(snapshot_id,)).fetchone()
        if failure!='before_spawn':
            assert ready.wait(5)
            child=runtime.collection
            if failure=='cutoff':clock.value+=timedelta(minutes=10)
            elif failure=='monotonic':runtime.monotonic=lambda:child.deadline+1
            elif failure=='child_crash':child.process.kill();child.process.join(1)
            if failure=='stop':runtime.stop()
            else:runtime.tick()
            assert runtime.collection is None and not child.process.is_alive()
            assert not Path(child.directory.name).exists()
        runtime.barrier=lambda name:None
        runtime.stop()
        stages=(tmp_path/'stages').read_text() if (tmp_path/'stages').exists() else ''
        successor=runtime.successor()
        try:
            assert successor.start()=='RUNNING'
            successor.tick()
            assert successor.collection is None and successor.child is None
            assert successor.job('DAILY')['state']=='UNKNOWN'
            assert not successor.work.conn.execute('SELECT 1 FROM daily_evaluations').fetchone()
            assert (tmp_path/'stages').read_text()==stages if (tmp_path/'stages').exists() else stages==''
            markers=[e for e in successor.journal.list_events(successor.job('DAILY')['job_id']) if e['reason_code']=='INPUT_COLLECTION_STARTED']
            assert len(markers)==1 and markers[0]['source_ids_json']==marker['source_ids_json']
            recovered=next(e for e in successor.journal.list_events(successor.job('DAILY')['job_id']) if e['reason_code']=='INPUT_COLLECTION_PREDECESSOR_EXIT')
            assert recovered['source_ids_json']==marker['source_ids_json']
        finally:successor.stop()


@pytest.mark.parametrize('status,filled', [('OPEN',0),('PARTIAL',1),('NO_FILL',0)])
def test_production_account_work_accepts_exact_nonterminal_truth_without_clearing(tmp_path,status,filled):
    from trading_bot.portfolio import PortfolioOrder
    from trading_bot.audit_models import OrderEvent,OrderEventType,RunKind,RunStatus
    from trading_bot import sqlite_audit
    order=PortfolioOrder('known-open',None,'000660','BUY',2,filled,2-filled,0,0,100,status,'20261005','090000')
    with production_root(tmp_path,orders=(order,)) as (runtime,reader,clock):
        conn=runtime.work.conn
        sqlite_audit.start_run(conn,run_id='origin',trading_mode='mock',run_kind=RunKind.RUN,dry_run=False,
            trading_date_kst='2026-10-05')
        sqlite_audit.append_order_event(conn,OrderEvent('original-intent','origin','origin','000660',
            OrderEventType.SUBMISSION_ACCEPTED,broker_order_id='known-open',side='BUY',requested_qty=2,
            filled_qty=0,unfilled_qty=2,observed_at=clock().isoformat()))
        before=tuple(reader.read_freezes())
        assert runtime.start()=='RUNNING'
        seen=runtime.work.run(lambda lease,current,budget:(lease.state,tuple(h.ticker for h in current.holdings)))
        assert '005930' in seen[1]
        from trading_bot import soak_store
        from trading_bot.soak_models import CampaignKind
        import sqlite3
        runtime.settings.trading_journal_paths[1].parent.mkdir(exist_ok=True)
        with sqlite3.connect(runtime.settings.trading_journal_paths[1]) as soak:
            soak_store.migrate_soak_store(soak)
            soak_store.create_campaign(soak,campaign_id='retained-freeze',accepted_profile_fingerprint='profile',
                accepted_profile_version='TEST',field_contract_version='TEST',ambiguity_policy_version='TEST',
                ambiguity_window_seconds=30,ambiguity_poll_cadence_seconds=5,ambiguity_max_observations=6,
                campaign_kind=CampaignKind.PROOF_ORDER,credit_eligible=False)
            soak_store.freeze_ticker(soak,freeze_id='000660-original',campaign_id='retained-freeze',ticker='000660',
                freeze_kind='AMBIGUITY',order_intent_id='original-intent')
            original=tuple(tuple(row) for row in soak.execute('SELECT * FROM soak_ticker_freezes'))
        from trading_bot.domain import Money
        from types import SimpleNamespace
        runtime.trading=replace(runtime.trading,quote_reader=lambda ticker:SimpleNamespace(price=Money(68000),observed_at=clock()))
        runtime.work.run(lambda lease,current,budget:runtime.trading.risk(runtime,lease,current,budget))
        with sqlite3.connect(runtime.settings.trading_journal_paths[1]) as soak:
            assert tuple(soak.execute('SELECT * FROM soak_ticker_freezes'))==original
        rows=conn.execute("SELECT broker_status FROM order_events WHERE event_type='RECONCILED'").fetchall()
        assert rows and {r[0] for r in rows}=={status}
        assert tuple(reader.read_freezes())==before
        assert not conn.execute("SELECT 1 FROM mutation_leases WHERE state!='RELEASED'").fetchone()


@pytest.mark.parametrize('corruption',['unknown','missing','duplicate','quantity','wrong_subject'])
def test_production_unknown_or_contradictory_order_truth_blocks_account(tmp_path,corruption):
    from trading_bot.portfolio import PortfolioOrder
    from trading_bot.audit_models import OrderEvent,OrderEventType,RunKind
    from trading_bot import sqlite_audit
    order=PortfolioOrder('known-open',None,'000660','BUY',2,0,2,0,0,100,'OPEN','20261005','090000')
    orders=(order,)
    if corruption=='unknown':orders=(replace(order,status='UNKNOWN'),)
    if corruption=='missing':orders=()
    if corruption=='duplicate':orders=(order,order)
    if corruption=='quantity':orders=(replace(order,ordered_quantity=3,remaining_quantity=3),)
    if corruption=='wrong_subject':orders=(replace(order,ticker='005930'),)
    with production_root(tmp_path,orders=orders) as (runtime,reader,clock):
        sqlite_audit.start_run(runtime.work.conn,run_id='origin',trading_mode='mock',run_kind=RunKind.RUN,
            dry_run=False,trading_date_kst='2026-10-05')
        sqlite_audit.append_order_event(runtime.work.conn,OrderEvent('original-intent','origin','origin','000660',
            OrderEventType.SUBMISSION_ACCEPTED,broker_order_id='known-open',side='BUY',requested_qty=2,
            filled_qty=0,unfilled_qty=2,observed_at=clock().isoformat()))
        if corruption=='duplicate':
            import sqlite3
            with pytest.raises(sqlite3.IntegrityError):runtime.start()
        else:assert runtime.start()=='RECOVERY_BLOCKED'
        assert not runtime.work.conn.execute("SELECT 1 FROM order_events WHERE event_type='RECONCILED'").fetchone()


def test_real_composition_root_binds_concrete_account_and_audit(tmp_path):
    from trading_bot.service_cli import build_production_runtime
    from trading_bot.service_runtime import ServiceRuntime,AccountTradingBinding
    from trading_bot.submission_authority import OwnedActivationCheck
    from trading_bot.account_work import BoundedAccountWork
    settings,reader,composition,calendar,now=production_fixture(tmp_path)
    with NoExternalCapabilities() as external, patch('trading_bot.service_cli.acceptance_reader',return_value=reader), \
            patch('trading_bot.service_cli.clock',return_value=now), \
            patch('trading_bot.service_composition.build_service_composition',side_effect=composition), \
            patch('trading_bot.data_source.ObservedKRXCalendar',calendar), \
            patch('trading_bot.pykrx_adapter.PykrxOhlcvAdapter',return_value=object()):
        runtime=build_production_runtime(settings)
        assert type(runtime) is ServiceRuntime and type(runtime.trading) is AccountTradingBinding
        assert type(runtime.work) is BoundedAccountWork and type(runtime.activation_check) is OwnedActivationCheck
        try:
            assert runtime.start()=='RUNNING'
            broker=runtime.work.run(lambda lease,current,budget:runtime.trading._broker(runtime,lease,current,budget))
            assert broker._submission_authority.unattended
            assert type(broker._submission_authority.activation_check) is OwnedActivationCheck
            assert runtime.work.conn.execute('SELECT COUNT(*) FROM portfolio_snapshots').fetchone()[0]>=4
            assert runtime.work.conn.execute('SELECT COUNT(*) FROM runs WHERE status=?',('COMPLETED',)).fetchone()[0]>=2
            assert not external.attempts
        finally: runtime.stop();runtime.close_resources()


def test_enabled_missing_real_receipt_denies_before_trading_construction(tmp_path):
    from trading_bot.service_cli import build_production_runtime
    settings,_=configured(tmp_path)
    settings=settings.model_copy(update={'service_enabled':True,'mode':'KIS_MOCK'})
    with NoExternalCapabilities() as external, patch('trading_bot.service_composition.load_mock_trading_settings',side_effect=AssertionError('credentials')):
        import pytest
        with pytest.raises((ValueError,OSError)): build_production_runtime(settings)
        assert not external.attempts


def test_dry_run_frozen_replay_separate_temp_output(tmp_path):
    _,config=configured(tmp_path)
    from tests.test_replay import FIXTURES
    result=invoke(config,'dry-run','--fixture',str(FIXTURES/'focused.json'),
        '--output-root',str(tmp_path/'replay-output'))
    assert result.exit_code==0,result.output
    assert json.loads((tmp_path/'replay-output'/'replay-result.json').read_text())['outcomes']
    assert invoke(config,'dry-run','--fixture',str(FIXTURES/'focused.json'),
        '--output-root',str(config.parent)).exit_code==1


def test_receipt_capture_shared_saved_checks_do_not_grant_activation(tmp_path):
    from trading_bot.service_activation import validate_receipt_capture,load_acceptance_receipt
    settings,reader,_,_,now=production_fixture(tmp_path)
    receipt=load_acceptance_receipt(settings.acceptance_receipt_path)
    disabled=settings.model_copy(update={'mode':'DISABLED','service_enabled':False})
    reader._settings=disabled
    verdict=validate_receipt_capture(disabled,receipt,reader,now=now)
    assert verdict.allowed and verdict.authority=='DENIED'
    saved=reader.read(receipt)
    reader.read=lambda receipt:saved.model_copy(update={'source_hashes':tuple(
        h.model_copy(update={'source_hash':'f'*64}) for h in saved.source_hashes)})
    verdict=validate_receipt_capture(disabled,receipt,reader,now=now)
    assert not verdict.allowed and 'SOURCE_IDENTITY_MISMATCH' in verdict.reason_codes
