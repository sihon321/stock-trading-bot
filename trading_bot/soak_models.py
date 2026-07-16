"""Immutable, provider-neutral contracts for KIS mock soak evidence."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Mapping


class SoakEvidenceClass(StrEnum):
    SYNTHETIC = "SYNTHETIC"
    CONTROLLED_INJECTION = "CONTROLLED_INJECTION"
    KIS_OBSERVED = "KIS_OBSERVED"


class CompatibilityState(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


class PageCompleteness(StrEnum):
    COMPLETE = "COMPLETE"
    INCOMPLETE = "INCOMPLETE"
    UNKNOWN = "UNKNOWN"


class CampaignState(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class CampaignKind(StrEnum):
    SOAK = "SOAK"
    PROOF_ORDER = "PROOF_ORDER"


class DayCreditState(StrEnum):
    ELIGIBLE = "ELIGIBLE"
    CREDITED = "CREDITED"
    NOT_CREDITED = "NOT_CREDITED"


class ReconciliationStage(StrEnum):
    STARTUP = "STARTUP"
    RESUME = "RESUME"
    PRE_RUN = "PRE_RUN"
    POST_SUBMISSION = "POST_SUBMISSION"
    PRE_FINALIZE = "PRE_FINALIZE"
    PRE_FINALIZATION = "PRE_FINALIZATION"


class ReconciliationVerdict(StrEnum):
    MATCHED = "MATCHED"
    MISMATCHED = "MISMATCHED"
    UNKNOWN = "UNKNOWN"


class AmbiguityVerdict(StrEnum):
    NO_MATCH_CONFIRMED = "NO_MATCH_CONFIRMED"
    ONE_MATCH_DETERMINATE = "ONE_MATCH_DETERMINATE"
    MULTIPLE_OR_INCONCLUSIVE = "MULTIPLE_OR_INCONCLUSIVE"


class FreezeState(StrEnum):
    FROZEN = "FROZEN"
    RELEASED = "RELEASED"


class FaultName(StrEnum):
    STALE_DATA = "STALE_DATA"
    MALFORMED_LLM = "MALFORMED_LLM"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    KIS_API_FAILURE = "KIS_API_FAILURE"
    ACCEPTED_THEN_TIMEOUT = "ACCEPTED_THEN_TIMEOUT"
    THROTTLING = "THROTTLING"
    PARTIAL_OR_NO_FILL = "PARTIAL_OR_NO_FILL"
    INTERRUPTION = "INTERRUPTION"
    NOTIFICATION_FAILURE = "NOTIFICATION_FAILURE"
    AUDIT_FAILURE = "AUDIT_FAILURE"


class InjectionBoundary(StrEnum):
    DATA = "DATA"
    LLM = "LLM"
    KIS_QUERY = "KIS_QUERY"
    KIS_POST_ACK = "KIS_POST_ACK"
    PROCESS = "PROCESS"
    NOTIFICATION = "NOTIFICATION"
    AUDIT = "AUDIT"


class DrillVerdict(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class MockTrProfile:
    version: str
    buy_tr_id: str
    sell_tr_id: str
    daily_ccld_tr_id: str
    balance_tr_id: str

    @property
    def tr_ids(self) -> tuple[str, str, str, str]:
        return (
            self.buy_tr_id,
            self.sell_tr_id,
            self.daily_ccld_tr_id,
            self.balance_tr_id,
        )


@dataclass(frozen=True)
class MockIdentityReceipt:
    target: str
    domain_class: str
    account_suffix: str
    profile_version: str
    buy_tr_id: str
    sell_tr_id: str
    daily_ccld_tr_id: str
    balance_tr_id: str
    campaign_id: str
    policy_version: str


@dataclass(frozen=True)
class BrokerPageEnvelope:
    rows: tuple[Mapping[str, str | int | float | bool | None], ...] = ()
    summary: Mapping[str, str | int | float | bool | None] = field(default_factory=dict)
    page_count: int = 0
    completeness: PageCompleteness = PageCompleteness.UNKNOWN
    reason_code: str = "NOT_QUERIED"

    def __post_init__(self) -> None:
        object.__setattr__(self, "completeness", PageCompleteness(self.completeness))
        object.__setattr__(self, "rows", tuple(MappingProxyType(dict(row)) for row in self.rows))
        object.__setattr__(self, "summary", MappingProxyType(dict(self.summary)))
