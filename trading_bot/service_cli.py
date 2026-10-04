"""Explicit owner-local service CLI; read/request paths have no trading authority."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile

import typer

from .control_store import control_request_capabilities
from .service_config import ServiceSettings, load_service_settings, protected_file
from .service_models import ControlRequest, InstallationScope, ServiceScope
from .web_config import ControlResourceDescriptor, checked_path, overlaps

app = typer.Typer(no_args_is_help=True, help='소유자 서비스 설정·요청·감독')
SAFE_ERROR = '서비스 설정 또는 저장 증거를 확인하세요. 실행 권한은 부여되지 않았습니다.'


def clock():
    return datetime.now(timezone.utc)


def owner_actor():
    return f'local-owner-uid-{os.getuid()}'


def private_write(path, payload):
    """Exclusive atomic publication, durable bytes; never replace existing evidence."""
    path = checked_path(path)
    from .service_store import private_directory
    private_directory(path.parent)
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()
    if path.exists():
        protected_file(path)
        if path.read_bytes() == data:
            return
        raise ValueError('existing owner evidence conflict')
    fd, temporary = tempfile.mkstemp(prefix='.pending-', dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, 'wb') as file:
            file.write(data); file.flush(); os.fsync(file.fileno())
        os.link(temporary, path, follow_symlinks=False)
        directory = os.open(path.parent, os.O_RDONLY)
        try: os.fsync(directory)
        finally: os.close(directory)
    finally:
        Path(temporary).unlink(missing_ok=True)


def request_ports(settings):
    descriptor = ControlResourceDescriptor(resource_id='installation-control',
        path=settings.control_db_path, lock_dir=settings.lock_dir,
        registered_scopes=tuple((s.account_scope_hash,s.execution_target) for s in settings.registered_scopes))
    return control_request_capabilities(descriptor, actor=owner_actor(), clock=clock)


def attention_request_path(settings):
    return checked_path(settings.control_db_path).parent / 'attention-reset.json'


def attention_history_path(settings,request_id):
    return attention_request_path(settings).parent/'attention-reset-history'/f'{hashlib.sha256(request_id.encode()).hexdigest()}.json'


@app.callback()
def root(ctx: typer.Context, config: Path = typer.Option(..., '--config')):
    ctx.obj = config


def guarded(function):
    try: return function()
    except (ValueError, OSError, UnicodeError, sqlite3.Error, RuntimeError):
        typer.echo(SAFE_ERROR, err=True)
        raise typer.Exit(1) from None


@app.command('setup-disabled')
def setup_disabled(ctx: typer.Context, root: Path = typer.Option(...,'--root'),
                   account_scope_hash: str = typer.Option(...,'--account-scope-hash')):
    def setup():
        config=checked_path(ctx.obj); state=checked_path(root)
        if config.exists() or state.exists() or overlaps(config.parent,state):
            raise ValueError('fresh separate installation paths required')
        scope=ServiceScope(account_scope_hash=account_scope_hash,execution_target='mock')
        settings=ServiceSettings(registered_scopes=(scope,),
            trading_config_path=config.parent/'trading.json',acceptance_receipt_path=config.parent/'acceptance.json',
            session_evidence_path=config.parent/'sessions.json',observer_config_path=config.parent/'observer.json',
            service_db_path=state/'journal'/'service.db',control_db_path=state/'control'/'control.db',
            lock_dir=state/'locks',trading_journal_paths=tuple(state/'evidence'/name for name in
                ('audit.db','soak.db','soak-controller.db')),artifact_roots=(state/'artifacts',))
        from .service_store import ServiceJournal, private_directory
        from .control_store import ControlStore
        private_directory(state)
        ServiceJournal(settings).initialize();ControlStore(settings).initialize(actor=owner_actor())
        private_write(config,settings.model_dump(mode='json'))
        observer={'operational_db_path':str(state/'observer'/'operator.db'),
            'expectation_service_config_path':str(config),'registered_resources':[
                {'id':kind,'path':str(path),'owner':kind,'account_hash':account_scope_hash,'target':'mock'}
                for kind,path in [('service',settings.service_db_path),('control',settings.control_db_path)]]}
        private_write(settings.observer_config_path,observer)
        typer.echo('DISABLED / PAUSED: receipt absent; observer stores initialize only on explicit observation')
    guarded(setup)


@app.command()
def status(ctx: typer.Context):
    def read():
        settings=load_service_settings(ctx.obj);reader,_=request_ports(settings)
        current=reader.effective_state()
        typer.echo(json.dumps({'mode':settings.mode,'enabled':settings.service_enabled,
            'effective':current.mode,'applied':current.applied.mode,'accepted_revision':current.acceptance_revision,
            'receipt_present':settings.acceptance_receipt_path.exists(),
            'reset_requested':attention_request_path(settings).exists()},sort_keys=True))
    guarded(read)


def submit(ctx,action,request_id,expected_revision):
    def request():
        settings=load_service_settings(ctx.obj);reader,writer=request_ports(settings)
        previous=reader.get_request(request_id)
        timestamp=previous.requested_at if previous else clock()
        value=ControlRequest(request_id=request_id,actor=owner_actor(),requested_at=timestamp,
            scope=InstallationScope(registered_scopes=settings.registered_scopes),action=action,
            expected_revision=expected_revision)
        result=writer.append_request(value)
        typer.echo(json.dumps(asdict(result)|{'application':'pending'},sort_keys=True))
        if result.status!='REQUESTED': raise typer.Exit(1)
    guarded(request)


@app.command()
def pause(ctx: typer.Context, request_id: str=typer.Option(...,'--request-id'),expected_revision:int=typer.Option(...,'--expected-revision',min=0)):
    submit(ctx,'PAUSE',request_id,expected_revision)


@app.command()
def resume(ctx: typer.Context, request_id: str=typer.Option(...,'--request-id'),expected_revision:int=typer.Option(...,'--expected-revision',min=0)):
    submit(ctx,'RESUME',request_id,expected_revision)


@app.command()
def kill(ctx: typer.Context, request_id: str=typer.Option(...,'--request-id'),expected_revision:int=typer.Option(...,'--expected-revision',min=0)):
    submit(ctx,'KILL',request_id,expected_revision)


@app.command('reset-attention')
def reset_attention(ctx: typer.Context, request_id: str=typer.Option(...,'--request-id'),expected_revision:int=typer.Option(...,'--expected-revision',min=0)):
    def request():
        settings=load_service_settings(ctx.obj);reader,_=request_ports(settings)
        if reader.effective_state().acceptance_revision!=expected_revision: raise ValueError('revision conflict')
        path=attention_request_path(settings)
        from .service_activation import _protected_json
        history=attention_history_path(settings,request_id)
        if history.exists() and not path.exists():
            saved=_protected_json(history,65536)
            if (saved['request_id']!=request_id or saved['expected_revision']!=expected_revision
                    or saved['actor']!=owner_actor() or saved['scope']!=InstallationScope(
                        registered_scopes=settings.registered_scopes).model_dump(mode='json')):
                raise ValueError('reset replay conflict')
            typer.echo('RECORDED: previous explicit reset request retained; no new reset');return
        prior=_protected_json(path,65536) if path.exists() else None
        # Validate shared identity and bounded scope using the same request contract.
        value=ControlRequest(request_id=request_id,actor=owner_actor(),requested_at=
            prior['requested_at'] if prior else clock(),scope=InstallationScope(registered_scopes=settings.registered_scopes),
            action='PAUSE',expected_revision=expected_revision).model_dump(mode='json')
        private_write(path,value|{'action':'RESET_ATTENTION','schema_version':1})
        typer.echo('REQUESTED: reset pending; controls and history retained')
    guarded(request)


def acceptance_reader(settings):
    from .service_activation import ReadOnlyAcceptanceEvidenceReader
    return ReadOnlyAcceptanceEvidenceReader(settings,
        profile_path=settings.trading_config_path.parent/'accepted-profile.json',owner_actor=owner_actor())


@app.command('acceptance-status')
def acceptance_status(ctx: typer.Context):
    def read():
        settings=load_service_settings(ctx.obj)
        from .service_activation import load_acceptance_receipt
        if not settings.acceptance_receipt_path.exists():
            typer.echo('ACCEPTANCE_RECEIPT_MISSING: no activation authority');return
        receipt=load_acceptance_receipt(settings.acceptance_receipt_path)
        from .service_activation import validate_receipt_capture
        verdict=validate_receipt_capture(settings,receipt,acceptance_reader(settings),now=clock())
        typer.echo(verdict.model_dump_json())
    guarded(read)


@app.command('record-acceptance')
def record_acceptance(ctx:typer.Context,receipt_input:Path=typer.Option(...,'--receipt-input'),
    verified_task_1:bool=typer.Option(False,'--verified-task-1'),verified_task_2:bool=typer.Option(False,'--verified-task-2'),
    campaign_id:str=typer.Option(...,'--campaign-id'),profile_fingerprint:str=typer.Option(...,'--profile-fingerprint'),
    source_id:list[str]=typer.Option(...,'--source-id')):
    def capture():
        settings=load_service_settings(ctx.obj)
        from .service_activation import load_acceptance_receipt, validate_receipt_capture
        receipt=load_acceptance_receipt(receipt_input)
        if (not verified_task_1 or not verified_task_2 or receipt.evidence_class!='KIS_OBSERVED'
                or receipt.campaign_id!=campaign_id or receipt.profile_fingerprint!=profile_fingerprint
                or set(source_id)!={s.source_id for s in receipt.source_hashes}
                or any(a.actor!=owner_actor() for a in receipt.checkpoint_approvals)):
            raise ValueError('explicit authentic checkpoint transport required')
        verdict=validate_receipt_capture(settings,receipt,acceptance_reader(settings),now=clock())
        if not verdict.allowed: raise ValueError('saved acceptance not verified')
        private_write(settings.acceptance_receipt_path,receipt.model_dump(mode='json'))
        if load_acceptance_receipt(settings.acceptance_receipt_path)!=receipt: raise ValueError('receipt readback failed')
        typer.echo('RECORDED: mode, controls and freezes retained; activation still requires fresh recovery')
    guarded(capture)


@app.command('dry-run')
def dry_run(ctx:typer.Context,fixture:Path=typer.Option(...,'--fixture'),output_root:Path=typer.Option(...,'--output-root')):
    def preview():
        settings=load_service_settings(ctx.obj)
        from .service_activation import OfflineActivationAuthority
        output=checked_path(output_root)
        if not output.exists(): output.mkdir(mode=0o700)
        OfflineActivationAuthority(output)
        if any(overlaps(output,checked_path(p).parent) for p in (*settings.trading_journal_paths,
                settings.service_db_path,settings.control_db_path,ctx.obj)): raise ValueError('separate temporary output required')
        from .replay import load_replay_bundle, run_replay_scenarios
        bundle=load_replay_bundle(fixture)
        result=run_replay_scenarios(bundle)
        from .replay_evidence import canonical_json_bytes
        private_write(output/'replay-result.json',{'outcomes':[json.loads(canonical_json_bytes(r)) for r in result]})
        private_write(output/'service-result.json',offline_service_proof(output,bundle))
        typer.echo('OFFLINE_ONLY: frozen replay and temporary service recovery complete')
    guarded(preview)


def offline_service_proof(output, bundle):
    """Actual service reducers with frozen inputs; stop before any provider admission.

    Registration paths are rebuilt under the owned temporary root. No receipt,
    credentials, source journal or policy from the installed registration is read.
    The consumed-dispatch interruption is intentional offline fault evidence.
    """
    from datetime import timedelta
    import time
    from .account_work import BoundedAccountWork
    from .control_runtime import ResumeSafetyEvidence
    from .control_store import ControlStore
    from .market_cycle import MarketCyclePolicy
    from .mutation_lease import acquire_mutation_lease
    from .portfolio import PortfolioSnapshot, PortfolioCompleteness, PortfolioAccountSummary
    from .portfolio_store import connect_portfolio_store
    from .service_activation import ActivationVerdict, OfflineActivationAuthority
    from .service_composition import ServiceComposition
    from .service_models import DailyDispatchEnvelope, KST, SourceHash, SessionEvidence
    from .service_runtime import ServiceRuntime, DailyInput, ProviderChildFactory, ProviderSettings
    from .service_store import ServiceJournal
    from .trade_signal import TradeSignal

    if not bundle or not bundle[0].steps:
        raise ValueError('frozen nonempty service inputs required')
    scope=ServiceScope(account_scope_hash=hashlib.sha256(b'OFFLINE_ONLY').hexdigest(),execution_target='mock')
    day=datetime.strptime(bundle[0].trading_date,'%Y%m%d').date()
    wall=[datetime(day.year,day.month,day.day,8,50,tzinfo=KST)]
    now=lambda:wall[0]
    root=output/'service-proof'
    root.mkdir(mode=0o700)  # exclusive: never reuse previous temporary authority
    for name in ('unused-trading','unused-session','unused-observer','absent-receipt'):
        private_write(root/'config'/f'{name}.json',{'evidence_class':'SYNTHETIC','authority':'OFFLINE_ONLY'})
    settings=ServiceSettings(service_enabled=True,mode='KIS_MOCK',registered_scopes=(scope,),
        trading_config_path=root/'config'/'unused-trading.json',acceptance_receipt_path=root/'config'/'absent-receipt.json',
        session_evidence_path=root/'config'/'unused-session.json',observer_config_path=root/'config'/'unused-observer.json',
        service_db_path=root/'journal'/'service.db',control_db_path=root/'control'/'control.db',lock_dir=root/'locks',
        trading_journal_paths=(root/'account'/'audit.db',root/'evidence'/'soak.db',root/'evidence'/'controller.db'),
        artifact_roots=(root/'artifacts',))
    authority=OfflineActivationAuthority(root)
    journal=ServiceJournal(settings,clock=now);journal.initialize()
    controls=ControlStore(settings,clock=now);controls.initialize(actor='offline-owner')
    conn=connect_portfolio_store(settings.trading_journal_paths[0])
    observations=[]
    def snapshot():
        observations.append(now())
        return PortfolioSnapshot(snapshot_id=f'offline-{len(observations)}',account_scope_hash=scope.account_scope_hash,
            trading_date=day,previous_trading_date=day-timedelta(days=1),observed_at=now(),
            completeness=PortfolioCompleteness.COMPLETE,reason_code='SYNTHETIC',daily_page_count=1,balance_page_count=1,
            holdings=(),orders=(),fills=(),account=PortfolioAccountSummary(bundle[0].initial_cash,bundle[0].initial_cash))
    work=BoundedAccountWork(conn=conn,account_scope_hash=scope.account_scope_hash,clock=now,
        lease_factory=lambda:acquire_mutation_lease(conn,account_scope_hash=scope.account_scope_hash,
            lock_dir=root/'account-locks',command='offline-service',cycle_id='offline-pass',observed_at=now()),
        snapshot_reader=snapshot,terminalize_prior=lambda:True,reconcile_snapshot=lambda current:{'determinate':True},
        terminalize=lambda:None,persist_unresolved=lambda:None)
    session=SessionEvidence(trading_date_kst=day,source_id='offline-frozen-session',source_hash='a'*64,
        source_url='https://kind.krx.co.kr/offline',notice_id='offline',reviewer='offline',reviewed_at=now(),
        observed_at=now(),effective_at=now(),eligibility='ELIGIBLE',
        continuous_open=wall[0].replace(hour=9,minute=0),continuous_close=wall[0].replace(hour=15,minute=30))
    class Sessions:
        def for_date(self,date):
            if date!=day: raise ValueError('no inferred future session')
            return session
    class Calendar:
        def is_trading_day(self,date):return date==day
        def previous_trading_day(self,date):return day-timedelta(days=1)
    class Inputs:
        def collect(self,date,held):
            values=[]
            for ticker in dict.fromkeys(s.ticker for s in bundle[0].steps):
                payload=json.dumps({'evidence_class':'SYNTHETIC','scenario':bundle[0].scenario_id,'ticker':ticker,
                    'raw_signals':[s.raw_signal for s in bundle[0].steps if s.ticker==ticker]},sort_keys=True).encode()
                envelope=DailyDispatchEnvelope(prompt_bytes=payload,prompt_hash=hashlib.sha256(payload).hexdigest(),
                    system_prompt='OFFLINE_ONLY frozen input',schema_hash=hashlib.sha256(json.dumps(
                        TradeSignal.model_json_schema(),sort_keys=True,separators=(',',':')).encode()).hexdigest(),
                    provider='openai',model='offline-unused',temperature=0.,prompt_version='offline-v1')
                values.append(DailyInput(ticker,('SCREENED',),envelope))
            return tuple(values)
    def safety(scope,stamp):
        return ResumeSafetyEvidence(scope=scope,observed_at=stamp,expires_at=stamp+timedelta(seconds=10),
            broker_complete=True,evidence_complete=True,calendar_confirmed=True,authority_current=True,
            safety_latched=False,frozen_subjects=(),source_hashes=tuple(SourceHash(source_id=f'offline-{i}',
                source_hash=str(i)*64) for i in range(4)))
    def interrupt(name):
        if name=='DISPATCH_COMMITTED':raise RuntimeError('OFFLINE_CONSUMED_DISPATCH_CRASH')
    runtime=ServiceRuntime(settings=settings,journal=journal,controls=controls,account_work=work,
        composition=ServiceComposition(mode='KIS_MOCK',activation=ActivationVerdict(allowed=True,
            reason_codes=('SYNTHETIC',),authority='OFFLINE_ONLY'),authentication='SYNTHETIC',
            runtime_wired=True,scope=scope,prep_read_only=lambda:None),
        policy=MarketCyclePolicy(Calendar(),session_evidence_provider=Sessions()),daily_inputs=Inputs(),
        provider_factory=ProviderChildFactory(ProviderSettings(llm_provider='openai'),offline_authority=authority),
        clock=now,monotonic=time.monotonic,offline_authority=authority,barrier=interrupt,
        validate_resume=safety,current_resume_safety=safety)
    states=[]
    try:
        controls.request_writer(actor='offline-owner').append_request(ControlRequest(request_id='offline-resume',
            actor='offline-owner',requested_at=now(),scope=controls.scope,action='RESUME',expected_revision=0))
        runtime.start()
        for hour,minute in ((8,50),(9,0),(9,10)):
            wall[0]=wall[0].replace(hour=hour,minute=minute);runtime.tick();states.append(runtime.state)
        jobs=[runtime.job(kind)['job_id'] for kind in ('PREP','DAILY','RISK')]
        runtime.stop();wall[0]=wall[0].replace(hour=9,minute=20)
        runtime=runtime.successor();runtime.barrier=lambda name:None;runtime.start();runtime.tick()
        assert jobs==[runtime.job(kind)['job_id'] for kind in ('PREP','DAILY','RISK')]
        dispatch=conn.execute('SELECT dispatch_state FROM daily_evaluation_dispatches WHERE dispatched_at IS NOT NULL').fetchone()
        for hour,minute in ((15,20),(15,30)):
            wall[0]=wall[0].replace(hour=hour,minute=minute);runtime.tick();states.append(runtime.state)
        runtime.stop()
        return {'evidence_class':'SYNTHETIC','authority':'OFFLINE_ONLY','provider_calls':0,'broker_calls':0,
            'runtime_states':states,'stable_job_ids':jobs,'recovered_dispatch_state':dispatch[0],
            'evaluation_ids':[r[0] for r in conn.execute('SELECT evaluation_id FROM daily_evaluations')],
            'account_leases_released':not conn.execute("SELECT 1 FROM mutation_leases WHERE state!='RELEASED'").fetchone()}
    finally:
        runtime.stop();conn.close()


def build_production_runtime(settings):
    """Installed concrete root, lazily imported only after explicit enabled mock admission."""
    return _build_production_runtime(settings)


def _build_production_runtime(settings):
    """Concrete primary audit, fresh account exclusion, mock broker and owned receipt root."""
    from datetime import timedelta
    from types import SimpleNamespace
    import uuid
    from pydantic import Field
    from .service_models import ServiceContract, KST
    from .service_activation import (_protected_json,load_acceptance_receipt,CurrentActivationSafety,
        validate_receipt_capture)
    from .service_composition import build_service_composition,load_mock_trading_settings,PortfolioReadRequest,BrokerGuardBindings
    from .service_runtime import ServiceRuntime,AccountTradingBinding,ProviderChildFactory,ProviderSettings
    from .service_store import ServiceJournal
    from .control_store import ControlStore
    from .market_cycle import MarketCyclePolicy
    from .session_evidence import SessionEvidenceProvider
    from .submission_authority import SubmissionAuthority,OwnedActivationCheck
    from .account_work import BoundedAccountWork
    from .mutation_lease import acquire_mutation_lease
    from .portfolio_store import migrate_portfolio,record_transition_state
    from .audit_models import OrderEvent,OrderEventType,RunStatus,RunKind,TransitionObservation,OperationalSeverity
    from . import sqlite_audit
    from .execution import ExecutionConfig
    from .risk import RiskConfig,DailyLossState
    from .data_source import ObservedKRXCalendar
    from .pykrx_adapter import PykrxOhlcvAdapter
    from .config import LLMProviderName
    from .llm_provider import signal_schema_hash
    from .prompts import SYSTEM_PROMPT,PROMPT_VERSION

    class Policy(ServiceContract):
        model_config=ServiceContract.model_config|{'strict':True}
        ohlcv_adjusted: bool
        pykrx_request_timeout_seconds: float=Field(gt=0,le=15)
        screener_max_candidates: int=Field(ge=1,le=20)
        screener_markets: tuple[str,...]
        screener_min_trading_value: float=Field(gt=0)
        screener_min_volume_ratio: float=Field(gt=0)
        screener_excluded_states: tuple[str,...]
        naver_news_enabled: bool
        naver_news_max_items: int=Field(ge=1,le=5)
        naver_news_max_chars: int=Field(ge=1,le=2000)
        buy_confidence_threshold: float=Field(ge=.8,le=1)
        sell_confidence_threshold: float=Field(ge=.8,le=1)
        buy_cash_fraction: float=Field(gt=0,le=1)
        max_position_value: float=Field(gt=0)
        stop_loss_pct: float=Field(gt=0,lt=1)
        take_profit_pct: float=Field(gt=0,lt=1)
        daily_loss_threshold: float=Field(gt=0)

    if not settings.service_enabled or settings.mode!='KIS_MOCK' or len(settings.registered_scopes)!=1:
        raise ValueError('one explicit protected mock account required')
    receipt=load_acceptance_receipt(settings.acceptance_receipt_path)
    reader=acceptance_reader(settings)
    capture=validate_receipt_capture(settings,receipt,reader,now=clock())
    if not capture.allowed: raise RuntimeError('AUTHENTIC_ACCEPTANCE_REQUIRED')

    def observe_safety(scope,now):
        observed=now; evidence=reader.read(load_acceptance_receipt(settings.acceptance_receipt_path))
        return CurrentActivationSafety(scope=evidence.scope,observed_at=observed,
            expires_at=observed+timedelta(seconds=10),healthy=(evidence.scope==scope
                and evidence.state=='COMPLETED' and not evidence.cross_store_unknown
                and not evidence.reconciliation_unknown and not evidence.reconciliation_incomplete),
            safety_latched=evidence.safety_latched, frozen_tickers=reader.read_freezes(),source_hashes=evidence.source_hashes[:3])

    from .service_activation import ObservedSafetyReader
    safety=ObservedSafetyReader(observe_safety,clock)

    policy_values=Policy.model_validate_json(json.dumps(_protected_json(settings.trading_config_path.parent/'service-policy.json',65536)))
    trading=load_mock_trading_settings(settings.trading_config_path)
    # Current Codex CLI has no verified single-shot implementation: deny before clients/DBs.
    if trading.llm_provider is LLMProviderName.CODEX_CLI:
        raise RuntimeError('PROVIDER_SINGLE_SHOT_UNVERIFIED')
    provider_settings=ProviderSettings(llm_provider=trading.llm_provider,api_key=trading.active_llm_api_key,
        anthropic_auth_token=trading.anthropic_auth_token,anthropic_model=trading.anthropic_model,
        anthropic_temperature=trading.anthropic_temperature,openai_model=trading.openai_model,
        openai_temperature=trading.openai_temperature)
    sessions=SessionEvidenceProvider(settings.session_evidence_path,clock)
    ohlcv=PykrxOhlcvAdapter(adjusted=policy_values.ohlcv_adjusted,
        request_timeout_seconds=policy_values.pykrx_request_timeout_seconds)
    policy=MarketCyclePolicy(ObservedKRXCalendar(ohlcv,current_date=lambda:clock().astimezone(KST).date()),
        session_evidence_provider=sessions)
    composition=build_service_composition(settings,receipt=receipt,saved_evidence_reader=reader,
        current_safety=safety,clock=clock,policy=policy)
    if not composition.activation.allowed: raise RuntimeError('CURRENT_ACTIVATION_BLOCKED')
    conn=None
    try:
        # Production entry owns only the primary writer; it never migrates soak/controller.
        primary=protected_file(settings.trading_journal_paths[0])
        conn=sqlite_audit.connect(primary);conn.row_factory=sqlite3.Row;migrate_portfolio(conn)
        controls=ControlStore(settings,clock=clock);journal=ServiceJournal(settings,clock=clock)
        scope=receipt.scope; active=[None]; latest_snapshot=[None]

        def unresolved():
            rows=conn.execute('SELECT * FROM order_events ORDER BY id').fetchall()
            latest={}
            for row in rows: latest[row['order_intent_id']]=dict(row)
            return tuple(r for r in latest.values() if r['event_type'] in
                ('SUBMISSION_ATTEMPTED','SUBMISSION_ACCEPTED','SUBMISSION_AMBIGUOUS')
                or r['event_type']=='RECONCILED' and r['broker_status'] not in
                    ('FILLED','CANCELLED','EXPIRED','REJECTED'))

        def snapshot_reader(*_):
            now=clock(); day=now.astimezone(KST).date(); cutoff=policy.completed_bar_cutoff(day)
            if not cutoff.available: raise RuntimeError('COMPLETED_BAR_UNKNOWN')
            local=[]
            for row in unresolved():
                origin=conn.execute('SELECT trading_date_kst FROM runs WHERE run_id=?',(row['origin_run_id'],)).fetchone()
                if origin is None or not origin[0]: raise RuntimeError('UNRESOLVED_ORIGIN_UNKNOWN')
                from datetime import date
                local.append(row|{'origin_date':date.fromisoformat(str(origin[0]))})
            latest_snapshot[0]=composition.read_portfolio(PortfolioReadRequest(day,cutoff.cutoff_date,local))
            return latest_snapshot[0]

        def lifecycle_fact(state):
            record_transition_state(conn,TransitionObservation(account_scope_hash=scope.account_scope_hash,
                ticker=None,event_family='SERVICE_ACCOUNT',normalized_state=state,
                broker_subject_id=active[0].cycle_id if active[0] else 'service-account',
                severity=OperationalSeverity.CRITICAL if state=='RECONCILIATION_UNRESOLVED' else OperationalSeverity.INFO,
                observed_at=clock(),detail={'target':'mock'}))

        def lease_factory():
            cycle=str(uuid.uuid4())
            lease=acquire_mutation_lease(conn,account_scope_hash=scope.account_scope_hash,
                lock_dir=primary.parent/'.mutation-locks',command='service-account',cycle_id=cycle,observed_at=clock())
            active[0]=lease
            sqlite_audit.start_run(conn,run_id=cycle,trading_mode='mock',dry_run=False,run_kind=RunKind.RUN,
                target='mock',trading_date_kst=str(clock().astimezone(KST).date()),started_at=clock().isoformat())
            return lease

        def prior_terminal():
            prior=active[0].prior_cycle_id
            row=conn.execute('SELECT status FROM runs WHERE run_id=?',(prior,)).fetchone()
            if row and row[0]=='RUNNING': sqlite_audit.finish_run(conn,run_id=prior,status=RunStatus.INTERRUPTED)
            return True

        def terminal():
            row=conn.execute('SELECT status FROM runs WHERE run_id=?',(active[0].cycle_id,)).fetchone()
            if row and row[0]=='RUNNING': sqlite_audit.finish_run(conn,run_id=active[0].cycle_id,status=RunStatus.COMPLETED)
            lifecycle_fact('STOPPED')

        def reconcile(current):
            determinate=current.mutation_capable and all(o.status!='UNKNOWN' for o in current.orders)
            for row in unresolved():
                matches=[o for o in current.orders if o.order_id==row['broker_order_id']
                    and o.ticker==row['ticker'] and o.side==row['side']]
                if len(matches)!=1:
                    determinate=False;continue
                order=matches[0]
                # Exact determinate nonterminal truth scopes suppression to the
                # subject. It proves account reconciliation, never freeze release.
                if (order.status not in {'OPEN','PARTIAL','NO_FILL','FILLED','CANCELLED','EXPIRED','REJECTED'}
                        or row['requested_qty']!=order.ordered_quantity
                        or order.ordered_quantity<=0
                        or min(order.filled_quantity,order.remaining_quantity,order.cancelled_quantity,order.rejected_quantity)<0
                        or order.ordered_quantity!=order.filled_quantity+order.remaining_quantity+order.cancelled_quantity+order.rejected_quantity
                        or row['filled_qty'] is not None and order.filled_quantity<row['filled_qty']
                        or order.status in {'OPEN','NO_FILL'} and (order.filled_quantity or not order.remaining_quantity)
                        or order.status=='PARTIAL' and not (order.filled_quantity and order.remaining_quantity)
                        or order.terminal and order.remaining_quantity):
                    determinate=False;continue
                sqlite_audit.append_order_event(conn,OrderEvent(order_intent_id=row['order_intent_id'],
                    origin_run_id=row['origin_run_id'],observer_run_id=active[0].cycle_id,ticker=row['ticker'],
                    event_type=OrderEventType.RECONCILED,submission_id=row['submission_id'],broker_order_id=order.order_id,
                    side=order.side,requested_qty=order.ordered_quantity,filled_qty=order.filled_quantity,
                    unfilled_qty=order.remaining_quantity,broker_status=order.status,observed_at=clock().isoformat()))
            return {'determinate':determinate}

        work=BoundedAccountWork(conn=conn,account_scope_hash=scope.account_scope_hash,lease_factory=lease_factory,
            snapshot_reader=snapshot_reader,terminalize_prior=prior_terminal,reconcile_snapshot=reconcile,
            terminalize=terminal,persist_unresolved=lambda:lifecycle_fact('RECONCILIATION_UNRESOLVED'),clock=clock)
        activation=OwnedActivationCheck(settings,reader,safety,clock)
        authority=SubmissionAuthority(controls,policy=policy,clock=clock,unattended=True,activation_check=activation)
        binding=None
        def broker_factory(lease,current,budget):
            lease.assert_active_owner(observed_at=clock());budget.assert_available()
            first=conn.execute('SELECT total_evaluation FROM portfolio_snapshots WHERE account_scope_hash=? '
                'AND trading_date_kst=? AND completeness=? ORDER BY observed_at,rowid LIMIT 1',
                (scope.account_scope_hash,str(current.trading_date),'COMPLETE')).fetchone()
            # Whole-account equity loss is conservative relative to realized-only loss.
            loss=max(0.,float(first[0])-current.account.total_evaluation) if first else policy_values.daily_loss_threshold
            object.__setattr__(binding,'daily_loss_state',DailyLossState(loss,policy_values.daily_loss_threshold))
            class GuardedAdapter:
                def __init__(self,adapter): self.adapter=adapter
            return composition.guarded_broker_builder(BrokerGuardBindings(
                order_adapter_guard=lambda adapter,context:GuardedAdapter(adapter),
                evidence_sink=lambda event:sqlite_audit.append_order_event(conn,event),
                data_fresh=lambda:0<=(clock()-current.observed_at).total_seconds()<=10,
                submission_authority=authority))
        def audit_cycle(result,evaluation_id,cycle):
            if result.audit is None: raise RuntimeError('CYCLE_AUDIT_REQUIRED')
            sqlite_audit.write_decision(conn,cycle,result.audit,confidence=result.confidence,
                current_price=result.order.limit_price.amount if result.order else None,correlation_id=evaluation_id)
        binding=AccountTradingBinding(broker_factory=broker_factory,quote_reader=composition.read_quote,
            execution_config=ExecutionConfig(policy_values.buy_confidence_threshold,policy_values.sell_confidence_threshold,
                policy_values.buy_cash_fraction,policy_values.max_position_value),
            risk_config=RiskConfig(policy_values.stop_loss_pct,policy_values.take_profit_pct),
            daily_loss_state=DailyLossState(policy_values.daily_loss_threshold,policy_values.daily_loss_threshold),audit_cycle=audit_cycle)

        from .service_collection import ProductionInputSource,QuoteSettings,PromptIdentity
        provider='openai' if trading.llm_provider is LLMProviderName.OPENAI else 'anthropic'
        inputs=ProductionInputSource(policy=tuple((key,value) for key,value in policy_values.model_dump().items()
            if key in {'ohlcv_adjusted','pykrx_request_timeout_seconds'} or key.startswith(('screener_','naver_news_'))),
            quote=QuoteSettings(domain=trading.kis_mock.domain,app_key=trading.kis_mock.app_key,
                app_secret=trading.kis_mock.app_secret,refresh_margin_seconds=trading.kis_token_refresh_margin_seconds,
                min_interval_seconds=trading.kis_min_interval_seconds,max_retries=trading.kis_max_retries,
                retry_backoff_seconds=trading.kis_retry_backoff_seconds,timeout_seconds=trading.kis_timeout_seconds),
            prompt=PromptIdentity(system_prompt=SYSTEM_PROMPT,schema_hash=signal_schema_hash(),provider=provider,
                model=trading.openai_model if provider=='openai' else trading.anthropic_model,
                temperature=trading.openai_temperature if provider=='openai' else trading.anthropic_temperature,
                prompt_version=PROMPT_VERSION))

        from .control_runtime import ResumeSafetyEvidence
        def current_resume(scope,now):
            current=latest_snapshot[0]
            facts=safety(scope,now)
            saved=reader.read(load_acceptance_receipt(settings.acceptance_receipt_path))
            session=sessions.for_date(now.astimezone(KST).date())
            return ResumeSafetyEvidence(scope=scope,observed_at=current.observed_at,
                expires_at=current.observed_at+timedelta(seconds=10),
                broker_complete=current.mutation_capable and all(o.status!='UNKNOWN' for o in current.orders)
                    and all(r['event_type']=='RECONCILED' and r['broker_status'] in {'OPEN','PARTIAL','NO_FILL'} for r in unresolved()),
                evidence_complete=facts.healthy,calendar_confirmed=session.eligibility=='ELIGIBLE',
                authority_current=activation().allowed,safety_latched=facts.safety_latched,
                frozen_subjects=facts.frozen_tickers,source_hashes=saved.source_hashes)
        def validate_resume(scope,now):
            if scope!=receipt.scope: raise RuntimeError('REGISTERED_SCOPE_REQUIRED')
            work.run(lambda lease,current,budget:current)
            return current_resume(scope,clock())
        runtime=ServiceRuntime(settings=settings,journal=journal,controls=controls,composition=composition,
            account_work=work,policy=policy,daily_inputs=inputs,provider_factory=ProviderChildFactory(provider_settings),
            trading=binding,clock=clock,activation_check=activation,
            validate_resume=validate_resume,current_resume_safety=current_resume)
        runtime.close_resources=lambda:(composition.close(),conn.close())
        return runtime
    except BaseException:
        if conn: conn.close()
        if composition.close: composition.close()
        raise


def execute(ctx, launcher):
    def work():
        settings=load_service_settings(ctx.obj)
        if not settings.service_enabled or settings.mode=='DISABLED':
            typer.echo('DISABLED: worker not constructed');return
        if settings.mode!='KIS_MOCK': raise ValueError('explicit mock runtime required')
        from .service_launchd import launch_worker
        result=launch_worker(settings,runtime_factory=build_production_runtime)
        typer.echo(result)
    guarded(work)


@app.command()
def run(ctx:typer.Context): execute(ctx,False)


@app.command()
def launch(ctx:typer.Context): execute(ctx,True)


def lifecycle(ctx,command):
    def call():
        settings=load_service_settings(ctx.obj)
        from .service_launchd import lifecycle_command
        result=lifecycle_command(settings,config_path=ctx.obj,command=command)
        typer.echo(json.dumps(result,sort_keys=True))
    guarded(call)


@app.command('render-launchagents')
def render_launchagents(ctx:typer.Context): lifecycle(ctx,'render')


@app.command('install-launchagents')
def install_launchagents(ctx:typer.Context): lifecycle(ctx,'install')


@app.command()
def start(ctx:typer.Context): lifecycle(ctx,'start')


@app.command()
def stop(ctx:typer.Context): lifecycle(ctx,'stop')


@app.command('remove-launchagents')
def remove_launchagents(ctx:typer.Context): lifecycle(ctx,'remove')


if __name__=='__main__': app()
