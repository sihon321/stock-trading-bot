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
    LeaseRecoveryBlocked,
    acquire_mutation_lease,
    recover_to_active,
    release_after_reconciliation,
    stop_after_ownership_loss,
)
from trading_bot.portfolio import (
    PortfolioAccountSummary,
    PortfolioCompleteness,
    PortfolioSnapshot,
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


def _crash_owner(db_path: str, lock_dir: str, ready) -> None:
    conn = connect_portfolio_store(db_path)
    acquire_mutation_lease(
        conn,
        account_scope_hash=SCOPE,
        lock_dir=lock_dir,
        command="watch",
        cycle_id="origin-cycle",
        observed_at=NOW,
    )
    ready.set()
    time.sleep(30)


def _leave_abandoned_owner(db_path, lock_dir) -> None:
    ready = multiprocessing.Event()
    child = multiprocessing.Process(
        target=_crash_owner,
        args=(str(db_path), str(lock_dir), ready),
    )
    child.start()
    assert ready.wait(timeout=5)
    child.terminate()
    child.join(timeout=5)
    assert child.exitcode is not None


def _snapshot(
    *, completeness: PortfolioCompleteness = PortfolioCompleteness.COMPLETE,
    snapshot_id: str = "recovery-snapshot",
) -> PortfolioSnapshot:
    return PortfolioSnapshot(
        snapshot_id=snapshot_id,
        account_scope_hash=SCOPE,
        trading_date=date(2026, 9, 4),
        previous_trading_date=date(2026, 9, 3),
        observed_at=NOW + timedelta(minutes=1),
        completeness=completeness,
        reason_code=completeness.value,
        daily_page_count=1,
        balance_page_count=1,
        holdings=(),
        orders=(),
        fills=(),
        account=PortfolioAccountSummary(1_000_000, 1_000_000),
    )


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


def test_crashed_owner_enters_recovery_before_fresh_broker_callbacks(tmp_path):
    db_path = tmp_path / "audit.db"
    lock_dir = tmp_path / "locks"
    _leave_abandoned_owner(db_path, lock_dir)
    conn = connect_portfolio_store(db_path)
    lease = acquire_mutation_lease(
        conn,
        account_scope_hash=SCOPE,
        lock_dir=lock_dir,
        command="run",
        cycle_id="observer-cycle",
        observed_at=NOW + timedelta(seconds=30),
    )
    assert lease.state is MutationLeaseState.RECOVERY

    callback_order: list[str] = []

    def terminalize() -> bool:
        assert conn.execute(
            "SELECT state FROM mutation_leases WHERE account_scope_hash=?", (SCOPE,)
        ).fetchone()[0] == MutationLeaseState.RECOVERY.value
        callback_order.append("terminalize")
        return True

    def fresh_snapshot() -> PortfolioSnapshot:
        callback_order.append("snapshot")
        return _snapshot()

    def reconcile(snapshot: PortfolioSnapshot):
        callback_order.append(f"reconcile:{snapshot.snapshot_id}")
        return ({"ticker": "000660", "determinate": True},)

    recovered = recover_to_active(
        lease,
        terminalize_prior_cycles=terminalize,
        query_fresh_snapshot=fresh_snapshot,
        reconcile_prior_orders=reconcile,
        observed_at=NOW + timedelta(minutes=2),
    )
    assert recovered.snapshot_id == "recovery-snapshot"
    assert callback_order == [
        "terminalize",
        "snapshot",
        "reconcile:recovery-snapshot",
    ]
    assert lease.state is MutationLeaseState.ACTIVE
    assert conn.execute(
        "SELECT COUNT(*) FROM portfolio_snapshots WHERE snapshot_id='recovery-snapshot'"
    ).fetchone()[0] == 1
    transition = conn.execute(
        """SELECT event_type, origin_cycle_id, observer_cycle_id
           FROM mutation_lease_events ORDER BY id DESC LIMIT 1"""
    ).fetchone()
    assert transition == (MutationLeaseEventType.ACTIVE.value, "origin-cycle", "observer-cycle")
    lease.release()


@pytest.mark.parametrize("failure", ["incomplete", "ambiguous", "callback"])
def test_recovery_blocked_never_grants_post_authority(tmp_path, failure):
    db_path = tmp_path / failure / "audit.db"
    lock_dir = tmp_path / failure / "locks"
    _leave_abandoned_owner(db_path, lock_dir)
    conn = connect_portfolio_store(db_path)
    lease = acquire_mutation_lease(
        conn,
        account_scope_hash=SCOPE,
        lock_dir=lock_dir,
        command="run",
        cycle_id=f"observer-{failure}",
    )
    post_calls: list[str] = []

    def terminalize():
        if failure == "callback":
            raise RuntimeError("bounded callback failed")
        return True

    def query():
        return _snapshot(
            completeness=(
                PortfolioCompleteness.INCOMPLETE
                if failure == "incomplete"
                else PortfolioCompleteness.COMPLETE
            ),
            snapshot_id=f"snapshot-{failure}",
        )

    def reconcile(_snapshot):
        return ({"ticker": "000660", "determinate": failure != "ambiguous"},)

    with pytest.raises(LeaseRecoveryBlocked):
        recover_to_active(
            lease,
            terminalize_prior_cycles=terminalize,
            query_fresh_snapshot=query,
            reconcile_prior_orders=reconcile,
        )
        post_calls.append("POST")
    assert post_calls == []
    assert lease.state is MutationLeaseState.RECOVERY_BLOCKED
    with pytest.raises(LeaseOwnershipLost):
        lease.assert_active_owner()
    lease.release()


def test_ownership_loss_and_normal_shutdown_reconcile_before_release(tmp_path):
    conn = connect_portfolio_store(tmp_path / "audit.db")
    lease = acquire_mutation_lease(
        conn,
        account_scope_hash=SCOPE,
        lock_dir=tmp_path / "locks",
        command="watch",
        cycle_id="cycle-loss",
    )
    conn.execute(
        "UPDATE mutation_leases SET state=? WHERE account_scope_hash=?",
        (MutationLeaseState.LOST.value, SCOPE),
    )
    conn.commit()
    with pytest.raises(LeaseOwnershipLost):
        lease.renew()

    order: list[str] = []
    result = stop_after_ownership_loss(
        lease,
        reconcile_submitted=lambda: order.append("reconcile") or False,
        terminalize_cycle=lambda: order.append("terminalize"),
    )
    assert result is False
    assert order == ["reconcile", "terminalize"]
    assert lease.closed

    second = acquire_mutation_lease(
        conn,
        account_scope_hash="b" * 64,
        lock_dir=tmp_path / "locks",
        command="run",
        cycle_id="cycle-release",
    )
    normal_order: list[str] = []
    determinate = release_after_reconciliation(
        second,
        reconcile_submitted=lambda: normal_order.append("reconcile") or True,
        terminalize_cycle=lambda: normal_order.append("terminalize"),
    )
    assert determinate is True
    assert normal_order == ["reconcile", "terminalize"]
    assert second.state is MutationLeaseState.RELEASED
    assert second.closed
