"""KIS domestic-stock current-price adapter (DATA-03, D-02/D-15).

This module isolates the KIS inquire-price REST endpoint. It obtains auth from
the shared :class:`~trading_bot.kis_auth.KisTokenManager` (never issuing tokens
itself, per D-14), calls the domestic-stock current-price endpoint with TR ID
``FHKST01010100``, and validates the numeric price field before constructing a
:class:`~trading_bot.domain.Money`. Missing, nonnumeric, zero, negative,
throttled, HTTP-error, malformed-JSON, ``rt_cd`` failure, and auth-unavailable
states all normalize to an UNAVAILABLE :class:`~trading_bot.data_models.SourceHealth`
(D-15) so a bad quote can never masquerade as a tradeable ``Money(0)`` (threat
T-03-04-T). Retries are bounded and a minimum request interval is honored to
avoid a denial-of-service retry storm (threat T-03-04-D).

The result feeds ``DataContext.current_price`` in Plan 03-06 once source-health
policy resolves to AVAILABLE. This adapter contains only the read-only quote
path - order placement and balance/broker reconciliation are Phase 5.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from trading_bot.data_models import SourceHealth, SourceStatus
from trading_bot.domain import Money
from trading_bot.kis_auth import KisAuthError, KisTokenManager

_SOURCE = "kis_quote"
_QUOTE_PATH = "/uapi/domestic-stock/v1/quotations/inquire-price"
_MARKET_DIV_CODE = "J"  # domestic stock/ETF/ETN.
_PRICE_FIELD = "stck_prpr"


class _TransientQuoteError(Exception):
    """Internal marker for retryable transient quote-fetch failures."""


@dataclass(frozen=True)
class KisQuoteResult:
    """A validated current price paired with its normalized source health.

    ``price`` is a :class:`Money` only when ``health.status`` is
    :attr:`SourceStatus.AVAILABLE`; otherwise it is ``None`` so an unavailable
    quote can never be mistaken for a tradeable price.
    """

    price: Optional[Money]
    health: SourceHealth
    observed_at: Optional[datetime] = None


def _unavailable(reason: str) -> KisQuoteResult:
    return KisQuoteResult(
        price=None,
        health=SourceHealth(source=_SOURCE, status=SourceStatus.UNAVAILABLE, reason=reason),
    )


def _is_valid_ticker(ticker: Any) -> bool:
    return isinstance(ticker, str) and len(ticker) == 6 and ticker.isdigit()


class KisQuoteAdapter:
    """Synchronous KIS current-price adapter returning typed health-checked results.

    Args:
        token_manager: Shared token source exposing ``get_token()`` and the KIS
            app key/secret for request headers (D-14). The single credential
            source; the adapter never reads independent credential fields.
        domain: KIS REST domain from ``Settings.active_kis.domain``.
        tr_id: Transaction ID for the current-price endpoint (``FHKST01010100``).
        client: Object exposing ``get(url, *, params, headers, timeout)`` returning
            an ``httpx.Response``-like object. Injectable for offline tests.
        min_interval_seconds/max_retries/retry_backoff_seconds/timeout_seconds:
            Phase 3 KIS rate/retry controls from ``Settings``.
    """

    def __init__(
        self,
        *,
        token_manager: KisTokenManager,
        domain: str,
        tr_id: str,
        client: Any = None,
        min_interval_seconds: float = 0.5,
        max_retries: int = 3,
        retry_backoff_seconds: float = 1.0,
        timeout_seconds: float = 5.0,
        clock: Optional[Callable[[], datetime]] = None,
    ) -> None:
        if client is None:
            import httpx

            client = httpx.Client()
        self._token_manager = token_manager
        self._domain = domain
        self._tr_id = tr_id
        self._client = client
        self._min_interval_seconds = float(min_interval_seconds)
        self._max_retries = max(1, int(max_retries))
        self._retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))
        self._timeout_seconds = float(timeout_seconds)
        self._clock = clock or (lambda: datetime.now(ZoneInfo("Asia/Seoul")))
        self._last_request_at: Optional[float] = None

    def __repr__(self) -> str:  # pragma: no cover - trivial redaction
        return f"KisQuoteAdapter(domain={self._domain!r}, tr_id={self._tr_id!r})"

    def fetch_current_price(self, ticker: str) -> KisQuoteResult:
        """Fetch and validate the current price for ``ticker`` (6-digit KRX code)."""

        if not _is_valid_ticker(ticker):
            return _unavailable("ticker must be a 6-digit KRX code")

        try:
            token = self._token_manager.get_token()
        except KisAuthError:
            # Auth is unavailable after its own bounded policy; do not call the API.
            return _unavailable("KIS auth unavailable for quote")

        try:
            body = self._fetch_body(ticker, token)
        except _TransientQuoteError as exc:
            return _unavailable(str(exc))
        except KisAuthError:
            return _unavailable("KIS auth unavailable for quote")

        result = self._parse_price(body)
        if result.price is None:
            return result
        observed_at = self._clock()
        if observed_at.tzinfo is None:
            return _unavailable("quote observation clock was not timezone-aware")
        return KisQuoteResult(result.price, result.health, observed_at)

    def _fetch_body(self, ticker: str, token: str) -> Any:
        @retry(
            reraise=True,
            stop=stop_after_attempt(self._max_retries),
            wait=wait_fixed(self._retry_backoff_seconds),
            retry=retry_if_exception_type(_TransientQuoteError),
        )
        def _attempt() -> Any:
            return self._request(ticker, token)

        return _attempt()

    def _request(self, ticker: str, token: str) -> Any:
        self._respect_min_interval()

        url = self._domain.rstrip("/") + _QUOTE_PATH
        params = {"FID_COND_MRKT_DIV_CODE": _MARKET_DIV_CODE, "FID_INPUT_ISCD": ticker}
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {token}",
            "appkey": getattr(self._token_manager, "app_key", ""),
            "appsecret": getattr(self._token_manager, "app_secret", ""),
            "tr_id": self._tr_id,
            "custtype": "P",
        }

        try:
            response = self._client.get(
                url, params=params, headers=headers, timeout=self._timeout_seconds
            )
        except Exception as exc:  # noqa: BLE001 - transient transport failure.
            raise _TransientQuoteError(
                f"quote request failed: {type(exc).__name__}"
            ) from None

        status = getattr(response, "status_code", None)
        if status is None or int(status) >= 400:
            raise _TransientQuoteError(f"quote request returned HTTP {status}")

        try:
            return response.json()
        except Exception:  # noqa: BLE001 - malformed body is terminal, not retryable.
            return {"__nonjson__": True}

    def _parse_price(self, body: Any) -> KisQuoteResult:
        if not isinstance(body, dict) or body.get("__nonjson__"):
            return _unavailable("quote response was not valid JSON")

        rt_cd = body.get("rt_cd")
        if rt_cd is not None and str(rt_cd) != "0":
            return _unavailable(f"quote response rt_cd={rt_cd}")

        output = body.get("output")
        if not isinstance(output, dict):
            return _unavailable("quote response missing output")

        raw_price = output.get(_PRICE_FIELD)
        if raw_price is None or (isinstance(raw_price, str) and not raw_price.strip()):
            return _unavailable("quote response missing price field")

        try:
            price = float(raw_price)
        except (TypeError, ValueError):
            return _unavailable("quote price is not numeric")

        if not (price > 0) or price != price or price in (float("inf"), float("-inf")):
            return _unavailable("quote price is non-positive or non-finite")

        return KisQuoteResult(
            price=Money(price, "KRW"),
            health=SourceHealth(source=_SOURCE, status=SourceStatus.AVAILABLE, reason="ok"),
        )

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
