"""KIS domestic-stock account-query foundation for real order readiness.

This module reuses the shared :class:`~trading_bot.kis_auth.KisTokenManager`
and mirrors the Phase 3 quote adapter's bounded retry and fail-safe response
validation. Task 1 intentionally exposes only account query legs, TR_ID
selection, and tick snapping; the dangerous placement path and fill parser are
deferred until the operator confirms the KIS field spellings.
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
from trading_bot.domain import OrderSide
from trading_bot.kis_auth import KisAuthError, KisTokenManager

_SOURCE = "kis_order"
_DAILY_CCLD_PATH = "/uapi/domestic-stock/v1/trading/inquire-daily-ccld"
_BALANCE_PATH = "/uapi/domestic-stock/v1/trading/inquire-balance"
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
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {token}",
            "appkey": getattr(self._token_manager, "app_key", ""),
            "appsecret": getattr(self._token_manager, "app_secret", ""),
            "tr_id": tr_id,
            "custtype": "P",
        }

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
        if not isinstance(body, dict) or body.get("__nonjson__"):
            return _unavailable("order query response was not valid JSON")

        rt_cd = body.get("rt_cd")
        if rt_cd is not None and str(rt_cd) != "0":
            return _unavailable(f"order query response rt_cd={rt_cd}")

        output = body.get("output")
        if not isinstance(output, expected_shape):
            return _unavailable("order query response missing output")
        if not self._numeric_fields_are_valid(output):
            return _unavailable("order query numeric field is invalid")

        return _available(output)

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
