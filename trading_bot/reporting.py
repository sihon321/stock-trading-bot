"""Read-only, deterministic projections of persisted audit and replay evidence."""

from __future__ import annotations

import sqlite3
import hashlib
import json
from dataclasses import dataclass, replace
from datetime import date, datetime
from enum import StrEnum
from pathlib import Path
from types import MappingProxyType
from typing import Any, Mapping, Sequence

from .audit_models import (
    NotificationDeliveryStatus,
    NotificationKind,
    OrderEventType,
    ReasonCode,
    RunStatus,
    TickerOutcomeCode,
)
from .sqlite_audit import SCHEMA_VERSION
from .replay import (
    NON_PROFITABILITY_DISCLAIMER,
    ReplayCheck,
    ReplayCount,
    ReplayFunnel,
    ReplayManifest,
    ReplayVerification,
    canonical_json_bytes,
)


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


@dataclass(frozen=True)
class ReplayInputResult:
    source_paths: tuple[Path, ...]
    stable_result_id: str
    verification_status: str
    compatibility_signature: tuple[tuple[str, str], ...]
    funnel: ReplayFunnel


@dataclass(frozen=True)
class ReplayCompatibilityGroup:
    signature: tuple[tuple[str, str], ...]
    result_ids: tuple[str, ...]
    aggregate_funnel: ReplayFunnel
    incompatible_fields: tuple[str, ...]


@dataclass(frozen=True)
class ReplayReport:
    results: tuple[ReplayInputResult, ...]
    groups: tuple[ReplayCompatibilityGroup, ...]
    disclaimer: str


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


_REPLAY_TOP_LEVEL_FIELDS = {
    "schema_version", "result_id", "evidence", "observational_metadata"
}
_REPLAY_EVIDENCE_FIELDS = {
    "manifest", "outcomes", "funnel", "verification", "disclaimer"
}
_REPLAY_MANIFEST_FIELDS = {
    "scenario_hash", "ohlcv_hash", "raw_signal_hash", "policy", "head_commit",
    "relevant_tracked_diff_hash", "code_state", "initial_state",
    "evaluation_time", "trading_date", "fixture_schema_version",
}
_FUNNEL_FIELDS = {
    "evaluated", "selected", "buy_signaled", "confidence_qualified",
    "risk_qualified", "validly_sized", "order_eligible", "actions",
    "blocked_reasons",
}
_FUNNEL_STAGE_FIELDS = (
    "evaluated", "selected", "buy_signaled", "confidence_qualified",
    "risk_qualified", "validly_sized", "order_eligible",
)
_CHECK_FIELDS = {
    "boundary_id", "scenario_id", "ticker", "stage", "expected", "actual", "passed"
}
_MAX_REPLAY_BYTES = 16 * 1024 * 1024


