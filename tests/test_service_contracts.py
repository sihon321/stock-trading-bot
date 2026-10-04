"""Offline Phase 15 contract proofs; no production capability or evidence."""
from datetime import date, datetime, timedelta, timezone
import hashlib
import importlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

NOW = datetime(2026, 10, 5, 0, 0, tzinfo=timezone.utc)
DAY = date(2026, 10, 5)
HASH = 'a' * 64


def models():
    return importlib.import_module('trading_bot.service_models')


def scope():
    return models().ServiceScope(account_scope_hash=HASH, execution_target='mock')


def session(**changes):
    values = dict(trading_date_kst=DAY, source_id='reviewed-session', source_hash=HASH,
        source_url='https://kind.krx.co.kr/reviewed', notice_id='notice-1',
        reviewed_at=NOW, reviewer='owner', observed_at=NOW, effective_at=NOW,
        eligibility='ELIGIBLE', continuous_open=NOW, continuous_close=NOW + timedelta(hours=6, minutes=30))
    return models().SessionEvidence(**(values | changes))


def expectation_values():
    return dict(expectation_id='expected-daily', scope=scope(), trading_date_kst=DAY,
        kind='DAILY', state='EXPECTED', producer_kind='OBSERVER_DERIVED',
        source_id='observer-registration', source_hash=HASH, observed_at=NOW,
        effective_at=NOW, eligibility='ELIGIBLE', continuous_open=NOW,
        continuous_close=NOW + timedelta(hours=6, minutes=30),
        due_at=NOW + timedelta(minutes=10), deadline_at=NOW + timedelta(minutes=20),
        config_hash=HASH, config_effective_at=NOW, login_source_id='gui-probe',
        login_effective_at=NOW, session_source_id='reviewed-session',
        session_source_hash=HASH, control_revision=0, controls_source_id='control-0',
        controls_observed_at=NOW, controls_effective_at=NOW, reason_code='ELIGIBLE')


def test_logical_identity_is_restart_stable_and_scope_date_kind_specific():
    m = models()
    job = m.LogicalJobKey(scope=scope(), trading_date_kst=DAY, kind='DAILY')
    assert job == m.LogicalJobKey.model_validate_json(job.model_dump_json())
    assert job.logical_id == m.LogicalJobKey.model_validate_json(job.model_dump_json()).logical_id
    for changes in ({'kind': 'RISK'}, {'trading_date_kst': DAY + timedelta(days=1)},
                    {'scope': m.ServiceScope(account_scope_hash='b' * 64, execution_target='mock')}):
        assert m.LogicalJobKey(**(job.model_dump() | changes)).logical_id != job.logical_id
    with pytest.raises(ValidationError):
        m.LogicalJobKey(**(job.model_dump() | {'generation_id': 'restart'}))


def test_control_is_global_narrow_frozen_and_attributable():
    m = models()
    installation = m.InstallationScope(registered_scopes=(scope(),))
    values = dict(request_id='request-1', actor='owner', requested_at=NOW,
                  scope=installation, action='KILL', expected_revision=0)
    request = m.ControlRequest(**values)
    with pytest.raises(ValidationError):
        request.action = 'RESUME'
    for forbidden in ('policy', 'approval', 'job', 'path', 'broker', 'trading_date_kst'):
        with pytest.raises(ValidationError) as exc:
            m.ControlRequest(**values, **{forbidden: 'credential-never-show'})
        assert 'credential-never-show' not in str(exc.value)
    with pytest.raises(ValidationError):
        m.ControlRequest(**(values | {'requested_at': NOW.replace(tzinfo=None)}))
    with pytest.raises(ValidationError):
        m.InstallationScope(registered_scopes=(scope(), scope()))
    applied = m.AppliedControl(revision=1, mode='KILLED', request_id=request.request_id,
                              applied_at=NOW, safety_evidence_ids=('gate-blocked',))
    assert applied.request_id == request.request_id
    assert 'trading_date_kst' not in applied.model_fields


