from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import importlib
import multiprocessing
import os
import sqlite3

import pytest

from tests.service_fixtures import FakeServiceClock, NOW, SCOPE, TempServiceTopology
from trading_bot.service_models import ControlRequest, InstallationScope, ServiceScope


def store(tmp_path, *, extra_scope=False):
    module = importlib.import_module('trading_bot.control_store')
    settings = TempServiceTopology(tmp_path).registration()
    if extra_scope:
        settings = settings.model_copy(update={'registered_scopes': (SCOPE, ServiceScope(
            account_scope_hash='b'*64, execution_target='mock'))})
    clock = FakeServiceClock()
    journal = module.ControlStore(settings, clock=clock)
    journal.initialize(actor='owner')
    return journal, clock


def request(journal, action='PAUSE', revision=0, rid='request1', **updates):
    return ControlRequest(**(dict(request_id=rid, actor='owner', requested_at=journal.clock(),
        scope=journal.scope, action=action, expected_revision=revision) | updates))


def test_request_acceptance_pending_restriction_and_capability(tmp_path):
    j, _ = store(tmp_path, extra_scope=True)
    writer = j.request_writer(actor='owner')
    reader = j.reader()
    accepted = writer.append_request(request(j, 'KILL'))
    assert accepted.status == 'REQUESTED' and accepted.acceptance_revision == 1
    for scope in j.settings.registered_scopes:
        state = reader.effective_state(scope)
        assert state.mode == 'KILLED' and state.applied.mode == 'PAUSED'
        assert state.applied.revision == 0 and state.acceptance_revision == 1
        assert not state.allows_buy and not state.allows_risk_sell and not state.allows_daily
        assert state.allows_reconciliation
    assert reader.list_requests()[0]['actor'] == 'owner'
    for facade in (reader, writer):
        for forbidden in ('initialize', 'connection', 'apply_pending', 'service_capability',
                          'admission_lock', 'record_admission', 'claim_job', 'settings', 'path'):
            assert not hasattr(facade, forbidden)
    with pytest.raises(ValueError): reader.effective_state(ServiceScope(account_scope_hash='c'*64, execution_target='mock'))
    with pytest.raises(ValueError): reader.list_requests(limit=101)


def test_request_revision_idempotence_changed_replay_actor_scope(tmp_path):
    j, _ = store(tmp_path, extra_scope=True)
    w = j.request_writer(actor='owner')
    first = request(j)
    assert w.append_request(first).status == 'REQUESTED'
    assert w.append_request(first).idempotent
    assert w.append_request(request(j, 'KILL')).status == 'CONFLICT'
    assert w.append_request(request(j, rid='stale')).status == 'CONFLICT'
    with pytest.raises(ValueError): w.append_request(request(j, actor='intruder', rid='other'))
    with pytest.raises(ValueError): w.append_request(request(j, scope=InstallationScope(registered_scopes=(SCOPE,))))
    assert len(j.reader().list_requests()) == 1
    assert w.append_request(request(j, 'KILL', 1, 'kill')).acceptance_revision == 2


def test_request_revision_two_writers_one_winner(tmp_path):
    j, _ = store(tmp_path)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda rid: j.request_writer(actor='owner').append_request(
            request(j, rid=rid)), ('first', 'second')))
    assert sorted(r.status for r in results) == ['CONFLICT', 'REQUESTED']
    assert j.reader().effective_state(SCOPE).acceptance_revision == 1


def test_request_persistence_restart_and_date_no_reset(tmp_path):
    j, clock = store(tmp_path)
    j.request_writer(actor='owner').append_request(request(j, 'KILL'))
    clock.advance(86400*5)
    module = importlib.import_module('trading_bot.control_store')
    restarted = module.ControlStore(j.settings, clock=clock)
    restarted.initialize(actor='owner')
    assert restarted.reader().effective_state(SCOPE).mode == 'KILLED'
    restarted.request_writer(actor='owner').append_request(request(restarted, 'RESUME', 1, 'resume'))
    assert restarted.reader().effective_state(SCOPE).mode == 'KILLED'


