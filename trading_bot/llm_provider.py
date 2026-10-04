"""Concrete LLM provider adapters with fail-safe signal re-validation."""

from __future__ import annotations

import json
import subprocess
import hashlib
import time
from datetime import datetime, time as wall_time
from typing import Any, Callable

import httpx

import structlog
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from trading_bot.config import LLMProviderName, Settings
from trading_bot.domain import DataContext, LLMSignal
from trading_bot.execution import (
    CycleAuditEvent,
    ExecutionAction,
    ExecutionConfig,
    ExecutionResult,
    execute_signal_cycle,
)
from trading_bot.ports import Broker, LLMProvider
from trading_bot.prompts import PROMPT_VERSION, SYSTEM_PROMPT, render_prompt
from trading_bot.risk import DailyLossState, RiskConfig
from trading_bot.signal_parser import SignalParseError, parse_signal
from trading_bot.trade_signal import TradeSignal
from trading_bot.service_models import DailyDispatchEnvelope, KST, ProviderAdmissionState


def signal_schema_hash() -> str:
    return hashlib.sha256(json.dumps(TradeSignal.model_json_schema(), sort_keys=True,
        separators=(',', ':')).encode()).hexdigest()


class TransportEntryAck:
    """Single synchronous acknowledgement; never a reusable transport permit."""
    def __init__(self, admission, lock, deadline):
        self.admission, self.lock, self.deadline = admission, lock, deadline
        self.entered = False
        self.open = True

    def __call__(self, create=None):
        if not self.open or self.entered:
            raise LLMProviderError('ENTRY_ACK_INVALID')
        self.lock.assert_owned()
        def check():
            if time.monotonic() >= self.deadline:
                raise LLMProviderError('ENTRY_BUDGET_EXCEEDED')
            return self.admission.check_current()
        self.admission.writer.enter_transport(check)
        result = create() if create is not None else None
        self.entered = True
        self.lock.__exit__(None, None, None)
        return result


class ProviderDispatchAdmission:
    """Consumed operational identity only; no trading or account capability."""
    def __init__(self, *, dispatch_id, scope, trading_date_kst, envelope_hash,
                 session_source_id, control_reader, session_reader, clock, writer, lock_factory):
        self.dispatch_id, self.scope = dispatch_id, scope
        self.trading_date_kst, self.envelope_hash = trading_date_kst, envelope_hash
        self.session_source_id = session_source_id
        self.control_reader, self.session_reader, self.clock = control_reader, session_reader, clock
        self.writer, self.lock_factory = writer, lock_factory
        self.used = False

    def check_current(self):
        now = self.clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise LLMProviderError('CLOCK_UNKNOWN')
        local = now.astimezone(KST)
        if local.date() != self.trading_date_kst or not wall_time(9, 10) <= local.time() < wall_time(9, 20):
            raise LLMProviderError('DISPATCH_EXPIRED')
        session = self.session_reader(self.trading_date_kst)
        if (session.trading_date_kst != self.trading_date_kst or session.eligibility != 'ELIGIBLE'
                or session.source_id != self.session_source_id
                or session.continuous_open is None or session.continuous_close is None
                or not session.continuous_open <= now < session.continuous_close
                or session.observed_at > now or session.reviewed_at > now or session.effective_at > now):
            raise LLMProviderError('SESSION_CHANGED')
        control = self.control_reader.effective_state(self.scope)
        if control.mode != 'RUNNING': raise LLMProviderError('CONTROL_STOPPED')
        return now, control.acceptance_revision, session.source_id

    def suppress(self, code):
        try:
            self.writer.transition_prepared('SUPPRESSED_NO_CALL', reason_code=code,
                observed_at=self.clock())
        except Exception:
            # Failed local evidence never grants transport permission; consumption stays.
            pass

    def admit_at_transport_entry(self, invocation):
        if self.used: raise LLMProviderError('DISPATCH_ALREADY_CONSUMED')
        self.used = True
        ack = None
        try:
            with self.lock_factory() as lock:
                row = self.writer.read_prepared()
                if (row.dispatch_id != self.dispatch_id or row.scope != self.scope
                        or row.trading_date_kst != self.trading_date_kst
                        or row.envelope_hash != self.envelope_hash):
                    raise LLMProviderError('HANDOFF_MISMATCH')
                self.check_current()
                ack = TransportEntryAck(self, lock, min(lock.deadline, time.monotonic() + 1))
                result = invocation(ack)
                if not ack.entered: raise LLMProviderError('ENTRY_ACK_MISSING')
                return result
        except Exception as exc:
            if ack is None or not ack.entered:
                self.suppress(str(exc) if isinstance(exc, LLMProviderError) else 'ENTRY_UNKNOWN')
            raise LLMProviderError(str(exc) if isinstance(exc, LLMProviderError) else 'ENTRY_UNKNOWN') from None
        finally:
            if ack is not None: ack.open = False


