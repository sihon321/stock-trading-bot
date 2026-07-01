"""Offline tests for the KIS current-price quote adapter (DATA-03, D-15).

The quote adapter must consume the shared :class:`KisTokenManager` for auth
(never issue tokens itself), call the domestic-stock inquire-price endpoint with
TR ID ``FHKST01010100``, validate the numeric price before constructing
:class:`~trading_bot.domain.Money`, and normalize missing/nonnumeric/zero/
negative/throttled/HTTP-error/auth-unavailable states into an UNAVAILABLE
:class:`~trading_bot.data_models.SourceHealth`. Every test injects fakes; no live
KIS calls. No order endpoint/hashkey/broker logic is introduced.
"""

import dataclasses
import inspect

import httpx
import pytest

from trading_bot.data_models import SourceHealth, SourceStatus
from trading_bot.domain import Money
from trading_bot.kis_auth import KisAuthError, KisTokenManager
from trading_bot.kis_quote import (
    KisQuoteAdapter,
    KisQuoteResult,
)

DOMAIN = "https://mock.kis.example.test"
ACCESS_TOKEN = "kis-access-token-secret-value"
TR_ID = "FHKST01010100"
QUOTE_PATH = "/uapi/domestic-stock/v1/quotations/inquire-price"
APP_KEY = "mock-app-key-secret"
APP_SECRET = "mock-app-secret-secret"

SECRET_VALUES = (APP_KEY, APP_SECRET, ACCESS_TOKEN)


def assert_no_secret_leaked(*texts: str) -> None:
    combined = "\n".join(texts)
    for secret in SECRET_VALUES:
        assert secret not in combined


class _FakeTokenManager:
    """Returns a fixed token or raises the shared KisAuthError."""

    def __init__(self, token=ACCESS_TOKEN, error=None) -> None:
        self._token = token
        self._error = error
        self.calls = 0

    def get_token(self) -> str:
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._token


class _FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def get(self, url, *, params=None, headers=None, timeout=None):
        self.calls.append(
            {"url": url, "params": params, "headers": headers, "timeout": timeout}
        )
        if not self._responses:
            raise AssertionError("no more fake responses queued")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _response(status_code: int = 200, *, price="70500", rt_cd="0", body=None):
    if body is None:
        body = {"rt_cd": rt_cd, "msg1": "정상", "output": {"stck_prpr": price}}
    return httpx.Response(
        status_code=status_code,
        json=body,
        request=httpx.Request("GET", DOMAIN + QUOTE_PATH),
    )


def _adapter(responses, *, token_manager=None):
    return KisQuoteAdapter(
        token_manager=token_manager or _FakeTokenManager(),
        domain=DOMAIN,
        tr_id=TR_ID,
        client=_FakeClient(responses),
        min_interval_seconds=0.0,
        max_retries=3,
        retry_backoff_seconds=0.0,
        timeout_seconds=5.0,
    )


# --- Typed model shape ------------------------------------------------------


def test_quote_result_is_frozen_dataclass_and_pairs_health() -> None:
    result = KisQuoteResult(
        price=Money(70500.0, "KRW"),
        health=SourceHealth(source="kis_quote", status=SourceStatus.AVAILABLE, reason="ok"),
    )

    assert dataclasses.is_dataclass(result)
    assert isinstance(result.health, SourceHealth)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.price = Money(1.0, "KRW")  # type: ignore[misc]


def test_adapter_method_is_synchronous() -> None:
    assert not inspect.iscoroutinefunction(KisQuoteAdapter.fetch_current_price)


# --- Happy path -------------------------------------------------------------


def test_valid_response_returns_money_krw() -> None:
    token_manager = _FakeTokenManager()
    client = _FakeClient([_response(price="70500")])
    adapter = KisQuoteAdapter(
        token_manager=token_manager,
        domain=DOMAIN,
        tr_id=TR_ID,
        client=client,
        min_interval_seconds=0.0,
        max_retries=3,
        retry_backoff_seconds=0.0,
    )

    result = adapter.fetch_current_price("005930")

    assert result.health.status is SourceStatus.AVAILABLE
    assert result.price == Money(70500.0, "KRW")
    # Token reuse: adapter asked the shared manager, did not issue itself.
    assert token_manager.calls == 1


def test_request_uses_endpoint_tr_id_and_ticker_mapping() -> None:
    token_manager = _FakeTokenManager()
    client = _FakeClient([_response()])
    adapter = KisQuoteAdapter(
        token_manager=token_manager,
        domain=DOMAIN,
        tr_id=TR_ID,
        client=client,
        min_interval_seconds=0.0,
    )

    adapter.fetch_current_price("005930")

    call = client.calls[0]
    assert call["url"].endswith(QUOTE_PATH)
    assert call["params"]["FID_COND_MRKT_DIV_CODE"] == "J"
    assert call["params"]["FID_INPUT_ISCD"] == "005930"
    assert call["headers"]["tr_id"] == TR_ID
    assert call["headers"]["authorization"] == f"Bearer {ACCESS_TOKEN}"
    assert call["headers"]["appkey"]  # present
    assert call["timeout"] is not None


# --- Ticker validation ------------------------------------------------------


