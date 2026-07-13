"""Behavior tests for the SQLite audit writer."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import sqlite3

import pytest

from trading_bot.audit_models import (
    NotificationAttempt,
    NotificationDeliveryStatus,
    NotificationKind,
    OrderEvent,
    OrderEventType,
    ReasonCode,
    RunKind,
    RunStatus,
    TickerOutcome,
    TickerOutcomeCode,
)
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


def test_v1_migrates_to_v3_idempotently_without_row_loss(tmp_path) -> None:
    from trading_bot import sqlite_audit

    path = tmp_path / "legacy.db"
    create_v1_audit_database(path).close()
    first = sqlite_audit.connect(path)
    assert first.execute("PRAGMA user_version").fetchone()[0] == 3
    assert first.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert first.execute("SELECT run_id FROM runs").fetchall() == [("legacy-run",)]
    assert first.execute("SELECT ticker FROM decisions").fetchall() == [("005930",)]
    first.close()
    second = sqlite_audit.connect(path)
    assert second.execute("PRAGMA user_version").fetchone()[0] == 3
    assert second.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1


def test_v2_migration_preserves_normalized_evidence(tmp_path) -> None:
    from trading_bot import sqlite_audit

    path = tmp_path / "v2.db"
    conn = create_v1_audit_database(path)
    for name, definition in sqlite_audit._RUN_V2_COLUMNS:
        conn.execute(f"ALTER TABLE runs ADD COLUMN {name} {definition}")
    conn.executescript(
        """
        CREATE TABLE ticker_outcomes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT NOT NULL REFERENCES runs(run_id), ticker TEXT NOT NULL,
            outcome_code TEXT NOT NULL, reason_code TEXT NOT NULL, detail_json TEXT NOT NULL,
            failed_stage TEXT, order_intent_id TEXT, final_order_state TEXT,
            created_at TEXT NOT NULL, UNIQUE(run_id, ticker)
        );
        CREATE TABLE order_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT, order_intent_id TEXT NOT NULL,
            origin_run_id TEXT NOT NULL REFERENCES runs(run_id),
            observer_run_id TEXT NOT NULL REFERENCES runs(run_id), ticker TEXT NOT NULL,
            event_type TEXT NOT NULL, submission_id TEXT, broker_order_id TEXT, side TEXT,
            requested_qty INTEGER, filled_qty INTEGER, unfilled_qty INTEGER,
            broker_status TEXT, duplicate_of_intent_id TEXT, detail_json TEXT NOT NULL,
            observed_at TEXT NOT NULL
        );
        INSERT INTO ticker_outcomes (
            run_id, ticker, outcome_code, reason_code, detail_json, created_at
        ) VALUES ('legacy-run', '005930', 'NO_TRADE', 'HOLD_SIGNAL', '{}',
                  '2026-07-10T00:00:02+00:00');
        INSERT INTO order_events (
            order_intent_id, origin_run_id, observer_run_id, ticker, event_type,
            detail_json, observed_at
        ) VALUES ('intent-legacy', 'legacy-run', 'legacy-run', '005930',
                  'INTENT_CREATED', '{}', '2026-07-10T00:00:03+00:00');
        PRAGMA user_version = 2;
        """
    )
    conn.commit()
    conn.close()

    upgraded = sqlite_audit.connect(path)
    assert upgraded.execute("PRAGMA user_version").fetchone()[0] == 3
    assert upgraded.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1
    assert upgraded.execute("SELECT COUNT(*) FROM decisions").fetchone()[0] == 1
    assert upgraded.execute("SELECT COUNT(*) FROM ticker_outcomes").fetchone()[0] == 1
    assert upgraded.execute("SELECT COUNT(*) FROM order_events").fetchone()[0] == 1
    columns = {
        row[1] for row in upgraded.execute("PRAGMA table_info(notification_attempts)")
    }
    assert columns == {
        "id", "run_id", "ticker", "kind", "delivery_status",
        "failure_category", "detail_json", "observed_at",
    }


def test_notification_contract_rejects_sensitive_and_non_scalar_detail() -> None:
    base = dict(
        run_id="run", ticker=None, kind=NotificationKind.FINAL_SUMMARY,
        status=NotificationDeliveryStatus.FAILED,
        failure_category="TRANSPORT_ERROR",
        observed_at=datetime(2026, 7, 14, tzinfo=timezone.utc),
    )
    with pytest.raises(ValueError, match="forbidden"):
        NotificationAttempt(**base, detail={"webhook_url": "https://secret.test"})
    with pytest.raises(TypeError, match="scalar"):
        NotificationAttempt(**base, detail={"provider": {"status": 500}})
    with pytest.raises(ValueError, match="failure_category"):
        NotificationAttempt(**base, detail={}, failure_category="raw exception text " * 20)


def test_migration_failure_rolls_back_and_reopen_retries(tmp_path) -> None:
    from trading_bot import sqlite_audit

    path = tmp_path / "legacy.db"
    conn = create_v1_audit_database(path)
    with pytest.raises(RuntimeError, match="injected"):
        sqlite_audit.migrate(conn, fail_after_step="runs")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1
    assert "run_kind" not in {r[1] for r in conn.execute("PRAGMA table_info(runs)")}
    conn.close()
    reopened = sqlite_audit.connect(path)
    assert reopened.execute("PRAGMA user_version").fetchone()[0] == 2


def test_unique_ticker_outcome_and_append_only_order_event_order(tmp_path) -> None:
    from trading_bot import sqlite_audit

    conn = sqlite_audit.connect(tmp_path / "audit.db")
    sqlite_audit.start_run(
        conn, run_id="origin", trading_mode="mock", dry_run=True, run_kind=RunKind.RUN
    )
    sqlite_audit.start_run(
        conn, run_id="observer", trading_mode="mock", dry_run=True, run_kind=RunKind.RUN
    )
    outcome = TickerOutcome(
        run_id="origin", ticker="005930", outcome_code=TickerOutcomeCode.ORDER_SUBMITTED,
        reason_code=ReasonCode.COMPLETED, order_intent_id="intent-1"
    )
    sqlite_audit.write_ticker_outcome(conn, outcome)
    with pytest.raises(sqlite3.IntegrityError):
        sqlite_audit.write_ticker_outcome(conn, outcome)

    first = OrderEvent(
        order_intent_id="intent-1", origin_run_id="origin", observer_run_id="origin",
        ticker="005930", event_type=OrderEventType.INTENT_CREATED,
    )
    second = OrderEvent(
        order_intent_id="intent-1", origin_run_id="origin", observer_run_id="observer",
        ticker="005930", event_type=OrderEventType.BROKER_OBSERVED,
        submission_id="submission-1", **normalized_broker_observation(),
    )
    first_id = sqlite_audit.append_order_event(conn, first)
    second_id = sqlite_audit.append_order_event(conn, second)
    assert first_id < second_id
    assert conn.execute(
        "SELECT event_type, origin_run_id, observer_run_id FROM order_events ORDER BY id"
    ).fetchall() == [
        ("INTENT_CREATED", "origin", "origin"),
        ("BROKER_OBSERVED", "origin", "observer"),
    ]


def test_storage_rejects_raw_provider_and_credential_detail(tmp_path) -> None:
    from trading_bot import sqlite_audit

    conn = sqlite_audit.connect(tmp_path / "audit.db")
    sqlite_audit.start_run(
        conn, run_id="run", trading_mode="mock", dry_run=True, run_kind=RunKind.RUN
    )
    base = dict(
        order_intent_id="intent", origin_run_id="run", observer_run_id="run",
        ticker="005930", event_type=OrderEventType.INTENT_CREATED,
    )
    with pytest.raises(ValueError, match="forbidden"):
        sqlite_audit.append_order_event(conn, OrderEvent(**base, detail={"raw_payload": "x"}))
    with pytest.raises(ValueError, match="forbidden"):
        sqlite_audit.append_order_event(conn, OrderEvent(**base, detail={"access_token": "x"}))


def test_outcome_vocabulary_is_scoped_to_run_kind(tmp_path) -> None:
    from trading_bot import sqlite_audit

    conn = sqlite_audit.connect(tmp_path / "audit.db")
    sqlite_audit.start_run(
        conn, run_id="screen", trading_mode="mock", dry_run=True,
        run_kind=RunKind.SCREEN,
    )
    with pytest.raises(ValueError, match="run kind"):
        sqlite_audit.write_ticker_outcome(
            conn,
            TickerOutcome(
                run_id="screen", ticker="005930",
                outcome_code=TickerOutcomeCode.NO_TRADE,
                reason_code=ReasonCode.HOLD_SIGNAL,
            ),
        )


def test_run_lifecycle_recovers_once_and_terminalizes_once(tmp_path) -> None:
    from trading_bot import sqlite_audit

    conn = sqlite_audit.connect(tmp_path / "audit.db")
    sqlite_audit.start_run(
        conn, run_id="abandoned", trading_mode="mock", dry_run=True,
        run_kind=RunKind.RUN,
    )
    assert sqlite_audit.recover_abandoned_runs(
        conn, recovered_at="2026-07-11T00:00:00+00:00"
    ) == 1
    assert sqlite_audit.recover_abandoned_runs(conn) == 0
    assert conn.execute(
        "SELECT status, recovered_at, recovery_reason FROM runs WHERE run_id='abandoned'"
    ).fetchone() == (
        "INTERRUPTED", "2026-07-11T00:00:00+00:00", "ABANDONED_PROCESS"
    )

    sqlite_audit.start_run(
        conn, run_id="current", trading_mode="mock", dry_run=True,
        run_kind=RunKind.RUN,
    )
    sqlite_audit.finish_run(conn, run_id="current", status=RunStatus.COMPLETED)
    with pytest.raises(ValueError, match="already terminal"):
        sqlite_audit.finish_run(conn, run_id="current", status=RunStatus.FAILED)


def test_parent_run_must_be_existing_uuid_and_child_remains_distinct(tmp_path) -> None:
    from trading_bot import sqlite_audit

    conn = sqlite_audit.connect(tmp_path / "audit.db")
    parent = "f4d726b8-687c-4e76-aea6-4429a50b0ac8"
    child = "a84b9bdf-d10b-476c-a68c-21e1c80631be"
    sqlite_audit.start_run(conn, run_id=parent, trading_mode="mock", dry_run=True)
    sqlite_audit.start_run(
        conn, run_id=child, trading_mode="mock", dry_run=True, parent_run_id=parent
    )
    assert conn.execute(
        "SELECT run_id, parent_run_id FROM runs WHERE run_id=?", (child,)
    ).fetchone() == (child, parent)
    with pytest.raises(ValueError, match="UUID"):
        sqlite_audit.start_run(
            conn, run_id="next", trading_mode="mock", dry_run=True,
            parent_run_id="not-a-uuid",
        )
    with pytest.raises(ValueError, match="does not exist"):
        sqlite_audit.start_run(
            conn, run_id="next", trading_mode="mock", dry_run=True,
            parent_run_id="1e75125d-2f91-4546-b74d-f064dfcb512d",
        )
