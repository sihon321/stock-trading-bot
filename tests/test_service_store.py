from datetime import timedelta
import importlib
import os
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

from tests.service_fixtures import FakeServiceClock, NOW, SCOPE, TempServiceTopology
from trading_bot.service_models import LogicalJobKey, ProviderCallAdmission, ServiceExpectation


def store(tmp_path):
    module = importlib.import_module('trading_bot.service_store')
    clock = FakeServiceClock()
    journal = module.ServiceJournal(TempServiceTopology(tmp_path).registration(), clock=clock)
    journal.initialize()
    return journal, clock


def key():
    return LogicalJobKey(scope=SCOPE, trading_date_kst=NOW.date(), kind='DAILY')


def claim(journal, owner='g1'):
    return journal.claim_job(key(), due_at=NOW, dispatch_deadline_at=NOW + timedelta(minutes=20), owner_generation=owner)


def admission():
    return ProviderCallAdmission(dispatch_id='dispatch1', evaluation_id='eval1', scope=SCOPE,
        trading_date_kst=NOW.date(), envelope_hash='b'*64, state='PREPARED', reason_code='READY',
        control_revision=0, session_source_id='session1', observed_at=NOW, invocation_started_at=None)


def consumed():
    return dict(dispatch_id='dispatch1', evaluation_id='eval1', account_scope_hash=SCOPE.account_scope_hash,
        execution_target='mock', trading_date_kst=NOW.date().isoformat(), envelope_hash='b'*64,
        dispatch_state='DISPATCHED', dispatch_started_at=NOW.isoformat())


def expectation(producer='OBSERVER_DERIVED', **updates):
    values = dict(expectation_id='caller-id', scope=SCOPE, trading_date_kst=NOW.date(), kind='DAILY',
        state='EXPECTED', producer_kind=producer, source_id='inputs1', source_hash='c'*64,
        observed_at=NOW, effective_at=NOW, eligibility='ELIGIBLE', continuous_open=NOW,
        continuous_close=NOW+timedelta(hours=6), due_at=NOW+timedelta(minutes=10),
        deadline_at=NOW+timedelta(minutes=20), config_hash='d'*64, config_effective_at=NOW,
        login_source_id='login1', login_effective_at=NOW, session_source_id='session1',
        session_source_hash='e'*64, control_revision=0, controls_source_id='controls1',
        controls_observed_at=NOW, controls_effective_at=NOW, reason_code='ELIGIBLE')
    return ServiceExpectation(**(values | updates))


def test_owned_migration_idempotence_rollback_and_foreign_rejection(tmp_path):
    m = importlib.import_module('trading_bot.service_store')
    settings = TempServiceTopology(tmp_path).registration()
    j = m.ServiceJournal(settings)
    with pytest.raises(RuntimeError):
        j.initialize(fail_after_step='jobs')
    with sqlite3.connect(settings.service_db_path) as c:
        assert c.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall() == []
    j.initialize(); j.initialize()
    assert settings.service_db_path.stat().st_mode & 0o777 == 0o600
    assert settings.service_db_path.parent.stat().st_mode & 0o777 == 0o700
    with sqlite3.connect(settings.service_db_path) as c:
        c.execute("UPDATE service_metadata SET owner='foreign'")
    with pytest.raises(ValueError): j.initialize()


@pytest.mark.parametrize('unsafe', ['symlink', 'hardlink', 'version', 'permissions'])
def test_unsafe_store_rejected(tmp_path, unsafe):
    j, _ = store(tmp_path)
    path = j.path
    if unsafe == 'symlink':
        path.rename(path.with_suffix('.original')); path.symlink_to(path.with_suffix('.original'))
    elif unsafe == 'hardlink': os.link(path, path.with_suffix('.linked'))
    elif unsafe == 'version':
        with sqlite3.connect(path) as c: c.execute('UPDATE service_metadata SET version=99')
    else: path.chmod(0o644)
    with pytest.raises(ValueError): j.initialize()


def test_concurrent_claim_and_immutable_ordered_universe(tmp_path):
    j, _ = store(tmp_path)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(lambda owner: claim(j, owner), ('g1', 'g2')))
    assert sum(r is not None for r in results) == 1
    job_id = key().logical_id
    assert j.commit_universe(job_id, ('000660', '005930')) == j.commit_universe(job_id, ('000660', '005930'))
    with pytest.raises(ValueError): j.commit_universe(job_id, ('005930', '000660'))
    j.append_job_event(job_id, 'RUNNING', reason_code='INPUT_COMMITTED', source_ids=('input1',))
    j.append_job_event(job_id, 'UNKNOWN', reason_code='CRASH')
    assert [r['sequence'] for r in j.list_events(job_id)] == [1, 2, 3]
    assert j.load_job(job_id)['universe_json'] == '["000660","005930"]'
    assert claim(j, 'after-crash') is None
    with j.connection() as c:
        with pytest.raises(sqlite3.IntegrityError): c.execute('UPDATE service_job_events SET state=?', ('DUE',))


