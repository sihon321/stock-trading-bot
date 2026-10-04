"""Offline approval shape proofs are never elapsed KIS acceptance."""
from datetime import date, timedelta
from types import SimpleNamespace

import pytest

from tests.service_fixtures import ApprovalBundle, NOW, SCOPE, TempServiceTopology
from trading_bot.service_models import CheckpointApproval, SourceHash


def activation_fixture(tmp_path):
    from trading_bot.service_activation import (
        AcceptanceDay, AcceptanceDrill, CurrentActivationSafety,
        OfflineActivationAuthority, SavedAcceptanceEvidence,
    )
    from trading_bot.soak_models import FaultName
    settings = TempServiceTopology(tmp_path).registration(enabled=True)
    sources = tuple(SourceHash(source_id=f'{owner}:v1:fixture', source_hash=char * 64)
                    for owner, char in zip(('primary', 'soak', 'controller', 'profile'), 'bcde'))
    days = tuple(AcceptanceDay(trading_date=date(2026, 9, 1) + timedelta(days=i),
        run_id=f'run-{i}', eligible=True, terminal=True, target='mock',
        evidence_class='KIS_OBSERVED') for i in range(20))
    drills = tuple(AcceptanceDrill(fault=fault.value, drill_id=f'drill-{fault.value}',
        verdict='PASSED', complete=True, evidence_class='CONTROLLED_INJECTION')
        for fault in FaultName)
    ids = ('campaign:synthetic-campaign', 'identity:mock-identity',
           *(f'run:{day.run_id}' for day in days), *(f'drill:{d.drill_id}' for d in drills))
    evidence = SavedAcceptanceEvidence(scope=SCOPE, campaign_id='synthetic-campaign',
        profile_fingerprint='c' * 64, profile_version='official-example-v1',
        owner_actor='synthetic-owner', source_hashes=sources, evidence_ids=ids,
        state='COMPLETED', campaign_kind='SOAK', target_days=20, availability_budget=2,
        availability_used=2, safety_breaches=0, safety_latched=False,
        cross_store_unknown=0, reconciliation_unknown=0, reconciliation_incomplete=0,
        profile_accepted=True, days=days, drills=drills, frozen_tickers=())
    receipt = ApprovalBundle.synthetic().receipt.model_copy(update={
        'source_hashes': sources, 'evidence_ids': ids,
        'checkpoint_approvals': tuple(CheckpointApproval(checkpoint=f'09-08 task {i}',
            actor='synthetic-owner', approved_at=NOW,
            evidence_ids=(ids[2], ids[-1]) if i == 1 else ids) for i in (1, 2))})
    safety = CurrentActivationSafety(scope=SCOPE, observed_at=NOW,
        expires_at=NOW + timedelta(seconds=10), healthy=True,
        safety_latched=False, frozen_tickers=(), source_hashes=sources[:3])
    reader = SimpleNamespace(read=lambda receipt: evidence, authority='OFFLINE_ONLY')
    return settings, receipt, reader, safety, OfflineActivationAuthority(tmp_path), evidence


def verdict(tmp_path, **changes):
    from trading_bot.service_activation import validate_unattended_activation
    settings, receipt, reader, safety, authority, evidence = activation_fixture(tmp_path)
    receipt = receipt.model_copy(update=changes.pop('receipt', {}))
    evidence = evidence.model_copy(update=changes.pop('evidence', {}))
    safety = safety.model_copy(update=changes.pop('safety', {}))
    reader.read = lambda receipt: evidence
    return validate_unattended_activation(settings, receipt, reader,
        lambda scope, now: safety, now=NOW, offline_authority=authority, **changes)


def test_offline_shape_is_explicitly_nonproduction(tmp_path):
    result = verdict(tmp_path)
    assert result.allowed and result.authority == 'OFFLINE_ONLY'
    assert result.receipt_id == 'synthetic-receipt'
    assert len(result.source_ids) == 4


@pytest.mark.parametrize('task', [1, 2])
def test_both_checkpoint_approvals_required(tmp_path, task):
    _, receipt, *_ = activation_fixture(tmp_path)
    result = verdict(tmp_path, receipt={'checkpoint_approvals': (receipt.checkpoint_approvals[task-1],)})
    assert not result.allowed and 'CHECKPOINT_APPROVAL_MISSING' in result.reason_codes


@pytest.mark.parametrize('change,reason', [
    ({'campaign_id': 'another'}, 'CAMPAIGN_MISMATCH'),
    ({'profile_fingerprint': 'f'*64}, 'PROFILE_MISMATCH'),
    ({'source_hashes': (SourceHash(source_id='foreign', source_hash='b'*64),)}, 'SOURCE_IDENTITY_MISMATCH'),
])
def test_exact_immutable_identity(tmp_path, change, reason):
    result = verdict(tmp_path, receipt=change)
    assert not result.allowed and reason in result.reason_codes