def test_request_busy_storage_and_failed_audit_never_claim_acceptance(tmp_path):
    j, _ = store(tmp_path)
    with sqlite3.connect(j.path) as conn:
        conn.execute('BEGIN IMMEDIATE')
        result = j.request_writer(actor='owner').append_request(request(j))
        assert result.status == 'UNAVAILABLE'
        conn.rollback()
        conn.execute("CREATE TRIGGER fail_audit BEFORE INSERT ON control_request_audit WHEN NEW.event='REQUESTED' BEGIN SELECT RAISE(ABORT,'failure'); END")
    assert j.request_writer(actor='owner').append_request(request(j)).status == 'UNAVAILABLE'
    assert not j.reader().list_requests()
    assert j.reader().effective_state(SCOPE).acceptance_revision == 0


@pytest.mark.parametrize('unsafe', ['permissions', 'symlink', 'hardlink', 'version', 'owner', 'lock_permissions', 'lock_replacement', 'registration'])
def test_request_unsafe_storage_denies(tmp_path, unsafe):
    j, _ = store(tmp_path)
    if unsafe == 'permissions': j.path.chmod(0o644)
    elif unsafe == 'symlink':
        original = j.path.with_suffix('.original'); j.path.rename(original); j.path.symlink_to(original)
    elif unsafe == 'hardlink': os.link(j.path, j.path.with_suffix('.linked'))
    elif unsafe in ('version', 'owner'):
        with sqlite3.connect(j.path) as c:
            c.execute('UPDATE control_metadata SET '+ ('version=99' if unsafe == 'version' else "owner='other'"))
    elif unsafe == 'lock_permissions': (j.settings.lock_dir / 'admission.lock').chmod(0o644)
    elif unsafe == 'lock_replacement':
        lock = j.settings.lock_dir / 'admission.lock'
        lock.rename(lock.with_suffix('.old'))
        fd = os.open(lock,os.O_CREAT|os.O_WRONLY,0o600); os.close(fd)
    else:
        j = type(j)(j.settings.model_copy(update={'registered_scopes': (ServiceScope(account_scope_hash='c'*64, execution_target='mock'),)}))
    assert j.request_writer(actor='owner').append_request(request(j)).status == 'UNAVAILABLE'
    with pytest.raises((ValueError, OSError, sqlite3.DatabaseError)): j.reader().effective_state(j.settings.registered_scopes[0])


def test_request_migration_rollback_idempotence_immutable_history(tmp_path):
    m = importlib.import_module('trading_bot.control_store')
    settings = TempServiceTopology(tmp_path).registration()
    j = m.ControlStore(settings, clock=FakeServiceClock())
    with pytest.raises(RuntimeError): j.initialize(actor='owner', fail_after_step='control_requests')
    with sqlite3.connect(j.path) as c:
        assert not c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    j.initialize(actor='owner'); j.initialize(actor='owner')
    j.request_writer(actor='owner').append_request(request(j))
    with sqlite3.connect(j.path) as c:
        for table in ('control_requests', 'control_request_audit', 'control_applications'):
            with pytest.raises(sqlite3.IntegrityError): c.execute(f'DELETE FROM {table}')
    assert j.path.stat().st_mode & 0o777 == 0o600
    assert j.path.parent.stat().st_mode & 0o777 == 0o700
    assert len(j.reader().list_applications()) == 1


def hold_admission(settings_json, acquired, release):
    from trading_bot.service_config import ServiceSettings
    from trading_bot.control_store import ControlStore
    j = ControlStore(ServiceSettings.model_validate_json(settings_json))
    with j.admission_lock():
        acquired.set()
        release.wait(10)


