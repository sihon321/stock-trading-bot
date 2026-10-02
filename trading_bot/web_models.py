"""Immutable credential-free operator evidence contracts."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from types import MappingProxyType
from typing import Protocol
from zoneinfo import ZoneInfo

KST = ZoneInfo('Asia/Seoul')


@dataclass(frozen=True)
class ResourceScope:
    account_hash: str
    target: str
    resource_id: str | None = None

    def __post_init__(self):
        if not self.account_hash or self.target not in {'mock', 'real', 'dry_run', 'simulated', 'shadow'}:
            raise ValueError('positive scope required')


@dataclass(frozen=True)
class PeriodSelection:
    start: datetime
    end: datetime

    def __post_init__(self):
        if (self.start.tzinfo is None or self.end.tzinfo is None or self.end <= self.start
                or self.end - self.start > timedelta(days=366)):
            raise ValueError('bounded aware half-open period required')

    @classmethod
    def for_days(cls, now: datetime, days: int = 1):
        if now.tzinfo is None or days not in {1, 7, 30}:
            raise ValueError('invalid history period')
        end = datetime.combine(now.astimezone(KST).date() + timedelta(days=1), time(), KST)
        return cls(end - timedelta(days=days), end)

    @classmethod
    def custom(cls, start: date, end: date):
        return cls(datetime.combine(start, time(), KST),
                   datetime.combine(end + timedelta(days=1), time(), KST))


@dataclass(frozen=True)
class SourceEnvelope:
    resource_id: str
    schema_owner: str
    schema_version: int | None
    account_hash: str
    target: str
    query_at: datetime
    source_observed_at: datetime | None = None
    completeness: str = 'UNKNOWN'
    query_status: str = 'OK'
    freshness: str = 'UNKNOWN'
    diagnostic_code: str | None = None
    provenance: str = 'saved'

    def __post_init__(self):
        if self.query_at.tzinfo is None or (self.source_observed_at is not None and self.source_observed_at.tzinfo is None):
            raise ValueError('aware evidence times required')

    @property
    def age_seconds(self):
        return None if self.source_observed_at is None else max(0, (self.query_at - self.source_observed_at).total_seconds())


@dataclass(frozen=True)
class EvidenceSelection:
    selection_id: str
    resource_id: str
    kind: str
    scope: ResourceScope
    record_ids: tuple[str, ...] = ()
    snapshot_id: str | None = None
    source_ids: tuple[str, ...] = ()
    numerator: int | None = None
    denominator: int | None = None


@dataclass(frozen=True)
class EvidenceRecord:
    record_id: str
    kind: str
    envelope: SourceEnvelope
    selection: EvidenceSelection
    fields: tuple[tuple[str, str | int | float | bool | None], ...] = ()

    def __post_init__(self):
        if not isinstance(self.fields, tuple) or any(not isinstance(pair, tuple) or len(pair) != 2 or
            not isinstance(pair[0], str) or not (pair[1] is None or type(pair[1]) in {str, int, float, bool})
            for pair in self.fields):
            raise ValueError('immutable scalar evidence fields required')

    @property
    def data(self):
        return MappingProxyType(dict(self.fields))

    @property
    def resource_id(self):
        return self.envelope.resource_id

    @property
    def snapshot_id(self):
        return self.selection.snapshot_id


@dataclass(frozen=True)
class AccountDTO:
    envelope: SourceEnvelope
    selection: EvidenceSelection
    available_cash: float | None = None
    total_evaluation: float | None = None
    unrealized_value: float | None = None
    holdings: tuple[EvidenceRecord, ...] = ()
    orders: tuple[EvidenceRecord, ...] = ()
    fills: tuple[EvidenceRecord, ...] = ()
    latest_attempt_id: str | None = None
    latest_attempt_status: str = 'UNKNOWN'
    historical: bool = True

    @property
    def snapshot_id(self):
        return self.selection.snapshot_id


@dataclass(frozen=True)
class RecordPage:
    kind: str
    selection_id: str
    rows: tuple[EvidenceRecord, ...] = ()
    total: int | None = None
    cursor: str | None = None
    sources: tuple[SourceEnvelope, ...] = ()
    active_unresolved: tuple[EvidenceRecord, ...] = ()
    diagnostic_code: str | None = None


@dataclass(frozen=True)
class WorkerDTO:
    envelope: SourceEnvelope
    worker_id: str
    state: str = 'UNKNOWN'
    expected_running: bool | None = None
    cadence_seconds: float | None = None
    lease_observed_at: datetime | None = None
    source_ids: tuple[str, ...] = ()
    snapshot_id: str | None = None


@dataclass(frozen=True)
class OverviewDTO:
    query_at: datetime
    accounts: tuple[AccountDTO, ...] = ()
    unresolved: tuple[EvidenceRecord, ...] = ()
    workers: tuple[WorkerDTO, ...] = ()
    sources: tuple[SourceEnvelope, ...] = ()
    atomic_cross_store: bool = False


@dataclass(frozen=True)
class AlertSourceBatch:
    query_at: datetime
    facts: tuple[EvidenceRecord, ...] = ()
    workers: tuple[WorkerDTO, ...] = ()
    sources: tuple[SourceEnvelope, ...] = ()
    cursor: str | None = None


# Kind-specific aliases preserve one immutable detail/evidence projection contract.
HoldingDTO = RunDTO = DecisionDTO = OrderDTO = FillDTO = EvidenceRecord


class EvidenceReader(Protocol):
    def source_status(self) -> tuple[SourceEnvelope, ...]: ...
    def overview(self, scope: ResourceScope) -> OverviewDTO: ...
    def list_records(self, kind, scope, period=None, cursor=None, limit=50) -> RecordPage: ...
    def get_record(self, resource_id, record_id) -> EvidenceRecord: ...
    def get_evidence(self, resource_id, record_id) -> EvidenceRecord: ...
    def observe_alert_sources(self, cursor=None) -> AlertSourceBatch: ...
