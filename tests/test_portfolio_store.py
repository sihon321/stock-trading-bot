from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone

import pytest

from trading_bot.audit_models import DailyEvaluationEventType, DailyEvaluationStatus
from trading_bot.portfolio import (
    DivergenceSeverity,
    PortfolioAccountSummary,
    PortfolioCompleteness,
    PortfolioDivergence,
    PortfolioFill,
    PortfolioHolding,
    PortfolioOrder,
    PortfolioSnapshot,
)
from trading_bot.portfolio_store import (
    append_daily_evaluation_event,
    append_portfolio_snapshot,
    connect_portfolio_store,
    load_daily_evaluation,
    migrate_portfolio,
    recover_started_evaluations,
    start_daily_evaluation,
)


NOW = datetime(2026, 9, 4, 1, 0, tzinfo=timezone.utc)


def snapshot() -> PortfolioSnapshot:
    return PortfolioSnapshot(
        snapshot_id="snapshot-1",
        account_scope_hash="scope-sha256",
        trading_date=date(2026, 9, 4),
        previous_trading_date=date(2026, 9, 3),
        observed_at=NOW,
        completeness=PortfolioCompleteness.COMPLETE,
        reason_code="COMPLETE",
        daily_page_count=2,
        balance_page_count=1,
        holdings=(PortfolioHolding("005930", 3, 2, 70000),),
        orders=(
            PortfolioOrder(
                "ORDER-1", None, "005930", "SELL", 1, 0, 1, 0, 0,
                71000, "NO_FILL", "20260904", "100000",
            ),
        ),
        fills=(PortfolioFill("FILL-1", "ORDER-0", "005930", 1, 69000),),
        account=PortfolioAccountSummary(1000000, 1210000),
        divergences=(
            PortfolioDivergence("HOLDING_DRIFT", DivergenceSeverity.WARNING, "005930"),
        ),
    )


def test_snapshot_facts_are_append_only_and_immediately_visible(tmp_path):
    path = tmp_path / "audit.db"
    conn = connect_portfolio_store(path)

    append_portfolio_snapshot(
        conn, snapshot(), cycle_id="cycle-1", observation_id="observation-1"
    )

    observer = sqlite3.connect(path)
    assert observer.execute("SELECT COUNT(*) FROM portfolio_snapshots").fetchone()[0] == 1
    assert observer.execute("SELECT ticker, total_quantity FROM portfolio_holdings").fetchone() == ("005930", 3)
    assert observer.execute("SELECT status, remaining_quantity FROM portfolio_orders").fetchone() == ("NO_FILL", 1)
    assert observer.execute("SELECT code, severity FROM portfolio_divergences").fetchone() == ("HOLDING_DRIFT", "WARNING")
    with pytest.raises(sqlite3.IntegrityError):
        append_portfolio_snapshot(
            conn, snapshot(), cycle_id="cycle-2", observation_id="observation-2"
        )


def test_daily_identity_is_unique_and_canonical_input_is_immutable(tmp_path):
    path = tmp_path / "audit.db"
    first_conn = connect_portfolio_store(path)
    second_conn = connect_portfolio_store(path)

    first = start_daily_evaluation(
        first_conn,
        trading_date_kst=date(2026, 9, 4),
        ticker="005930",
        provenance=("HELD", "SCREENED"),
        canonical_input=b'{"ticker":"005930"}',
        account_scope_hash="scope-sha256",
        observed_at=NOW,
    )
    second = start_daily_evaluation(
        second_conn,
        trading_date_kst=date(2026, 9, 4),
        ticker="005930",
        provenance=("SCREENED",),
        canonical_input=b'{"different":true}',
        account_scope_hash="scope-sha256",
        observed_at=NOW,
    )

    assert second.evaluation_id == first.evaluation_id
    loaded = load_daily_evaluation(second_conn, first.evaluation_id)
    assert loaded.canonical_input == b'{"ticker":"005930"}'
    assert loaded.status is DailyEvaluationStatus.STARTED
    assert second_conn.execute("SELECT COUNT(*) FROM daily_evaluations").fetchone()[0] == 1


def test_recovery_finalizes_started_evaluation_once_without_provider_call(tmp_path):
    conn = connect_portfolio_store(tmp_path / "audit.db")
    evaluation = start_daily_evaluation(
        conn,
        trading_date_kst=date(2026, 9, 4), ticker="005930",
        provenance=("HELD",), canonical_input=b"canonical",
        account_scope_hash="scope", observed_at=NOW,
    )

    assert recover_started_evaluations(conn, observed_at=NOW) == 1
    assert recover_started_evaluations(conn, observed_at=NOW) == 0

    loaded = load_daily_evaluation(conn, evaluation.evaluation_id)
    assert loaded.status is DailyEvaluationStatus.FINALIZED
    terminal = [event for event in loaded.events if event.event_type is DailyEvaluationEventType.LLM_UNAVAILABLE]
    assert len(terminal) == 1
    assert terminal[0].action == "HOLD"
    assert terminal[0].reason_code == "LLM_UNAVAILABLE"


def test_terminal_event_is_once_only_and_invalid_detail_rolls_back(tmp_path):
    conn = connect_portfolio_store(tmp_path / "audit.db")
    evaluation = start_daily_evaluation(
        conn,
        trading_date_kst=date(2026, 9, 4), ticker="005930",
        provenance=("HELD",), canonical_input=b"canonical",
        account_scope_hash="scope", observed_at=NOW,
    )
    with pytest.raises(ValueError, match="forbidden"):
        append_daily_evaluation_event(
            conn, evaluation.evaluation_id,
            event_type=DailyEvaluationEventType.PROVIDER_ATTEMPT,
            detail={"raw_payload": "secret"}, observed_at=NOW,
        )
    assert conn.execute("SELECT COUNT(*) FROM daily_evaluation_events").fetchone()[0] == 1

    append_daily_evaluation_event(
        conn, evaluation.evaluation_id,
        event_type=DailyEvaluationEventType.SIGNAL_FINALIZED,
        action="SELL", confidence=0.91, reason_code="MODEL_SELL",
        detail={"attempt": 1}, observed_at=NOW,
    )
    with pytest.raises(ValueError, match="already finalized"):
        append_daily_evaluation_event(
            conn, evaluation.evaluation_id,
            event_type=DailyEvaluationEventType.SIGNAL_FINALIZED,
            action="HOLD", reason_code="SECOND_FINAL", observed_at=NOW,
        )


def test_portfolio_migration_failure_rolls_back_and_retry_succeeds(tmp_path):
    path = tmp_path / "audit.db"
    conn = sqlite3.connect(path)
    with pytest.raises(RuntimeError, match="injected"):
        migrate_portfolio(conn, fail_after_step="snapshots")
    assert conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE name LIKE 'portfolio_%'"
    ).fetchone()[0] == 0

    migrate_portfolio(conn)
    assert conn.execute(
        "SELECT version FROM portfolio_schema_metadata WHERE owner='phase11'"
    ).fetchone()[0] == 2
    expected = {
        "portfolio_snapshots", "portfolio_holdings", "portfolio_orders",
        "portfolio_fills", "portfolio_divergences", "daily_evaluations",
        "daily_evaluation_events", "watch_iterations", "watch_observations",
        "transition_states", "mutation_leases", "mutation_lease_events",
    }
    actual = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert expected <= actual
