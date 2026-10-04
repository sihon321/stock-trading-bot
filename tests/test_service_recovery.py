"""Real temporary account ownership and spawned offline transport supervision."""
from dataclasses import replace
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from datetime import timedelta
import hashlib
import json
import multiprocessing
import os
import time

import httpx
import pytest

from tests.service_fixtures import FakeServiceClock, SCOPE, TempServiceTopology, session_evidence
from tests.test_service_schedule import at


class ExactSession:
    def for_date(self,day):return session_evidence(day=day)


def runtime_fixture(tmp_path, *, clock=None, inputs_failure=False, barrier=lambda name:None):
    from trading_bot.service_runtime import ServiceRuntime, DailyInput, ProviderChildFactory, ProviderSettings
    from trading_bot.service_store import ServiceJournal
    from trading_bot.control_store import ControlStore
    from trading_bot.service_composition import ServiceComposition
    from trading_bot.service_activation import ActivationVerdict, OfflineActivationAuthority
    from trading_bot.service_models import ControlRequest
    from trading_bot.service_leader import ServiceLeader
    from trading_bot.control_runtime import ControlApplier
    from tests.test_service_controls import safety
    from tests.test_service_authority import account_work_fixture
    from tests.test_daily_dispatch import envelope
    clock=clock or FakeServiceClock(at(9,10))
    settings=TempServiceTopology(tmp_path).registration(enabled=True)
    journal=ServiceJournal(settings,clock=clock); journal.initialize()
    controls=ControlStore(settings,clock=clock); controls.initialize(actor='owner')
    fixture_leader=ServiceLeader(settings,journal=journal); fixture_leader.acquire()
    controls.request_writer(actor='owner').append_request(ControlRequest(request_id='resume',actor='owner',
        requested_at=clock(),scope=controls.scope,action='RESUME',expected_revision=0))
    ControlApplier(controls.service_capability(fixture_leader),validate_resume=lambda scope,now:safety(scope,now),
        current_safety=lambda scope,now:safety(scope,now),clock=clock).apply_pending()
    fixture_leader.close()
    work,conn,unused,sequence=account_work_fixture(tmp_path)
    work.clock=clock
    original=work.snapshot_reader
    work.snapshot_reader=lambda:replace(original(),observed_at=clock())
    original_lease=work.lease_factory
    from trading_bot.mutation_lease import acquire_mutation_lease
    work.lease_factory=lambda:acquire_mutation_lease(conn,account_scope_hash=SCOPE.account_scope_hash,
        lock_dir=tmp_path/'account-locks',command='service',cycle_id='service-pass',observed_at=clock())
    from trading_bot.market_cycle import MarketCyclePolicy
    class Calendar:
        def is_trading_day(self,day):return True
        def previous_trading_day(self,day):return day-timedelta(days=1)
    policy=MarketCyclePolicy(Calendar(),session_evidence_provider=ExactSession())
    composition=ServiceComposition(mode='KIS_MOCK',activation=ActivationVerdict(allowed=True,
        reason_codes=('SYNTHETIC',),authority='OFFLINE_ONLY'),authentication='SYNTHETIC',
        runtime_wired=True,scope=SCOPE,prep_read_only=lambda:sequence.append('prep'))
    class Source:
        def collect(self,day,held_tickers):
            sequence.append('collect')
            if inputs_failure:raise ValueError('raw provider key must not be saved')
            return (DailyInput('005930',('SCREENED',),envelope()),)
    authority=OfflineActivationAuthority(tmp_path)
    provider=ProviderChildFactory(ProviderSettings(llm_provider='openai',api_key='offline-key'),
        offline_authority=authority,transport_handler=offline_response)
    runtime=ServiceRuntime(settings=settings,journal=journal,controls=controls,composition=composition,
        account_work=work,policy=policy,daily_inputs=Source(),provider_factory=provider,
        clock=clock,monotonic=time.monotonic,offline_authority=authority,barrier=barrier)
    return runtime,conn,clock,sequence