def _exact_keys(value: object, expected: set[str], label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise ValueError(f"{label} fields mismatch")
    return value


def _strict_json(path: Path) -> Mapping[str, Any]:
    if path.is_symlink():
        raise ValueError("replay input may not be a symbolic link")
    try:
        resolved = path.resolve(strict=True)
    except FileNotFoundError:
        raise FileNotFoundError(f"replay result does not exist: {path}") from None
    if not resolved.is_file():
        raise ValueError("replay input must be a regular file")
    if resolved.stat().st_size > _MAX_REPLAY_BYTES:
        raise ValueError("replay input exceeds size limit")

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite JSON constant: {value}")

    try:
        document = json.loads(
            resolved.read_text(encoding="utf-8"), parse_constant=reject_constant
        )
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid replay result JSON") from exc
    return _exact_keys(document, _REPLAY_TOP_LEVEL_FIELDS, "replay result")


def _replay_count(value: object, label: str) -> ReplayCount:
    raw = _exact_keys(value, {"numerator", "denominator"}, label)
    numerator = raw["numerator"]
    denominator = raw["denominator"]
    if (
        isinstance(numerator, bool)
        or isinstance(denominator, bool)
        or not isinstance(numerator, int)
        or not isinstance(denominator, int)
        or numerator < 0
        or denominator < 0
        or numerator > denominator
    ):
        raise ValueError(f"invalid replay count: {label}")
    return ReplayCount(numerator, denominator)


def _replay_funnel(value: object, outcome_count: int) -> ReplayFunnel:
    raw = _exact_keys(value, _FUNNEL_FIELDS, "replay funnel")
    stages = {
        name: _replay_count(raw[name], f"funnel.{name}")
        for name in _FUNNEL_STAGE_FIELDS
    }
    actions_raw = _exact_keys(raw["actions"], {"BUY", "HOLD", "SELL"}, "actions")
    actions = {
        name: _replay_count(actions_raw[name], f"actions.{name}")
        for name in ("BUY", "HOLD", "SELL")
    }
    blocked_raw = raw["blocked_reasons"]
    if not isinstance(blocked_raw, Mapping) or not all(
        isinstance(key, str) and key for key in blocked_raw
    ):
        raise ValueError("blocked_reasons must be an object of stable codes")
    blocked = {
        _bounded(name): _replay_count(blocked_raw[name], f"blocked_reasons.{name}")
        for name in sorted(blocked_raw)
    }
    numerators = [stages[name].numerator for name in _FUNNEL_STAGE_FIELDS]
    if numerators != sorted(numerators, reverse=True):
        raise ValueError("replay funnel is not monotonic")
    expected_denominators = (
        outcome_count,
        stages["evaluated"].numerator,
        stages["selected"].numerator,
        stages["buy_signaled"].numerator,
        stages["confidence_qualified"].numerator,
        stages["risk_qualified"].numerator,
        stages["validly_sized"].numerator,
    )
    if stages["evaluated"] != ReplayCount(outcome_count, outcome_count) or tuple(
        stages[name].denominator for name in _FUNNEL_STAGE_FIELDS
    ) != expected_denominators:
        raise ValueError("replay funnel denominator chain is inconsistent")
    if any(count.denominator != outcome_count for count in actions.values()):
        raise ValueError("replay action denominator is inconsistent")
    if sum(count.numerator for count in actions.values()) != outcome_count:
        raise ValueError("replay action counts do not reconcile")
    if any(count.denominator != outcome_count for count in blocked.values()):
        raise ValueError("replay block denominator is inconsistent")
    return ReplayFunnel(
        stages["evaluated"], stages["selected"], stages["buy_signaled"],
        stages["confidence_qualified"], stages["risk_qualified"],
        stages["validly_sized"], stages["order_eligible"], actions, blocked,
    )


def _replay_verification(value: object) -> ReplayVerification:
    raw = _exact_keys(value, {"passed", "checks"}, "replay verification")
    if not isinstance(raw["passed"], bool) or not isinstance(raw["checks"], list):
        raise ValueError("invalid replay verification")
    checks: list[ReplayCheck] = []
    for item in raw["checks"]:
        check = _exact_keys(item, _CHECK_FIELDS, "replay verification check")
        if not isinstance(check["passed"], bool) or not all(
            isinstance(check[name], str) and check[name]
            for name in _CHECK_FIELDS - {"passed"}
        ):
            raise ValueError("invalid replay verification check")
        checks.append(ReplayCheck(
            _bounded(check["boundary_id"]), _bounded(check["scenario_id"]),
            _bounded(check["ticker"], limit=24), _bounded(check["stage"]),
            _bounded(check["expected"]), _bounded(check["actual"]), check["passed"],
        ))
    if raw["passed"] and not all(check.passed for check in checks):
        raise ValueError("replay verification status contradicts checks")
    return ReplayVerification(raw["passed"], tuple(checks))


def _compatibility_signature(manifest: Mapping[str, Any]) -> tuple[tuple[str, str], ...]:
    fields = {
        "fixture_schema_version": manifest["fixture_schema_version"],
        "policy": manifest["policy"],
        "scenario_hash": manifest["scenario_hash"],
        "ohlcv_hash": manifest["ohlcv_hash"],
        "raw_signal_hash": manifest["raw_signal_hash"],
        "initial_state": manifest["initial_state"],
        "evaluation_time": manifest["evaluation_time"],
        "trading_date": manifest["trading_date"],
    }
    return tuple(
        (name, canonical_json_bytes(fields[name]).decode("utf-8"))
        for name in sorted(fields)
    )


def _load_replay_result(path: Path) -> ReplayInputResult:
    raw_path = Path(path)
    document = _strict_json(raw_path)
    if document["schema_version"] != 1:
        raise ValueError("unsupported normalized replay schema version")
    if not isinstance(document["result_id"], str) or len(document["result_id"]) != 64:
        raise ValueError("invalid replay result identity")
    if not isinstance(document["observational_metadata"], Mapping):
        raise ValueError("observational_metadata must be an object")
    evidence = _exact_keys(document["evidence"], _REPLAY_EVIDENCE_FIELDS, "replay evidence")
    expected_identity = hashlib.sha256(canonical_json_bytes(evidence)).hexdigest()
    if document["result_id"] != expected_identity:
        raise ValueError("replay result identity mismatch")
    manifest = _exact_keys(evidence["manifest"], _REPLAY_MANIFEST_FIELDS, "replay manifest")
    if not isinstance(manifest["policy"], Mapping) or not isinstance(
        manifest["initial_state"], Mapping
    ):
        raise ValueError("replay manifest policy/state must be objects")
    if isinstance(manifest["fixture_schema_version"], bool) or not isinstance(
        manifest["fixture_schema_version"], int
    ):
        raise ValueError("fixture_schema_version must be an integer")
    if not all(
        isinstance(manifest[name], str) and manifest[name]
        for name in _REPLAY_MANIFEST_FIELDS
        - {"policy", "initial_state", "fixture_schema_version"}
    ):
        raise ValueError("invalid replay manifest scalar")
    outcomes = evidence["outcomes"]
    if not isinstance(outcomes, list) or not all(isinstance(item, Mapping) for item in outcomes):
        raise ValueError("replay outcomes must be an ordered object list")
    funnel = _replay_funnel(evidence["funnel"], len(outcomes))
    verification = _replay_verification(evidence["verification"])
    if evidence["disclaimer"] != NON_PROFITABILITY_DISCLAIMER:
        raise ValueError("replay non-profitability disclaimer mismatch")
    return ReplayInputResult(
        source_paths=(raw_path.resolve(),),
        stable_result_id=document["result_id"],
        verification_status="PASSED" if verification.passed else "FAILED",
        compatibility_signature=_compatibility_signature(manifest),
        funnel=funnel,
    )


def load_replay_results(paths: Sequence[Path]) -> tuple[ReplayInputResult, ...]:
    """Strictly verify normalized replay files and deduplicate stable identities."""

    by_id: dict[str, ReplayInputResult] = {}
    order: list[str] = []
    for path in paths:
        loaded = _load_replay_result(Path(path))
        existing = by_id.get(loaded.stable_result_id)
        if existing is None:
            by_id[loaded.stable_result_id] = loaded
            order.append(loaded.stable_result_id)
        else:
            by_id[loaded.stable_result_id] = replace(
                existing, source_paths=existing.source_paths + loaded.source_paths
            )
    return tuple(by_id[result_id] for result_id in order)


def _sum_funnels(funnels: Sequence[ReplayFunnel]) -> ReplayFunnel:
    def add_counts(counts: Sequence[ReplayCount]) -> ReplayCount:
        return ReplayCount(
            sum(count.numerator for count in counts),
            sum(count.denominator for count in counts),
        )

    stages = {
        name: add_counts([getattr(funnel, name) for funnel in funnels])
        for name in _FUNNEL_STAGE_FIELDS
    }
    actions = {
        name: add_counts([funnel.actions[name] for funnel in funnels])
        for name in ("BUY", "HOLD", "SELL")
    }
    blocked_names = sorted({name for funnel in funnels for name in funnel.blocked_reasons})
    blocked = {
        name: add_counts([
            funnel.blocked_reasons.get(name, ReplayCount(0, funnel.evaluated.denominator))
            for funnel in funnels
        ])
        for name in blocked_names
    }
    return ReplayFunnel(
        stages["evaluated"], stages["selected"], stages["buy_signaled"],
        stages["confidence_qualified"], stages["risk_qualified"],
        stages["validly_sized"], stages["order_eligible"], actions, blocked,
    )


def build_replay_report(results: Sequence[ReplayInputResult]) -> ReplayReport:
    grouped: dict[tuple[tuple[str, str], ...], list[ReplayInputResult]] = {}
    for result in results:
        grouped.setdefault(result.compatibility_signature, []).append(result)
    signatures = tuple(grouped)
    varying_fields = tuple(
        name
        for name in (name for name, _ in signatures[0])
        if len({dict(signature)[name] for signature in signatures}) > 1
    ) if signatures else ()
    groups = tuple(
        ReplayCompatibilityGroup(
            signature=signature,
            result_ids=tuple(result.stable_result_id for result in grouped[signature]),
            aggregate_funnel=_sum_funnels(
                [result.funnel for result in grouped[signature]]
            ),
            incompatible_fields=varying_fields,
        )
        for signature in signatures
    )
    return ReplayReport(tuple(results), groups, NON_PROFITABILITY_DISCLAIMER)


def _count_text(count: DenominatorCount) -> str:
    return (
        f"{count.numerator}/{count.total_denominator}"
        f" (판정 가능 분모 {count.determinate_denominator})"
    )


def _render_runs(runs: Sequence[RunReportSection]) -> list[str]:
    lines = ["상세"]
    for run in runs:
        lifecycle = run.run_status.value if run.run_status is not None else "UNKNOWN"
        lines.append(
            f"실행 {run.run_id} | 종류={run.run_kind} | 대상={run.target} | "
            f"수명주기={lifecycle} | 증거={run.run_state.value} | "
            f"최종알림={run.final_summary_notification_state.value}"
        )
        if run.preview_run_id is not None:
            lines.append(
                f"  미리보기={run.preview_run_id} | preview-only="
                f"{','.join(run.preview_only_tickers) or '-'} | run-only="
                f"{','.join(run.run_only_tickers) or '-'}"
            )
        for candidate in run.candidates:
            confidence = "UNKNOWN" if candidate.confidence is None else f"{candidate.confidence:.6g}"
            decision = candidate.decision or "UNKNOWN"
            lines.append(
                f"  {candidate.processing_id}. {candidate.ticker} | 결정={decision} | "
                f"신뢰도={confidence} | 주문={candidate.order_state} | "
                f"조정={candidate.reconciliation_state.value} | 증거={candidate.ticker_state.value} | "
                f"{candidate.reason_code} — {candidate.reason_ko}"
            )
            for attempt in candidate.notification_attempts:
                failure = attempt.failure_category or "-"
                lines.append(
                    f"    알림#{attempt.attempt_id} {attempt.kind.value} "
                    f"{attempt.delivery_state.value} 실패분류={failure}"
                )
        for attempt in run.run_notification_attempts:
            failure = attempt.failure_category or "-"
            lines.append(
                f"  실행알림#{attempt.attempt_id} {attempt.kind.value} "
                f"{attempt.delivery_state.value} 실패분류={failure}"
            )
    return lines


def render_daily_report(report: DailyReport) -> str:
    lines = [
        f"일일 의사결정 보고서 {report.trading_date_kst.isoformat()}",
        "요약",
        f"실행={len(report.runs)} 후보={report.total_candidates}",
        f"완전={_count_text(report.complete)}",
        f"불완전={_count_text(report.incomplete)}",
        f"알수없음={_count_text(report.unknown)}",
        *_render_runs(report.runs),
    ]
    return "\n".join(lines) + "\n"


def render_period_report(report: PeriodReport) -> str:
    lines = [
        f"기간 의사결정 보고서 {report.start_date_kst.isoformat()} ~ "
        f"{report.end_date_kst.isoformat()}",
        "요약",
        f"실행={len(report.runs)} 후보={report.total_candidates}",
        f"완전={_count_text(report.complete)}",
        f"불완전={_count_text(report.incomplete)}",
        f"알수없음={_count_text(report.unknown)}",
        *_render_runs(report.runs),
    ]
    return "\n".join(lines) + "\n"


def _replay_count_text(count: ReplayCount) -> str:
    return f"{count.numerator}/{count.denominator}"


def render_replay_report(report: ReplayReport) -> str:
    lines = ["Replay 검증 보고서", "개별 결과"]
    for result in report.results:
        sources = ",".join(_bounded(path.name) for path in result.source_paths)
        lines.append(
            f"{result.stable_result_id} | 검증={result.verification_status} | 파일={sources}"
        )
    lines.append("호환 그룹")
    for index, group in enumerate(report.groups, 1):
        mismatch = ",".join(group.incompatible_fields) or "없음"
        lines.append(
            f"그룹 {index} | 결과={len(group.result_ids)} | 비호환필드={mismatch}"
        )
        lines.append(
            "  evaluated=" + _replay_count_text(group.aggregate_funnel.evaluated)
            + " selected=" + _replay_count_text(group.aggregate_funnel.selected)
            + " buy-signaled=" + _replay_count_text(group.aggregate_funnel.buy_signaled)
            + " confidence-qualified="
            + _replay_count_text(group.aggregate_funnel.confidence_qualified)
            + " risk-qualified=" + _replay_count_text(group.aggregate_funnel.risk_qualified)
            + " validly-sized=" + _replay_count_text(group.aggregate_funnel.validly_sized)
            + " order-eligible=" + _replay_count_text(group.aggregate_funnel.order_eligible)
        )
        lines.append(
            "  actions=" + ",".join(
                f"{name}:{_replay_count_text(group.aggregate_funnel.actions[name])}"
                for name in ("BUY", "HOLD", "SELL")
            )
        )
    lines.extend(("주의", report.disclaimer))
    return "\n".join(lines) + "\n"
