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

from datetime import datetime
from contextlib import nullcontext
from typing import Any, Callable, Dict, List, Optional, Sequence
import uuid
from zoneinfo import ZoneInfo

from trading_bot.audit_models import FreshnessEvidence, OrderEvent, OrderEventType
from trading_bot.data_models import SourceStatus
from trading_bot.domain import Money, Order, OrderSide, Position, Ticker
from trading_bot.market_cycle import MarketCyclePolicy, QuoteObservation


class MockBroker:
    """Deterministic in-memory paper broker satisfying the ``Broker`` Protocol."""

    def __init__(
        self,
        cash: Money,
        positions: Optional[Sequence[Position]] = None,
        pre_submit_quote_reader: Optional[Callable[[str], Any]] = None,
        evidence_sink: Optional[Callable[[OrderEvent], object]] = None,
        clock: Optional[Callable[[], datetime]] = None,
        freshness_policy_version: str = "quote-freshness-v1",
        submission_authority: Any = None,
        submission_scope: Any = None,
    ) -> None:
        self._cash = cash
        self._positions: Dict[str, Position] = {
            position.ticker.value: position for position in (positions or ())
        }
        self._order_history: List[Order] = []
        self._order_counter = 0
        self._pre_submit_quote_reader = pre_submit_quote_reader
        self._evidence_sink = evidence_sink
        self._clock = clock or (lambda: datetime.now(ZoneInfo("Asia/Seoul")))
        self._freshness_policy_version = freshness_policy_version
        self._submission_authority = submission_authority
        self._submission_scope = submission_scope

    def set_evidence_sink(self, sink: Callable[[OrderEvent], object]) -> None:
        self._evidence_sink = sink

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

    def place_order(self, order: Order, **context: object) -> str:
        """Apply ``order`` to in-memory state and return a deterministic order ID.

        Raises:
            ValueError: If quantity is non-positive, currencies mismatch, a BUY
                exceeds available cash, or a SELL exceeds the held quantity. On any
                such rejection no state is mutated.
        """

        quote = None
        if self._pre_submit_quote_reader is not None:
            from trading_bot.kis_broker import MarketClosedError

            intent_id = str(context.get("order_intent_id") or uuid.uuid4())
            origin = str(context.get("origin_run_id") or "unattributed")
            observer = str(context.get("observer_run_id") or origin)
            quote = self._pre_submit_quote_reader(order.ticker.value)
            checked_at = self._clock()
            observed_at = getattr(quote, "observed_at", None)
            health = getattr(quote, "health", None)
            freshness = None
            if health is not None and health.status is SourceStatus.AVAILABLE and observed_at is not None:
                class _UnusedCalendar:
                    def is_trading_day(self, day): return None
                    def previous_trading_day(self, day): return None
                freshness = MarketCyclePolicy(_UnusedCalendar()).quote_freshness(
                    QuoteObservation(observed_at), checked_at
                )
            passed = freshness is not None and freshness.fresh
            facts = FreshnessEvidence(
                observed_at=observed_at.isoformat() if observed_at else None,
                checked_at=checked_at.isoformat(),
                age_seconds=freshness.age_seconds if freshness else None,
                verdict="PASS" if passed else "BLOCK",
                reason=freshness.reason if freshness else "quote unavailable",
                policy_version=self._freshness_policy_version,
            )
            if self._evidence_sink is not None:
                self._evidence_sink(OrderEvent(
                    order_intent_id=intent_id, origin_run_id=origin,
                    observer_run_id=observer, ticker=order.ticker.value,
                    event_type=(OrderEventType.FRESHNESS_CHECKED if passed else OrderEventType.FRESHNESS_BLOCKED),
                    side=order.side.value, requested_qty=order.quantity,
                    broker_status="FRESH" if passed else "STALE_QUOTE",
                    detail=facts.detail(), observed_at=facts.observed_at,
                ))
            if not passed:
                raise MarketClosedError("mock order skipped: pre-submit quote is stale")

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

        authority=self._submission_authority
        intent_id=str(context.get('order_intent_id') or uuid.uuid4())
        submission_id=str(uuid.uuid4())
        origin=str(context.get('origin_run_id') or 'unattributed')
        boundary=nullcontext(None)
        if authority is not None:
            from .submission_authority import SubmissionAuthority
            if type(authority) is not SubmissionAuthority:
                raise ValueError('actual submission authority required')
            refresh=context.get('portfolio_refresh')
            snapshot=refresh(order.ticker.value) if callable(refresh) else None
            boundary=authority.admit(order,self._submission_scope,intent_id,submission_id,
                context.get('lease_guard'),(snapshot,quote))
        with boundary as admission:
            if authority is not None:
                if self._evidence_sink is None:
                    raise ValueError('committed primary evidence required')
                self._evidence_sink(OrderEvent(order_intent_id=intent_id,origin_run_id=origin,
                    observer_run_id=origin,ticker=order.ticker.value,
                    event_type=OrderEventType.SUBMISSION_ATTEMPTED,submission_id=submission_id,
                    side=order.side.value,requested_qty=order.quantity,detail=admission.detail()))
                authority.verify_attempt(admission,order,origin,
                    lease=context.get('lease_guard'),fresh_evidence=(snapshot,quote))
            if order.side is OrderSide.BUY:
                self._apply_buy(order, notional)
            elif order.side is OrderSide.SELL:
                self._apply_sell(order, notional)
            else:  # pragma: no cover
                raise ValueError(f"unsupported order side: {order.side!r}")
            self._order_counter += 1
            self._order_history.append(order)
            result=f"MOCK-{self._order_counter}"
            if authority is not None:
                self._evidence_sink(OrderEvent(order_intent_id=intent_id,origin_run_id=origin,
                    observer_run_id=origin,ticker=order.ticker.value,
                    event_type=OrderEventType.RECONCILED,submission_id=submission_id,
                    broker_order_id=result,side=order.side.value,requested_qty=order.quantity,
                    filled_qty=order.quantity,unfilled_qty=0,broker_status='FILLED'))
            return result

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
