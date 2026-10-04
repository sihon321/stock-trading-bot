import importlib
import multiprocessing
import os
import sqlite3
from datetime import timedelta

import pytest

from tests.service_fixtures import FakeServiceClock, NOW, SCOPE, TempServiceTopology


def _hold(settings, ready, release):
    from trading_bot.service_leader import ServiceLeader
    from trading_bot.service_store import ServiceJournal
    journal = ServiceJournal(settings, clock=FakeServiceClock())
    with ServiceLeader(settings, journal=journal) as leader:
        journal.heartbeat('worker', leader.generation_id, phase='ACTIVE', observed_at=NOW-timedelta(seconds=1000))
        ready.put((leader.generation_id, leader.state))
        release.wait(30)


def setup(tmp_path):
    from trading_bot.service_store import ServiceJournal
    module = importlib.import_module('trading_bot.service_leader')
    settings = TempServiceTopology(tmp_path).registration()
    clock = FakeServiceClock()
    journal = ServiceJournal(settings, clock=clock)
    journal.initialize()
    return module, settings, journal, clock


def test_spawn_live_owner_cannot_be_displaced_by_stale_heartbeat(tmp_path):
    module, settings, journal, _ = setup(tmp_path)
    ctx=multiprocessing.get_context('spawn')
    ready,release=ctx.Queue(),ctx.Event()
    child=ctx.Process(target=_hold,args=(settings,ready,release)); child.start()
    try:
        generation,state=ready.get(timeout=10)
        assert state=='RUNNING'
        with pytest.raises(module.ServiceLeaderBusy):
            module.ServiceLeader(settings,journal=journal).acquire()
        with journal.connection() as c:
            assert c.execute('SELECT COUNT(*) FROM service_generations').fetchone()[0]==1
            assert c.execute('SELECT COUNT(*) FROM service_restart_attempts').fetchone()[0]==0
    finally:
        release.set(); child.join(10)
        if child.is_alive(): child.kill(); child.join(5)
    assert child.exitcode==0
    with module.ServiceLeader(settings,journal=journal) as leader:
        assert leader.generation_id!=generation and leader.state=='RUNNING'


def test_killed_owner_enters_recovery_retaining_jobs_and_restart_reservation(tmp_path):
    module, settings, journal, clock = setup(tmp_path)
    from trading_bot.service_models import LogicalJobKey
    key=LogicalJobKey(scope=SCOPE,trading_date_kst=NOW.date(),kind='DAILY')
    job=journal.claim_job(key,due_at=NOW,dispatch_deadline_at=NOW+timedelta(minutes=20),owner_generation='previous')
    ctx=multiprocessing.get_context('spawn'); ready,release=ctx.Queue(),ctx.Event()
    child=ctx.Process(target=_hold,args=(settings,ready,release)); child.start()
    try:
        previous,_=ready.get(timeout=10)
    finally:
        child.kill(); child.join(10)
    clock.advance(5)
    with module.ServiceLeader(settings,journal=journal) as leader:
        assert leader.state=='RECOVERY_ONLY'
        leader.assert_owner()
        assert journal.load_job(job)['job_id']==job
        with journal.connection() as c:
            assert c.execute('SELECT state FROM service_generations WHERE generation_id=?',(previous,)).fetchone()[0]=='UNEXPECTED_EXIT'
            assert c.execute('SELECT generation_id FROM service_restart_attempts').fetchone()[0]==leader.generation_id


def test_exhausted_generation_releases_lock_and_never_constructs_worker(tmp_path):
    module,settings,journal,clock=setup(tmp_path)
    for i in range(3):
        leader=module.ServiceLeader(settings,journal=journal).acquire()
        leader.close(clean_stop=False)
        clock.advance(1)
    leader=module.ServiceLeader(settings,journal=journal).acquire()
    leader.close(clean_stop=False)
    with pytest.raises(module.ServiceRestartDenied):
        module.ServiceLeader(settings,journal=journal).acquire()
    clock.advance(1000)
    with pytest.raises(module.ServiceRestartDenied):
        module.ServiceLeader(settings,journal=journal).acquire()
    assert journal.request_attention_reset(safety_validated=True,recovery_validated=True)
    with module.ServiceLeader(settings,journal=journal) as leader:
        assert leader.state=='RECOVERY_ONLY'


def test_owner_checks_close_inode_and_no_account_capability(tmp_path):
    module,settings,journal,_=setup(tmp_path)
    leader=module.ServiceLeader(settings,journal=journal).acquire()
    assert os.get_inheritable(leader._lock_fd) is False
    assert leader.lock_path.name=='service-leader.lock'
    assert leader.lock_path.stat().st_mode&0o777==0o600
    assert not hasattr(leader,'submit') and not hasattr(leader,'assert_active_owner')
    assert leader.lock_path.name!=f'{SCOPE.account_scope_hash}.lock'
    leader.close(clean_stop=True)
    with pytest.raises(module.ServiceOwnershipLost): leader.assert_owner()


def test_nonowner_process_and_changed_durable_generation_fail_closed(tmp_path, monkeypatch):
    module,settings,journal,_=setup(tmp_path)
    leader=module.ServiceLeader(settings,journal=journal).acquire()
    original_pid=os.getpid()
    with monkeypatch.context() as patch:
        patch.setattr(module.os,'getpid',lambda: original_pid+1)
        with pytest.raises(module.ServiceOwnershipLost): leader.assert_owner()
    with journal.connection() as c:
        c.execute("UPDATE service_generations SET state='UNEXPECTED_EXIT' WHERE generation_id=?",(leader.generation_id,))
    with pytest.raises(module.ServiceOwnershipLost): leader.assert_owner()
    leader.close(clean_stop=False)


def test_replaced_lock_inode_is_never_accepted(tmp_path):
    module,settings,journal,_=setup(tmp_path)
    leader=module.ServiceLeader(settings,journal=journal).acquire()
    leader.lock_path.rename(leader.lock_path.with_suffix('.old'))
    leader.lock_path.touch(mode=0o600)
    with pytest.raises(module.ServiceOwnershipLost): leader.assert_owner()
    leader.close(clean_stop=False)


def test_automatic_launcher_attempt_counts_even_after_clean_stop(tmp_path):
    module,settings,journal,_=setup(tmp_path)
    with module.ServiceLeader(settings,journal=journal): pass
    for _ in range(3):
        with module.ServiceLeader(settings,journal=journal,automatic_restart=True): pass
    with pytest.raises(module.ServiceRestartDenied):
        module.ServiceLeader(settings,journal=journal,automatic_restart=True).acquire()
