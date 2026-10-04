"""Immutable, secret-free scheduling evidence; none of these models grants authority."""
from __future__ import annotations

from datetime import date
from enum import StrEnum
import hashlib
import json
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

KST = ZoneInfo('Asia/Seoul')
Identity = Annotated[str, Field(pattern=r'^[a-zA-Z0-9][a-zA-Z0-9_.:/ -]{0,127}$')]
Digest = Annotated[str, Field(pattern=r'^[a-f0-9]{64}$')]
Revision = Annotated[int, Field(ge=0, strict=True)]


class ServiceContract(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid', hide_input_in_errors=True,
                             validate_default=True, revalidate_instances='always',
                             ser_json_bytes='base64', val_json_bytes='base64')

    def model_copy(self, *, update=None, deep=False):
        # BaseModel's unchecked update cannot be used to manufacture valid evidence.
        return type(self).model_validate(self.model_dump() | (update or {}))


class ServiceMode(StrEnum):
    DISABLED = 'DISABLED'
    DRY_RUN = 'DRY_RUN'
    KIS_MOCK = 'KIS_MOCK'


class ServiceScope(ServiceContract):
    account_scope_hash: Digest
    execution_target: Literal['mock']


class InstallationScope(ServiceContract):
    """Global operational stop domain, independent of trading day and generation."""
    registered_scopes: tuple[ServiceScope, ...] = Field(min_length=1, max_length=64)

    @model_validator(mode='after')
    def unique_scopes(self):
        if len(set(self.registered_scopes)) != len(self.registered_scopes):
            raise ValueError('unique registered scopes required')
        object.__setattr__(self, 'registered_scopes', tuple(sorted(
            self.registered_scopes, key=lambda s: (s.account_scope_hash, s.execution_target))))
        return self


class ServiceJobKind(StrEnum):
    PREP = 'PREP'
    DAILY = 'DAILY'
    RISK = 'RISK'


class LogicalJobKey(ServiceContract):
    scope: ServiceScope
    trading_date_kst: date
    kind: ServiceJobKind

    @property
    def logical_id(self) -> str:
        return hashlib.sha256(self.model_dump_json().encode()).hexdigest()


class ServiceAttempt(ServiceContract):
    job: LogicalJobKey
    generation_id: Identity
    attempt_id: Identity
    observed_at: AwareDatetime


class ServiceJobState(StrEnum):
    DUE = 'DUE'
    CLAIMED = 'CLAIMED'
    RUNNING = 'RUNNING'
    COMPLETED = 'COMPLETED'
    PARTIAL = 'PARTIAL'
    MISSED = 'MISSED'
    BLOCKED = 'BLOCKED'
    UNKNOWN = 'UNKNOWN'


class ControlAction(StrEnum):
    PAUSE = 'PAUSE'
    RESUME = 'RESUME'
    KILL = 'KILL'


class ControlMode(StrEnum):
    RUNNING = 'RUNNING'
    PAUSED = 'PAUSED'
    KILLED = 'KILLED'


class ControlRequest(ServiceContract):
    request_id: Identity
    actor: Identity
    requested_at: AwareDatetime
    scope: InstallationScope
    action: ControlAction
    expected_revision: Revision


class AppliedControl(ServiceContract):
    revision: Revision
    mode: ControlMode
    request_id: Identity | None
    applied_at: AwareDatetime
    safety_evidence_ids: tuple[Identity, ...] = Field(max_length=128)

    @model_validator(mode='after')
    def attributable_revision(self):
        if (self.revision == 0) != (self.request_id is None):
            raise ValueError('non-initial revision requires a request identity')
        return self