@pytest.mark.parametrize('change,reason', [
    ({'target_days': 21}, 'IMMUTABLE_POLICY_MISMATCH'),
    ({'availability_budget': 3}, 'IMMUTABLE_POLICY_MISMATCH'),
    ({'availability_used': 3}, 'AVAILABILITY_BUDGET_EXCEEDED'),
    ({'safety_breaches': 1}, 'SAFETY_BREACH'),
    ({'safety_latched': True}, 'SAFETY_BREACH'),
    ({'state': 'ACTIVE'}, 'CAMPAIGN_NOT_COMPLETED'),
    ({'campaign_kind': 'PROOF_ORDER'}, 'CAMPAIGN_NOT_COMPLETED'),
    ({'cross_store_unknown': 1}, 'EVIDENCE_LINKS_UNKNOWN'),
    ({'reconciliation_unknown': 1}, 'RECONCILIATION_UNKNOWN'),
    ({'reconciliation_incomplete': 1}, 'RECONCILIATION_UNKNOWN'),
    ({'profile_accepted': False}, 'PROFILE_NOT_AUTHENTICATED'),
    ({'frozen_tickers': ('000660',)}, 'UNRESOLVED_FREEZE'),
    ({'drills': ()}, 'CONTROLLED_DRILLS_INCOMPLETE'),
    ({'days': ()}, 'ELIGIBLE_DAY_COUNT_MISMATCH'),
])
def test_zero_tolerance_and_counts(tmp_path, change, reason):
    result = verdict(tmp_path, evidence=change)
    assert not result.allowed and reason in result.reason_codes


@pytest.mark.parametrize('corruption', ['duplicate', 'ineligible', 'nonterminal', 'synthetic', 'missing_drill', 'wrong_drill'])
def test_detail_not_aggregate_proves_days_and_exact_drills(tmp_path, corruption):
    *_, evidence = activation_fixture(tmp_path)
    changes = {}
    if corruption == 'duplicate':
        changes['days'] = (evidence.days[0],)*20
    elif corruption in {'ineligible', 'nonterminal', 'synthetic'}:
        field, value = {'ineligible': ('eligible', False), 'nonterminal': ('terminal', False),
                        'synthetic': ('evidence_class', 'SYNTHETIC')}[corruption]
        changes['days'] = (evidence.days[0].model_copy(update={field: value}), *evidence.days[1:])
    elif corruption == 'missing_drill':
        changes['drills'] = evidence.drills[:-1]
    else:
        changes['drills'] = (evidence.drills[0],)*len(evidence.drills)
    assert not verdict(tmp_path, evidence=changes).allowed


@pytest.mark.parametrize('change', [{'healthy': False}, {'safety_latched': True},
    {'frozen_tickers': ('000660',)}, {'expires_at': NOW-timedelta(seconds=1)},
    {'observed_at': NOW+timedelta(seconds=1), 'expires_at': NOW+timedelta(seconds=2)},
    {'source_hashes': (SourceHash(source_id='other', source_hash='f'*64),)}])
def test_current_safety_rechecked(tmp_path, change):
    assert not verdict(tmp_path, safety=change).allowed


def test_synthetic_and_injected_evidence_never_grant_production(tmp_path):
    from trading_bot.service_activation import validate_unattended_activation
    settings, receipt, reader, safety, *_ = activation_fixture(tmp_path)
    for item in (receipt, receipt.model_copy(update={'evidence_class':'KIS_OBSERVED'})):
        result = validate_unattended_activation(settings, item, reader, lambda *a: safety, now=NOW)
        assert not result.allowed and result.authority == 'DENIED'


def test_missing_or_inaccessible_evidence_fail_closed(tmp_path):
    from trading_bot.service_activation import validate_unattended_activation
    settings, receipt, reader, safety, authority, _ = activation_fixture(tmp_path)
    assert not validate_unattended_activation(settings, None, reader, lambda *a: safety, now=NOW).allowed
    reader.read = lambda receipt: (_ for _ in ()).throw(RuntimeError('secret'))
    result = validate_unattended_activation(settings, receipt, reader, lambda *a: safety,
        now=NOW, offline_authority=authority)
    assert not result.allowed and result.reason_codes == ('SAVED_EVIDENCE_UNKNOWN',)
    assert 'secret' not in result.model_dump_json()


def test_approval_actor_and_links_are_not_boolean_authority(tmp_path):
    _, receipt, *_ = activation_fixture(tmp_path)
    wrong = receipt.checkpoint_approvals[0].model_copy(update={'actor':'foreign-owner'})
    assert not verdict(tmp_path, receipt={'checkpoint_approvals':(wrong,receipt.checkpoint_approvals[1])}).allowed
    wrong = receipt.checkpoint_approvals[0].model_copy(update={'evidence_ids':(receipt.evidence_ids[0],)})
    assert not verdict(tmp_path, receipt={'checkpoint_approvals':(wrong,receipt.checkpoint_approvals[1])}).allowed


def test_real_target_rejected_at_schema_and_runtime(tmp_path):
    from trading_bot.service_activation import validate_unattended_activation
    from trading_bot.service_models import ServiceScope
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ServiceScope(account_scope_hash='a'*64, execution_target='real')
    settings, receipt, reader, safety, authority, _ = activation_fixture(tmp_path)
    object.__setattr__(settings, 'execution_target', 'real')
    result = validate_unattended_activation(settings, receipt, reader, lambda *a: safety,
        now=NOW, offline_authority=authority)
    assert not result.allowed and 'REAL_TARGET_FORBIDDEN' in result.reason_codes
