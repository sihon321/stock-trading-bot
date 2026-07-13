"""Read-only report projection and rendering behavior."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from trading_bot import sqlite_audit
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
from trading_bot.reporting import (
    EvidenceState,
    NotificationState,
    ReadOnlyAuditRepository,
    ReconciliationState,
    build_replay_report,
    build_daily_report,
    build_period_report,
    load_replay_results,
    render_daily_report,
    render_period_report,
    render_replay_report,
)
from trading_bot.replay import (
    NON_PROFITABILITY_DISCLAIMER,
    ReplayCheck,
    ReplayCount,
    ReplayFunnel,
    ReplayManifest,
    ReplayResult,
    ReplayVerification,
)


DAY = date(2026, 7, 14)


def _start(
    conn,
    run_id: str,
    *,
    kind: RunKind,
    status: RunStatus,
    started_at: str,
    day: str = "20260714",
    target: str = "mock",
) -> None:
    sqlite_audit.start_run(
        conn,
        run_id=run_id,
        trading_mode="mock",
        dry_run=True,
        run_kind=kind,
        status=status,
        started_at=started_at,
        trading_date_kst=day,
        target=target,
    )


def _outcome(
    conn,
    run_id: str,
    ticker: str,
    *,
    code: TickerOutcomeCode = TickerOutcomeCode.NO_TRADE,
    reason: ReasonCode = ReasonCode.HOLD_SIGNAL,
    intent: str | None = None,
    final_order_state: str | None = None,
) -> int:
    return sqlite_audit.write_ticker_outcome(
        conn,
        TickerOutcome(
            run_id=run_id,
            ticker=ticker,
            outcome_code=code,
            reason_code=reason,
            order_intent_id=intent,
            final_order_state=final_order_state,
        ),
    )


def _decision(conn, run_id: str, ticker: str, action: str, confidence: float) -> None:
    event = SimpleNamespace(
        ticker=ticker,
        final_action=action,
        parsed_decision=action,
        parse_error=None,
        risk_override=False,
        override_reason="",
        order_reason="reason",
        broker_order_id=None,
    )
    sqlite_audit.write_decision(
        conn,
        run_id,
        event,
        confidence=confidence,
        current_price=70_000,
        correlation_id=f"corr-{run_id}-{ticker}",
    )


def _notification(
    conn,
    run_id: str,
    *,
    ticker: str | None,
    kind: NotificationKind,
    status: NotificationDeliveryStatus,
    failure: str | None = None,
) -> int:
    return sqlite_audit.append_notification_attempt(
        conn,
        NotificationAttempt(
            run_id=run_id,
            ticker=ticker,
            kind=kind,
            status=status,
            failure_category=failure,
            detail={},
            observed_at=datetime(2026, 7, 14, 0, 10, tzinfo=timezone.utc),
        ),
    )


def test_readonly_daily_preserves_order_preview_and_notification_scope(tmp_path: Path) -> None:
    path = tmp_path / "audit.db"
    conn = sqlite_audit.connect(path)
    _start(
        conn,
        "screen-earlier",
        kind=RunKind.SCREEN,
        status=RunStatus.COMPLETED,
        started_at="2026-07-14T00:05:00+00:00",
    )
    _outcome(conn, "screen-earlier", "005930", code=TickerOutcomeCode.SELECTED, reason=ReasonCode.COMPLETED)
    _outcome(conn, "screen-earlier", "000660", code=TickerOutcomeCode.SELECTED, reason=ReasonCode.COMPLETED)

    _start(
        conn,
        "run-main",
        kind=RunKind.RUN,
        status=RunStatus.COMPLETED,
        started_at="2026-07-14T00:10:00+00:00",
    )
    first_id = _outcome(conn, "run-main", "035420")
    second_id = _outcome(conn, "run-main", "005930", reason=ReasonCode.LOW_CONFIDENCE)
    _decision(conn, "run-main", "005930", "HOLD", 0.79)
    ticker_attempt_id = _notification(
        conn,
        "run-main",
        ticker="005930",
        kind=NotificationKind.IMMEDIATE_ERROR,
        status=NotificationDeliveryStatus.FAILED,
        failure="TRANSPORT_ERROR",
    )
    run_attempt_id = _notification(
        conn,
        "run-main",
        ticker=None,
        kind=NotificationKind.FINAL_SUMMARY,
        status=NotificationDeliveryStatus.DELIVERED,
    )
    conn.close()

    before = path.read_bytes()
    report = build_daily_report(ReadOnlyAuditRepository(path), DAY)
    after = path.read_bytes()

    assert before == after
    assert report.total_candidates == 4
    assert [run.run_id for run in report.runs] == ["screen-earlier", "run-main"]
    run = report.runs[1]
    assert [row.processing_id for row in run.candidates] == [first_id, second_id]
    assert [row.ticker for row in run.candidates] == ["035420", "005930"]
    assert run.preview_run_id == "screen-earlier"
    assert run.preview_only_tickers == ("000660",)
    assert run.run_only_tickers == ("035420",)
    assert run.candidates[1].decision == "HOLD"
    assert run.candidates[1].confidence == pytest.approx(0.79)
    assert [attempt.attempt_id for attempt in run.candidates[1].notification_attempts] == [ticker_attempt_id]
    assert run.candidates[0].notification_attempts == ()
    assert [attempt.attempt_id for attempt in run.run_notification_attempts] == [run_attempt_id]
    assert run.final_summary_notification_state is NotificationState.DELIVERED
    assert all(
        attempt.attempt_id != run_attempt_id
        for candidate in run.candidates
        for attempt in candidate.notification_attempts
    )


@pytest.mark.parametrize(
    ("status", "with_candidate", "expected"),
    [
        (RunStatus.COMPLETED, True, EvidenceState.COMPLETE),
        (RunStatus.COMPLETED_WITH_ERRORS, True, EvidenceState.COMPLETE),
        (RunStatus.FAILED, True, EvidenceState.INCOMPLETE),
        (RunStatus.INTERRUPTED, True, EvidenceState.INCOMPLETE),
        (RunStatus.RUNNING, True, EvidenceState.INCOMPLETE),
        (RunStatus.COMPLETED, False, EvidenceState.COMPLETE),
    ],
)
def test_run_lifecycle_and_zero_candidates_remain_visible(
    tmp_path: Path,
    status: RunStatus,
    with_candidate: bool,
    expected: EvidenceState,
) -> None:
    path = tmp_path / f"{status.value}-{with_candidate}.db"
    conn = sqlite_audit.connect(path)
    _start(
        conn,
        "run",
        kind=RunKind.RUN,
        status=status,
        started_at="2026-07-14T00:10:00+00:00",
    )
    if with_candidate:
        _outcome(conn, "run", "005930")
    conn.close()

    section = ReadOnlyAuditRepository(path).load_daily(DAY)[0]
    assert section.run_status is status
    assert section.run_state is expected
    assert len(section.candidates) == int(with_candidate)


def test_missing_or_unknown_lifecycle_is_unknown(tmp_path: Path) -> None:
    path = tmp_path / "audit.db"
    conn = sqlite_audit.connect(path)
    _start(
        conn,
        "run",
        kind=RunKind.RUN,
        status=RunStatus.COMPLETED,
        started_at="2026-07-14T00:10:00+00:00",
    )
    conn.execute("UPDATE runs SET status = ? WHERE run_id = ?", ("LEGACY", "run"))
    conn.commit()
    conn.close()
    section = ReadOnlyAuditRepository(path).load_daily(DAY)[0]
    assert section.run_status is None
    assert section.run_state is EvidenceState.UNKNOWN


@pytest.mark.parametrize(
    ("delivery", "expected"),
    [
        (NotificationDeliveryStatus.DELIVERED, NotificationState.DELIVERED),
        (NotificationDeliveryStatus.FAILED, NotificationState.FAILED),
        (NotificationDeliveryStatus.DISABLED, NotificationState.DISABLED),
    ],
)
def test_final_summary_notification_uses_latest_insertion_id(
    tmp_path: Path,
    delivery: NotificationDeliveryStatus,
    expected: NotificationState,
) -> None:
    path = tmp_path / "audit.db"
    conn = sqlite_audit.connect(path)
    _start(
        conn,
        "run",
        kind=RunKind.RUN,
        status=RunStatus.COMPLETED,
        started_at="2026-07-14T00:10:00+00:00",
    )
    _notification(
        conn,
        "run",
        ticker=None,
        kind=NotificationKind.FINAL_SUMMARY,
        status=NotificationDeliveryStatus.FAILED,
        failure="EARLIER",
    )
    _notification(
        conn,
        "run",
        ticker=None,
        kind=NotificationKind.FINAL_SUMMARY,
        status=delivery,
        failure="LATEST" if delivery is NotificationDeliveryStatus.FAILED else None,
    )
    conn.close()
    section = ReadOnlyAuditRepository(path).load_daily(DAY)[0]
    assert section.final_summary_notification_state is expected
    assert [attempt.attempt_id for attempt in section.run_notification_attempts] == sorted(
        attempt.attempt_id for attempt in section.run_notification_attempts
    )


def test_missing_final_summary_notification_is_unknown(tmp_path: Path) -> None:
    path = tmp_path / "audit.db"
    conn = sqlite_audit.connect(path)
    _start(
        conn,
        "run",
        kind=RunKind.RUN,
        status=RunStatus.COMPLETED,
        started_at="2026-07-14T00:10:00+00:00",
    )
    conn.close()
    section = ReadOnlyAuditRepository(path).load_daily(DAY)[0]
    assert section.final_summary_notification_state is NotificationState.UNKNOWN


def test_period_is_inclusive_and_reconciles_detail_denominators(tmp_path: Path) -> None:
    path = tmp_path / "audit.db"
    conn = sqlite_audit.connect(path)
    for index, day in enumerate(("20260713", "20260714", "20260715", "20260716")):
        run_id = f"run-{day}"
        _start(
            conn,
            run_id,
            kind=RunKind.RUN,
            status=RunStatus.COMPLETED,
            started_at=f"2026-07-{13 + index:02d}T00:10:00+00:00",
            day=day,
        )
        _outcome(conn, run_id, f"{index:06d}")
    conn.close()

    report = build_period_report(
        ReadOnlyAuditRepository(path), date(2026, 7, 14), date(2026, 7, 15)
    )
    assert [run.trading_date_kst for run in report.runs] == [
        date(2026, 7, 14),
        date(2026, 7, 15),
    ]
    assert report.total_candidates == 2
    assert sum(
        count.numerator for count in (report.complete, report.incomplete, report.unknown)
    ) == report.total_candidates
    assert report.complete.total_denominator == 2
    assert report.complete.determinate_denominator == 2


def test_reconciliation_reduces_order_events_without_multiplying_candidates(tmp_path: Path) -> None:
    path = tmp_path / "audit.db"
    conn = sqlite_audit.connect(path)
    _start(
        conn,
        "run",
        kind=RunKind.RUN,
        status=RunStatus.COMPLETED,
        started_at="2026-07-14T00:10:00+00:00",
    )
    _outcome(
        conn,
        "run",
        "005930",
        code=TickerOutcomeCode.ORDER_RECONCILED,
        reason=ReasonCode.COMPLETED,
        intent="intent-1",
        final_order_state="FILLED",
    )
    for event_type in (OrderEventType.INTENT_CREATED, OrderEventType.RECONCILED):
        sqlite_audit.append_order_event(
            conn,
            OrderEvent(
                order_intent_id="intent-1",
                origin_run_id="run",
                observer_run_id="run",
                ticker="005930",
                event_type=event_type,
            ),
        )
    conn.close()
    section = ReadOnlyAuditRepository(path).load_daily(DAY)[0]
    assert len(section.candidates) == 1
    assert section.candidates[0].order_state == "FILLED"
    assert section.candidates[0].reconciliation_state is ReconciliationState.DETERMINATE


def test_readonly_repository_refuses_missing_and_unsupported_databases(tmp_path: Path) -> None:
    missing = tmp_path / "missing" / "audit.db"
    with pytest.raises(FileNotFoundError):
        ReadOnlyAuditRepository(missing)
    assert not missing.exists()
    assert not missing.parent.exists()

    unsupported = tmp_path / "unsupported.db"
    unsupported.write_bytes(b"")
    with pytest.raises(RuntimeError, match="schema"):
        ReadOnlyAuditRepository(unsupported).load_daily(DAY)


def _manifest(**changes) -> ReplayManifest:
    values = {
        "scenario_hash": "1" * 64,
        "ohlcv_hash": "2" * 64,
        "raw_signal_hash": "3" * 64,
        "policy": {"buy_confidence_threshold": 0.8},
        "head_commit": "abc123",
        "relevant_tracked_diff_hash": "4" * 64,
        "code_state": "clean",
        "initial_state": {"cash": 1_000_000, "positions": []},
        "evaluation_time": "2026-07-14T09:10:00+09:00",
        "trading_date": "20260714",
        "fixture_schema_version": 1,
    }
    values.update(changes)
    return ReplayManifest(**values)


def _funnel(total: int = 1) -> ReplayFunnel:
    return ReplayFunnel(
        evaluated=ReplayCount(total, total),
        selected=ReplayCount(total, total),
        buy_signaled=ReplayCount(total, total),
        confidence_qualified=ReplayCount(total, total),
        risk_qualified=ReplayCount(total, total),
        validly_sized=ReplayCount(total, total),
        order_eligible=ReplayCount(total, total),
        actions={
            "BUY": ReplayCount(total, total),
            "HOLD": ReplayCount(0, total),
            "SELL": ReplayCount(0, total),
        },
        blocked_reasons={},
    )


def _result(path: Path, *, manifest: ReplayManifest | None = None) -> ReplayResult:
    verification = ReplayVerification(
        passed=True,
        checks=(ReplayCheck("buy", "scenario", "005930", "action", "BUY", "BUY", True),),
    )
    result = ReplayResult(
        manifest or _manifest(),
        ({"ticker": "005930", "action": "BUY"},),
        {"source": "test"},
        _funnel(),
        verification,
    )
    path.write_bytes(result.normalized_bytes())
    return result


def test_replay_identity_is_verified_and_duplicate_ids_count_once(tmp_path: Path) -> None:
    first_path = tmp_path / "first.json"
    duplicate_path = tmp_path / "duplicate.json"
    expected = _result(first_path)
    duplicate_path.write_bytes(first_path.read_bytes())

    loaded = load_replay_results((first_path, duplicate_path))
    assert len(loaded) == 1
    assert loaded[0].stable_result_id == expected.result_id
    assert loaded[0].source_paths == (first_path.resolve(), duplicate_path.resolve())
    assert loaded[0].verification_status == "PASSED"

    forged = json.loads(first_path.read_text(encoding="utf-8"))
    forged["result_id"] = "f" * 64
    forged_path = tmp_path / "forged.json"
    forged_path.write_text(json.dumps(forged), encoding="utf-8")
    with pytest.raises(ValueError, match="identity"):
        load_replay_results((forged_path,))


@pytest.mark.parametrize("mutation", ["cardinality", "non_finite", "unknown_field"])
def test_replay_malformed_funnel_fails_before_aggregation(
    tmp_path: Path, mutation: str
) -> None:
    path = tmp_path / "result.json"
    _result(path)
    document = json.loads(path.read_text(encoding="utf-8"))
    if mutation == "cardinality":
        document["evidence"]["funnel"]["selected"]["numerator"] = 2
    elif mutation == "non_finite":
        document["evidence"]["funnel"]["selected"]["numerator"] = float("inf")
    else:
        document["evidence"]["funnel"]["extra"] = {"numerator": 0, "denominator": 0}
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError):
        load_replay_results((path,))


def test_replay_compatibility_groups_only_identical_basis_and_explains_mismatch(
    tmp_path: Path,
) -> None:
    first_path = tmp_path / "first.json"
    second_path = tmp_path / "second.json"
    third_path = tmp_path / "third.json"
    first = _result(first_path)
    second = _result(second_path, manifest=replace(_manifest(), head_commit="other"))
    third = _result(
        third_path,
        manifest=replace(_manifest(), policy={"buy_confidence_threshold": 0.9}),
    )

    report = build_replay_report(load_replay_results((first_path, second_path, third_path)))
    assert len(report.results) == 3
    assert len(report.groups) == 2
    same_basis = next(group for group in report.groups if len(group.result_ids) == 2)
    assert same_basis.result_ids == (first.result_id, second.result_id)
    assert same_basis.aggregate_funnel.evaluated == ReplayCount(2, 2)
    assert all("policy" in group.incompatible_fields for group in report.groups)
    assert report.disclaimer == NON_PROFITABILITY_DISCLAIMER


def test_daily_period_and_replay_renderers_are_summary_first_and_deterministic(
    tmp_path: Path,
) -> None:
    database = tmp_path / "audit.db"
    conn = sqlite_audit.connect(database)
    _start(
        conn,
        "run",
        kind=RunKind.RUN,
        status=RunStatus.COMPLETED,
        started_at="2026-07-14T00:10:00+00:00",
    )
    _outcome(conn, "run", "005930", reason=ReasonCode.LOW_CONFIDENCE)
    _decision(conn, "run", "005930", "HOLD", 0.79)
    conn.close()

    repository = ReadOnlyAuditRepository(database)
    daily = render_daily_report(build_daily_report(repository, DAY))
    period = render_period_report(build_period_report(repository, DAY, DAY))
    replay_path = tmp_path / "replay.json"
    replay_result = _result(replay_path)
    replay = render_replay_report(build_replay_report(load_replay_results((replay_path,))))

    assert daily == render_daily_report(build_daily_report(repository, DAY))
    assert daily.endswith("\n") and "\r" not in daily
    assert daily.index("요약") < daily.index("상세") < daily.index("005930")
    assert "LOW_CONFIDENCE — 신뢰도가 매수 기준보다 낮습니다" in daily
    assert period.index("요약") < period.index("상세")
    assert replay.index(replay_result.result_id) < replay.index("호환 그룹")
    assert NON_PROFITABILITY_DISCLAIMER in replay
    assert "P&L:" not in replay and "Sharpe:" not in replay
