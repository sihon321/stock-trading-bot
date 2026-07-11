"""Versioned SQLite audit storage with additive, normalized evidence."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Union

from .audit_models import (
    FailedStage,
    OrderEvent,
    OrderEventType,
    ReasonCode,
    RunKind,
    RunStatus,
    TickerOutcome,
    TickerOutcomeCode,
    sanitize_detail,
)

PathLike = Union[str, Path]
SCHEMA_VERSION = 2

_V1_SCHEMA = (
    "CREATE TABLE IF NOT EXISTS runs (run_id TEXT PRIMARY KEY, started_at TEXT NOT NULL, "
    "trading_mode TEXT NOT NULL, dry_run INTEGER NOT NULL)",
    "CREATE TABLE IF NOT EXISTS decisions (id INTEGER PRIMARY KEY AUTOINCREMENT, "
    "run_id TEXT NOT NULL REFERENCES runs(run_id), ticker TEXT NOT NULL, final_action TEXT NOT NULL, "
    "parsed_decision TEXT, confidence REAL, parse_error TEXT, risk_override INTEGER NOT NULL, "
    "override_reason TEXT, order_reason TEXT, broker_order_id TEXT, requested_qty INTEGER, "
    "filled_qty INTEGER, current_price REAL, correlation_id TEXT NOT NULL, created_at TEXT NOT NULL)",
    "CREATE INDEX IF NOT EXISTS ix_decisions_run ON decisions(run_id)",
    "CREATE INDEX IF NOT EXISTS ix_decisions_ticker ON decisions(ticker)",
)

_RUN_V2_COLUMNS = (
    ("run_kind", "TEXT"), ("status", "TEXT NOT NULL DEFAULT 'RUNNING'"),
    ("finished_at", "TEXT"), ("trading_date_kst", "TEXT"), ("target", "TEXT"),
    ("policy_snapshot", "TEXT"), ("provenance", "TEXT"), ("parent_run_id", "TEXT"),
    ("recovered_at", "TEXT"), ("recovery_reason", "TEXT"),
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _table_columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {str(row[1]) for row in conn.execute(f"PRAGMA table_info({table})")}


def migrate(conn: sqlite3.Connection, *, fail_after_step: str | None = None) -> None:
    """Upgrade the audit schema additively in one explicit transaction."""

    version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if version > SCHEMA_VERSION:
        raise RuntimeError(f"unsupported audit schema version: {version}")
    if version == SCHEMA_VERSION:
        return
    try:
        conn.execute("BEGIN IMMEDIATE")
        for statement in _V1_SCHEMA:
            conn.execute(statement)
        existing = _table_columns(conn, "runs")
        for name, definition in _RUN_V2_COLUMNS:
            if name not in existing:
                conn.execute(f"ALTER TABLE runs ADD COLUMN {name} {definition}")
        if fail_after_step == "runs":
            raise RuntimeError("injected migration failure")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS ticker_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id TEXT NOT NULL REFERENCES runs(run_id), ticker TEXT NOT NULL,
                outcome_code TEXT NOT NULL, reason_code TEXT NOT NULL, detail_json TEXT NOT NULL,
                failed_stage TEXT, order_intent_id TEXT, final_order_state TEXT,
                created_at TEXT NOT NULL, UNIQUE(run_id, ticker))"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS order_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_intent_id TEXT NOT NULL,
                origin_run_id TEXT NOT NULL REFERENCES runs(run_id),
                observer_run_id TEXT NOT NULL REFERENCES runs(run_id),
                ticker TEXT NOT NULL, event_type TEXT NOT NULL, submission_id TEXT,
                broker_order_id TEXT, side TEXT, requested_qty INTEGER, filled_qty INTEGER,
                unfilled_qty INTEGER, broker_status TEXT, duplicate_of_intent_id TEXT,
                detail_json TEXT NOT NULL, observed_at TEXT NOT NULL)"""
        )
        conn.execute("CREATE INDEX IF NOT EXISTS ix_order_events_intent ON order_events(order_intent_id, id)")
        conn.execute("PRAGMA user_version = 2")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def connect(path: PathLike) -> sqlite3.Connection:
    db_path = Path(path)
    if str(db_path) != ":memory:":
        db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    migrate(conn)
    return conn


