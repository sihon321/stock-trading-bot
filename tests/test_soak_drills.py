"""Fault-drill controller and orchestration safety contracts."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from trading_bot.soak_controller import (
    CONTROLLER_SCHEMA_VERSION,
    append_controller_observation,
    commit_drill_contract,
    connect_controller,
    controller_integrity_check,
    finalize_drill,
    load_pending_drills,
    migrate_controller,
    prepare_drill,
)
from trading_bot.soak_models import DrillVerdict, FaultName, InjectionBoundary, SoakEvidenceClass


def _paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    return tmp_path / "controller.db", tmp_path / "audit.db", tmp_path / "soak.db"


def _prepared(conn: sqlite3.Connection, *, drill_id: str = "drill-1") -> str:
    return prepare_drill(
        conn,
        campaign_id="campaign-1",
        drill_id=drill_id,
        fault=FaultName.AUDIT_FAILURE,
        boundary=InjectionBoundary.AUDIT,
        expected_containment=("NO_ORDER_POST", "CONTROLLER_SURVIVES"),
        required_observations=(
            "CONTAINMENT_CHECKED",
            "PRIMARY_AUDIT_CHECKED",
            "RESTART_CHECKED",
            "PROHIBITED_ACTIONS_CHECKED",
        ),
        policy_version="fault-drill-v1",
    )


@pytest.mark.parametrize(
    ("left", "right"),
    ((0, 1), (0, 2), (1, 2)),
)
def test_controller_rejects_every_store_path_alias(
    tmp_path: Path, left: int, right: int
) -> None:
    paths = list(_paths(tmp_path))
    paths[right] = paths[left]
    with pytest.raises(ValueError, match="pairwise distinct"):
        connect_controller(paths[0], paths[1], paths[2])


def test_controller_rejects_existing_same_inode_alias(tmp_path: Path) -> None:
    controller, audit, soak = _paths(tmp_path)
    audit.touch()
    soak.hardlink_to(audit)
    with pytest.raises(ValueError, match="same inode"):
        connect_controller(controller, audit, soak)


def test_controller_uses_full_wal_without_attaching_other_stores(tmp_path: Path) -> None:
    controller, audit, soak = _paths(tmp_path)
    conn = connect_controller(controller, audit, soak)

    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    assert int(conn.execute("PRAGMA synchronous").fetchone()[0]) == 2
    assert int(conn.execute("PRAGMA foreign_keys").fetchone()[0]) == 1
    assert conn.execute("PRAGMA user_version").fetchone()[0] == CONTROLLER_SCHEMA_VERSION
    assert [row[1] for row in conn.execute("PRAGMA database_list")] == ["main"]


def test_migration_failure_rolls_back_and_reopen_retries(tmp_path: Path) -> None:
    controller, audit, soak = _paths(tmp_path)
    conn = sqlite3.connect(controller)
    conn.execute("PRAGMA foreign_keys=ON")
    with pytest.raises(RuntimeError, match="injected"):
        migrate_controller(conn, fail_after_step="contracts")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE name='drill_contracts'"
    ).fetchone() is None
    conn.close()

    reopened = connect_controller(controller, audit, soak)
    assert reopened.execute("PRAGMA user_version").fetchone()[0] == CONTROLLER_SCHEMA_VERSION


def test_commit_returns_capability_only_after_independent_read_back(tmp_path: Path) -> None:
    controller, audit, soak = _paths(tmp_path)
    conn = connect_controller(controller, audit, soak)
    _prepared(conn)

    token = commit_drill_contract(conn, drill_id="drill-1")

    assert token.drill_id == "drill-1"
    assert token.fault is FaultName.AUDIT_FAILURE
    assert token.boundary is InjectionBoundary.AUDIT
    observer = sqlite3.connect(controller)
    assert observer.execute(
        "SELECT drill_id FROM drill_commits WHERE drill_id='drill-1'"
    ).fetchone() == ("drill-1",)


def test_primary_audit_and_soak_unavailability_do_not_block_terminal_controller_evidence(
    tmp_path: Path,
) -> None:
    controller, audit, soak = _paths(tmp_path)
    conn = connect_controller(controller, audit, soak)
    _prepared(conn)
    commit_drill_contract(conn, drill_id="drill-1")
    audit.mkdir()
    soak.mkdir()

    for kind in (
        "CONTAINMENT_CHECKED",
        "PRIMARY_AUDIT_CHECKED",
        "RESTART_CHECKED",
        "PROHIBITED_ACTIONS_CHECKED",
    ):
        append_controller_observation(
            conn,
            drill_id="drill-1",
            observation_type=kind,
            evidence_class=SoakEvidenceClass.CONTROLLED_INJECTION,
            facts={"passed": True},
        )
    verdict = finalize_drill(conn, drill_id="drill-1", requested_verdict=DrillVerdict.PASSED)

    assert verdict is DrillVerdict.PASSED
    assert controller_integrity_check(conn) == "ok"


def test_missing_required_evidence_forces_fail_and_terminal_verdict_is_immutable(
    tmp_path: Path,
) -> None:
    controller, audit, soak = _paths(tmp_path)
    conn = connect_controller(controller, audit, soak)
    _prepared(conn)
    commit_drill_contract(conn, drill_id="drill-1")
    append_controller_observation(
        conn,
        drill_id="drill-1",
        observation_type="CONTAINMENT_CHECKED",
        evidence_class=SoakEvidenceClass.CONTROLLED_INJECTION,
        facts={"passed": True},
    )

    assert finalize_drill(
        conn, drill_id="drill-1", requested_verdict=DrillVerdict.PASSED
    ) is DrillVerdict.FAILED
    with pytest.raises(ValueError, match="already terminal"):
        finalize_drill(conn, drill_id="drill-1", requested_verdict=DrillVerdict.PASSED)
    with pytest.raises(sqlite3.IntegrityError, match="append-only"):
        conn.execute("UPDATE drill_observations SET observation_type='ALTERED'")


def test_pending_contract_reopens_in_a_second_process(tmp_path: Path) -> None:
    controller, audit, soak = _paths(tmp_path)
    conn = connect_controller(controller, audit, soak)
    _prepared(conn, drill_id="restart-drill")
    commit_drill_contract(conn, drill_id="restart-drill")
    conn.close()

    script = """
import json, sys
from trading_bot.soak_controller import connect_controller, load_pending_drills
conn = connect_controller(sys.argv[1], sys.argv[2], sys.argv[3])
print(json.dumps([row.drill_id for row in load_pending_drills(conn)]))
"""
    result = subprocess.run(
        [sys.executable, "-c", script, str(controller), str(audit), str(soak)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert json.loads(result.stdout) == ["restart-drill"]


def test_observations_reject_sensitive_or_nested_facts(tmp_path: Path) -> None:
    controller, audit, soak = _paths(tmp_path)
    conn = connect_controller(controller, audit, soak)
    _prepared(conn)
    commit_drill_contract(conn, drill_id="drill-1")

    with pytest.raises(ValueError, match="forbidden"):
        append_controller_observation(
            conn,
            drill_id="drill-1",
            observation_type="PRIMARY_AUDIT_CHECKED",
            evidence_class=SoakEvidenceClass.CONTROLLED_INJECTION,
            facts={"raw_payload": "secret"},
        )
    with pytest.raises(TypeError, match="scalar"):
        append_controller_observation(
            conn,
            drill_id="drill-1",
            observation_type="PRIMARY_AUDIT_CHECKED",
            evidence_class=SoakEvidenceClass.CONTROLLED_INJECTION,
            facts={"nested": {"value": 1}},
        )
