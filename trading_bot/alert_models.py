"""Immutable operational alert contracts with no trading capabilities."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
import hashlib
import json
import re


def bounded_identity(value: str, *, limit: int = 128) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:/-]*", value) or len(value) > limit:
        raise ValueError("invalid bounded identity")
    return value


def timestamp(value: datetime) -> float:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("aware timestamp required")
    return value.timestamp()


class Severity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"

    @property
    def rank(self) -> int:
        return (Severity.INFO, Severity.WARNING, Severity.CRITICAL).index(self)


class DeliveryState(StrEnum):
    QUEUED = "QUEUED"
    CLAIMED = "CLAIMED"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    DISABLED = "DISABLED"
    SUPPRESSED = "SUPPRESSED"


@dataclass(frozen=True)
class AlertSubject:
    resource_id: str
    account_hash: str
    target: str
    ticker_or_account: str
    problem_family: str
    broker_subject: str = "NONE"

    def __post_init__(self):
        if not isinstance(self.account_hash, str) or not re.fullmatch(r"[a-f0-9]{64}", self.account_hash):
            raise ValueError("account hash required")
        if self.target not in {"mock", "real", "simulated", "unknown"}:
            raise ValueError("invalid target")
        for name in ("resource_id", "ticker_or_account", "problem_family", "broker_subject"):
            bounded_identity(getattr(self, name))

    @property
    def identity(self) -> str:
        return hashlib.sha256(json.dumps(self.parts, separators=(",", ":")).encode()).hexdigest()

    @property
    def parts(self) -> tuple[str, ...]:
        return (self.resource_id, self.account_hash, self.target, self.ticker_or_account,
                self.problem_family, self.broker_subject)


@dataclass(frozen=True)
class AlertSourceFact:
    subject: AlertSubject
    source_owner: str
    source_id: str
    sequence: int
    observed_at: datetime
    normalized_state: str
    severity: Severity
    positive_recovery: bool = False
    recovery_proof_id: str | None = None
    delivery_owner: str = "observer"
    producer_event_id: str | None = None
    producer_attempt_id: str | None = None
    producer_delivery_state: DeliveryState | None = None

    def __post_init__(self):
        if not isinstance(self.subject, AlertSubject):
            raise ValueError("typed subject required")
        bounded_identity(self.source_owner)
        bounded_identity(self.source_id, limit=256)
        if type(self.sequence) is not int or self.sequence < 0:
            raise ValueError("nonnegative durable sequence required")
        timestamp(self.observed_at)
        bounded_identity(self.normalized_state)
        object.__setattr__(self, "severity", Severity(self.severity))
        if type(self.positive_recovery) is not bool:
            raise ValueError("positive recovery must be boolean")
        if self.positive_recovery and not self.recovery_proof_id:
            raise ValueError("positive recovery requires same-subject saved proof")
        if self.delivery_owner not in {"observer", "producer"}:
            raise ValueError("invalid delivery owner")
        for value in (self.recovery_proof_id, self.producer_event_id, self.producer_attempt_id):
            if value is not None:
                bounded_identity(value, limit=256)
        if self.producer_delivery_state is not None:
            state = DeliveryState(self.producer_delivery_state)
            if state not in {DeliveryState.DELIVERED, DeliveryState.FAILED, DeliveryState.UNKNOWN, DeliveryState.DISABLED}:
                raise ValueError("terminal producer delivery state required")
            object.__setattr__(self, "producer_delivery_state", state)


@dataclass(frozen=True)
class IncidentEpisode:
    episode_id: str
    subject: AlertSubject
    revision: int
    severity: Severity
    normalized_state: str
    active: bool
    first_observed_at: datetime
    last_observed_at: datetime
    occurrence_count: int
    duration_seconds: float
    recovered_at: datetime | None
    recovery_proof_id: str | None
    acknowledged: bool
    next_reminder_at: datetime | None


@dataclass(frozen=True)
class SeverityRevision:
    episode_id: str
    revision: int
    severity: Severity
    observed_at: datetime
    source_owner: str
    source_id: str


@dataclass(frozen=True)
class Acknowledgement:
    acknowledgement_id: int
    episode_id: str
    revision: int
    actor: str
    at: datetime
    note: str | None


@dataclass(frozen=True)
class DeliveryAttempt:
    event_key: str
    episode_id: str
    revision: int
    kind: str
    delivery_owner: str
    state: DeliveryState
    due_at: datetime
    claim_id: str | None = None
    owner: str | None = None
    claimed_at: datetime | None = None
    finalized_at: datetime | None = None
    failure_code: str | None = None
    producer_event_id: str | None = None
    producer_attempt_id: str | None = None


@dataclass(frozen=True)
class AlertAction:
    actor: str
    action: str
    episode_id: str
    revision: int
    result_code: str
    at: datetime
