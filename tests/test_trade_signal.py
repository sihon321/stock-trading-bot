"""Provider I/O schema tests for the Phase 4 signal contract."""

import dataclasses
import json

import pytest
from pydantic import ValidationError

from trading_bot.domain import Decision, LLMSignal
from trading_bot.signal_parser import parse_signal
from trading_bot.trade_signal import TradeSignal


def test_trade_signal_fields_stay_in_lockstep_with_llm_signal() -> None:
    assert set(TradeSignal.model_fields) == {
        field.name for field in dataclasses.fields(LLMSignal)
    }


def test_trade_signal_json_round_trips_through_parse_signal() -> None:
    source = TradeSignal(
        decision=Decision.BUY,
        confidence=0.9,
        reason="RSI 72 + vol 2x",
    )

    parsed = parse_signal(json.dumps(source.model_dump(mode="json")))

    assert parsed.signal == LLMSignal(
        decision=Decision.BUY,
        confidence=0.9,
        reason="RSI 72 + vol 2x",
    )


def test_trade_signal_forbids_extras_and_schema_is_strict() -> None:
    with pytest.raises(ValidationError):
        TradeSignal(
            decision=Decision.HOLD,
            confidence=0.1,
            reason="No corroboration.",
            ticker="005930",
        )

    schema = TradeSignal.model_json_schema()
    assert schema["additionalProperties"] is False
    assert set(schema["required"]) == {"decision", "confidence", "reason"}


def test_trade_signal_accepts_only_known_decision_values() -> None:
    for decision in Decision:
        signal = TradeSignal(
            decision=decision,
            confidence=0.5,
            reason=f"{decision.value} is valid.",
        )
        assert signal.decision is decision

    with pytest.raises(ValidationError):
        TradeSignal(decision="MAYBE", confidence=0.5, reason="Unknown.")
