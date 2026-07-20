"""Independent durable controller journal for controlled soak fault drills."""

from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from .audit_models import sanitize_detail
from .soak_config import validate_store_topology
from .soak_models import (
    DrillVerdict,
    FaultName,
    InjectionBoundary,
    SoakEvidenceClass,
)

CONTROLLER_SCHEMA_VERSION = 1
PathLike = str | Path
_CODE = re.compile(r"[A-Z][A-Z0-9_]{0,63}\Z")


@dataclass(frozen=True)
class CommittedDrillToken:
    """Capability proving that a drill contract survived an independent read-back."""

    drill_id: str
    campaign_id: str
    fault: FaultName
    boundary: InjectionBoundary
    expected_containment: tuple[str, ...]
    required_observations: tuple[str, ...]
    policy_version: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stable_code(value: str, field: str) -> str:
    if not isinstance(value, str) or _CODE.fullmatch(value) is None:
        raise ValueError(f"{field} must be a bounded stable code")
    return value


def _bounded_identifier(value: str, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 128:
        raise ValueError(f"{field} must be a non-empty bounded identifier")
    return value


def _json_codes(values: Sequence[str], field: str) -> str:
    normalized = tuple(_stable_code(value, field) for value in values)
    if not normalized or len(set(normalized)) != len(normalized):
        raise ValueError(f"{field} must contain distinct stable codes")
    return json.dumps(normalized, separators=(",", ":"))


def _controller_path(conn: sqlite3.Connection) -> Path:
    rows = tuple(conn.execute("PRAGMA database_list"))
    if len(rows) != 1 or rows[0][1] != "main" or not rows[0][2]:
        raise RuntimeError("controller must have exactly one file-backed main database")
    return Path(str(rows[0][2])).resolve(strict=True)


def migrate_controller(
    conn: sqlite3.Connection, *, fail_after_step: str | None = None
) -> None:
    """Create the append-only controller schema in one rollback-safe transaction."""

    version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if version > CONTROLLER_SCHEMA_VERSION:
        raise RuntimeError(f"unsupported controller schema version: {version}")
    if version == CONTROLLER_SCHEMA_VERSION:
        return
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """CREATE TABLE drill_contracts (
                drill_id TEXT PRIMARY KEY,
                campaign_id TEXT NOT NULL,
                fault TEXT NOT NULL,
                injection_boundary TEXT NOT NULL,
                expected_containment_json TEXT NOT NULL,
                required_observations_json TEXT NOT NULL,
                policy_version TEXT NOT NULL,
                prepared_at TEXT NOT NULL
            )"""
        )
        if fail_after_step == "contracts":
            raise RuntimeError("injected migration failure")
        conn.execute(
            """CREATE TABLE drill_commits (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                drill_id TEXT NOT NULL UNIQUE REFERENCES drill_contracts(drill_id),
                committed_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE drill_observations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                drill_id TEXT NOT NULL REFERENCES drill_contracts(drill_id),
                observation_type TEXT NOT NULL,
                evidence_class TEXT NOT NULL,
                primary_run_id TEXT,
                ticker TEXT,
                order_intent_id TEXT,
                reconciliation_id TEXT,
                freeze_id TEXT,
                facts_json TEXT NOT NULL,
                observed_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE drill_verdicts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                drill_id TEXT NOT NULL UNIQUE REFERENCES drill_contracts(drill_id),
                verdict TEXT NOT NULL,
                detail_json TEXT NOT NULL,
                finalized_at TEXT NOT NULL
            )"""
        )
        for table in (
            "drill_contracts",
            "drill_commits",
            "drill_observations",
            "drill_verdicts",
        ):
            conn.execute(
                f"""CREATE TRIGGER {table}_no_update BEFORE UPDATE ON {table}
                BEGIN SELECT RAISE(ABORT, 'append-only controller evidence'); END"""
            )
            conn.execute(
                f"""CREATE TRIGGER {table}_no_delete BEFORE DELETE ON {table}
                BEGIN SELECT RAISE(ABORT, 'append-only controller evidence'); END"""
            )
        conn.execute(
            "CREATE INDEX ix_drill_observations_type "
            "ON drill_observations(drill_id,observation_type,id)"
        )
        conn.execute(f"PRAGMA user_version={CONTROLLER_SCHEMA_VERSION}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise


def connect_controller(
    controller_db_path: PathLike,
    primary_audit_db_path: PathLike,
    soak_db_path: PathLike,
) -> sqlite3.Connection:
    """Open only the isolated controller after validating all three store paths."""

    paths = validate_store_topology(
        Path(primary_audit_db_path), Path(soak_db_path), Path(controller_db_path)
    )
    path = paths["controller_db_path"]
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        mode = str(conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]).lower()
        if mode != "wal":
            raise RuntimeError("controller journal WAL unavailable")
        conn.execute("PRAGMA synchronous=FULL")
        if int(conn.execute("PRAGMA synchronous").fetchone()[0]) != 2:
            raise RuntimeError("controller synchronous FULL unavailable")
        migrate_controller(conn)
        return conn
    except Exception:
        conn.close()
        raise


