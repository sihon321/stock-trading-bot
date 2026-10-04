"""Independent Phase 11 schema owner for portfolio and evaluation evidence."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
from zoneinfo import ZoneInfo

from trading_bot.audit_models import (
    DailyEvaluationEvent,
    DailyEvaluationEventType,
    DailyEvaluationStatus,
    DailyDispatchState,
    OperationalSeverity,
    TransitionNotification,
    TransitionObservation,
    TransitionState,
    sanitize_detail,
    render_transition_notification,
)
from trading_bot.portfolio import PortfolioSnapshot
from trading_bot.service_models import DailyDispatchEnvelope


SCHEMA_VERSION = 4
_TERMINAL_EVENTS = {
    DailyEvaluationEventType.SIGNAL_FINALIZED,
    DailyEvaluationEventType.LLM_UNAVAILABLE,
}


_SCHEMA = (
    """CREATE TABLE portfolio_schema_metadata (
        owner TEXT PRIMARY KEY, version INTEGER NOT NULL)""",
    """CREATE TABLE portfolio_snapshots (
        snapshot_id TEXT PRIMARY KEY, cycle_id TEXT NOT NULL,
        observation_id TEXT NOT NULL UNIQUE, account_scope_hash TEXT NOT NULL,
        trading_date_kst TEXT NOT NULL, previous_trading_date_kst TEXT NOT NULL,
        observed_at TEXT NOT NULL, completeness TEXT NOT NULL, reason_code TEXT NOT NULL,
        daily_page_count INTEGER NOT NULL, balance_page_count INTEGER NOT NULL,
        available_cash REAL NOT NULL, total_evaluation REAL NOT NULL)""",
    """CREATE TABLE portfolio_holdings (
        snapshot_id TEXT NOT NULL REFERENCES portfolio_snapshots(snapshot_id),
        ticker TEXT NOT NULL, total_quantity INTEGER NOT NULL,
        orderable_quantity INTEGER NOT NULL, average_price REAL NOT NULL,
        PRIMARY KEY(snapshot_id, ticker))""",
    """CREATE TABLE portfolio_orders (
        snapshot_id TEXT NOT NULL REFERENCES portfolio_snapshots(snapshot_id),
        order_id TEXT NOT NULL, original_order_id TEXT, ticker TEXT NOT NULL,
        side TEXT NOT NULL, ordered_quantity INTEGER NOT NULL,
        filled_quantity INTEGER NOT NULL, remaining_quantity INTEGER NOT NULL,
        cancelled_quantity INTEGER NOT NULL, rejected_quantity INTEGER NOT NULL,
        limit_price REAL NOT NULL, status TEXT NOT NULL,
        order_date TEXT NOT NULL, order_time TEXT NOT NULL,
        PRIMARY KEY(snapshot_id, order_id))""",
    """CREATE TABLE portfolio_fills (
        snapshot_id TEXT NOT NULL REFERENCES portfolio_snapshots(snapshot_id),
        fill_id TEXT NOT NULL, order_id TEXT NOT NULL, ticker TEXT NOT NULL,
        quantity INTEGER NOT NULL, price REAL NOT NULL,
        PRIMARY KEY(snapshot_id, fill_id))""",
    """CREATE TABLE portfolio_divergences (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_id TEXT NOT NULL REFERENCES portfolio_snapshots(snapshot_id),
        code TEXT NOT NULL, severity TEXT NOT NULL, ticker TEXT,
        order_intent_id TEXT)""",
    """CREATE TABLE daily_evaluations (
        evaluation_id TEXT PRIMARY KEY, trading_date_kst TEXT NOT NULL,
        ticker TEXT NOT NULL, provenance_json TEXT NOT NULL,
        canonical_input BLOB NOT NULL, canonical_input_hash TEXT NOT NULL,
        account_scope_hash TEXT NOT NULL, status TEXT NOT NULL,
        started_at TEXT NOT NULL, finalized_at TEXT,
        UNIQUE(trading_date_kst, ticker))""",
    """CREATE TABLE daily_evaluation_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        evaluation_id TEXT NOT NULL REFERENCES daily_evaluations(evaluation_id),
        event_type TEXT NOT NULL, action TEXT, confidence REAL, reason_code TEXT,
        detail_json TEXT NOT NULL, observed_at TEXT NOT NULL)""",
    """CREATE UNIQUE INDEX ux_daily_evaluation_terminal
        ON daily_evaluation_events(evaluation_id)
        WHERE event_type IN ('SIGNAL_FINALIZED', 'LLM_UNAVAILABLE')""",
    """CREATE TABLE watch_iterations (
        iteration_id TEXT PRIMARY KEY, cycle_id TEXT NOT NULL,
        snapshot_id TEXT REFERENCES portfolio_snapshots(snapshot_id),
        started_at TEXT NOT NULL, terminal_status TEXT)""",
    """CREATE TABLE watch_observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        iteration_id TEXT NOT NULL REFERENCES watch_iterations(iteration_id),
        state_code TEXT NOT NULL, detail_json TEXT NOT NULL, observed_at TEXT NOT NULL)""",
    """CREATE TABLE transition_states (
        id INTEGER PRIMARY KEY AUTOINCREMENT, state_identity TEXT NOT NULL UNIQUE,
        account_scope_hash TEXT NOT NULL, ticker TEXT, event_family TEXT NOT NULL,
        broker_subject_id TEXT, state_code TEXT NOT NULL,
        occurrence_count INTEGER NOT NULL, first_observed_at TEXT NOT NULL,
        last_observed_at TEXT NOT NULL, duration_seconds REAL NOT NULL,
        active INTEGER NOT NULL, severity TEXT NOT NULL,
        last_notification_status TEXT)""",
    """CREATE TABLE transition_observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT, state_identity TEXT NOT NULL,
        state_code TEXT NOT NULL, severity TEXT NOT NULL,
        detail_json TEXT NOT NULL, observed_at TEXT NOT NULL)""",
    """CREATE TABLE transition_notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT, state_identity TEXT NOT NULL,
        event_code TEXT NOT NULL, severity TEXT NOT NULL, text TEXT NOT NULL,
        delivery_status TEXT NOT NULL, failure_category TEXT,
        observed_at TEXT NOT NULL,
        UNIQUE(state_identity, event_code))""",
)


_LEASE_SCHEMA = (
    """CREATE TABLE mutation_leases (
        account_scope_hash TEXT PRIMARY KEY, owner_token TEXT NOT NULL,
        state TEXT NOT NULL, pid INTEGER NOT NULL, command TEXT NOT NULL,
        started_at TEXT NOT NULL, heartbeat_at TEXT NOT NULL,
        cycle_id TEXT NOT NULL)""",
    """CREATE TABLE mutation_lease_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT, account_scope_hash TEXT NOT NULL,
        owner_token TEXT NOT NULL, event_type TEXT NOT NULL,
        from_state TEXT, to_state TEXT NOT NULL,
        origin_cycle_id TEXT, observer_cycle_id TEXT,
        detail_json TEXT NOT NULL, observed_at TEXT NOT NULL)""",
    """CREATE INDEX ix_mutation_lease_events_scope
        ON mutation_lease_events(account_scope_hash, id)""",
)

_DISPATCH_SCHEMA = (
    """CREATE TABLE daily_evaluation_dispatches (
        evaluation_id TEXT PRIMARY KEY REFERENCES daily_evaluations(evaluation_id),
        execution_target TEXT, envelope_json TEXT, envelope_hash TEXT,
        dispatch_state TEXT NOT NULL, dispatch_id TEXT UNIQUE,
        dispatched_at TEXT, finalized_at TEXT, execution_intent_id TEXT)""",
    """CREATE TABLE daily_dispatch_identities (
        evaluation_id TEXT PRIMARY KEY REFERENCES daily_evaluations(evaluation_id),
        account_scope_hash TEXT NOT NULL, execution_target TEXT NOT NULL,
        trading_date_kst TEXT NOT NULL, ticker TEXT NOT NULL,
        UNIQUE(account_scope_hash,execution_target,trading_date_kst,ticker))""",
    """CREATE TRIGGER immutable_daily_dispatch_envelope
        BEFORE UPDATE OF evaluation_id,execution_target,envelope_json,envelope_hash
        ON daily_evaluation_dispatches BEGIN
        SELECT RAISE(ABORT,'immutable dispatch envelope'); END""",
    """CREATE TRIGGER immutable_daily_dispatch_consumption
        BEFORE UPDATE ON daily_evaluation_dispatches
        WHEN (OLD.dispatch_id IS NOT NULL AND
            (NEW.dispatch_id IS NOT OLD.dispatch_id OR NEW.dispatched_at IS NOT OLD.dispatched_at))
          OR (OLD.dispatch_state <> 'NEVER_DISPATCHED' AND
              NEW.dispatch_state IN ('NEVER_DISPATCHED','DISPATCHED'))
        BEGIN SELECT RAISE(ABORT,'consumed dispatch cannot reset'); END""",
    """CREATE TRIGGER immutable_daily_input BEFORE UPDATE OF
        evaluation_id,trading_date_kst,ticker,provenance_json,canonical_input,
        canonical_input_hash,account_scope_hash,started_at ON daily_evaluations
        BEGIN SELECT RAISE(ABORT,'immutable canonical input'); END""",
    """CREATE TRIGGER immutable_daily_dispatch_delete BEFORE DELETE
        ON daily_evaluation_dispatches BEGIN SELECT RAISE(ABORT,'immutable dispatch'); END""",
    """CREATE TRIGGER immutable_daily_identity_update BEFORE UPDATE
        ON daily_dispatch_identities BEGIN SELECT RAISE(ABORT,'immutable dispatch identity'); END""",
    """CREATE TRIGGER immutable_daily_identity_delete BEFORE DELETE
        ON daily_dispatch_identities BEGIN SELECT RAISE(ABORT,'immutable dispatch identity'); END""",
)


@dataclass(frozen=True)
class StoredDailyEvaluation:
    evaluation_id: str
    trading_date_kst: date
    ticker: str
    provenance: tuple[str, ...]
    canonical_input: bytes
    canonical_input_hash: str
    account_scope_hash: str
    status: DailyEvaluationStatus
    started_at: datetime
    finalized_at: datetime | None
    events: tuple[DailyEvaluationEvent, ...]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: datetime | None) -> datetime:
    result = value or _now()
    if result.tzinfo is None or result.utcoffset() is None:
        raise ValueError("timestamp must be timezone-aware")
    return result


def _stable_code(value: str, name: str, *, max_length: int = 128) -> str:
    candidate = str(value).strip()
    if not candidate or len(candidate) > max_length or re.fullmatch(
        r"[A-Za-z0-9_.:-]+", candidate
    ) is None:
        raise ValueError(f"{name} must be a bounded stable identifier")
    return candidate


def portfolio_schema_version(conn: sqlite3.Connection) -> int:
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='portfolio_schema_metadata'"
    ).fetchone()
    if exists is None:
        return 0
    rows = conn.execute("SELECT owner,version FROM portfolio_schema_metadata").fetchall()
    if len(rows) != 1 or rows[0][0] != 'phase11':
        raise RuntimeError('unsupported portfolio schema owner')
    version = rows[0][1]
    if type(version) is not int or version not in {1, 2, 3, 4}:
        raise RuntimeError('unsupported portfolio schema version')
    return version


def migrate_portfolio(
    conn: sqlite3.Connection, *, fail_after_step: str | None = None
) -> None:
    version = portfolio_schema_version(conn)
    if version > SCHEMA_VERSION:
        raise RuntimeError(f"unsupported portfolio schema version: {version}")
    if version == SCHEMA_VERSION:
        return
    try:
        conn.execute("BEGIN IMMEDIATE")
        if version == 0:
            for index, statement in enumerate(_SCHEMA):
                conn.execute(statement)
                if fail_after_step == "snapshots" and index == 1:
                    raise RuntimeError("injected portfolio migration failure")
        if version in {1, 2}:
            columns = {
                str(row[1])
                for row in conn.execute("PRAGMA table_info(transition_states)")
            }
            additions = {
                "account_scope_hash": "TEXT NOT NULL DEFAULT ''",
                "ticker": "TEXT",
                "event_family": "TEXT NOT NULL DEFAULT 'UNKNOWN'",
                "broker_subject_id": "TEXT",
                "duration_seconds": "REAL NOT NULL DEFAULT 0",
                "active": "INTEGER NOT NULL DEFAULT 1",
                "severity": "TEXT NOT NULL DEFAULT 'INFO'",
                "last_notification_status": "TEXT",
            }
            for name, declaration in additions.items():
                if name not in columns:
                    conn.execute(
                        f"ALTER TABLE transition_states ADD COLUMN {name} {declaration}"
                    )
            conn.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS ux_transition_state_identity "
                "ON transition_states(state_identity)"
            )
            conn.execute(_SCHEMA[-2].replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS"))
            conn.execute(_SCHEMA[-1].replace("CREATE TABLE", "CREATE TABLE IF NOT EXISTS"))
        if version in {0, 1, 2}:
            for statement in _LEASE_SCHEMA:
                conn.execute(statement)
        for statement in _DISPATCH_SCHEMA:
            conn.execute(statement)
        conn.execute("""INSERT INTO daily_evaluation_dispatches(
            evaluation_id,dispatch_state,finalized_at)
            SELECT e.evaluation_id, CASE
                WHEN e.status='FINALIZED' THEN 'FINALIZED'
                WHEN EXISTS(SELECT 1 FROM daily_evaluation_events v
                    WHERE v.evaluation_id=e.evaluation_id AND v.event_type='PROVIDER_ATTEMPT')
                    THEN 'DISPATCHED_UNKNOWN'
                ELSE 'BLOCKED_LEGACY' END, e.finalized_at FROM daily_evaluations e""")
        if fail_after_step == 'dispatches':
            raise RuntimeError('injected portfolio migration failure')
        if version == 0:
            conn.execute(
                "INSERT INTO portfolio_schema_metadata(owner, version) VALUES ('phase11', ?)",
                (SCHEMA_VERSION,),
            )
        else:
            conn.execute(
                "UPDATE portfolio_schema_metadata SET version=? WHERE owner='phase11'",
                (SCHEMA_VERSION,),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def connect_portfolio_store(path: str | Path) -> sqlite3.Connection:
    db_path = Path(path)
    if str(db_path) != ":memory:":
        db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=5.0)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    migrate_portfolio(conn)
    return conn


def append_portfolio_snapshot(
    conn: sqlite3.Connection,
    snapshot: PortfolioSnapshot,
    *,
    cycle_id: str,
    observation_id: str,
) -> str:
    cycle = _stable_code(cycle_id, "cycle_id")
    observation = _stable_code(observation_id, "observation_id")
    _stable_code(snapshot.snapshot_id, "snapshot_id")
    _stable_code(snapshot.account_scope_hash, "account_scope_hash")
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """INSERT INTO portfolio_snapshots VALUES (
               ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                snapshot.snapshot_id, cycle, observation, snapshot.account_scope_hash,
                snapshot.trading_date.isoformat(), snapshot.previous_trading_date.isoformat(),
                snapshot.observed_at.isoformat(), snapshot.completeness.value,
                _stable_code(snapshot.reason_code, "reason_code"),
                snapshot.daily_page_count, snapshot.balance_page_count,
                snapshot.account.available_cash, snapshot.account.total_evaluation,
            ),
        )
        conn.executemany(
            "INSERT INTO portfolio_holdings VALUES (?, ?, ?, ?, ?)",
            [
                (snapshot.snapshot_id, item.ticker, item.total_quantity,
                 item.orderable_quantity, item.average_price)
                for item in snapshot.holdings
            ],
        )
        conn.executemany(
            "INSERT INTO portfolio_orders VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (snapshot.snapshot_id, item.order_id, item.original_order_id,
                 item.ticker, item.side, item.ordered_quantity, item.filled_quantity,
                 item.remaining_quantity, item.cancelled_quantity, item.rejected_quantity,
                 item.limit_price, item.status, item.order_date, item.order_time)
                for item in snapshot.orders
            ],
        )
        conn.executemany(
            "INSERT INTO portfolio_fills VALUES (?, ?, ?, ?, ?, ?)",
            [
                (snapshot.snapshot_id, item.fill_id, item.order_id, item.ticker,
                 item.quantity, item.price)
                for item in snapshot.fills
            ],
        )
        conn.executemany(
            """INSERT INTO portfolio_divergences(
               snapshot_id, code, severity, ticker, order_intent_id)
               VALUES (?, ?, ?, ?, ?)""",
            [
                (snapshot.snapshot_id, _stable_code(item.code, "divergence code"),
                 item.severity.value, item.ticker, item.order_intent_id)
                for item in snapshot.divergences
            ],
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return snapshot.snapshot_id


def append_watch_iteration(
    conn: sqlite3.Connection,
    result: Any,
    *,
    observed_at: datetime | None = None,
) -> str:
    """Persist one terminal intraday iteration and its stable outcome."""

    stamp = _aware(observed_at)
    iteration_id = _stable_code(result.iteration_id, "iteration_id")
    phase = _stable_code(result.phase.value, "intraday phase")
    outcome = _stable_code(result.outcome.value, "intraday outcome")
    reason = _stable_code(result.reason_code, "intraday reason")
    detail = sanitize_detail(
        {
            "phase": phase,
            "outcome": outcome,
            "reason_code": reason,
            "exit_count": len(result.exit_results),
        }
    )
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """INSERT INTO watch_iterations(
               iteration_id, cycle_id, snapshot_id, started_at, terminal_status)
               VALUES (?, ?, ?, ?, ?)""",
            (iteration_id, iteration_id, result.snapshot_id, stamp.isoformat(), outcome),
        )
        conn.execute(
            """INSERT INTO watch_observations(
               iteration_id, state_code, detail_json, observed_at)
               VALUES (?, ?, ?, ?)""",
            (iteration_id, phase, json.dumps(detail, sort_keys=True), stamp.isoformat()),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return iteration_id


def append_watch_observation(
    conn: sqlite3.Connection,
    *,
    iteration_id: str,
    state_code: str,
    detail: Mapping[str, Any] | None = None,
    observed_at: datetime | None = None,
) -> int:
    """Append a sanitized observation to an existing watch iteration."""

    stamp = _aware(observed_at)
    clean = sanitize_detail(detail)
    try:
        cursor = conn.execute(
            """INSERT INTO watch_observations(
               iteration_id, state_code, detail_json, observed_at)
               VALUES (?, ?, ?, ?)""",
            (
                _stable_code(iteration_id, "iteration_id"),
                _stable_code(state_code, "state_code"),
                json.dumps(clean, sort_keys=True),
                stamp.isoformat(),
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return int(cursor.lastrowid)


def record_transition_state(
    conn: sqlite3.Connection,
    observation: TransitionObservation,
) -> TransitionNotification | None:
    """Append an observation and atomically update its restart-stable projection."""

    identity = observation.state_identity
    stamp = observation.observed_at
    state_code = _stable_code(observation.normalized_state.upper(), "state_code")
    family = _stable_code(observation.event_family.upper(), "event_family")
    active = state_code not in {"RECOVERED", "STOPPED", "FILLED", "RESOLVED"}
    try:
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute(
            """SELECT occurrence_count,first_observed_at
               FROM transition_states WHERE state_identity=?""",
            (identity,),
        ).fetchone()
        prior = conn.execute(
            """SELECT state_code FROM transition_states
               WHERE account_scope_hash=? AND COALESCE(ticker,'')=COALESCE(?, '')
                 AND event_family=?
                 AND COALESCE(broker_subject_id,'')=COALESCE(?, '')
                 AND active=1 AND state_identity<>?
               ORDER BY last_observed_at DESC LIMIT 1""",
            (
                observation.account_scope_hash,
                observation.ticker,
                family,
                observation.broker_subject_id,
                identity,
            ),
        ).fetchone()
        if prior is not None:
            conn.execute(
                """UPDATE transition_states SET active=0
                   WHERE account_scope_hash=? AND COALESCE(ticker,'')=COALESCE(?, '')
                     AND event_family=?
                     AND COALESCE(broker_subject_id,'')=COALESCE(?, '')
                     AND active=1 AND state_identity<>?""",
                (
                    observation.account_scope_hash,
                    observation.ticker,
                    family,
                    observation.broker_subject_id,
                    identity,
                ),
            )
        if current is None:
            first = stamp
            occurrence = 1
            conn.execute(
                """INSERT INTO transition_states(
                   state_identity,account_scope_hash,ticker,event_family,
                   broker_subject_id,state_code,occurrence_count,
                   first_observed_at,last_observed_at,duration_seconds,
                   active,severity,last_notification_status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, NULL)""",
                (
                    identity,
                    observation.account_scope_hash,
                    observation.ticker,
                    family,
                    observation.broker_subject_id,
                    state_code,
                    occurrence,
                    stamp.isoformat(),
                    stamp.isoformat(),
                    int(active),
                    observation.severity.value,
                ),
            )
        else:
            occurrence = int(current[0]) + 1
            first = datetime.fromisoformat(str(current[1]))
            duration = max(0.0, (stamp - first).total_seconds())
            conn.execute(
                """UPDATE transition_states
                   SET occurrence_count=?,last_observed_at=?,duration_seconds=?,
                       active=?,severity=? WHERE state_identity=?""",
                (
                    occurrence,
                    stamp.isoformat(),
                    duration,
                    int(active),
                    observation.severity.value,
                    identity,
                ),
            )
        conn.execute(
            """INSERT INTO transition_observations(
               state_identity,state_code,severity,detail_json,observed_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                identity,
                state_code,
                observation.severity.value,
                json.dumps(dict(observation.detail), sort_keys=True),
                stamp.isoformat(),
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    if current is not None:
        return None
    event_code = (
        "STATE_RECOVERED"
        if not active
        else "STATE_CHANGED" if prior is not None else "STATE_BEGIN"
    )
    return TransitionNotification(
        identity,
        event_code,
        observation.severity,
        render_transition_notification(state_code, observation.severity),
        stamp,
    )


def record_transition_notification(
    conn: sqlite3.Connection,
    notification: TransitionNotification,
    *,
    delivery_status: str,
    failure_category: str | None = None,
) -> int:
    """Commit delivery evidence separately from the fail-soft transport call."""

    status = _stable_code(delivery_status.upper(), "delivery_status")
    failure = (
        _stable_code(failure_category.upper(), "failure_category")
        if failure_category
        else None
    )
    try:
        cursor = conn.execute(
            """INSERT OR IGNORE INTO transition_notifications(
               state_identity,event_code,severity,text,delivery_status,
               failure_category,observed_at) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                notification.state_identity,
                _stable_code(notification.event_code, "event_code"),
                notification.severity.value,
                notification.text[:180],
                status,
                failure,
                notification.observed_at.isoformat(),
            ),
        )
        conn.execute(
            """UPDATE transition_states SET last_notification_status=?
               WHERE state_identity=?""",
            (status, notification.state_identity),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return int(cursor.lastrowid or 0)


def load_transition_state(
    conn: sqlite3.Connection, state_identity: str
) -> TransitionState:
    row = conn.execute(
        """SELECT state_code,occurrence_count,first_observed_at,last_observed_at,
                  duration_seconds,active,severity,last_notification_status
           FROM transition_states WHERE state_identity=?""",
        (state_identity,),
    ).fetchone()
    if row is None:
        raise KeyError(state_identity)
    return TransitionState(
        state_identity=state_identity,
        state_code=str(row[0]),
        occurrence_count=int(row[1]),
        first_observed_at=datetime.fromisoformat(str(row[2])),
        last_observed_at=datetime.fromisoformat(str(row[3])),
        duration_seconds=float(row[4]),
        active=bool(row[5]),
        severity=OperationalSeverity(row[6]),
        last_notification_status=str(row[7]) if row[7] is not None else None,
    )


def start_daily_evaluation(
    conn: sqlite3.Connection,
    *,
    trading_date_kst: date,
    ticker: str,
    provenance: Sequence[str],
    canonical_input: bytes,
    account_scope_hash: str,
    observed_at: datetime | None = None,
    execution_target: str | None = None,
    envelope: DailyDispatchEnvelope | None = None,
    lease: Any = None,
) -> StoredDailyEvaluation:
    if len(ticker) != 6 or not ticker.isdigit():
        raise ValueError("ticker must be a 6-digit KRX code")
    if not isinstance(canonical_input, bytes) or not canonical_input:
        raise ValueError("canonical_input must be non-empty bytes")
    normalized_provenance = tuple(dict.fromkeys(str(item).upper() for item in provenance))
    if not normalized_provenance or not set(normalized_provenance) <= {"HELD", "SCREENED"}:
        raise ValueError("provenance must contain HELD and/or SCREENED")
    scope = _stable_code(account_scope_hash, "account_scope_hash")
    stamp = _aware(observed_at)
    if execution_target is not None or envelope is not None:
        if execution_target != 'mock':
            raise RuntimeError('unsupported execution target')
        if not isinstance(envelope, DailyDispatchEnvelope):
            raise ValueError('frozen dispatch envelope required')
        envelope = DailyDispatchEnvelope.model_validate(envelope)
        if envelope.prompt_bytes != canonical_input:
            raise ValueError('canonical input must match frozen envelope')
        _assert_dispatch_owner(conn, lease, scope, stamp)
    digest = hashlib.sha256(canonical_input).hexdigest()
    evaluation_id = str(uuid.uuid4())
    try:
        conn.execute("BEGIN IMMEDIATE")
        if envelope is not None:
            _assert_dispatch_owner(conn, lease, scope, stamp, in_transaction=True)
        cursor = conn.execute(
            """INSERT OR IGNORE INTO daily_evaluations(
               evaluation_id, trading_date_kst, ticker, provenance_json,
               canonical_input, canonical_input_hash, account_scope_hash,
               status, started_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                evaluation_id, trading_date_kst.isoformat(), ticker,
                json.dumps(normalized_provenance, separators=(",", ":")),
                canonical_input, digest, scope, DailyEvaluationStatus.STARTED.value,
                stamp.isoformat(),
            ),
        )
        if cursor.rowcount == 1:
            conn.execute("""INSERT INTO daily_evaluation_dispatches(
                evaluation_id,execution_target,envelope_json,envelope_hash,dispatch_state)
                VALUES(?,?,?,?,?)""", (evaluation_id, execution_target,
                envelope.model_dump_json() if envelope else None,
                envelope.envelope_hash if envelope else None,
                DailyDispatchState.NEVER_DISPATCHED.value if envelope else
                DailyDispatchState.BLOCKED_LEGACY.value))
            if envelope is not None:
                conn.execute('INSERT INTO daily_dispatch_identities VALUES(?,?,?,?,?)',
                    (evaluation_id, scope, execution_target, trading_date_kst.isoformat(), ticker))
            conn.execute(
                """INSERT INTO daily_evaluation_events(
                   evaluation_id, event_type, detail_json, observed_at)
                   VALUES (?, ?, ?, ?)""",
                (
                    evaluation_id, DailyEvaluationEventType.INPUT_COMMITTED.value,
                    json.dumps({"canonical_input_hash": digest}, sort_keys=True),
                    stamp.isoformat(),
                ),
            )
        else:
            evaluation_id = str(
                conn.execute(
                    "SELECT evaluation_id FROM daily_evaluations WHERE trading_date_kst=? AND ticker=?",
                    (trading_date_kst.isoformat(), ticker),
                ).fetchone()[0]
            )
            committed = load_daily_dispatch(conn, evaluation_id)
            if committed['account_scope_hash'] != scope:
                raise RuntimeError('daily identity account scope collision')
            if committed['execution_target'] != execution_target:
                raise RuntimeError('daily identity target collision or blocked legacy')
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return load_daily_evaluation(conn, evaluation_id)


def append_daily_evaluation_event(
    conn: sqlite3.Connection,
    evaluation_id: str,
    *,
    event_type: DailyEvaluationEventType,
    action: str | None = None,
    confidence: float | None = None,
    reason_code: str | None = None,
    detail: Mapping[str, Any] | None = None,
    observed_at: datetime | None = None,
    lease: Any = None,
) -> int:
    event = DailyEvaluationEvent(
        evaluation_id=_stable_code(evaluation_id, "evaluation_id"),
        event_type=DailyEvaluationEventType(event_type),
        action=action,
        confidence=confidence,
        reason_code=reason_code,
        detail=detail or {},
        observed_at=_aware(observed_at),
    )
    terminal = event.event_type in _TERMINAL_EVENTS
    dispatch = load_daily_dispatch(conn, evaluation_id)
    if dispatch['execution_target'] is not None:
        _assert_dispatch_owner(conn, lease, dispatch['account_scope_hash'], event.observed_at)
        if terminal or event.event_type is DailyEvaluationEventType.PROVIDER_ATTEMPT:
            raise RuntimeError('use one-shot dispatch claim/finalize owner methods')
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT status FROM daily_evaluations WHERE evaluation_id=?",
            (evaluation_id,),
        ).fetchone()
        if row is None:
            raise ValueError("evaluation not found")
        if terminal:
            updated = conn.execute(
                """UPDATE daily_evaluations SET status=?, finalized_at=?
                   WHERE evaluation_id=? AND status=?""",
                (DailyEvaluationStatus.FINALIZED.value, event.observed_at.isoformat(),
                 evaluation_id, DailyEvaluationStatus.STARTED.value),
            )
            if updated.rowcount != 1:
                raise ValueError("evaluation already finalized")
        elif row[0] != DailyEvaluationStatus.STARTED.value:
            raise ValueError("evaluation already finalized")
        cursor = conn.execute(
            """INSERT INTO daily_evaluation_events(
               evaluation_id, event_type, action, confidence, reason_code,
               detail_json, observed_at) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (evaluation_id, event.event_type.value, event.action, event.confidence,
             event.reason_code, json.dumps(dict(event.detail), sort_keys=True),
             event.observed_at.isoformat()),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return int(cursor.lastrowid)


def load_daily_evaluation(
    conn: sqlite3.Connection, evaluation_id: str
) -> StoredDailyEvaluation:
    row = conn.execute(
        """SELECT evaluation_id, trading_date_kst, ticker, provenance_json,
           canonical_input, canonical_input_hash, account_scope_hash, status,
           started_at, finalized_at FROM daily_evaluations WHERE evaluation_id=?""",
        (evaluation_id,),
    ).fetchone()
    if row is None:
        raise ValueError("evaluation not found")
    event_rows = conn.execute(
        """SELECT event_type, action, confidence, reason_code, detail_json, observed_at
           FROM daily_evaluation_events WHERE evaluation_id=? ORDER BY id""",
        (evaluation_id,),
    ).fetchall()
    events = tuple(
        DailyEvaluationEvent(
            evaluation_id=evaluation_id,
            event_type=DailyEvaluationEventType(item[0]),
            action=item[1], confidence=item[2], reason_code=item[3],
            detail=json.loads(item[4]), observed_at=datetime.fromisoformat(item[5]),
        )
        for item in event_rows
    )
    return StoredDailyEvaluation(
        evaluation_id=row[0], trading_date_kst=date.fromisoformat(row[1]), ticker=row[2],
        provenance=tuple(json.loads(row[3])), canonical_input=bytes(row[4]),
        canonical_input_hash=row[5], account_scope_hash=row[6],
        status=DailyEvaluationStatus(row[7]), started_at=datetime.fromisoformat(row[8]),
        finalized_at=datetime.fromisoformat(row[9]) if row[9] else None,
        events=events,
    )


def _assert_dispatch_owner(conn, lease, scope, now, *, in_transaction=False):
    """Prove real live account authority and recheck its durable row under the write lock."""
    from trading_bot.mutation_lease import MutationLease
    if (not isinstance(lease, MutationLease) or lease.closed
            or lease.account_scope_hash != scope or lease.state.value != 'ACTIVE'):
        raise RuntimeError('active scoped account owner required')
    source = conn.execute('PRAGMA database_list').fetchone()[2]
    owner_source = lease._conn.execute('PRAGMA database_list').fetchone()[2]
    if (source != owner_source or (not source and conn is not lease._conn)):
        raise RuntimeError('same trading store owner required')
    if not in_transaction:
        lease.assert_active_owner(observed_at=now)
    row = conn.execute('SELECT owner_token,state FROM mutation_leases WHERE account_scope_hash=?',
                       (scope,)).fetchone()
    if row is None or tuple(row) != (lease.owner_token, 'ACTIVE'):
        raise RuntimeError('active account owner no longer current')


def load_daily_dispatch(conn: sqlite3.Connection, evaluation_id: str) -> dict[str, Any]:
    """Committed owner read-back; callers must not hand raw envelope JSON to saved readers."""
    row = conn.execute('''SELECT d.evaluation_id,e.account_scope_hash,e.trading_date_kst,
        e.ticker,e.status,e.canonical_input_hash,e.started_at,d.execution_target,
        d.envelope_json,d.envelope_hash,d.dispatch_state,d.dispatch_id,d.dispatched_at,
        d.finalized_at,d.execution_intent_id
        FROM daily_evaluation_dispatches d JOIN daily_evaluations e
        ON e.evaluation_id=d.evaluation_id WHERE d.evaluation_id=?''', (evaluation_id,)).fetchone()
    if row is None:
        raise ValueError('daily dispatch not found')
    keys = ('evaluation_id','account_scope_hash','trading_date_kst','ticker','status',
            'canonical_input_hash','started_at','execution_target','envelope_json','envelope_hash',
            'dispatch_state','dispatch_id','dispatched_at','finalized_at','execution_intent_id')
    return dict(zip(keys, row))


def _intact_envelope(conn, dispatch):
    try:
        envelope = DailyDispatchEnvelope.model_validate_json(dispatch['envelope_json'])
        raw = conn.execute('SELECT canonical_input FROM daily_evaluations WHERE evaluation_id=?',
                           (dispatch['evaluation_id'],)).fetchone()[0]
        identity = conn.execute('SELECT account_scope_hash,execution_target,trading_date_kst,ticker '
            'FROM daily_dispatch_identities WHERE evaluation_id=?', (dispatch['evaluation_id'],)).fetchone()
        if (envelope.envelope_hash != dispatch['envelope_hash']
                or envelope.prompt_hash != dispatch['canonical_input_hash']
                or envelope.prompt_bytes != bytes(raw) or dispatch['execution_target'] != 'mock'
                or identity is None or tuple(identity) != tuple(dispatch[k] for k in
                    ('account_scope_hash','execution_target','trading_date_kst','ticker'))):
            raise ValueError()
        return envelope
    except (ValueError, TypeError):
        raise RuntimeError('frozen envelope or scoped identity is invalid') from None


def _dispatch_window(dispatch, now, deadline):
    stamp, end = _aware(now), _aware(deadline)
    day = date.fromisoformat(dispatch['trading_date_kst'])
    cutoff = datetime(day.year, day.month, day.day, 9, 20, tzinfo=ZoneInfo('Asia/Seoul'))
    if end > cutoff or end.astimezone(ZoneInfo('Asia/Seoul')).date() != day:
        raise RuntimeError('dispatch deadline must not exceed 09:20 KST')
    if stamp.astimezone(ZoneInfo('Asia/Seoul')).date() != day or stamp >= end:
        return False
    started = datetime.fromisoformat(dispatch['started_at'])
    if stamp < _aware(started):
        raise RuntimeError('dispatch clock precedes committed input')
    return True


def _dispatch_event(conn, evaluation_id, kind, now, detail=None):
    conn.execute('''INSERT INTO daily_evaluation_events(
        evaluation_id,event_type,detail_json,observed_at) VALUES(?,?,?,?)''',
        (evaluation_id, kind.value, json.dumps(sanitize_detail(detail), sort_keys=True), now.isoformat()))


def claim_daily_dispatch(conn, evaluation_id, lease, now, deadline):
    """Consume once, committing before any transport call; returns the exact handoff facts."""
    stamp = _aware(now)
    scope = getattr(lease, 'account_scope_hash', None)
    _assert_dispatch_owner(conn, lease, scope, stamp)
    try:
        conn.execute('BEGIN IMMEDIATE')
        _assert_dispatch_owner(conn, lease, scope, stamp, in_transaction=True)
        dispatch = load_daily_dispatch(conn, evaluation_id)
        if dispatch['account_scope_hash'] != scope:
            raise RuntimeError('daily dispatch scope mismatch')
        if dispatch['dispatch_state'] != DailyDispatchState.NEVER_DISPATCHED.value:
            raise RuntimeError('daily dispatch already consumed or blocked')
        _intact_envelope(conn, dispatch)
        if not _dispatch_window(dispatch, stamp, deadline):
            raise RuntimeError('dispatch input expired at deadline or date')
        dispatch_id = str(uuid.uuid4())
        conn.execute('''UPDATE daily_evaluation_dispatches SET dispatch_state='DISPATCHED',
            dispatch_id=?,dispatched_at=? WHERE evaluation_id=?''',
            (dispatch_id, stamp.isoformat(), evaluation_id))
        _dispatch_event(conn, evaluation_id, DailyEvaluationEventType.DISPATCH_CLAIMED, stamp,
                        {'dispatch_id': dispatch_id})
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return load_daily_dispatch(conn, evaluation_id)


def _finalize_dispatch(conn, dispatch, stamp, *, action, confidence, reason_code, unknown,
                       execution_intent_id=None, final_state=None, signal_reason=None):
    if dispatch['status'] != 'STARTED':
        raise RuntimeError('daily dispatch already finalized')
    if dispatch['dispatched_at'] and stamp < _aware(datetime.fromisoformat(dispatch['dispatched_at'])):
        raise RuntimeError('finalization precedes dispatch')
    if unknown:
        action, confidence, reason_code = 'HOLD', 0.0, 'LLM_UNAVAILABLE'
    event = DailyEvaluationEvent(dispatch['evaluation_id'],
        DailyEvaluationEventType.LLM_UNAVAILABLE if unknown else DailyEvaluationEventType.SIGNAL_FINALIZED,
        action, confidence, reason_code, {}, stamp)
    state = final_state or (DailyDispatchState.DISPATCHED_UNKNOWN if unknown else DailyDispatchState.FINALIZED)
    conn.execute('UPDATE daily_evaluations SET status=\'FINALIZED\',finalized_at=? WHERE evaluation_id=?',
                 (stamp.isoformat(), dispatch['evaluation_id']))
    conn.execute('''UPDATE daily_evaluation_dispatches SET dispatch_state=?,finalized_at=?,
        execution_intent_id=? WHERE evaluation_id=?''',
        (state.value, stamp.isoformat(), execution_intent_id, dispatch['evaluation_id']))
    _dispatch_event(conn, dispatch['evaluation_id'],
        DailyEvaluationEventType.DISPATCH_UNKNOWN if unknown else DailyEvaluationEventType.DISPATCH_FINALIZED, stamp)
    detail = {'reason': signal_reason} if not unknown and signal_reason is not None else {}
    conn.execute('''INSERT INTO daily_evaluation_events(evaluation_id,event_type,action,
        confidence,reason_code,detail_json,observed_at) VALUES(?,?,?,?,?,?,?)''',
        (event.evaluation_id,event.event_type.value,event.action,event.confidence,event.reason_code,
         json.dumps(sanitize_detail(detail),ensure_ascii=False),stamp.isoformat()))


def finalize_daily_dispatch(conn, evaluation_id, *, lease, now, action='HOLD', confidence=0.0,
                            reason_code='LLM_UNAVAILABLE', unknown=False, execution_intent_id=None, signal_reason=None):
    stamp = _aware(now)
    scope = getattr(lease, 'account_scope_hash', None)
    _assert_dispatch_owner(conn, lease, scope, stamp)
    if execution_intent_id is not None:
        execution_intent_id = _stable_code(execution_intent_id, 'execution_intent_id')
    if signal_reason is not None:
        if not isinstance(signal_reason, str) or not signal_reason.strip() or len(signal_reason)>4096:
            raise ValueError('bounded validated signal reason required')
        from trading_bot.signal_parser import parse_signal
        parsed = parse_signal(json.dumps({'decision':action,'confidence':confidence,'reason':signal_reason})).signal
        signal_reason = parsed.reason
    try:
        conn.execute('BEGIN IMMEDIATE')
        _assert_dispatch_owner(conn, lease, scope, stamp, in_transaction=True)
        dispatch = load_daily_dispatch(conn, evaluation_id)
        if dispatch['account_scope_hash'] != scope:
            raise RuntimeError('daily dispatch scope mismatch')
        if dispatch['dispatch_state'] != 'DISPATCHED':
            raise RuntimeError('only a consumed dispatch can finalize')
        _intact_envelope(conn, dispatch)
        _finalize_dispatch(conn, dispatch, stamp, action=action, confidence=confidence,
            reason_code=reason_code, unknown=unknown, execution_intent_id=execution_intent_id, signal_reason=signal_reason)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return load_daily_dispatch(conn, evaluation_id)


def recover_daily_dispatches(conn, *, lease, account_scope_hash, execution_target,
                             trading_date_kst, now, deadline):
    stamp = _aware(now)
    _assert_dispatch_owner(conn, lease, account_scope_hash, stamp)
    if execution_target != 'mock':
        raise RuntimeError('unsupported recovery target')
    try:
        conn.execute('BEGIN IMMEDIATE')
        _assert_dispatch_owner(conn, lease, account_scope_hash, stamp, in_transaction=True)
        ids = [row[0] for row in conn.execute('''SELECT d.evaluation_id
            FROM daily_evaluation_dispatches d JOIN daily_evaluations e USING(evaluation_id)
            WHERE e.account_scope_hash=? AND e.trading_date_kst=? AND e.status='STARTED'
            AND (d.execution_target=? OR d.execution_target IS NULL) ORDER BY e.started_at,e.evaluation_id''',
            (account_scope_hash,trading_date_kst.isoformat(),execution_target))]
        for evaluation_id in ids:
            dispatch = load_daily_dispatch(conn, evaluation_id)
            state = DailyDispatchState(dispatch['dispatch_state'])
            if state is DailyDispatchState.NEVER_DISPATCHED:
                _intact_envelope(conn, dispatch)
                if _dispatch_window(dispatch, stamp, deadline):
                    continue
                _dispatch_event(conn, evaluation_id, DailyEvaluationEventType.DISPATCH_EXPIRED, stamp)
                _finalize_dispatch(conn, dispatch, stamp, action='HOLD', confidence=0,
                    reason_code='LLM_UNAVAILABLE', unknown=True,
                    final_state=DailyDispatchState.EXPIRED_NEVER_DISPATCHED)
            else:
                _finalize_dispatch(conn, dispatch, stamp, action='HOLD', confidence=0,
                    reason_code='LLM_UNAVAILABLE', unknown=True,
                    final_state=DailyDispatchState.BLOCKED_LEGACY if state is DailyDispatchState.BLOCKED_LEGACY else None)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return tuple(load_daily_dispatch(conn, identity) for identity in ids)


def recover_started_evaluations(conn, *, observed_at=None, lease=None, account_scope_hash=None,
                                execution_target=None, trading_date_kst=None, deadline=None):
    """Compatibility name; global recovery without exclusive account authority is forbidden."""
    if lease is None:
        raise RuntimeError('scoped active owner required for evaluation recovery')
    if any(value is None for value in (account_scope_hash,execution_target,trading_date_kst,deadline)):
        raise RuntimeError('owner recovery requires explicit scope, target, date and deadline')
    rows = recover_daily_dispatches(conn, lease=lease, account_scope_hash=account_scope_hash,
        execution_target=execution_target,trading_date_kst=trading_date_kst,
        now=_aware(observed_at),deadline=deadline)
    return sum(row['status'] == 'FINALIZED' for row in rows)
