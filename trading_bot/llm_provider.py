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

from trading_bot.domain import DataContext, LLMSignal
from trading_bot.prompts import PROMPT_VERSION, SYSTEM_PROMPT, render_prompt
from trading_bot.signal_parser import SignalParseError, parse_signal
from trading_bot.trade_signal import TradeSignal


class LLMProviderError(RuntimeError):
    """Raised when provider output cannot produce a safe canonical signal.

    A ``LLMProviderError`` is fail-safe: callers must treat it as HOLD /
    no-trade and never as a partially parsed or synthetic trading signal.
    """


class _TransientLLMError(Exception):
    """Internal marker for retryable transient LLM-call failures."""


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
        @retry(
            reraise=True,
            stop=stop_after_attempt(self._max_retries),
            wait=wait_exponential(multiplier=self._retry_backoff_seconds),
            retry=retry_if_exception_type(_TransientLLMError),
        )
        def _attempt() -> Any:
            try:
                return self._client.messages.create(
                    model=self._model,
                    max_tokens=1024,
                    system=SYSTEM_PROMPT,
                    tools=[EMIT_SIGNAL_TOOL],
                    tool_choice={"type": "tool", "name": "emit_signal"},
                    messages=[{"role": "user", "content": prompt}],
                )
            except Exception as exc:  # noqa: BLE001 - provider transports vary.
                raise _TransientLLMError(
                    f"LLM request failed: {type(exc).__name__}"
                ) from exc

        try:
            return _attempt()
        except _TransientLLMError as exc:
            raise LLMProviderError(str(exc)) from exc

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
