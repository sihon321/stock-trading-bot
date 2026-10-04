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


@pytest.mark.parametrize('unsafe', ['permissions', 'symlink', 'hardlink', 'version', 'owner', 'lock_permissions', 'registration'])
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