def test_request_process_global_lock_busy_no_false_acceptance(tmp_path):
    j, _ = store(tmp_path)
    ctx = multiprocessing.get_context('spawn')
    acquired, release = ctx.Event(), ctx.Event()
    process = ctx.Process(target=hold_admission, args=(j.settings.model_dump_json(), acquired, release))
    process.start()
    try:
        assert acquired.wait(5)
        result = j.request_writer(actor='owner').append_request(request(j, 'KILL'))
        assert result.status == 'UNAVAILABLE' and result.reason_code == 'LOCK_UNAVAILABLE'
        assert j.reader().effective_state(SCOPE).acceptance_revision == 0
    finally:
        release.set(); process.join(5)
        if process.is_alive(): process.terminate(); process.join()
    assert process.exitcode == 0
    assert j.request_writer(actor='owner').append_request(request(j, 'KILL')).status == 'REQUESTED'


def test_request_strict_fields(tmp_path):
    j, _ = store(tmp_path)
    for updates in ({'expected_revision': True}, {'expected_revision': -1}, {'action': 'CANCEL'},
                    {'path': '/tmp/other'}, {'requested_at': NOW.replace(tzinfo=None)}):
        with pytest.raises(ValueError): request(j, **updates)


def submission_fixture(tmp_path, *, suffix_scope=False):
    """Actual temporary journals/lease, with an explicitly offline market source."""
    from trading_bot import sqlite_audit, soak_store
    from trading_bot.soak_controller import connect_controller
    from trading_bot.portfolio import canonical_account_scope_hash
    from trading_bot.mutation_lease import acquire_mutation_lease
    from trading_bot.service_activation import OfflineActivationAuthority
    from trading_bot.submission_authority import SubmissionAuthority
    from trading_bot.market_cycle import MarketCyclePolicy
    from tests.test_exit_manager import _snapshot
    from dataclasses import replace
    from tests.service_fixtures import session_evidence
    settings = TempServiceTopology(tmp_path).registration()
    scope = ServiceScope(account_scope_hash=canonical_account_scope_hash('mock', '5678' if suffix_scope else '5678:01'), execution_target='mock')
    settings = settings.model_copy(update={'registered_scopes': (scope,)})
    from trading_bot.control_store import ControlStore
    j = ControlStore(settings, clock=FakeServiceClock())
    j.initialize(actor='owner')
    primary = sqlite_audit.connect(settings.trading_journal_paths[0])
    from trading_bot.portfolio_store import migrate_portfolio
    migrate_portfolio(primary)
    soak_store.connect_soak_store(settings.trading_journal_paths[1]).close()
    connect_controller(settings.trading_journal_paths[2], *settings.trading_journal_paths[:2]).close()
    if primary.execute("SELECT 1 FROM runs WHERE run_id='submission-run'").fetchone() is None:
        sqlite_audit.start_run(primary, run_id='submission-run', trading_mode='mock', dry_run=False, target='kis_mock')
    lease = acquire_mutation_lease(primary, account_scope_hash=scope.account_scope_hash,
        lock_dir=tmp_path/'account-locks', command='test', cycle_id='submission-run', observed_at=NOW)
    class Calendar:
        def is_trading_day(self, day): return True
        def previous_trading_day(self, day): return day-timedelta(days=1)
    class Sessions:
        def for_date(self, day): return session_evidence(day=day)
    policy = MarketCyclePolicy(Calendar(), session_evidence_provider=Sessions())
    guard = SubmissionAuthority(j, policy=policy, clock=j.clock,
        offline_authority=OfflineActivationAuthority(tmp_path))
    snap = replace(_snapshot(), account_scope_hash=scope.account_scope_hash,
        trading_date=NOW.date(), observed_at=NOW)
    from tests.test_kis_broker import _FakeOrderAdapter
    from trading_bot.kis_broker import KISBroker
    from trading_bot.kis_order import KisOrderAccount
    from trading_bot.data_models import SourceHealth, SourceStatus
    from trading_bot.domain import Money
    from types import SimpleNamespace
    adapter = _FakeOrderAdapter()
    quote = SimpleNamespace(observed_at=NOW, price=Money(70000), health=SourceHealth(
        source='fixture', status=SourceStatus.AVAILABLE, reason='offline'))
    broker = KISBroker(order_adapter=adapter, account=KisOrderAccount('12345678','01'),
        submission_authority=guard, market_clock=lambda:True, clock=j.clock,
        evidence_sink=lambda event:sqlite_audit.append_order_event(primary,event),
        pre_submit_quote_reader=lambda ticker:quote)
    args = dict(order_intent_id='intent-final', origin_run_id='submission-run',
        portfolio_refresh=lambda ticker:snap, lease_guard=lease,
        trigger_revalidator=lambda snapshot, price:True)
    return j, primary, lease, guard, broker, adapter, args


