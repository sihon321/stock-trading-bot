"""Read-only, provenance-preserving projections of Phase 9 soak evidence."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from .soak_controller import CONTROLLER_SCHEMA_VERSION
from .soak_models import CampaignKind, CampaignState, SoakEvidenceClass
from .soak_store import SOAK_SCHEMA_VERSION
from .sqlite_audit import SCHEMA_VERSION


@dataclass(frozen=True)
class CampaignProgress:
    campaign_id: str
    state: CampaignState
    campaign_kind: CampaignKind
    credited_days: int
    target_days: int
    designated_runs: int
    non_credit_runs: int
    availability_used: int
    availability_budget: int
    safety_failure_code: str | None
    availability_failure_code: str | None


@dataclass(frozen=True)
class ReconciliationSummary:
    total: int
    complete: int
    incomplete: int
    unknown: int
    stages: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class FreezeSummary:
    active_count: int
    tickers: tuple[str, ...]
    ambiguity_count: int
    remaining_order_count: int


@dataclass(frozen=True)
class DrillCoverage:
    evidence_class: SoakEvidenceClass
    required: int
    passed: int
    failed: int
    unknown: int


@dataclass(frozen=True)
class SoakReport:
    campaign: CampaignProgress
    reconciliation: ReconciliationSummary
    freezes: FreezeSummary
    drills: tuple[DrillCoverage, ...]
    cross_store_unknown: int


_PRIMARY_SCHEMA = {
    "runs": {
        "run_id", "started_at", "trading_mode", "dry_run", "run_kind", "status",
        "finished_at", "trading_date_kst", "target", "policy_snapshot", "provenance",
        "parent_run_id", "recovered_at", "recovery_reason",
    },
    "decisions": {
        "id", "run_id", "ticker", "final_action", "parsed_decision", "confidence",
        "parse_error", "risk_override", "override_reason", "order_reason",
        "broker_order_id", "requested_qty", "filled_qty", "current_price",
        "correlation_id", "created_at",
    },
    "ticker_outcomes": {
        "id", "run_id", "ticker", "outcome_code", "reason_code", "detail_json",
        "failed_stage", "order_intent_id", "final_order_state", "created_at",
    },
    "order_events": {
        "id", "order_intent_id", "origin_run_id", "observer_run_id", "ticker",
        "event_type", "submission_id", "broker_order_id", "side", "requested_qty",
        "filled_qty", "unfilled_qty", "broker_status", "duplicate_of_intent_id",
        "detail_json", "observed_at",
    },
    "notification_attempts": {
        "id", "run_id", "ticker", "kind", "delivery_status", "failure_category",
        "detail_json", "observed_at",
    },
}

_SOAK_SCHEMA = {
    "soak_campaigns": {
        "campaign_id", "state", "campaign_kind", "credit_eligible",
        "target_eligible_days", "availability_failure_budget",
        "availability_failures_used", "safety_failure_code",
        "availability_failure_code", "accepted_profile_fingerprint",
        "accepted_profile_version", "field_contract_version",
        "ambiguity_policy_version", "ambiguity_window_seconds",
        "ambiguity_poll_cadence_seconds", "ambiguity_max_observations", "created_at",
    },
    "soak_identity_receipts": {
        "id", "receipt_id", "campaign_id", "target", "domain_class", "account_suffix",
        "profile_version", "policy_version", "detail_json", "observed_at",
    },
    "soak_days": {
        "id", "campaign_id", "trading_date", "run_id", "run_kind", "terminal",
        "credit_state", "credit_detail_json", "designated_at",
    },
    "soak_events": {
        "id", "observation_id", "campaign_id", "run_id", "ticker", "order_intent_id",
        "drill_id", "event_code", "evidence_class", "detail_json", "observed_at",
    },
    "soak_snapshots": {
        "snapshot_id", "campaign_id", "run_id", "stage", "ticker", "completeness",
        "detail_json", "observed_at",
    },
    "soak_snapshot_orders": {
        "id", "observation_id", "snapshot_id", "order_id", "status", "remaining_qty",
        "detail_json",
    },
    "soak_snapshot_fills": {
        "id", "observation_id", "snapshot_id", "order_id", "fill_id", "quantity",
        "price", "detail_json",
    },
    "soak_snapshot_holdings": {
        "id", "observation_id", "snapshot_id", "ticker", "quantity", "average_price",
        "detail_json",
    },
    "soak_snapshot_accounts": {
        "id", "observation_id", "snapshot_id", "available_cash", "total_value",
        "detail_json",
    },
    "soak_comparisons": {
        "id", "comparison_id", "campaign_id", "snapshot_id", "run_id", "ticker",
        "order_intent_id", "verdict", "remaining_order_terminal", "detail_json",
        "observed_at",
    },
    "soak_ambiguity_observations": {
        "id", "observation_id", "campaign_id", "run_id", "ticker", "order_intent_id",
        "verdict", "remaining_order_terminal", "detail_json", "observed_at",
    },
    "soak_ticker_freezes": {
        "id", "freeze_id", "campaign_id", "ticker", "order_intent_id", "freeze_kind",
        "state", "prior_transition_id", "release_evidence_type", "release_evidence_id",
        "detail_json", "observed_at",
    },
    "soak_drill_links": {
        "id", "link_id", "campaign_id", "drill_id", "run_id", "ticker",
        "order_intent_id", "evidence_class", "verdict", "detail_json", "observed_at",
    },
}
_CONTROLLER_SCHEMA = {
    "drill_contracts": {
        "drill_id", "campaign_id", "fault", "injection_boundary",
        "expected_containment_json", "required_observations_json", "policy_version",
        "prepared_at",
    },
    "drill_commits": {"id", "drill_id", "committed_at"},
    "drill_observations": {
        "id", "drill_id", "observation_type", "evidence_class", "primary_run_id",
        "ticker", "order_intent_id", "reconciliation_id", "freeze_id", "facts_json",
        "observed_at",
    },
    "drill_verdicts": {"id", "drill_id", "verdict", "detail_json", "finalized_at"},
}


class ReadOnlySoakRepository:
    """Open the three evidence owners without creating, migrating, or attaching them."""

    def __init__(
        self,
        primary_audit_db_path: Path,
        soak_db_path: Path,
        controller_db_path: Path,
    ) -> None:
        paths = tuple(self._regular_path(value) for value in (
            primary_audit_db_path, soak_db_path, controller_db_path
        ))
        if len(set(paths)) != 3:
            raise ValueError("evidence database paths must be pairwise distinct")
        inodes = {(path.stat().st_dev, path.stat().st_ino) for path in paths}
        if len(inodes) != 3:
            raise ValueError("evidence database paths must be pairwise distinct inodes")
        self.primary_audit_db_path, self.soak_db_path, self.controller_db_path = paths

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
            str(row[0]) for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }

    @staticmethod
    def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
        return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}

    @classmethod
    def _validate_primary(cls, connection: sqlite3.Connection) -> None:
        if int(connection.execute("PRAGMA user_version").fetchone()[0]) != SCHEMA_VERSION:
            raise RuntimeError("unsupported primary audit schema version")
        if cls._tables(connection) != set(_PRIMARY_SCHEMA):
            raise RuntimeError("unsupported primary audit schema tables")
        for table, columns in _PRIMARY_SCHEMA.items():
            if cls._columns(connection, table) != columns:
                raise RuntimeError(f"unsupported primary audit schema: {table}")

    @classmethod
    def _validate_owner(
        cls,
        connection: sqlite3.Connection,
        *,
        version: int,
        schema: dict[str, set[str]],
        owner: str,
    ) -> None:
        if int(connection.execute("PRAGMA user_version").fetchone()[0]) != version:
            raise RuntimeError(f"unsupported {owner} schema version")
        if cls._tables(connection) != set(schema):
            raise RuntimeError(f"unsupported {owner} schema tables")
        for table, columns in schema.items():
            if cls._columns(connection, table) != columns:
                raise RuntimeError(f"unsupported {owner} schema: {table}")

    def transactions(self) -> Iterator[tuple[sqlite3.Connection, sqlite3.Connection, sqlite3.Connection]]:
        """Yield one stable read transaction per owner without claiming atomicity."""

        primary = self._open(self.primary_audit_db_path)
        soak = self._open(self.soak_db_path)
        controller = self._open(self.controller_db_path)
        connections = (primary, soak, controller)
        try:
            self._validate_primary(primary)
            self._validate_owner(
                soak, version=SOAK_SCHEMA_VERSION, schema=_SOAK_SCHEMA, owner="soak"
            )
            self._validate_owner(
                controller,
                version=CONTROLLER_SCHEMA_VERSION,
                schema=_CONTROLLER_SCHEMA,
                owner="controller",
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

    def load(self, campaign_id: str) -> dict[str, Any]:
        iterator = self.transactions()
        connections = next(iterator)
        try:
            return self._load(*connections, campaign_id=campaign_id)
        finally:
            try:
                next(iterator)
            except StopIteration:
                pass

    @staticmethod
    def _load(
        primary: sqlite3.Connection,
        soak: sqlite3.Connection,
        controller: sqlite3.Connection,
        *,
        campaign_id: str,
    ) -> dict[str, Any]:
        campaign = soak.execute(
            "SELECT * FROM soak_campaigns WHERE campaign_id=?", (campaign_id,)
        ).fetchone()
        if campaign is None:
            raise KeyError(campaign_id)
        days = soak.execute(
            "SELECT * FROM soak_days WHERE campaign_id=? ORDER BY id", (campaign_id,)
        ).fetchall()
        events = soak.execute(
            "SELECT * FROM soak_events WHERE campaign_id=? ORDER BY id", (campaign_id,)
        ).fetchall()
        snapshots = soak.execute(
            "SELECT * FROM soak_snapshots WHERE campaign_id=? ORDER BY observed_at,snapshot_id",
            (campaign_id,),
        ).fetchall()
        comparisons = soak.execute(
            "SELECT * FROM soak_comparisons WHERE campaign_id=? ORDER BY id", (campaign_id,)
        ).fetchall()
        freezes = soak.execute(
            """SELECT f.* FROM soak_ticker_freezes f
               WHERE f.campaign_id=? AND f.state='FROZEN'
               AND NOT EXISTS (SELECT 1 FROM soak_ticker_freezes r
                   WHERE r.freeze_id=f.freeze_id AND r.state='RELEASED') ORDER BY f.id""",
            (campaign_id,),
        ).fetchall()
        links = soak.execute(
            "SELECT * FROM soak_drill_links WHERE campaign_id=? ORDER BY id", (campaign_id,)
        ).fetchall()
        controller_rows = {
            str(row["drill_id"]): row
            for row in controller.execute(
                """SELECT c.drill_id,c.campaign_id,v.verdict
                   FROM drill_contracts c
                   LEFT JOIN drill_verdicts v ON v.drill_id=c.drill_id"""
            )
        }
        primary_runs = {
            str(row[0]) for row in primary.execute("SELECT run_id FROM runs")
        }
        primary_subjects = {
            (str(row[0]), str(row[1]), str(row[2]) if row[2] is not None else None)
            for row in primary.execute(
                "SELECT run_id,ticker,order_intent_id FROM ticker_outcomes"
            )
        }
        primary_intents = {
            str(row[0]) for row in primary.execute("SELECT DISTINCT order_intent_id FROM order_events")
        }
        return {
            "campaign": campaign,
            "days": days,
            "events": events,
            "snapshots": snapshots,
            "comparisons": comparisons,
            "freezes": freezes,
            "links": links,
            "controller": controller_rows,
            "primary_runs": primary_runs,
            "primary_subjects": primary_subjects,
            "primary_intents": primary_intents,
        }


def _valid_primary_reference(data: dict[str, Any], row: sqlite3.Row) -> bool:
    run_id = row["run_id"] if "run_id" in row.keys() else None
    ticker = row["ticker"] if "ticker" in row.keys() else None
    intent = row["order_intent_id"] if "order_intent_id" in row.keys() else None
    if run_id is not None and str(run_id) not in data["primary_runs"]:
        return False
    if run_id is not None and ticker is not None:
        subject = (str(run_id), str(ticker), str(intent) if intent is not None else None)
        if subject not in data["primary_subjects"]:
            return False
    if intent is not None and str(intent) not in data["primary_intents"]:
        return False
    return True


def build_soak_report(repo: ReadOnlySoakRepository, campaign_id: str) -> SoakReport:
    """Build a deterministic report while preserving independent evidence dimensions."""

    data = repo.load(campaign_id)
    row = data["campaign"]
    credited = sum(item["credit_state"] == "CREDITED" for item in data["days"])
    non_credit = sum(item["event_code"] == "DAY_NOT_CREDITED" for item in data["events"])
    campaign = CampaignProgress(
        campaign_id=str(row["campaign_id"]),
        state=CampaignState(row["state"]),
        campaign_kind=CampaignKind(row["campaign_kind"]),
        credited_days=credited,
        target_days=int(row["target_eligible_days"]),
        designated_runs=len(data["days"]),
        non_credit_runs=non_credit,
        availability_used=int(row["availability_failures_used"]),
        availability_budget=int(row["availability_failure_budget"]),
        safety_failure_code=row["safety_failure_code"],
        availability_failure_code=row["availability_failure_code"],
    )

    stages: dict[str, int] = {}
    complete = incomplete = unknown = cross_unknown = 0
    for snapshot in data["snapshots"]:
        stage = str(snapshot["stage"])
        stages[stage] = stages.get(stage, 0) + 1
        if not _valid_primary_reference(data, snapshot):
            unknown += 1
            cross_unknown += 1
        elif snapshot["completeness"] == "COMPLETE":
            complete += 1
        elif snapshot["completeness"] == "INCOMPLETE":
            incomplete += 1
        else:
            unknown += 1
    for comparison in data["comparisons"]:
        if not _valid_primary_reference(data, comparison):
            unknown += 1
            cross_unknown += 1
        elif comparison["verdict"] == "MATCHED" and bool(comparison["remaining_order_terminal"]):
            complete += 1
        elif comparison["verdict"] == "MISMATCHED":
            incomplete += 1
        else:
            unknown += 1
    total = complete + incomplete + unknown
    reconciliation = ReconciliationSummary(
        total=total,
        complete=complete,
        incomplete=incomplete,
        unknown=unknown,
        stages=tuple(sorted(stages.items())),
    )

    active_tickers = tuple(sorted({str(item["ticker"]) for item in data["freezes"]}))
    freezes = FreezeSummary(
        active_count=len(data["freezes"]),
        tickers=active_tickers,
        ambiguity_count=sum(item["freeze_kind"] == "AMBIGUITY" for item in data["freezes"]),
        remaining_order_count=sum(
            item["freeze_kind"] != "AMBIGUITY" for item in data["freezes"]
        ),
    )

    coverage: list[DrillCoverage] = []
    for evidence_class in (
        SoakEvidenceClass.CONTROLLED_INJECTION,
        SoakEvidenceClass.KIS_OBSERVED,
        SoakEvidenceClass.SYNTHETIC,
    ):
        relevant = [item for item in data["links"] if item["evidence_class"] == evidence_class.value]
        passed = failed = drill_unknown = 0
        for link in relevant:
            valid_primary = _valid_primary_reference(data, link)
            if evidence_class is SoakEvidenceClass.CONTROLLED_INJECTION:
                controller_row = data["controller"].get(str(link["drill_id"]))
                valid_controller = (
                    controller_row is not None
                    and str(controller_row["campaign_id"]) == campaign_id
                    and controller_row["verdict"] == link["verdict"]
                )
            else:
                valid_controller = True
            if not valid_primary or not valid_controller:
                drill_unknown += 1
                cross_unknown += 1
            elif link["verdict"] == "PASSED":
                passed += 1
            elif link["verdict"] == "FAILED":
                failed += 1
            else:
                drill_unknown += 1
        coverage.append(DrillCoverage(
            evidence_class=evidence_class,
            required=len(relevant),
            passed=passed,
            failed=failed,
            unknown=drill_unknown,
        ))

    return SoakReport(
        campaign=campaign,
        reconciliation=reconciliation,
        freezes=freezes,
        drills=tuple(coverage),
        cross_store_unknown=cross_unknown,
    )


def render_soak_report(report: SoakReport) -> str:
    """Render bounded Korean explanations while retaining stable English codes."""

    campaign = report.campaign
    lines = [
        f"캠페인: {campaign.campaign_id}",
        f"상태: {campaign.state.value} / 종류: {campaign.campaign_kind.value}",
        f"적격일: {campaign.credited_days}/{campaign.target_days}",
        f"지정 실행: {campaign.designated_runs} / 비인정 실행: {campaign.non_credit_runs}",
        f"가용성 실패: {campaign.availability_used}/{campaign.availability_budget}",
        f"영구 안전 래치: {campaign.safety_failure_code or 'NONE'}",
        f"가용성 종료 코드: {campaign.availability_failure_code or 'NONE'}",
        (
            "reconciliation: "
            f"COMPLETE={report.reconciliation.complete}/"
            f"INCOMPLETE={report.reconciliation.incomplete}/"
            f"UNKNOWN={report.reconciliation.unknown}/"
            f"TOTAL={report.reconciliation.total}"
        ),
        f"활성 동결: {report.freezes.active_count} ({','.join(report.freezes.tickers) or 'NONE'})",
        f"교차 저장소 UNKNOWN: {report.cross_store_unknown}",
    ]
    for coverage in report.drills:
        lines.append(
            f"드릴[{coverage.evidence_class.value}]: required={coverage.required} "
            f"passed={coverage.passed} failed={coverage.failed} unknown={coverage.unknown}"
        )
    return "\n".join(lines) + "\n"


__all__ = [
    "CampaignProgress", "DrillCoverage", "FreezeSummary", "ReadOnlySoakRepository",
    "ReconciliationSummary", "SoakReport", "build_soak_report", "render_soak_report",
]
