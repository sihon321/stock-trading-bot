"""Behavior tests for the SQLite audit writer."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

from trading_bot.execution import CycleAuditEvent
from tests.conftest import create_v1_audit_database, normalized_broker_observation


def _event(ticker: str, *, final_action: str = "HOLD") -> CycleAuditEvent:
    return CycleAuditEvent(
        ticker=ticker,
        parsed_decision=final_action,
        parse_error=None,
        risk_override=False,
        override_reason="",
        final_action=final_action,
        order_reason=f"{final_action.lower()} reason",
        dry_run=True,
        broker_order_id=None,
    )


def test_two_table_write(tmp_path) -> None:
    from trading_bot import sqlite_audit

    db_path = tmp_path / "audit.db"
    conn = sqlite_audit.connect(db_path)

    sqlite_audit.start_run(
        conn,
        run_id="run-001",
        trading_mode="mock",
        dry_run=True,
    )
    sqlite_audit.write_decision(
        conn,
        "run-001",
        _event("005930", final_action="BUY"),
        confidence=0.91,
        current_price=70000.0,
        requested_qty=2,
        filled_qty=0,
        correlation_id="corr-005930",
    )
    sqlite_audit.write_decision(
        conn,
        "run-001",
        _event("000660", final_action="HOLD"),
        confidence=0.42,
        current_price=120000.0,
        correlation_id="corr-000660",
    )

    assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 2

    joined = conn.execute(
        """
        SELECT runs.run_id, runs.trading_mode, decisions.ticker, decisions.final_action
        FROM runs
        JOIN decisions ON decisions.run_id = runs.run_id
        WHERE runs.run_id = ?
        ORDER BY decisions.ticker
        """,
        ("run-001",),
    ).fetchall()
    assert joined == [
        ("run-001", "mock", "000660", "HOLD"),
        ("run-001", "mock", "005930", "BUY"),
    ]

    by_ticker = conn.execute(
        "SELECT final_action, confidence, current_price FROM decisions WHERE ticker = ?",
        ("005930",),
    ).fetchone()
    assert by_ticker == ("BUY", 0.91, 70000.0)

    pragma = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert pragma.lower() == "wal"


def test_correlation_id(tmp_path) -> None:
    from trading_bot import sqlite_audit

    event = _event("005930", final_action="SELL")
    conn = sqlite_audit.connect(tmp_path / "audit.db")
    sqlite_audit.start_run(conn, run_id="run-correlation", trading_mode="mock", dry_run=True)
    sqlite_audit.write_decision(
        conn,
        "run-correlation",
        event,
        confidence=0.88,
        current_price=71000.0,
        filled_qty=1,
        requested_qty=1,
        correlation_id="llm-signal-cycle-abc123",
    )

    columns = {
        row[1] for row in conn.execute("PRAGMA table_info(decisions)").fetchall()
    }
    assert "correlation_id" in columns
    assert "prompt" not in columns
    assert "response" not in columns

    stored = conn.execute(
        """
        SELECT ticker, parsed_decision, final_action, filled_qty, requested_qty, correlation_id
        FROM decisions
        WHERE run_id = ?
        """,
        ("run-correlation",),
    ).fetchone()
    assert stored == (
        "005930",
        "SELL",
        "SELL",
        1,
        1,
        "llm-signal-cycle-abc123",
    )

    try:
        event.ticker = "000660"
    except FrozenInstanceError:
        pass
    else:  # pragma: no cover - dataclass contract would be broken.
        raise AssertionError("CycleAuditEvent must remain frozen")


def test_shipped_v1_fixture_preserves_legacy_reads_and_writes(tmp_path) -> None:
    from trading_bot import sqlite_audit

    path = tmp_path / "legacy.db"
    conn = create_v1_audit_database(path)
    conn.close()

    upgraded = sqlite_audit.connect(path)
    assert upgraded.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1
    assert upgraded.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 1
    sqlite_audit.start_run(
        upgraded, run_id="new-run", trading_mode="mock", dry_run=True
    )
    sqlite_audit.write_decision(
        upgraded,
        "new-run",
        _event("000660"),
        confidence=0.5,
        current_price=120000,
        correlation_id="new-correlation",
    )
    assert upgraded.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 2
    assert upgraded.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 2


def test_normalized_broker_fixture_has_no_raw_or_secret_fields() -> None:
    observation = normalized_broker_observation()
    assert observation["requested_qty"] == 2
    assert observation["filled_qty"] + observation["unfilled_qty"] == 2
    forbidden = {"raw", "payload", "response", "app_key", "secret", "token"}
    assert forbidden.isdisjoint(observation)
