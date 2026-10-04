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


def admitted(tmp_path, *, clock=None, session_reader=None, env=None):
    from trading_bot.control_store import ControlStore
    from trading_bot.service_store import ServiceJournal
    from trading_bot.llm_provider import ProviderDispatchAdmission
    clock = clock or FakeServiceClock(NOW + timedelta(minutes=10))
    settings = TempServiceTopology(tmp_path).registration()
    controls = ControlStore(settings, clock=clock)
    controls.initialize(actor='tester')
    # Initial state is conservatively PAUSED. Explicit offline application only.
    from trading_bot.service_leader import ServiceLeader
    journal = ServiceJournal(settings, clock=clock); journal.initialize()
    leader = ServiceLeader(settings, journal=journal)
    leader.acquire()
    # Use normal control request/application APIs to grant RUNNING in this fixture.
    from trading_bot.service_models import ControlRequest
    request = ControlRequest(request_id='resume1', actor='tester', requested_at=clock(),
        scope=controls.scope, action='RESUME', expected_revision=0)
    assert controls.request_writer(actor='tester').append_request(request).status == 'REQUESTED'
    from trading_bot.control_runtime import ControlApplier
    from tests.test_service_controls import safety
    applier = ControlApplier(controls.service_capability(leader),
        validate_resume=lambda scope, now: safety(scope, now),
        current_safety=lambda scope, now: safety(scope, now), clock=clock)
    applier.apply_pending()
    leader.close()
    key = LogicalJobKey(scope=SCOPE, trading_date_kst=NOW.date(), kind='DAILY')
    journal.claim_job(key, due_at=clock(), dispatch_deadline_at=NOW+timedelta(minutes=20), owner_generation='fixture')
    journal.commit_universe(key.logical_id, ('005930',))
    env = env or envelope()
    row = dict(dispatch_id='dispatch1', evaluation_id='eval1', account_scope_hash=SCOPE.account_scope_hash,
        execution_target='mock', trading_date_kst=NOW.date().isoformat(), envelope_hash=env.envelope_hash,
        dispatch_state='DISPATCHED', dispatched_at=clock().isoformat())
    writer = journal.prepare_provider_admission(ProviderCallAdmission(dispatch_id='dispatch1', evaluation_id='eval1',
        scope=SCOPE, trading_date_kst=NOW.date(), envelope_hash=env.envelope_hash, state='PREPARED',
        reason_code='READY', control_revision=1, session_source_id=session_evidence().source_id,
        observed_at=clock(), invocation_started_at=None), consumed_dispatch=row)
    admission = ProviderDispatchAdmission(dispatch_id='dispatch1', scope=SCOPE,
        trading_date_kst=NOW.date(), envelope_hash=env.envelope_hash,
        session_source_id=session_evidence().source_id, control_reader=controls.reader(),
        session_reader=session_reader or (lambda day: session_evidence(day=day)), clock=clock,
        writer=writer, lock_factory=controls.admission_lock,
        session_fingerprint=hashlib.sha256(session_evidence().model_dump_json().encode()).hexdigest())
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