class DailyDispatchEnvelope(ServiceContract):
    prompt_bytes: bytes = Field(min_length=1, max_length=2 * 1024 * 1024, repr=False)
    prompt_hash: Digest
    system_prompt: str = Field(min_length=1, max_length=65536, repr=False)
    schema_hash: Digest
    provider: Literal['codex', 'openai', 'anthropic']
    model: Identity
    temperature: float = Field(ge=0, le=2, allow_inf_nan=False)
    prompt_version: Identity

    @model_validator(mode='after')
    def exact_prompt(self):
        if hashlib.sha256(self.prompt_bytes).hexdigest() != self.prompt_hash:
            raise ValueError('prompt digest mismatch')
        return self

    @property
    def envelope_hash(self) -> str:
        # Byte digest plus all dispatch-affecting fields, unambiguous canonical JSON.
        facts = self.model_dump(exclude={'prompt_bytes'})
        return hashlib.sha256(json.dumps(facts, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


class SourceHash(ServiceContract):
    source_id: Identity
    source_hash: Digest


class CheckpointApproval(ServiceContract):
    checkpoint: Literal['09-08 task 1', '09-08 task 2']
    actor: Identity
    approved_at: AwareDatetime
    evidence_ids: tuple[Identity, ...] = Field(min_length=1, max_length=128)


class AcceptanceReceipt(ServiceContract):
    receipt_id: Identity
    evidence_class: Literal['KIS_OBSERVED', 'CONTROLLED_INJECTION', 'SYNTHETIC']
    scope: ServiceScope
    campaign_id: Identity
    profile_fingerprint: Digest
    source_hashes: tuple[SourceHash, ...] = Field(min_length=1, max_length=128)
    checkpoint_approvals: tuple[CheckpointApproval, ...] = Field(max_length=2)
    evidence_ids: tuple[Identity, ...] = Field(min_length=1, max_length=128)
    approved_at: AwareDatetime

    @model_validator(mode='after')
    def attributable_approvals(self):
        if len({s.source_id for s in self.source_hashes}) != len(self.source_hashes):
            raise ValueError('source identities must be unique')
        if len({a.checkpoint for a in self.checkpoint_approvals}) != len(self.checkpoint_approvals):
            raise ValueError('checkpoint identities must be unique')
        for approval in self.checkpoint_approvals:
            if (approval.approved_at > self.approved_at
                    or not set(approval.evidence_ids).issubset(self.evidence_ids)):
                raise ValueError('approval must link covered prior evidence')
        return self

    @property
    def has_both_checkpoint_approvals(self) -> bool:
        # Shape completeness only; activation must validate authentic current sources.
        return {a.checkpoint for a in self.checkpoint_approvals} == {'09-08 task 1', '09-08 task 2'}


class SessionEligibility(StrEnum):
    ELIGIBLE = 'ELIGIBLE'
    HOLIDAY = 'HOLIDAY'
    UNKNOWN = 'UNKNOWN'


class SessionEvidence(ServiceContract):
    trading_date_kst: date
    source_id: Identity
    source_hash: Digest
    source_url: str = Field(min_length=1, max_length=2048, repr=False)
    notice_id: Identity
    reviewed_at: AwareDatetime
    reviewer: Identity
    observed_at: AwareDatetime
    effective_at: AwareDatetime
    eligibility: SessionEligibility
    continuous_open: AwareDatetime | None
    continuous_close: AwareDatetime | None

    @model_validator(mode='after')
    def exact_session(self):
        if self.eligibility == SessionEligibility.ELIGIBLE:
            if self.continuous_open is None or self.continuous_close is None:
                raise ValueError('eligible session requires confirmed bounds')
        elif self.continuous_open is not None or self.continuous_close is not None:
            raise ValueError('unconfirmed session cannot assert trading bounds')
        if self.continuous_open is not None:
            if (self.continuous_close is None or self.continuous_open >= self.continuous_close
                    or any(t.astimezone(KST).date() != self.trading_date_kst
                           for t in (self.continuous_open, self.continuous_close))):
                raise ValueError('ordered exact-date session bounds required')
        if self.effective_at > self.observed_at or self.reviewed_at > self.observed_at:
            raise ValueError('future session provenance forbidden')
        return self


class OwnerLoginState(StrEnum):
    CONFIRMED = 'CONFIRMED'
    ABSENT = 'ABSENT'
    UNKNOWN = 'UNKNOWN'


class OwnerLoginEvidence(ServiceContract):
    owner_uid: Annotated[int, Field(ge=0, strict=True)]
    gui_session_id: Identity | None
    source_id: Identity
    observed_at: AwareDatetime
    effective_at: AwareDatetime
    state: OwnerLoginState

    @model_validator(mode='after')
    def confirmed_identity(self):
        if self.state == OwnerLoginState.CONFIRMED and self.gui_session_id is None:
            raise ValueError('confirmed GUI session identity required')
        if self.effective_at > self.observed_at:
            raise ValueError('future login provenance forbidden')
        return self


class ExpectationInputs(ServiceContract):
    registered_scopes: tuple[ServiceScope, ...] = Field(min_length=1, max_length=64)
    service_enabled: bool = Field(strict=True)
    mode: ServiceMode
    config_hash: Digest
    config_effective_at: AwareDatetime
    login_evidence: OwnerLoginEvidence
    session: SessionEvidence
    effective_controls: AppliedControl
    control_scope: InstallationScope
    controls_source_id: Identity
    controls_observed_at: AwareDatetime
    controls_effective_at: AwareDatetime

    @model_validator(mode='after')
    def exact_control_scope(self):
        if (len(set(self.registered_scopes)) != len(self.registered_scopes)
                or set(self.registered_scopes) != set(self.control_scope.registered_scopes)):
            raise ValueError('control scope must cover the installation registration')
        if self.controls_effective_at > self.controls_observed_at:
            raise ValueError('future control provenance forbidden')
        return self


class ServiceExpectation(ServiceContract):
    expectation_id: Identity
    scope: ServiceScope
    trading_date_kst: date
    kind: ServiceJobKind
    state: Literal['EXPECTED', 'NOT_EXPECTED', 'UNKNOWN']
    producer_kind: Literal['OBSERVER_DERIVED', 'RUNTIME_OBSERVED']
    source_id: Identity
    source_hash: Digest
    observed_at: AwareDatetime
    effective_at: AwareDatetime
    eligibility: SessionEligibility
    continuous_open: AwareDatetime | None
    continuous_close: AwareDatetime | None
    due_at: AwareDatetime | None
    deadline_at: AwareDatetime | None
    config_hash: Digest
    config_effective_at: AwareDatetime
    login_source_id: Identity
    login_effective_at: AwareDatetime
    session_source_id: Identity
    session_source_hash: Digest
    control_revision: Revision
    controls_source_id: Identity
    controls_observed_at: AwareDatetime
    controls_effective_at: AwareDatetime
    reason_code: Annotated[str, Field(pattern=r'^[A-Z][A-Z0-9_]{0,63}$')]

    @model_validator(mode='after')
    def obligation_provenance(self):
        if self.state == 'EXPECTED' and (self.eligibility != SessionEligibility.ELIGIBLE
                or self.continuous_open is None or self.continuous_close is None
                or self.due_at is None or self.deadline_at is None):
            raise ValueError('expected obligation requires positive dated session and slots')
        for value in (self.continuous_open, self.continuous_close, self.due_at, self.deadline_at):
            if value is not None and value.astimezone(KST).date() != self.trading_date_kst:
                raise ValueError('exact-date obligation required')
        if self.due_at and self.deadline_at and self.due_at >= self.deadline_at:
            raise ValueError('ordered obligation interval required')
        if self.continuous_open and self.continuous_close and self.continuous_open >= self.continuous_close:
            raise ValueError('ordered session interval required')
        if (self.effective_at > self.observed_at
                or self.controls_effective_at > self.controls_observed_at
                or self.controls_observed_at > self.observed_at
                or self.config_effective_at > self.observed_at
                or self.login_effective_at > self.observed_at):
            raise ValueError('future expectation provenance forbidden')
        return self


class ProviderAdmissionState(StrEnum):
    PREPARED = 'PREPARED'
    IN_FLIGHT = 'IN_FLIGHT'
    SUPPRESSED_NO_CALL = 'SUPPRESSED_NO_CALL'
    UNKNOWN = 'UNKNOWN'
    FINISHED = 'FINISHED'


class ProviderCallAdmission(ServiceContract):
    dispatch_id: Identity
    evaluation_id: Identity
    scope: ServiceScope
    trading_date_kst: date
    envelope_hash: Digest
    state: ProviderAdmissionState
    reason_code: Annotated[str, Field(pattern=r'^[A-Z][A-Z0-9_]{0,63}$')]
    control_revision: Revision
    session_source_id: Identity
    observed_at: AwareDatetime
    invocation_started_at: AwareDatetime | None

    @model_validator(mode='after')
    def operational_handoff(self):
        if self.state in {ProviderAdmissionState.PREPARED, ProviderAdmissionState.SUPPRESSED_NO_CALL}:
            if self.invocation_started_at is not None:
                raise ValueError('no-call evidence cannot assert invocation')
        if self.state in {ProviderAdmissionState.IN_FLIGHT, ProviderAdmissionState.FINISHED}:
            if self.invocation_started_at is None:
                raise ValueError('transport entry evidence required')
        if self.invocation_started_at is not None:
            if (self.invocation_started_at > self.observed_at
                    or self.invocation_started_at.astimezone(KST).date() != self.trading_date_kst):
                raise ValueError('exact-date prior invocation evidence required')
        return self

    @property
    def restores_dispatch_authority(self) -> Literal[False]:
        return False
