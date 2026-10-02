"""Read-only, provenance-preserving projections of Phase 9 soak evidence."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import AbstractSet, Any, Iterator, Mapping

from .evidence_contracts import (
    CONTROLLER_SCHEMA_VERSION,
    CONTROLLER_REPORT_SCHEMA as _CONTROLLER_SCHEMA,
    PRIMARY_AUDIT_SCHEMA_VERSION as SCHEMA_VERSION,
    PRIMARY_REPORT_SCHEMA as _PRIMARY_SCHEMA,
    SOAK_REPORT_SCHEMA as _SOAK_SCHEMA,
    SOAK_SCHEMA_VERSION,
)
from .soak_models import (
    CampaignKind,
    CampaignState,
    PRE_RUN_PREFLIGHT_RUN_ID,
    ReconciliationStage,
    SoakEvidenceClass,
)


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
    resolved_historical_ambiguity: int = 0




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
        if not set(_PRIMARY_SCHEMA) <= cls._tables(connection):
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
        schema: Mapping[str, AbstractSet[str]],
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
        legacy_pre_run_snapshot_ids = {
            str(row[0])
            for row in soak.execute(
                """SELECT s.snapshot_id
                   FROM soak_snapshots s
                   WHERE s.campaign_id=? AND s.stage=? AND s.ticker IS NULL
                     AND EXISTS (SELECT 1 FROM soak_snapshot_accounts a
                                 WHERE a.snapshot_id=s.snapshot_id)
                     AND NOT EXISTS (SELECT 1 FROM soak_snapshot_orders o
                                     WHERE o.snapshot_id=s.snapshot_id)
                     AND NOT EXISTS (SELECT 1 FROM soak_snapshot_fills f
                                     WHERE f.snapshot_id=s.snapshot_id)
                     AND NOT EXISTS (SELECT 1 FROM soak_snapshot_holdings h
                                     WHERE h.snapshot_id=s.snapshot_id)""",
                (campaign_id, ReconciliationStage.PRE_RUN.value),
            )
        }
        comparisons = soak.execute(
            "SELECT * FROM soak_comparisons WHERE campaign_id=? ORDER BY id", (campaign_id,)
        ).fetchall()
        freezes = soak.execute(
            """SELECT f.* FROM soak_ticker_freezes f
               WHERE f.campaign_id=? AND f.state='FROZEN' ORDER BY f.id""",
            (campaign_id,),
        ).fetchall()
        releases = soak.execute(
            "SELECT * FROM soak_ticker_freezes WHERE campaign_id=? AND state='RELEASED' ORDER BY id",
            (campaign_id,),
        ).fetchall()
        ambiguity_observations = soak.execute(
            "SELECT * FROM soak_ambiguity_observations WHERE campaign_id=? ORDER BY id",
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
            "legacy_pre_run_snapshot_ids": legacy_pre_run_snapshot_ids,
            "comparisons": comparisons,
            "freezes": freezes,
            "releases": releases,
            "ambiguity_observations": ambiguity_observations,
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
    if run_id is not None and ticker is not None and intent is None:
        subject = (str(run_id), str(ticker), str(intent) if intent is not None else None)
        if subject not in data["primary_subjects"]:
            return False
    if intent is not None and str(intent) not in data["primary_intents"]:
        return False
    return True


def _valid_snapshot_reference(data: dict[str, Any], row: sqlite3.Row) -> bool:
    campaign_scope_run_ids = {
        ReconciliationStage.STARTUP.value: "startup",
        ReconciliationStage.RESUME.value: "resume",
    }
    expected_run_id = campaign_scope_run_ids.get(str(row["stage"]))
    if expected_run_id is not None:
        return str(row["run_id"]) == expected_run_id and row["ticker"] is None

    # A PRE_RUN snapshot is campaign-scoped only before any execution identity
    # exists. All ordinary PRE_RUN snapshots must retain their primary-audit link.
    if str(row["stage"]) == ReconciliationStage.PRE_RUN.value:
        if (
            str(row["run_id"]) == PRE_RUN_PREFLIGHT_RUN_ID
            and row["ticker"] is None
        ):
            return True
        # Before PRE_RUN snapshots were made campaign-scoped, a no-order
        # preflight could be persisted with a generated future run ID.  It is
        # still safely campaign-scoped only when no run was designated and no
        # comparison ever claimed that ID, and the immutable snapshot carries
        # account evidence but no order, fill, or holding evidence.
        if (
            str(row["snapshot_id"]) in data["legacy_pre_run_snapshot_ids"]
            and str(row["run_id"]) not in data["primary_runs"]
            and all(str(day["run_id"]) != str(row["run_id"]) for day in data["days"])
            and all(
                str(comparison["run_id"]) != str(row["run_id"])
                for comparison in data["comparisons"]
            )
        ):
            return True
        return _valid_primary_reference(data, row)

    return _valid_primary_reference(data, row)


def _valid_comparison_reference(data: dict[str, Any], row: sqlite3.Row) -> bool:
    """Accept a campaign RESUME comparison only when both evidence owners anchor it."""

    if str(row["run_id"]) != "resume":
        return _valid_primary_reference(data, row)

    snapshot_id = row["snapshot_id"]
    intent_id = row["order_intent_id"]
    if snapshot_id is None or intent_id is None or str(intent_id) not in data["primary_intents"]:
        return False
    snapshots = [
        snapshot for snapshot in data["snapshots"]
        if str(snapshot["snapshot_id"]) == str(snapshot_id)
        and str(snapshot["campaign_id"]) == str(data["campaign"]["campaign_id"])
    ]
    return len(snapshots) == 1 and _valid_snapshot_reference(data, snapshots[0])


def _valid_release(data: dict[str, Any], frozen: sqlite3.Row, release: sqlite3.Row) -> bool:
    """Only same-subject, primary-linked terminal truth resolves a freeze."""

    if (
        release["prior_transition_id"] != frozen["id"]
        or release["id"] <= frozen["id"]
        or frozen["order_intent_id"] is None
        or any(release[key] != frozen[key] for key in (
            "freeze_id", "campaign_id", "ticker", "order_intent_id", "freeze_kind"
        ))
    ):
        return False
    if release["release_evidence_type"] == "COMPARISON":
        rows = data["comparisons"]
        identity_key = "comparison_id"
        terminal_verdicts = {"MATCHED"}
        valid_reference = _valid_comparison_reference
    elif release["release_evidence_type"] == "AMBIGUITY_OBSERVATION":
        rows = data["ambiguity_observations"]
        identity_key = "observation_id"
        terminal_verdicts = {"NO_MATCH_CONFIRMED", "ONE_MATCH_DETERMINATE"}
        valid_reference = _valid_primary_reference
    else:
        return False
    matches = [row for row in rows if row[identity_key] == release["release_evidence_id"]]
    if len(matches) != 1:
        return False
    evidence = matches[0]
    return (
        all(evidence[key] == frozen[key] for key in ("campaign_id", "ticker", "order_intent_id"))
        and evidence["verdict"] in terminal_verdicts
        and bool(evidence["remaining_order_terminal"])
        and valid_reference(data, evidence)
    )


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
        if not _valid_snapshot_reference(data, snapshot):
            unknown += 1
            cross_unknown += 1
        elif snapshot["completeness"] == "COMPLETE":
            complete += 1
        elif snapshot["completeness"] == "INCOMPLETE":
            incomplete += 1
        else:
            unknown += 1
    latest_comparisons = {}
    for comparison in data["comparisons"]:
        key = str(comparison["order_intent_id"] or comparison["comparison_id"])
        latest_comparisons[key] = comparison
    for comparison in latest_comparisons.values():
        if not _valid_comparison_reference(data, comparison):
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

    active_freezes = []
    resolved_ambiguity = set()
    valid_release_ids = set()
    for frozen in data["freezes"]:
        releases = [row for row in data["releases"] if row["freeze_id"] == frozen["freeze_id"]]
        if len(releases) == 1 and _valid_release(data, frozen, releases[0]):
            valid_release_ids.add(releases[0]["id"])
            if frozen["freeze_kind"] == "AMBIGUITY":
                resolved_ambiguity.add(str(frozen["freeze_id"]))
        else:
            active_freezes.append(frozen)
    cross_unknown += sum(row["id"] not in valid_release_ids for row in data["releases"])
    active_tickers = tuple(sorted({str(item["ticker"]) for item in active_freezes}))
    freezes = FreezeSummary(
        active_count=len(active_freezes),
        tickers=active_tickers,
        ambiguity_count=sum(item["freeze_kind"] == "AMBIGUITY" for item in active_freezes),
        remaining_order_count=sum(
            item["freeze_kind"] != "AMBIGUITY" for item in active_freezes
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
        resolved_historical_ambiguity=len(resolved_ambiguity),
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