@pytest.mark.parametrize('action,side,allowed', [('PAUSE','BUY',False),('PAUSE','SELL',True),('KILL','BUY',False),('KILL','SELL',False)])
def test_final_authority_pending_restrictions(tmp_path, action, side, allowed):
    from trading_bot.domain import Order, OrderSide, Money, Ticker
    from trading_bot.kis_broker import MarketClosedError
    j, primary, lease, guard, broker, adapter, args = submission_fixture(tmp_path)
    try:
        j.request_writer(actor='owner').append_request(request(j, action))
        order = Order(Ticker('005930'),OrderSide(side),1,Money(70000))
        if allowed: broker.place_order(order, **args)
        else:
            with pytest.raises(MarketClosedError): broker.place_order(order, **args)
        assert adapter.post_attempts == int(allowed)
        if allowed: assert j.reader().list_admissions()[0]['state']=='FINISHED'
    finally: lease.release(); primary.close()


def test_final_authority_callback_kill_zero_post(tmp_path):
    from tests.test_kis_broker import _order
    from trading_bot.kis_broker import MarketClosedError
    j, primary, lease, guard, broker, adapter, args = submission_fixture(tmp_path)
    def callback(snapshot, price):
        j.request_writer(actor='owner').append_request(request(j,'KILL'))
        return True
    args['trigger_revalidator']=callback
    try:
        with pytest.raises(MarketClosedError): broker.place_order(_order(),**args)
        assert adapter.post_attempts==0
    finally: lease.release(); primary.close()


@pytest.mark.parametrize('failure', ['primary','post','terminal','crash'])
def test_final_authority_consumes_partial_unknown_intent(tmp_path, failure, monkeypatch):
    from trading_bot.domain import Order, OrderSide, Money, Ticker
    j, primary, lease, guard, broker, adapter, args = submission_fixture(tmp_path)
    order=Order(Ticker('005930'),OrderSide.SELL,1,Money(70000))
    original=broker._evidence_sink
    def sink(event):
        if event.event_type.value=='SUBMISSION_ATTEMPTED':
            if failure=='primary': raise RuntimeError('fixture store failure')
            if failure=='crash': raise SystemExit('fixture crash')
        original(event)
    broker.set_evidence_sink(sink)
    if failure=='post': adapter.post_exception=TimeoutError()
    if failure=='terminal':
        monkeypatch.setattr(j,'_finish_admission',lambda *a,**kw:(_ for _ in ()).throw(RuntimeError('fixture terminal')))
    try:
        with pytest.raises(BaseException): broker.place_order(order,**args)
        assert len(j.reader().list_admissions())==1
        broker.set_evidence_sink(original)
        with pytest.raises(Exception): broker.place_order(order,**args)
        assert adapter.post_attempts==int(failure in ('post','terminal'))
    finally: lease.release(); primary.close()


def test_final_authority_post_has_no_sql_transaction_and_lock_cannot_accept(tmp_path):
    from trading_bot.domain import Order, OrderSide, Money, Ticker
    j, primary, lease, guard, broker, adapter, args = submission_fixture(tmp_path)
    post=adapter.place_order_cash
    def transport(**kw):
        assert not primary.in_transaction
        with sqlite3.connect(j.path,timeout=.1) as connection:
            connection.execute('BEGIN IMMEDIATE'); connection.rollback()
        assert j.request_writer(actor='owner').append_request(request(j,'KILL')).status=='UNAVAILABLE'
        return post(**kw)
    adapter.place_order_cash=transport
    try:
        broker.place_order(Order(Ticker('005930'),OrderSide.SELL,1,Money(70000)),**args)
        assert j.request_writer(actor='owner').append_request(request(j,'KILL')).status=='REQUESTED'
    finally: lease.release(); primary.close()


