"""Offline transport-entry proof using the real protected operational stores."""
from datetime import timedelta
from types import SimpleNamespace
import hashlib
import json
import threading

import httpx
import pytest

from tests.service_fixtures import FakeServiceClock, NOW, SCOPE, TempServiceTopology, session_evidence
from trading_bot.service_models import DailyDispatchEnvelope, LogicalJobKey, ProviderCallAdmission
from trading_bot.trade_signal import TradeSignal


def envelope(provider='openai'):
    prompt = b'first saved input: 005930'
    return DailyDispatchEnvelope(prompt_bytes=prompt, prompt_hash=hashlib.sha256(prompt).hexdigest(),
        system_prompt='first trusted system', schema_hash=hashlib.sha256(json.dumps(
            TradeSignal.model_json_schema(), sort_keys=True, separators=(',', ':')).encode()).hexdigest(),
        provider=provider, model='saved-model', temperature=.2, prompt_version='saved-v1')


def admitted(tmp_path, *, clock=None, session_reader=None):
    from trading_bot.control_store import ControlStore
    from trading_bot.service_store import ServiceJournal
    from trading_bot.llm_provider import ProviderDispatchAdmission
    clock = clock or FakeServiceClock(NOW + timedelta(minutes=10))
    settings = TempServiceTopology(tmp_path).registration()
    controls = ControlStore(settings, clock=clock)
    controls.initialize()
    # Initial state is conservatively PAUSED. Explicit offline application only.
    from trading_bot.service_leader import ServiceLeader
    journal = ServiceJournal(settings, clock=clock); journal.initialize()
    leader = ServiceLeader(settings, journal=journal)
    leader.__enter__()
    controls.service_capability(leader).apply_pending(safety_check=lambda: ('proof1',))
    # Use normal control request/application APIs to grant RUNNING in this fixture.
    from trading_bot.service_models import ControlRequest
    request = ControlRequest(request_id='resume1', actor='tester', requested_at=clock(),
        scope=controls.scope, action='RESUME', expected_revision=0)
    assert controls.request_writer(actor='tester').accept(request).status == 'ACCEPTED'
    controls.service_capability(leader).apply_pending(safety_check=lambda: ('proof1',))
    leader.__exit__(None, None, None)
    key = LogicalJobKey(scope=SCOPE, trading_date_kst=NOW.date(), kind='DAILY')
    journal.claim_job(key, due_at=clock(), dispatch_deadline_at=NOW+timedelta(minutes=20), owner_generation='fixture')
    journal.commit_universe(key.logical_id, ('005930',))
    env = envelope()
    row = dict(dispatch_id='dispatch1', evaluation_id='eval1', account_scope_hash=SCOPE.account_scope_hash,
        execution_target='mock', trading_date_kst=NOW.date().isoformat(), envelope_hash=env.envelope_hash,
        dispatch_state='DISPATCHED', dispatched_at=clock().isoformat())
    writer = journal.prepare_provider_admission(ProviderCallAdmission(dispatch_id='dispatch1', evaluation_id='eval1',
        scope=SCOPE, trading_date_kst=NOW.date(), envelope_hash=env.envelope_hash, state='PREPARED',
        reason_code='READY', control_revision=1, session_source_id=session_evidence().source_id,
        observed_at=clock()), consumed_dispatch=row)
    admission = ProviderDispatchAdmission(dispatch_id='dispatch1', scope=SCOPE,
        trading_date_kst=NOW.date(), envelope_hash=env.envelope_hash,
        session_source_id=session_evidence().source_id, control_reader=controls.reader(),
        session_reader=session_reader or (lambda day: session_evidence(day=day)), clock=clock,
        writer=writer, lock_factory=controls.admission_lock)
    return admission, journal, controls, clock


