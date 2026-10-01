"""Strictly read-only calibration projections over audit and soak evidence."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import re
import sqlite3
from typing import Iterator

from .audit_models import RunStatus
from .calibration import (
    CalibrationJudgment,
    CalibrationJudgmentStatus,
    CalibrationSourceCounts,
    EvidenceGrade,
    PolicyField,
    VariantEvaluation,
    VariantMetrics,
    baseline_policy,
    judge_variants,
)
from .replay import NON_PROFITABILITY_DISCLAIMER, canonical_json_bytes
from .soak_reporting import _PRIMARY_SCHEMA, _SOAK_SCHEMA
from .soak_store import SOAK_SCHEMA_VERSION
from .sqlite_audit import SCHEMA_VERSION


_ACTIONS = frozenset({"BUY", "SELL", "HOLD"})
_BAD_RECONCILIATION = {
    "MISMATCHED": "RECONCILIATION_FAILED",
    "UNKNOWN": "RECONCILIATION_UNKNOWN",
}


@dataclass(frozen=True)
class CalibrationObservation:
    ticker: str
    action: str
    confidence: float | None
    current_price: float | None
    risk_override: bool
    available_cash: float | None
    average_price: float | None


@dataclass(frozen=True)
class ObservedCycle:
    run_id: str
    trading_date: str
    observations: tuple[CalibrationObservation, ...]


@dataclass(frozen=True)
class CalibrationRiskCase:
    code: str
    run_id: str | None = None
    ticker: str | None = None
    facts: tuple[tuple[str, str | int | float | bool | None], ...] = ()

    def __post_init__(self) -> None:
        if re.fullmatch(r"[A-Z][A-Z0-9_]{0,63}", self.code) is None:
            raise ValueError("risk case code must be a bounded stable code")


@dataclass(frozen=True)
class CalibrationEvidence:
    campaign_id: str
    eligible_days: int
    grade: EvidenceGrade
    normal_cycles: tuple[ObservedCycle, ...]
    excluded_cycle_ids: tuple[str, ...]
    unknown_cycle_ids: tuple[str, ...]
    risk_cases: tuple[CalibrationRiskCase, ...]
    source_counts: CalibrationSourceCounts

    def __post_init__(self) -> None:
        if self.source_counts.eligible_days != self.eligible_days:
            raise ValueError("eligible-day count does not reconcile")
        if self.source_counts.normal_cycles != len(self.normal_cycles):
            raise ValueError("normal-cycle count does not reconcile")
        if self.source_counts.excluded_cycles != len(self.excluded_cycle_ids):
            raise ValueError("excluded-cycle count does not reconcile")
        if self.source_counts.unknown_cycles != len(self.unknown_cycle_ids):
            raise ValueError("unknown-cycle count does not reconcile")


@dataclass(frozen=True)
class CalibrationReportRow:
    variant_id: str
    changed_field: PolicyField | None
    baseline_value: float | None
    candidate_value: float | None
    selected: bool
    status: CalibrationJudgmentStatus
    metrics: VariantMetrics
    buy_delta: int
    hold_delta: int
    sell_delta: int
    order_eligible_delta: int
    risk_event_delta: int
    exposure_delta: float


@dataclass(frozen=True)
class CalibrationReport:
    calibration_id: str
    campaign_id: str
    source_identities: tuple[str, ...]
    evidence_grade: EvidenceGrade
    eligible_days: int
    normal_cycles: int
    excluded_cycles: int
    unknown_cycles: int
    judgment: CalibrationJudgment
    rows: tuple[CalibrationReportRow, ...]
    risk_cases: tuple[CalibrationRiskCase, ...]
    disclaimer: str = NON_PROFITABILITY_DISCLAIMER

    def __post_init__(self) -> None:
        if re.fullmatch(r"[0-9a-f]{64}", self.calibration_id) is None:
            raise ValueError("calibration_id must be a SHA-256 hex digest")


class ReadOnlyCalibrationEvidenceRepository:
    """Read two independent evidence owners without migration or attachment."""

    def __init__(self, primary_audit_db_path: Path, soak_db_path: Path) -> None:
        primary = self._regular_path(primary_audit_db_path)
        soak = self._regular_path(soak_db_path)
        if primary == soak:
            raise ValueError("evidence database paths must be distinct")
        if (primary.stat().st_dev, primary.stat().st_ino) == (
            soak.stat().st_dev,
            soak.stat().st_ino,
        ):
            raise ValueError("evidence database inodes must be distinct")
        self.primary_audit_db_path = primary
        self.soak_db_path = soak

    @staticmethod
    def _regular_path(value: Path) -> Path:
        raw = Path(value)
        try:
            path = raw.resolve(strict=True)
        except FileNotFoundError:
            raise FileNotFoundError(f"evidence database does not exist: {raw}") from None
        if not path.is_file():
            raise ValueError("evidence database path must be a regular file")
        return path

    @staticmethod
    def _open(path: Path) -> sqlite3.Connection:
        connection = sqlite3.connect(
            f"{path.as_uri()}?mode=ro", uri=True, isolation_level=None
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        return connection

    @staticmethod
    def _tables(connection: sqlite3.Connection) -> set[str]:
        return {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }

    @staticmethod
    def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
        return {
            str(row[1])
            for row in connection.execute(f"PRAGMA table_info({table})")
        }

    @classmethod
    def _validate(
        cls,
        connection: sqlite3.Connection,
        *,
        version: int,
        schema: dict[str, set[str]],
        owner: str,
    ) -> None:
        actual_version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if actual_version != version:
            raise RuntimeError(f"unsupported {owner} schema version")
        actual_tables = cls._tables(connection)
        # The primary audit file also hosts independently versioned portfolio
        # evidence. Validate only the tables this reader owns and consumes.
        tables_valid = (
            set(schema) <= actual_tables
            if owner == "primary audit"
            else actual_tables == set(schema)
        )
        if not tables_valid:
            raise RuntimeError(f"unsupported {owner} schema tables")
        for table, expected_columns in schema.items():
            if cls._columns(connection, table) != set(expected_columns):
                raise RuntimeError(f"unsupported {owner} schema: {table}")

    @contextmanager
    def _transactions(self) -> Iterator[tuple[sqlite3.Connection, sqlite3.Connection]]:
        primary = self._open(self.primary_audit_db_path)
        soak = self._open(self.soak_db_path)
        connections = (primary, soak)
        try:
            self._validate(
                primary,
                version=SCHEMA_VERSION,
                schema=_PRIMARY_SCHEMA,
                owner="primary audit",
            )
            self._validate(
                soak,
                version=SOAK_SCHEMA_VERSION,
                schema=_SOAK_SCHEMA,
                owner="soak",
            )
            for connection in connections:
                connection.execute("BEGIN")
            yield connections
            for connection in connections:
                connection.commit()
        except Exception:
            for connection in connections:
                if connection.in_transaction:
                    connection.rollback()
            raise
        finally:
            for connection in connections:
                connection.close()

    def load(self, campaign_id: str) -> CalibrationEvidence:
        if re.fullmatch(r"[^\x00-\x1f]{1,128}", campaign_id) is None:
            raise ValueError("campaign_id must be non-empty and bounded")
        with self._transactions() as (primary, soak):
            return self._load(primary, soak, campaign_id=campaign_id)

    @staticmethod
    def _load(
        primary: sqlite3.Connection,
        soak: sqlite3.Connection,
        *,
        campaign_id: str,
    ) -> CalibrationEvidence:
        campaign = soak.execute(
            "SELECT * FROM soak_campaigns WHERE campaign_id=?", (campaign_id,)
        ).fetchone()
        if campaign is None:
            raise KeyError(campaign_id)
        days = soak.execute(
            "SELECT * FROM soak_days WHERE campaign_id=? ORDER BY id", (campaign_id,)
        ).fetchall()
        run_ids = tuple(str(day["run_id"]) for day in days)
        runs = ReadOnlyCalibrationEvidenceRepository._load_runs(primary, run_ids)
        decisions = ReadOnlyCalibrationEvidenceRepository._load_decisions(
            primary, run_ids
        )
        comparisons = soak.execute(
            "SELECT * FROM soak_comparisons WHERE campaign_id=? ORDER BY id",
            (campaign_id,),
        ).fetchall()
        ambiguities = soak.execute(
            "SELECT * FROM soak_ambiguity_observations WHERE campaign_id=? ORDER BY id",
            (campaign_id,),
        ).fetchall()
        freezes = soak.execute(
            """SELECT f.* FROM soak_ticker_freezes f
               WHERE f.campaign_id=? AND f.state='FROZEN'
                 AND NOT EXISTS (
                   SELECT 1 FROM soak_ticker_freezes r
                   WHERE r.freeze_id=f.freeze_id AND r.state='RELEASED')
               ORDER BY f.id""",
            (campaign_id,),
        ).fetchall()
        portfolio = ReadOnlyCalibrationEvidenceRepository._load_portfolio(
            soak, campaign_id=campaign_id, run_ids=run_ids
        )

        risks: list[CalibrationRiskCase] = []
        excluded: list[str] = []
        unknown: list[str] = []
        normal: list[ObservedCycle] = []
        bad_runs: set[str] = set()

        for row in comparisons:
            run_id = str(row["run_id"])
            verdict = str(row["verdict"])
            if verdict in _BAD_RECONCILIATION:
                bad_runs.add(run_id)
                risks.append(
                    CalibrationRiskCase(
                        _BAD_RECONCILIATION[verdict],
                        run_id=run_id,
                        ticker=_text_or_none(row["ticker"]),
                        facts=(("remaining_order_terminal", bool(row["remaining_order_terminal"])),),
                    )
                )
            elif not bool(row["remaining_order_terminal"]):
                bad_runs.add(run_id)
                risks.append(
                    CalibrationRiskCase(
                        "RECONCILIATION_NON_TERMINAL",
                        run_id=run_id,
                        ticker=_text_or_none(row["ticker"]),
                    )
                )

        for row in ambiguities:
            if (
                str(row["verdict"]) == "MULTIPLE_OR_INCONCLUSIVE"
                or not bool(row["remaining_order_terminal"])
            ):
                run_id = str(row["run_id"])
                bad_runs.add(run_id)
                risks.append(
                    CalibrationRiskCase(
                        "AMBIGUOUS_SUBMISSION",
                        run_id=run_id,
                        ticker=str(row["ticker"]),
                    )
                )

        active_freeze_tickers = {str(row["ticker"]) for row in freezes}
        for row in freezes:
            risks.append(
                CalibrationRiskCase(
                    "ACTIVE_TICKER_FREEZE",
                    ticker=str(row["ticker"]),
                    facts=(("freeze_kind", str(row["freeze_kind"])),),
                )
            )

        if campaign["safety_failure_code"] is not None:
            risks.append(
                CalibrationRiskCase(
                    "SAFETY_LATCHED",
                    facts=(("reason_code", str(campaign["safety_failure_code"])),),
                )
            )

        for day in days:
            run_id = str(day["run_id"])
            run = runs.get(run_id)
            if run is None:
                unknown.append(run_id)
                risks.append(
                    CalibrationRiskCase("BROKEN_PRIMARY_RUN_REFERENCE", run_id=run_id)
                )
                continue
            eligible = (
                str(day["run_kind"]) == "RUN"
                and bool(day["terminal"])
                and str(day["credit_state"]) == "CREDITED"
            )
            normally_completed = (
                str(run["run_kind"]) == "RUN"
                and str(run["status"]) == RunStatus.COMPLETED.value
                and str(run["target"]) == "mock"
            )
            if not eligible or not normally_completed:
                excluded.append(run_id)
                risks.append(
                    CalibrationRiskCase(
                        "INCOMPLETE_RUN",
                        run_id=run_id,
                        facts=(("status", _text_or_none(run["status"])),),
                    )
                )
                continue
            run_observations = decisions.get(run_id, ())
            if run_id in bad_runs or active_freeze_tickers.intersection(
                observation["ticker"] for observation in run_observations
            ):
                excluded.append(run_id)
                continue
            cash, average_prices = portfolio.get(run_id, (None, {}))
            observations = tuple(
                CalibrationObservation(
                    ticker=str(row["ticker"]),
                    action=_action(row["final_action"]),
                    confidence=_probability(row["confidence"]),
                    current_price=_positive(row["current_price"]),
                    risk_override=bool(row["risk_override"]),
                    available_cash=cash,
                    average_price=average_prices.get(str(row["ticker"])),
                )
                for row in run_observations
                if _valid_ticker(row["ticker"])
            )
            missing_dimensions: list[str] = []
            if cash is None:
                missing_dimensions.append("MAX_POSITION")
            if any(observation.average_price is None for observation in observations):
                missing_dimensions.extend(("STOP_LOSS", "TAKE_PROFIT"))
            if missing_dimensions:
                risks.append(
                    CalibrationRiskCase(
                        "UNEVALUABLE_MISSING_PORTFOLIO_STATE",
                        run_id=run_id,
                        facts=tuple(
                            ("dimension", dimension)
                            for dimension in dict.fromkeys(missing_dimensions)
                        ),
                    )
                )
            normal.append(
                ObservedCycle(
                    run_id=run_id,
                    trading_date=str(day["trading_date"]),
                    observations=observations,
                )
            )

        eligible_days = sum(
            1 for day in days if str(day["credit_state"]) == "CREDITED"
        )
        grade = _grade(
            eligible_days=eligible_days,
            target_days=int(campaign["target_eligible_days"]),
            has_integrity_risk=bool(excluded or unknown or campaign["safety_failure_code"]),
        )
        counts = CalibrationSourceCounts(
            eligible_days=eligible_days,
            normal_cycles=len(normal),
            excluded_cycles=len(excluded),
            unknown_cycles=len(unknown),
        )
        return CalibrationEvidence(
            campaign_id=campaign_id,
            eligible_days=eligible_days,
            grade=grade,
            normal_cycles=tuple(normal),
            excluded_cycle_ids=tuple(excluded),
            unknown_cycle_ids=tuple(unknown),
            risk_cases=tuple(risks),
            source_counts=counts,
        )

    @staticmethod
    def _load_runs(
        primary: sqlite3.Connection, run_ids: tuple[str, ...]
    ) -> dict[str, sqlite3.Row]:
        if not run_ids:
            return {}
        marks = ",".join("?" for _ in run_ids)
        return {
            str(row["run_id"]): row
            for row in primary.execute(
                f"SELECT run_id,run_kind,status,target FROM runs WHERE run_id IN ({marks})",
                run_ids,
            )
        }

    @staticmethod
    def _load_decisions(
        primary: sqlite3.Connection, run_ids: tuple[str, ...]
    ) -> dict[str, tuple[sqlite3.Row, ...]]:
        if not run_ids:
            return {}
        marks = ",".join("?" for _ in run_ids)
        grouped: dict[str, list[sqlite3.Row]] = {}
        for row in primary.execute(
            f"""SELECT id,run_id,ticker,final_action,confidence,current_price,risk_override
                FROM decisions WHERE run_id IN ({marks}) ORDER BY id""",
            run_ids,
        ):
            grouped.setdefault(str(row["run_id"]), []).append(row)
        return {key: tuple(value) for key, value in grouped.items()}

    @staticmethod
    def _load_portfolio(
        soak: sqlite3.Connection,
        *,
        campaign_id: str,
        run_ids: tuple[str, ...],
    ) -> dict[str, tuple[float | None, dict[str, float]]]:
        if not run_ids:
            return {}
        marks = ",".join("?" for _ in run_ids)
        snapshots = soak.execute(
            f"""SELECT snapshot_id,run_id FROM soak_snapshots
                WHERE campaign_id=? AND stage='PRE_RUN' AND completeness='COMPLETE'
                  AND run_id IN ({marks}) ORDER BY observed_at,snapshot_id""",
            (campaign_id, *run_ids),
        ).fetchall()
        result: dict[str, tuple[float | None, dict[str, float]]] = {}
        for snapshot in snapshots:
            snapshot_id = str(snapshot["snapshot_id"])
            cash_rows = soak.execute(
                "SELECT available_cash FROM soak_snapshot_accounts WHERE snapshot_id=? ORDER BY id",
                (snapshot_id,),
            ).fetchall()
            cash = _non_negative(cash_rows[-1][0]) if cash_rows else None
            averages = {
                str(row["ticker"]): value
                for row in soak.execute(
                    "SELECT ticker,average_price FROM soak_snapshot_holdings "
                    "WHERE snapshot_id=? ORDER BY id",
                    (snapshot_id,),
                )
                if (value := _positive(row["average_price"])) is not None
                and _valid_ticker(row["ticker"])
            }
            result[str(snapshot["run_id"])] = (cash, averages)
        return result


def _valid_ticker(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9]{6}", value) is not None


def _action(value: object) -> str:
    text = str(value)
    return text if text in _ACTIONS else "HOLD"


def _probability(value: object) -> float | None:
    number = _number(value)
    return number if number is not None and 0.0 <= number <= 1.0 else None


def _positive(value: object) -> float | None:
    number = _number(value)
    return number if number is not None and number > 0.0 else None


def _non_negative(value: object) -> float | None:
    number = _number(value)
    return number if number is not None and number >= 0.0 else None


def _number(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _text_or_none(value: object) -> str | None:
    if value is None:
        return None
    return str(value)[:96]


def _grade(*, eligible_days: int, target_days: int, has_integrity_risk: bool) -> EvidenceGrade:
    if eligible_days < target_days:
        return EvidenceGrade.INSUFFICIENT
    if has_integrity_risk:
        return EvidenceGrade.LIMITED
    return EvidenceGrade.SUFFICIENT


def _metric_risk_events(metrics: VariantMetrics) -> int:
    return metrics.risk_blocks + metrics.stop_loss_triggers + metrics.take_profit_triggers


def build_calibration_report(
    evidence: CalibrationEvidence,
    evaluations: tuple[VariantEvaluation, ...] | list[VariantEvaluation],
    *,
    source_identities: tuple[str, ...] | list[str],
) -> CalibrationReport:
    """Build one canonical advisory report without parsing or mutating runtime state."""

    sources = tuple(sorted(source_identities))
    if not sources or len(sources) != len(set(sources)):
        raise ValueError("source identities must be non-empty and unique")
    if any(re.fullmatch(r"[^\x00-\x1f]{1,256}", source) is None for source in sources):
        raise ValueError("source identity must be bounded printable text")
    evaluation_rows = tuple(evaluations)
    judgment = judge_variants(evaluation_rows)
    baseline_rows = [row for row in evaluation_rows if row.variant.variant_id == "BASELINE"]
    if len(baseline_rows) != 1:
        raise ValueError("report requires exactly one baseline evaluation")
    baseline = baseline_rows[0]
    baseline_values = baseline_policy().as_mapping()
    report_rows: list[CalibrationReportRow] = []
    for evaluation in evaluation_rows:
        changed_field = evaluation.variant.changed_field
        baseline_value = (
            None if changed_field is None else baseline_values[changed_field.value]
        )
        candidate_value = (
            None
            if changed_field is None
            else evaluation.variant.policy.as_mapping()[changed_field.value]
        )
        selected = evaluation.variant.variant_id == judgment.selected_variant_id
        if evaluation.variant.variant_id == "BASELINE":
            row_status = CalibrationJudgmentStatus.BASELINE
        elif selected and judgment.status is CalibrationJudgmentStatus.PROVISIONAL_CANDIDATE:
            row_status = CalibrationJudgmentStatus.PROVISIONAL_CANDIDATE
        else:
            row_status = CalibrationJudgmentStatus.NO_MEANINGFUL_DIFFERENCE
        metrics = evaluation.metrics
        report_rows.append(
            CalibrationReportRow(
                variant_id=evaluation.variant.variant_id,
                changed_field=changed_field,
                baseline_value=baseline_value,
                candidate_value=candidate_value,
                selected=selected,
                status=row_status,
                metrics=metrics,
                buy_delta=metrics.buy_actions - baseline.metrics.buy_actions,
                hold_delta=metrics.hold_actions - baseline.metrics.hold_actions,
                sell_delta=metrics.sell_actions - baseline.metrics.sell_actions,
                order_eligible_delta=(
                    metrics.order_eligible - baseline.metrics.order_eligible
                ),
                risk_event_delta=(
                    _metric_risk_events(metrics)
                    - _metric_risk_events(baseline.metrics)
                ),
                exposure_delta=(
                    metrics.exposure_total - baseline.metrics.exposure_total
                ),
            )
        )

    identity_document = {
        "schema_version": 1,
        "campaign_id": evidence.campaign_id,
        "source_identities": sources,
        "evidence_grade": evidence.grade,
        "source_counts": evidence.source_counts,
        "risk_cases": evidence.risk_cases,
        "rows": tuple(report_rows),
        "judgment": judgment,
        "disclaimer": NON_PROFITABILITY_DISCLAIMER,
    }
    calibration_id = hashlib.sha256(canonical_json_bytes(identity_document)).hexdigest()
    return CalibrationReport(
        calibration_id=calibration_id,
        campaign_id=evidence.campaign_id,
        source_identities=sources,
        evidence_grade=evidence.grade,
        eligible_days=evidence.eligible_days,
        normal_cycles=len(evidence.normal_cycles),
        excluded_cycles=len(evidence.excluded_cycle_ids),
        unknown_cycles=len(evidence.unknown_cycle_ids),
        judgment=judgment,
        rows=tuple(report_rows),
        risk_cases=evidence.risk_cases,
    )


def _number_text(value: float | None) -> str:
    return "NONE" if value is None else f"{value:g}"


def render_calibration_report(report: CalibrationReport) -> str:
    """Render deterministic Korean operator text with stable English evidence codes."""

    lines = [
        "정책 보정 자문 보고서 [CALIBRATION_ADVISORY_ONLY]",
        f"calibration_id={report.calibration_id}",
        f"campaign_id={report.campaign_id}",
        f"evidence_grade={report.evidence_grade.value}",
    ]
    if report.evidence_grade is EvidenceGrade.INSUFFICIENT:
        lines.append("경고=INSUFFICIENT_EVIDENCE (승격 또는 정책 변경 근거로 사용할 수 없음)")
    lines.extend(
        (
            "표본="
            f"eligible_days={report.eligible_days} "
            f"normal_cycles={report.normal_cycles} "
            f"excluded_cycles={report.excluded_cycles} "
            f"unknown_cycles={report.unknown_cycles}",
            "판정="
            f"status={report.judgment.status.value} "
            f"selected_variant={report.judgment.selected_variant_id} "
            f"risk_event_delta={report.judgment.risk_event_delta:+d} "
            f"exposure_delta={report.judgment.exposure_delta:+g} "
            f"order_eligible_delta={report.judgment.order_eligible_delta:+d}",
            "정렬기준=RISK_EVENTS_ASC,EXPOSURE_ASC,ORDER_ELIGIBLE_ASC (숨은 종합점수 없음)",
        )
    )
    for source in report.source_identities:
        lines.append(f"source_identity={source}")
    lines.append("비교 행:")
    for row in report.rows:
        metrics = row.metrics
        lines.append(
            "- "
            f"variant={row.variant_id} status={row.status.value} "
            f"selected={str(row.selected).lower()} "
            f"changed_field={row.changed_field.value if row.changed_field else 'NONE'} "
            f"baseline_value={_number_text(row.baseline_value)} "
            f"candidate_value={_number_text(row.candidate_value)} "
            f"evaluated={metrics.evaluated}/{metrics.denominator} "
            f"actions=BUY:{metrics.buy_actions},HOLD:{metrics.hold_actions},SELL:{metrics.sell_actions} "
            f"action_deltas=BUY:{row.buy_delta:+d},HOLD:{row.hold_delta:+d},SELL:{row.sell_delta:+d} "
            f"order_eligible={metrics.order_eligible} "
            f"order_eligible_delta={row.order_eligible_delta:+d} "
            f"risk_triggers=BLOCK:{metrics.risk_blocks},STOP_LOSS:{metrics.stop_loss_triggers},TAKE_PROFIT:{metrics.take_profit_triggers} "
            f"risk_event_delta={row.risk_event_delta:+d} "
            f"exposure={metrics.exposure_total:g} exposure_delta={row.exposure_delta:+g} "
            f"expectation_deltas={metrics.expectation_deltas}"
        )
    lines.append("위험 및 평가불가 사례:")
    if not report.risk_cases:
        lines.append("- NONE")
    for case in report.risk_cases:
        facts = ",".join(f"{key}={value}" for key, value in case.facts) or "NONE"
        lines.append(
            f"- code={case.code} run_id={case.run_id or 'NONE'} "
            f"ticker={case.ticker or 'NONE'} facts={facts}"
        )
    lines.extend(
        (
            "주의=이 결과는 읽기 전용 반사실 자문이며 실행 설정을 변경하거나 실거래를 활성화하지 않습니다.",
            report.disclaimer,
        )
    )
    return "\n".join(lines) + "\n"


__all__ = [
    "CalibrationEvidence",
    "CalibrationObservation",
    "CalibrationReport",
    "CalibrationReportRow",
    "CalibrationRiskCase",
    "ObservedCycle",
    "ReadOnlyCalibrationEvidenceRepository",
    "build_calibration_report",
    "render_calibration_report",
]
