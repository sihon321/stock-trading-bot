import json

import pytest

from trading_bot.domain import Decision, LLMSignal
from trading_bot.signal_parser import ParsedSignal, SignalParseError, parse_signal


def _valid_payload(**overrides: object) -> str:
    payload = {
        "decision": "BUY",
        "confidence": 0.82,
        "reason": "Momentum and volume both improved.",
    }
    payload.update(overrides)
    return json.dumps(payload)


def test_valid_payload_returns_parsed_signal_with_canonical_llm_signal() -> None:
    result = parse_signal(_valid_payload())

    assert isinstance(result, ParsedSignal)
    assert isinstance(result.signal, LLMSignal)
    assert result.signal.decision is Decision.BUY
    assert result.signal.confidence == 0.82
    assert result.signal.reason == "Momentum and volume both improved."


def test_parse_signal_accepts_every_known_decision() -> None:
    for decision in (Decision.BUY, Decision.SELL, Decision.HOLD):
        result = parse_signal(_valid_payload(decision=decision.value))
        assert result.signal.decision is decision


def test_extra_fields_are_ignored_and_do_not_change_canonical_signal() -> None:
    result = parse_signal(
        _valid_payload(ticker="005930", model="claude-opus-4-8", note="extra")
    )

    assert result.signal == LLMSignal(
        decision=Decision.BUY,
        confidence=0.82,
        reason="Momentum and volume both improved.",
    )


def test_confidence_bounds_are_inclusive() -> None:
    low = parse_signal(_valid_payload(confidence=0.0))
    high = parse_signal(_valid_payload(confidence=1.0))

    assert low.signal.confidence == 0.0
    assert high.signal.confidence == 1.0


def test_parser_accepts_in_range_confidence_below_execution_thresholds() -> None:
    # D-03: parser validates range only; it does not apply BUY/SELL thresholds.
    buy = parse_signal(_valid_payload(decision="BUY", confidence=0.10))
    sell = parse_signal(_valid_payload(decision="SELL", confidence=0.42))

    assert buy.signal.decision is Decision.BUY
    assert buy.signal.confidence == 0.10
    assert sell.signal.decision is Decision.SELL
    assert sell.signal.confidence == 0.42


@pytest.mark.parametrize(
    "raw_input",
    [
        pytest.param("{not valid json", id="malformed-json"),
        pytest.param("", id="empty-string"),
        pytest.param("[1, 2, 3]", id="json-array-not-object"),
        pytest.param('"a string"', id="json-string-not-object"),
        pytest.param("42", id="json-number-not-object"),
        pytest.param("null", id="json-null-not-object"),
        pytest.param(
            json.dumps({"confidence": 0.9, "reason": "no decision"}),
            id="missing-decision",
        ),
        pytest.param(
            json.dumps({"decision": "BUY", "reason": "no confidence"}),
            id="missing-confidence",
        ),
        pytest.param(
            json.dumps({"decision": "BUY", "confidence": 0.9}),
            id="missing-reason",
        ),
        pytest.param(
            json.dumps({"decision": "MAYBE", "confidence": 0.9, "reason": "unknown"}),
            id="unknown-decision",
        ),
        pytest.param(
            json.dumps({"decision": "BUY", "confidence": 1.5, "reason": "too high"}),
            id="confidence-above-range",
        ),
        pytest.param(
            json.dumps({"decision": "BUY", "confidence": -0.1, "reason": "too low"}),
            id="confidence-below-range",
        ),
        pytest.param(
            json.dumps({"decision": "BUY", "confidence": "high", "reason": "text"}),
            id="confidence-non-numeric",
        ),
        pytest.param(
            json.dumps({"decision": "BUY", "confidence": True, "reason": "bool"}),
            id="confidence-boolean",
        ),
        pytest.param(
            json.dumps({"decision": "BUY", "confidence": 0.9, "reason": ""}),
            id="empty-reason",
        ),
        pytest.param(
            json.dumps({"decision": "BUY", "confidence": 0.9, "reason": "   "}),
            id="blank-reason",
        ),
    ],
)
def test_invalid_payloads_raise_signal_parse_error(raw_input: str) -> None:
    with pytest.raises(SignalParseError):
        parse_signal(raw_input)


def test_signal_parse_error_is_a_value_error() -> None:
    assert issubclass(SignalParseError, ValueError)
