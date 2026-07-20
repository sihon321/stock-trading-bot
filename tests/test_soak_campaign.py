"""Eligible-day accounting and irreversible KIS mock soak safety behavior."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from trading_bot.market_cycle import MarketCyclePolicy
from trading_bot.reporting import (
    CandidateReportRow,
    DailyReport,
    DenominatorCount,
    EvidenceState,
    NotificationState,
    ReconciliationState,
    RunReportSection,
)
from trading_bot.soak_campaign import (
    AvailabilityCode,
    DayVerdictCode,
    SafetyBreachCode,
    SoakCampaignService,
)
from trading_bot.soak_models import CampaignState, DayCreditState
from trading_bot.soak_store import connect_soak_store, freeze_ticker


KST = ZoneInfo("Asia/Seoul")
OBSERVED = datetime(2026, 7, 20, 10, 0, tzinfo=KST)


class Calendar:
    def __init__(self, trading_day: bool | None = True) -> None:
        self.trading_day = trading_day

    def is_trading_day(self, day: date) -> bool | None:
        return self.trading_day

    def previous_trading_day(self, day: date) -> date | None:
        return day


def _run(
    *,
    run_id: str = "run-1",
    candidates: tuple[CandidateReportRow, ...] = (),
    run_state: EvidenceState = EvidenceState.COMPLETE,
    run_kind: str = "RUN",
    target: str = "mock",
) -> RunReportSection:
    return RunReportSection(
        run_id=run_id,
        run_kind=run_kind,
        started_at=OBSERVED,
        trading_date_kst=OBSERVED.date(),
        target=target,
        run_status=None,
        run_state=run_state,
        run_notification_attempts=(),
        final_summary_notification_state=NotificationState.DISABLED,
        candidates=candidates,
        preview_run_id=None,
        preview_only_tickers=(),
        run_only_tickers=(),
    )


def _candidate(
    *, reconciliation: ReconciliationState = ReconciliationState.NOT_APPLICABLE
) -> CandidateReportRow:
    return CandidateReportRow(
        run_id="run-1",
        run_kind="RUN",
        started_at=OBSERVED,
        trading_date_kst=OBSERVED.date(),
        target="mock",
        processing_id=1,
        ticker="005930",
        decision="HOLD",
        confidence=0.99,
        reason_code="HOLD_SIGNAL",
        reason_ko="hold",
        ticker_state=EvidenceState.COMPLETE,
        order_state="NOT_APPLICABLE",
        reconciliation_state=reconciliation,
        notification_attempts=(),
    )


def _report(run: RunReportSection) -> DailyReport:
    total = len(run.candidates)
    complete = sum(c.ticker_state is EvidenceState.COMPLETE for c in run.candidates)
    incomplete = sum(c.ticker_state is EvidenceState.INCOMPLETE for c in run.candidates)
    unknown = sum(c.ticker_state is EvidenceState.UNKNOWN for c in run.candidates)
    determinate = complete + incomplete
    return DailyReport(
        OBSERVED.date(),
        (run,),
        total,
        DenominatorCount(complete, total, determinate),
        DenominatorCount(incomplete, total, determinate),
        DenominatorCount(unknown, total, determinate),
    )


def _service(tmp_path: Path, *, trading_day: bool | None = True) -> SoakCampaignService:
    conn = connect_soak_store(tmp_path / "soak.db")
    service = SoakCampaignService(
        market_policy=MarketCyclePolicy(Calendar(trading_day)),
        store=conn,
        daily_report_builder=lambda _day: _report(_run()),
    )
    service.start_campaign(
        campaign_id="campaign",
        accepted_profile_fingerprint="sha256:accepted",
        accepted_profile_version="official-example-v1",
        field_contract_version="kis-mock-fields-v1",
        ambiguity_policy_version="bounded-v1",
        ambiguity_window_seconds=60,
        ambiguity_poll_cadence_seconds=5,
        ambiguity_max_observations=12,
        target_eligible_days=2,
        availability_failure_budget=2,
    )
    return service


@pytest.mark.parametrize(
    ("run", "kwargs", "expected"),
    [
        (_run(), {}, DayVerdictCode.CREDITED),
        (_run(candidates=(_candidate(),)), {}, DayVerdictCode.CREDITED),
        (_run(run_kind="SCREEN"), {}, DayVerdictCode.NON_DESIGNATED_KIND),
        (_run(), {"dry_run": True}, DayVerdictCode.DRY_RUN),
        (_run(), {"controlled_drill": True}, DayVerdictCode.CONTROLLED_DRILL),
        (_run(), {"rerun": True}, DayVerdictCode.EXTRA_RERUN),
        (_run(run_state=EvidenceState.INCOMPLETE), {}, DayVerdictCode.INCOMPLETE_REPORT),
        (
            _run(candidates=(_candidate(reconciliation=ReconciliationState.UNKNOWN),)),
            {},
            DayVerdictCode.INCOMPLETE_ORDER_EVIDENCE,
        ),
    ],
)
def test_day_credit_matrix_is_fail_closed_and_persisted_only_when_eligible(
    tmp_path: Path,
    run: RunReportSection,
    kwargs: dict[str, bool],
    expected: DayVerdictCode,
) -> None:
    service = _service(tmp_path)
    report = _report(run)
    verdict = service.finalize_designated_day(
        campaign_id="campaign",
        run_id="run-1",
        observed_at=OBSERVED,
        report=report,
        pre_finalize_complete=True,
        **kwargs,
    )

    assert verdict.code is expected
    rows = service.store.execute("SELECT credit_state FROM soak_days").fetchall()
    assert rows == ([(DayCreditState.CREDITED.value,)] if expected is DayVerdictCode.CREDITED else [])


@pytest.mark.parametrize(
    ("trading_day", "expected"),
    [
        (False, DayVerdictCode.CLOSED_DATE),
        (None, DayVerdictCode.UNKNOWN_DATE),
    ],
)
def test_closed_or_unknown_date_never_consumes_an_attempt(
    tmp_path: Path, trading_day: bool | None, expected: DayVerdictCode
) -> None:
    service = _service(tmp_path, trading_day=trading_day)
    verdict = service.finalize_designated_day(
        campaign_id="campaign",
        run_id="run-1",
        observed_at=OBSERVED,
        report=_report(_run()),
        pre_finalize_complete=True,
    )
    assert verdict.code is expected
    assert service.store.execute("SELECT COUNT(*) FROM soak_days").fetchone()[0] == 0


def test_pre_finalize_uncertainty_and_denominator_mismatch_never_credit(tmp_path: Path) -> None:
    service = _service(tmp_path)
    report = _report(_run(candidates=(_candidate(),)))
    bad = replace(report, total_candidates=2)
    assert service.derive_day_verdict(
        campaign_id="campaign", run_id="run-1", observed_at=OBSERVED,
        report=bad, pre_finalize_complete=True,
    ).code is DayVerdictCode.REPORT_DENOMINATOR_MISMATCH
    assert service.derive_day_verdict(
        campaign_id="campaign", run_id="run-1", observed_at=OBSERVED,
        report=report, pre_finalize_complete=False,
    ).code is DayVerdictCode.RECONCILIATION_INCOMPLETE


def test_availability_budget_is_separate_from_safety_and_drills(tmp_path: Path) -> None:
    service = _service(tmp_path)
    for code in (AvailabilityCode.KIS_UNAVAILABLE, AvailabilityCode.LLM_UNAVAILABLE):
        status = service.record_availability_failure(
            campaign_id="campaign", code=code, run_id="run-1"
        )
        assert status["safety_failure_code"] is None
    assert status["state"] is CampaignState.ACTIVE

    service.record_controlled_drill(
        campaign_id="campaign", drill_id="drill-1", passed=True
    )
    unchanged = service.load_status("campaign")
    assert unchanged["availability_failures_used"] == 2
    assert unchanged["credited_days"] == 0

    failed = service.record_availability_failure(
        campaign_id="campaign", code=AvailabilityCode.DATA_UNAVAILABLE
    )
    assert failed["state"] is CampaignState.FAILED
    assert failed["safety_failure_code"] is None
    with pytest.raises(ValueError, match="not active"):
        service.record_availability_failure(
            campaign_id="campaign", code=AvailabilityCode.KIS_UNAVAILABLE
        )


@pytest.mark.parametrize("code", list(SafetyBreachCode))
def test_every_safety_breach_is_an_irreversible_distinct_d09_latch(
    tmp_path: Path, code: SafetyBreachCode
) -> None:
    service = _service(tmp_path)
    failed = service.record_safety_breach(campaign_id="campaign", code=code)
    assert failed["state"] is CampaignState.FAILED
    assert failed["safety_failure_code"] == f"D09_{code.value}"
    with pytest.raises(ValueError, match="not active"):
        service.record_safety_breach(campaign_id="campaign", code=code)


def test_credit_does_not_release_an_existing_ambiguity_freeze(tmp_path: Path) -> None:
    service = _service(tmp_path)
    freeze_ticker(
        service.store,
        freeze_id="proof-freeze",
        campaign_id="campaign",
        ticker="000660",
        freeze_kind="AMBIGUITY",
        order_intent_id="proof-intent",
    )
    verdict = service.finalize_designated_day(
        campaign_id="campaign", run_id="run-1", observed_at=OBSERVED,
        report=_report(_run()), pre_finalize_complete=True,
    )
    assert verdict.code is DayVerdictCode.CREDITED
    assert [row["ticker"] for row in service.load_status("campaign")["active_freezes"]] == ["000660"]


def test_only_one_designated_run_can_credit_a_trading_date(tmp_path: Path) -> None:
    service = _service(tmp_path)
    first = service.finalize_designated_day(
        campaign_id="campaign", run_id="run-1", observed_at=OBSERVED,
        report=_report(_run()), pre_finalize_complete=True,
    )
    second_run = _run(run_id="run-2")
    second = service.finalize_designated_day(
        campaign_id="campaign", run_id="run-2", observed_at=OBSERVED,
        report=_report(second_run), pre_finalize_complete=True,
    )
    assert first.code is DayVerdictCode.CREDITED
    assert second.code is DayVerdictCode.DATE_ALREADY_DESIGNATED
    assert service.load_status("campaign")["credited_days"] == 1
