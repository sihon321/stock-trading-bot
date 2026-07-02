"""Structural KIS Broker implementation with broker-truth reconciliation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time as dt_time
from typing import Any, Callable, Dict, Optional, Sequence
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


class MarketClosedError(RuntimeError):
    """Raised when the order pre-flight guard fails safe to HOLD/skip."""


@dataclass(frozen=True)
class OrderReconciliation:
    """Requested-vs-filled audit state from the latest broker readback."""

    order_id: str
    ticker: str
    requested_qty: int
    filled_qty: int
    remaining_qty: int
    local_client_ref: str


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
    ) -> None:
        self._order_adapter = order_adapter
        self._account = account
        self._positions: Dict[str, Position] = {
            position.ticker.value: position for position in (tracked_positions or ())
        }
        self._market_clock = market_clock or _default_market_clock
        self._data_fresh = data_fresh or _default_data_fresh
        self._last_reconciliation: Optional[OrderReconciliation] = None

    @property
    def last_reconciliation(self) -> Optional[OrderReconciliation]:
        return self._last_reconciliation

    def get_position(self, ticker: Ticker) -> Optional[Position]:
        return self._positions.get(ticker.value)

    def place_order(self, order: Order) -> str:
        """Place a KIS order after query-before-POST reconciliation."""

        self._preflight()
        snapped_price = snap_to_tick(order.limit_price.amount, side=order.side)
        client_ref = self._local_client_ref(order)

        existing = self._find_existing_order(order)
        if existing is not None:
            return existing

        result = self._order_adapter.place_order_cash(
            account=self._account,
            order=order,
            snapped_price=snapped_price,
        )

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
        )
        return result.order_id

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
    )
