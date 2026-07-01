"""Fail-safe parser turning untrusted raw signal JSON into a canonical signal.

`parse_signal` is the only boundary that converts a raw LLM-like JSON payload
into a typed :class:`~trading_bot.domain.LLMSignal`. It validates strictly and
never repairs malformed or schema-invalid input into a tradeable signal: any
such input raises :class:`SignalParseError`, which execution-facing code maps to
HOLD / no-trade.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Sequence

from trading_bot.domain import Decision, LLMSignal

_REQUIRED_FIELDS = ("decision", "confidence", "reason")
_MIN_CONFIDENCE = 0.0
_MAX_CONFIDENCE = 1.0


class SignalParseError(ValueError):
    """Raised when raw signal input is malformed or schema-invalid.

    A ``SignalParseError`` is the fail-safe signal: the caller must treat it as
    HOLD / no-trade and never as a partially-parsed order.
    """


@dataclass(frozen=True)
class ParsedSignal:
    """Successful parse result preserving the canonical signal and diagnostics.

    Attributes:
        signal: The validated canonical :class:`LLMSignal`.
        raw_input: The exact raw string that was parsed.
        ignored_fields: Names of extra JSON fields that were ignored and did not
            affect the canonical signal. Non-sensitive diagnostics only.
    """

    signal: LLMSignal
    raw_input: str
    ignored_fields: Sequence[str] = field(default_factory=tuple)


def parse_signal(raw_input: str) -> ParsedSignal:
    """Parse ``raw_input`` into a :class:`ParsedSignal` or fail closed.

    Raises:
        SignalParseError: If the input is not a JSON object, is missing a
            required field, has an unknown decision, a non-numeric confidence,
            a confidence outside ``0.0..1.0``, or a blank reason.
    """

    try:
        payload = json.loads(raw_input)
    except (json.JSONDecodeError, TypeError) as exc:
        raise SignalParseError(f"raw signal is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise SignalParseError(
            f"raw signal must be a JSON object, got {type(payload).__name__}"
        )

    missing = [name for name in _REQUIRED_FIELDS if name not in payload]
    if missing:
        raise SignalParseError(f"raw signal missing required field(s): {missing}")

    decision = _parse_decision(payload["decision"])
    confidence = _parse_confidence(payload["confidence"])
    reason = _parse_reason(payload["reason"])

    ignored_fields = tuple(
        sorted(name for name in payload if name not in _REQUIRED_FIELDS)
    )

    signal = LLMSignal(decision=decision, confidence=confidence, reason=reason)
    return ParsedSignal(
        signal=signal,
        raw_input=raw_input,
        ignored_fields=ignored_fields,
    )


def _parse_decision(value: object) -> Decision:
    if not isinstance(value, str):
        raise SignalParseError(
            f"decision must be a string, got {type(value).__name__}"
        )
    try:
        return Decision(value)
    except ValueError as exc:
        known = [member.value for member in Decision]
        raise SignalParseError(
            f"unknown decision {value!r}; expected one of {known}"
        ) from exc


def _parse_confidence(value: object) -> float:
    # bool is a subclass of int; reject it explicitly so ``True``/``False``
    # cannot masquerade as numeric confidence.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SignalParseError(
            f"confidence must be a number, got {type(value).__name__}"
        )
    confidence = float(value)
    if not _MIN_CONFIDENCE <= confidence <= _MAX_CONFIDENCE:
        raise SignalParseError(
            f"confidence {confidence} outside range "
            f"[{_MIN_CONFIDENCE}, {_MAX_CONFIDENCE}]"
        )
    return confidence


def _parse_reason(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SignalParseError("reason must be a non-empty string")
    return value
