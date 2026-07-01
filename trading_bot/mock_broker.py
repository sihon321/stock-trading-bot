"""In-memory paper-account broker for mock-safe Phase 2 execution.

``MockBroker`` satisfies the existing synchronous :class:`~trading_bot.ports.Broker`
Protocol. It holds cash, positions, and an order history entirely in memory and
mutates them *only* through explicit :meth:`place_order` calls (T-02-09). It never
places a real order, opens a network connection, or imports any KIS/LLM/pykrx/HTTP
or data-adapter code (T-02-10) — it depends solely on :mod:`trading_bot.domain`.

Accounting is deterministic:
    * BUY debits ``quantity * limit_price`` from cash, adds the shares to the held
      position, and volume-weights the average entry price.
    * SELL credits ``quantity * limit_price`` to cash and reduces (or removes) the
      held position.
Invalid orders (non-positive quantity, selling more than held) raise ``ValueError``
and leave all state unchanged — the broker never mutates on a rejected order.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence

from trading_bot.domain import Money, Order, OrderSide, Position, Ticker


class MockBroker:
    """Deterministic in-memory paper broker satisfying the ``Broker`` Protocol."""

    def __init__(
        self,
        cash: Money,
        positions: Optional[Sequence[Position]] = None,
    ) -> None:
        self._cash = cash
        self._positions: Dict[str, Position] = {
            position.ticker.value: position for position in (positions or ())
        }
        self._order_history: List[Order] = []
        self._order_counter = 0

    @property
    def cash(self) -> Money:
        """Current in-memory cash balance."""
        return self._cash

    @property
    def order_history(self) -> List[Order]:
        """Copy of the orders placed so far, in placement order."""
        return list(self._order_history)

    def get_position(self, ticker: Ticker) -> Optional[Position]:
        """Return the in-memory position for ``ticker`` without side effects."""
        return self._positions.get(ticker.value)

    def place_order(self, order: Order) -> str:
        """Apply ``order`` to in-memory state and return a deterministic order ID.

        Raises:
            ValueError: If quantity is non-positive, currencies mismatch, a BUY
                exceeds available cash, or a SELL exceeds the held quantity. On any
                such rejection no state is mutated.
        """

        if order.quantity <= 0:
            raise ValueError(
                f"order quantity must be positive, got {order.quantity}"
            )
        if order.limit_price.currency != self._cash.currency:
            raise ValueError(
                "order currency "
                f"{order.limit_price.currency!r} does not match account currency "
                f"{self._cash.currency!r}"
            )

        notional = order.quantity * order.limit_price.amount

        if order.side is OrderSide.BUY:
            self._apply_buy(order, notional)
        elif order.side is OrderSide.SELL:
            self._apply_sell(order, notional)
        else:  # pragma: no cover - OrderSide is exhaustively BUY/SELL
            raise ValueError(f"unsupported order side: {order.side!r}")

        self._order_counter += 1
        self._order_history.append(order)
        return f"MOCK-{self._order_counter}"

    def _apply_buy(self, order: Order, notional: float) -> None:
        if notional > self._cash.amount:
            raise ValueError(
                f"insufficient cash for BUY: need {notional}, have "
                f"{self._cash.amount}"
            )

        ticker_key = order.ticker.value
        existing = self._positions.get(ticker_key)
        if existing is None:
            new_position = Position(
                ticker=order.ticker,
                quantity=order.quantity,
                average_price=order.limit_price,
            )
        else:
            total_quantity = existing.quantity + order.quantity
            weighted = (
                existing.quantity * existing.average_price.amount + notional
            )
            new_position = Position(
                ticker=order.ticker,
                quantity=total_quantity,
                average_price=Money(weighted / total_quantity, self._cash.currency),
            )

        self._positions[ticker_key] = new_position
        self._cash = Money(self._cash.amount - notional, self._cash.currency)

    def _apply_sell(self, order: Order, notional: float) -> None:
        ticker_key = order.ticker.value
        existing = self._positions.get(ticker_key)
        if existing is None or existing.quantity < order.quantity:
            held = 0 if existing is None else existing.quantity
            raise ValueError(
                f"cannot SELL {order.quantity}; only {held} held for "
                f"{ticker_key}"
            )

        remaining = existing.quantity - order.quantity
        if remaining == 0:
            del self._positions[ticker_key]
        else:
            self._positions[ticker_key] = Position(
                ticker=order.ticker,
                quantity=remaining,
                average_price=existing.average_price,
            )

        self._cash = Money(self._cash.amount + notional, self._cash.currency)
