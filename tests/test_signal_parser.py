import importlib
import json
import sys

import pytest

from trading_bot.domain import Decision, LLMSignal
from trading_bot.signal_parser import ParsedSignal, SignalParseError, parse_signal


FORBIDDEN_MODULE_PREFIXES = (
    "anthropic",
    "openai",
    "pykrx",
    "requests",
    "httpx",
)

FORBIDDEN_LOCAL_MODULE_FRAGMENTS = (
    "adapter",
    "broker",
    "execution",
    "kis",
    "naver",
    "scrap",
)


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


def test_parsed_signal_preserves_raw_input() -> None:
    # D-04: the wrapper preserves the exact raw input for audit/diagnostics.
    raw = _valid_payload(ticker="005930")
    result = parse_signal(raw)

    assert result.raw_input == raw


def test_ignored_field_names_are_observable_as_diagnostics() -> None:
    # D-04: extra fields surface only as non-sensitive diagnostics and cannot
    # affect the canonical signal.
    result = parse_signal(_valid_payload(model="claude-opus-4-8", ticker="005930"))

    assert tuple(result.ignored_fields) == ("model", "ticker")
    assert result.signal == LLMSignal(
        decision=Decision.BUY,
        confidence=0.82,
        reason="Momentum and volume both improved.",
    )


def test_valid_payload_without_extras_has_no_ignored_fields() -> None:
    result = parse_signal(_valid_payload())

    assert tuple(result.ignored_fields) == ()


def test_diagnostics_never_expose_required_field_names() -> None:
    result = parse_signal(_valid_payload(extra="x"))

    assert "decision" not in result.ignored_fields
    assert "confidence" not in result.ignored_fields
    assert "reason" not in result.ignored_fields


def test_signal_parser_import_has_no_forbidden_module_side_effects() -> None:
    for name in list(sys.modules):
        if name == "trading_bot.signal_parser" or name.startswith(
            "trading_bot.signal_parser."
        ):
            del sys.modules[name]

    before_import = set(sys.modules)
    importlib.import_module("trading_bot.signal_parser")

    loaded_modules = set(sys.modules) - before_import
    for prefix in FORBIDDEN_MODULE_PREFIXES:
        assert prefix not in loaded_modules

    forbidden_local = [
        name
        for name in loaded_modules
        if name.startswith("trading_bot.")
        and any(fragment in name for fragment in FORBIDDEN_LOCAL_MODULE_FRAGMENTS)
    ]
    assert forbidden_local == []
    assert "trading_bot.config" not in loaded_modules