def start_run(conn: sqlite3.Connection, *, run_id: str, trading_mode: str,
              dry_run: bool, started_at: str | None = None,
              run_kind: RunKind | None = None, status: RunStatus = RunStatus.RUNNING,
              trading_date_kst: str | None = None, target: str | None = None,
              policy_snapshot: dict[str, Any] | None = None,
              provenance: dict[str, Any] | None = None,
              parent_run_id: str | None = None) -> str:
    conn.execute(
        """INSERT INTO runs (run_id, started_at, trading_mode, dry_run, run_kind, status,
           trading_date_kst, target, policy_snapshot, provenance, parent_run_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (run_id, started_at or _utc_now(), trading_mode, int(bool(dry_run)),
         run_kind.value if run_kind else None, status.value, trading_date_kst, target,
         json.dumps(sanitize_detail(policy_snapshot), sort_keys=True),
         json.dumps(sanitize_detail(provenance), sort_keys=True), parent_run_id),
    )
    conn.commit()
    return run_id


def write_ticker_outcome(conn: sqlite3.Connection, outcome: TickerOutcome) -> int:
    code = TickerOutcomeCode(outcome.outcome_code)
    ReasonCode(outcome.reason_code)
    if outcome.failed_stage is not None:
        FailedStage(outcome.failed_stage)
    run_kind = conn.execute("SELECT run_kind FROM runs WHERE run_id = ?", (outcome.run_id,)).fetchone()
    if run_kind is None:
        raise sqlite3.IntegrityError("unknown run")
    screen_codes = {TickerOutcomeCode.SELECTED, TickerOutcomeCode.REJECTED, TickerOutcomeCode.SCREEN_ERROR}
    if (run_kind[0] == RunKind.SCREEN.value) != (code in screen_codes):
        raise ValueError("outcome code does not match run kind")
    cursor = conn.execute(
        """INSERT INTO ticker_outcomes (run_id, ticker, outcome_code, reason_code,
           detail_json, failed_stage, order_intent_id, final_order_state, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (outcome.run_id, outcome.ticker, code.value, outcome.reason_code.value,
         json.dumps(sanitize_detail(outcome.detail), sort_keys=True),
         outcome.failed_stage.value if outcome.failed_stage else None,
         outcome.order_intent_id, outcome.final_order_state, outcome.created_at or _utc_now()),
    )
    conn.commit()
    return int(cursor.lastrowid)


def append_order_event(conn: sqlite3.Connection, event: OrderEvent) -> int:
    OrderEventType(event.event_type)
    detail = sanitize_detail(event.detail)
    if event.requested_qty is not None and event.requested_qty < 0:
        raise ValueError("requested_qty cannot be negative")
    cursor = conn.execute(
        """INSERT INTO order_events (order_intent_id, origin_run_id, observer_run_id,
           ticker, event_type, submission_id, broker_order_id, side, requested_qty,
           filled_qty, unfilled_qty, broker_status, duplicate_of_intent_id,
           detail_json, observed_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (event.order_intent_id, event.origin_run_id, event.observer_run_id, event.ticker,
         event.event_type.value, event.submission_id, event.broker_order_id, event.side,
         event.requested_qty, event.filled_qty, event.unfilled_qty, event.broker_status,
         event.duplicate_of_intent_id, json.dumps(detail, sort_keys=True),
         event.observed_at or _utc_now()),
    )
    conn.commit()
    return int(cursor.lastrowid)


def write_decision(conn: sqlite3.Connection, run_id: str, event: Any, *,
                   confidence: float | None, current_price: float | None,
                   filled_qty: int | None = None, requested_qty: int | None = None,
                   correlation_id: str, created_at: str | None = None) -> int:
    cursor = conn.execute(
        """INSERT INTO decisions (run_id, ticker, final_action, parsed_decision,
           confidence, parse_error, risk_override, override_reason, order_reason,
           broker_order_id, requested_qty, filled_qty, current_price, correlation_id,
           created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (run_id, event.ticker, event.final_action, event.parsed_decision, confidence,
         event.parse_error, int(bool(event.risk_override)), event.override_reason,
         event.order_reason, event.broker_order_id, requested_qty, filled_qty,
         current_price, correlation_id, created_at or _utc_now()),
    )
    conn.commit()
    return int(cursor.lastrowid)


__all__ = ["RunStatus", "RunKind", "TickerOutcome", "OrderEvent", "migrate"]