def prepare_drill(
    conn: sqlite3.Connection,
    *,
    campaign_id: str,
    drill_id: str,
    fault: FaultName | str,
    boundary: InjectionBoundary | str,
    expected_containment: Sequence[str],
    required_observations: Sequence[str],
    policy_version: str,
    prepared_at: str | None = None,
) -> str:
    """Durably append the D-21 contract while granting no injection authority."""

    campaign = _bounded_identifier(campaign_id, "campaign_id")
    drill = _bounded_identifier(drill_id, "drill_id")
    policy = _bounded_identifier(policy_version, "policy_version")
    fault_value = FaultName(fault).value
    boundary_value = InjectionBoundary(boundary).value
    containment_json = _json_codes(expected_containment, "expected_containment")
    required_json = _json_codes(required_observations, "required_observations")
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """INSERT INTO drill_contracts (
               drill_id,campaign_id,fault,injection_boundary,expected_containment_json,
               required_observations_json,policy_version,prepared_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (
                drill,
                campaign,
                fault_value,
                boundary_value,
                containment_json,
                required_json,
                policy,
                prepared_at or _now(),
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return drill


def _token_from_row(row: Sequence[Any]) -> CommittedDrillToken:
    return CommittedDrillToken(
        drill_id=str(row[0]),
        campaign_id=str(row[1]),
        fault=FaultName(row[2]),
        boundary=InjectionBoundary(row[3]),
        expected_containment=tuple(json.loads(row[4])),
        required_observations=tuple(json.loads(row[5])),
        policy_version=str(row[6]),
    )


def commit_drill_contract(
    conn: sqlite3.Connection, *, drill_id: str, committed_at: str | None = None
) -> CommittedDrillToken:
    """Commit and independently read back a contract before returning capability."""

    drill = _bounded_identifier(drill_id, "drill_id")
    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute(
            "INSERT INTO drill_commits (drill_id,committed_at) "
            "SELECT drill_id,? FROM drill_contracts WHERE drill_id=?",
            (committed_at or _now(), drill),
        )
        if cursor.rowcount != 1:
            raise ValueError("prepared drill contract does not exist")
        conn.commit()
    except Exception:
        conn.rollback()
        raise

    observer = sqlite3.connect(_controller_path(conn))
    try:
        row = observer.execute(
            """SELECT c.drill_id,c.campaign_id,c.fault,c.injection_boundary,
               c.expected_containment_json,c.required_observations_json,c.policy_version
               FROM drill_contracts c JOIN drill_commits m ON m.drill_id=c.drill_id
               WHERE c.drill_id=?""",
            (drill,),
        ).fetchone()
    finally:
        observer.close()
    if row is None:
        raise RuntimeError("committed drill contract failed independent read-back")
    return _token_from_row(row)


def append_controller_observation(
    conn: sqlite3.Connection,
    *,
    drill_id: str,
    observation_type: str,
    evidence_class: SoakEvidenceClass | str,
    primary_run_id: str | None = None,
    ticker: str | None = None,
    order_intent_id: str | None = None,
    reconciliation_id: str | None = None,
    freeze_id: str | None = None,
    facts: Mapping[str, Any] | None = None,
    observed_at: str | None = None,
) -> int:
    """Append sanitized D-22 cross-store links without claiming atomicity."""

    drill = _bounded_identifier(drill_id, "drill_id")
    kind = _stable_code(observation_type, "observation_type")
    evidence = SoakEvidenceClass(evidence_class).value
    clean = sanitize_detail(facts)
    if conn.execute(
        "SELECT 1 FROM drill_commits WHERE drill_id=?", (drill,)
    ).fetchone() is None:
        raise ValueError("drill contract is not committed")
    if conn.execute(
        "SELECT 1 FROM drill_verdicts WHERE drill_id=?", (drill,)
    ).fetchone() is not None:
        raise ValueError("drill is already terminal")
    try:
        conn.execute("BEGIN IMMEDIATE")
        cursor = conn.execute(
            """INSERT INTO drill_observations (
               drill_id,observation_type,evidence_class,primary_run_id,ticker,
               order_intent_id,reconciliation_id,freeze_id,facts_json,observed_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                drill,
                kind,
                evidence,
                primary_run_id,
                ticker,
                order_intent_id,
                reconciliation_id,
                freeze_id,
                json.dumps(clean, sort_keys=True, separators=(",", ":")),
                observed_at or _now(),
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)
    except Exception:
        conn.rollback()
        raise


