"""KIS domestic-stock order/query adapter for real order readiness.

This module reuses the shared :class:`~trading_bot.kis_auth.KisTokenManager`
and mirrors the Phase 3 quote adapter's bounded retry and fail-safe response
validation for query legs. The order-cash POST is intentionally single-shot and
is never decorated with tenacity retry.
"""

from __future__ import annotations

import math
import re
import time
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Mapping, Optional, Union
from zoneinfo import ZoneInfo

from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from trading_bot.data_models import SourceHealth, SourceStatus
from trading_bot.domain import Order, OrderSide
from trading_bot.kis_auth import KisAuthError, KisTokenManager
from trading_bot.kis_rate_limit import KisRequestLimiter
from trading_bot.soak_models import BrokerPageEnvelope, MockTrProfile, PageCompleteness

_SOURCE = "kis_order"
_DAILY_CCLD_PATH = "/uapi/domestic-stock/v1/trading/inquire-daily-ccld"
_BALANCE_PATH = "/uapi/domestic-stock/v1/trading/inquire-balance"
_CHK_HOLIDAY_PATH = "/uapi/domestic-stock/v1/quotations/chk-holiday"
_HASHKEY_PATH = "/uapi/hashkey"
_ORDER_CASH_PATH = "/uapi/domestic-stock/v1/trading/order-cash"
_CHK_HOLIDAY_TR_ID = "VTCA0903R"

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

    _ALLOWED_REASON_CODES = frozenset(
        {
            "QUERY_TIMEOUT",
            "QUERY_TRANSPORT_ERROR",
            "QUERY_HTTP_AUTH_ERROR",
            "QUERY_HTTP_ERROR",
        }
    )

    def __init__(self, reason_code: str) -> None:
        safe_reason = (
            reason_code
            if reason_code in self._ALLOWED_REASON_CODES
            else "QUERY_TRANSPORT_ERROR"
        )
        super().__init__(safe_reason)
        self.reason_code = safe_reason


def _query_transport_reason(exc: Exception) -> str:
    type_names = {base.__name__.lower() for base in type(exc).__mro__}
    if isinstance(exc, TimeoutError) or any("timeout" in name for name in type_names):
        return "QUERY_TIMEOUT"
    return "QUERY_TRANSPORT_ERROR"


def _query_http_reason(status: Any) -> str:
    try:
        numeric_status = int(status)
    except (TypeError, ValueError, OverflowError):
        return "QUERY_HTTP_ERROR"
    if numeric_status in {401, 403}:
        return "QUERY_HTTP_AUTH_ERROR"
    return "QUERY_HTTP_ERROR"


def _query_http_failed(status: Any) -> bool:
    try:
        return status is None or int(status) >= 400
    except (TypeError, ValueError, OverflowError):
        return True


class KisOrderError(RuntimeError):
    """Raised when a single-shot KIS order operation fails safe.

    ``safe_diagnostics`` is deliberately limited to bounded classification
    fields.  Provider prose, response bodies, request data, credentials, and
    exception messages must never cross into durable order evidence.
    """

    _ALLOWED_CATEGORIES = frozenset(
        {
            "TIMEOUT",
            "TRANSPORT_ERROR",
            "HTTP_ERROR",
            "PARSE_ERROR",
            "PROVIDER_ERROR",
            "RESPONSE_SCHEMA_ERROR",
            "MISSING_HASHKEY",
            "MISSING_ORDER_ID",
            "ORDER_ERROR",
        }
    )
    _ALLOWED_STAGES = frozenset({"HASHKEY", "ORDER_POST", "QUERY", "UNKNOWN"})
    _SAFE_CODE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")

    def __init__(
        self,
        message: str,
        *,
        failure_category: str = "ORDER_ERROR",
        failure_stage: str = "UNKNOWN",
        http_status: int | None = None,
        rt_cd: object = None,
        msg_cd: object = None,
    ) -> None:
        super().__init__(message)
        self._failure_category = (
            failure_category
            if failure_category in self._ALLOWED_CATEGORIES
            else "ORDER_ERROR"
        )
        self._failure_stage = (
            failure_stage if failure_stage in self._ALLOWED_STAGES else "UNKNOWN"
        )
        self._http_status = self._normalize_http_status(http_status)
        self._rt_cd = self._normalize_code(rt_cd)
        self._msg_cd = self._normalize_code(msg_cd)

    @classmethod
    def _normalize_code(cls, value: object) -> str | None:
        if value is None:
            return None
        candidate = str(value).strip()
        return candidate if cls._SAFE_CODE.fullmatch(candidate) else None

    @staticmethod
    def _normalize_http_status(value: object) -> int | None:
        try:
            status = int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError, OverflowError):
            return None
        return status if 100 <= status <= 599 else None

    @property
    def safe_diagnostics(self) -> dict[str, str | int]:
        detail: dict[str, str | int] = {
            "failure_category": self._failure_category,
            "failure_stage": self._failure_stage,
        }
        if self._http_status is not None:
            detail["http_status"] = self._http_status
        if self._rt_cd is not None:
            detail["rt_cd"] = self._rt_cd
        if self._msg_cd is not None:
            detail["msg_cd"] = self._msg_cd
        return detail


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