class _SingleShotTransport(httpx.BaseTransport):
    """Actual SDK transport entry, armed once for one consumed evaluation."""
    def __init__(self, inner):
        self.inner, self.admission = inner, None
        self.used = False

    def handle_request(self, request):
        if self.used or self.admission is None: raise LLMProviderError('TRANSPORT_UNARMED')
        self.used = True
        def entry(ack):
            # This is the synchronous HTTP transport invocation entry, not an
            # SDK pre-request callback. Response/network waiting follows ACK.
            ack()
            return self.inner.handle_request(request)
        return self.admission.admit_at_transport_entry(entry)

    def close(self): self.inner.close()


def _validate_envelope(provider, envelope, admission):
    try:
        envelope = DailyDispatchEnvelope.model_validate(envelope)
        expected = {'claude': 'anthropic', 'openai': 'openai', 'codex_cli': 'codex'}[provider.provider_name]
        if envelope.provider != expected or envelope.schema_hash != signal_schema_hash():
            raise ValueError('unsupported provider/schema')
        if isinstance(admission, ProviderDispatchAdmission) and envelope.envelope_hash != admission.envelope_hash:
            raise ValueError('frozen envelope mismatch')
        envelope.prompt_bytes.decode('utf-8')
        return envelope
    except Exception:
        raise LLMProviderError('ENVELOPE_INVALID') from None


def _generate_stored(provider, envelope, admission):
    envelope = _validate_envelope(provider, envelope, admission)
    transport = getattr(provider, '_single_shot_transport', None)
    if transport is None or getattr(provider._client, 'max_retries', None) != 0:
        if isinstance(admission, ProviderDispatchAdmission): admission.suppress('UNSUPPORTED_TRANSPORT')
        raise LLMProviderError('UNSUPPORTED_TRANSPORT')
    transport.admission = admission
    try:
        if envelope.provider == 'anthropic':
            response = provider._client.messages.create(model=envelope.model, temperature=envelope.temperature,
                max_tokens=1024, system=envelope.system_prompt,
                tools=[EMIT_SIGNAL_TOOL | {'input_schema': TradeSignal.model_json_schema()}],
                tool_choice={'type':'tool','name':'emit_signal'},
                messages=[{'role':'user','content':envelope.prompt_bytes.decode()}])
            if getattr(response, 'stop_reason', None) == 'refusal': raise ValueError('refusal')
            return _finalize(provider._select_tool_input(response))
        response = provider._client.chat.completions.parse(model=envelope.model, temperature=envelope.temperature,
            response_format=TradeSignal, messages=[{'role':'system','content':envelope.system_prompt},
                {'role':'user','content':envelope.prompt_bytes.decode()}])
        message = response.choices[0].message
        if message.refusal or message.parsed is None: raise ValueError('refusal')
        return _finalize(message.parsed.model_dump(mode='json'))
    except Exception as exc:
        raise LLMProviderError(type(exc).__name__.upper()) from None