def offline_response(request):
    body={'id':'test','object':'chat.completion','created':0,'model':'saved-model',
        'choices':[{'index':0,'finish_reason':'stop','message':{'role':'assistant',
            'content':json.dumps({'decision':'HOLD','confidence':0.1,'reason':'offline'})}}]}
    return httpx.Response(200,json=body)


def test_every_start_recovers_before_collect_or_tick(tmp_path):
    runtime,conn,clock,sequence=runtime_fixture(tmp_path)
    try:
        assert runtime.start()=='RUNNING'
        assert sequence[:3]==['snapshot','terminal','snapshot']
        assert conn.execute("SELECT count(*) FROM mutation_leases WHERE state!='RELEASED'").fetchone()[0]==0
        runtime.tick()
        assert sequence.index('collect')>sequence.index('terminal')
    finally:runtime.stop();conn.close()


def test_daily_failure_keeps_risk_alive_and_controls_persist(tmp_path):
    runtime,conn,clock,sequence=runtime_fixture(tmp_path,inputs_failure=True)
    try:
        runtime.start();runtime.tick()
        daily=runtime.job('DAILY')
        assert daily['state']=='UNKNOWN'
        assert runtime.job('RISK')['state']=='RUNNING'
        clock.advance(60);runtime.tick()
        events=runtime.journal.list_events(runtime.job('RISK')['job_id'])
        assert sum(e['reason_code']=='RISK_RECONCILED' for e in events)==2
        from trading_bot.service_models import ControlRequest
        runtime.controls.request_writer(actor='owner').append_request(ControlRequest(request_id='kill',actor='owner',
            requested_at=clock(),scope=runtime.controls.scope,action='KILL',expected_revision=1))
        clock.advance(60);runtime.tick()
        assert runtime.controls.reader().effective_state().mode=='KILLED'
        assert runtime.journal.list_events(runtime.job('RISK')['job_id'])[-1]['reason_code']=='RECONCILIATION_ONLY'
    finally:runtime.stop();conn.close()


def test_runtime_spawn_completion_has_no_live_account_ownership(tmp_path):
    runtime,conn,clock,sequence=runtime_fixture(tmp_path)
    try:
        runtime.start();runtime.tick()
        assert runtime.child is not None
        assert runtime.child.process._start_method=='spawn'
        assert not conn.in_transaction
        assert conn.execute("SELECT count(*) FROM mutation_leases WHERE state!='RELEASED'").fetchone()[0]==0
        deadline=time.monotonic()+5
        while runtime.child is not None and time.monotonic()<deadline:
            time.sleep(.02);runtime.tick()
        assert runtime.child is None
        assert conn.execute("SELECT dispatch_state FROM daily_evaluation_dispatches").fetchone()[0]=='FINALIZED'
        assert runtime.job('DAILY')['state']=='COMPLETED'
        assert runtime.journal.load_provider_admission(runtime.last_dispatch_id).state=='FINISHED'
    finally:runtime.stop();conn.close()


@pytest.mark.parametrize('barrier_name',['INPUT_COMMITTED','DISPATCH_COMMITTED','ACCOUNT_RELEASED','CHILD_STARTED'])
def test_crash_barriers_consumed_work_never_replays(tmp_path,barrier_name):
    seen=[]
    def barrier(name):
        seen.append(name)
        if name==barrier_name:raise RuntimeError('simulated crash')
    runtime,conn,clock,sequence=runtime_fixture(tmp_path,barrier=barrier)
    try:
        runtime.start();runtime.tick()
        assert barrier_name in seen
        runtime.barrier=lambda name:None
        runtime.stop()
        clock.advance(11*60)
        # Recovery after cutoff expires NEVER_DISPATCHED and never resets claims.
        runtime2=runtime.successor()
        runtime2.start()
        try:
            runtime2.tick()
            assert runtime2.child is None
            assert all(r[0]!='NEVER_DISPATCHED' for r in conn.execute('SELECT dispatch_state FROM daily_evaluation_dispatches'))
        finally:runtime2.stop()
    finally:runtime.stop();conn.close()


