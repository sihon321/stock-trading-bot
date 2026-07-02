from __future__ import annotations

import inspect
import subprocess
import sys
from unittest.mock import patch

import pytest
import structlog.testing
from pydantic import SecretStr

from trading_bot.config import LLMProviderName
from trading_bot.domain import Decision, LLMSignal, Money, Order, Ticker
from trading_bot.execution import ExecutionAction, ExecutionConfig
from trading_bot.mock_broker import MockBroker
from trading_bot.ports import LLMProvider
from trading_bot.prompts import PROMPT_VERSION, SYSTEM_PROMPT, render_prompt
from trading_bot.risk import DailyLossState, RiskConfig
from trading_bot.signal_parser import SignalParseError
from trading_bot.trade_signal import TradeSignal

from conftest import (
    FakeAnthropicClient,
    FakeOpenAIClient,
    anthropic_response,
    make_data_context,
    make_settings,
    openai_response,
)


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


def _execution_config() -> ExecutionConfig:
    return ExecutionConfig(
        buy_confidence_threshold=0.8,
        sell_confidence_threshold=0.8,
        buy_cash_fraction=0.1,
        max_position_value=1_000_000.0,
    )


def _risk_config() -> RiskConfig:
    return RiskConfig(stop_loss_pct=0.05, take_profit_pct=0.10)


def _no_loss() -> DailyLossState:
    return DailyLossState(realized_loss=0.0, threshold=500_000.0)


class FailingProvider:
    def generate_signal(self, context):
        from trading_bot.llm_provider import LLMProviderError

        raise LLMProviderError("transient outage")


class StubSignalProvider:
    def __init__(self, signal: LLMSignal) -> None:
        self.signal = signal

    def generate_signal(self, context):
        return self.signal


class RecordingNoTouchBroker:
    def __init__(self) -> None:
        self.get_position_calls = []
        self.place_order_calls = []

    def get_position(self, ticker: Ticker):
        self.get_position_calls.append(ticker)
        raise AssertionError("get_position must not be called")

    def place_order(self, order: Order):
        self.place_order_calls.append(order)
        raise AssertionError("place_order must not be called")


def test_build_llm_provider_selects_adapter_from_settings_value() -> None:
    from trading_bot.llm_provider import (
        ClaudeLLMProvider,
        OpenAILLMProvider,
        build_llm_provider,
    )

    claude_settings = make_settings(
        llm_provider=LLMProviderName.CLAUDE,
        anthropic_model="claude-sonnet-4-6",
        anthropic_temperature=0.2,
        llm_max_retries=5,
        llm_retry_backoff_seconds=2.5,
    )
    claude = build_llm_provider(claude_settings, client=FakeAnthropicClient())

    assert isinstance(claude, ClaudeLLMProvider)
    assert claude._model == claude_settings.anthropic_model
    assert claude._temperature == claude_settings.anthropic_temperature
    assert claude._max_retries == claude_settings.llm_max_retries
    assert claude._retry_backoff_seconds == claude_settings.llm_retry_backoff_seconds

    openai_settings = make_settings(
        llm_provider=LLMProviderName.OPENAI,
        openai_model="gpt-4.1-mini",
        openai_temperature=0.1,
        llm_max_retries=4,
        llm_retry_backoff_seconds=1.5,
    )
    openai = build_llm_provider(openai_settings, client=FakeOpenAIClient())

    assert isinstance(openai, OpenAILLMProvider)
    assert openai._model == openai_settings.openai_model
    assert openai._temperature == openai_settings.openai_temperature
    assert openai._max_retries == openai_settings.llm_max_retries
    assert openai._retry_backoff_seconds == openai_settings.llm_retry_backoff_seconds


def test_built_adapters_satisfy_llm_provider_protocol() -> None:
    from trading_bot.llm_provider import build_llm_provider

    claude = build_llm_provider(
        make_settings(llm_provider=LLMProviderName.CLAUDE),
        client=FakeAnthropicClient(),
    )
    openai = build_llm_provider(
        make_settings(llm_provider=LLMProviderName.OPENAI),
        client=FakeOpenAIClient(),
    )

    assert isinstance(claude, LLMProvider)
    assert isinstance(openai, LLMProvider)
    assert not inspect.iscoroutinefunction(claude.generate_signal)
    assert not inspect.iscoroutinefunction(openai.generate_signal)