def test_exact_session_dates_and_bounds_and_unknown():
    assert session().eligibility == 'ELIGIBLE'
    assert session(eligibility='UNKNOWN', continuous_open=None, continuous_close=None).eligibility == 'UNKNOWN'
    for changes in ({'observed_at': NOW.replace(tzinfo=None)},
                    {'continuous_close': NOW - timedelta(seconds=1)},
                    {'continuous_open': NOW + timedelta(days=1)},
                    {'eligibility': 'ELIGIBLE', 'continuous_open': None}):
        with pytest.raises(ValidationError):
            session(**changes)


def test_expectations_require_all_provenance_and_preserve_producer():
    m, values = models(), expectation_values()
    expected = m.ServiceExpectation(**values)
    assert expected.producer_kind == 'OBSERVER_DERIVED'
    for key in ('config_hash', 'config_effective_at', 'login_source_id', 'login_effective_at',
                'session_source_hash', 'controls_observed_at', 'source_id', 'effective_at'):
        missing = dict(values)
        missing.pop(key)
        with pytest.raises(ValidationError):
            m.ServiceExpectation(**missing)
    for key in ('observed_at', 'effective_at', 'config_effective_at', 'login_effective_at',
                'controls_observed_at', 'controls_effective_at', 'due_at', 'deadline_at'):
        with pytest.raises(ValidationError):
            m.ServiceExpectation(**(values | {key: NOW.replace(tzinfo=None)}))
    with pytest.raises(ValidationError):
        m.ServiceExpectation(**(values | {'producer_kind': 'SCHEDULER_ASSUMED'}))
    login = m.OwnerLoginEvidence(owner_uid=1, gui_session_id='gui-1', source_id='gui-probe',
        observed_at=NOW, effective_at=NOW, state='CONFIRMED')
    installation = m.InstallationScope(registered_scopes=(scope(),))
    controls = m.AppliedControl(revision=0, mode='RUNNING', request_id=None,
                               applied_at=NOW, safety_evidence_ids=())
    inputs = dict(registered_scopes=installation.registered_scopes, service_enabled=True,
        mode='KIS_MOCK', config_hash=HASH, config_effective_at=NOW, login_evidence=login,
        session=session(), effective_controls=controls, controls_source_id='control-0',
        controls_observed_at=NOW, controls_effective_at=NOW, control_scope=installation)
    assert m.ExpectationInputs(**inputs).session.trading_date_kst == DAY
    other = m.ServiceScope(account_scope_hash='b' * 64, execution_target='mock')
    with pytest.raises(ValidationError):
        m.ExpectationInputs(**(inputs | {'registered_scopes': (other,)}))


def test_dispatch_pins_bytes_and_suppression_never_grants_replay():
    m = models()
    raw = b'frozen prompt'
    values = dict(prompt_bytes=raw, prompt_hash=hashlib.sha256(raw).hexdigest(),
        system_prompt='strict signal', schema_hash=HASH, provider='openai', model='test-model',
        temperature=0, prompt_version='v1')
    envelope = m.DailyDispatchEnvelope(**values)
    assert envelope.envelope_hash == m.DailyDispatchEnvelope(**values).envelope_hash
    assert raw.decode() not in repr(envelope)
    with pytest.raises(ValidationError):
        m.DailyDispatchEnvelope(**(values | {'prompt_hash': HASH}))
    admission = m.ProviderCallAdmission(dispatch_id='dispatch-1', evaluation_id='evaluation-1',
        scope=scope(), trading_date_kst=DAY, envelope_hash=envelope.envelope_hash,
        state='SUPPRESSED_NO_CALL', reason_code='PAUSED', control_revision=1,
        session_source_id='reviewed-session', observed_at=NOW, invocation_started_at=None)
    assert admission.restores_dispatch_authority is False
    with pytest.raises(ValidationError):
        admission.state = 'PREPARED'
    with pytest.raises(ValidationError):
        m.ProviderCallAdmission(**(admission.model_dump() | {'invocation_started_at': NOW}))


