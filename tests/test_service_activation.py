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
            evidence_ids=(ids[2], *ids[22:]) if i == 1 else ids) for i in (1, 2))})
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


def owned_fixture(tmp_path):
    """Manufactured journals under explicit offline authority, never real approval."""
    import json
    from trading_bot import sqlite_audit, soak_store
    from trading_bot.audit_models import RunKind, RunStatus
    from trading_bot.portfolio import canonical_account_scope_hash
    from trading_bot.service_activation import ReadOnlyAcceptanceEvidenceReader, OfflineActivationAuthority
    from trading_bot.service_models import ServiceScope
    from trading_bot.soak_controller import (connect_controller, prepare_drill,
        commit_drill_contract, append_controller_observation, finalize_drill)
    from trading_bot.soak_drills import FAULT_REGISTRY, DRILL_POLICY_VERSION
    topology = TempServiceTopology(tmp_path)
    settings = topology.registration(enabled=True)
    scope = ServiceScope(account_scope_hash=canonical_account_scope_hash('mock','1234'), execution_target='mock')
    settings = settings.model_copy(update={'registered_scopes':(scope,)})
    profile = {'schema_version':'kis-mock-compat-v1', 'state':'ACCEPTED',
        'evidence_class':'KIS_OBSERVED', 'profile_version':'official-example-v1',
        'facts':{}, 'daily':{'rows':[], 'completeness':'COMPLETE','page_count':1},
        'balance':{'rows':[], 'summary':{}, 'completeness':'COMPLETE','page_count':1}}
    profile_path = tmp_path/'config'/'profile.json'
    profile_path.write_text(json.dumps(profile)); profile_path.chmod(0o600)
    primary = sqlite_audit.connect(topology.audit_db_path)
    soak = soak_store.connect_soak_store(topology.soak_db_path)
    controller = connect_controller(topology.controller_db_path,topology.audit_db_path,topology.soak_db_path)
    soak_store.create_campaign(soak, campaign_id='synthetic-campaign',
        accepted_profile_fingerprint=soak_store.fingerprint_accepted_profile(profile),
        accepted_profile_version='official-example-v1',field_contract_version='kis-mock-compat-v1',
        ambiguity_policy_version='ambiguity-v1',ambiguity_window_seconds=60,
        ambiguity_poll_cadence_seconds=5,ambiguity_max_observations=12)
    soak_store.append_identity_receipt(soak,receipt_id='mock-identity',campaign_id='synthetic-campaign',
        target='mock',domain_class='KIS_MOCK_VTS',account_suffix='1234',
        profile_version='official-example-v1',policy_version='mock-isolation-v1')
    for i in range(20):
        day = date(2026,9,1)+timedelta(days=i)
        sqlite_audit.start_run(primary,run_id=f'run-{i}',trading_mode='mock',dry_run=False,
            run_kind=RunKind.RUN,trading_date_kst=day.isoformat(),target='mock')
        sqlite_audit.finish_run(primary,run_id=f'run-{i}',status=RunStatus.COMPLETED)
        soak_store.designate_day(soak,campaign_id='synthetic-campaign',trading_date=day.isoformat(),
            run_id=f'run-{i}',run_kind='RUN',terminal=True,credit_state='CREDITED',detail={'verdict_code':'CREDITED'})
        for stage in ('PRE_RUN','PRE_FINALIZE'):
            soak_store.append_snapshot(soak,snapshot_id=f'{stage}-{i}',campaign_id='synthetic-campaign',
                run_id=f'run-{i}',stage=stage,accounts=({'available_cash':1000,'total_value':1000},))
    for fault, spec in FAULT_REGISTRY.items():
        drill_id=f'drill-{fault.value}'
        prepare_drill(controller,campaign_id='synthetic-campaign',drill_id=drill_id,fault=fault,
            boundary=spec.boundary,expected_containment=spec.expected_containment,
            required_observations=spec.required_observations,policy_version=DRILL_POLICY_VERSION)
        commit_drill_contract(controller,drill_id=drill_id)
        for kind in spec.required_observations:
            append_controller_observation(controller,drill_id=drill_id,observation_type=kind,
                evidence_class='CONTROLLED_INJECTION',primary_run_id='run-0',facts={'passed':True})
        finalize_drill(controller,drill_id=drill_id,requested_verdict='PASSED')
        soak_store.append_drill_link(soak,link_id=drill_id,campaign_id='synthetic-campaign',
            drill_id=drill_id,evidence_class='CONTROLLED_INJECTION',verdict='PASSED',run_id='run-0')
    soak.execute("UPDATE soak_campaigns SET state='COMPLETED' WHERE campaign_id='synthetic-campaign'")
    soak.commit()
    for conn in (primary,soak,controller):conn.close()
    reader = ReadOnlyAcceptanceEvidenceReader(settings,profile_path=profile_path,owner_actor='synthetic-owner')
    receipt = ApprovalBundle.synthetic().receipt.model_copy(update={'scope':scope})
    saved = reader.read(receipt)
    receipt=receipt.model_copy(update={'source_hashes':saved.source_hashes,
        'profile_fingerprint':saved.profile_fingerprint,'evidence_ids':saved.evidence_ids,
        'checkpoint_approvals':tuple(CheckpointApproval(checkpoint=f'09-08 task {i}',
            actor='synthetic-owner',approved_at=NOW,evidence_ids=saved.evidence_ids) for i in (1,2))})
    from trading_bot.service_activation import CurrentActivationSafety
    safety=CurrentActivationSafety(scope=scope,observed_at=NOW,expires_at=NOW+timedelta(seconds=10),
        healthy=True,safety_latched=False,frozen_tickers=(),source_hashes=saved.source_hashes[:3])
    return settings,receipt,reader,safety,OfflineActivationAuthority(tmp_path)