def test_admission_is_single_use_and_releases_lock_at_actual_entry(tmp_path):
    from trading_bot.llm_provider import LLMProviderError
    admission, journal, controls, clock = admitted(tmp_path)
    calls = []
    def invoke(ack):
        ack()
        # A slow response owns neither the admission flock nor a transaction.
        with controls.admission_lock(): calls.append('entered')
        return 'result'
    assert admission.admit_at_transport_entry(invoke) == 'result'
    assert journal.load_provider_admission('dispatch1').state == 'IN_FLIGHT'
    with pytest.raises(LLMProviderError): admission.admit_at_transport_entry(invoke)
    assert calls == ['entered']


@pytest.mark.parametrize('boundary', ['cutoff', 'date', 'session', 'pause', 'kill'])
def test_changed_current_facts_suppress_consumed_dispatch_without_call(tmp_path, boundary):
    from trading_bot.llm_provider import LLMProviderError
    admission, journal, controls, clock = admitted(tmp_path)
    if boundary == 'cutoff': clock.advance(600)
    if boundary == 'date': clock.advance(86400)
    if boundary == 'session': admission.session_reader = lambda day: session_evidence('unknown', day)
    if boundary in ('pause', 'kill'):
        from trading_bot.service_models import ControlRequest
        controls.request_writer(actor='tester').accept(ControlRequest(request_id='stop', actor='tester',
            requested_at=clock(), scope=controls.scope, action=boundary.upper(), expected_revision=1))
    calls=[]
    with pytest.raises(LLMProviderError): admission.admit_at_transport_entry(lambda ack: calls.append('BAD'))
    result=journal.load_provider_admission('dispatch1')
    assert calls == [] and result.state == 'SUPPRESSED_NO_CALL'
    assert result.invocation_started_at is None


def test_gap_inside_transport_entry_refreshes_cutoff(tmp_path):
    from trading_bot.llm_provider import LLMProviderError
    admission, journal, controls, clock = admitted(tmp_path)
    calls=[]
    def invoke(ack):
        clock.advance(600)
        ack()
        calls.append('BAD')
    with pytest.raises(LLMProviderError): admission.admit_at_transport_entry(invoke)
    assert calls == []
    assert journal.load_provider_admission('dispatch1').state == 'SUPPRESSED_NO_CALL'


@pytest.mark.parametrize('provider', ['openai', 'anthropic'])
@pytest.mark.parametrize('failure', ['timeout', 'reset', 'parse'])
def test_sdk_single_shot_frozen_request_and_nested_retries(tmp_path, monkeypatch, provider, failure):
    from conftest import make_settings
    from trading_bot.config import LLMProviderName
    from trading_bot.llm_provider import build_single_shot_llm_provider, LLMProviderError
    admission, journal, controls, clock = admitted(tmp_path)
    env=envelope(provider); admission.envelope_hash=env.envelope_hash
    # Provider identity changes need a matching committed handoff: hash on fixture
    # differs for Anthropic; this test uses a verified transport admission double.
    class Entry:
        def admit_at_transport_entry(self, call): return call(lambda: None)
    attempts=[]; constructors=[]
    def transport(request):
        attempts.append(json.loads(request.content))
        if failure == 'timeout': raise httpx.ReadTimeout('sanitized', request=request)
        if failure == 'reset': raise httpx.ConnectError('sanitized', request=request)
        return httpx.Response(200, json={'bad':'response'})
    import openai, anthropic
    actual = openai.OpenAI if provider == 'openai' else anthropic.Anthropic
    def constructor(**kw): constructors.append(kw.copy()); return actual(**kw)
    monkeypatch.setattr(openai if provider=='openai' else anthropic,
        'OpenAI' if provider=='openai' else 'Anthropic', constructor)
    settings=make_settings(llm_provider=LLMProviderName.OPENAI if provider=='openai' else LLMProviderName.CLAUDE)
    adapter=build_single_shot_llm_provider(settings, transport=httpx.MockTransport(transport))
    with pytest.raises(LLMProviderError): adapter.generate_signal_from_envelope(env, Entry())
    assert len(attempts)==1
    assert constructors[0]['max_retries']==0 and constructors[0]['timeout']==90
    request=attempts[0]
    assert request['model']=='saved-model'
    assert env.prompt_bytes.decode() in str(request['messages'])
    assert env.system_prompt in str(request)
