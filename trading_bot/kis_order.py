"""KIS domestic-stock order/query adapter for real order readiness.

This module reuses the shared :class:`~trading_bot.kis_auth.KisTokenManager`
and mirrors the Phase 3 quote adapter's bounded retry and fail-safe response
validation for query legs. The order-cash POST is intentionally single-shot and
is never decorated with tenacity retry.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from typing import Any, Optional, Union

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from trading_bot.data_models import SourceHealth, SourceStatus
from trading_bot.domain import Order, OrderSide
from trading_bot.kis_auth import KisAuthError, KisTokenManager

_SOURCE = "kis_order"
_DAILY_CCLD_PATH = "/uapi/domestic-stock/v1/trading/inquire-daily-ccld"
_BALANCE_PATH = "/uapi/domestic-stock/v1/trading/inquire-balance"
_HASHKEY_PATH = "/uapi/hashkey"
_ORDER_CASH_PATH = "/uapi/domestic-stock/v1/trading/order-cash"
_MARKET_DIV_CODE = "J"

_TICK_BANDS = (
    (2_000, 1),
    (5_000, 5),
    (20_000, 10),
    (50_000, 50),
    (100_000, 100),
    (200_000, 100),
    (500_000, 500),
    (float("inf"), 1_000),
)


class _TransientOrderQueryError(Exception):
    """Internal marker for retryable KIS account-query failures."""


class KisOrderError(RuntimeError):
    """Raised when a single-shot KIS order operation fails safe."""


@dataclass(frozen=True)
class KisOrderAccount:
    """KIS account tuple required by domestic stock order endpoints."""

    cano: str
    account_product_code: str


@dataclass(frozen=True)
class KisOrderTrIds:
    """Mode-derived TR_ID family for domestic stock trading endpoints."""

    buy: str
    sell: str
    daily_fills: str
    balance: str


@dataclass(frozen=True)
class KisOrderQueryResult:
    """Validated raw KIS account-query output paired with normalized health."""

    output: Optional[Union[dict, list]]
    health: SourceHealth


@dataclass(frozen=True)
class KisOrderPostResult:
    """Broker-assigned identifiers from a successful order-cash POST."""

    order_id: str
    krx_forwarding_order_orgno: str = ""
    raw_output: Optional[dict] = None


@dataclass(frozen=True)
class FillStatus:
    """Validated fill readback from the confirmed TTTC8001R field family."""

    order_id: str
    ticker: str
    ordered_qty: int
    filled_qty: int
    remaining_qty: int


def _unavailable(reason: str) -> KisOrderQueryResult:
    return KisOrderQueryResult(
        output=None,
        health=SourceHealth(source=_SOURCE, status=SourceStatus.UNAVAILABLE, reason=reason),
    )


def _available(output: Union[dict, list]) -> KisOrderQueryResult:
    return KisOrderQueryResult(
        output=output,
        health=SourceHealth(source=_SOURCE, status=SourceStatus.AVAILABLE, reason="ok"),
    )


def _is_valid_ticker(ticker: Any) -> bool:
    return isinstance(ticker, str) and len(ticker) == 6 and ticker.isdigit()


def _normalize_side(side: Union[OrderSide, str]) -> str:
    value = side.value if isinstance(side, OrderSide) else str(side)
    return value.upper()


def snap_to_tick(price: float, *, side: Union[OrderSide, str]) -> int:
    """Snap a KRW limit price down to a valid KRX 2023-reform tick band.

    [ASSUMED] The 1,000-2,000 KRW band uses a 1 KRW tick, and SELL uses the
    same conservative down-snap policy as BUY until the operator chooses a
    different side-specific policy.
    """

    try:
        numeric_price = float(price)
    except (TypeError, ValueError):
        raise ValueError("price must be numeric") from None
    if not math.isfinite(numeric_price) or numeric_price <= 0:
        raise ValueError("price must be positive and finite")

    side_value = _normalize_side(side)
    if side_value not in {OrderSide.BUY.value, OrderSide.SELL.value}:
        raise ValueError(f"unsupported order side: {side!r}")

    for upper, tick in _TICK_BANDS:
        if numeric_price < upper:
            return int(numeric_price // tick) * tick
    return int(numeric_price)


def _derive_tr_ids(tr_id_profile: str) -> KisOrderTrIds:
    profile = str(tr_id_profile).strip().lower()
    if profile == "mock":
        return KisOrderTrIds(
            buy="VTTC0802U",
            sell="VTTC0801U",
            daily_fills="VTTC8001R",
            balance="VTTC8434R",
        )
    if profile == "real":
        return KisOrderTrIds(
            buy="TTTC0802U",
            sell="TTTC0801U",
            daily_fills="TTTC8001R",
            balance="TTTC8434R",
        )
    raise ValueError(f"unsupported KIS tr_id_profile: {tr_id_profile!r}")


class KisOrderAdapter:
    """Synchronous KIS account-query adapter using the shared token manager."""

    def __init__(
        self,
        *,
        token_manager: KisTokenManager,
        domain: str,
        tr_id_profile: str,
        client: Any = None,
        min_interval_seconds: float = 0.5,
        max_retries: int = 3,
        retry_backoff_seconds: float = 1.0,
        timeout_seconds: float = 5.0,
    ) -> None:
        if client is None:
            import httpx

            client = httpx.Client()
        self._token_manager = token_manager
        self._domain = domain
        self._tr_ids = _derive_tr_ids(tr_id_profile)
        self._client = client
        self._min_interval_seconds = float(min_interval_seconds)
        self._max_retries = max(1, int(max_retries))
        self._retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))
        self._timeout_seconds = float(timeout_seconds)
        self._last_request_at: Optional[float] = None

    def __repr__(self) -> str:  # pragma: no cover - trivial redaction
        return f"KisOrderAdapter(domain={self._domain!r}, tr_ids={self._tr_ids!r})"

    @property
    def tr_ids(self) -> KisOrderTrIds:
        """Return the mode-derived TR_ID family."""

        return self._tr_ids

    def inquire_daily_ccld(
        self, *, ticker: Optional[str] = None, order_id: Optional[str] = None
    ) -> KisOrderQueryResult:
        """Fetch recent same-day KIS executions/orders as untrusted raw output."""

        if ticker is not None and not _is_valid_ticker(ticker):
            return _unavailable("ticker must be a 6-digit KRX code")
        try:
            token = self._token_manager.get_token()
            body = self._fetch_query_body(
                path=_DAILY_CCLD_PATH,
                tr_id=self._tr_ids.daily_fills,
                params=self._daily_params(ticker=ticker, order_id=order_id),
                token=token,
            )
        except KisAuthError:
            return _unavailable("KIS auth unavailable for order query")
        except _TransientOrderQueryError as exc:
            return _unavailable(str(exc))
        return self._parse_query_output(body, expected_shape=list)

    def inquire_balance(self) -> KisOrderQueryResult:
        """Fetch KIS account balance as untrusted raw output."""

        try:
            token = self._token_manager.get_token()
            body = self._fetch_query_body(
                path=_BALANCE_PATH,
                tr_id=self._tr_ids.balance,
                params=self._balance_params(),
                token=token,
            )
        except KisAuthError:
            return _unavailable("KIS auth unavailable for order query")
        except _TransientOrderQueryError as exc:
            return _unavailable(str(exc))
        return self._parse_query_output(body, expected_shape=dict)

    def place_order_cash(
        self, *, account: KisOrderAccount, order: Order, snapped_price: int
    ) -> KisOrderPostResult:
        """Submit one limit order-cash POST and return the broker order ID.

        This method deliberately has no tenacity retry wrapper. If the hashkey or
        order POST fails, the exception propagates after exactly one order-cash
        POST attempt so callers can re-query broker truth before any resend.
        """

        body = self.build_order_body(
            account=account, order=order, snapped_price=snapped_price
        )
        token = self._token_manager.get_token()
        hashkey = self._request_hashkey(body=body)
        tr_id = self._tr_ids.buy if order.side is OrderSide.BUY else self._tr_ids.sell
        headers = self._headers(token=token, tr_id=tr_id, hashkey=hashkey)

        url = self._domain.rstrip("/") + _ORDER_CASH_PATH
        try:
            response = self._client.post(
                url, json=body, headers=headers, timeout=self._timeout_seconds
            )
        except Exception as exc:  # noqa: BLE001 - never retry a real order POST.
            raise KisOrderError(f"order POST failed: {type(exc).__name__}") from exc

        status = getattr(response, "status_code", None)
        if status is None or int(status) >= 400:
            raise KisOrderError(f"order POST returned HTTP {status}")

        try:
            payload = response.json()
        except Exception as exc:  # noqa: BLE001 - malformed body is terminal.
            raise KisOrderError("order POST response was not valid JSON") from exc

        output = self._validated_response_output(payload, expected_shape=dict)
        order_id = str(output.get("ODNO") or output.get("odno") or "").strip()
        if not order_id:
            raise KisOrderError("order POST response missing ODNO")
        krx_orgno = str(output.get("KRX_FWDG_ORD_ORGNO") or "").strip()
        return KisOrderPostResult(
            order_id=order_id,
            krx_forwarding_order_orgno=krx_orgno,
            raw_output=output,
        )

    def parse_fill_status(
        self, output: Union[dict, list], *, order_id: str, ticker: str
    ) -> FillStatus:
        """Parse confirmed TTTC8001R fill fields for one broker order."""

        rows = output if isinstance(output, list) else [output]
        matched: Optional[dict] = None
        for row in rows:
            if not isinstance(row, dict):
                continue
            row_order_id = str(row.get("odno") or row.get("ODNO") or "").strip()
            row_ticker = str(row.get("pdno") or row.get("PDNO") or "").strip()
            if row_order_id == str(order_id) and (not ticker or row_ticker == ticker):
                matched = row
                break
        if matched is None:
            raise KisOrderError(f"fill status not found for order {order_id}")

        ordered_qty = self._parse_quantity(matched, "ord_qty")
        filled_qty = self._parse_quantity(matched, "tot_ccld_qty")
        remaining_qty = self._parse_quantity(matched, "rmn_qty")
        return FillStatus(
            order_id=str(order_id),
            ticker=str(ticker),
            ordered_qty=ordered_qty,
            filled_qty=filled_qty,
            remaining_qty=remaining_qty,
        )

    def read_fill_status(self, *, ticker: str, order_id: str) -> FillStatus:
        """Query recent executions and parse the confirmed fill-status fields."""

        result = self.inquire_daily_ccld(ticker=ticker, order_id=order_id)
        if result.health.status is not SourceStatus.AVAILABLE or result.output is None:
            raise KisOrderError(f"fill readback unavailable: {result.health.reason}")
        return self.parse_fill_status(result.output, order_id=order_id, ticker=ticker)

    @staticmethod
    def build_order_body(
        *, account: KisOrderAccount, order: Order, snapped_price: int
    ) -> dict:
        if order.quantity <= 0:
            raise ValueError("order quantity must be positive")
        if order.limit_price.currency != "KRW":
            raise ValueError("KIS domestic stock orders require KRW limit prices")
        if not _is_valid_ticker(order.ticker.value):
            raise ValueError("order ticker must be a 6-digit KRX code")
        if int(snapped_price) <= 0:
            raise ValueError("snapped_price must be positive")
        return {
            "CANO": account.cano,
            "ACNT_PRDT_CD": account.account_product_code,
            "PDNO": order.ticker.value,
            "ORD_DVSN": "00",
            "ORD_QTY": str(order.quantity),
            "ORD_UNPR": str(int(snapped_price)),
        }

    def _fetch_query_body(
        self, *, path: str, tr_id: str, params: dict, token: str
    ) -> Any:
        @retry(
            reraise=True,
            stop=stop_after_attempt(self._max_retries),
            wait=wait_fixed(self._retry_backoff_seconds),
            retry=retry_if_exception_type(_TransientOrderQueryError),
        )
        def _attempt() -> Any:
            return self._query_request(path=path, tr_id=tr_id, params=params, token=token)

        return _attempt()

    def _query_request(self, *, path: str, tr_id: str, params: dict, token: str) -> Any:
        self._respect_min_interval()

        url = self._domain.rstrip("/") + path
        headers = self._headers(token=token, tr_id=tr_id)

        try:
            response = self._client.get(
                url, params=params, headers=headers, timeout=self._timeout_seconds
            )
        except Exception as exc:  # noqa: BLE001 - transient transport failure.
            raise _TransientOrderQueryError(
                f"order query failed: {type(exc).__name__}"
            ) from None

        status = getattr(response, "status_code", None)
        if status is None or int(status) >= 400:
            raise _TransientOrderQueryError(f"order query returned HTTP {status}")

        try:
            return response.json()
        except Exception:  # noqa: BLE001 - malformed body is terminal.
            return {"__nonjson__": True}

    def _parse_query_output(self, body: Any, *, expected_shape: type) -> KisOrderQueryResult:
        try:
            output = self._validated_response_output(body, expected_shape=expected_shape)
        except KisOrderError as exc:
            return _unavailable(str(exc))
        return _available(output)

    def _request_hashkey(self, *, body: dict) -> str:
        url = self._domain.rstrip("/") + _HASHKEY_PATH
        headers = {
            "content-type": "application/json",
            "appkey": getattr(self._token_manager, "app_key", ""),
            "appsecret": getattr(self._token_manager, "app_secret", ""),
        }
        try:
            response = self._client.post(
                url, json=body, headers=headers, timeout=self._timeout_seconds
            )
        except Exception as exc:  # noqa: BLE001 - fail before placing any order.
            raise KisOrderError(f"hashkey request failed: {type(exc).__name__}") from exc
        status = getattr(response, "status_code", None)
        if status is None or int(status) >= 400:
            raise KisOrderError(f"hashkey request returned HTTP {status}")
        try:
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            raise KisOrderError("hashkey response was not valid JSON") from exc
        hashkey = str(payload.get("HASH") or payload.get("hashkey") or "").strip()
        if not hashkey:
            raise KisOrderError("hashkey response missing HASH")
        return hashkey

    def _headers(
        self, *, token: str, tr_id: str, hashkey: Optional[str] = None
    ) -> dict:
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {token}",
            "appkey": getattr(self._token_manager, "app_key", ""),
            "appsecret": getattr(self._token_manager, "app_secret", ""),
            "tr_id": tr_id,
            "custtype": "P",
        }
        if hashkey is not None:
            headers["hashkey"] = hashkey
        return headers

    def _validated_response_output(self, body: Any, *, expected_shape: type) -> Any:
        if not isinstance(body, dict) or body.get("__nonjson__"):
            raise KisOrderError("order response was not valid JSON")

        rt_cd = body.get("rt_cd")
        if rt_cd is not None and str(rt_cd) != "0":
            raise KisOrderError(f"order response rt_cd={rt_cd}")

        output = body.get("output")
        if not isinstance(output, expected_shape):
            raise KisOrderError("order response missing output")
        if not self._numeric_fields_are_valid(output):
            raise KisOrderError("order response numeric field is invalid")

        return output

    @staticmethod
    def _parse_quantity(row: dict, field: str) -> int:
        value = row.get(field)
        try:
            quantity = int(str(value))
        except (TypeError, ValueError):
            raise KisOrderError(f"fill status field {field} is not an integer") from None
        if quantity < 0:
            raise KisOrderError(f"fill status field {field} is negative")
        return quantity

    def _numeric_fields_are_valid(self, output: Union[dict, list]) -> bool:
        candidates = output if isinstance(output, list) else [output]
        for item in candidates:
            if not isinstance(item, dict):
                return False
            for key, value in item.items():
                if value is None or value == "":
                    continue
                if not self._looks_numeric_field(key):
                    continue
                try:
                    number = float(value)
                except (TypeError, ValueError):
                    return False
                if not math.isfinite(number):
                    return False
        return True

    @staticmethod
    def _looks_numeric_field(key: str) -> bool:
        lowered = key.lower()
        numeric_fragments = (
            "amt",
            "qty",
            "prc",
            "prpr",
            "unpr",
            "ord",
            "ccld",
            "rmn",
            "evlu",
            "pchs",
        )
        return any(fragment in lowered for fragment in numeric_fragments)

    @staticmethod
    def _daily_params(*, ticker: Optional[str], order_id: Optional[str]) -> dict:
        params = {
            "FID_COND_MRKT_DIV_CODE": _MARKET_DIV_CODE,
            "FID_INPUT_ISCD": ticker or "",
        }
        if order_id:
            params["ODNO"] = order_id
        return params

    @staticmethod
    def _balance_params() -> dict:
        return {
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }

    def _respect_min_interval(self) -> None:
        interval = self._min_interval_seconds
        if interval <= 0:
            self._last_request_at = time.monotonic()
            return
        now = time.monotonic()
        if self._last_request_at is not None:
            elapsed = now - self._last_request_at
            if elapsed < interval:
                time.sleep(interval - elapsed)
        self._last_request_at = time.monotonic()