class LLMProviderError(RuntimeError):
    """Raised when provider output cannot produce a safe canonical signal.

    A ``LLMProviderError`` is fail-safe: callers must treat it as HOLD /
    no-trade and never as a partially parsed or synthetic trading signal.
    """


class _TransientLLMError(Exception):
    """Internal marker for retryable transient LLM-call failures."""


# Beta header required by the Anthropic API when authenticating with an OAuth
# bearer token (auth_token) instead of an API key. Kept as a single source of
# truth so tests assert against the same value the client sends.
ANTHROPIC_OAUTH_BETA_HEADER = "oauth-2025-04-20"


# Appended to the rendered prompt for the Codex CLI provider. The CLI returns
# free-form agent text rather than a schema-guaranteed tool call, so we ask for a
# bare JSON object and re-validate it through ``parse_signal`` (fail-safe).
CODEX_JSON_INSTRUCTION = (
    "Respond with ONLY a single JSON object and nothing else: no markdown, no "
    "code fences, no commentary, no tool calls, and do not modify any files. "
    'The object must have exactly these keys: "decision" (one of "BUY", "SELL", '
    '"HOLD"), "confidence" (a number from 0.0 to 1.0), and "reason" (a short '
    "string). Example: "
    '{"decision": "HOLD", "confidence": 0.4, "reason": "no confirmed breakout"}'
)


EMIT_SIGNAL_TOOL = {
    "name": "emit_signal",
    "description": "Emit one validated trading signal for the rendered candidate.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "decision": {"type": "string", "enum": ["BUY", "SELL", "HOLD"]},
            "confidence": {"type": "number"},
            "reason": {"type": "string"},
        },
        "required": ["decision", "confidence", "reason"],
        "additionalProperties": False,
    },
}


def _finalize(raw_input_obj: dict[str, Any]) -> LLMSignal:
    raw_json = json.dumps(raw_input_obj)
    try:
        return parse_signal(raw_json).signal
    except SignalParseError as exc:
        raise LLMProviderError(f"provider output failed re-validation: {exc}") from exc


def _json_default(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "__dict__"):
        return {
            key: item
            for key, item in vars(value).items()
            if not key.startswith("_") and key != "api_key"
        }
    return repr(value)


def _serialize_response(value: Any) -> str:
    return json.dumps(value, default=_json_default)


def _last_json_object(text: str) -> str:
    """Return the last top-level ``{...}`` block in ``text`` (string-aware).

    Codex CLI output can wrap the signal in prose or code fences; this scans for
    a balanced brace span, ignoring braces inside JSON string literals, and
    returns ``""`` when none is found.
    """

    depth = 0
    start = -1
    in_str = False
    escape = False
    best = ""
    for index, char in enumerate(text):
        if in_str:
            if escape:
                escape = False
            elif char == "\\":
                escape = True
            elif char == '"':
                in_str = False
            continue
        if char == '"':
            in_str = True
        elif char == "{":
            if depth == 0:
                start = index
            depth += 1
        elif char == "}" and depth > 0:
            depth -= 1
            if depth == 0 and start != -1:
                best = text[start : index + 1]
    return best


def _extract_json_object(text: str) -> dict[str, Any]:
    """Pull a single JSON object out of CLI stdout or fail safe."""

    stripped = (text or "").strip()
    for source in (stripped, _last_json_object(stripped)):
        if not source:
            continue
        try:
            payload = json.loads(source)
        except (json.JSONDecodeError, TypeError):
            continue
        if isinstance(payload, dict):
            return payload
    raise LLMProviderError("codex CLI output did not contain a JSON object")


def _log_cycle(
    *,
    provider: str,
    model: str,
    temperature: float,
    prompt: str,
    response: str,
    outcome: str,
) -> None:
    structlog.get_logger().info(
        "llm_signal_cycle",
        provider=provider,
        model=model,
        temperature=temperature,
        prompt_version=PROMPT_VERSION,
        prompt=prompt,
        response=response,
        outcome=outcome,
    )


