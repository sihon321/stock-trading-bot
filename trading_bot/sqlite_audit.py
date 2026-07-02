"""SQLite audit sink for per-run trading decisions.

The writer consumes the frozen ``CycleAuditEvent`` shape from ``execution.py``
without importing or changing that domain type. Raw LLM prompt/response payloads
stay in structlog; SQLite stores only structured decision fields plus a
correlation id to the corresponding log line.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Union

PathLike = Union[str, Path]


SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    trading_mode TEXT NOT NULL,
    dry_run INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES runs(run_id),
    ticker TEXT NOT NULL,
    final_action TEXT NOT NULL,
    parsed_decision TEXT,
    confidence REAL,
    parse_error TEXT,
    risk_override INTEGER NOT NULL,
    override_reason TEXT,
    order_reason TEXT,
    broker_order_id TEXT,
    requested_qty INTEGER,
    filled_qty INTEGER,
    current_price REAL,
    correlation_id TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_decisions_run ON decisions(run_id);
CREATE INDEX IF NOT EXISTS ix_decisions_ticker ON decisions(ticker);
"""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def connect(path: PathLike) -> sqlite3.Connection:
    """Open an audit DB, enable WAL, and ensure the two-table schema."""

    db_path = Path(path)
    if str(db_path) != ":memory:":
        db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.executescript(SCHEMA)
    conn.commit()
    return conn


def start_run(
    conn: sqlite3.Connection,
    *,
    run_id: str,
    trading_mode: str,
    dry_run: bool,
    started_at: str | None = None,
) -> str:
    """Insert the per-invocation run header and return ``run_id``."""

    conn.execute(
        """
        INSERT INTO runs (run_id, started_at, trading_mode, dry_run)
        VALUES (?, ?, ?, ?)
        """,
        (run_id, started_at or _utc_now(), trading_mode, int(bool(dry_run))),
    )
    conn.commit()
    return run_id


def write_decision(
    conn: sqlite3.Connection,
    run_id: str,
    event: Any,
    *,
    confidence: float | None,
    current_price: float | None,
    filled_qty: int | None = None,
    requested_qty: int | None = None,
    correlation_id: str,
    created_at: str | None = None,
) -> int:
    """Write one ticker decision row and commit it immediately.

    ``event`` is intentionally structural: callers pass the frozen
    ``CycleAuditEvent`` and this function only reads its public attributes.
    """

    cursor = conn.execute(
        """
        INSERT INTO decisions (
            run_id,
            ticker,
            final_action,
            parsed_decision,
            confidence,
            parse_error,
            risk_override,
            override_reason,
            order_reason,
            broker_order_id,
            requested_qty,
            filled_qty,
            current_price,
            correlation_id,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            run_id,
            event.ticker,
            event.final_action,
            event.parsed_decision,
            confidence,
            event.parse_error,
            int(bool(event.risk_override)),
            event.override_reason,
            event.order_reason,
            event.broker_order_id,
            requested_qty,
            filled_qty,
            current_price,
            correlation_id,
            created_at or _utc_now(),
        ),
    )
    conn.commit()
    return int(cursor.lastrowid)