def finalize_drill(
    conn: sqlite3.Connection,
    *,
    drill_id: str,
    requested_verdict: DrillVerdict | str,
    finalized_at: str | None = None,
) -> DrillVerdict:
    """Append a one-way verdict, forcing FAIL for missing or failed D-22 checks."""

    drill = _bounded_identifier(drill_id, "drill_id")
    requested = DrillVerdict(requested_verdict)
    if requested is DrillVerdict.UNKNOWN:
        raise ValueError("terminal drill verdict cannot be UNKNOWN")
    row = conn.execute(
        """SELECT c.required_observations_json
           FROM drill_contracts c JOIN drill_commits m ON m.drill_id=c.drill_id
           WHERE c.drill_id=?""",
        (drill,),
    ).fetchone()
    if row is None:
        raise ValueError("drill contract is not committed")
    if conn.execute(
        "SELECT 1 FROM drill_verdicts WHERE drill_id=?", (drill,)
    ).fetchone() is not None:
        raise ValueError("drill is already terminal")
    required = tuple(json.loads(row[0]))
    observations = conn.execute(
        "SELECT observation_type,facts_json FROM drill_observations WHERE drill_id=?",
        (drill,),
    ).fetchall()
    passing = {
        str(kind)
        for kind, facts_json in observations
        if json.loads(facts_json).get("passed") is True
    }
    missing = tuple(code for code in required if code not in passing)
    verdict = (
        DrillVerdict.PASSED
        if requested is DrillVerdict.PASSED and not missing
        else DrillVerdict.FAILED
    )
    detail = {"evidence_complete": not missing, "missing_count": len(missing)}
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """INSERT INTO drill_verdicts
               (drill_id,verdict,detail_json,finalized_at) VALUES (?,?,?,?)""",
            (
                drill,
                verdict.value,
                json.dumps(detail, sort_keys=True, separators=(",", ":")),
                finalized_at or _now(),
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return verdict


def load_pending_drills(conn: sqlite3.Connection) -> tuple[CommittedDrillToken, ...]:
    """Load committed, non-terminal drill capabilities after process restart."""

    rows = conn.execute(
        """SELECT c.drill_id,c.campaign_id,c.fault,c.injection_boundary,
           c.expected_containment_json,c.required_observations_json,c.policy_version
           FROM drill_contracts c JOIN drill_commits m ON m.drill_id=c.drill_id
           LEFT JOIN drill_verdicts v ON v.drill_id=c.drill_id
           WHERE v.drill_id IS NULL ORDER BY m.id"""
    ).fetchall()
    return tuple(_token_from_row(row) for row in rows)


def controller_integrity_check(conn: sqlite3.Connection) -> str:
    """Return SQLite's explicit integrity verdict for the controller journal."""

    rows = tuple(str(row[0]).lower() for row in conn.execute("PRAGMA integrity_check"))
    if rows != ("ok",):
        raise RuntimeError("controller integrity check failed")
    return "ok"


__all__ = [
    "CONTROLLER_SCHEMA_VERSION",
    "CommittedDrillToken",
    "append_controller_observation",
    "commit_drill_contract",
    "connect_controller",
    "controller_integrity_check",
    "finalize_drill",
    "load_pending_drills",
    "migrate_controller",
    "prepare_drill",
]
