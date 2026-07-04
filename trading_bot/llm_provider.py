"""Concrete LLM provider adapters with fail-safe signal re-validation."""

from __future__ import annotations

import json
from typing import Any

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


def build_llm_provider(settings: Settings, *, client: Any = None) -> LLMProvider:
    """Build the configured LLM provider, constructing real SDK clients lazily."""

    if settings.llm_provider is LLMProviderName.CLAUDE:
        if client is None:
            import anthropic

            if settings.anthropic_auth_token is not None:
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
    )
