"""Core domain objects for trading decisions and execution intent."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Sequence


class Decision(str, Enum):
    """Machine-checkable trading signal decisions."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class OrderSide(str, Enum):
    """Executable order sides."""

    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True)
class Ticker:
    """Market ticker symbol."""

    value: str


@dataclass(frozen=True)
class Money:
    """Monetary amount in a currency."""

    amount: float
    currency: str = "KRW"


@dataclass(frozen=True)
class Order:
    """Order intent produced by execution logic."""

    ticker: Ticker
    side: OrderSide
    quantity: int
    limit_price: Money


@dataclass(frozen=True)
class Position:
    """Current holding for a ticker."""

    ticker: Ticker
    quantity: int
    average_price: Money


@dataclass(frozen=True)
class DataContext:
    """Ticker-oriented context passed to an LLM provider."""

    ticker: Ticker
    current_price: Money
    technicals: Mapping[str, float] = field(default_factory=dict)
    news: Sequence[str] = field(default_factory=tuple)


@dataclass(frozen=True)
class LLMSignal:
    """Strict JSON-compatible LLM trading signal shape."""

    decision: Decision
    confidence: float
    reason: str