def _spawn_final_post(root, barrier, ready, release, results):
    from pathlib import Path
    from trading_bot.domain import Order, OrderSide, Money, Ticker
    from trading_bot.mutation_lease import recover_to_active
    j, primary, lease, guard, broker, adapter, args = submission_fixture(Path(root))
    def wait():
        ready.set()
        if not release.wait(10): raise TimeoutError('fixture barrier')
    refresh=args['portfolio_refresh']
    if lease.recovery_required:
        recover_to_active(lease,terminalize_prior_cycles=lambda:None,
            reconcile_broker_truth=lambda:True,refresh_snapshot=lambda:refresh('005930'))
    if barrier=='EARLY': args['trigger_revalidator']=lambda snapshot,price:(wait() or True)
    if barrier=='ATTEMPT':
        sink=broker._evidence_sink
        def evidence(event):
            sink(event)
            if event.event_type.value=='SUBMISSION_ATTEMPTED': wait()
        broker.set_evidence_sink(evidence)
    post=adapter.place_order_cash
    def transport(**kw):
        if barrier=='POST': wait()
        results.put('POST')
        return post(**kw)
    adapter.place_order_cash=transport
    try:
        broker.place_order(Order(Ticker('005930'),OrderSide.SELL,1,Money(70000)),**args)
        results.put('FINISHED')
    except Exception: results.put('DENIED')
    finally: lease.release(); primary.close()


@pytest.mark.parametrize('barrier', ['EARLY','ATTEMPT','POST'])
def test_final_authority_spawned_control_post_ordering(tmp_path,barrier):
    j, primary, lease, guard, broker, adapter, args=submission_fixture(tmp_path)
    lease.release(); primary.close()
    ctx=multiprocessing.get_context('spawn')
    ready,release,results=ctx.Event(),ctx.Event(),ctx.Queue()
    child=ctx.Process(target=_spawn_final_post,args=(str(tmp_path),barrier,ready,release,results))
    child.start()
    try:
        assert ready.wait(10)
        accepted=j.request_writer(actor='owner').append_request(request(j,'KILL'))
        assert accepted.status==('REQUESTED' if barrier=='EARLY' else 'UNAVAILABLE')
        release.set(); child.join(10)
        assert child.exitcode==0
        if barrier=='EARLY': assert results.get(timeout=2)=='DENIED'
        else:
            assert results.get(timeout=2)=='POST' and results.get(timeout=2)=='FINISHED'
            assert j.request_writer(actor='owner').append_request(request(j,'KILL')).status=='REQUESTED'
        assert j.reader().effective_state().mode=='KILLED'
    finally:
        release.set()
        if child.is_alive(): child.kill(); child.join(5)


@pytest.mark.parametrize('changed', ['quote','snapshot','session','fake_lease','fake_activation'])
def test_final_authority_rechecks_actual_gates(tmp_path,changed):
    from dataclasses import replace
    from trading_bot.domain import Order, OrderSide, Money, Ticker
    from trading_bot.kis_broker import MarketClosedError
    j, primary, lease, guard, broker, adapter, args=submission_fixture(tmp_path)
    if changed in ('quote','snapshot'): j.clock.advance(11)
    elif changed=='session': j.clock.advance(6*3600+20*60)
    elif changed=='fake_lease':
        class FakeLease:
            account_scope_hash=lease.account_scope_hash
            def assert_active_owner(self): return True
        args['lease_guard']=FakeLease()
    else: guard.unattended=True; guard.activation_check=lambda:True
    try:
        with pytest.raises(MarketClosedError):
            broker.place_order(Order(Ticker('005930'),OrderSide.SELL,1,Money(70000)),**args)
        assert adapter.post_attempts==0
    finally: lease.release(); primary.close()


def application(j):
    runtime = importlib.import_module('trading_bot.control_runtime')
    from trading_bot.service_leader import ServiceLeader
    from trading_bot.service_store import ServiceJournal
    operational = ServiceJournal(j.settings, clock=j.clock)
    operational.initialize()
    leader = ServiceLeader(j.settings, journal=operational).acquire()
    return runtime, leader, j.service_capability(leader)


