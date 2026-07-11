"""Stable, provider-neutral evidence contracts for the audit database."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping


class RunStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_ERRORS = "COMPLETED_WITH_ERRORS"
    FAILED = "FAILED"
    INTERRUPTED = "INTERRUPTED"


class RunKind(StrEnum):
    SCREEN = "SCREEN"
    RUN = "RUN"


class TickerOutcomeCode(StrEnum):
    SELECTED = "SELECTED"
    REJECTED = "REJECTED"
    SCREEN_ERROR = "SCREEN_ERROR"
    NO_TRADE = "NO_TRADE"
    ORDER_SUPPRESSED = "ORDER_SUPPRESSED"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ORDER_RECONCILED = "ORDER_RECONCILED"
    EXECUTION_ERROR = "EXECUTION_ERROR"


class ReasonCode(StrEnum):
    COMPLETED = "COMPLETED"
    HOLD_SIGNAL = "HOLD_SIGNAL"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    STALE_OHLCV = "STALE_OHLCV"
    STALE_QUOTE = "STALE_QUOTE"
    MALFORMED_SIGNAL = "MALFORMED_SIGNAL"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    KIS_UNAVAILABLE = "KIS_UNAVAILABLE"
    DUPLICATE_ORDER = "DUPLICATE_ORDER"
    AMBIGUOUS_SUBMISSION = "AMBIGUOUS_SUBMISSION"
    UNKNOWN_MARKET_STATE = "UNKNOWN_MARKET_STATE"


class FailedStage(StrEnum):
    SCREENING = "SCREENING"
    DATA_COLLECTION = "DATA_COLLECTION"
    LLM = "LLM"
    PARSING = "PARSING"
    RISK = "RISK"
    ORDER = "ORDER"
    RECONCILIATION = "RECONCILIATION"


class OrderEventType(StrEnum):
    INTENT_CREATED = "INTENT_CREATED"
    DUPLICATE_CHECKED = "DUPLICATE_CHECKED"
    SUBMISSION_ATTEMPTED = "SUBMISSION_ATTEMPTED"
    SUBMISSION_ACCEPTED = "SUBMISSION_ACCEPTED"
    SUBMISSION_AMBIGUOUS = "SUBMISSION_AMBIGUOUS"
    BROKER_OBSERVED = "BROKER_OBSERVED"
    RECONCILED = "RECONCILED"


_FORBIDDEN_DETAIL_KEYS = {
    "raw", "payload", "response", "request", "app_key", "app_secret",
    "secret", "token", "authorization", "credential", "credentials",
}


def sanitize_detail(detail: Mapping[str, Any] | None) -> dict[str, Any]:
    """Allow normalized scalar facts and reject provider payload/credential shapes."""

    if detail is None:
        return {}
    clean: dict[str, Any] = {}
    for key, value in detail.items():
        normalized_key = key.lower()
        if normalized_key in _FORBIDDEN_DETAIL_KEYS or any(
            marker in normalized_key
            for marker in ("secret", "token", "credential", "app_key", "payload")
        ):
            raise ValueError(f"forbidden evidence detail field: {key}")
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise TypeError(f"evidence detail must contain scalar facts: {key}")
        clean[key] = value
    return clean


@dataclass(frozen=True)
class TickerOutcome:
    run_id: str
    ticker: str
    outcome_code: TickerOutcomeCode
    reason_code: ReasonCode
    detail: Mapping[str, Any] | None = None
    failed_stage: FailedStage | None = None
    order_intent_id: str | None = None
    final_order_state: str | None = None
    created_at: str | None = None


@dataclass(frozen=True)
class OrderEvent:
    order_intent_id: str
    origin_run_id: str
    observer_run_id: str
    ticker: str
    event_type: OrderEventType
    submission_id: str | None = None
    broker_order_id: str | None = None
    side: str | None = None
    requested_qty: int | None = None
    filled_qty: int | None = None
    unfilled_qty: int | None = None
    broker_status: str | None = None
    duplicate_of_intent_id: str | None = None
    detail: Mapping[str, Any] | None = None
    observed_at: str | None = None