def _call_provider_with_retry(
    raw_call: Any,
    *,
    max_retries: int,
    retry_backoff_seconds: float,
) -> Any:
    @retry(
        reraise=True,
        stop=stop_after_attempt(max_retries),
        wait=wait_exponential(multiplier=retry_backoff_seconds),
        retry=retry_if_exception_type(_TransientLLMError),
    )
    def _attempt() -> Any:
        try:
            return raw_call()
        except Exception as exc:  # noqa: BLE001 - provider transports vary.
            raise _TransientLLMError(
                f"LLM request failed: {type(exc).__name__}"
            ) from exc

    try:
        return _attempt()
    except _TransientLLMError as exc:
        raise LLMProviderError(str(exc)) from exc


class ClaudeLLMProvider:
    """Anthropic Claude adapter using strict forced tool use."""

    provider_name = "claude"

    def generate_signal_from_envelope(self, envelope, dispatch_admission):
        return _generate_stored(self, envelope, dispatch_admission)

    def __init__(
        self,
        *,
        client: Any,
        model: str,
        temperature: float,
        max_retries: int = 3,
        retry_backoff_seconds: float = 1.0,
    ) -> None:
        self._client = client
        self._model = model
        self._temperature = float(temperature)
        self._max_retries = max(1, int(max_retries))
        self._retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))

    def __repr__(self) -> str:  # pragma: no cover - trivial redaction
        return f"ClaudeLLMProvider(provider_name={self.provider_name!r}, model={self._model!r})"

    def generate_signal(self, context: DataContext) -> LLMSignal:
        prompt = render_prompt(context)
        response_text = ""
        try:
            response = self._call_with_retry(prompt)
            response_text = _serialize_response(response)
            if getattr(response, "stop_reason", None) == "refusal":
                raise LLMProviderError("provider refused to emit a signal")

            tool_input = self._select_tool_input(response)
            signal = _finalize(dict(tool_input))
            _log_cycle(
                provider=self.provider_name,
                model=self._model,
                temperature=self._temperature,
                prompt=prompt,
                response=response_text,
                outcome=f"parsed:{signal.decision.value}",
            )
            return signal
        except LLMProviderError as exc:
            _log_cycle(
                provider=self.provider_name,
                model=self._model,
                temperature=self._temperature,
                prompt=prompt,
                response=response_text or str(exc),
                outcome=f"error:{exc}",
            )
            raise

    def _call_with_retry(self, prompt: str) -> Any:
        return _call_provider_with_retry(
            lambda: self._client.messages.create(
                model=self._model,
                max_tokens=1024,
                system=SYSTEM_PROMPT,
                tools=[EMIT_SIGNAL_TOOL],
                tool_choice={"type": "tool", "name": "emit_signal"},
                messages=[{"role": "user", "content": prompt}],
            ),
            max_retries=self._max_retries,
            retry_backoff_seconds=self._retry_backoff_seconds,
        )

    def _select_tool_input(self, response: Any) -> dict[str, Any]:
        for block in getattr(response, "content", ()) or ():
            if (
                getattr(block, "type", None) == "tool_use"
                and getattr(block, "name", None) == "emit_signal"
            ):
                tool_input = getattr(block, "input", None)
                if isinstance(tool_input, dict):
                    return tool_input
                raise LLMProviderError("emit_signal tool input was not an object")
        raise LLMProviderError("provider response missing emit_signal tool block")