def safety(scope=SCOPE, now=NOW, **updates):
    runtime = importlib.import_module('trading_bot.control_runtime')
    from trading_bot.service_models import SourceHash
    return runtime.ResumeSafetyEvidence(**(dict(scope=scope, observed_at=now,
        expires_at=now+timedelta(seconds=10), broker_complete=True, evidence_complete=True,
        calendar_confirmed=True, authority_current=True, safety_latched=False,
        frozen_subjects=(), source_hashes=tuple(SourceHash(source_id=name,source_hash=char*64)
            for name,char in zip(('broker','evidence','calendar','authority'), 'abcd'))) | updates))


def applier(j, *, validate=None, current=None):
    runtime, leader, capability = application(j)
    checks = lambda scope, now: safety(scope,now)
    return runtime.ControlApplier(capability,validate_resume=validate or checks,
        current_safety=current or checks,clock=j.clock), leader


def test_service_capability_only_actual_live_leader_applies(tmp_path):
    j, _ = store(tmp_path)
    with pytest.raises(ValueError): j.service_capability(object())
    runtime, leader, capability = application(j)
    try:
        with pytest.raises(ValueError): runtime.ControlApplier(j.request_writer(actor='owner'))
        j.request_writer(actor='owner').append_request(request(j))
        a = runtime.ControlApplier(capability,clock=j.clock)
        assert a.apply_pending()[0]['result'] == 'APPLIED'
    finally: leader.close()
    j.request_writer(actor='owner').append_request(request(j,'KILL',1,'kill'))
    with pytest.raises(RuntimeError): a.apply_pending()
    assert j.reader().effective_state(SCOPE).mode == 'KILLED'
    assert j.reader().effective_state(SCOPE).applied.revision == 1


def test_service_pause_kill_skip_permissive_checks_and_preserve_risk_observation(tmp_path):
    j, _ = store(tmp_path)
    def forbidden(*args): raise AssertionError('restrictive controls must skip permissive checks')
    a, leader = applier(j,validate=forbidden,current=forbidden)
    try:
        j.request_writer(actor='owner').append_request(request(j))
        assert a.apply_pending()[0]['mode'] == 'PAUSED'
        state = j.reader().effective_state(SCOPE)
        assert state.allows_risk_sell and state.allows_reconciliation and not state.allows_buy
        j.request_writer(actor='owner').append_request(request(j,'KILL',1,'kill'))
        assert a.apply_pending()[0]['mode'] == 'KILLED'
        j.request_writer(actor='owner').append_request(request(j,'PAUSE',2,'pause-after-kill'))
        assert a.apply_pending()[0]['mode'] == 'KILLED'
        assert j.reader().effective_state(SCOPE).allows_reconciliation
        assert not j.reader().effective_state(SCOPE).allows_risk_sell
    finally: leader.close()


def test_service_fresh_owner_resume_latest_revision_all_registered_scopes(tmp_path):
    j, _ = store(tmp_path,extra_scope=True)
    seen = []
    def validate(scope,now):
        seen.append(scope)
        return safety(scope,now)
    a, leader = applier(j,validate=validate)
    try:
        j.request_writer(actor='owner').append_request(request(j,'KILL'))
        a.apply_pending()
        j.request_writer(actor='owner').append_request(request(j,'RESUME',1,'resume'))
        assert j.reader().effective_state(SCOPE).mode == 'KILLED'
        result = a.apply_pending()[0]
        state = j.reader().effective_state(SCOPE)
        assert result['result'] == 'APPLIED' and state.mode == 'RUNNING' and state.applied.revision == 2
        assert set(seen) == set(j.scope.registered_scopes)
        assert state.applied.safety_evidence_ids == ('broker','evidence','calendar','authority')
        # A control state supplies neither acceptance receipt nor account permission.
        assert not hasattr(state, 'activation_receipt') and not hasattr(a,'clear_freeze')
        assert a.apply_pending() == ()
    finally: leader.close()


