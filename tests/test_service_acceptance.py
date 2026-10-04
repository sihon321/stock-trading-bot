"""Cross-owner acceptance evidence; all stores and transports are temporary."""
from dataclasses import replace
import hashlib
import json
import multiprocessing
import os
import sqlite3

import pytest

from tests.service_fixtures import FakeServiceClock, SCOPE, session_evidence
from tests.test_service_schedule import at
from tests.test_service_recovery import (
    runtime_fixture, FileClock, Gate, CountedTransport, wait_completion,
)


class Sessions:
    def __init__(self,kind):self.kind=kind
    def for_date(self,day):return session_evidence(self.kind,day)


def test_failed_actual_risk_ticks_preserve_stall_until_successful_attributed_progress(tmp_path):
    from tests.test_service_health import health_fixture
    from tests.test_alert_observer import Transport
    from trading_bot.alert_observer import AlertObserver
    from trading_bot.alert_config import ObserverSettings
    from trading_bot.web_config import ResourceDescriptor
    from trading_bot.web_models import AlertSourceBatch
    runtime,conn,clock,sequence=runtime_fixture(tmp_path,clock=FakeServiceClock(at(8,0)))
    (tmp_path/'obligations').mkdir()
    reader,unused,unusedclock,unusedtopology=health_fixture(tmp_path/'obligations')
    # Publish real independent obligations into this runtime's owner store.
    with unused.connection() as source:
        for row in source.execute('SELECT evidence_json FROM service_expectations'):
            from trading_bot.service_models import ServiceExpectation
            runtime.journal.expectation_writer().record_derived(ServiceExpectation.model_validate_json(row[0]).model_copy(update={'control_revision':1}))
    bot=AlertObserver(ObserverSettings(operational_db_path=tmp_path/'observer'/'alerts.db',
        registered_resources=tuple(ResourceDescriptor(id=owner,owner=owner,path=path,
            account_hash=SCOPE.account_scope_hash,target='mock') for owner,path in
            [('service',runtime.journal.path),('control',runtime.controls.path)])),clock=clock,notifier=Transport())
    def observe():
        for fact in bot.detector.detect(AlertSourceBatch(clock(),(),service_health=bot.evidence.service_health())):
            bot.store.observe(fact)
    try:
        bot.start()
        runtime.start()
        clock.wall=at(9,5);observe()
        incident=next(e for e in bot.store.list_incidents(active=True) if e.subject.problem_family=='WORKER_STALLED')
        original=runtime.work.run
        runtime.work.run=lambda op:(_ for _ in ()).throw(RuntimeError('account unavailable'))
        for _ in range(2):
            runtime.tick();observe()
            health=next(h for h in bot.evidence.service_health() if h.kind=='RISK')
            assert health.state=='BLOCKED' and health.reason_code=='RISK_UNAVAILABLE'
            assert health.mutation_ready is False and health.last_progress_at is None
            assert bot.store.get_incident(incident.episode_id).active
            clock.advance(60)
        runtime.work.run=original
        runtime.tick();observe()
        health=next(h for h in bot.evidence.service_health() if h.kind=='RISK')
        assert health.state=='RUNNING' and health.last_progress_at is not None
        assert not bot.store.get_incident(incident.episode_id).active
    finally:runtime.stop();conn.close();bot.stop()


@pytest.mark.parametrize('kind',['normal','holiday','unknown','delayed'])
def test_actual_runtime_fixed_boundary_matrix_coalesces_without_provider(kind,tmp_path):
    def interrupted(name):
        if name=='DISPATCH_COMMITTED':raise RuntimeError('offline consumed interruption')
    runtime,conn,clock,sequence=runtime_fixture(tmp_path,clock=FakeServiceClock(at(8,50)),barrier=interrupted)
    runtime.policy.session_evidence_provider=Sessions(kind)
    try:
        runtime.start()
        for hour,minute in ((8,50),(9,0),(9,10),(9,20),(15,20),(15,30)):
            clock.wall=at(hour,minute);runtime.tick()
            assert runtime.child is None
            assert not conn.in_transaction
        assert runtime.state=='IDLE'
        count=conn.execute('SELECT count(*) FROM daily_evaluation_dispatches').fetchone()[0]
        assert count==int(kind=='normal')
        if kind=='normal':
            assert runtime.job('PREP')['state']=='COMPLETED'
            assert runtime.job('DAILY')['state']=='PARTIAL'
            assert any(e['state']=='UNKNOWN' for e in runtime.journal.list_events(runtime.job('DAILY')['job_id']))
            assert runtime.job('RISK')['state']=='COMPLETED'
        elif kind=='delayed':assert runtime.job('DAILY')['state']=='MISSED'
        assert not conn.execute("SELECT 1 FROM mutation_leases WHERE state!='RELEASED'").fetchone()
    finally:runtime.stop();conn.close()