def test_receipt_approvals_have_exact_checkpoint_names_and_immutable_sources():
    m = models()
    values = dict(receipt_id='receipt-1', evidence_class='SYNTHETIC', scope=scope(),
        campaign_id='campaign-1', profile_fingerprint=HASH,
        source_hashes=(m.SourceHash(source_id='report', source_hash=HASH),),
        checkpoint_approvals=(m.CheckpointApproval(checkpoint='09-08 task 1', actor='owner',
            approved_at=NOW, evidence_ids=('synthetic-drill',)),),
        evidence_ids=('synthetic-drill',), approved_at=NOW)
    receipt = m.AcceptanceReceipt(**values)
    assert receipt.has_both_checkpoint_approvals is False
    with pytest.raises(ValidationError):
        m.CheckpointApproval(checkpoint='09-08', actor='owner', approved_at=NOW, evidence_ids=('drill',))
    with pytest.raises(ValidationError):
        receipt.source_hashes[0].source_hash = 'b' * 64
    assert m.AcceptanceReceipt.model_validate_json(receipt.model_dump_json()) == receipt


def settings_class():
    return importlib.import_module('trading_bot.service_config').ServiceSettings


def test_defaults_and_every_fixed_timeout():
    cls = settings_class()
    defaults = cls()
    assert defaults.service_enabled is False and defaults.mode == 'DISABLED'
    assert defaults.execution_target == 'mock'
    timings = dict(risk_interval_seconds=60, provider_timeout_seconds=90,
        account_work_timeout_seconds=45, post_timeout_seconds=10, control_lock_timeout_seconds=1,
        provider_admission_timeout_seconds=1, restart_window_seconds=600,
        max_automatic_restarts=3, shutdown_timeout_seconds=30, worker_stale_seconds=120)
    for name, value in timings.items():
        assert getattr(defaults, name) == value
        for wrong in (value - 1, value + 1, True):
            with pytest.raises(ValidationError):
                cls(**{name: wrong})
    for changes in ({'mode': 'REAL'}, {'execution_target': 'real'}, {'service_enabled': True},
                    {'mode': 'KIS_MOCK'}, {'app_secret': 'credential-never-show'}):
        with pytest.raises(ValidationError) as exc:
            cls(**changes)
        assert 'credential-never-show' not in str(exc.value)


def test_settings_ignore_dotenv_and_file_secrets(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / '.env').write_text('BOT_SERVICE_MODE=KIS_MOCK\nBOT_SERVICE_SERVICE_ENABLED=true\n')
    secrets = tmp_path / 'secrets'
    secrets.mkdir()
    (secrets / 'BOT_SERVICE_MODE').write_text('KIS_MOCK')
    assert settings_class()(_env_file=tmp_path / '.env', _secrets_dir=secrets).mode == 'DISABLED'
    monkeypatch.setenv('BOT_SERVICE_RISK_INTERVAL_SECONDS', '59')
    with pytest.raises(ValidationError):
        settings_class()()


def test_topology_rejects_links_overlap_and_unprotected_config(tmp_path):
    cls = settings_class()
    target = tmp_path / 'source.json'
    target.write_text('{}')
    target.chmod(0o600)
    link = tmp_path / 'link.json'
    link.symlink_to(target)
    for path in (link, tmp_path / '..' / 'unsafe'):
        with pytest.raises(ValidationError):
            cls(trading_config_path=path)
    with pytest.raises(ValidationError):
        cls(service_db_path=tmp_path / 'journal' / 'service.db',
            trading_journal_paths=(tmp_path / 'journal' / 'audit.db',))
    with pytest.raises(ValidationError):
        cls(service_db_path=tmp_path / 'artifacts' / 'service.db', artifact_roots=(tmp_path / 'artifacts',))
    target.chmod(0o644)
    with pytest.raises(ValidationError):
        cls(trading_config_path=target)


def test_explicit_protected_registration_loads_without_trading_settings(tmp_path):
    module = importlib.import_module('trading_bot.service_config')
    config = tmp_path / 'service.json'
    config.write_text(json.dumps({'service_enabled': False, 'mode': 'DISABLED'}))
    config.chmod(0o600)
    assert module.load_service_settings(config).mode == 'DISABLED'
    config.chmod(0o644)
    with pytest.raises(ValueError):
        module.load_service_settings(config)


def test_service_imports_do_not_acquire_trading_capabilities():
    import subprocess
    import sys
    code = "import sys; import trading_bot.service_config; assert not any(n in sys.modules for n in ('trading_bot.config', 'trading_bot.cli', 'trading_bot.kis_broker', 'trading_bot.llm_provider', 'dotenv'))"
    # pydantic-settings imports dotenv internally, so enforce no dotenv *loads* below.
    code = code.replace(", 'dotenv'", '')
    result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