@pytest.mark.parametrize('gate', ['broker_complete','evidence_complete','calendar_confirmed','authority_current',
                                 'safety_latched','frozen_subjects','expired','missing','wrong_scope'])
def test_service_resume_uncertain_gates_rejected_preserves_freeze_and_kill(tmp_path,gate):
    j, _ = store(tmp_path)
    def validate(scope,now):
        if gate == 'missing': return None
        if gate == 'expired': return safety(scope,now-timedelta(seconds=20))
        if gate == 'wrong_scope': return safety(ServiceScope(account_scope_hash='e'*64,execution_target='mock'),now)
        changes = {gate: True if gate=='safety_latched' else ('000660',) if gate=='frozen_subjects' else False}
        return safety(scope,now,**changes)
    a, leader = applier(j,validate=validate)
    try:
        j.request_writer(actor='owner').append_request(request(j,'KILL'))
        a.apply_pending()
        j.request_writer(actor='owner').append_request(request(j,'RESUME',1,'resume'))
        result=a.apply_pending()[0]
        assert result['result'] == 'REJECTED'
        assert j.reader().effective_state(SCOPE).mode == 'KILLED'
        assert j.reader().effective_state(SCOPE).applied.revision == 1
        assert j.reader().effective_state(SCOPE).pending_request_ids == ()
        assert result['reason_code'] in ('SAFETY_BLOCKED','SAFETY_UNAVAILABLE','SAFETY_STALE')
    finally: leader.close()


def test_service_queued_stale_resume_followed_by_kill_never_running(tmp_path):
    j, _ = store(tmp_path)
    a, leader = applier(j)
    try:
        j.request_writer(actor='owner').append_request(request(j,'RESUME'))
        j.request_writer(actor='owner').append_request(request(j,'KILL',1,'kill'))
        results = a.apply_pending()
        assert [r['result'] for r in results] == ['CONFLICT','APPLIED']
        assert all(r['mode'] != 'RUNNING' for r in results)
        assert j.reader().effective_state(SCOPE).mode == 'KILLED'
    finally: leader.close()


def accept_kill_child(settings_json, revision, returned):
    from trading_bot.control_store import ControlStore
    from trading_bot.service_config import ServiceSettings
    j = ControlStore(ServiceSettings.model_validate_json(settings_json),clock=FakeServiceClock())
    result=j.request_writer(actor='owner').append_request(request(j,'KILL',revision,'concurrent-kill'))
    returned.put(result.status)


def test_service_resume_checks_outside_lock_two_process_restriction_wins(tmp_path):
    j, _ = store(tmp_path)
    ctx = multiprocessing.get_context('spawn')
    statuses = []
    def validate(scope,now):
        output=ctx.Queue()
        child=ctx.Process(target=accept_kill_child,args=(j.settings.model_dump_json(),1,output))
        child.start(); child.join(5)
        if child.is_alive(): child.terminate(); child.join(); pytest.fail('validation held global lock')
        assert child.exitcode == 0
        statuses.append(output.get(timeout=1)); output.close(); output.join_thread()
        return safety(scope,now)
    a, leader = applier(j,validate=validate)
    try:
        j.request_writer(actor='owner').append_request(request(j,'RESUME'))
        result = a.apply_pending(limit=1)[0]
        assert statuses == ['REQUESTED'] and result['result'] == 'CONFLICT'
        assert j.reader().effective_state(SCOPE).mode == 'KILLED'
        assert j.reader().effective_state(SCOPE).applied.mode == 'PAUSED'
    finally: leader.close()


def test_service_resume_source_change_and_expiry_between_validation_commit(tmp_path):
    j, clock = store(tmp_path)
    original = safety()
    def validate(scope,now): return original
    def current(scope,now):
        clock.advance(11)
        return original
    a, leader = applier(j,validate=validate,current=current)
    try:
        j.request_writer(actor='owner').append_request(request(j,'RESUME'))
        result=a.apply_pending()[0]
        assert result['result'] == 'REJECTED' and result['reason_code'] == 'SAFETY_STALE'
        assert j.reader().effective_state(SCOPE).mode == 'PAUSED'
    finally: leader.close()