def crash_runtime(root,barrier_name):
    from pathlib import Path
    from trading_bot.service_runtime import ProviderChildFactory
    def crash(name):
        if name==barrier_name:os._exit(73)
    runtime,conn,clock,sequence=runtime_fixture(Path(root),barrier=crash)
    runtime.provider_factory=ProviderChildFactory(runtime.provider_factory.settings,
        offline_authority=runtime.offline_authority,transport_handler=CountedTransport(Path(root)/'calls'))
    runtime.start();runtime.tick()
    if barrier_name=='RESPONSE_BEFORE_FINALIZATION':wait_completion(runtime)
    os._exit(74)


@pytest.mark.parametrize('barrier_name',[
    'INPUT_COMMITTED','DISPATCH_COMMITTED','ACCOUNT_RELEASED','CHILD_STARTED','RESPONSE_BEFORE_FINALIZATION'])
def test_hard_process_crash_recovers_stable_primary_identity_without_replay(tmp_path,barrier_name):
    child=multiprocessing.get_context('spawn').Process(target=crash_runtime,args=(str(tmp_path),barrier_name))
    child.start();child.join(10)
    if child.is_alive():child.kill();child.join(5)
    assert child.exitcode==73
    with sqlite3.connect(tmp_path/'account.db') as saved:
        original=tuple(saved.execute('SELECT evaluation_id,canonical_input_hash FROM daily_evaluations'))
    assert original
    runtime,conn,clock,sequence=runtime_fixture(tmp_path,clock=FakeServiceClock(at(9,20)))
    original_snapshot=runtime.work.snapshot_reader
    import uuid
    runtime.work.snapshot_reader=lambda:replace(original_snapshot(),snapshot_id=f'recovery-{uuid.uuid4().hex}')
    try:
        runtime.start();runtime.tick()
        assert runtime.child is None
        assert tuple(conn.execute('SELECT evaluation_id,canonical_input_hash FROM daily_evaluations'))==original
        assert conn.execute('SELECT count(*) FROM daily_evaluation_dispatches').fetchone()[0]==1
        dispatch=conn.execute('SELECT dispatch_state FROM daily_evaluation_dispatches').fetchone()[0]
        assert dispatch==('EXPIRED_NEVER_DISPATCHED' if barrier_name=='INPUT_COMMITTED' else 'DISPATCHED_UNKNOWN')
        clock.advance(60);runtime.tick()
        assert runtime.child is None
        assert len((tmp_path/'calls').read_text().splitlines())<=1 if (tmp_path/'calls').exists() else True
        assert runtime.job('RISK')['state']=='RUNNING'
    finally:runtime.stop();conn.close()


@pytest.mark.parametrize('uncertain',[False,True])
def test_evaluation_intent_at_most_one_post_preserves_unknown_000660_freeze(tmp_path,uncertain):
    """Frozen other targets survive a determinate or lost-response first POST."""
    from tests.test_service_controls import submission_fixture
    from trading_bot import soak_store
    from trading_bot.soak_models import CampaignKind
    from trading_bot.cli import _LeaseGuardedBroker
    from trading_bot.domain import Order,OrderSide,Money,Ticker
    from trading_bot.submission_authority import SubmissionDenied
    j,primary,lease,guard,broker,adapter,args=submission_fixture(tmp_path)
    try:
        with sqlite3.connect(j.settings.trading_journal_paths[1]) as soak:
            soak_store.create_campaign(soak,campaign_id='frozen-proof',accepted_profile_fingerprint='profile',
                accepted_profile_version='TEST',field_contract_version='TEST',ambiguity_policy_version='TEST',
                ambiguity_window_seconds=30,ambiguity_poll_cadence_seconds=5,ambiguity_max_observations=6,
                campaign_kind=CampaignKind.PROOF_ORDER,credit_eligible=False)
            soak_store.freeze_ticker(soak,freeze_id='000660-original',campaign_id='frozen-proof',ticker='000660',
                freeze_kind='AMBIGUITY',order_intent_id='original-uncertain-submission')
        scope=guard.assert_account(broker._account,adapter)
        with pytest.raises(SubmissionDenied,match='TICKER_FROZEN'):guard._saved_safety(scope,'new-intent','000660')
        order=Order(Ticker('005930'),OrderSide.SELL,1,Money(70000))
        if uncertain:
            original=adapter.place_order_cash
            def lost(**kw):
                original(**kw)
                raise TimeoutError('offline lost POST response')
            adapter.place_order_cash=lost
        wrapper=lambda:_LeaseGuardedBroker(broker,lease,portfolio_refresh=lambda:args['portfolio_refresh']('005930'),
            evaluation_id='frozen-evaluation')
        first=wrapper()
        if uncertain:
            with pytest.raises(Exception):first.place_order(order,**args)
        else:first.place_order(order,**args)
        second=wrapper()
        with pytest.raises(Exception):second.place_order(order,**args)
        assert first._execution_intent_id==second._execution_intent_id
        assert adapter.post_attempts==1 and len(j.reader().list_admissions())==1
        with sqlite3.connect(j.settings.trading_journal_paths[1]) as soak:
            assert soak.execute("SELECT ticker,state FROM soak_ticker_freezes").fetchall()==[('000660','FROZEN')]
        if uncertain:assert j.reader().list_admissions()[0]['state']=='UNKNOWN'
    finally:lease.release();primary.close()


