from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone

import pytest

from trading_bot.audit_models import (
    OperationalSeverity,
    TransitionObservation,
    render_transition_notification,
)
from trading_bot.portfolio_store import migrate_portfolio, record_transition_state


NOW = datetime(2026, 9, 4, 1, 0, tzinfo=timezone.utc)


def observation(*, state: str = "OPEN", seconds: int = 0) -> TransitionObservation:
    return TransitionObservation(
        account_scope_hash="a" * 64,
        ticker="005930",
        event_family="BROKER_ORDER",
        normalized_state=state,
        broker_subject_id="ORDER-1",
        severity=(
            OperationalSeverity.WARNING
            if state == "LONG_OPEN_ORDER"
            else OperationalSeverity.INFO
        ),
        observed_at=NOW + timedelta(seconds=seconds),
        detail={"remaining_quantity": 1},
    )


def test_repeated_transition_observations_are_durable_but_notify_once() -> None:
    conn = sqlite3.connect(":memory:")
    migrate_portfolio(conn)

    notifications = [record_transition_state(conn, observation(seconds=index)) for index in range(5)]

    row = conn.execute(
        """SELECT occurrence_count,first_observed_at,last_observed_at,
                  duration_seconds,severity,state_code
           FROM transition_states"""
    ).fetchone()
    assert row == (5, NOW.isoformat(), (NOW + timedelta(seconds=4)).isoformat(), 4.0, "INFO", "OPEN")
    assert conn.execute("SELECT COUNT(*) FROM transition_observations").fetchone() == (5,)
    assert sum(item is not None for item in notifications) == 1
    assert notifications[0].event_code == "STATE_BEGIN"


@pytest.mark.parametrize(
    ("code", "severity", "phrase"),
    [
        ("STARTED", OperationalSeverity.INFO, "시작"),
        ("LONG_OPEN_ORDER", OperationalSeverity.WARNING, "장시간"),
        ("ORDER_AMBIGUOUS", OperationalSeverity.CRITICAL, "불명확"),
        ("LEASE_LOST", OperationalSeverity.CRITICAL, "소유권"),
        ("AUDIT_EVIDENCE_FAILED", OperationalSeverity.CRITICAL, "감사 증거"),
    ],
)
def test_transition_alerts_have_stable_severity_and_bounded_korean_text(
    code, severity, phrase
) -> None:
    rendered = render_transition_notification(code, severity)
    assert rendered.startswith(f"[{severity.value}]")
    assert phrase in rendered
    assert len(rendered) <= 180


def test_transition_details_reject_secrets_and_raw_payloads() -> None:
    with pytest.raises(ValueError):
        TransitionObservation(
            account_scope_hash="a" * 64,
            ticker="005930",
            event_family="BROKER_ORDER",
            normalized_state="OPEN",
            broker_subject_id="ORDER-1",
            severity=OperationalSeverity.INFO,
            observed_at=NOW,
            detail={"raw_payload": "secret"},
        )
