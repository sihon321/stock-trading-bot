"""Offline tests for the direct-REST KIS order query foundation.

Task 1 of 05-02 intentionally adds only retryable account-query legs,
mode-derived TR_ID selection, and KRX tick snapping. The dangerous order-cash
POST and fill-readback parser are gated behind a later human verification task.
"""

from __future__ import annotations

import inspect

import httpx

from test_kis_quote import (
    ACCESS_TOKEN,
    APP_KEY,
    APP_SECRET,
    DOMAIN,
    SECRET_VALUES,
    _FakeTokenManager,
)
from trading_bot.data_models import SourceStatus
from trading_bot.domain import OrderSide
from trading_bot.kis_order import KisOrderAdapter, snap_to_tick

DAILY_CCLD_PATH = "/uapi/domestic-stock/v1/trading/inquire-daily-ccld"
BALANCE_PATH = "/uapi/domestic-stock/v1/trading/inquire-balance"


def assert_no_secret_leaked(*texts: str) -> None:
    combined = "\n".join(texts)
    for secret in SECRET_VALUES:
        assert secret not in combined


class _FakeClient:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def get(self, url, *, params=None, headers=None, timeout=None):
        self.calls.append(
            {"method": "GET", "url": url, "params": params, "headers": headers, "timeout": timeout}
        )
        if not self._responses:
            raise AssertionError("no more fake responses queued")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _response(path: str, *, status_code: int = 200, output=None, rt_cd="0"):
    if output is None:
        output = [{"odno": "12345", "pdno": "005930"}]
    return httpx.Response(
        status_code=status_code,
        json={"rt_cd": rt_cd, "msg1": "정상", "output": output},
        request=httpx.Request("GET", DOMAIN + path),
    )


def _adapter(responses, *, tr_id_profile="mock", client=None) -> KisOrderAdapter:
    return KisOrderAdapter(
        token_manager=_FakeTokenManager(),
        domain=DOMAIN,
        tr_id_profile=tr_id_profile,
        client=client or _FakeClient(responses),
        min_interval_seconds=0.0,
        max_retries=3,
        retry_backoff_seconds=0.0,
        timeout_seconds=5.0,
    )


def test_tick_snap() -> None:
    assert snap_to_tick(74_321, side=OrderSide.BUY) == 74_300
    assert snap_to_tick(74_321, side=OrderSide.SELL) == 74_300
    assert snap_to_tick(74_300, side=OrderSide.BUY) == 74_300
    assert snap_to_tick(1_999, side=OrderSide.BUY) == 1_999


def test_tr_id_selection() -> None:
    mock_adapter = _adapter([], tr_id_profile="mock")
    real_adapter = _adapter([], tr_id_profile="real")

    assert mock_adapter.tr_ids.buy == "VTTC0802U"
    assert mock_adapter.tr_ids.sell == "VTTC0801U"
    assert mock_adapter.tr_ids.daily_fills == "VTTC8001R"
    assert mock_adapter.tr_ids.balance == "VTTC8434R"
    assert real_adapter.tr_ids.buy == "TTTC0802U"
    assert real_adapter.tr_ids.sell == "TTTC0801U"
    assert real_adapter.tr_ids.daily_fills == "TTTC8001R"
    assert real_adapter.tr_ids.balance == "TTTC8434R"


def test_query_legs_use_headers_and_retry_transient_errors() -> None:
    client = _FakeClient(
        [
            httpx.ConnectError("boom", request=httpx.Request("GET", DOMAIN)),
            _response(DAILY_CCLD_PATH, output=[{"odno": "1", "pdno": "005930"}]),
            _response(BALANCE_PATH, output={"dnca_tot_amt": "1000000"}),
        ]
    )
    adapter = _adapter([], client=client)

    daily = adapter.inquire_daily_ccld(ticker="005930")
    balance = adapter.inquire_balance()

    assert daily.health.status is SourceStatus.AVAILABLE
    assert daily.output == [{"odno": "1", "pdno": "005930"}]
    assert balance.health.status is SourceStatus.AVAILABLE
    assert len(client.calls) == 3
    first = client.calls[0]
    assert first["url"].endswith(DAILY_CCLD_PATH)
    assert first["headers"]["authorization"] == f"Bearer {ACCESS_TOKEN}"
    assert first["headers"]["appkey"] == APP_KEY
    assert first["headers"]["appsecret"] == APP_SECRET
    assert first["headers"]["tr_id"] == "VTTC8001R"
    assert client.calls[2]["url"].endswith(BALANCE_PATH)
    assert client.calls[2]["headers"]["tr_id"] == "VTTC8434R"


def test_malformed_query_output_fails_safe_without_secret_leakage() -> None:
    adapter = _adapter(
        [
            _response(DAILY_CCLD_PATH, output={"tot_ccld_qty": "not parsed in task 1"}),
            _response(BALANCE_PATH, output=None, rt_cd="1"),
        ]
    )

    daily = adapter.inquire_daily_ccld(ticker="005930")
    balance = adapter.inquire_balance()

    assert daily.health.status is SourceStatus.UNAVAILABLE
    assert balance.health.status is SourceStatus.UNAVAILABLE
    assert_no_secret_leaked(repr(adapter), repr(daily), daily.health.reason, balance.health.reason)


def test_task1_introduces_no_order_post_or_fill_parser_surface() -> None:
    import trading_bot.kis_order as module

    source = inspect.getsource(module)
    lowered = source.lower()
    assert "order-cash" not in lowered
    assert "hashkey" not in lowered
    assert not hasattr(KisOrderAdapter, "place_order")
    assert not hasattr(KisOrderAdapter, "order_cash")
    assert not hasattr(KisOrderAdapter, "parse_fill")
