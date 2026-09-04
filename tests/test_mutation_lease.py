from __future__ import annotations

import multiprocessing
import os
import sqlite3
import stat
import time
from datetime import date, datetime, timedelta, timezone

import pytest

from trading_bot.audit_models import MutationLeaseEventType, MutationLeaseState
from trading_bot.mutation_lease import (
    LeaseBusyError,
    LeaseOwnershipLost,
    acquire_mutation_lease,
)
from trading_bot.portfolio_store import connect_portfolio_store


NOW = datetime(2026, 9, 4, 1, 0, tzinfo=timezone.utc)
SCOPE = "a" * 64


def _hold_lease(db_path: str, lock_dir: str, ready, release) -> None:
    conn = connect_portfolio_store(db_path)
    lease = acquire_mutation_lease(
        conn,
        account_scope_hash=SCOPE,
        lock_dir=lock_dir,
        command="intraday-watch",
        cycle_id="cycle-owner",
    )
    ready.put((lease.state.value, os.path.basename(lease.lock_path)))
    release.get(timeout=5)
    lease.release()
    conn.close()


def test_exclusive_process_owner_is_immediate_and_metadata_is_bounded(tmp_path):
    db_path = tmp_path / "audit.db"
    lock_dir = tmp_path / "locks"
    ready = multiprocessing.Queue()
    release = multiprocessing.Queue()
    child = multiprocessing.Process(
        target=_hold_lease,
        args=(str(db_path), str(lock_dir), ready, release),
    )
    child.start()
    state, filename = ready.get(timeout=5)
    assert state == "ACTIVE"
    assert filename == f"{SCOPE}.lock"

    conn = connect_portfolio_store(db_path)
    started = time.monotonic()
    with pytest.raises(LeaseBusyError) as raised:
        acquire_mutation_lease(
            conn,
            account_scope_hash=SCOPE,
            lock_dir=lock_dir,
            command="run",
            cycle_id="cycle-loser",
        )
    assert time.monotonic() - started < 0.5
    assert raised.value.owner_metadata["command"] == "intraday-watch"
    assert "owner_token" not in raised.value.owner_metadata
    assert all(len(str(value)) <= 128 for value in raised.value.owner_metadata.values())

    release.put(True)
    child.join(timeout=5)
    assert child.exitcode == 0


def test_lock_path_permissions_and_durable_metadata_are_sanitized(tmp_path):
    raw_account = "12345678-01"
    conn = connect_portfolio_store(tmp_path / "audit.db")
    lease = acquire_mutation_lease(
        conn,
        account_scope_hash=raw_account,
        lock_dir=tmp_path / "locks",
        command="run",
        cycle_id="cycle-1",
        observed_at=NOW,
    )

    assert raw_account not in lease.lock_path
    assert raw_account not in os.path.basename(lease.lock_path)
    assert stat.S_IMODE(os.stat(lease.lock_path).st_mode) == 0o600
    stored = conn.execute(
        "SELECT account_scope_hash, command, state FROM mutation_leases"
    ).fetchone()
    assert stored[0] == lease.account_scope_hash
    assert raw_account not in "|".join(str(item) for item in stored)
    assert stored[2] == MutationLeaseState.ACTIVE.value
    assert not conn.in_transaction
    lease.release(observed_at=NOW + timedelta(seconds=1))


def test_active_owner_and_renew_require_exact_token_and_active_state(tmp_path):
    conn = connect_portfolio_store(tmp_path / "audit.db")
    lease = acquire_mutation_lease(
        conn,
        account_scope_hash=SCOPE,
        lock_dir=tmp_path / "locks",
        command="run",
        cycle_id="cycle-1",
        observed_at=NOW,
    )
    lease.assert_active_owner(observed_at=NOW + timedelta(seconds=1))
    lease.renew(observed_at=NOW + timedelta(seconds=2))

    conn.execute(
        "UPDATE mutation_leases SET owner_token='replacement' WHERE account_scope_hash=?",
        (SCOPE,),
    )
    conn.commit()
    post_calls: list[str] = []
    with pytest.raises(LeaseOwnershipLost):
        lease.assert_active_owner(observed_at=NOW + timedelta(seconds=3))
        post_calls.append("POST")
    assert post_calls == []
    assert lease.state is MutationLeaseState.LOST
    assert conn.execute(
        "SELECT event_type FROM mutation_lease_events ORDER BY id DESC LIMIT 1"
    ).fetchone()[0] == MutationLeaseEventType.LOST.value
    assert not conn.in_transaction
    lease.release(observed_at=NOW + timedelta(seconds=4))


def test_release_is_durable_before_kernel_unlock(tmp_path, monkeypatch):
    conn = connect_portfolio_store(tmp_path / "audit.db")
    lease = acquire_mutation_lease(
        conn,
        account_scope_hash=SCOPE,
        lock_dir=tmp_path / "locks",
        command="run",
        cycle_id="cycle-1",
        observed_at=NOW,
    )
    import trading_bot.mutation_lease as module

    real_flock = module.fcntl.flock
    observed_states: list[str] = []

    def inspecting_flock(fd: int, operation: int) -> None:
        if operation == module.fcntl.LOCK_UN:
            observer = sqlite3.connect(tmp_path / "audit.db")
            observed_states.append(
                observer.execute(
                    "SELECT state FROM mutation_leases WHERE account_scope_hash=?",
                    (SCOPE,),
                ).fetchone()[0]
            )
            observer.close()
        real_flock(fd, operation)

    monkeypatch.setattr(module.fcntl, "flock", inspecting_flock)
    lease.release(observed_at=NOW + timedelta(seconds=1))
    assert observed_states == [MutationLeaseState.RELEASED.value]
    assert lease.closed