class OpenAILLMProvider:
    """OpenAI adapter using chat.completions.parse structured outputs."""

    provider_name = "openai"

    def generate_signal_from_envelope(self, envelope, dispatch_admission):
        return _generate_stored(self, envelope, dispatch_admission)

    def __init__(
        self,
        *,
        client: Any,
        model: str,
        temperature: float,
        max_retries: int = 3,
        retry_backoff_seconds: float = 1.0,
    ) -> None:
        self._client = client
        self._model = model
        self._temperature = float(temperature)
        self._max_retries = max(1, int(max_retries))
        self._retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))

    def __repr__(self) -> str:  # pragma: no cover - trivial redaction
        return f"OpenAILLMProvider(provider_name={self.provider_name!r}, model={self._model!r})"

    def generate_signal(self, context: DataContext) -> LLMSignal:
        prompt = render_prompt(context)
        response_text = ""
        try:
            response = self._call_with_retry(prompt)
            response_text = _serialize_response(response)
            message = response.choices[0].message
            refusal = getattr(message, "refusal", None)
            if refusal:
                raise LLMProviderError(f"provider refused to emit a signal: {refusal}")

            parsed = getattr(message, "parsed", None)
            if parsed is None:
                raise LLMProviderError("provider returned no parsed signal")

            signal = _finalize(dict(parsed.model_dump(mode="json")))
            _log_cycle(
                provider=self.provider_name,
                model=self._model,
                temperature=self._temperature,
                prompt=prompt,
                response=response_text,
                outcome=f"parsed:{signal.decision.value}",
            )
            return signal
        except LLMProviderError as exc:
            _log_cycle(
                provider=self.provider_name,
                model=self._model,
                temperature=self._temperature,
                prompt=prompt,
                response=response_text or str(exc),
                outcome=f"error:{exc}",
            )
            raise

    def _call_with_retry(self, prompt: str) -> Any:
        return _call_provider_with_retry(
            lambda: self._client.chat.completions.parse(
                model=self._model,
                temperature=self._temperature,
                response_format=TradeSignal,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            ),
            max_retries=self._max_retries,
            retry_backoff_seconds=self._retry_backoff_seconds,
        )