def test_owned_reader_reuses_exact_versions_and_never_writes(tmp_path):
    from trading_bot.service_activation import validate_unattended_activation
    settings,receipt,reader,safety,authority=owned_fixture(tmp_path)
    before={p:p.read_bytes() for p in settings.trading_journal_paths}
    result=validate_unattended_activation(settings,receipt,reader,lambda *a:safety,now=NOW,offline_authority=authority)
    assert result.allowed and result.authority=='OFFLINE_ONLY'
    assert before=={p:p.read_bytes() for p in settings.trading_journal_paths}
    assert not hasattr(reader,'clear_freeze') and not hasattr(reader,'capture_approval')


def test_owned_reader_cross_campaign_freeze_remains_blocking(tmp_path):
    from trading_bot.service_activation import validate_unattended_activation
    from trading_bot import soak_store
    settings,receipt,reader,safety,authority=owned_fixture(tmp_path)
    conn=soak_store.connect_soak_store(settings.trading_journal_paths[1])
    soak_store.create_campaign(conn,campaign_id='foreign-proof',accepted_profile_fingerprint='sha256:'+'c'*64,
        accepted_profile_version='official-example-v1',field_contract_version='kis-mock-compat-v1',
        ambiguity_policy_version='ambiguity-v1',ambiguity_window_seconds=60,ambiguity_poll_cadence_seconds=5,
        ambiguity_max_observations=12)
    soak_store.freeze_ticker(conn,freeze_id='unresolved',campaign_id='foreign-proof',ticker='000660',
        order_intent_id='unknown',freeze_kind='AMBIGUITY')
    conn.close()
    assert reader.read_freezes()==('000660',)
    result=validate_unattended_activation(settings,receipt,reader,lambda *a:safety,now=NOW,offline_authority=authority)
    assert not result.allowed and 'UNRESOLVED_FREEZE' in result.reason_codes


def test_owned_reader_changed_source_and_schema_fail_closed(tmp_path):
    from trading_bot.service_activation import validate_unattended_activation
    from trading_bot import soak_store
    settings,receipt,reader,safety,authority=owned_fixture(tmp_path)
    conn=soak_store.connect_soak_store(settings.trading_journal_paths[1])
    soak_store.append_campaign_event(conn,campaign_id=receipt.campaign_id,event_code='NEW_OBSERVATION')
    conn.close()
    result=validate_unattended_activation(settings,receipt,reader,lambda *a:safety,now=NOW,offline_authority=authority)
    assert not result.allowed and 'SOURCE_IDENTITY_MISMATCH' in result.reason_codes
    import sqlite3
    conn=sqlite3.connect(settings.trading_journal_paths[2]);conn.execute('PRAGMA user_version=99');conn.close()
    result=validate_unattended_activation(settings,receipt,reader,lambda *a:safety,now=NOW,offline_authority=authority)
    assert not result.allowed and result.reason_codes==('SAVED_EVIDENCE_UNKNOWN',)
