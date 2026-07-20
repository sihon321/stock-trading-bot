"""Fault-drill controller and orchestration safety contracts."""

from __future__ import annotations

import json
import signal
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import SecretStr

from trading_bot.config import KisCredentialGroup
from trading_bot import sqlite_audit
from trading_bot.soak_config import SoakSettings
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
from trading_bot.soak_drills import (
    FAULT_REGISTRY,
    DrillService,
    activate_fault,
    build_drill_runtime,
    parse_fault_name,
)
from trading_bot.soak_models import DrillVerdict, FaultName, InjectionBoundary, SoakEvidenceClass
from trading_bot.soak_store import connect_soak_store, create_campaign


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


def _drill_settings(tmp_path: Path) -> SoakSettings:
    return SoakSettings(
        kis_mock=KisCredentialGroup(
            domain="https://openapivts.koreainvestment.com:29443",
            app_key=SecretStr("test-app-key"),
            app_secret=SecretStr("test-app-secret"),
            tr_id_profile="official-example-v1",
            label="mock",
        ),
        kis_mock_account_cano=SecretStr("12345678"),
        primary_audit_db_path=tmp_path / "audit.db",
        soak_db_path=tmp_path / "soak.db",
        controller_db_path=tmp_path / "controller.db",
        accepted_profile_versions=("official-example-v1",),
    )


def _active_campaign(tmp_path: Path, campaign_id: str = "campaign-1") -> SoakSettings:
    settings = _drill_settings(tmp_path)
    sqlite_audit.connect(settings.primary_audit_db_path).close()
    soak = connect_soak_store(settings.soak_db_path)
    create_campaign(
        soak,
        campaign_id=campaign_id,
        accepted_profile_fingerprint="sha256:test",
        accepted_profile_version="official-example-v1",
        field_contract_version="kis-mock-compat-v1",
        ambiguity_policy_version="ambiguity-v1",
        ambiguity_window_seconds=60,
        ambiguity_poll_cadence_seconds=5,
        ambiguity_max_observations=12,
    )
    soak.close()
    return settings


def test_fault_registry_is_exact_immutable_and_has_one_boundary_each() -> None:
    assert set(FAULT_REGISTRY) == set(FaultName)
    assert {spec.name for spec in FAULT_REGISTRY.values()} == set(FaultName)
    assert all(isinstance(spec.boundary, InjectionBoundary) for spec in FAULT_REGISTRY.values())
    assert parse_fault_name("stale-data") is FaultName.STALE_DATA
    assert parse_fault_name("timed-out-llm") is FaultName.LLM_TIMEOUT
    with pytest.raises(TypeError):
        FAULT_REGISTRY[FaultName.STALE_DATA] = FAULT_REGISTRY[FaultName.STALE_DATA]


def test_fault_port_is_built_after_commit_and_activates_exactly_once(tmp_path: Path) -> None:
    settings = _active_campaign(tmp_path)
    runtime = build_drill_runtime(
        fault=FaultName.STALE_DATA,
        campaign_id="campaign-1",
        settings=settings,
        drill_id="drill-one",
    )
    try:
        assert runtime.controller.execute(
            "SELECT COUNT(*) FROM drill_commits WHERE drill_id='drill-one'"
        ).fetchone()[0] == 1
        outcome = activate_fault(runtime.token, runtime.fault_port)
        assert outcome.activation_count == 1
        assert outcome.order_post_count == 0
        with pytest.raises(ValueError, match="exactly once"):
            activate_fault(runtime.token, runtime.fault_port)
    finally:
        runtime.close()


@pytest.mark.parametrize("fault", tuple(FaultName))
def test_every_controlled_drill_is_terminal_and_preserves_campaign_accounting(
    tmp_path: Path, fault: FaultName
) -> None:
    settings = _active_campaign(tmp_path / fault.value)
    before = connect_soak_store(settings.soak_db_path).execute(
        "SELECT availability_failures_used FROM soak_campaigns WHERE campaign_id='campaign-1'"
    ).fetchone()[0]
    result = DrillService(settings=settings).run(fault, "campaign-1")
    soak = connect_soak_store(settings.soak_db_path)

    assert result.verdict is DrillVerdict.PASSED
    assert result.activation_count == 1
    assert result.order_post_count == int(fault is FaultName.ACCEPTED_THEN_TIMEOUT)
    assert soak.execute("SELECT COUNT(*) FROM soak_days").fetchone()[0] == 0
    assert soak.execute(
        "SELECT availability_failures_used FROM soak_campaigns WHERE campaign_id='campaign-1'"
    ).fetchone()[0] == before
    assert soak.execute(
        "SELECT evidence_class FROM soak_drill_links WHERE drill_id=?", (result.drill_id,)
    ).fetchone() == (SoakEvidenceClass.CONTROLLED_INJECTION.value,)


def test_kis_observed_and_controlled_provenance_remain_distinct(tmp_path: Path) -> None:
    settings = _active_campaign(tmp_path)
    runtime = build_drill_runtime(
        fault=FaultName.KIS_API_FAILURE,
        campaign_id="campaign-1",
        settings=settings,
        drill_id="provenance-drill",
    )
    try:
        for evidence in (
            SoakEvidenceClass.CONTROLLED_INJECTION,
            SoakEvidenceClass.KIS_OBSERVED,
        ):
            append_controller_observation(
                runtime.controller,
                drill_id=runtime.token.drill_id,
                observation_type="PROVENANCE_CHECKED",
                evidence_class=evidence,
                facts={"passed": True},
            )
        assert runtime.controller.execute(
            "SELECT evidence_class,COUNT(*) FROM drill_observations "
            "GROUP BY evidence_class ORDER BY evidence_class"
        ).fetchall() == [
            (SoakEvidenceClass.CONTROLLED_INJECTION.value, 1),
            (SoakEvidenceClass.KIS_OBSERVED.value, 1),
        ]
    finally:
        runtime.close()


@pytest.mark.parametrize("fault", (FaultName.INTERRUPTION, FaultName.AUDIT_FAILURE))
def test_process_termination_after_durable_checkpoint_reopens_pending_contract(
    tmp_path: Path, fault: FaultName
) -> None:
    settings = _active_campaign(tmp_path)
    runtime = build_drill_runtime(
        fault=fault,
        campaign_id="campaign-1",
        settings=settings,
        drill_id=f"killed-{fault.value.lower()}",
    )
    drill_id = runtime.token.drill_id
    runtime.close()
    script = """
import os, signal, sys
from trading_bot.soak_controller import connect_controller, append_controller_observation
from trading_bot.soak_models import SoakEvidenceClass
conn = connect_controller(sys.argv[1], sys.argv[2], sys.argv[3])
append_controller_observation(
    conn, drill_id=sys.argv[4], observation_type='INJECTION_ACTIVATED',
    evidence_class=SoakEvidenceClass.CONTROLLED_INJECTION,
    facts={'passed': True, 'durable_checkpoint': True},
)
os.kill(os.getpid(), signal.SIGTERM)
"""
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(settings.controller_db_path),
            str(settings.primary_audit_db_path),
            str(settings.soak_db_path),
            drill_id,
        ],
        check=False,
    )
    assert child.returncode == -signal.SIGTERM
    reopened = connect_controller(
        settings.controller_db_path,
        settings.primary_audit_db_path,
        settings.soak_db_path,
    )
    assert [item.drill_id for item in load_pending_drills(reopened)] == [drill_id]
    assert reopened.execute(
        "SELECT facts_json FROM drill_observations WHERE drill_id=?", (drill_id,)
    ).fetchone() == ('{"durable_checkpoint":true,"passed":true}',)