def test_partial_first_input_keeps_000660_in_committed_universe_after_sleep_gap(tmp_path):
    from trading_bot.service_runtime import DailyInput
    from tests.test_daily_dispatch import envelope
    def partial(name):
        if name=='INPUT_COMMITTED':raise RuntimeError('offline partial save')
    runtime,conn,clock,sequence=runtime_fixture(tmp_path,barrier=partial)
    calls=[]
    class PartialSource:
        def collect(self,day,held):
            calls.append(day)
            other=b'frozen canonical context: 000660'
            second=envelope().model_copy(update={'prompt_bytes':other,'prompt_hash':hashlib.sha256(other).hexdigest()})
            return (DailyInput('005930',('SCREENED',),envelope()),DailyInput('000660',('SCREENED',),second))
    runtime.daily_inputs=PartialSource()
    try:
        runtime.start();runtime.tick()
        job=runtime.job('DAILY');identity=job['job_id']
        assert json.loads(job['universe_json'])==['005930','000660']
        assert conn.execute('SELECT ticker FROM daily_evaluations').fetchall()==[('005930',)]
        runtime.stop();clock.wall=at(15,20)
        runtime=runtime.successor();runtime.barrier=lambda name:None
        runtime.start();runtime.tick()
        assert runtime.child is None and len(calls)==1
        assert runtime.job('DAILY')['job_id']==identity
        assert json.loads(runtime.job('DAILY')['universe_json'])==['005930','000660']
        assert runtime._remaining()==('000660',)
        assert runtime.job('RISK')['state']=='RUNNING'
    finally:runtime.stop();conn.close()


@pytest.mark.parametrize('restriction',['PAUSE','KILL','CUTOFF'])
def test_actual_spawn_entry_rechecks_pending_acceptance_before_application(tmp_path,restriction):
    from trading_bot.service_runtime import ProviderChildFactory
    from trading_bot.service_models import ControlRequest
    wall=tmp_path/'clock';clock=FileClock(wall);clock.set(at(9,19,59))
    runtime,conn,clock,sequence=runtime_fixture(tmp_path,clock=clock)
    ctx=multiprocessing.get_context('spawn');ready=ctx.Event();release=ctx.Event()
    runtime.provider_factory=ProviderChildFactory(runtime.provider_factory.settings,
        offline_authority=runtime.offline_authority,transport_handler=CountedTransport(tmp_path/'calls'),
        before_entry=Gate(ready,release))
    try:
        runtime.start();runtime.tick();assert ready.wait(5)
        if restriction=='CUTOFF':clock.set(at(9,20))
        else:
            accepted=runtime.controls.request_writer(actor='owner').append_request(ControlRequest(
                request_id='pending-stop',actor='owner',requested_at=clock(),scope=runtime.controls.scope,
                action=restriction,expected_revision=1))
            assert accepted.status=='REQUESTED'
            current=runtime.controls.reader().effective_state()
            assert current.applied.mode=='RUNNING' and current.mode!=current.applied.mode
        dispatch=runtime.last_dispatch_id
        assert not conn.in_transaction
        assert not conn.execute("SELECT 1 FROM mutation_leases WHERE state!='RELEASED'").fetchone()
        release.set();wait_completion(runtime)
        assert not (tmp_path/'calls').exists()
        assert runtime.journal.load_provider_admission(dispatch).state=='SUPPRESSED_NO_CALL'
        assert conn.execute('SELECT dispatch_state FROM daily_evaluation_dispatches').fetchone()[0]=='DISPATCHED_UNKNOWN'
        assert runtime.job('RISK')['state']=='RUNNING'
    finally:release.set();runtime.stop();conn.close()


