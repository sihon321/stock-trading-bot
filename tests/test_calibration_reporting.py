"""Read-only calibration evidence projection contracts."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from trading_bot import sqlite_audit, soak_store
from trading_bot.audit_models import RunKind, RunStatus
from trading_bot.calibration import EvidenceGrade
from trading_bot.calibration_reporting import ReadOnlyCalibrationEvidenceRepository


def _stores(tmp_path: Path, *, target_days: int = 20) -> tuple[Path, Path]:
    audit_path = tmp_path / "audit.db"
    soak_path = tmp_path / "soak.db"
    sqlite_audit.connect(audit_path).close()
    soak = soak_store.connect_soak_store(soak_path)
    soak_store.create_campaign(
        soak,
        campaign_id="campaign-1",
        accepted_profile_fingerprint="sha256:test",
        accepted_profile_version="official-example-v1",
        field_contract_version="kis-mock-compat-v1",
        ambiguity_policy_version="ambiguity-v1",
        ambiguity_window_seconds=60,
        ambiguity_poll_cadence_seconds=5,
        ambiguity_max_observations=12,
        target_eligible_days=target_days,
        availability_failure_budget=2,
    )
    soak.close()
    return audit_path, soak_path


def _run(
    audit_path: Path,
    soak_path: Path,
    *,
    index: int,
    status: RunStatus = RunStatus.COMPLETED,
    decisions: int = 1,
) -> str:
    run_id = f"run-{index}"
    day = f"2026-07-{index:02d}"
    audit = sqlite_audit.connect(audit_path)
    sqlite_audit.start_run(
        audit,
        run_id=run_id,
        trading_mode="mock",
        dry_run=False,
        run_kind=RunKind.RUN,
        status=status,
        started_at=f"{day}T00:00:00+00:00",
        trading_date_kst=day.replace("-", ""),
        target="mock",
    )
    for decision_index in range(decisions):
        ticker = f"{decision_index + 1:06d}"
        event = SimpleNamespace(
            ticker=ticker,
            final_action="BUY" if decision_index % 2 == 0 else "HOLD",
            parsed_decision="BUY" if decision_index % 2 == 0 else "HOLD",
            parse_error=None,
            risk_override=False,
            override_reason="",
            order_reason="test",
            broker_order_id=None,
        )
        sqlite_audit.write_decision(
            audit,
            run_id,
            event,
            confidence=0.81,
            current_price=70_000,
            correlation_id=f"corr-{run_id}-{ticker}",
        )
    audit.close()
    soak = soak_store.connect_soak_store(soak_path)
    soak_store.designate_day(
        soak,
        campaign_id="campaign-1",
        trading_date=day,
        run_id=run_id,
        run_kind="RUN",
        terminal=True,
        credit_state="CREDITED",
    )
    soak.close()
    return run_id


def test_readonly_load_preserves_database_bytes_and_versions(tmp_path: Path) -> None:
    audit_path, soak_path = _stores(tmp_path)
    _run(audit_path, soak_path, index=1)
    before = {path: path.read_bytes() for path in (audit_path, soak_path)}
    versions_before = {
        path: sqlite_audit.sqlite3.connect(path).execute("PRAGMA user_version").fetchone()[0]
        for path in (audit_path, soak_path)
    }

    evidence = ReadOnlyCalibrationEvidenceRepository(audit_path, soak_path).load(
        "campaign-1"
    )

    assert len(evidence.normal_cycles) == 1
    assert before == {path: path.read_bytes() for path in (audit_path, soak_path)}
    assert versions_before == {
        path: sqlite_audit.sqlite3.connect(path).execute("PRAGMA user_version").fetchone()[0]
        for path in (audit_path, soak_path)
    }


def test_evidence_keeps_abnormal_and_broken_runs_out_of_normal_denominator(
    tmp_path: Path,
) -> None:
    audit_path, soak_path = _stores(tmp_path)
    normal_id = _run(audit_path, soak_path, index=1)
    failed_id = _run(
        audit_path, soak_path, index=2, status=RunStatus.FAILED
    )
    unknown_id = "missing-primary-run"
    soak = soak_store.connect_soak_store(soak_path)
    soak_store.designate_day(
        soak,
        campaign_id="campaign-1",
        trading_date="2026-07-03",
        run_id=unknown_id,
        run_kind="RUN",
        terminal=True,
        credit_state="CREDITED",
    )
    soak_store.append_comparison(
        soak,
        comparison_id="comparison-unknown",
        campaign_id="campaign-1",
        run_id=normal_id,
        ticker="000001",
        verdict="UNKNOWN",
        remaining_order_terminal=False,
    )
    soak_store.freeze_ticker(
        soak,
        freeze_id="freeze-1",
        campaign_id="campaign-1",
        ticker="000001",
        order_intent_id="intent-1",
        freeze_kind="AMBIGUITY",
    )
    soak.close()

    evidence = ReadOnlyCalibrationEvidenceRepository(audit_path, soak_path).load(
        "campaign-1"
    )

    assert evidence.normal_cycles == ()
    assert evidence.excluded_cycle_ids == (normal_id, failed_id)
    assert evidence.unknown_cycle_ids == (unknown_id,)
    assert evidence.source_counts.total_cycles == 3
    codes = {case.code for case in evidence.risk_cases}
    assert {
        "RECONCILIATION_UNKNOWN",
        "ACTIVE_TICKER_FREEZE",
        "INCOMPLETE_RUN",
        "BROKEN_PRIMARY_RUN_REFERENCE",
    } <= codes


def test_denominator_uses_eligible_days_not_decision_or_drill_rows(tmp_path: Path) -> None:
    audit_path, soak_path = _stores(tmp_path)
    for index in range(1, 11):
        run_id = _run(audit_path, soak_path, index=index, decisions=12)
        soak = soak_store.connect_soak_store(soak_path)
        for drill_index in range(5):
            soak_store.append_drill_link(
                soak,
                link_id=f"link-{index}-{drill_index}",
                campaign_id="campaign-1",
                drill_id=f"drill-{index}-{drill_index}",
                run_id=run_id,
                evidence_class="CONTROLLED_INJECTION",
                verdict="PASSED",
            )
        soak.close()

    evidence = ReadOnlyCalibrationEvidenceRepository(audit_path, soak_path).load(
        "campaign-1"
    )

    assert evidence.eligible_days == 10
    assert len(evidence.normal_cycles) == 10
    assert sum(len(cycle.observations) for cycle in evidence.normal_cycles) == 120
    assert evidence.grade is EvidenceGrade.INSUFFICIENT
    assert "UNEVALUABLE_MISSING_PORTFOLIO_STATE" in {
        case.code for case in evidence.risk_cases
    }


def test_readonly_repository_rejects_missing_or_unsupported_schema_without_creation(
    tmp_path: Path,
) -> None:
    audit_path, soak_path = _stores(tmp_path)
    missing = tmp_path / "missing.db"
    with pytest.raises(FileNotFoundError):
        ReadOnlyCalibrationEvidenceRepository(missing, soak_path)
    assert not missing.exists()

    raw = sqlite_audit.sqlite3.connect(audit_path)
    raw.execute("PRAGMA user_version=999")
    raw.commit()
    raw.close()
    with pytest.raises(RuntimeError, match="primary audit schema version"):
        ReadOnlyCalibrationEvidenceRepository(audit_path, soak_path).load("campaign-1")
