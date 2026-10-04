"""Read-only Phase 09-08 acceptance gates. No receipt capture or freeze mutation."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Callable, Literal, Protocol

from pydantic import AwareDatetime, Field

from .service_config import ServiceSettings, protected_file
from .service_models import AcceptanceReceipt, Digest, Identity, ServiceContract, ServiceScope, SourceHash


class ActivationVerdict(ServiceContract):
    allowed: bool = Field(strict=True)
    reason_codes: tuple[Identity, ...]
    source_ids: tuple[Identity, ...] = ()
    receipt_id: Identity | None = None
    authority: Literal['DENIED', 'OWNED_KIS_OBSERVED', 'OFFLINE_ONLY'] = 'DENIED'


class AcceptanceDay(ServiceContract):
    trading_date: date
    run_id: Identity
    eligible: bool = Field(strict=True)
    terminal: bool = Field(strict=True)
    target: Literal['mock', 'real', 'unknown']
    evidence_class: Literal['KIS_OBSERVED', 'SYNTHETIC', 'UNKNOWN']


class AcceptanceDrill(ServiceContract):
    fault: Identity
    drill_id: Identity
    verdict: Literal['PASSED', 'FAILED', 'UNKNOWN']
    complete: bool = Field(strict=True)
    evidence_class: Literal['CONTROLLED_INJECTION', 'KIS_OBSERVED', 'SYNTHETIC']


class SavedAcceptanceEvidence(ServiceContract):
    scope: ServiceScope
    campaign_id: Identity
    profile_fingerprint: Digest
    profile_version: Identity
    owner_actor: Identity
    source_hashes: tuple[SourceHash, ...]
    evidence_ids: tuple[Identity, ...]
    state: Literal['ACTIVE', 'COMPLETED', 'FAILED']
    campaign_kind: Literal['SOAK', 'PROOF_ORDER']
    target_days: int = Field(strict=True, ge=0)
    availability_budget: int = Field(strict=True, ge=0)
    availability_used: int = Field(strict=True, ge=0)
    safety_breaches: int = Field(strict=True, ge=0)
    safety_latched: bool = Field(strict=True)
    cross_store_unknown: int = Field(strict=True, ge=0)
    reconciliation_unknown: int = Field(strict=True, ge=0)
    reconciliation_incomplete: int = Field(strict=True, ge=0)
    profile_accepted: bool = Field(strict=True)
    days: tuple[AcceptanceDay, ...]
    drills: tuple[AcceptanceDrill, ...]
    frozen_tickers: tuple[Identity, ...]


class CurrentActivationSafety(ServiceContract):
    scope: ServiceScope
    observed_at: AwareDatetime
    expires_at: AwareDatetime
    healthy: bool = Field(strict=True)
    safety_latched: bool = Field(strict=True)
    frozen_tickers: tuple[Identity, ...]
    source_hashes: tuple[SourceHash, ...]


@dataclass(frozen=True)
class OfflineActivationAuthority:
    """Only temporary shape tests; this token can never authorize production clients."""
    root: Path

    def __post_init__(self):
        root = Path(self.root).resolve(strict=True)
        temporary = Path(tempfile.gettempdir()).resolve()
        repository = Path(__file__).resolve().parents[1]
        if (not root.is_dir() or root == temporary or not root.is_relative_to(temporary)
                or root.is_relative_to(repository) or root.stat().st_uid != os.getuid()):
            raise ValueError('owned temporary offline authority required')
        object.__setattr__(self, 'root', root)

    def assert_settings(self, settings: ServiceSettings) -> None:
        paths = (*settings.trading_journal_paths, settings.service_db_path,
                 settings.control_db_path, settings.lock_dir, settings.trading_config_path,
                 settings.acceptance_receipt_path, settings.session_evidence_path)
        if any(not Path(p).resolve().is_relative_to(self.root) for p in paths):
            raise ValueError('offline topology must remain temporary')


class SavedEvidenceReader(Protocol):
    def read(self, receipt: AcceptanceReceipt) -> SavedAcceptanceEvidence: ...


SafetyReader = Callable[[ServiceScope, datetime], CurrentActivationSafety]


@dataclass(frozen=True)
class ObservedSafetyReader:
    """Trusted observation with an actual clock after bounded source reads.

    The supplied timestamp is observation start. Evaluation end determines age;
    neither a later read nor an advancing clock rewrites the source timestamp.
    Legacy readers retain their explicit fixed evaluation time.
    """
    read: SafetyReader
    clock: Callable[[], datetime]

    def __call__(self, scope, now):
        return self.read(scope, now)


def _protected_json(path: Path, limit: int = 2 * 1024 * 1024):
    checked = protected_file(path)
    before = checked.stat()
    fd = os.open(checked, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, 'rb') as file:
        info = os.fstat(file.fileno())
        if (info.st_dev, info.st_ino) != (before.st_dev, before.st_ino):
            raise ValueError('protected source replaced')
        payload = file.read(limit + 1)
    if len(payload) > limit:
        raise ValueError('protected source exceeds bound')
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('duplicate source key')
            value[key] = item
        return value
    return json.loads(payload, object_pairs_hook=unique)


def load_acceptance_receipt(path: Path) -> AcceptanceReceipt:
    return AcceptanceReceipt.model_validate(_protected_json(path, 65536))


def _digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False).encode()).hexdigest()


def _source(owner: str, version: int | str, path: Path, payload) -> SourceHash:
    location = hashlib.sha256(str(path.resolve()).encode()).hexdigest()
    return SourceHash(source_id=f'{owner}:v{version}:{location}',
                      source_hash=_digest(payload))


class ReadOnlyAcceptanceEvidenceReader:
    """Exact owned SQLite schemas/transactions and protected accepted profile.

    Digests cover canonical selected rows (including WAL truth), not DB file bytes.
    Each owner has its own transaction; no cross-store atomic snapshot is claimed.
    """
    def __init__(self, settings: ServiceSettings, *, profile_path: Path, owner_actor: str):
        from .soak_reporting import ReadOnlySoakRepository
        if len(settings.trading_journal_paths) != 3:
            raise ValueError('exact primary/soak/controller paths required')
        self._settings = settings
        self._profile_path = protected_file(profile_path)
        self._owner_actor = owner_actor
        self._repo = ReadOnlySoakRepository(*settings.trading_journal_paths)

    def read(self, receipt: AcceptanceReceipt) -> SavedAcceptanceEvidence:
        from .reporting import ReadOnlyAuditRepository, EvidenceState, ReconciliationState
        from .soak_drills import FAULT_REGISTRY, DRILL_POLICY_VERSION
        from .soak_models import FaultName
        from .soak_reporting import build_soak_report
        from .portfolio import canonical_account_scope_hash
        profile = _protected_json(self._profile_path)
        iterator = self._repo.transactions()
        primary, soak, controller = next(iterator)
        try:
            data = self._repo._load(primary, soak, controller, campaign_id=receipt.campaign_id)
            # The shipped report sees the identical independently saved read transactions.
            class FrozenReportSource:
                def load(self, campaign_id):
                    return data
            report = build_soak_report(FrozenReportSource(), receipt.campaign_id)
            campaign = data['campaign']
            identities = soak.execute('SELECT * FROM soak_identity_receipts WHERE campaign_id=? ORDER BY id',
                                      (receipt.campaign_id,)).fetchall()
            if len(identities) != 1:
                raise ValueError('one immutable mock identity required')
            identity = identities[0]
            scope = ServiceScope(account_scope_hash=canonical_account_scope_hash(
                'mock', identity['account_suffix']), execution_target=identity['target'])
            days = []
            primary_payload = {}
            ids = {f'campaign:{receipt.campaign_id}', f'identity:{identity["receipt_id"]}'}
            primary_reader = ReadOnlyAuditRepository(self._repo.primary_audit_db_path)
            selected_runs = {str(d['run_id']) for d in data['days']}
            selected_runs.update(str(link['run_id']) for link in data['links'] if link['run_id'])
            for item in data['days']:
                if item['credit_state'] != 'CREDITED':
                    continue
                run = primary.execute('SELECT * FROM runs WHERE run_id=?', (item['run_id'],)).fetchone()
                detail = json.loads(item['credit_detail_json'])
                section = primary_reader._load_run(primary, run) if run is not None else None
                day = date.fromisoformat(item['trading_date'])
                run_day = str(run['trading_date_kst']).replace('-', '') if run else ''
                stages = {s['stage'] for s in data['snapshots'] if s['run_id'] == item['run_id']
                          and s['completeness'] == 'COMPLETE'}
                submission_count = primary.execute("SELECT COUNT(*) FROM order_events WHERE origin_run_id=? "
                    "AND event_type IN ('SUBMISSION_ACCEPTED','SUBMISSION_AMBIGUOUS')", (item['run_id'],)).fetchone()[0]
                post_count = sum(s['run_id']==item['run_id'] and s['stage']=='POST_SUBMISSION'
                    and s['completeness']=='COMPLETE' for s in data['snapshots'])
                eligible = (detail.get('verdict_code') == 'CREDITED' and run_day == day.strftime('%Y%m%d')
                    and section is not None and section.run_kind == 'RUN' and item['run_kind'] == 'RUN'
                    and not bool(run['dry_run']) and submission_count==post_count
                    and section.run_state is EvidenceState.COMPLETE
                    and all(c.ticker_state is EvidenceState.COMPLETE and
                        c.reconciliation_state not in {ReconciliationState.PENDING, ReconciliationState.UNKNOWN}
                        for c in section.candidates)
                    and 'PRE_RUN' in stages and bool(stages & {'PRE_FINALIZE', 'PRE_FINALIZATION'}))
                days.append(AcceptanceDay(trading_date=day, run_id=item['run_id'], eligible=eligible,
                    terminal=bool(item['terminal']), target=run['target'] if run else 'unknown',
                    evidence_class='KIS_OBSERVED' if eligible else 'UNKNOWN'))
            for table, columns in (('runs', ('run_id',)), ('ticker_outcomes', ('run_id',)),
                    ('decisions', ('run_id',)), ('order_events', ('origin_run_id', 'observer_run_id')),
                    ('notification_attempts', ('run_id',))):
                rows = primary.execute(f'SELECT * FROM {table} ORDER BY rowid').fetchall()
                primary_payload[table] = [dict(r) for r in rows if any(r[c] in selected_runs for c in columns)]
            ids.update(f'run:{r}' for r in selected_runs if r in data['primary_runs'])
            # Named roots fit the receipt's bounded IDs; each source digest covers
            # every nested snapshot/comparison/observation ID and immutable row.
            for key, column, prefix in (('links','drill_id','drill'),):
                ids.update(f'{prefix}:{r[column]}' for r in data[key])
            soak_payload = {}
            for table in ('soak_campaigns', 'soak_identity_receipts', 'soak_days', 'soak_events',
                    'soak_snapshots', 'soak_comparisons', 'soak_ambiguity_observations',
                    'soak_ticker_freezes', 'soak_drill_links'):
                soak_payload[table] = [dict(r) for r in soak.execute(
                    f'SELECT * FROM {table} WHERE campaign_id=? ORDER BY rowid', (receipt.campaign_id,))]
            snapshot_ids = {r['snapshot_id'] for r in data['snapshots']}
            for suffix in ('orders','fills','holdings','accounts'):
                table = f'soak_snapshot_{suffix}'
                soak_payload[table] = [dict(r) for r in soak.execute(f'SELECT * FROM {table} ORDER BY id')
                                      if r['snapshot_id'] in snapshot_ids]
            contracts = [dict(r) for r in controller.execute(
                'SELECT * FROM drill_contracts WHERE campaign_id=? ORDER BY drill_id', (receipt.campaign_id,))]
            drill_ids = {r['drill_id'] for r in contracts}
            controller_payload = {'drill_contracts': contracts}
            for table in ('drill_commits', 'drill_observations', 'drill_verdicts'):
                controller_payload[table] = [dict(r) for r in controller.execute(f'SELECT * FROM {table} ORDER BY id')
                                             if r['drill_id'] in drill_ids]
            drills = []
            for contract in contracts:
                spec = FAULT_REGISTRY[FaultName(contract['fault'])]
                observations = [r for r in controller_payload['drill_observations']
                                if r['drill_id'] == contract['drill_id']]
                passing = {r['observation_type'] for r in observations
                           if json.loads(r['facts_json']).get('passed') is True
                           and r['evidence_class'] == 'CONTROLLED_INJECTION'
                           and (r['primary_run_id'] is None or r['primary_run_id'] in data['primary_runs'])
                           and (r['order_intent_id'] is None or r['order_intent_id'] in data['primary_intents'])
                           and (r['reconciliation_id'] is None or r['reconciliation_id'] in
                                {x['comparison_id'] for x in data['comparisons']})
                           and (r['freeze_id'] is None or r['freeze_id'] in
                                {x['freeze_id'] for x in data['freezes']})}
                verdicts = [r for r in controller_payload['drill_verdicts'] if r['drill_id']==contract['drill_id']]
                links = [r for r in data['links'] if r['drill_id']==contract['drill_id']
                         and r['evidence_class']=='CONTROLLED_INJECTION' and r['verdict']=='PASSED']
                complete = (len(verdicts)==1 and len(links)==1
                    and json.loads(verdicts[0]['detail_json']).get('evidence_complete') is True
                    and any(r['drill_id']==contract['drill_id'] for r in controller_payload['drill_commits'])
                    and tuple(json.loads(contract['required_observations_json'])) == spec.required_observations
                    and set(spec.required_observations) <= passing
                    and contract['policy_version'] == DRILL_POLICY_VERSION
                    and contract['injection_boundary'] == spec.boundary.value
                    and tuple(json.loads(contract['expected_containment_json'])) == spec.expected_containment)
                drills.append(AcceptanceDrill(fault=contract['fault'], drill_id=contract['drill_id'],
                    verdict=verdicts[0]['verdict'] if len(verdicts)==1 else 'UNKNOWN',
                    complete=complete, evidence_class='CONTROLLED_INJECTION'))
            sources = tuple(_source(owner, conn.execute('PRAGMA user_version').fetchone()[0], path, payload)
                for owner, conn, path, payload in (
                    ('primary',primary,self._repo.primary_audit_db_path,primary_payload),
                    ('soak',soak,self._repo.soak_db_path,soak_payload),
                    ('controller',controller,self._repo.controller_db_path,controller_payload)))
            sources += (_source('profile', 'kis-mock-compat-v1', self._profile_path, profile),)
            frozen = self._current_freezes(primary, soak, controller)
            profile_ok = (profile.get('state')=='ACCEPTED' and profile.get('evidence_class')=='KIS_OBSERVED'
                and profile.get('schema_version')=='kis-mock-compat-v1'
                and profile.get('profile_version')==campaign['accepted_profile_version']==identity['profile_version']
                and all(profile.get(key, {}).get('completeness')=='COMPLETE' and
                        type(profile.get(key, {}).get('page_count')) is int and profile[key]['page_count']>0
                        for key in ('daily','balance'))
                and identity['domain_class']=='KIS_MOCK_VTS' and identity['policy_version']=='mock-isolation-v1'
                and campaign['accepted_profile_fingerprint']=='sha256:'+_digest(profile))
            return SavedAcceptanceEvidence(scope=scope, campaign_id=receipt.campaign_id,
                profile_fingerprint=str(campaign['accepted_profile_fingerprint']).removeprefix('sha256:'),
                profile_version=campaign['accepted_profile_version'], owner_actor=self._owner_actor,
                source_hashes=sources, evidence_ids=tuple(sorted(ids)), state=campaign['state'],
                campaign_kind=campaign['campaign_kind'], target_days=report.campaign.target_days,
                availability_budget=report.campaign.availability_budget, availability_used=report.campaign.availability_used,
                safety_breaches=sum('SAFETY' in r['event_code'] or r['event_code'].startswith('D09_') for r in data['events']),
                safety_latched=bool(campaign['safety_failure_code']), cross_store_unknown=report.cross_store_unknown,
                reconciliation_unknown=report.reconciliation.unknown, reconciliation_incomplete=report.reconciliation.incomplete,
                profile_accepted=profile_ok, days=tuple(days), drills=tuple(drills), frozen_tickers=frozen)
        finally:
            try:
                next(iterator)
            except StopIteration:
                pass

    def _current_freezes(self, primary, soak, controller) -> tuple[str, ...]:
        from .soak_reporting import build_soak_report
        frozen = set()
        for row in soak.execute('SELECT campaign_id FROM soak_campaigns ORDER BY campaign_id'):
            data = self._repo._load(primary, soak, controller, campaign_id=row[0])
            class Saved:
                def load(self, campaign_id):
                    return data
            report = build_soak_report(Saved(), row[0])
            frozen.update(report.freezes.tickers)
        return tuple(sorted(frozen))

    def read_freezes(self) -> tuple[str, ...]:
        iterator = self._repo.transactions()
        connections = next(iterator)
        try:
            return self._current_freezes(*connections)
        finally:
            try:
                next(iterator)
            except StopIteration:
                pass


def validate_unattended_activation(settings: ServiceSettings, receipt: AcceptanceReceipt | None,
        saved_evidence_reader: SavedEvidenceReader | None, current_safety: SafetyReader | None, *,
        now: datetime | None = None, offline_authority: OfflineActivationAuthority | None = None) -> ActivationVerdict:
    return _validate_acceptance(settings, receipt, saved_evidence_reader, current_safety,
        now=now, offline_authority=offline_authority)


def validate_receipt_capture(settings: ServiceSettings, receipt: AcceptanceReceipt,
        saved_evidence_reader: ReadOnlyAcceptanceEvidenceReader, *, now: datetime) -> ActivationVerdict:
    """Authentic saved proof transport validation; grants no execution authority."""
    return _validate_acceptance(settings,receipt,saved_evidence_reader,None,now=now,capture_only=True)


def _validate_acceptance(settings: ServiceSettings, receipt: AcceptanceReceipt | None,
        saved_evidence_reader: SavedEvidenceReader | None, current_safety: SafetyReader | None, *,
        now: datetime | None = None, offline_authority: OfflineActivationAuthority | None = None,
        capture_only: bool = False) -> ActivationVerdict:
    """Both 09-08 approvals + exact immutable owner/version/hash proof + current gates."""
    now = now or datetime.now(timezone.utc)
    reasons = []
    def denied(code):
        return ActivationVerdict(allowed=False, reason_codes=(code,),
                                 receipt_id=getattr(receipt, 'receipt_id', None))
    if settings.execution_target != 'mock' or any(s.execution_target!='mock' for s in settings.registered_scopes):
        return denied('REAL_TARGET_FORBIDDEN')
    if not capture_only and (not settings.service_enabled or settings.mode.value != 'KIS_MOCK'):
        return denied('SERVICE_NOT_ACTIVE')
    if receipt is None:
        return denied('ACCEPTANCE_RECEIPT_MISSING')
    try:
        receipt = AcceptanceReceipt.model_validate(receipt.model_dump())
    except Exception:
        return denied('ACCEPTANCE_RECEIPT_INVALID')
    offline = offline_authority is not None
    if offline:
        try:
            if type(offline_authority) is not OfflineActivationAuthority:
                return denied('OFFLINE_AUTHORITY_INVALID')
            offline_authority.assert_settings(settings)
        except Exception:
            return denied('OFFLINE_AUTHORITY_INVALID')
    elif (receipt.evidence_class != 'KIS_OBSERVED'
            or type(saved_evidence_reader) is not ReadOnlyAcceptanceEvidenceReader):
        return denied('AUTHENTIC_ACCEPTANCE_REQUIRED')
    if not receipt.has_both_checkpoint_approvals:
        return denied('CHECKPOINT_APPROVAL_MISSING')
    if receipt.scope not in settings.registered_scopes:
        return denied('ACCOUNT_SCOPE_MISMATCH')
    if now.tzinfo is None or receipt.approved_at > now:
        return denied('APPROVAL_TIME_INVALID')
    try:
        if not offline:
            if saved_evidence_reader._settings != settings:
                return denied('SOURCE_TOPOLOGY_MISMATCH')
            if not capture_only and load_acceptance_receipt(settings.acceptance_receipt_path) != receipt:
                return denied('PROTECTED_RECEIPT_MISMATCH')
        evidence = SavedAcceptanceEvidence.model_validate(saved_evidence_reader.read(receipt).model_dump())
    except Exception:
        return denied('SAVED_EVIDENCE_UNKNOWN')
    if evidence.scope != receipt.scope:
        reasons.append('ACCOUNT_SCOPE_MISMATCH')
    if evidence.campaign_id != receipt.campaign_id:
        reasons.append('CAMPAIGN_MISMATCH')
    if evidence.profile_fingerprint != receipt.profile_fingerprint:
        reasons.append('PROFILE_MISMATCH')
    if (len(evidence.source_hashes)!=4 or len(set(s.source_id for s in evidence.source_hashes))!=4
            or set(evidence.source_hashes)!=set(receipt.source_hashes)):
        reasons.append('SOURCE_IDENTITY_MISMATCH')
    if (set(evidence.evidence_ids)!=set(receipt.evidence_ids)
            or len(set(evidence.evidence_ids))!=len(evidence.evidence_ids)):
        reasons.append('EVIDENCE_LINKS_UNKNOWN')
    day_ids = {f'run:{d.run_id}' for d in evidence.days}
    drill_ids = {f'drill:{d.drill_id}' for d in evidence.drills}
    for approval in receipt.checkpoint_approvals:
        linked = set(approval.evidence_ids)
        if approval.actor != evidence.owner_actor:
            reasons.append('APPROVAL_ACTOR_MISMATCH')
        if approval.checkpoint=='09-08 task 1' and (not linked & day_ids or not drill_ids <= linked):
            reasons.append('CHECKPOINT_EVIDENCE_INCOMPLETE')
        if approval.checkpoint=='09-08 task 2' and not set(evidence.evidence_ids) <= linked:
            reasons.append('CHECKPOINT_EVIDENCE_INCOMPLETE')
    if evidence.target_days!=20 or evidence.availability_budget!=2:
        reasons.append('IMMUTABLE_POLICY_MISMATCH')
    if evidence.availability_used>2:
        reasons.append('AVAILABILITY_BUDGET_EXCEEDED')
    if evidence.state!='COMPLETED' or evidence.campaign_kind!='SOAK':
        reasons.append('CAMPAIGN_NOT_COMPLETED')
    if evidence.safety_breaches or evidence.safety_latched:
        reasons.append('SAFETY_BREACH')
    if evidence.cross_store_unknown:
        reasons.append('EVIDENCE_LINKS_UNKNOWN')
    if evidence.reconciliation_unknown or evidence.reconciliation_incomplete:
        reasons.append('RECONCILIATION_UNKNOWN')
    if not evidence.profile_accepted:
        reasons.append('PROFILE_NOT_AUTHENTICATED')
    if (len(evidence.days)!=20 or len({d.trading_date for d in evidence.days})!=20
            or len({d.run_id for d in evidence.days})!=20):
        reasons.append('ELIGIBLE_DAY_COUNT_MISMATCH')
    if any(not d.eligible or not d.terminal or d.target!='mock'
           or d.evidence_class!='KIS_OBSERVED' for d in evidence.days):
        reasons.append('ELIGIBLE_DAY_EVIDENCE_INVALID')
    from .soak_models import FaultName
    controlled = [d for d in evidence.drills if d.evidence_class=='CONTROLLED_INJECTION']
    if (set(d.fault for d in controlled)!={f.value for f in FaultName}
            or len({d.drill_id for d in controlled})!=len(controlled)
            or any(d.verdict!='PASSED' or not d.complete for d in controlled)):
        reasons.append('CONTROLLED_DRILLS_INCOMPLETE')
    if capture_only:
        if evidence.frozen_tickers:
            reasons.append('UNRESOLVED_FREEZE')
        reasons=tuple(dict.fromkeys(reasons))
        return ActivationVerdict(allowed=not reasons,reason_codes=reasons or ('RECEIPT_CAPTURE_VERIFIED',),
            source_ids=tuple(s.source_id for s in evidence.source_hashes),receipt_id=receipt.receipt_id,
            authority='DENIED')
    try:
        safety = CurrentActivationSafety.model_validate(current_safety(receipt.scope, now).model_dump())
        evaluated = current_safety.clock() if type(current_safety) is ObservedSafetyReader else now
        source_map = {s.source_id:s.source_hash for s in evidence.source_hashes}
        if (safety.scope!=receipt.scope or not safety.healthy or safety.safety_latched
                or not safety.observed_at<=now<=evaluated<safety.expires_at
                or not 0<(safety.expires_at-safety.observed_at).total_seconds()<=10
                or set(safety.source_hashes)!=set(evidence.source_hashes[:3])
                or any(source_map.get(s.source_id)!=s.source_hash for s in safety.source_hashes)):
            reasons.append('CURRENT_SAFETY_UNKNOWN')
        if safety.frozen_tickers or evidence.frozen_tickers:
            reasons.append('UNRESOLVED_FREEZE')
    except Exception:
        reasons.append('CURRENT_SAFETY_UNKNOWN')
    reasons = tuple(dict.fromkeys(reasons))
    return ActivationVerdict(allowed=not reasons, reason_codes=reasons or ('ACCEPTANCE_VALIDATED',),
        source_ids=tuple(s.source_id for s in evidence.source_hashes), receipt_id=receipt.receipt_id,
        authority='DENIED' if reasons else 'OFFLINE_ONLY' if offline else 'OWNED_KIS_OBSERVED')