def test_service_resume_changed_evidence_and_failed_application_remain_restrictive(tmp_path):
    j, _ = store(tmp_path)
    from trading_bot.service_models import SourceHash
    def current(scope,now):
        original = safety(scope,now)
        return original.model_copy(update={'source_hashes': (SourceHash(source_id='broker',source_hash='f'*64),
            *original.source_hashes[1:])})
    a, leader = applier(j,current=current)
    try:
        j.request_writer(actor='owner').append_request(request(j,'RESUME'))
        result = a.apply_pending()[0]
        assert result['result']=='REJECTED' and result['reason_code']=='SAFETY_SOURCE_CHANGED'
        j.request_writer(actor='owner').append_request(request(j,'KILL',1,'kill'))
        with sqlite3.connect(j.path) as c:
            c.execute("CREATE TRIGGER fail_application BEFORE INSERT ON control_applications BEGIN SELECT RAISE(ABORT,'failure'); END")
        with pytest.raises(sqlite3.DatabaseError): a.apply_pending()
        assert j.reader().effective_state(SCOPE).mode=='KILLED'
        assert j.reader().effective_state(SCOPE).applied.revision==0
    finally: leader.close()


def test_service_admission_evidence_honest_unique_unknown_no_replay(tmp_path):
    j, _ = store(tmp_path)
    with j.admission_lock() as lock:
        aid=j._record_admission(lock,scope=SCOPE,intent_id='intent',submission_id='post',control_revision=0,admitted_at=NOW)
        assert j.reader().list_admissions()[0]['state']=='IN_FLIGHT'
        j._finish_admission(lock,aid,state='UNKNOWN',finished_at=NOW)
        with pytest.raises(sqlite3.IntegrityError):
            j._record_admission(lock,scope=SCOPE,intent_id='intent',submission_id='retry',control_revision=0,admitted_at=NOW)
        with pytest.raises(ValueError): j._finish_admission(lock,aid,state='FINISHED',finished_at=NOW)
    j.request_writer(actor='owner').append_request(request(j,'KILL'))
    assert j.reader().list_admissions()[0]['state']=='UNKNOWN'
    with pytest.raises(ValueError): j._record_admission(None,scope=SCOPE,intent_id='new',submission_id='post2',control_revision=1,admitted_at=NOW)


def test_service_pending_pause_blocks_running_and_foreign_resume_cannot_weaken(tmp_path):
    j, _ = store(tmp_path)
    a, leader = applier(j)
    try:
        j.request_writer(actor='owner').append_request(request(j,'RESUME'))
        a.apply_pending()
        assert j.reader().effective_state(SCOPE).mode=='RUNNING'
        j.request_writer(actor='owner').append_request(request(j,'PAUSE',1,'pause'))
        state=j.reader().effective_state(SCOPE)
        assert state.applied.mode=='RUNNING' and state.mode=='PAUSED'
        assert not state.allows_buy and not state.allows_daily and state.allows_risk_sell
        a.apply_pending()
        j.request_writer(actor='other').append_request(request(j,'RESUME',2,'foreign',actor='other'))
        result=a.apply_pending()[0]
        assert result['result']=='REJECTED' and result['reason_code']=='OWNER_REQUIRED'
        assert j.reader().effective_state(SCOPE).mode=='PAUSED'
    finally: leader.close()


def test_service_resume_validator_exception_never_grants_authority(tmp_path):
    j, _ = store(tmp_path)
    def unavailable(scope,now): raise RuntimeError('private provider payload')
    a, leader = applier(j,validate=unavailable)
    try:
        j.request_writer(actor='owner').append_request(request(j,'RESUME'))
        result=a.apply_pending()[0]
        assert result['result']=='REJECTED' and result['reason_code']=='SAFETY_UNAVAILABLE'
        assert 'private' not in str(j.reader().list_applications())
        assert j.reader().effective_state(SCOPE).mode=='PAUSED'
    finally: leader.close()
