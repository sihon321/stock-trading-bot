"""Account-scoped process exclusion and durable mutation authority."""

from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import os
import re
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Mapping, Sequence

from trading_bot.audit_models import MutationLeaseEventType, MutationLeaseState
from trading_bot.portfolio import PortfolioCompleteness, PortfolioSnapshot
from trading_bot.portfolio_store import append_portfolio_snapshot


_HASH = re.compile(r"[0-9a-f]{64}")
_RECOVERY_STATES = {
    MutationLeaseState.ACQUIRING.value,
    MutationLeaseState.RECOVERY.value,
    MutationLeaseState.ACTIVE.value,
    MutationLeaseState.LOST.value,
    MutationLeaseState.RECOVERY_BLOCKED.value,
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime:
    stamp = value or _now()
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    return stamp


def _bounded(value: str, name: str, *, maximum: int = 128) -> str:
    result = str(value).strip()
    if not result or len(result) > maximum or re.fullmatch(
        r"[A-Za-z0-9_.:/-]+", result
    ) is None:
        raise ValueError(f"{name} must be a bounded stable identifier")
    return result


def _scope_hash(value: str) -> str:
    candidate = str(value).strip().lower()
    if _HASH.fullmatch(candidate):
        return candidate
    if not candidate:
        raise ValueError("account scope is required")
    return hashlib.sha256(candidate.encode("utf-8")).hexdigest()


def _event(
    conn: sqlite3.Connection,
    *,
    scope: str,
    token: str,
    event_type: MutationLeaseEventType,
    from_state: str | None,
    to_state: MutationLeaseState,
    origin_cycle_id: str | None,
    observer_cycle_id: str | None,
    observed_at: datetime,
    detail: Mapping[str, Any] | None = None,
) -> None:
    clean: dict[str, str | int | float | bool | None] = {}
    for key, value in (detail or {}).items():
        if len(key) > 64 or value is not None and not isinstance(
            value, (str, int, float, bool)
        ):
            raise ValueError("lease event detail must contain bounded scalar facts")
        if any(marker in key.lower() for marker in ("secret", "token", "credential", "raw")):
            raise ValueError("lease event detail contains a forbidden field")
        if isinstance(value, str) and len(value) > 128:
            raise ValueError("lease event detail value is too long")
        clean[key] = value
    conn.execute(
        """INSERT INTO mutation_lease_events(
           account_scope_hash, owner_token, event_type, from_state, to_state,
           origin_cycle_id, observer_cycle_id, detail_json, observed_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            scope,
            token,
            event_type.value,
            from_state,
            to_state.value,
            origin_cycle_id,
            observer_cycle_id,
            json.dumps(clean, sort_keys=True),
            observed_at.isoformat(),
        ),
    )


class LeaseBusyError(RuntimeError):
    """A live local process already owns the account lock."""

    def __init__(self, owner_metadata: Mapping[str, str | int]) -> None:
        self.owner_metadata = MappingProxyType(dict(owner_metadata))
        super().__init__("account mutation lease is busy")


class LeaseOwnershipLost(RuntimeError):
    """The durable row no longer grants this owner POST authority."""


class LeaseRecoveryBlocked(RuntimeError):
    """Fresh broker recovery could not prove determinate account state."""


class MutationLease:
    def __init__(
        self,
        *,
        conn: sqlite3.Connection,
        account_scope_hash: str,
        owner_token: str,
        cycle_id: str,
        lock_path: Path,
        lock_fd: int,
        state: MutationLeaseState,
        prior_owner_token: str | None,
        prior_cycle_id: str | None,
        acquired_at: datetime,
    ) -> None:
        self._conn = conn
        self.account_scope_hash = account_scope_hash
        self.owner_token = owner_token
        self.cycle_id = cycle_id
        self.lock_path = str(lock_path)
        self._lock_fd = lock_fd
        self.state = state
        self.prior_owner_token = prior_owner_token
        self.prior_cycle_id = prior_cycle_id
        self.acquired_at = acquired_at
        self.closed = False

    @property
    def recovery_required(self) -> bool:
        return self.state is MutationLeaseState.RECOVERY

    def _mark_lost(self, observed_at: datetime) -> None:
        if self.state is MutationLeaseState.LOST:
            return
        previous = self.state
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            _event(
                self._conn,
                scope=self.account_scope_hash,
                token=self.owner_token,
                event_type=MutationLeaseEventType.LOST,
                from_state=previous.value,
                to_state=MutationLeaseState.LOST,
                origin_cycle_id=self.cycle_id,
                observer_cycle_id=self.cycle_id,
                observed_at=observed_at,
                detail={"reason": "OWNER_ROW_MISMATCH"},
            )
            self._conn.commit()
        except Exception:
            self._conn.rollback()
            raise
        finally:
            self.state = MutationLeaseState.LOST

    def assert_active_owner(self, *, observed_at: datetime | None = None) -> None:
        stamp = _aware(observed_at)
        if self.closed:
            raise LeaseOwnershipLost("mutation lease is closed")
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            cursor = self._conn.execute(
                """UPDATE mutation_leases SET heartbeat_at=heartbeat_at
                   WHERE account_scope_hash=? AND owner_token=? AND state=?""",
                (
                    self.account_scope_hash,
                    self.owner_token,
                    MutationLeaseState.ACTIVE.value,
                ),
            )
            if cursor.rowcount != 1:
                self._conn.rollback()
                self._mark_lost(stamp)
                raise LeaseOwnershipLost("active mutation ownership was lost")
            self._conn.commit()
        except LeaseOwnershipLost:
            raise
        except Exception:
            self._conn.rollback()
            self._mark_lost(stamp)
            raise LeaseOwnershipLost("active mutation ownership could not be proven")

    def renew(self, *, observed_at: datetime | None = None) -> None:
        stamp = _aware(observed_at)
        if self.closed:
            raise LeaseOwnershipLost("mutation lease is closed")
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            cursor = self._conn.execute(
                """UPDATE mutation_leases SET heartbeat_at=?
                   WHERE account_scope_hash=? AND owner_token=? AND state=?""",
                (
                    stamp.isoformat(),
                    self.account_scope_hash,
                    self.owner_token,
                    MutationLeaseState.ACTIVE.value,
                ),
            )
            if cursor.rowcount != 1:
                self._conn.rollback()
                self._mark_lost(stamp)
                raise LeaseOwnershipLost("mutation lease renewal failed")
            _event(
                self._conn,
                scope=self.account_scope_hash,
                token=self.owner_token,
                event_type=MutationLeaseEventType.HEARTBEAT,
                from_state=MutationLeaseState.ACTIVE.value,
                to_state=MutationLeaseState.ACTIVE,
                origin_cycle_id=self.cycle_id,
                observer_cycle_id=self.cycle_id,
                observed_at=stamp,
            )
            self._conn.commit()
        except LeaseOwnershipLost:
            raise
        except Exception:
            self._conn.rollback()
            self._mark_lost(stamp)
            raise LeaseOwnershipLost("mutation lease renewal failed")

    def _transition_recovery(
        self,
        target: MutationLeaseState,
        event_type: MutationLeaseEventType,
        *,
        observed_at: datetime,
        detail: Mapping[str, Any] | None = None,
    ) -> None:
        try:
            self._conn.execute("BEGIN IMMEDIATE")
            cursor = self._conn.execute(
                """UPDATE mutation_leases SET state=?, heartbeat_at=?
                   WHERE account_scope_hash=? AND owner_token=? AND state=?""",
                (
                    target.value,
                    observed_at.isoformat(),
                    self.account_scope_hash,
                    self.owner_token,
                    MutationLeaseState.RECOVERY.value,
                ),
            )
            if cursor.rowcount != 1:
                self._conn.rollback()
                self._mark_lost(observed_at)
                raise LeaseOwnershipLost("recovery ownership was lost")
            _event(
                self._conn,
                scope=self.account_scope_hash,
                token=self.owner_token,
                event_type=event_type,
                from_state=MutationLeaseState.RECOVERY.value,
                to_state=target,
                origin_cycle_id=self.prior_cycle_id,
                observer_cycle_id=self.cycle_id,
                observed_at=observed_at,
                detail=detail,
            )
            self._conn.commit()
            self.state = target
        except (LeaseOwnershipLost, LeaseRecoveryBlocked):
            raise
        except Exception:
            self._conn.rollback()
            raise

    def recover_to_active(
        self,
        *,
        terminalize_prior_cycles: Callable[[], Any],
        query_fresh_snapshot: Callable[[], PortfolioSnapshot],
        reconcile_prior_orders: Callable[[PortfolioSnapshot], Any],
        observed_at: datetime | None = None,
    ) -> PortfolioSnapshot:
        """Recover abandoned evidence with no POST authority until every proof passes."""

        stamp = _aware(observed_at)
        if self.closed or self.state is not MutationLeaseState.RECOVERY:
            raise LeaseOwnershipLost("lease is not the current recovery owner")
        try:
            terminalized = terminalize_prior_cycles()
            if terminalized is False:
                raise LeaseRecoveryBlocked("prior cycles could not be terminalized")
            snapshot = query_fresh_snapshot()
            if not isinstance(snapshot, PortfolioSnapshot):
                raise LeaseRecoveryBlocked("recovery requires a portfolio snapshot")
            if (
                snapshot.completeness is not PortfolioCompleteness.COMPLETE
                or not snapshot.mutation_capable
                or snapshot.account_scope_hash != self.account_scope_hash
                or snapshot.observed_at < self.acquired_at
            ):
                raise LeaseRecoveryBlocked("fresh complete broker truth was not proven")
            append_portfolio_snapshot(
                self._conn,
                snapshot,
                cycle_id=self.cycle_id,
                observation_id=f"recovery-{uuid.uuid4()}",
            )
            reconciliation = reconcile_prior_orders(snapshot)
            if not _reconciliation_is_determinate(reconciliation):
                raise LeaseRecoveryBlocked("prior broker subjects remain unresolved")
            self._transition_recovery(
                MutationLeaseState.ACTIVE,
                MutationLeaseEventType.ACTIVE,
                observed_at=stamp,
                detail={"snapshot_id": snapshot.snapshot_id},
            )
            return snapshot
        except LeaseOwnershipLost:
            raise
        except Exception as exc:
            if self.state is MutationLeaseState.RECOVERY:
                self._transition_recovery(
                    MutationLeaseState.RECOVERY_BLOCKED,
                    MutationLeaseEventType.RECOVERY_BLOCKED,
                    observed_at=stamp,
                    detail={"failure": type(exc).__name__},
                )
            if isinstance(exc, LeaseRecoveryBlocked):
                raise
            raise LeaseRecoveryBlocked("recovery callback failed") from exc

    def release(self, *, observed_at: datetime | None = None) -> None:
        if self.closed:
            return
        stamp = _aware(observed_at)
        previous = self.state
        if previous is not MutationLeaseState.LOST:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
                cursor = self._conn.execute(
                    """UPDATE mutation_leases SET state=?, heartbeat_at=?
                       WHERE account_scope_hash=? AND owner_token=?""",
                    (
                        MutationLeaseState.RELEASED.value,
                        stamp.isoformat(),
                        self.account_scope_hash,
                        self.owner_token,
                    ),
                )
                if cursor.rowcount == 1:
                    _event(
                        self._conn,
                        scope=self.account_scope_hash,
                        token=self.owner_token,
                        event_type=MutationLeaseEventType.RELEASED,
                        from_state=previous.value,
                        to_state=MutationLeaseState.RELEASED,
                        origin_cycle_id=self.cycle_id,
                        observer_cycle_id=self.cycle_id,
                        observed_at=stamp,
                    )
                    self._conn.commit()
                    self.state = MutationLeaseState.RELEASED
                else:
                    self._conn.rollback()
                    self._mark_lost(stamp)
            except Exception:
                self._conn.rollback()
                raise
        try:
            fcntl.flock(self._lock_fd, fcntl.LOCK_UN)
        finally:
            os.close(self._lock_fd)
            self.closed = True

    def __enter__(self) -> MutationLease:
        return self

    def __exit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
        self.release()


def _busy_metadata(conn: sqlite3.Connection, scope: str) -> dict[str, str | int]:
    row = conn.execute(
        """SELECT pid, command, started_at, heartbeat_at, state
           FROM mutation_leases WHERE account_scope_hash=?""",
        (scope,),
    ).fetchone()
    if row is None:
        return {"state": "LOCKED"}
    keys = ("pid", "command", "started_at", "heartbeat_at", "state")
    return {
        key: int(value) if key == "pid" else str(value)[:128]
        for key, value in zip(keys, row, strict=True)
    }


def acquire_mutation_lease(
    conn: sqlite3.Connection,
    *,
    account_scope_hash: str,
    lock_dir: str | Path,
    command: str,
    cycle_id: str,
    observed_at: datetime | None = None,
) -> MutationLease:
    """Acquire immediately; a held kernel lock is never waited on or stolen."""

    scope = _scope_hash(account_scope_hash)
    normalized_command = _bounded(command, "command", maximum=64)
    normalized_cycle = _bounded(cycle_id, "cycle_id")
    stamp = _aware(observed_at)
    directory = Path(lock_dir)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        directory.chmod(0o700)
    except OSError:
        pass
    lock_path = directory / f"{scope}.lock"
    fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
    os.fchmod(fd, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError as exc:
        os.close(fd)
        if exc.errno in (errno.EACCES, errno.EAGAIN):
            raise LeaseBusyError(_busy_metadata(conn, scope)) from None
        raise

    token = str(uuid.uuid4())
    prior_owner: str | None = None
    prior_cycle: str | None = None
    try:
        conn.execute("BEGIN IMMEDIATE")
        prior = conn.execute(
            "SELECT owner_token, state, cycle_id FROM mutation_leases WHERE account_scope_hash=?",
            (scope,),
        ).fetchone()
        prior_state = str(prior[1]) if prior else None
        prior_owner = str(prior[0]) if prior else None
        prior_cycle = str(prior[2]) if prior else None
        conn.execute(
            """INSERT INTO mutation_leases(
               account_scope_hash, owner_token, state, pid, command,
               started_at, heartbeat_at, cycle_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(account_scope_hash) DO UPDATE SET
               owner_token=excluded.owner_token, state=excluded.state,
               pid=excluded.pid, command=excluded.command,
               started_at=excluded.started_at, heartbeat_at=excluded.heartbeat_at,
               cycle_id=excluded.cycle_id""",
            (
                scope,
                token,
                MutationLeaseState.ACQUIRING.value,
                os.getpid(),
                normalized_command,
                stamp.isoformat(),
                stamp.isoformat(),
                normalized_cycle,
            ),
        )
        _event(
            conn,
            scope=scope,
            token=token,
            event_type=MutationLeaseEventType.ACQUIRING,
            from_state=prior_state,
            to_state=MutationLeaseState.ACQUIRING,
            origin_cycle_id=prior_cycle,
            observer_cycle_id=normalized_cycle,
            observed_at=stamp,
        )
        target = (
            MutationLeaseState.RECOVERY
            if prior_state in _RECOVERY_STATES
            else MutationLeaseState.ACTIVE
        )
        conn.execute(
            """UPDATE mutation_leases SET state=?
               WHERE account_scope_hash=? AND owner_token=? AND state=?""",
            (target.value, scope, token, MutationLeaseState.ACQUIRING.value),
        )
        _event(
            conn,
            scope=scope,
            token=token,
            event_type=(
                MutationLeaseEventType.RECOVERY
                if target is MutationLeaseState.RECOVERY
                else MutationLeaseEventType.ACTIVE
            ),
            from_state=MutationLeaseState.ACQUIRING.value,
            to_state=target,
            origin_cycle_id=prior_cycle,
            observer_cycle_id=normalized_cycle,
            observed_at=stamp,
        )
        conn.commit()
    except Exception:
        conn.rollback()
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)
        raise
    return MutationLease(
        conn=conn,
        account_scope_hash=scope,
        owner_token=token,
        cycle_id=normalized_cycle,
        lock_path=lock_path,
        lock_fd=fd,
        state=target,
        prior_owner_token=prior_owner,
        prior_cycle_id=prior_cycle,
        acquired_at=stamp,
    )


def _reconciliation_is_determinate(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, Mapping):
        return value.get("determinate") is True
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return all(_reconciliation_is_determinate(item) for item in value)
    return False


def recover_to_active(
    lease: MutationLease,
    *,
    terminalize_prior_cycles: Callable[[], Any],
    query_fresh_snapshot: Callable[[], PortfolioSnapshot],
    reconcile_prior_orders: Callable[[PortfolioSnapshot], Any],
    observed_at: datetime | None = None,
) -> PortfolioSnapshot:
    return lease.recover_to_active(
        terminalize_prior_cycles=terminalize_prior_cycles,
        query_fresh_snapshot=query_fresh_snapshot,
        reconcile_prior_orders=reconcile_prior_orders,
        observed_at=observed_at,
    )


def release_after_reconciliation(
    lease: MutationLease,
    *,
    reconcile_submitted: Callable[[], Any],
    terminalize_cycle: Callable[[], Any],
    persist_unresolved: Callable[[], Any] | None = None,
    observed_at: datetime | None = None,
) -> bool:
    """Terminalize, reconcile bounded work, then durably release and unlock.

    The terminal record must exist before a broker query can time out or become
    ambiguous.  A failed or indeterminate query is itself durable evidence when
    the caller supplies an unresolved recorder; neither outcome can postpone
    release of the OS lock descriptor.
    """

    determinate = False
    try:
        terminalize_cycle()
        try:
            determinate = _reconciliation_is_determinate(reconcile_submitted())
        except Exception:
            determinate = False
        if not determinate and persist_unresolved is not None:
            persist_unresolved()
        return determinate
    finally:
        lease.release(observed_at=observed_at)


def stop_after_ownership_loss(
    lease: MutationLease,
    *,
    reconcile_submitted: Callable[[], Any],
    terminalize_cycle: Callable[[], Any],
    persist_unresolved: Callable[[], Any] | None = None,
    observed_at: datetime | None = None,
) -> bool:
    """Use the common no-new-POST shutdown path after owner-token loss."""

    if lease.state is not MutationLeaseState.LOST:
        lease._mark_lost(_aware(observed_at))
    return release_after_reconciliation(
        lease,
        reconcile_submitted=reconcile_submitted,
        terminalize_cycle=terminalize_cycle,
        persist_unresolved=persist_unresolved,
        observed_at=observed_at,
    )


__all__ = [
    "LeaseBusyError",
    "LeaseOwnershipLost",
    "LeaseRecoveryBlocked",
    "MutationLease",
    "acquire_mutation_lease",
    "recover_to_active",
    "release_after_reconciliation",
    "stop_after_ownership_loss",
]
