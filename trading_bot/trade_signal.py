"""Provider I/O schema for structured LLM trading signals.

This Pydantic model is only the provider structured-output schema. The canonical
domain type remains the frozen ``LLMSignal`` dataclass produced by
``parse_signal``. This mirror deliberately re-implements none of the parser's
validation, such as confidence range checks, bool-as-number rejection, or
non-empty reason validation, because ``parse_signal`` is the single audited
authority for provider output.
"""

from __future__ import annotations

from pydantic import BaseModel

from trading_bot.domain import Decision


class TradeSignal(BaseModel):
    """Strict provider I/O mirror of ``LLMSignal``."""

    model_config = {"extra": "forbid"}

    decision: Decision
    confidence: float
    reason: str
