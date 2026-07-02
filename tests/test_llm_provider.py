from __future__ import annotations

import pytest
import structlog.testing

from trading_bot.domain import Decision, LLMSignal
from trading_bot.prompts import PROMPT_VERSION, SYSTEM_PROMPT, render_prompt
from trading_bot.signal_parser import SignalParseError
from trading_bot.trade_signal import TradeSignal

from conftest import FakeAnthropicClient, anthropic_response, make_data_context


def _provider(fake, *, max_retries=3):
    from trading_bot.llm_provider import ClaudeLLMProvider

    return ClaudeLLMProvider(
        client=fake,
        model="claude-opus-4-8",
        temperature=0.0,
        max_retries=max_retries,
        retry_backoff_seconds=0.0,
    )


def _valid_tool_input(decision="BUY", confidence=0.9, reason="RSI 72 + vol 2x"):
    return {"decision": decision, "confidence": confidence, "reason": reason}


def test_claude_request_shape_forces_strict_tool_and_omits_sampling_params() -> None:
    from trading_bot.llm_provider import EMIT_SIGNAL_TOOL

    context = make_data_context()
    fake = FakeAnthropicClient(
        [anthropic_response(tool_input=_valid_tool_input())],
        api_key="sk-test-sentinel-secret",
    )

    _provider(fake).generate_signal(context)

    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["model"] == "claude-opus-4-8"
    assert call["max_tokens"] == 1024
    assert call["system"] == SYSTEM_PROMPT
    assert call["tools"] == [EMIT_SIGNAL_TOOL]
    assert call["tool_choice"] == {"type": "tool", "name": "emit_signal"}
    assert call["messages"] == [{"role": "user", "content": render_prompt(context)}]
    assert "temperature" not in call
    assert "top_p" not in call
    assert "top_k" not in call


def test_emit_signal_tool_schema_stays_in_lockstep_with_trade_signal() -> None:
    from trading_bot.llm_provider import EMIT_SIGNAL_TOOL

    schema = EMIT_SIGNAL_TOOL["input_schema"]

    assert EMIT_SIGNAL_TOOL["strict"] is True
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["decision", "confidence", "reason"]
    assert set(schema["properties"]) == set(TradeSignal.model_fields)
    assert schema["properties"]["decision"]["enum"] == ["BUY", "SELL", "HOLD"]


def test_claude_valid_tool_use_block_returns_parse_signal_validated_signal() -> None:
    fake = FakeAnthropicClient([anthropic_response(tool_input=_valid_tool_input())])

    signal = _provider(fake).generate_signal(make_data_context())

    assert signal == LLMSignal(
        decision=Decision.BUY,
        confidence=0.9,
        reason="RSI 72 + vol 2x",
    )


def test_claude_refusal_raises_llm_provider_error() -> None:
    from trading_bot.llm_provider import LLMProviderError

    fake = FakeAnthropicClient(
        [anthropic_response(tool_input=_valid_tool_input(), stop_reason="refusal")]
    )

    with pytest.raises(LLMProviderError):
        _provider(fake).generate_signal(make_data_context())


def test_claude_missing_tool_block_raises_llm_provider_error() -> None:
    from trading_bot.llm_provider import LLMProviderError

    fake = FakeAnthropicClient(
        [
            anthropic_response(
                content=[SimpleTextBlock(type="text", text="not a tool")]
            )
        ]
    )

    with pytest.raises(LLMProviderError):
        _provider(fake).generate_signal(make_data_context())


class SimpleTextBlock:
    def __init__(self, *, type: str, text: str) -> None:
        self.type = type
        self.text = text


def test_claude_malformed_tool_input_is_revalidated_by_parse_signal() -> None:
    from trading_bot.llm_provider import LLMProviderError

    fake = FakeAnthropicClient(
        [
            anthropic_response(
                tool_input={"decision": "BUY", "confidence": 1.5, "reason": "x"}
            )
        ]
    )

    with pytest.raises(LLMProviderError) as excinfo:
        _provider(fake).generate_signal(make_data_context())

    assert isinstance(excinfo.value.__cause__, SignalParseError)


def test_claude_retries_are_bounded_and_success_after_transient_failure() -> None:
    from trading_bot.llm_provider import LLMProviderError

    exhausted = FakeAnthropicClient(
        [anthropic_response(tool_input=_valid_tool_input())],
        error=RuntimeError("transport down"),
        fail_times=3,
    )

    with pytest.raises(LLMProviderError):
        _provider(exhausted, max_retries=3).generate_signal(make_data_context())
    assert len(exhausted.calls) == 3

    succeeds = FakeAnthropicClient(
        [anthropic_response(tool_input=_valid_tool_input())],
        error=RuntimeError("temporary"),
        fail_times=1,
    )

    assert _provider(succeeds, max_retries=3).generate_signal(make_data_context())
    assert len(succeeds.calls) == 2


def test_claude_logs_one_secret_free_cycle_event_on_success_and_error() -> None:
    from trading_bot.llm_provider import LLMProviderError

    context = make_data_context()
    secret = "sk-test-sentinel-secret"
    success_fake = FakeAnthropicClient(
        [anthropic_response(tool_input=_valid_tool_input())],
        api_key=secret,
    )

    with structlog.testing.capture_logs() as logs:
        _provider(success_fake).generate_signal(context)

    assert len(logs) == 1
    event = logs[0]
    assert event["event"] == "llm_signal_cycle"
    assert event["provider"] == "claude"
    assert event["model"] == "claude-opus-4-8"
    assert event["temperature"] == 0.0
    assert event["prompt_version"] == PROMPT_VERSION
    assert event["prompt"] == render_prompt(context)
    assert event["response"]
    assert event["outcome"] == "parsed:BUY"
    assert secret not in repr(event)

    refusal_fake = FakeAnthropicClient(
        [anthropic_response(tool_input=_valid_tool_input(), stop_reason="refusal")],
        api_key=secret,
    )
    with structlog.testing.capture_logs() as logs:
        with pytest.raises(LLMProviderError):
            _provider(refusal_fake).generate_signal(context)

    assert len(logs) == 1
    assert logs[0]["provider"] == "claude"
    assert logs[0]["outcome"].startswith("error:")
    assert secret not in repr(logs[0])