def test_restart_reservations_persist_and_attention_requires_explicit_validated_reset(tmp_path):
    j, clock = store(tmp_path)
    for i in range(3):
        assert j.reserve_restart(f'g{i}', reason='UNEXPECTED_EXIT')
        clock.advance(10)
    assert not j.reserve_restart('fourth', reason='UNEXPECTED_EXIT')
    clock.advance(700)
    assert not j.reserve_restart('late', reason='UNEXPECTED_EXIT')
    assert not j.request_attention_reset(safety_validated=False, recovery_validated=True)
    assert j.request_attention_reset(safety_validated=True, recovery_validated=True)
    assert j.reserve_restart('after-reset', reason='UNEXPECTED_EXIT')
    with j.connection() as c:
        assert c.execute('SELECT COUNT(*) FROM service_restart_attempts').fetchone()[0] == 4
        assert c.execute('SELECT COUNT(*) FROM service_launcher_events').fetchone()[0] == 2
        assert c.execute('SELECT state FROM service_attention_events ORDER BY event_id DESC LIMIT 1').fetchone()[0] == 'RESET'


def test_restart_clock_reversal_and_unknown_predecessor_fail_closed(tmp_path):
    j, clock = store(tmp_path)
    assert j.reserve_restart('g1', reason='CRASH')
    clock.advance(-1)
    assert not j.reserve_restart('g2', reason='CRASH')
    clock.advance(1000)
    assert not j.reserve_restart('g3', reason='CRASH')
    assert not j.request_attention_reset(safety_validated=True, recovery_validated=False)


def test_provider_single_consumed_handoff_and_bound_narrow_writer(tmp_path):
    j, _ = store(tmp_path)
    with pytest.raises(ValueError): j.prepare_provider_admission(admission(), consumed_dispatch=consumed() | {'dispatch_state':'NEVER_DISPATCHED'})
    writer = j.prepare_provider_admission(admission(), consumed_dispatch=consumed())
    assert not hasattr(writer, 'claim_job') and not hasattr(writer, 'initialize')
    with pytest.raises(ValueError): writer.transition_prepared('IN_FLIGHT', reason_code='ENTERED', observed_at=NOW)
    writer.transition_prepared('SUPPRESSED_NO_CALL', reason_code='CUTOFF', observed_at=NOW)
    assert j.load_provider_admission('dispatch1').invocation_started_at is None
    with pytest.raises(ValueError): j.prepare_provider_admission(admission(), consumed_dispatch=consumed())
    with pytest.raises(ValueError): writer.transition_prepared('IN_FLIGHT', reason_code='ENTERED', observed_at=NOW, invocation_started_at=NOW)
    assert not j.load_provider_admission('dispatch1').restores_dispatch_authority


def test_provider_unknown_and_finished_cannot_replay(tmp_path):
    j, _ = store(tmp_path)
    writer = j.prepare_provider_admission(admission(), consumed_dispatch=consumed())
    writer.transition_prepared('IN_FLIGHT', reason_code='ENTERED', observed_at=NOW, invocation_started_at=NOW)
    writer.transition_prepared('UNKNOWN', reason_code='CHILD_CRASH', observed_at=NOW+timedelta(seconds=1))
    with pytest.raises(ValueError): writer.transition_prepared('FINISHED', reason_code='LATE', observed_at=NOW+timedelta(seconds=2))
    with pytest.raises(ValueError): j.prepare_provider_admission(admission(), consumed_dispatch=consumed())


def test_expectation_scoped_append_only_provenance_and_runtime_separation(tmp_path):
    j, _ = store(tmp_path)
    writer = j.expectation_writer()
    first = writer.record_derived(expectation())
    assert first == writer.record_derived(expectation())
    second = writer.record_derived(expectation(config_hash='f'*64))
    assert second != first
    with pytest.raises(ValueError): writer.record_derived(expectation('RUNTIME_OBSERVED'))
    j.record_expectation(expectation('RUNTIME_OBSERVED'))
    writer.record_source_health(scope=SCOPE, trading_date_kst=NOW.date(), source_kind='SESSION',
        source_id='session1', state='UNKNOWN', reason_code='UNAVAILABLE', observed_at=NOW)
    assert not hasattr(writer, 'connection') and not hasattr(writer, 'heartbeat')
    with j.connection() as c:
        assert c.execute('SELECT COUNT(*) FROM service_expectations').fetchone()[0] == 3
        with pytest.raises(sqlite3.IntegrityError): c.execute('DELETE FROM service_expectations')
