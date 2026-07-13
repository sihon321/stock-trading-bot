"""Read-only, deterministic projections of persisted audit and replay evidence."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence

from .audit_models import (
    NotificationDeliveryStatus,
    NotificationKind,
    OrderEventType,
    ReasonCode,
    RunStatus,
    TickerOutcomeCode,
)
from .sqlite_audit import SCHEMA_VERSION


class EvidenceState(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    UNKNOWN = "UNKNOWN"


class ReconciliationState(StrEnum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    PENDING = "PENDING"
    DETERMINATE = "DETERMINATE"
    UNKNOWN = "UNKNOWN"


class NotificationState(StrEnum):
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    DISABLED = "DISABLED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class NotificationReportAttempt:
    attempt_id: int
    kind: NotificationKind
    delivery_state: NotificationState
    failure_category: str | None
    observed_at: datetime


@dataclass(frozen=True)
class CandidateReportRow:
    run_id: str
    run_kind: str
    started_at: datetime
    trading_date_kst: date
    target: str
    processing_id: int
    ticker: str
    decision: str | None
    confidence: float | None
    reason_code: str
    reason_ko: str
    ticker_state: EvidenceState
    order_state: str
    reconciliation_state: ReconciliationState
    notification_attempts: tuple[NotificationReportAttempt, ...]


@dataclass(frozen=True)
class RunReportSection:
    run_id: str
    run_kind: str
    started_at: datetime
    trading_date_kst: date
    target: str
    run_status: RunStatus | None
    run_state: EvidenceState
    run_notification_attempts: tuple[NotificationReportAttempt, ...]
    final_summary_notification_state: NotificationState
    candidates: tuple[CandidateReportRow, ...]
    preview_run_id: str | None
    preview_only_tickers: tuple[str, ...]
    run_only_tickers: tuple[str, ...]


@dataclass(frozen=True)
class DenominatorCount:
    numerator: int
    total_denominator: int
    determinate_denominator: int


@dataclass(frozen=True)
class DailyReport:
    trading_date_kst: date
    runs: tuple[RunReportSection, ...]
    total_candidates: int
    complete: DenominatorCount
    incomplete: DenominatorCount
    unknown: DenominatorCount


@dataclass(frozen=True)
class PeriodReport:
    start_date_kst: date
    end_date_kst: date
    runs: tuple[RunReportSection, ...]
    total_candidates: int
    complete: DenominatorCount
    incomplete: DenominatorCount
    unknown: DenominatorCount


REASON_EXPLANATIONS_KO: Mapping[str, str] = MappingProxyType({
    ReasonCode.COMPLETED.value: "처리가 정상적으로 완료되었습니다",
    ReasonCode.HOLD_SIGNAL.value: "보유 신호로 주문하지 않았습니다",
    ReasonCode.LOW_CONFIDENCE.value: "신뢰도가 매수 기준보다 낮습니다",
    ReasonCode.STALE_OHLCV.value: "일봉 데이터가 최신이 아닙니다",
    ReasonCode.STALE_QUOTE.value: "주문 직전 시세가 오래되었습니다",
    ReasonCode.MALFORMED_SIGNAL.value: "LLM 신호 형식이 올바르지 않습니다",
    ReasonCode.LLM_TIMEOUT.value: "LLM 응답 시간이 초과되었습니다",
    ReasonCode.KIS_UNAVAILABLE.value: "KIS 서비스를 확인할 수 없습니다",
    ReasonCode.DUPLICATE_ORDER.value: "기존 주문과 중복되어 억제되었습니다",
    ReasonCode.AMBIGUOUS_SUBMISSION.value: "주문 접수 여부가 불명확합니다",
    ReasonCode.UNKNOWN_MARKET_STATE.value: "시장 상태를 확정할 수 없습니다",
})

_REQUIRED_SCHEMA: Mapping[str, frozenset[str]] = {
    "runs": frozenset({
        "run_id", "started_at", "run_kind", "status", "trading_date_kst", "target"
    }),
    "decisions": frozenset({"id", "run_id", "ticker", "final_action", "confidence"}),
    "ticker_outcomes": frozenset({
        "id", "run_id", "ticker", "outcome_code", "reason_code",
        "order_intent_id", "final_order_state",
    }),
    "order_events": frozenset({"id", "order_intent_id", "event_type"}),
    "notification_attempts": frozenset({
        "id", "run_id", "ticker", "kind", "delivery_status",
        "failure_category", "observed_at",
    }),
}


def _bounded(value: object, *, limit: int = 96, default: str = "UNKNOWN") -> str:
    if value is None:
        return default
    text = str(value).replace("\r", " ").replace("\n", " ")
    return text[:limit] or default


def _parse_datetime(value: object) -> datetime:
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise ValueError("invalid persisted report timestamp") from exc


def _parse_trading_date(value: object) -> date:
    raw = str(value)
    for format_string in ("%Y%m%d", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, format_string).date()
        except ValueError:
            continue
    raise ValueError("invalid persisted KST trading date")


def _run_status(value: object) -> RunStatus | None:
    try:
        return RunStatus(str(value))
    except (TypeError, ValueError):
        return None


def _reason_explanation(code: str) -> str:
    known = REASON_EXPLANATIONS_KO.get(code)
    if known is not None:
        return known
    return f"알 수 없는 사유 코드({_bounded(code)})"


def derive_run_evidence_state(
    run_status: RunStatus | None,
    candidates: Sequence[CandidateReportRow],
) -> EvidenceState:
    """Derive evidence completeness independently of trading success."""

    if run_status in {RunStatus.FAILED, RunStatus.INTERRUPTED, RunStatus.RUNNING}:
        return EvidenceState.INCOMPLETE
    if run_status in {RunStatus.COMPLETED, RunStatus.COMPLETED_WITH_ERRORS}:
        if all(candidate.ticker_state is EvidenceState.COMPLETE for candidate in candidates):
            return EvidenceState.COMPLETE
        if any(candidate.ticker_state is EvidenceState.UNKNOWN for candidate in candidates):
            return EvidenceState.UNKNOWN
        return EvidenceState.INCOMPLETE
    return EvidenceState.UNKNOWN


def derive_final_summary_notification_state(
    attempts: Sequence[NotificationReportAttempt],
) -> NotificationState:
    final_attempts = [
        attempt for attempt in attempts if attempt.kind is NotificationKind.FINAL_SUMMARY
    ]
    if not final_attempts:
        return NotificationState.UNKNOWN
    return max(final_attempts, key=lambda attempt: attempt.attempt_id).delivery_state


def _notification_state(value: object) -> NotificationState:
    try:
        status = NotificationDeliveryStatus(str(value))
    except ValueError:
        return NotificationState.UNKNOWN
    return NotificationState(status.value)


def _notification_attempt(row: sqlite3.Row) -> NotificationReportAttempt:
    try:
        kind = NotificationKind(str(row["kind"]))
    except ValueError as exc:
        raise ValueError("unsupported notification kind in audit evidence") from exc
    return NotificationReportAttempt(
        attempt_id=int(row["id"]),
        kind=kind,
        delivery_state=_notification_state(row["delivery_status"]),
        failure_category=(
            _bounded(row["failure_category"], limit=64)
            if row["failure_category"] is not None else None
        ),
        observed_at=_parse_datetime(row["observed_at"]),
    )


class ReadOnlyAuditRepository:
    """Project supported audit evidence without creating or migrating SQLite."""

    def __init__(self, path: Path) -> None:
        raw_path = Path(path)
        try:
            resolved = raw_path.resolve(strict=True)
        except FileNotFoundError:
            raise FileNotFoundError(f"audit database does not exist: {raw_path}") from None
        if not resolved.is_file():
            raise ValueError("audit database path must be a regular file")
        self._path = resolved

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            f"{self._path.as_uri()}?mode=ro", uri=True, isolation_level=None
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        return connection

    @staticmethod
    def _validate_schema(connection: sqlite3.Connection) -> None:
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if version != SCHEMA_VERSION:
            raise RuntimeError(f"unsupported audit schema version: {version}")
        for table, required in _REQUIRED_SCHEMA.items():
            columns = {
                str(row["name"])
                for row in connection.execute(f"PRAGMA table_info({table})")
            }
            if not required.issubset(columns):
                raise RuntimeError(f"unsupported audit schema capability: {table}")

    def load_daily(self, trading_date_kst: date) -> tuple[RunReportSection, ...]:
        return self.load_period(trading_date_kst, trading_date_kst)

    def load_period(
        self,
        start_date_kst: date,
        end_date_kst: date,
    ) -> tuple[RunReportSection, ...]:
        if start_date_kst > end_date_kst:
            raise ValueError("period start must not be after end")
        connection = self._connect()
        try:
            self._validate_schema(connection)
            connection.execute("BEGIN")
            runs = connection.execute(
                """SELECT run_id, started_at, run_kind, status, trading_date_kst, target
                   FROM runs
                   WHERE REPLACE(trading_date_kst, '-', '') BETWEEN ? AND ?
                   ORDER BY started_at, run_id""",
                (start_date_kst.strftime("%Y%m%d"), end_date_kst.strftime("%Y%m%d")),
            ).fetchall()
            sections = tuple(self._load_run(connection, run) for run in runs)
            connection.commit()
        except Exception:
            if connection.in_transaction:
                connection.rollback()
            raise
        finally:
            connection.close()
        return self._pair_previews(sections)

    def _load_run(
        self,
        connection: sqlite3.Connection,
        run: sqlite3.Row,
    ) -> RunReportSection:
        run_id = str(run["run_id"])
        outcomes = connection.execute(
            """SELECT id, ticker, outcome_code, reason_code, order_intent_id,
                      final_order_state
               FROM ticker_outcomes WHERE run_id = ? ORDER BY id""",
            (run_id,),
        ).fetchall()
        decisions = connection.execute(
            """SELECT id, ticker, final_action, confidence
               FROM decisions WHERE run_id = ? ORDER BY id""",
            (run_id,),
        ).fetchall()
        notifications = connection.execute(
            """SELECT id, ticker, kind, delivery_status, failure_category, observed_at
               FROM notification_attempts WHERE run_id = ? ORDER BY id""",
            (run_id,),
        ).fetchall()

        decisions_by_ticker: dict[str, list[sqlite3.Row]] = {}
        for decision in decisions:
            decisions_by_ticker.setdefault(str(decision["ticker"]), []).append(decision)
        notifications_by_ticker: dict[str, list[NotificationReportAttempt]] = {}
        run_attempts: list[NotificationReportAttempt] = []
        for raw_attempt in notifications:
            attempt = _notification_attempt(raw_attempt)
            ticker = raw_attempt["ticker"]
            if ticker is None:
                run_attempts.append(attempt)
            else:
                notifications_by_ticker.setdefault(str(ticker), []).append(attempt)

        started_at = _parse_datetime(run["started_at"])
        trading_date = _parse_trading_date(run["trading_date_kst"])
        run_kind = _bounded(run["run_kind"])
        target = _bounded(run["target"])
        candidates: list[CandidateReportRow] = []
        for outcome in outcomes:
            ticker = _bounded(outcome["ticker"], limit=24)
            matching_decisions = decisions_by_ticker.get(ticker, [])
            decision = matching_decisions[-1] if len(matching_decisions) == 1 else None
            reason_code = _bounded(outcome["reason_code"])
            try:
                TickerOutcomeCode(str(outcome["outcome_code"]))
                ReasonCode(reason_code)
                known_terminal = True
            except ValueError:
                known_terminal = False
            if len(matching_decisions) > 1:
                known_terminal = False
                reason_code = "INTEGRITY_DUPLICATE_DECISION"
            intent_id = outcome["order_intent_id"]
            reconciliation = self._reconciliation_state(connection, intent_id)
            candidates.append(CandidateReportRow(
                run_id=run_id,
                run_kind=run_kind,
                started_at=started_at,
                trading_date_kst=trading_date,
                target=target,
                processing_id=int(outcome["id"]),
                ticker=ticker,
                decision=(
                    _bounded(decision["final_action"]) if decision is not None else None
                ),
                confidence=(
                    float(decision["confidence"])
                    if decision is not None and decision["confidence"] is not None else None
                ),
                reason_code=reason_code,
                reason_ko=_reason_explanation(reason_code),
                ticker_state=(EvidenceState.COMPLETE if known_terminal else EvidenceState.UNKNOWN),
                order_state=(
                    _bounded(outcome["final_order_state"])
                    if outcome["final_order_state"] is not None
                    else ("PENDING" if intent_id is not None else "NOT_APPLICABLE")
                ),
                reconciliation_state=reconciliation,
                notification_attempts=tuple(notifications_by_ticker.get(ticker, ())),
            ))
        candidate_tuple = tuple(candidates)
        status = _run_status(run["status"])
        run_attempt_tuple = tuple(run_attempts)
        return RunReportSection(
            run_id=run_id,
            run_kind=run_kind,
            started_at=started_at,
            trading_date_kst=trading_date,
            target=target,
            run_status=status,
            run_state=derive_run_evidence_state(status, candidate_tuple),
            run_notification_attempts=run_attempt_tuple,
            final_summary_notification_state=derive_final_summary_notification_state(
                run_attempt_tuple
            ),
            candidates=candidate_tuple,
            preview_run_id=None,
            preview_only_tickers=(),
            run_only_tickers=(),
        )

    @staticmethod
    def _reconciliation_state(
        connection: sqlite3.Connection,
        intent_id: object,
    ) -> ReconciliationState:
        if intent_id is None:
            return ReconciliationState.NOT_APPLICABLE
        events = connection.execute(
            "SELECT event_type FROM order_events WHERE order_intent_id = ? ORDER BY id",
            (str(intent_id),),
        ).fetchall()
        if not events:
            return ReconciliationState.UNKNOWN
        event_types: list[OrderEventType] = []
        for event in events:
            try:
                event_types.append(OrderEventType(str(event["event_type"])))
            except ValueError:
                return ReconciliationState.UNKNOWN
        if OrderEventType.RECONCILED in event_types:
            return ReconciliationState.DETERMINATE
        if OrderEventType.SUBMISSION_AMBIGUOUS in event_types:
            return ReconciliationState.UNKNOWN
        return ReconciliationState.PENDING

    @staticmethod
    def _pair_previews(
        sections: tuple[RunReportSection, ...],
    ) -> tuple[RunReportSection, ...]:
        paired: list[RunReportSection] = []
        for index, section in enumerate(sections):
            if section.run_kind != "RUN":
                paired.append(section)
                continue
            screens = [
                candidate
                for candidate in sections[:index]
                if candidate.run_kind == "SCREEN"
                and candidate.trading_date_kst == section.trading_date_kst
                and candidate.target == section.target
            ]
            if not screens:
                paired.append(section)
                continue
            preview = screens[-1]
            preview_tickers = {
                row.ticker
                for row in preview.candidates
                if row.reason_code == ReasonCode.COMPLETED.value
            }
            run_tickers = {row.ticker for row in section.candidates}
            paired.append(replace(
                section,
                preview_run_id=preview.run_id,
                preview_only_tickers=tuple(sorted(preview_tickers - run_tickers)),
                run_only_tickers=tuple(sorted(run_tickers - preview_tickers)),
            ))
        return tuple(paired)


def _state_counts(
    runs: Sequence[RunReportSection],
) -> tuple[int, DenominatorCount, DenominatorCount, DenominatorCount]:
    candidates = tuple(candidate for run in runs for candidate in run.candidates)
    total = len(candidates)
    complete = sum(row.ticker_state is EvidenceState.COMPLETE for row in candidates)
    incomplete = sum(row.ticker_state is EvidenceState.INCOMPLETE for row in candidates)
    unknown = sum(row.ticker_state is EvidenceState.UNKNOWN for row in candidates)
    if complete + incomplete + unknown != total:
        raise ValueError("report evidence states do not reconcile")
    determinate = complete + incomplete
    return (
        total,
        DenominatorCount(complete, total, determinate),
        DenominatorCount(incomplete, total, determinate),
        DenominatorCount(unknown, total, determinate),
    )


def build_daily_report(
    repository: ReadOnlyAuditRepository,
    trading_date_kst: date,
) -> DailyReport:
    runs = repository.load_daily(trading_date_kst)
    total, complete, incomplete, unknown = _state_counts(runs)
    return DailyReport(
        trading_date_kst, runs, total, complete, incomplete, unknown
    )


def build_period_report(
    repository: ReadOnlyAuditRepository,
    start_date_kst: date,
    end_date_kst: date,
) -> PeriodReport:
    runs = repository.load_period(start_date_kst, end_date_kst)
    total, complete, incomplete, unknown = _state_counts(runs)
    return PeriodReport(
        start_date_kst, end_date_kst, runs, total, complete, incomplete, unknown
    )