@pytest.mark.parametrize("ticker", ["", "  ", "12", "ABCDEF", "12345a", None])
def test_invalid_ticker_is_unavailable_without_calling_api(ticker) -> None:
    token_manager = _FakeTokenManager()
    client = _FakeClient([])  # must not be called
    adapter = KisQuoteAdapter(
        token_manager=token_manager,
        domain=DOMAIN,
        tr_id=TR_ID,
        client=client,
        min_interval_seconds=0.0,
    )

    result = adapter.fetch_current_price(ticker)  # type: ignore[arg-type]

    assert result.price is None
    assert result.health.status is SourceStatus.UNAVAILABLE
    assert client.calls == []
    assert token_manager.calls == 0


# --- Price field validation -------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        {"rt_cd": "0", "output": {}},  # missing price
        {"rt_cd": "0", "output": {"stck_prpr": "abc"}},  # nonnumeric
        {"rt_cd": "0", "output": {"stck_prpr": "0"}},  # zero
        {"rt_cd": "0", "output": {"stck_prpr": "-100"}},  # negative
        {"rt_cd": "0"},  # missing output
        {"rt_cd": "1", "msg1": "error", "output": {"stck_prpr": "70500"}},  # rt_cd fail
    ],
)
def test_bad_price_payload_is_unavailable(body) -> None:
    adapter = _adapter([_response(body=body)])

    result = adapter.fetch_current_price("005930")

    assert result.price is None
    assert result.health.status is SourceStatus.UNAVAILABLE


def test_non_json_body_is_unavailable() -> None:
    bad = httpx.Response(
        status_code=200,
        text="<html/>",
        request=httpx.Request("GET", DOMAIN + QUOTE_PATH),
    )
    adapter = _adapter([bad])

    result = adapter.fetch_current_price("005930")

    assert result.health.status is SourceStatus.UNAVAILABLE


# --- Transport / throttle / auth failures -----------------------------------


@pytest.mark.parametrize("status", [403, 429, 500])
def test_http_error_status_is_unavailable_after_bounded_retry(status) -> None:
    resp = _response(status_code=status)
    adapter = _adapter([resp, resp, resp])

    result = adapter.fetch_current_price("005930")

    assert result.health.status is SourceStatus.UNAVAILABLE


def test_transient_error_retries_then_succeeds() -> None:
    client = _FakeClient(
        [
            httpx.ConnectError("boom", request=httpx.Request("GET", DOMAIN)),
            _response(price="12345"),
        ]
    )
    adapter = KisQuoteAdapter(
        token_manager=_FakeTokenManager(),
        domain=DOMAIN,
        tr_id=TR_ID,
        client=client,
        min_interval_seconds=0.0,
        max_retries=3,
        retry_backoff_seconds=0.0,
    )

    result = adapter.fetch_current_price("005930")

    assert result.health.status is SourceStatus.AVAILABLE
    assert result.price == Money(12345.0, "KRW")
    assert len(client.calls) == 2


def test_exhausted_retries_is_unavailable_and_bounded() -> None:
    err = httpx.ConnectError("down", request=httpx.Request("GET", DOMAIN))
    client = _FakeClient([err, err, err, err, err])
    adapter = KisQuoteAdapter(
        token_manager=_FakeTokenManager(),
        domain=DOMAIN,
        tr_id=TR_ID,
        client=client,
        min_interval_seconds=0.0,
        max_retries=3,
        retry_backoff_seconds=0.0,
    )

    result = adapter.fetch_current_price("005930")

    assert result.health.status is SourceStatus.UNAVAILABLE
    assert len(client.calls) == 3  # bounded, not a retry storm.


def test_auth_unavailable_becomes_quote_unavailable_without_http_call() -> None:
    auth_health = SourceHealth(
        source="kis_auth", status=SourceStatus.UNAVAILABLE, reason="token issue exhausted retries"
    )
    token_manager = _FakeTokenManager(error=KisAuthError(auth_health))
    client = _FakeClient([])  # must not be called when auth is unavailable.
    adapter = KisQuoteAdapter(
        token_manager=token_manager,
        domain=DOMAIN,
        tr_id=TR_ID,
        client=client,
        min_interval_seconds=0.0,
    )

    result = adapter.fetch_current_price("005930")

    assert result.price is None
    assert result.health.status is SourceStatus.UNAVAILABLE
    assert client.calls == []


# --- No order/broker surface (acceptance) -----------------------------------


def test_adapter_introduces_no_order_or_hashkey_surface() -> None:
    import trading_bot.kis_quote as module

    source = inspect.getsource(module)
    lowered = source.lower()
    for forbidden in ("hashkey", "order-cash", "place_order", "inquire-balance", "trading-order"):
        assert forbidden not in lowered


# --- Secret redaction --------------------------------------------------------


def test_no_secret_leaks_in_result_or_repr() -> None:
    auth_health = SourceHealth(
        source="kis_auth", status=SourceStatus.UNAVAILABLE, reason="down"
    )
    adapter = _adapter([_response(body={"rt_cd": "1", "msg1": "x", "output": {}})])
    result = adapter.fetch_current_price("005930")

    assert_no_secret_leaked(repr(adapter), repr(result), result.health.reason)
    assert_no_secret_leaked(auth_health.reason)
