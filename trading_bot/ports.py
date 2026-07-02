"""Synchronous semantic ports for future adapters."""

from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from trading_bot.domain import DataContext, LLMSignal, Order, Position, Ticker


@runtime_checkable
class Broker(Protocol):
    """Broker operations needed by execution logic."""

    def get_position(self, ticker: Ticker) -> Optional[Position]:
        """Return the current position for a ticker, if any."""
        ...

    def place_order(self, order: Order) -> str:
        """Place an order and return the broker's order identifier."""
        ...


@runtime_checkable
class LLMProvider(Protocol):
    """LLM signal generation boundary."""

    def generate_signal(self, context: DataContext) -> LLMSignal:
        """Generate a trading signal from prepared market context."""
        ...


@runtime_checkable
class DataSource(Protocol):
    """Market data context boundary."""

    def build_context(self, ticker: Ticker) -> DataContext:
        """Build ticker-oriented context for signal generation."""
        ...


@runtime_checkable
class Notifier(Protocol):
    """Operator notification boundary (fail-soft; never raises)."""

    def send(self, summary: str) -> bool:
        """Deliver a run summary; return True on delivery, False on give-up."""
        ...