class CodexCLIProvider:
    """Codex CLI adapter that shells out to ``codex exec`` via subprocess.

    Unlike the API-backed adapters, this provider runs the locally installed
    ``codex`` binary (``codex exec [args] "<prompt>"``), captures stdout, and
    extracts a strict JSON signal from it. The subprocess runner is injectable so
    tests never spawn a real process. Any transport failure (non-zero exit,
    timeout, missing binary) is retried and ultimately mapped to a fail-safe
    :class:`LLMProviderError`; unparseable output never becomes a trade.
    """

    provider_name = "codex_cli"

    def generate_signal_from_envelope(self, envelope, dispatch_admission):
        envelope = _validate_envelope(self, envelope, dispatch_admission)
        if not getattr(self, '_single_shot', False):
            dispatch_admission.suppress('UNSUPPORTED_TRANSPORT')
            raise LLMProviderError('UNSUPPORTED_TRANSPORT')
        prompt = '\n\n'.join((envelope.system_prompt, envelope.prompt_bytes.decode(), CODEX_JSON_INSTRUCTION))
        argv = [self._binary, 'exec', '--model', envelope.model,
            '-c', 'model_providers.openai.request_max_retries=0',
            '-c', 'model_providers.openai.stream_max_retries=0', prompt]
        child = None
        def enter(ack):
            nonlocal child
            # Popen itself is the local invocation boundary. No response wait
            # occurs until creation is positively established and ACK releases.
            child = ack(lambda: self._popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                stdin=subprocess.DEVNULL, text=True))
            return child
        try:
            dispatch_admission.admit_at_transport_entry(enter)
            stdout, _stderr = child.communicate(timeout=90)
            if child.returncode != 0: raise ValueError('nonzero')
            return _finalize(_extract_json_object(stdout))
        except Exception as exc:
            if child is not None and child.poll() is None:
                child.kill(); child.communicate(timeout=1)
            raise LLMProviderError(type(exc).__name__.upper()) from None

    def __init__(
        self,
        *,
        binary: str = "codex",
        model: str | None = None,
        temperature: float = 0.0,
        timeout_seconds: float = 120.0,
        extra_args: tuple[str, ...] = (),
        max_retries: int = 3,
        retry_backoff_seconds: float = 1.0,
        runner: Callable[..., Any] | None = None,
    ) -> None:
        self._binary = binary
        self._model = model
        self._temperature = float(temperature)
        self._timeout_seconds = float(timeout_seconds)
        self._extra_args = tuple(extra_args)
        self._max_retries = max(1, int(max_retries))
        self._retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))
        self._runner = runner or subprocess.run

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return (
            "CodexCLIProvider("
            f"provider_name={self.provider_name!r}, model={self._model_label!r})"
        )

    @property
    def _model_label(self) -> str:
        return self._model or f"{self._binary}:default"

    def generate_signal(self, context: DataContext) -> LLMSignal:
        prompt = self._build_prompt(context)
        response_text = ""
        try:
            response_text = self._call_with_retry(prompt)
            raw_input_obj = _extract_json_object(response_text)
            signal = _finalize(raw_input_obj)
            _log_cycle(
                provider=self.provider_name,
                model=self._model_label,
                temperature=self._temperature,
                prompt=prompt,
                response=response_text,
                outcome=f"parsed:{signal.decision.value}",
            )
            return signal
        except LLMProviderError as exc:
            _log_cycle(
                provider=self.provider_name,
                model=self._model_label,
                temperature=self._temperature,
                prompt=prompt,
                response=response_text or str(exc),
                outcome=f"error:{exc}",
            )
            raise

    def _build_prompt(self, context: DataContext) -> str:
        return "\n\n".join(
            (SYSTEM_PROMPT, render_prompt(context), CODEX_JSON_INSTRUCTION)
        )

    def _build_argv(self, prompt: str) -> list[str]:
        argv = [self._binary, "exec"]
        if self._model:
            argv += ["--model", self._model]
        argv += list(self._extra_args)
        argv.append(prompt)
        return argv

    def _call_with_retry(self, prompt: str) -> str:
        return _call_provider_with_retry(
            lambda: self._invoke(prompt),
            max_retries=self._max_retries,
            retry_backoff_seconds=self._retry_backoff_seconds,
        )

    def _invoke(self, prompt: str) -> str:
        completed = self._runner(
            self._build_argv(prompt),
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            timeout=self._timeout_seconds,
        )
        returncode = getattr(completed, "returncode", 0)
        if returncode != 0:
            stderr = (getattr(completed, "stderr", "") or "").strip()
            raise RuntimeError(
                f"codex CLI exited with status {returncode}: {stderr[:500]}"
            )
        return getattr(completed, "stdout", "") or ""


def build_single_shot_llm_provider(settings: Settings, *, transport=None, popen=None):
    """Construct positively verified clients; injected arbitrary SDKs are unsupported."""
    if settings.llm_provider is LLMProviderName.CODEX_CLI:
        provider = CodexCLIProvider(binary=settings.codex_cli_binary, model=settings.codex_cli_model,
            temperature=settings.codex_cli_temperature, timeout_seconds=90, max_retries=1,
            extra_args=settings.codex_cli_extra_args)
        provider._single_shot = True
        provider._popen = popen or subprocess.Popen
        return provider
    boundary = _SingleShotTransport(transport or httpx.HTTPTransport(retries=0))
    http_client = httpx.Client(transport=boundary, timeout=90, follow_redirects=False)
    kwargs = dict(max_retries=0, timeout=90, http_client=http_client)
    if settings.llm_provider is LLMProviderName.CLAUDE:
        import anthropic
        if settings.anthropic_auth_token is not None and settings.anthropic_auth_token.get_secret_value().strip():
            kwargs.update(auth_token=settings.anthropic_auth_token.get_secret_value(),
                default_headers={'anthropic-beta': ANTHROPIC_OAUTH_BETA_HEADER})
        else: kwargs['api_key'] = settings.active_llm_api_key.get_secret_value()
        provider = ClaudeLLMProvider(client=anthropic.Anthropic(**kwargs), model=settings.anthropic_model,
            temperature=settings.anthropic_temperature, max_retries=1)
    else:
        import openai
        kwargs['api_key'] = settings.active_llm_api_key.get_secret_value()
        provider = OpenAILLMProvider(client=openai.OpenAI(**kwargs), model=settings.openai_model,
            temperature=settings.openai_temperature, max_retries=1)
    provider._single_shot_transport = boundary
    return provider


