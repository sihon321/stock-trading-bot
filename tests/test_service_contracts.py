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
    assert 'trading_date_kst' not in type(applied).model_fields


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
    assert m.DailyDispatchEnvelope.model_validate_json(envelope.model_dump_json()) == envelope
    with pytest.raises(ValidationError):
        m.DailyDispatchEnvelope(**(values | {'prompt_hash': HASH}))
    admission = m.ProviderCallAdmission(dispatch_id='dispatch-1', evaluation_id='evaluation-1',
        scope=scope(), trading_date_kst=DAY, envelope_hash=envelope.envelope_hash,
        state='SUPPRESSED_NO_CALL', reason_code='PAUSED', control_revision=1,
        session_source_id='reviewed-session', observed_at=NOW, invocation_started_at=None)
    assert admission.restores_dispatch_authority is False
    assert admission.model_copy(update={'state': 'PREPARED'}).restores_dispatch_authority is False
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


def test_state_allowlists_numeric_bounds_and_hidden_invalid_inputs():
    m = models()
    assert {v.value for v in m.ServiceJobState} == {
        'DUE', 'CLAIMED', 'RUNNING', 'COMPLETED', 'PARTIAL', 'MISSED', 'BLOCKED', 'UNKNOWN'}
    assert {v.value for v in m.ProviderAdmissionState} == {
        'PREPARED', 'IN_FLIGHT', 'SUPPRESSED_NO_CALL', 'UNKNOWN', 'FINISHED'}
    for enum in (m.ServiceJobState, m.ServiceMode, m.ControlMode, m.ControlAction,
                 m.OwnerLoginState, m.SessionEligibility, m.ProviderAdmissionState):
        with pytest.raises(ValueError):
            enum('INVALID')
    for value in (-1, True, 1.5):
        with pytest.raises(ValidationError):
            m.AppliedControl(revision=value, mode='RUNNING', request_id=None,
                             applied_at=NOW, safety_evidence_ids=())
    with pytest.raises(ValidationError) as exc:
        m.ServiceScope(account_scope_hash='credential-never-show', execution_target='mock')
    assert 'credential-never-show' not in str(exc.value)
    with pytest.raises(ValidationError):
        scope().model_copy(update={'execution_target': 'real'})


def test_unconfirmed_login_and_expectation_remain_explicit():
    m = models()
    for state in ('ABSENT', 'UNKNOWN'):
        evidence = m.OwnerLoginEvidence(owner_uid=1, gui_session_id=None, source_id='probe',
            observed_at=NOW, effective_at=NOW, state=state)
        assert evidence.state == state
    with pytest.raises(ValidationError):
        m.OwnerLoginEvidence(owner_uid=1, gui_session_id=None, source_id='probe',
            observed_at=NOW, effective_at=NOW, state='CONFIRMED')
    values = expectation_values() | dict(state='UNKNOWN', eligibility='UNKNOWN',
        continuous_open=None, continuous_close=None, due_at=None, deadline_at=None,
        reason_code='SESSION_UNKNOWN')
    assert m.ServiceExpectation(**values).state == 'UNKNOWN'


def test_topology_rejects_hardlinks_and_aliases_between_owners(tmp_path):
    import os
    file = tmp_path / 'private.json'
    file.write_text('{}')
    file.chmod(0o600)
    alias = tmp_path / 'alias.json'
    os.link(file, alias)
    with pytest.raises(ValidationError):
        settings_class()(session_evidence_path=alias)
    with pytest.raises(ValidationError):
        settings_class()(service_db_path=tmp_path / 'ops' / 'service.db',
                         control_db_path=tmp_path / 'ops' / 'control.db')


def test_settings_never_read_dotenv_even_when_explicit_override_supplied(tmp_path, monkeypatch):
    import dotenv
    import dotenv.main
    def denied(*args, **kwargs):
        raise AssertionError('dotenv loading is forbidden')
    monkeypatch.setattr(dotenv, 'load_dotenv', denied)
    monkeypatch.setattr(dotenv.main, 'dotenv_values', denied)
    path = tmp_path / '.env'
    path.write_text('BOT_SERVICE_MODE=KIS_MOCK')
    assert settings_class()(_env_file=path).mode == 'DISABLED'


def fixtures():
    return importlib.import_module('service_fixtures')


def test_fixture_clock_rollover_and_sleep_are_independent():
    f = fixtures()
    clock = f.FakeServiceClock(datetime(2026, 10, 5, 14, 59, tzinfo=timezone.utc))
    old = clock.monotonic()
    assert clock.now_kst().date() == DAY
    clock.advance(wall_seconds=120, monotonic_seconds=0)
    assert clock.now_kst().date() == DAY + timedelta(days=1)
    assert clock.monotonic() == old
    clock.advance(wall_seconds=-60, monotonic_seconds=30)
    assert clock.monotonic() == old + 30
    assert len(f.observer_only_midnight_progression()) == 3
    with pytest.raises(ValueError):
        f.FakeServiceClock(NOW.replace(tzinfo=None))


