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

from trading_bot.audit_models import (
    DailyEvaluationEvent,
    DailyEvaluationEventType,
    DailyEvaluationStatus,
    sanitize_detail,
)
from trading_bot.portfolio import PortfolioSnapshot


SCHEMA_VERSION = 1
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
        id INTEGER PRIMARY KEY AUTOINCREMENT, state_identity TEXT NOT NULL,
        state_code TEXT NOT NULL, occurrence_count INTEGER NOT NULL,
        first_observed_at TEXT NOT NULL, last_observed_at TEXT NOT NULL)""",
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
    row = conn.execute(
        "SELECT version FROM portfolio_schema_metadata WHERE owner='phase11'"
    ).fetchone()
    return int(row[0]) if row else 0


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
        for index, statement in enumerate(_SCHEMA):
            conn.execute(statement)
            if fail_after_step == "snapshots" and index == 1:
                raise RuntimeError("injected portfolio migration failure")
        conn.execute(
            "INSERT INTO portfolio_schema_metadata(owner, version) VALUES ('phase11', ?)",
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


def start_daily_evaluation(
    conn: sqlite3.Connection,
    *,
    trading_date_kst: date,
    ticker: str,
    provenance: Sequence[str],
    canonical_input: bytes,
    account_scope_hash: str,
    observed_at: datetime | None = None,
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
    digest = hashlib.sha256(canonical_input).hexdigest()
    evaluation_id = str(uuid.uuid4())
    try:
        conn.execute("BEGIN IMMEDIATE")
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


def recover_started_evaluations(
    conn: sqlite3.Connection, *, observed_at: datetime | None = None
) -> int:
    ids = [
        str(row[0]) for row in conn.execute(
            "SELECT evaluation_id FROM daily_evaluations WHERE status=? ORDER BY started_at",
            (DailyEvaluationStatus.STARTED.value,),
        )
    ]
    for evaluation_id in ids:
        append_daily_evaluation_event(
            conn, evaluation_id,
            event_type=DailyEvaluationEventType.LLM_UNAVAILABLE,
            action="HOLD", reason_code="LLM_UNAVAILABLE",
            detail={"recovery": True}, observed_at=observed_at,
        )
    return len(ids)