def test_runtime_rejects_unverified_activation_before_account_queries(tmp_path):
    from trading_bot.service_activation import ActivationVerdict
    runtime,conn,clock,sequence=runtime_fixture(tmp_path)
    runtime.composition=replace(runtime.composition,activation=ActivationVerdict(allowed=False,reason_codes=('APPROVALS_ABSENT',)))
    with pytest.raises(RuntimeError):runtime.start()
    assert sequence==[] and runtime.leader.state=='UNACQUIRED'
    conn.close()


@dataclass
class FileClock:
    path: Path
    def __call__(self):return datetime.fromisoformat(self.path.read_text())
    def set(self,now):self.path.write_text(now.isoformat())
    def advance(self,seconds):self.set(self()+timedelta(seconds=seconds))


@dataclass
class Gate:
    ready: object
    release: object
    def __call__(self):
        self.ready.set()
        if not self.release.wait(5):raise RuntimeError('offline gate timeout')


@dataclass
class CountedTransport:
    path: Path
    ready: object = None
    release: object = None
    def __call__(self,request):
        with self.path.open('a') as output:output.write('TRANSPORT\n')
        if self.ready:
            self.ready.set()
            if not self.release.wait(5):raise RuntimeError('offline response timeout')
        return offline_response(request)


def wait_completion(runtime,seconds=5):
    end=time.monotonic()+seconds
    while runtime.child is not None and time.monotonic()<end:
        time.sleep(.02);runtime.tick()
    assert runtime.child is None


@pytest.mark.parametrize('change',['deadline','pause','kill','midnight'])
def test_spawned_entry_after_startup_rechecks_current_restrictions(tmp_path,change):
    from trading_bot.service_runtime import ProviderChildFactory
    from trading_bot.service_models import ControlRequest
    wall=tmp_path/'clock';clock=FileClock(wall);clock.set(at(9,19,59))
    runtime,conn,clock,sequence=runtime_fixture(tmp_path,clock=clock)
    ctx=multiprocessing.get_context('spawn');ready=ctx.Event();release=ctx.Event()
    counter=tmp_path/'provider-calls'
    runtime.provider_factory=ProviderChildFactory(runtime.provider_factory.settings,
        offline_authority=runtime.offline_authority,transport_handler=CountedTransport(counter),
        before_entry=Gate(ready,release))
    try:
        runtime.start();runtime.tick();assert ready.wait(5)
        dispatch_id=runtime.last_dispatch_id
        if change=='deadline':clock.set(at(9,20))
        elif change=='midnight':clock.set(at(0,day=6))
        else:
            result=runtime.controls.request_writer(actor='owner').append_request(ControlRequest(
                request_id=change,actor='owner',requested_at=clock(),scope=runtime.controls.scope,
                action=change.upper(),expected_revision=1))
            assert result.status=='REQUESTED'
        release.set();wait_completion(runtime)
        assert not counter.exists()
        assert runtime.journal.load_provider_admission(dispatch_id).state=='SUPPRESSED_NO_CALL'
        assert conn.execute('SELECT count(*) FROM daily_evaluation_dispatches').fetchone()[0]==1
        assert conn.execute('SELECT dispatch_state FROM daily_evaluation_dispatches').fetchone()[0]=='DISPATCHED_UNKNOWN'
    finally:release.set();runtime.stop();conn.close()


def test_inflight_response_unlocks_control_and_healthy_risk_progress(tmp_path):
    from trading_bot.service_runtime import ProviderChildFactory
    from trading_bot.service_models import ControlRequest
    wall=tmp_path/'clock';clock=FileClock(wall);clock.set(at(9,19,59))
    runtime,conn,clock,sequence=runtime_fixture(tmp_path,clock=clock)
    ctx=multiprocessing.get_context('spawn');ready=ctx.Event();release=ctx.Event()
    counter=tmp_path/'provider-calls'
    runtime.provider_factory=ProviderChildFactory(runtime.provider_factory.settings,
        offline_authority=runtime.offline_authority,transport_handler=CountedTransport(counter,ready,release))
    try:
        runtime.start();runtime.tick();assert ready.wait(5)
        assert runtime.journal.load_provider_admission(runtime.last_dispatch_id).state=='IN_FLIGHT'
        clock.advance(60)
        runtime.tick()
        assert runtime.child is not None
        assert sum(e['reason_code']=='RISK_RECONCILED' for e in runtime.journal.list_events(runtime.job('RISK')['job_id']))==2
        accepted=runtime.controls.request_writer(actor='owner').append_request(ControlRequest(request_id='kill-response',actor='owner',
            requested_at=clock(),scope=runtime.controls.scope,action='KILL',expected_revision=1))
        assert accepted.status=='REQUESTED'
        release.set();wait_completion(runtime)
        assert counter.read_text()=='TRANSPORT\n'
        assert conn.execute('SELECT dispatch_state FROM daily_evaluation_dispatches').fetchone()[0]=='FINALIZED'
        assert runtime.controls.reader().effective_state().mode=='KILLED'
    finally:release.set();runtime.stop();conn.close()