@pytest.mark.parametrize('boundary', ['cutoff', 'date', 'session', 'session_hash', 'pause', 'kill'])
def test_changed_current_facts_suppress_consumed_dispatch_without_call(tmp_path, boundary):
    from trading_bot.llm_provider import LLMProviderError
    admission, journal, controls, clock = admitted(tmp_path)
    if boundary == 'cutoff': clock.advance(600)
    if boundary == 'date': clock.advance(86400)
    if boundary == 'session': admission.session_reader = lambda day: session_evidence('unknown', day)
    if boundary == 'session_hash':
        admission.session_reader=lambda day:session_evidence(day=day).model_copy(update={'source_hash':'d'*64})
    if boundary in ('pause', 'kill'):
        from trading_bot.service_models import ControlRequest
        controls.request_writer(actor='tester').append_request(ControlRequest(request_id='stop', actor='tester',
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
    env=envelope(provider)
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


def test_slow_response_accepts_kill_after_entry_and_before_response(tmp_path):
    admission, journal, controls, clock=admitted(tmp_path)
    from trading_bot.service_models import ControlRequest
    def invocation(ack):
        ack()
        result=controls.request_writer(actor='tester').append_request(ControlRequest(
            request_id='kill-during-response',actor='tester',requested_at=clock(),scope=controls.scope,
            action='KILL',expected_revision=1))
        assert result.status=='REQUESTED'
        clock.advance(600)  # an entered call may complete after 09:20
        return 'late response'
    assert admission.admit_at_transport_entry(invocation)=='late response'
    assert journal.load_provider_admission('dispatch1').invocation_started_at is not None
    assert controls.reader().effective_state(SCOPE).mode=='KILLED'


@pytest.mark.parametrize('stage', ['transaction','post_commit'])
def test_persistence_guard_gap_suppresses_without_false_invocation(tmp_path, monkeypatch, stage):
    from trading_bot.llm_provider import LLMProviderError
    admission,journal,controls,clock=admitted(tmp_path)
    original=admission.check_current
    count=[0]
    def check():
        count[0]+=1
        if count[0] == (3 if stage=='transaction' else 4): clock.advance(600)
        return original()
    monkeypatch.setattr(admission,'check_current',check)
    calls=[]
    with pytest.raises(LLMProviderError): admission.admit_at_transport_entry(lambda ack: (ack(),calls.append('BAD')))
    row=journal.load_provider_admission('dispatch1')
    assert calls==[] and row.state=='SUPPRESSED_NO_CALL' and row.invocation_started_at is None


@pytest.mark.parametrize('failure',['timeout','nonzero','parse','success'])
def test_codex_one_creation_with_response_wait_outside_lock(tmp_path,failure):
    from conftest import make_settings
    from trading_bot.config import LLMProviderName
    from trading_bot.llm_provider import build_single_shot_llm_provider,LLMProviderError
    env=envelope('codex'); admission,journal,controls,clock=admitted(tmp_path,env=env)
    calls=[]
    class Child:
        returncode=1 if failure=='nonzero' else 0
        def communicate(self,timeout):
            assert timeout==90
            with controls.admission_lock(): pass
            if failure=='timeout': raise TimeoutError('no raw error')
            return ('invalid' if failure=='parse' else '{"decision":"HOLD","confidence":0.8,"reason":"saved"}','')
        def poll(self): return self.returncode
    def popen(argv,**kw): calls.append((argv,kw)); return Child()
    popen.single_shot_capability='codex-request-stream-retries-zero-v1'
    provider=build_single_shot_llm_provider(make_settings(llm_provider=LLMProviderName.CODEX_CLI),popen=popen)
    if failure=='success': assert provider.generate_signal_from_envelope(env,admission).reason=='saved'
    else:
        with pytest.raises(LLMProviderError): provider.generate_signal_from_envelope(env,admission)
    assert len(calls)==1 and 'saved-model' in calls[0][0]
    assert env.system_prompt in calls[0][0][-1] and env.prompt_bytes.decode() in calls[0][0][-1]


def test_unknown_injected_sdk_has_no_envelope_transport_authority(tmp_path):
    from conftest import FakeOpenAIClient
    from trading_bot.llm_provider import OpenAILLMProvider,LLMProviderError
    admission,journal,controls,clock=admitted(tmp_path)
    client=FakeOpenAIClient()
    provider=OpenAILLMProvider(client=client,model='current',temperature=0)
    with pytest.raises(LLMProviderError): provider.generate_signal_from_envelope(envelope(),admission)
    assert journal.load_provider_admission('dispatch1').state=='SUPPRESSED_NO_CALL'


def test_unverified_codex_config_is_not_transport_capability(tmp_path):
    from conftest import make_settings
    from trading_bot.config import LLMProviderName
    from trading_bot.llm_provider import build_single_shot_llm_provider,LLMProviderError
    env=envelope('codex'); admission,journal,controls,clock=admitted(tmp_path,env=env)
    calls=[]
    provider=build_single_shot_llm_provider(make_settings(llm_provider=LLMProviderName.CODEX_CLI),
        popen=lambda *args,**kwargs:calls.append('BAD'))
    with pytest.raises(LLMProviderError): provider.generate_signal_from_envelope(env,admission)
    assert calls==[] and journal.load_provider_admission('dispatch1').state=='SUPPRESSED_NO_CALL'
