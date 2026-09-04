"""Stable, provider-neutral evidence contracts for the audit database."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import re
from types import MappingProxyType
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
    SCREEN_REJECTED = "SCREEN_REJECTED"
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
    FRESHNESS_BLOCKED = "FRESHNESS_BLOCKED"
    FRESHNESS_CHECKED = "FRESHNESS_CHECKED"


class DailyEvaluationStatus(StrEnum):
    STARTED = "STARTED"
    FINALIZED = "FINALIZED"


class DailyEvaluationEventType(StrEnum):
    INPUT_COMMITTED = "INPUT_COMMITTED"
    PROVIDER_ATTEMPT = "PROVIDER_ATTEMPT"
    SIGNAL_FINALIZED = "SIGNAL_FINALIZED"
    LLM_UNAVAILABLE = "LLM_UNAVAILABLE"


class MutationLeaseState(StrEnum):
    ACQUIRING = "ACQUIRING"
    RECOVERY = "RECOVERY"
    ACTIVE = "ACTIVE"
    LOST = "LOST"
    RECOVERY_BLOCKED = "RECOVERY_BLOCKED"
    RELEASED = "RELEASED"


class MutationLeaseEventType(StrEnum):
    ACQUIRING = "ACQUIRING"
    RECOVERY = "RECOVERY"
    ACTIVE = "ACTIVE"
    HEARTBEAT = "HEARTBEAT"
    LOST = "LOST"
    RECOVERY_BLOCKED = "RECOVERY_BLOCKED"
    RELEASED = "RELEASED"


@dataclass(frozen=True)
class DailyEvaluationEvent:
    evaluation_id: str
    event_type: DailyEvaluationEventType
    action: str | None
    confidence: float | None
    reason_code: str | None
    detail: Mapping[str, str | int | float | bool | None]
    observed_at: datetime

    def __post_init__(self) -> None:
        if not self.evaluation_id:
            raise ValueError("evaluation_id is required")
        object.__setattr__(self, "event_type", DailyEvaluationEventType(self.event_type))
        if self.action is not None and self.action not in {"BUY", "SELL", "HOLD"}:
            raise ValueError("action must be BUY, SELL, or HOLD")
        if self.confidence is not None and not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between zero and one")
        if self.reason_code is not None and re.fullmatch(
            r"[A-Z][A-Z0-9_]{0,63}", self.reason_code
        ) is None:
            raise ValueError("reason_code must be a bounded stable code")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        object.__setattr__(self, "detail", MappingProxyType(sanitize_detail(self.detail)))


class NotificationKind(StrEnum):
    IMMEDIATE_ERROR = "IMMEDIATE_ERROR"
    FINAL_SUMMARY = "FINAL_SUMMARY"


class NotificationDeliveryStatus(StrEnum):
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    DISABLED = "DISABLED"


_FORBIDDEN_DETAIL_KEYS = {
    "raw", "payload", "response", "request", "app_key", "app_secret",
    "secret", "token", "authorization", "credential", "credentials",
    "webhook", "webhook_url", "body", "message", "exception",
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
            for marker in (
                "secret", "token", "credential", "app_key", "payload", "webhook",
            )
        ):
            raise ValueError(f"forbidden evidence detail field: {key}")
        if value is not None and not isinstance(value, (str, int, float, bool)):
            raise TypeError(f"evidence detail must contain scalar facts: {key}")
        clean[key] = value
    return clean


@dataclass(frozen=True)
class NotificationAttempt:
    run_id: str
    ticker: str | None
    kind: NotificationKind
    status: NotificationDeliveryStatus
    failure_category: str | None
    detail: Mapping[str, str | int | float | bool | None]
    observed_at: datetime

    def __post_init__(self) -> None:
        if not self.run_id:
            raise ValueError("run_id is required")
        if self.ticker == "":
            raise ValueError("ticker cannot be empty")
        object.__setattr__(self, "kind", NotificationKind(self.kind))
        object.__setattr__(self, "status", NotificationDeliveryStatus(self.status))
        if self.failure_category is not None and re.fullmatch(
            r"[A-Z][A-Z0-9_]{0,63}", self.failure_category
        ) is None:
            raise ValueError("failure_category must be a bounded stable code")
        if self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        clean = sanitize_detail(self.detail)
        for key, value in clean.items():
            if len(key) > 64:
                raise ValueError("notification detail key is too long")
            if isinstance(value, str) and len(value) > 512:
                raise ValueError("notification detail value is too long")
        object.__setattr__(self, "detail", MappingProxyType(clean))


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


@dataclass(frozen=True)
class FreshnessEvidence:
    """Normalized quote-freshness facts persisted before broker mutation."""

    observed_at: str | None
    checked_at: str
    age_seconds: float | None
    verdict: str
    reason: str
    policy_version: str = "quote-freshness-v1"

    def detail(self) -> dict[str, Any]:
        return sanitize_detail({
            "observed_at": self.observed_at,
            "checked_at": self.checked_at,
            "age_seconds": self.age_seconds,
            "verdict": self.verdict,
            "reason": self.reason,
            "policy_version": self.policy_version,
        })