def test_first_transport_entry_keeps_locks_free_and_stale_resume_cannot_clear_kill(tmp_path):
    from trading_bot.service_runtime import ProviderChildFactory
    from trading_bot.service_models import ControlRequest
    runtime,conn,clock,sequence=runtime_fixture(tmp_path)
    ctx=multiprocessing.get_context('spawn');ready=ctx.Event();release=ctx.Event()
    runtime.provider_factory=ProviderChildFactory(runtime.provider_factory.settings,
        offline_authority=runtime.offline_authority,transport_handler=CountedTransport(tmp_path/'calls',ready,release))
    try:
        runtime.start();runtime.tick();assert ready.wait(5)
        dispatch=runtime.last_dispatch_id
        assert runtime.journal.load_provider_admission(dispatch).state=='IN_FLIGHT'
        assert not conn.in_transaction
        assert not conn.execute("SELECT 1 FROM mutation_leases WHERE state!='RELEASED'").fetchone()
        for action,revision in [('RESUME',1),('KILL',2)]:
            assert runtime.controls.request_writer(actor='owner').append_request(ControlRequest(
                request_id=f'pending-{action}',actor='owner',requested_at=clock(),scope=runtime.controls.scope,
                action=action,expected_revision=revision)).status=='REQUESTED'
        clock.advance(60);runtime.tick()
        assert runtime.child is not None and runtime.controls.reader().effective_state().mode=='KILLED'
        assert runtime.journal.list_events(runtime.job('RISK')['job_id'])[-1]['reason_code']=='RECONCILIATION_ONLY'
        assert any(r['reason_code']=='REVISION_CONFLICT' for r in runtime.controls.reader().list_applications())
        release.set();wait_completion(runtime)
        assert (tmp_path/'calls').read_text()=='TRANSPORT\n'
        assert runtime.journal.load_provider_admission(dispatch).state=='FINISHED'
        assert conn.execute('SELECT count(*) FROM daily_evaluation_dispatches').fetchone()[0]==1
    finally:release.set();runtime.stop();conn.close()


def test_observer_persistent_source_failures_keep_critical_outbox_reminders_and_no_false_clear(tmp_path,monkeypatch):
    from tests.test_service_schedule import producer_fixture
    from tests.test_alert_observer import Transport
    from tests.test_alert_detector import record
    from trading_bot.alert_config import ObserverSettings
    from trading_bot.alert_observer import AlertObserver, ObserverEvidenceError
    from trading_bot.web_config import ResourceDescriptor
    from trading_bot.web_models import AlertSourceBatch
    producer,_,clock,journal,controls,_=producer_fixture(tmp_path)
    bot=AlertObserver(ObserverSettings(operational_db_path=tmp_path/'observer'/'alerts.db',
        registered_resources=tuple(ResourceDescriptor(id=kind,owner=kind,path=path,
            account_hash=SCOPE.account_scope_hash,target='mock') for kind,path in
            [('service',journal.path),('control',controls.path)])),
        clock=clock,notifier=Transport(),expectation_producer=producer)
    bot.start()
    incident=bot.store.observe(bot.detector.detect(AlertSourceBatch(clock(),(record('orders',
        ticker='000660',order_intent_id='original-unknown'),)))[0])
    controls.path.chmod(0o644);journal.path.chmod(0o644)
    critical=lambda:sum('UNRESOLVED_ORDER' in text for text in bot.notifier.sent)
    try:
        bot._scan(clock());assert critical()==1
        clock.advance(1800);bot._scan(clock());assert critical()==2
        clock.advance(1800);bot._scan(clock());assert critical()==3
        assert bot.store.get_incident(incident.episode_id).active
        assert bot.store.get_checkpoint() is None
        count=len(bot.notifier.sent)
        monkeypatch.setattr(bot.store,'get_checkpoint',lambda:(_ for _ in ()).throw(sqlite3.DatabaseError('own-store')))
        clock.advance(1800)
        with pytest.raises(sqlite3.DatabaseError):bot._scan(clock())
        assert len(bot.notifier.sent)==count
    finally:
        bot.store.path.chmod(0o600);bot.stop()