MOCK_TR_PROFILE_CANDIDATES = (
    MockTrProfile(
        version="repository-legacy-v1",
        buy_tr_id="VTTC0802U",
        sell_tr_id="VTTC0801U",
        daily_ccld_tr_id="VTTC8001R",
        balance_tr_id="VTTC8434R",
    ),
    MockTrProfile(
        version="official-example-v1",
        buy_tr_id="VTTC0012U",
        sell_tr_id="VTTC0011U",
        daily_ccld_tr_id="VTTC0081R",
        balance_tr_id="VTTC8434R",
    ),
)


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
            daily_fills="VTTC0081R",
            balance="VTTC8434R",
        )
    if profile == "real":
        return KisOrderTrIds(
            buy="TTTC0802U",
            sell="TTTC0801U",
            daily_fills="TTTC0081R",
            balance="TTTC8434R",
        )
    raise ValueError(f"unsupported KIS tr_id_profile: {tr_id_profile!r}")


@dataclass(frozen=True, repr=False)
class PreparedOrderCash:
    """Immutable one-order network preparation; never durable/loggable."""
    adapter: Any
    account: KisOrderAccount
    order: Order
    snapped_price: int
    body: Any
    headers: Any


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
        query_timeout_seconds: float | None = None,
        request_limiter: KisRequestLimiter | None = None,
        _test_only_allow_unguarded_mutation: bool = False,
    ) -> None:
        if client is None:
            import httpx

            client = httpx.Client()
        self._token_manager = token_manager
        self._domain = domain
        self._tr_id_profile = str(tr_id_profile).strip().lower()
        self._tr_ids = _derive_tr_ids(tr_id_profile)
        self._client = client
        self._min_interval_seconds = float(min_interval_seconds)
        self._max_retries = max(1, int(max_retries))
        self._retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))
        self._timeout_seconds = float(timeout_seconds)
        self._query_timeout_seconds = float(
            timeout_seconds if query_timeout_seconds is None else query_timeout_seconds
        )
        if self._query_timeout_seconds <= 0:
            raise ValueError("query_timeout_seconds must be positive")
        self._last_request_at: Optional[float] = None
        self._request_limiter = request_limiter
        self._test_only_allow_unguarded_mutation=False
        if _test_only_allow_unguarded_mutation:
            import httpx
            if (token_manager is None or client is None or isinstance(token_manager,KisTokenManager)
                or isinstance(client,httpx.Client) or not callable(getattr(client,'post',None))
                or not type(client).__module__.startswith(('test_', 'tests.'))
                or not type(token_manager).__module__.startswith(('test_', 'tests.'))):
                raise ValueError('explicit no-credential offline test collaborators required')
            self._test_only_allow_unguarded_mutation=True

    @classmethod
    def for_test_legacy_mutation(cls, **kwargs):
        kwargs['_test_only_allow_unguarded_mutation']=True
        return cls(**kwargs)

    def __repr__(self) -> str:  # pragma: no cover - trivial redaction
        return f"KisOrderAdapter(domain={self._domain!r}, tr_ids={self._tr_ids!r})"

    @property
    def tr_ids(self) -> KisOrderTrIds:
        """Return the mode-derived TR_ID family."""

        return self._tr_ids

    def inquire_daily_ccld(
        self, *, account: KisOrderAccount, ticker: Optional[str] = None,
        order_id: Optional[str] = None,
    ) -> KisOrderQueryResult:
        """Fetch recent same-day KIS executions/orders as untrusted raw output."""

        if ticker is not None and not _is_valid_ticker(ticker):
            return _unavailable("ticker must be a 6-digit KRX code")
        try:
            token = self._token_manager.get_token()
            body = self._fetch_query_body(
                path=_DAILY_CCLD_PATH,
                tr_id=self._tr_ids.daily_fills,
                params=self._daily_params(
                    account=account, ticker=ticker, order_id=order_id
                ),
                token=token,
            )
        except KisAuthError:
            return _unavailable("KIS auth unavailable for order query")
        except _TransientOrderQueryError as exc:
            return _unavailable(str(exc))
        return self._parse_query_output(body, expected_shape=list, output_key="output1")

    def inquire_balance(self, *, account: KisOrderAccount) -> KisOrderQueryResult:
        """Fetch KIS account balance as untrusted raw output."""

        try:
            token = self._token_manager.get_token()
            body = self._fetch_query_body(
                path=_BALANCE_PATH,
                tr_id=self._tr_ids.balance,
                params=self._balance_params() | {
                    "CANO": account.cano,
                    "ACNT_PRDT_CD": account.account_product_code,
                },
                token=token,
            )
        except KisAuthError:
            return _unavailable("KIS auth unavailable for order query")
        except _TransientOrderQueryError as exc:
            return _unavailable(str(exc))
        return self._parse_query_output(
            body, expected_shape=(dict, list), output_key="output2"
        )

    def fetch_trading_day(self, day: date) -> bool | None:
        """Return explicit mock KIS calendar evidence for one KST date.

        This witness is intentionally unavailable outside the soak adapter's
        mock profile.  It only makes the authenticated GET calendar request;
        it cannot use hashkey or order-cash capability.  KIS can occasionally
        return a successful HTTP response whose calendar payload is incomplete,
        so both transport failures and semantically unavailable payloads are
        retried within the adapter's existing bounded query budget.
        """

        if self._tr_id_profile != "mock" or not isinstance(day, date):
            return None
        try:
            token = self._token_manager.get_token()
        except KisAuthError:
            return None

        params = {
            "BASS_DT": day.strftime("%Y%m%d"),
            "CTX_AREA_NK": "",
            "CTX_AREA_FK": "",
        }
        for attempt in range(self._max_retries):
            try:
                body = self._query_request(
                    path=_CHK_HOLIDAY_PATH,
                    tr_id=_CHK_HOLIDAY_TR_ID,
                    params=params,
                    token=token,
                )
            except _TransientOrderQueryError:
                witness = None
            else:
                witness = self._normalize_trading_day(body, day)
            if type(witness) is bool:
                return witness
            if attempt + 1 < self._max_retries:
                time.sleep(self._retry_backoff_seconds)
        return None

    @staticmethod
    def _normalize_trading_day(body: Any, requested_day: date) -> bool | None:
        """Accept exactly one documented requested-date ``opnd_yn`` value."""

        if not isinstance(body, dict) or str(body.get("rt_cd", "")) != "0":
            return None
        output = body.get("output")
        if not isinstance(output, list):
            return None
        requested_text = requested_day.strftime("%Y%m%d")
        rows = [
            row
            for row in output
            if isinstance(row, dict) and row.get("bass_dt") == requested_text
        ]
        if len(rows) != 1:
            return None
        open_value = rows[0].get("opnd_yn")
        if open_value == "Y":
            return True
        if open_value == "N":
            return False
        return None

    def query_daily_ccld_pages(
        self,
        *,
        account: KisOrderAccount,
        profile: MockTrProfile,
        start_date: date,
        end_date: date,
        ticker: str = "",
        side_code: str = "00",
        fill_code: str = "00",
        page_cap: int = 10,
    ) -> BrokerPageEnvelope:
        """Read every mock order/fill page or return explicit incompleteness."""

        if page_cap <= 0:
            raise ValueError("page_cap must be positive")
        if ticker and not _is_valid_ticker(ticker):
            return self._incomplete_envelope("INVALID_TICKER")
        params = {
            "CANO": account.cano,
            "ACNT_PRDT_CD": account.account_product_code,
            "INQR_STRT_DT": start_date.strftime("%Y%m%d"),
            "INQR_END_DT": end_date.strftime("%Y%m%d"),
            "SLL_BUY_DVSN_CD": side_code,
            "INQR_DVSN": "00",
            "PDNO": ticker,
            "CCLD_DVSN": fill_code,
            "ORD_GNO_BRNO": "",
            "ODNO": "",
            "INQR_DVSN_3": "00",
            "INQR_DVSN_1": "",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
            "EXCG_ID_DVSN_CD": "KRX",
        }
        return self._query_pages(
            path=_DAILY_CCLD_PATH,
            tr_id=profile.daily_ccld_tr_id,
            params=params,
            page_cap=page_cap,
            rows_key="output1",
            row_allowlist={
                "odno", "pdno", "sll_buy_dvsn_cd", "ord_qty", "ord_unpr",
                "tot_ccld_qty", "avg_prvs", "rmn_qty", "ord_tmd", "ord_dt",
                "ord_gno_brno", "ccld_no", "ord_stat", "ord_stat_name",
                "orgn_odno", "orig_odno", "cncl_cfrm_qty", "cncl_qty",
                "cncl_yn", "cancl_yn", "rjct_qty", "rjct_yn",
            },
            summary_key=None,
            summary_allowlist=set(),
        )

    def query_balance_pages(
        self,
        *,
        account: KisOrderAccount,
        profile: MockTrProfile,
        page_cap: int = 10,
    ) -> BrokerPageEnvelope:
        """Read all balance holdings pages and their allowlisted summary."""

        if page_cap <= 0:
            raise ValueError("page_cap must be positive")
        params = self._balance_params() | {
            "CANO": account.cano,
            "ACNT_PRDT_CD": account.account_product_code,
        }
        return self._query_pages(
            path=_BALANCE_PATH,
            tr_id=profile.balance_tr_id,
            params=params,
            page_cap=page_cap,
            rows_key="output1",
            row_allowlist={"pdno", "prdt_name", "hldg_qty", "ord_psbl_qty", "pchs_avg_pric"},
            summary_key="output2",
            summary_allowlist={"dnca_tot_amt", "nxdy_excc_amt", "prvs_rcdl_excc_amt", "tot_evlu_amt"},
        )

    def _query_pages(
        self,
        *,
        path: str,
        tr_id: str,
        params: dict[str, str],
        page_cap: int,
        rows_key: str,
        row_allowlist: set[str],
        summary_key: str | None,
        summary_allowlist: set[str],
    ) -> BrokerPageEnvelope:
        rows: list[Mapping[str, str | int | float | bool | None]] = []
        summary: dict[str, str | int | float | bool | None] = {}
        seen_tokens: set[tuple[str, str]] = set()
        try:
            token = self._token_manager.get_token()
        except KisAuthError as exc:
            return self._incomplete_envelope(exc.reason_code)

        for page_number in range(1, page_cap + 1):
            try:
                body, response_headers = self._fetch_query_page(
                    path=path, tr_id=tr_id, params=params, token=token
                )
                if not isinstance(body, dict) or str(body.get("rt_cd", "0")) != "0":
                    return self._incomplete_envelope("PROVIDER_ERROR", rows, summary, page_number)
                page_rows = body.get(rows_key)
                if not isinstance(page_rows, list) or any(not isinstance(row, dict) for row in page_rows):
                    return self._incomplete_envelope("PARSE_ERROR", rows, summary, page_number)
                rows.extend(self._allowlisted(row, row_allowlist) for row in page_rows)
                if summary_key is not None:
                    raw_summary = body.get(summary_key, [])
                    if not isinstance(raw_summary, (list, dict)):
                        return self._incomplete_envelope("PARSE_ERROR", rows, summary, page_number)
                    item = raw_summary[0] if isinstance(raw_summary, list) and raw_summary else raw_summary
                    if isinstance(item, dict):
                        summary.update(self._allowlisted(item, summary_allowlist))
                fk = str(body.get("ctx_area_fk100") or body.get("CTX_AREA_FK100") or "")
                nk = str(body.get("ctx_area_nk100") or body.get("CTX_AREA_NK100") or "")
                has_more = str(response_headers.get("tr_cont", "")).upper() in {"M", "F"}
                if not has_more:
                    return BrokerPageEnvelope(
                        rows=tuple(rows), summary=summary, page_count=page_number,
                        completeness=PageCompleteness.COMPLETE, reason_code="COMPLETE",
                    )
                continuation = (fk, nk)
                if not any(continuation) or continuation in seen_tokens:
                    return self._incomplete_envelope(
                        "REPEATED_CONTINUATION_TOKEN", rows, summary, page_number
                    )
                seen_tokens.add(continuation)
                params = params | {"CTX_AREA_FK100": fk, "CTX_AREA_NK100": nk}
            except _TransientOrderQueryError as exc:
                return self._incomplete_envelope(
                    exc.reason_code, rows, summary, page_number
                )
        return self._incomplete_envelope("PAGE_CAP_REACHED", rows, summary, page_cap)

    @staticmethod
    def _allowlisted(
        values: Mapping[str, Any], allowlist: set[str]
    ) -> dict[str, str | int | float | bool | None]:
        clean: dict[str, str | int | float | bool | None] = {}
        for key, value in values.items():
            normalized = str(key).lower()
            if normalized not in allowlist:
                continue
            if value is None or isinstance(value, (str, int, float, bool)):
                clean[normalized] = value
        return clean

    @staticmethod
    def _incomplete_envelope(
        reason: str,
        rows: list[Mapping[str, str | int | float | bool | None]] | None = None,
        summary: Mapping[str, str | int | float | bool | None] | None = None,
        page_count: int = 0,
    ) -> BrokerPageEnvelope:
        return BrokerPageEnvelope(
            rows=tuple(rows or ()), summary=summary or {}, page_count=page_count,
            completeness=PageCompleteness.INCOMPLETE, reason_code=reason,
        )

    def prepare_order_cash(self, *, account: KisOrderAccount, order: Order, snapped_price: int):
        """Finish token/hashkey IO before taking the global admission lock."""
        from types import MappingProxyType
        body=self.build_order_body(account=account,order=order,snapped_price=snapped_price)
        token=self._token_manager.get_token()
        hashkey=self._request_hashkey(body=body)
        tr_id=self._tr_ids.buy if order.side is OrderSide.BUY else self._tr_ids.sell
        return PreparedOrderCash(self,account,order,snapped_price,MappingProxyType(dict(body)),
            MappingProxyType(dict(self._headers(token=token,tr_id=tr_id,hashkey=hashkey))))

    def place_order_cash(
        self, *, account: KisOrderAccount, order: Order, snapped_price: int,
        prepared_order: PreparedOrderCash | None = None, submission_entry: Any = None,
    ) -> KisOrderPostResult:
        """Submit one limit order-cash POST and return the broker order ID.

        This method deliberately has no tenacity retry wrapper. If the hashkey or
        order POST fails, the exception propagates after exactly one order-cash
        POST attempt so callers can re-query broker truth before any resend.
        """

        from .submission_authority import FinalPostEntry, SubmissionDenied
        if type(submission_entry) is not FinalPostEntry and not self._test_only_allow_unguarded_mutation:
            raise SubmissionDenied('ACTUAL_POST_ENTRY_REQUIRED')
        prepared = prepared_order or self.prepare_order_cash(account=account,order=order,snapped_price=snapped_price)
        if (type(prepared) is not PreparedOrderCash or prepared.adapter is not self
            or prepared.account!=account or prepared.order!=order or prepared.snapped_price!=snapped_price):
            raise SubmissionDenied('PREPARED_ORDER_IDENTITY_MISMATCH')
        body,headers=dict(prepared.body),dict(prepared.headers)

        url = self._domain.rstrip("/") + _ORDER_CASH_PATH
        if submission_entry is not None:
            submission_entry.enter(self,account,order,snapped_price,prepared)
        try:
            response = self._client.post(
                url, json=body, headers=headers, timeout=self._timeout_seconds
            )
        except Exception as exc:  # noqa: BLE001 - never retry a real order POST.
            category = (
                "TIMEOUT"
                if _query_transport_reason(exc) == "QUERY_TIMEOUT"
                else "TRANSPORT_ERROR"
            )
            raise KisOrderError(
                f"order POST failed: {type(exc).__name__}",
                failure_category=category,
                failure_stage="ORDER_POST",
            ) from exc

        status = getattr(response, "status_code", None)
        if status is None or int(status) >= 400:
            raise KisOrderError(
                f"order POST returned HTTP {status}",
                failure_category="HTTP_ERROR",
                failure_stage="ORDER_POST",
                http_status=status,
            )

        try:
            payload = response.json()
        except Exception as exc:  # noqa: BLE001 - malformed body is terminal.
            raise KisOrderError(
                "order POST response was not valid JSON",
                failure_category="PARSE_ERROR",
                failure_stage="ORDER_POST",
            ) from exc

        output = self._validated_response_output(
            payload, expected_shape=dict, failure_stage="ORDER_POST"
        )
        order_id = str(output.get("ODNO") or output.get("odno") or "").strip()
        if not order_id:
            raise KisOrderError(
                "order POST response missing ODNO",
                failure_category="MISSING_ORDER_ID",
                failure_stage="ORDER_POST",
            )
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

    def read_fill_status(
        self, *, account: KisOrderAccount, ticker: str, order_id: str
    ) -> FillStatus:
        """Query recent executions and parse the confirmed fill-status fields."""

        result = self.inquire_daily_ccld(
            account=account, ticker=ticker, order_id=order_id
        )
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

    def _fetch_query_page(
        self, *, path: str, tr_id: str, params: dict, token: str
    ) -> tuple[Any, Mapping[str, str]]:
        @retry(
            reraise=True,
            stop=stop_after_attempt(self._max_retries),
            wait=wait_fixed(self._retry_backoff_seconds),
            retry=retry_if_exception_type(_TransientOrderQueryError),
        )
        def _attempt() -> tuple[Any, Mapping[str, str]]:
            self._respect_min_interval()
            url = self._domain.rstrip("/") + path
            try:
                response = self._client.get(
                    url,
                    params=params,
                    headers=self._headers(token=token, tr_id=tr_id),
                    timeout=self._query_timeout_seconds,
                )
            except Exception as exc:  # noqa: BLE001
                raise _TransientOrderQueryError(_query_transport_reason(exc)) from None
            status = getattr(response, "status_code", None)
            if _query_http_failed(status):
                raise _TransientOrderQueryError(_query_http_reason(status))
            try:
                return response.json(), response.headers
            except Exception:
                return {"__nonjson__": True}, response.headers

        return _attempt()

    def _query_request(self, *, path: str, tr_id: str, params: dict, token: str) -> Any:
        self._respect_min_interval()

        url = self._domain.rstrip("/") + path
        headers = self._headers(token=token, tr_id=tr_id)

        try:
            response = self._client.get(
                url, params=params, headers=headers,
                timeout=self._query_timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - transient transport failure.
            raise _TransientOrderQueryError(_query_transport_reason(exc)) from None

        status = getattr(response, "status_code", None)
        if _query_http_failed(status):
            raise _TransientOrderQueryError(_query_http_reason(status))

        try:
            return response.json()
        except Exception:  # noqa: BLE001 - malformed body is terminal.
            return {"__nonjson__": True}

    def _parse_query_output(
        self, body: Any, *, expected_shape: type | tuple[type, ...], output_key: str = "output"
    ) -> KisOrderQueryResult:
        try:
            output = self._validated_response_output(
                body, expected_shape=expected_shape, output_key=output_key
            )
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
            category = (
                "TIMEOUT"
                if _query_transport_reason(exc) == "QUERY_TIMEOUT"
                else "TRANSPORT_ERROR"
            )
            raise KisOrderError(
                f"hashkey request failed: {type(exc).__name__}",
                failure_category=category,
                failure_stage="HASHKEY",
            ) from exc
        status = getattr(response, "status_code", None)
        if status is None or int(status) >= 400:
            raise KisOrderError(
                f"hashkey request returned HTTP {status}",
                failure_category="HTTP_ERROR",
                failure_stage="HASHKEY",
                http_status=status,
            )
        try:
            payload = response.json()
        except Exception as exc:  # noqa: BLE001
            raise KisOrderError(
                "hashkey response was not valid JSON",
                failure_category="PARSE_ERROR",
                failure_stage="HASHKEY",
            ) from exc
        hashkey = str(payload.get("HASH") or payload.get("hashkey") or "").strip()
        if not hashkey:
            raise KisOrderError(
                "hashkey response missing HASH",
                failure_category="MISSING_HASHKEY",
                failure_stage="HASHKEY",
            )
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

    def _validated_response_output(
        self,
        body: Any,
        *,
        expected_shape: type | tuple[type, ...],
        output_key: str = "output",
        failure_stage: str = "QUERY",
    ) -> Any:
        if not isinstance(body, dict) or body.get("__nonjson__"):
            raise KisOrderError(
                "order response was not valid JSON",
                failure_category="PARSE_ERROR",
                failure_stage=failure_stage,
            )

        rt_cd = body.get("rt_cd")
        if rt_cd is not None and str(rt_cd) != "0":
            raise KisOrderError(
                f"order response rt_cd={rt_cd}",
                failure_category="PROVIDER_ERROR",
                failure_stage=failure_stage,
                rt_cd=rt_cd,
                msg_cd=body.get("msg_cd"),
            )

        output = body.get(output_key)
        if not isinstance(output, expected_shape):
            raise KisOrderError(
                "order response missing output",
                failure_category="RESPONSE_SCHEMA_ERROR",
                failure_stage=failure_stage,
            )
        if not self._numeric_fields_are_valid(output):
            raise KisOrderError(
                "order response numeric field is invalid",
                failure_category="RESPONSE_SCHEMA_ERROR",
                failure_stage=failure_stage,
            )

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
        non_numeric_fragments = (
            "name", "code", "dvsn", "stat", "type", "yn", "orgno",
        )
        if any(fragment in lowered for fragment in non_numeric_fragments):
            return False
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
    def _daily_params(
        *, account: KisOrderAccount, ticker: Optional[str], order_id: Optional[str]
    ) -> dict:
        today = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d")
        return {
            "CANO": account.cano,
            "ACNT_PRDT_CD": account.account_product_code,
            "INQR_STRT_DT": today,
            "INQR_END_DT": today,
            "SLL_BUY_DVSN_CD": "00",
            "INQR_DVSN": "00",
            "PDNO": ticker or "",
            "CCLD_DVSN": "00",
            "ORD_GNO_BRNO": "",
            "ODNO": order_id or "",
            "INQR_DVSN_3": "00",
            "INQR_DVSN_1": "",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
            "EXCG_ID_DVSN_CD": "KRX",
        }

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
        if self._request_limiter is not None:
            self._request_limiter.acquire()
            return
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
