"""Evidence-gated eligible-day accounting for the explicit KIS mock campaign."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Callable

from .market_cycle import CalendarState, MarketCyclePolicy
from .reporting import DailyReport, EvidenceState, ReconciliationState
from .soak_models import CampaignState, DayCreditState, DrillVerdict, SoakEvidenceClass
from .soak_store import (
    append_campaign_event,
    append_drill_link,
    consume_availability_failure,
    create_or_resume_campaign,
    designate_day,
    latch_safety_failure,
    load_campaign_state,
)


class AvailabilityCode(StrEnum):
    """Allowed pre-submission external availability failures (D-08)."""

    KIS_UNAVAILABLE = "KIS_UNAVAILABLE"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"
    DATA_UNAVAILABLE = "DATA_UNAVAILABLE"


class SafetyBreachCode(StrEnum):
    """Exhaustive irreversible campaign safety failures (D-09)."""

    REAL_TARGET_REACHABLE = "REAL_TARGET_REACHABLE"
    UNJUSTIFIED_SUBMISSION = "UNJUSTIFIED_SUBMISSION"
    BLIND_POST_RETRY = "BLIND_POST_RETRY"
    DUPLICATE_ORDER = "DUPLICATE_ORDER"
    AUDIT_EVIDENCE_LOST = "AUDIT_EVIDENCE_LOST"
    AUDIT_EVIDENCE_CONTRADICTORY = "AUDIT_EVIDENCE_CONTRADICTORY"
    AMBIGUITY_RELEASED_INCORRECTLY = "AMBIGUITY_RELEASED_INCORRECTLY"
    BROKER_TRUTH_DISAGREEMENT = "BROKER_TRUTH_DISAGREEMENT"


class DayVerdictCode(StrEnum):
    ADMITTED = "ADMITTED"
    CREDITED = "CREDITED"
    CAMPAIGN_NOT_ACTIVE = "CAMPAIGN_NOT_ACTIVE"
    CLOSED_DATE = "CLOSED_DATE"
    UNKNOWN_DATE = "UNKNOWN_DATE"
    NON_DESIGNATED_KIND = "NON_DESIGNATED_KIND"
    PREVIEW = "PREVIEW"
    DRY_RUN = "DRY_RUN"
    CONTROLLED_DRILL = "CONTROLLED_DRILL"
    EXTRA_RERUN = "EXTRA_RERUN"
    DATE_ALREADY_DESIGNATED = "DATE_ALREADY_DESIGNATED"
    RUN_ALREADY_DESIGNATED = "RUN_ALREADY_DESIGNATED"
    REPORT_MISSING_RUN = "REPORT_MISSING_RUN"
    REPORT_MULTIPLE_RUNS = "REPORT_MULTIPLE_RUNS"
    REPORT_DATE_MISMATCH = "REPORT_DATE_MISMATCH"
    NON_MOCK_TARGET = "NON_MOCK_TARGET"
    INCOMPLETE_REPORT = "INCOMPLETE_REPORT"
    INCOMPLETE_TICKER_EVIDENCE = "INCOMPLETE_TICKER_EVIDENCE"
    INCOMPLETE_ORDER_EVIDENCE = "INCOMPLETE_ORDER_EVIDENCE"
    REPORT_DENOMINATOR_MISMATCH = "REPORT_DENOMINATOR_MISMATCH"
    RECONCILIATION_INCOMPLETE = "RECONCILIATION_INCOMPLETE"


@dataclass(frozen=True)
class DayVerdict:
    code: DayVerdictCode
    trading_date: date
    credit_state: DayCreditState

    @property
    def credited(self) -> bool:
        return self.credit_state is DayCreditState.CREDITED


DailyReportBuilder = Callable[[date], DailyReport]


class SoakCampaignService:
    """Coordinate immutable campaign accounting without acquiring a POST capability."""

    def __init__(
        self,
        *,
        market_policy: MarketCyclePolicy,
        store: sqlite3.Connection | object,
        daily_report_builder: DailyReportBuilder,
        reconciler: object | None = None,
    ) -> None:
        self.market_policy = market_policy
        self.store = store if isinstance(store, sqlite3.Connection) else getattr(store, "conn")
        self.daily_report_builder = daily_report_builder
        self.reconciler = reconciler

    def start_campaign(self, **policy: Any) -> dict[str, Any]:
        return create_or_resume_campaign(self.store, **policy)

    def load_status(self, campaign_id: str) -> dict[str, Any]:
        return load_campaign_state(self.store, campaign_id=campaign_id)

    def admit_designated_run(
        self,
        *,
        campaign_id: str,
        run_id: str,
        observed_at: datetime,
        run_kind: str = "RUN",
        preview: bool = False,
        dry_run: bool = False,
        controlled_drill: bool = False,
        rerun: bool = False,
    ) -> DayVerdict:
        """Validate admission without consuming a day attempt or creating run evidence."""

        state = self.load_status(campaign_id)
        market = self.market_policy.classify(observed_at)
        trading_date = market.trading_date
        if state["state"] is not CampaignState.ACTIVE:
            return self._verdict(DayVerdictCode.CAMPAIGN_NOT_ACTIVE, trading_date)
        if market.calendar_state is CalendarState.UNKNOWN:
            return self._verdict(DayVerdictCode.UNKNOWN_DATE, trading_date)
        if market.calendar_state is not CalendarState.TRADING_DAY:
            return self._verdict(DayVerdictCode.CLOSED_DATE, trading_date)
        if controlled_drill:
            return self._verdict(DayVerdictCode.CONTROLLED_DRILL, trading_date)
        if preview:
            return self._verdict(DayVerdictCode.PREVIEW, trading_date)
        if dry_run:
            return self._verdict(DayVerdictCode.DRY_RUN, trading_date)
        if rerun:
            return self._verdict(DayVerdictCode.EXTRA_RERUN, trading_date)
        if run_kind != "RUN":
            return self._verdict(DayVerdictCode.NON_DESIGNATED_KIND, trading_date)
        existing_date = self.store.execute(
            "SELECT 1 FROM soak_days WHERE campaign_id=? AND trading_date=?",
            (campaign_id, trading_date.isoformat()),
        ).fetchone()
        if existing_date is not None:
            return self._verdict(DayVerdictCode.DATE_ALREADY_DESIGNATED, trading_date)
        existing_run = self.store.execute(
            "SELECT 1 FROM soak_days WHERE campaign_id=? AND run_id=?",
            (campaign_id, run_id),
        ).fetchone()
        if existing_run is not None:
            return self._verdict(DayVerdictCode.RUN_ALREADY_DESIGNATED, trading_date)
        return self._verdict(DayVerdictCode.ADMITTED, trading_date)

    def record_availability_failure(
        self,
        *,
        campaign_id: str,
        code: AvailabilityCode | str,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        reason = AvailabilityCode(code)
        return consume_availability_failure(
            self.store, campaign_id=campaign_id, reason_code=reason.value, run_id=run_id
        )

    def record_safety_breach(
        self,
        *,
        campaign_id: str,
        code: SafetyBreachCode | str,
        run_id: str | None = None,
        ticker: str | None = None,
        order_intent_id: str | None = None,
    ) -> dict[str, Any]:
        reason = SafetyBreachCode(code)
        return latch_safety_failure(
            self.store,
            campaign_id=campaign_id,
            reason_code=f"D09_{reason.value}",
            run_id=run_id,
            ticker=ticker,
            order_intent_id=order_intent_id,
        )

    def record_controlled_drill(
        self, *, campaign_id: str, drill_id: str, passed: bool
    ) -> int:
        """Record drill coverage without touching eligible-day or availability counters."""

        return append_drill_link(
            self.store,
            link_id=f"{campaign_id}:{drill_id}",
            campaign_id=campaign_id,
            drill_id=drill_id,
            evidence_class=SoakEvidenceClass.CONTROLLED_INJECTION,
            verdict=DrillVerdict.PASSED if passed else DrillVerdict.FAILED,
            detail={"accounting_effect": "NONE"},
        )

    def derive_day_verdict(
        self,
        *,
        campaign_id: str,
        run_id: str,
        observed_at: datetime,
        report: DailyReport | None = None,
        pre_finalize_complete: bool,
        run_kind: str = "RUN",
        preview: bool = False,
        dry_run: bool = False,
        controlled_drill: bool = False,
        rerun: bool = False,
    ) -> DayVerdict:
        admission = self.admit_designated_run(
            campaign_id=campaign_id,
            run_id=run_id,
            observed_at=observed_at,
            run_kind=run_kind,
            preview=preview,
            dry_run=dry_run,
            controlled_drill=controlled_drill,
            rerun=rerun,
        )
        if admission.code is not DayVerdictCode.ADMITTED:
            return admission
        if not pre_finalize_complete:
            return self._verdict(
                DayVerdictCode.RECONCILIATION_INCOMPLETE, admission.trading_date
            )
        actual_report = report or self.daily_report_builder(admission.trading_date)
        if actual_report.trading_date_kst != admission.trading_date:
            return self._verdict(DayVerdictCode.REPORT_DATE_MISMATCH, admission.trading_date)
        if not self._denominators_reconcile(actual_report):
            return self._verdict(
                DayVerdictCode.REPORT_DENOMINATOR_MISMATCH, admission.trading_date
            )
        matching = tuple(run for run in actual_report.runs if run.run_id == run_id)
        if not matching:
            return self._verdict(DayVerdictCode.REPORT_MISSING_RUN, admission.trading_date)
        if len(matching) != 1:
            return self._verdict(DayVerdictCode.REPORT_MULTIPLE_RUNS, admission.trading_date)
        run = matching[0]
        if run.run_kind != "RUN":
            return self._verdict(DayVerdictCode.NON_DESIGNATED_KIND, admission.trading_date)
        if run.target != "mock":
            return self._verdict(DayVerdictCode.NON_MOCK_TARGET, admission.trading_date)
        if run.run_state is not EvidenceState.COMPLETE:
            return self._verdict(DayVerdictCode.INCOMPLETE_REPORT, admission.trading_date)
        if any(item.ticker_state is not EvidenceState.COMPLETE for item in run.candidates):
            return self._verdict(
                DayVerdictCode.INCOMPLETE_TICKER_EVIDENCE, admission.trading_date
            )
        if any(
            item.reconciliation_state
            in {ReconciliationState.PENDING, ReconciliationState.UNKNOWN}
            for item in run.candidates
        ):
            return self._verdict(
                DayVerdictCode.INCOMPLETE_ORDER_EVIDENCE, admission.trading_date
            )
        return DayVerdict(
            DayVerdictCode.CREDITED,
            admission.trading_date,
            DayCreditState.CREDITED,
        )

    def finalize_designated_day(self, **evidence: Any) -> DayVerdict:
        verdict = self.derive_day_verdict(**evidence)
        campaign_id = str(evidence["campaign_id"])
        run_id = str(evidence["run_id"])
        if verdict.credited:
            designate_day(
                self.store,
                campaign_id=campaign_id,
                trading_date=verdict.trading_date.isoformat(),
                run_id=run_id,
                run_kind="RUN",
                terminal=True,
                credit_state=DayCreditState.CREDITED,
                detail={"verdict_code": verdict.code.value},
            )
            status = self.load_status(campaign_id)
            if status["credited_days"] >= status["target_eligible_days"]:
                self.store.execute(
                    "UPDATE soak_campaigns SET state='COMPLETED' WHERE campaign_id=? AND state='ACTIVE'",
                    (campaign_id,),
                )
                self.store.commit()
        else:
            append_campaign_event(
                self.store,
                campaign_id=campaign_id,
                run_id=run_id,
                event_code="DAY_NOT_CREDITED",
                detail={"verdict_code": verdict.code.value},
            )
        return verdict

    @staticmethod
    def _denominators_reconcile(report: DailyReport) -> bool:
        counts = (report.complete, report.incomplete, report.unknown)
        return (
            all(item.total_denominator == report.total_candidates for item in counts)
            and sum(item.numerator for item in counts) == report.total_candidates
            and report.complete.determinate_denominator
            == report.incomplete.determinate_denominator
            == report.unknown.determinate_denominator
            == report.complete.numerator + report.incomplete.numerator
        )

    @staticmethod
    def _verdict(code: DayVerdictCode, trading_date: date) -> DayVerdict:
        return DayVerdict(code, trading_date, DayCreditState.NOT_CREDITED)


__all__ = [
    "AvailabilityCode",
    "DayVerdict",
    "DayVerdictCode",
    "SafetyBreachCode",
    "SoakCampaignService",
]