def test_fixture_topology_registration_and_synthetic_approvals(tmp_path):
    f = fixtures()
    topology = f.TempServiceTopology(tmp_path)
    stores = [topology.audit_db_path, topology.service_db_path, topology.control_db_path,
              topology.web_db_path, topology.soak_db_path, topology.controller_db_path]
    assert len(set(stores)) == 6
    assert all(p.is_relative_to(tmp_path) and not p.exists() for p in stores)
    assert topology.registration(enabled=False).mode == 'DISABLED'
    enabled = topology.registration(enabled=True)
    assert enabled.mode == 'KIS_MOCK' and enabled.execution_target == 'mock'
    assert all(p.stat().st_mode & 0o077 == 0 for p in
        (enabled.trading_config_path, enabled.acceptance_receipt_path,
         enabled.session_evidence_path, enabled.observer_config_path))
    bundle = f.ApprovalBundle.synthetic()
    assert bundle.receipt.evidence_class == 'SYNTHETIC'
    assert bundle.receipt.has_both_checkpoint_approvals
    with pytest.raises(ValueError):
        f.TempServiceTopology(Path.cwd() / 'data')


def test_fixture_sessions_login_and_source_failures():
    f = fixtures()
    assert f.session_evidence('normal').continuous_open.astimezone(models().KST).hour == 9
    assert f.session_evidence('delayed').continuous_open.astimezone(models().KST).hour == 10
    assert f.session_evidence('holiday').eligibility == 'HOLIDAY'
    assert f.session_evidence('unknown').eligibility == 'UNKNOWN'
    for state in ('CONFIRMED', 'ABSENT', 'UNKNOWN'):
        assert f.FakeOwnerLoginProbe(state).observe_owner_gui().state == state
    reader = f.FakeSourceReader({'config': 1, 'session': 2}, failures=('session',))
    assert reader.read('config') == 1
    with pytest.raises(f.FixtureSourceUnavailable):
        reader.read('session')
    assert reader.calls == ('config', 'session')
    pending = f.healthy_pending_critical()
    assert pending.incident.severity == 'CRITICAL' and pending.incident.acknowledged_at is None
    assert pending.outbox.state == 'PENDING' and pending.next_reminder_at > NOW


def test_fixture_fakes_are_single_shot_and_append_only(tmp_path):
    f = fixtures()
    counter = f.AppendOnlyCallCounter(tmp_path / 'calls.jsonl')
    provider = f.FakeSingleShotProvider(counter)
    assert provider.generate_signal('saved-input').decision == 'HOLD'
    assert len(counter.calls) == 1
    with pytest.raises(f.FixtureAlreadyCalled):
        provider.generate_signal('saved-input')
    broker = f.FakeBroker(counter)
    broker.place_order('synthetic-order')
    notifier = f.FakeNotificationTransport(counter)
    assert notifier.send('synthetic-notification')
    assert tuple(c['kind'] for c in counter.calls) == ('PROVIDER', 'BROKER', 'NOTIFICATION')
    with pytest.raises(AttributeError):
        counter.calls = ()


@pytest.mark.parametrize('barrier', [
    'INPUT_COMMITTED', 'DISPATCHED', 'ACCOUNT_RECONCILED', 'ACCOUNT_RELEASED',
    'CHILD_STARTED', 'PROVIDER_ADMISSION_PREPARED', 'BEFORE_TRANSPORT_ENTRY',
    'TRANSPORT_ENTERED', 'RESPONSE_RECEIVED', 'SIGNAL_FINALIZED',
    'SUBMISSION_ATTEMPTED', 'POST_RETURNED'])
def test_fixture_child_crash_barriers_leave_durable_facts_and_no_process(tmp_path, barrier):
    f = fixtures()
    with f.SpawnedCrashBarrier(tmp_path, barrier) as child:
        assert child.reached.wait(5)
        assert child.checkpoints[-1] == barrier
        assert child.process.is_alive()
        if barrier in {'INPUT_COMMITTED', 'DISPATCHED', 'CHILD_STARTED',
                       'PROVIDER_ADMISSION_PREPARED', 'BEFORE_TRANSPORT_ENTRY'}:
            assert child.counter.calls == ()
    assert not child.process.is_alive()


def test_fixture_transport_acknowledges_entry_without_waiting_for_response(tmp_path):
    f = fixtures()
    with f.SpawnedCrashBarrier(tmp_path, 'TRANSPORT_ENTERED') as child:
        assert child.entered.wait(5)
        assert child.reached.wait(5)
        assert len(child.counter.calls) == 1
        assert 'RESPONSE_RECEIVED' not in child.checkpoints
        assert child.admission_lock.acquire(timeout=1)
        child.admission_lock.release()
        child.release.set()
        child.process.join(5)
        assert child.process.exitcode == 0
        assert 'RESPONSE_RECEIVED' in child.checkpoints


def test_fixture_capability_tripwires_block_real_clients_and_processes():
    import socket
    import subprocess
    import httpx
    import openai
    import anthropic
    f = fixtures()
    with f.NoExternalCapabilities() as guard:
        attempts = (lambda: socket.create_connection(('127.0.0.1', 9)),
                    lambda: httpx.get('https://example.com'),
                    lambda: openai.OpenAI(api_key='synthetic'),
                    lambda: anthropic.Anthropic(api_key='synthetic'),
                    lambda: subprocess.run(['launchctl', 'list']),
                    lambda: subprocess.run(['codex', 'exec', 'test']))
        for attempt in attempts:
            with pytest.raises(f.ExternalCapabilityForbidden):
                attempt()
        assert len(guard.attempts) == len(attempts)
