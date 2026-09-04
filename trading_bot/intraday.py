"""Foreground-only, LLM-free intraday position risk monitoring."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, time
from enum import StrEnum
from typing import Callable
from zoneinfo import ZoneInfo

from trading_bot.domain import Money, Position, Ticker
from trading_bot.exit_manager import (
    ExitDisposition,
    ExitResult,
    evaluate_exit_candidate,
    evaluate_risk_exit_trigger,
)
from trading_bot.portfolio import PortfolioSnapshot
from trading_bot.risk import RiskConfig, evaluate_position_risk


KST = ZoneInfo("Asia/Seoul")


class IntradaySessionPhase(StrEnum):
    PREFLIGHT_READ_ONLY = "PREFLIGHT_READ_ONLY"
    RECOVERY_ONLY = "RECOVERY_ONLY"
    ACTIVE = "ACTIVE"
    RECONCILE_ONLY = "RECONCILE_ONLY"
    STOPPING = "STOPPING"
    TERMINAL = "TERMINAL"


class IntradayIterationOutcome(StrEnum):
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"
    INTERRUPTED = "INTERRUPTED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class IntradayIterationResult:
    iteration_id: str
    phase: IntradaySessionPhase
    outcome: IntradayIterationOutcome
    snapshot_id: str | None
    exit_results: tuple[ExitResult, ...]
    reason_code: str


@dataclass(frozen=True)
class IntradayWatchResult:
    iterations: tuple[IntradayIterationResult, ...]
    final_phase: IntradaySessionPhase
    interrupted: bool


def session_phase_at(observed_at: datetime) -> IntradaySessionPhase:
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise ValueError("intraday clock must be timezone-aware")
    current = observed_at.astimezone(KST).time()
    if current < time(9, 0):
        return IntradaySessionPhase.PREFLIGHT_READ_ONLY
    if current < time(15, 20):
        return IntradaySessionPhase.ACTIVE
    if current < time(15, 30):
        return IntradaySessionPhase.RECONCILE_ONLY
    return IntradaySessionPhase.TERMINAL


def run_intraday_check(
    *,
    clock: Callable[[], datetime],
    snapshot_reader: Callable[[], PortfolioSnapshot],
    quote_reader: Callable[[str], Money],
    risk_config: RiskConfig,
    lease: object,
    exit_submitter: Callable[[ExitResult, Money], object],
    audit_sink: Callable[[IntradayIterationResult], object],
) -> IntradayIterationResult:
    """Run one fresh, independently identified, LLM-free held-position pass."""

    iteration_id = uuid.uuid4().hex
    phase = session_phase_at(clock())
    if getattr(lease, "recovery_required", False):
        phase = IntradaySessionPhase.RECOVERY_ONLY
    if phase is not IntradaySessionPhase.ACTIVE:
        outcome = (
            IntradayIterationOutcome.BLOCKED
            if phase is IntradaySessionPhase.RECOVERY_ONLY
            else IntradayIterationOutcome.COMPLETED
        )
        result = IntradayIterationResult(
            iteration_id, phase, outcome, None, (), phase.value
        )
        audit_sink(result)
        return result

    try:
        snapshot = snapshot_reader()
        if not snapshot.mutation_capable:
            result = IntradayIterationResult(
                iteration_id,
                phase,
                IntradayIterationOutcome.BLOCKED,
                snapshot.snapshot_id,
                (),
                "ACCOUNT_DATA_INCOMPLETE",
            )
            audit_sink(result)
            return result
        getattr(lease, "assert_active_owner")()
        exits: list[ExitResult] = []
        for holding in snapshot.holdings:
            quote = quote_reader(holding.ticker)
            position = Position(
                Ticker(holding.ticker), holding.total_quantity,
                Money(holding.average_price, quote.currency),
            )
            risk = evaluate_position_risk(position, quote, risk_config)
            trigger = evaluate_risk_exit_trigger(
                ticker=holding.ticker, cycle_id=iteration_id, decision=risk
            )
            candidate = evaluate_exit_candidate(trigger, snapshot)
            exits.append(candidate)
            if candidate.disposition is ExitDisposition.SUBMIT:
                getattr(lease, "assert_active_owner")()
                exit_submitter(candidate, quote)
        result = IntradayIterationResult(
            iteration_id,
            phase,
            IntradayIterationOutcome.COMPLETED,
            snapshot.snapshot_id,
            tuple(exits),
            "COMPLETED",
        )
    except Exception:
        result = IntradayIterationResult(
            iteration_id,
            IntradaySessionPhase.STOPPING,
            IntradayIterationOutcome.FAILED,
            None,
            (),
            "ITERATION_FAILED",
        )
    audit_sink(result)
    return result


def _release(lease: object, reconcile: Callable[[], object]) -> None:
    method = getattr(lease, "release_after_reconciliation", None)
    if method is not None:
        method(reconcile_submitted=reconcile, terminalize_cycle=lambda: None)
        return
    reconcile()
    release = getattr(lease, "release", None)
    if release is not None:
        release()


def run_intraday_watch(
    *,
    clock: Callable[[], datetime],
    sleeper: Callable[[float], object],
    stop_requested: Callable[[], bool],
    snapshot_reader: Callable[[], PortfolioSnapshot],
    quote_reader: Callable[[str], Money],
    risk_config: RiskConfig,
    lease: object,
    exit_submitter: Callable[[ExitResult, Money], object],
    audit_sink: Callable[[IntradayIterationResult], object],
    reconcile: Callable[[], object] = lambda: True,
    interval_seconds: float = 60,
    max_iterations: int | None = None,
) -> IntradayWatchResult:
    """Run foreground iterations until stop, cutoff, or terminal close."""

    if interval_seconds < 60:
        raise ValueError("intraday interval must be at least 60 seconds")
    iterations: list[IntradayIterationResult] = []
    interrupted = False
    final_phase = IntradaySessionPhase.PREFLIGHT_READ_ONLY
    while max_iterations is None or len(iterations) < max_iterations:
        if stop_requested():
            interrupted = True
            final_phase = IntradaySessionPhase.STOPPING
            _release(lease, reconcile)
            break
        now = clock()
        final_phase = session_phase_at(now)
        if final_phase is IntradaySessionPhase.TERMINAL:
            _release(lease, reconcile)
            break
        if final_phase is IntradaySessionPhase.RECONCILE_ONLY:
            reconcile()
            sleeper(interval_seconds)
            continue
        result = run_intraday_check(
            clock=lambda value=now: value,
            snapshot_reader=snapshot_reader,
            quote_reader=quote_reader,
            risk_config=risk_config,
            lease=lease,
            exit_submitter=exit_submitter,
            audit_sink=audit_sink,
        )
        iterations.append(result)
        sleeper(interval_seconds)
    return IntradayWatchResult(tuple(iterations), final_phase, interrupted)
