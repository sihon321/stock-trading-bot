"""Truthful, read-only Phase 9 soak reporting contracts."""

from __future__ import annotations

from pathlib import Path

import pytest

from trading_bot import sqlite_audit, soak_store
from trading_bot.audit_models import RunKind
from trading_bot.soak_controller import (
    append_controller_observation,
    commit_drill_contract,
    connect_controller,
    finalize_drill,
    prepare_drill,
)
from trading_bot.soak_models import (
    DrillVerdict,
    FaultName,
    InjectionBoundary,
    SoakEvidenceClass,
)
from trading_bot.soak_reporting import (
    ReadOnlySoakRepository,
    build_soak_report,
    render_soak_report,
)


def _stores(tmp_path: Path) -> tuple[Path, Path, Path]:
    audit_path = tmp_path / "audit.db"
    soak_path = tmp_path / "soak.db"
    controller_path = tmp_path / "controller.db"
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
        target_eligible_days=20,
        availability_failure_budget=2,
    )
    soak.close()
    connect_controller(controller_path, audit_path, soak_path).close()
    return audit_path, soak_path, controller_path


def _repository(paths: tuple[Path, Path, Path]) -> ReadOnlySoakRepository:
    audit, soak, controller = paths
    return ReadOnlySoakRepository(audit, soak, controller)


def test_report_is_byte_preserving_and_keeps_accounting_dimensions_distinct(
    tmp_path: Path,
) -> None:
    paths = _stores(tmp_path)
    audit_path, soak_path, _ = paths
    audit = sqlite_audit.connect(audit_path)
    sqlite_audit.start_run(
        audit,
        run_id="run-1",
        trading_mode="mock",
        dry_run=False,
        run_kind=RunKind.RUN,
        started_at="2026-07-20T00:00:00+00:00",
        trading_date_kst="20260720",
        target="mock",
    )
    audit.close()
    soak = soak_store.connect_soak_store(soak_path)
    soak_store.designate_day(
        soak,
        campaign_id="campaign-1",
        trading_date="2026-07-20",
        run_id="run-1",
        run_kind="RUN",
        terminal=True,
        credit_state="CREDITED",
    )
    soak_store.append_campaign_event(
        soak,
        campaign_id="campaign-1",
        run_id="run-closed",
        event_code="DAY_NOT_CREDITED",
        detail={"verdict_code": "CLOSED_DATE"},
    )
    soak_store.freeze_ticker(
        soak,
        freeze_id="freeze-proof",
        campaign_id="campaign-1",
        ticker="000660",
        order_intent_id="intent-proof",
        freeze_kind="AMBIGUITY",
        detail={"reason_code": "AMBIGUOUS_SUBMISSION"},
    )
    soak.close()

    before = {path: path.read_bytes() for path in paths}
    report = build_soak_report(_repository(paths), "campaign-1")
    after = {path: path.read_bytes() for path in paths}

    assert before == after
    assert report.campaign.credited_days == 1
    assert report.campaign.target_days == 20
    assert report.campaign.designated_runs == 1
    assert report.campaign.non_credit_runs == 1
    assert report.campaign.availability_used == 0
    assert report.campaign.availability_budget == 2
    assert report.campaign.safety_failure_code is None
    assert report.freezes.active_count == 1
    assert report.freezes.tickers == ("000660",)
    assert "000660" in render_soak_report(report)


def test_controlled_and_kis_observed_drills_have_separate_denominators(
    tmp_path: Path,
) -> None:
    paths = _stores(tmp_path)
    audit_path, soak_path, controller_path = paths
    controller = connect_controller(controller_path, audit_path, soak_path)
    prepare_drill(
        controller,
        campaign_id="campaign-1",
        drill_id="controlled-1",
        fault=FaultName.STALE_DATA,
        boundary=InjectionBoundary.DATA,
        expected_containment=("NO_ORDER_POST",),
        required_observations=("CONTAINMENT_CHECKED",),
        policy_version="fault-drill-v1",
    )
    commit_drill_contract(controller, drill_id="controlled-1")
    append_controller_observation(
        controller,
        drill_id="controlled-1",
        observation_type="CONTAINMENT_CHECKED",
        evidence_class=SoakEvidenceClass.CONTROLLED_INJECTION,
        facts={"passed": True},
    )
    finalize_drill(controller, drill_id="controlled-1", requested_verdict=DrillVerdict.PASSED)
    controller.close()
    soak = soak_store.connect_soak_store(soak_path)
    soak_store.append_drill_link(
        soak,
        link_id="link-controlled",
        campaign_id="campaign-1",
        drill_id="controlled-1",
        evidence_class=SoakEvidenceClass.CONTROLLED_INJECTION,
        verdict=DrillVerdict.PASSED,
    )
    soak_store.append_drill_link(
        soak,
        link_id="link-kis",
        campaign_id="campaign-1",
        drill_id="kis-observation-1",
        evidence_class=SoakEvidenceClass.KIS_OBSERVED,
        verdict=DrillVerdict.UNKNOWN,
    )
    soak.close()

    report = build_soak_report(_repository(paths), "campaign-1")
    coverage = {item.evidence_class: item for item in report.drills}

    assert coverage[SoakEvidenceClass.CONTROLLED_INJECTION].required == 1
    assert coverage[SoakEvidenceClass.CONTROLLED_INJECTION].passed == 1
    assert coverage[SoakEvidenceClass.KIS_OBSERVED].required == 1
    assert coverage[SoakEvidenceClass.KIS_OBSERVED].unknown == 1
    assert "combined" not in render_soak_report(report).lower()


def test_missing_cross_store_link_fails_closed_as_unknown(tmp_path: Path) -> None:
    paths = _stores(tmp_path)
    soak = soak_store.connect_soak_store(paths[1])
    soak_store.append_drill_link(
        soak,
        link_id="orphan",
        campaign_id="campaign-1",
        drill_id="missing-controller-contract",
        run_id="missing-primary-run",
        evidence_class=SoakEvidenceClass.CONTROLLED_INJECTION,
        verdict=DrillVerdict.PASSED,
    )
    soak.close()

    report = build_soak_report(_repository(paths), "campaign-1")
    controlled = next(
        item for item in report.drills
        if item.evidence_class is SoakEvidenceClass.CONTROLLED_INJECTION
    )
    assert controlled.passed == 0
    assert controlled.unknown == 1
    assert report.cross_store_unknown == 1


@pytest.mark.parametrize("alias", (0, 1, 2))
def test_repository_rejects_missing_alias_or_unsupported_stores(
    tmp_path: Path, alias: int
) -> None:
    paths = list(_stores(tmp_path))
    paths[(alias + 1) % 3] = paths[alias]
    with pytest.raises(ValueError, match="pairwise distinct"):
        ReadOnlySoakRepository(*paths)

    missing = tmp_path / "missing.db"
    with pytest.raises(FileNotFoundError):
        ReadOnlySoakRepository(paths[0], missing, paths[2])