def build_llm_provider(
    settings: Settings, *, client: Any = None, runner: Callable[..., Any] | None = None
) -> LLMProvider:
    """Build the configured LLM provider, constructing real SDK clients lazily."""

    if settings.llm_provider is LLMProviderName.CLAUDE:
        if client is None:
            import anthropic

            if (
                settings.anthropic_auth_token is not None
                and settings.anthropic_auth_token.get_secret_value().strip()
            ):
                # OAuth bearer token takes precedence over the API key. Exactly
                # one credential reaches the SDK; sending both auth headers is
                # rejected by the API.
                client = anthropic.Anthropic(
                    auth_token=settings.anthropic_auth_token.get_secret_value(),
                    default_headers={
                        "anthropic-beta": ANTHROPIC_OAUTH_BETA_HEADER
                    },
                )
            else:
                client = anthropic.Anthropic(
                    api_key=settings.active_llm_api_key.get_secret_value()
                )
        return ClaudeLLMProvider(
            client=client,
            model=settings.anthropic_model,
            temperature=settings.anthropic_temperature,
            max_retries=settings.llm_max_retries,
            retry_backoff_seconds=settings.llm_retry_backoff_seconds,
        )

    if settings.llm_provider is LLMProviderName.CODEX_CLI:
        return CodexCLIProvider(
            binary=settings.codex_cli_binary,
            model=settings.codex_cli_model,
            temperature=settings.codex_cli_temperature,
            timeout_seconds=settings.codex_cli_timeout_seconds,
            extra_args=settings.codex_cli_extra_args,
            max_retries=settings.llm_max_retries,
            retry_backoff_seconds=settings.llm_retry_backoff_seconds,
            runner=runner,
        )

    if client is None:
        import openai

        client = openai.OpenAI(
            api_key=settings.active_llm_api_key.get_secret_value()
        )
    return OpenAILLMProvider(
        client=client,
        model=settings.openai_model,
        temperature=settings.openai_temperature,
        max_retries=settings.llm_max_retries,
        retry_backoff_seconds=settings.llm_retry_backoff_seconds,
    )


def run_llm_cycle(
    provider: LLMProvider,
    context: DataContext,
    *,
    broker: Broker,
    available_cash: float,
    execution_config: ExecutionConfig,
    risk_config: RiskConfig,
    daily_loss_state: DailyLossState,
    dry_run: bool = True,
    origin_run_id: str | None = None,
) -> ExecutionResult:
    """Generate a provider signal and feed it through the execution core."""

    try:
        signal = provider.generate_signal(context)
    except LLMProviderError as exc:
        audit = CycleAuditEvent(
            ticker=context.ticker.value,
            parsed_decision=None,
            parse_error=f"llm_provider_error: {exc}",
            risk_override=False,
            override_reason="",
            final_action=ExecutionAction.HOLD.value,
            order_reason="llm provider failure",
            dry_run=dry_run,
            broker_order_id=None,
        )
        return ExecutionResult(
            ExecutionAction.HOLD,
            None,
            "llm provider failed; fail-safe HOLD",
            risk_override=False,
            override_reason=None,
            audit=audit,
            broker_order_id=None,
        )

    raw_signal = json.dumps(
        {
            "decision": signal.decision.value,
            "confidence": signal.confidence,
            "reason": signal.reason,
        }
    )
    return execute_signal_cycle(
        raw_signal,
        context.ticker,
        context.current_price,
        available_cash,
        broker,
        execution_config,
        risk_config,
        daily_loss_state,
        dry_run=dry_run,
        origin_run_id=origin_run_id,
    )
