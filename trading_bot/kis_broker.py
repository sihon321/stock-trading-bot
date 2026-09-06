"""Structural KIS Broker implementation with broker-truth reconciliation."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, time as dt_time
import hashlib
from typing import Any, Callable, Dict, Optional, Protocol, Sequence
import uuid
from zoneinfo import ZoneInfo

from trading_bot.data_models import SourceStatus
from trading_bot.domain import Money, Order, OrderSide, Position, Ticker
from trading_bot.kis_auth import KisTokenManager
from trading_bot.kis_order import (
    FillStatus,
    KisOrderAccount,
    KisOrderAdapter,
    KisOrderError,
    snap_to_tick,
)
from trading_bot.market_cycle import MarketCyclePolicy, QuoteObservation
from trading_bot.audit_models import FreshnessEvidence, OrderEvent, OrderEventType, sanitize_detail
from trading_bot.portfolio import PortfolioSnapshot


class MarketClosedError(RuntimeError):
    """Raised when the order pre-flight guard fails safe to HOLD/skip."""


class OrderEvidenceSink(Protocol):
    """Synchronous append-only sink used at the money-moving boundary."""

    def __call__(self, event: OrderEvent) -> object: ...


class AmbiguousSubmissionError(RuntimeError):
    """A single POST may have reached KIS but acknowledgement is unknown."""

    def __init__(self, *, order_intent_id: str, submission_id: str) -> None:
        self.order_intent_id = order_intent_id
        self.submission_id = submission_id
        super().__init__("KIS order submission is ambiguous; reconcile before retry")


@dataclass(frozen=True)
class OrderReconciliation:
    """Requested-vs-filled audit state from the latest broker readback."""

    order_id: str
    ticker: str
    requested_qty: int
    filled_qty: int
    remaining_qty: int
    local_client_ref: str
    order_intent_id: str = ""
    submission_id: Optional[str] = None
    broker_status: str = ""


def _default_market_clock() -> bool:
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    if now.weekday() >= 5:
        return False
    session_start = dt_time(9, 0)
    session_end = dt_time(15, 30)
    return session_start <= now.time() <= session_end


def _default_data_fresh() -> bool:
    return True


class KISBroker:
    """Plain structural Broker backed by KIS order/query REST calls."""

    def __init__(
        self,
        *,
        order_adapter: Any,
        account: KisOrderAccount,
        tracked_positions: Optional[Sequence[Position]] = None,
        market_clock: Optional[Callable[[], bool]] = None,
        data_fresh: Optional[Callable[[], bool]] = None,
        evidence_sink: Optional[OrderEvidenceSink] = None,
        pre_submit_quote_reader: Optional[Callable[[str], Any]] = None,
        clock: Optional[Callable[[], datetime]] = None,
        freshness_policy_version: str = "quote-freshness-v1",
        _test_only_allow_unguarded_mutation: bool = False,
    ) -> None:
        self._order_adapter = order_adapter
        self._account = account
        self._positions: Dict[str, Position] = {
            position.ticker.value: position for position in (tracked_positions or ())
        }
        self._market_clock = market_clock or _default_market_clock
        self._data_fresh = data_fresh or _default_data_fresh
        self._last_reconciliation: Optional[OrderReconciliation] = None
        self._evidence_sink = evidence_sink
        self._pre_submit_quote_reader = pre_submit_quote_reader
        self._clock = clock or (lambda: datetime.now(ZoneInfo("Asia/Seoul")))
        self._freshness_policy_version = freshness_policy_version
        self._test_only_allow_unguarded_mutation = bool(
            _test_only_allow_unguarded_mutation
        )

    @classmethod
    def for_test_legacy_mutation(cls, **kwargs: Any) -> "KISBroker":
        """Construct the sole offline-fixture compatibility seam.

        Production composition must use paired fresh account truth, lease
        authority, and source-decision revalidation.  This deliberately named
        constructor exists only for legacy, non-network test fixtures.
        """

        kwargs["_test_only_allow_unguarded_mutation"] = True
        return cls(**kwargs)

    def set_evidence_sink(self, sink: OrderEvidenceSink) -> None:
        self._evidence_sink = sink

    @property
    def last_reconciliation(self) -> Optional[OrderReconciliation]:
        return self._last_reconciliation

    def get_position(self, ticker: Ticker) -> Optional[Position]:
        return self._positions.get(ticker.value)

    def place_order(
        self, order: Order, *, order_intent_id: Optional[str] = None,
        origin_run_id: Optional[str] = None, observer_run_id: Optional[str] = None,
        portfolio_refresh: Optional[Callable[[str], PortfolioSnapshot]] = None,
        lease_guard: Any = None,
        cycle_snapshot_id: Optional[str] = None,
        trigger_revalidator: Optional[Callable[[PortfolioSnapshot, Money], bool]] = None,
    ) -> str:
        """Place one order through the fresh-truth, evidence-first boundary."""

        paired_capability = (
            portfolio_refresh is not None
            and lease_guard is not None
            and trigger_revalidator is not None
        )
        if not paired_capability and not self._test_only_allow_unguarded_mutation:
            raise MarketClosedError(
                "KIS order skipped: paired fresh truth, lease, and revalidator are required"
            )
        self._preflight()
        intent_id = order_intent_id or str(uuid.uuid4())
        origin = origin_run_id or "unattributed"
        observer = observer_run_id or origin
        snapped_price = snap_to_tick(order.limit_price.amount, side=order.side)
        client_ref = self._local_client_ref(order)
        self._emit(OrderEvent(
            order_intent_id=intent_id, origin_run_id=origin, observer_run_id=observer,
            ticker=order.ticker.value, event_type=OrderEventType.INTENT_CREATED,
            side=order.side.value, requested_qty=order.quantity,
            detail={"local_client_ref": client_ref, "snapped_price": snapped_price},
        ))

        if (portfolio_refresh is None) != (lease_guard is None):
            raise MarketClosedError(
                "KIS order skipped: portfolio refresh and lease guard are both required"
            )
        refresh_snapshot: PortfolioSnapshot | None = None
        if portfolio_refresh is not None:
            try:
                refresh_snapshot = portfolio_refresh(order.ticker.value)
                order = self._regate_order(order, refresh_snapshot)
            except MarketClosedError:
                raise
            except Exception:
                raise MarketClosedError(
                    "KIS order skipped: affected-ticker portfolio refresh failed"
                ) from None

        existing = self._find_existing_order(order)
        self._emit(OrderEvent(
            order_intent_id=intent_id, origin_run_id=origin, observer_run_id=observer,
            ticker=order.ticker.value, event_type=OrderEventType.DUPLICATE_CHECKED,
            side=order.side.value, requested_qty=order.quantity,
            broker_order_id=existing, broker_status="MATCHED" if existing else "CLEAR",
            detail={
                "cycle_snapshot_id": cycle_snapshot_id,
                "refresh_snapshot_id": (
                    refresh_snapshot.snapshot_id if refresh_snapshot is not None else None
                ),
            },
        ))
        if existing is not None:
            self._last_reconciliation = OrderReconciliation(
                existing, order.ticker.value, order.quantity, 0, order.quantity,
                client_ref, intent_id, None, "DUPLICATE_SUPPRESSED",
            )
            self._emit(OrderEvent(
                order_intent_id=intent_id, origin_run_id=origin, observer_run_id=observer,
                ticker=order.ticker.value, event_type=OrderEventType.RECONCILED,
                broker_order_id=existing, side=order.side.value,
                requested_qty=order.quantity, filled_qty=0, unfilled_qty=order.quantity,
                broker_status="DUPLICATE_SUPPRESSED",
                detail={"matching_broker_order_id": existing},
            ))
            return existing

        submission_id = str(uuid.uuid4())
        if self._pre_submit_quote_reader is not None:
            quote = self._pre_submit_quote_reader(order.ticker.value)
            checked_at = self._clock()
            observed_at = getattr(quote, "observed_at", None)
            health = getattr(quote, "health", None)
            freshness = None
            if (
                health is not None
                and health.status is SourceStatus.AVAILABLE
                and observed_at is not None
            ):
                # Calendar is irrelevant to this pure timestamp predicate.
                class _UnusedCalendar:
                    def is_trading_day(self, day): return None
                    def previous_trading_day(self, day): return None
                freshness = MarketCyclePolicy(_UnusedCalendar()).quote_freshness(
                    QuoteObservation(observed_at), checked_at
                )
            facts = FreshnessEvidence(
                observed_at=observed_at.isoformat() if observed_at else None,
                checked_at=checked_at.isoformat(),
                age_seconds=freshness.age_seconds if freshness else None,
                verdict="PASS" if freshness is not None and freshness.fresh else "BLOCK",
                reason=freshness.reason if freshness else "quote unavailable",
                policy_version=self._freshness_policy_version,
            )
            passed = freshness is not None and freshness.fresh
            self._emit(OrderEvent(
                    order_intent_id=intent_id, origin_run_id=origin,
                    observer_run_id=observer, ticker=order.ticker.value,
                    event_type=(OrderEventType.FRESHNESS_CHECKED if passed else OrderEventType.FRESHNESS_BLOCKED),
                    submission_id=submission_id, side=order.side.value,
                    requested_qty=order.quantity, broker_status="STALE_QUOTE",
                    detail=facts.detail(), observed_at=facts.observed_at,
                ))
            if not passed:
                raise MarketClosedError("KIS order skipped: pre-submit quote is stale")
            quote_money = getattr(quote, "price", None)
            if not isinstance(quote_money, Money):
                raise MarketClosedError("KIS order skipped: quote price is invalid")
            order = replace(order, limit_price=quote_money)
            if refresh_snapshot is not None and trigger_revalidator is not None:
                try:
                    actionable = bool(trigger_revalidator(refresh_snapshot, quote_money))
                except Exception:
                    actionable = False
                if not actionable:
                    raise MarketClosedError("EXIT_NO_LONGER_ACTIONABLE")
            if refresh_snapshot is not None and order.side is OrderSide.BUY:
                affordable = int(
                    refresh_snapshot.account.available_cash // quote_money.amount
                )
                if affordable <= 0:
                    raise MarketClosedError("KIS order skipped: BUY cash gate cleared")
                order = replace(order, quantity=min(order.quantity, affordable))
            snapped_price = snap_to_tick(order.limit_price.amount, side=order.side)
        if lease_guard is not None:
            expected_scope = getattr(lease_guard, "account_scope_hash", None)
            if (
                expected_scope is not None
                and refresh_snapshot is not None
                and expected_scope != refresh_snapshot.account_scope_hash
            ):
                raise MarketClosedError("KIS order skipped: account scope changed")
            try:
                lease_guard.assert_active_owner()
            except Exception:
                raise MarketClosedError(
                    "KIS order skipped: mutation ownership lost"
                ) from None
        owner_token = str(getattr(lease_guard, "owner_token", ""))
        owner_token_hash = (
            hashlib.sha256(owner_token.encode("utf-8")).hexdigest()
            if owner_token
            else None
        )
        self._emit(OrderEvent(
            order_intent_id=intent_id, origin_run_id=origin, observer_run_id=observer,
            ticker=order.ticker.value, event_type=OrderEventType.SUBMISSION_ATTEMPTED,
            submission_id=submission_id, side=order.side.value,
            requested_qty=order.quantity,
            detail={
                "cycle_snapshot_id": cycle_snapshot_id,
                "refresh_snapshot_id": (
                    refresh_snapshot.snapshot_id if refresh_snapshot is not None else None
                ),
                "lease_owner_fingerprint": owner_token_hash,
            },
        ))
        try:
            result = self._order_adapter.place_order_cash(
                account=self._account, order=order, snapped_price=snapped_price,
            )
        except Exception as exc:
            self._emit(OrderEvent(
                order_intent_id=intent_id, origin_run_id=origin, observer_run_id=observer,
                ticker=order.ticker.value, event_type=OrderEventType.SUBMISSION_AMBIGUOUS,
                submission_id=submission_id, side=order.side.value,
                requested_qty=order.quantity, broker_status="ACK_UNKNOWN",
                detail={"error_type": type(exc).__name__},
            ))
            self._last_reconciliation = OrderReconciliation(
                "", order.ticker.value, order.quantity, 0, order.quantity,
                client_ref, intent_id, submission_id, "AMBIGUOUS_SUBMISSION",
            )
            raise AmbiguousSubmissionError(
                order_intent_id=intent_id, submission_id=submission_id
            ) from None
        self._emit(OrderEvent(
            order_intent_id=intent_id, origin_run_id=origin, observer_run_id=observer,
            ticker=order.ticker.value, event_type=OrderEventType.SUBMISSION_ACCEPTED,
            submission_id=submission_id, broker_order_id=result.order_id,
            side=order.side.value, requested_qty=order.quantity, broker_status="ACCEPTED",
        ))

        fill = self._read_fill_status(
            ticker=order.ticker.value,
            order_id=result.order_id,
        )
        self._reconcile_position(order=order, fill=fill, snapped_price=snapped_price)
        self._last_reconciliation = OrderReconciliation(
            order_id=result.order_id,
            ticker=order.ticker.value,
            requested_qty=order.quantity,
            filled_qty=fill.filled_qty,
            remaining_qty=fill.remaining_qty,
            local_client_ref=client_ref,
            order_intent_id=intent_id,
            submission_id=submission_id,
            broker_status="RECONCILED",
        )
        self._emit(OrderEvent(
            order_intent_id=intent_id, origin_run_id=origin, observer_run_id=observer,
            ticker=order.ticker.value, event_type=OrderEventType.RECONCILED,
            submission_id=submission_id, broker_order_id=result.order_id,
            side=order.side.value, requested_qty=order.quantity,
            filled_qty=fill.filled_qty, unfilled_qty=fill.remaining_qty,
            broker_status="FILLED" if fill.remaining_qty == 0 else "PARTIAL",
        ))
        return result.order_id

    @staticmethod
    def _regate_order(order: Order, snapshot: PortfolioSnapshot) -> Order:
        """Recalculate a current order from complete affected-ticker truth."""

        if not isinstance(snapshot, PortfolioSnapshot) or not snapshot.mutation_capable:
            raise MarketClosedError("KIS order skipped: portfolio truth is incomplete")
        if any(
            item.ticker == order.ticker.value
            and item.side == "SELL"
            and item.status in {"OPEN", "PARTIAL"}
            for item in snapshot.orders
        ):
            raise MarketClosedError(
                "KIS order skipped: open SELL requires reconciliation"
            )
        if order.side is OrderSide.SELL:
            holding = next(
                (
                    item
                    for item in snapshot.holdings
                    if item.ticker == order.ticker.value
                ),
                None,
            )
            if holding is None or holding.orderable_quantity <= 0:
                raise MarketClosedError("KIS order skipped: no orderable holding")
            return replace(order, quantity=holding.orderable_quantity)
        if snapshot.account.available_cash <= 0:
            raise MarketClosedError("KIS order skipped: no available cash")
        return order

    def reconcile_order(
        self, *, order_intent_id: str, origin_run_id: str, observer_run_id: str,
        ticker: str, broker_order_id: str, submission_id: Optional[str] = None,
    ) -> OrderReconciliation:
        """Append later broker truth without mutating the originating facts."""
        fill = self._read_fill_status(ticker=ticker, order_id=broker_order_id)
        evidence = OrderReconciliation(
            broker_order_id, ticker, fill.ordered_qty, fill.filled_qty,
            fill.remaining_qty, "", order_intent_id, submission_id, "RECONCILED",
        )
        self._last_reconciliation = evidence
        self._emit(OrderEvent(
            order_intent_id=order_intent_id, origin_run_id=origin_run_id,
            observer_run_id=observer_run_id, ticker=ticker,
            event_type=OrderEventType.BROKER_OBSERVED, submission_id=submission_id,
            broker_order_id=broker_order_id, requested_qty=fill.ordered_qty,
            filled_qty=fill.filled_qty, unfilled_qty=fill.remaining_qty,
            broker_status="FILLED" if fill.remaining_qty == 0 else "PARTIAL",
        ))
        return evidence

    def _emit(self, event: OrderEvent) -> None:
        if self._evidence_sink is not None:
            sanitize_detail(event.detail)
            self._evidence_sink(event)

    def _preflight(self) -> None:
        if not self._market_clock():
            raise MarketClosedError("KIS order skipped: market is closed")
        if not self._data_fresh():
            raise MarketClosedError("KIS order skipped: market data is stale")

    def _local_client_ref(self, order: Order) -> str:
        # KIS honors no client idempotency key; this is only a local audit tag.
        return f"local:{order.ticker.value}:{order.side.value}:{order.quantity}"

    def _find_existing_order(self, order: Order) -> Optional[str]:
        daily = self._order_adapter.inquire_daily_ccld(ticker=order.ticker.value)
        if daily.health.status is not SourceStatus.AVAILABLE or daily.output is None:
            raise KisOrderError(f"daily order query unavailable: {daily.health.reason}")
        rows = daily.output if isinstance(daily.output, list) else [daily.output]
        for row in rows:
            if not isinstance(row, dict):
                continue
            order_id = str(row.get("odno") or row.get("ODNO") or "").strip()
            ticker = str(row.get("pdno") or row.get("PDNO") or "").strip()
            quantity = self._optional_int(row.get("ord_qty") or row.get("ORD_QTY"))
            raw_side = (
                row.get("sll_buy_dvsn_cd")
                or row.get("SLL_BUY_DVSN_CD")
                or row.get("side")
                or row.get("SIDE")
            )
            side = self._normalize_broker_side(raw_side)
            if not order_id or ticker != order.ticker.value or quantity != order.quantity:
                continue
            if side is None or side == order.side.value:
                return order_id
        self._order_adapter.inquire_balance()
        return None

    def _read_fill_status(self, *, ticker: str, order_id: str) -> FillStatus:
        if hasattr(self._order_adapter, "read_fill_status"):
            return self._order_adapter.read_fill_status(ticker=ticker, order_id=order_id)
        daily = self._order_adapter.inquire_daily_ccld(ticker=ticker, order_id=order_id)
        if daily.health.status is not SourceStatus.AVAILABLE or daily.output is None:
            raise KisOrderError(f"fill readback unavailable: {daily.health.reason}")
        return self._order_adapter.parse_fill_status(
            daily.output, order_id=order_id, ticker=ticker
        )

    def _reconcile_position(
        self, *, order: Order, fill: FillStatus, snapped_price: int
    ) -> None:
        ticker_key = order.ticker.value
        current = self._positions.get(ticker_key)
        if fill.filled_qty <= 0:
            return

        price = Money(float(snapped_price), order.limit_price.currency)
        if order.side is OrderSide.BUY:
            if current is None:
                self._positions[ticker_key] = Position(
                    ticker=order.ticker,
                    quantity=fill.filled_qty,
                    average_price=price,
                )
                return
            total_qty = current.quantity + fill.filled_qty
            weighted = (
                current.quantity * current.average_price.amount
                + fill.filled_qty * price.amount
            )
            self._positions[ticker_key] = Position(
                ticker=order.ticker,
                quantity=total_qty,
                average_price=Money(weighted / total_qty, price.currency),
            )
            return

        if current is None:
            return
        remaining = max(0, current.quantity - fill.filled_qty)
        if remaining == 0:
            self._positions.pop(ticker_key, None)
        else:
            self._positions[ticker_key] = Position(
                ticker=order.ticker,
                quantity=remaining,
                average_price=current.average_price,
            )

    @staticmethod
    def _optional_int(value: Any) -> Optional[int]:
        try:
            return int(str(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_broker_side(value: Any) -> Optional[str]:
        if value is None or value == "":
            return None
        normalized = str(value).strip().upper()
        if normalized in {"BUY", "02"}:
            return OrderSide.BUY.value
        if normalized in {"SELL", "01"}:
            return OrderSide.SELL.value
        return normalized


def build_kis_broker(
    settings: Any,
    *,
    token_manager: Optional[KisTokenManager],
    account: Optional[KisOrderAccount] = None,
    client: Any = None,
    pre_submit_quote_reader: Optional[Callable[[str], Any]] = None,
) -> KISBroker:
    """Build a KISBroker from Settings using the caller-owned token manager."""

    if token_manager is None:
        raise ValueError(
            "build_kis_broker requires the shared KisTokenManager; the factory "
            "does not open a second token flow"
        )
    if account is None:
        raise ValueError("build_kis_broker requires a KIS account descriptor")

    active_kis = settings.active_kis
    adapter = KisOrderAdapter(
        token_manager=token_manager,
        domain=active_kis.domain,
        tr_id_profile=active_kis.tr_id_profile,
        client=client,
        min_interval_seconds=settings.kis_min_interval_seconds,
        max_retries=settings.kis_max_retries,
        retry_backoff_seconds=settings.kis_retry_backoff_seconds,
        timeout_seconds=settings.order_timeout_seconds,
    )
    return KISBroker(
        order_adapter=adapter,
        account=account,
        pre_submit_quote_reader=pre_submit_quote_reader,
    )