def test_llm_provider_import_keeps_sdks_lazy_in_fresh_interpreter() -> None:
    program = (
        "import sys\n"
        "import trading_bot.llm_provider\n"
        "loaded = set(sys.modules)\n"
        "for p in ('anthropic', 'openai'):\n"
        "    assert not any(m == p or m.startswith(p + '.') for m in loaded), p\n"
        "print('OK')\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "OK" in completed.stdout


def test_injected_client_does_not_surface_active_api_key() -> None:
    from trading_bot.llm_provider import build_llm_provider

    fake = FakeAnthropicClient(api_key=None)

    with patch.object(
        SecretStr,
        "get_secret_value",
        side_effect=AssertionError("secret should not be surfaced"),
    ):
        provider = build_llm_provider(
            make_settings(llm_provider=LLMProviderName.CLAUDE),
            client=fake,
        )

    assert provider._client is fake
    assert fake.api_key is None


def test_error_maps_to_hold() -> None:
    from trading_bot.llm_provider import run_llm_cycle

    broker = RecordingNoTouchBroker()

    result = run_llm_cycle(
        FailingProvider(),
        make_data_context(),
        broker=broker,
        available_cash=10_000_000.0,
        execution_config=_execution_config(),
        risk_config=_risk_config(),
        daily_loss_state=_no_loss(),
        dry_run=True,
    )

    assert result.action is ExecutionAction.HOLD
    assert result.order is None
    assert result.audit is not None
    assert result.audit.final_action == "HOLD"
    assert result.audit.parse_error is not None
    assert result.audit.parse_error.startswith("llm_provider_error:")
    assert broker.get_position_calls == []
    assert broker.place_order_calls == []


def test_claude_run_llm_cycle_flows_into_dry_run_execution_chain() -> None:
    from trading_bot.llm_provider import ClaudeLLMProvider, run_llm_cycle

    context = make_data_context()
    fake = FakeAnthropicClient(
        [anthropic_response(tool_input=_valid_tool_input("BUY", 0.9))]
    )
    broker = MockBroker(cash=Money(10_000_000.0, "KRW"))
    provider = ClaudeLLMProvider(
        client=fake,
        model="claude-opus-4-8",
        temperature=0.0,
        max_retries=3,
        retry_backoff_seconds=0.0,
    )

    result = run_llm_cycle(
        provider,
        context,
        broker=broker,
        available_cash=10_000_000.0,
        execution_config=_execution_config(),
        risk_config=_risk_config(),
        daily_loss_state=_no_loss(),
        dry_run=True,
    )

    assert result.action is ExecutionAction.BUY
    assert result.order is not None
    assert result.audit is not None
    assert result.audit.dry_run is True
    assert result.audit.order_reason == "buy signal qualified"
    assert broker.order_history == []


def test_run_llm_cycle_serializes_signal_for_execution_revalidation() -> None:
    from trading_bot.llm_provider import run_llm_cycle

    signal = LLMSignal(
        decision=Decision.BUY,
        confidence=0.97,
        reason="breakout signal survived provider validation",
    )

    result = run_llm_cycle(
        StubSignalProvider(signal),
        make_data_context(),
        broker=MockBroker(cash=Money(10_000_000.0, "KRW")),
        available_cash=10_000_000.0,
        execution_config=_execution_config(),
        risk_config=_risk_config(),
        daily_loss_state=_no_loss(),
        dry_run=True,
    )

    assert result.audit is not None
    assert result.audit.parsed_decision == Decision.BUY.value
    assert result.action is ExecutionAction.BUY


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


def _openai_provider(fake, *, max_retries=3):
    from trading_bot.llm_provider import OpenAILLMProvider

    return OpenAILLMProvider(
        client=fake,
        model="gpt-4.1",
        temperature=0.0,
        max_retries=max_retries,
        retry_backoff_seconds=0.0,
    )


def test_openai_request_shape_uses_parse_with_trade_signal_schema() -> None:
    context = make_data_context()
    fake = FakeOpenAIClient(
        [
            openai_response(
                parsed=TradeSignal(
                    decision=Decision.SELL,
                    confidence=0.85,
                    reason="breakdown below 20-day low on 2x volume",
                )
            )
        ]
    )

    _openai_provider(fake).generate_signal(context)

    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["model"] == "gpt-4.1"
    assert call["temperature"] == 0.0
    assert call["response_format"] is TradeSignal
    assert call["messages"] == [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": render_prompt(context)},
    ]


def test_openai_valid_parsed_signal_is_revalidated_through_parse_signal() -> None:
    fake = FakeOpenAIClient(
        [
            openai_response(
                parsed=TradeSignal(
                    decision=Decision.SELL,
                    confidence=0.85,
                    reason="breakdown below 20-day low on 2x volume",
                )
            )
        ]
    )

    signal = _openai_provider(fake).generate_signal(make_data_context())

    assert signal == LLMSignal(
        decision=Decision.SELL,
        confidence=0.85,
        reason="breakdown below 20-day low on 2x volume",
    )


def test_openai_refusal_raises_llm_provider_error() -> None:
    from trading_bot.llm_provider import LLMProviderError

    fake = FakeOpenAIClient([openai_response(parsed=None, refusal="policy refusal")])

    with pytest.raises(LLMProviderError):
        _openai_provider(fake).generate_signal(make_data_context())


def test_openai_none_parsed_raises_llm_provider_error() -> None:
    from trading_bot.llm_provider import LLMProviderError

    fake = FakeOpenAIClient([openai_response(parsed=None, refusal=None)])

    with pytest.raises(LLMProviderError):
        _openai_provider(fake).generate_signal(make_data_context())


def test_openai_retries_are_bounded() -> None:
    from trading_bot.llm_provider import LLMProviderError

    fake = FakeOpenAIClient(
        [
            openai_response(
                parsed=TradeSignal(
                    decision=Decision.HOLD,
                    confidence=0.5,
                    reason="insufficient confirmation",
                )
            )
        ],
        error=RuntimeError("transport down"),
        fail_times=3,
    )

    with pytest.raises(LLMProviderError):
        _openai_provider(fake, max_retries=3).generate_signal(make_data_context())

    assert len(fake.calls) == 3


def test_openai_logs_one_secret_free_cycle_event() -> None:
    context = make_data_context()
    secret = "sk-test-sentinel-secret"
    fake = FakeOpenAIClient(
        [
            openai_response(
                parsed=TradeSignal(
                    decision=Decision.HOLD,
                    confidence=0.5,
                    reason="insufficient confirmation",
                )
            )
        ],
        api_key=secret,
    )

    with structlog.testing.capture_logs() as logs:
        _openai_provider(fake).generate_signal(context)

    assert len(logs) == 1
    event = logs[0]
    assert event["event"] == "llm_signal_cycle"
    assert event["provider"] == "openai"
    assert event["model"] == "gpt-4.1"
    assert event["temperature"] == 0.0
    assert event["prompt_version"] == PROMPT_VERSION
    assert event["prompt"] == render_prompt(context)
    assert event["response"]
    assert event["outcome"] == "parsed:HOLD"
    assert secret not in repr(event)