def test_child_timeout_and_stop_are_consumed_unknown_and_preserve_kill(tmp_path):
    from trading_bot.service_runtime import ProviderChildFactory
    runtime,conn,clock,sequence=runtime_fixture(tmp_path)
    ctx=multiprocessing.get_context('spawn');ready=ctx.Event();release=ctx.Event()
    counter=tmp_path/'provider-calls'
    runtime.provider_factory=ProviderChildFactory(runtime.provider_factory.settings,
        offline_authority=runtime.offline_authority,transport_handler=CountedTransport(counter,ready,release))
    try:
        runtime.start();runtime.tick();assert ready.wait(5)
        process=runtime.child.process
        runtime.child.deadline=time.monotonic()-.1
        runtime.tick()
        assert not process.is_alive() and runtime.child is None
        assert counter.read_text()=='TRANSPORT\n'
        assert conn.execute('SELECT dispatch_state FROM daily_evaluation_dispatches').fetchone()[0]=='DISPATCHED_UNKNOWN'
        runtime.tick();assert counter.read_text()=='TRANSPORT\n'
        assert runtime.journal.load_provider_admission(runtime.last_dispatch_id).state=='UNKNOWN'
    finally:
        # Terminating a waiter can poison multiprocessing.Event's condition.
        # Its isolated child owns no recovery resource; never reuse that event.
        runtime.stop();conn.close()


def test_recovery_resumes_only_saved_never_dispatched_before_deadline(tmp_path):
    def barrier(name):
        if name=='INPUT_COMMITTED':raise RuntimeError('crash before claim')
    runtime,conn,clock,sequence=runtime_fixture(tmp_path,barrier=barrier)
    try:
        runtime.start();runtime.tick()
        assert conn.execute('SELECT dispatch_state FROM daily_evaluation_dispatches').fetchone()[0]=='NEVER_DISPATCHED'
        original=conn.execute('SELECT canonical_input FROM daily_evaluations').fetchone()[0]
        runtime.stop();runtime.barrier=lambda name:None
        successor=runtime.successor();successor.start()
        try:
            successor.tick();wait_completion(successor)
            assert conn.execute('SELECT canonical_input FROM daily_evaluations').fetchone()[0]==original
            assert conn.execute('SELECT count(*) FROM daily_evaluation_dispatches').fetchone()[0]==1
        finally:successor.stop()
    finally:runtime.stop();conn.close()


def test_concrete_trading_binding_rejects_boolean_guard_and_low_buy_threshold(tmp_path):
    from trading_bot.service_runtime import AccountTradingBinding, RuntimeBlocked
    from trading_bot.execution import ExecutionConfig
    from trading_bot.risk import RiskConfig, DailyLossState
    kwargs=dict(broker_factory=lambda *args:True,quote_reader=lambda ticker:None,
        execution_config=ExecutionConfig(.8,.8,.1,1000),risk_config=RiskConfig(.05,.1),
        daily_loss_state=DailyLossState(0,100),audit_cycle=lambda *args:None)
    binding=AccountTradingBinding(**kwargs)
    with pytest.raises(RuntimeBlocked):binding._broker(None,None,None,None)
    kwargs['execution_config']=ExecutionConfig(.79,.8,.1,1000)
    with pytest.raises(TypeError):AccountTradingBinding(**kwargs)
