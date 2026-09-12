"""Offline tests for the direct-REST KIS order adapter."""

from __future__ import annotations

import inspect
from datetime import date

import httpx
import pytest

from test_kis_quote import (
    ACCESS_TOKEN,
    APP_KEY,
    APP_SECRET,
    DOMAIN,
    SECRET_VALUES,
    _FakeTokenManager,
)
from trading_bot.data_models import SourceHealth, SourceStatus
from trading_bot.domain import Money, Order, OrderSide, Ticker
from trading_bot.kis_auth import KisAuthError
from trading_bot.kis_order import (
    KisOrderAccount,
    KisOrderAdapter,
    KisOrderError,
    snap_to_tick,
)
from trading_bot.soak_models import MockTrProfile, PageCompleteness

DAILY_CCLD_PATH = "/uapi/domestic-stock/v1/trading/inquire-daily-ccld"
BALANCE_PATH = "/uapi/domestic-stock/v1/trading/inquire-balance"
HASHKEY_PATH = "/uapi/hashkey"
ORDER_CASH_PATH = "/uapi/domestic-stock/v1/trading/order-cash"
CHK_HOLIDAY_PATH = "/uapi/domestic-stock/v1/quotations/chk-holiday"
PAGE_PROFILE = MockTrProfile(
    version="offline-test-v1",
    buy_tr_id="VTTC0012U",
    sell_tr_id="VTTC0011U",
    daily_ccld_tr_id="VTTC0081R",
    balance_tr_id="VTTC8434R",
)


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

    def post(self, url, *, json=None, headers=None, timeout=None):
        self.calls.append(
            {"method": "POST", "url": url, "json": json, "headers": headers, "timeout": timeout}
        )
        if not self._responses:
            raise AssertionError("no more fake responses queued")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _response(
    path: str, *, status_code: int = 200, output=None, rt_cd="0", output_key="output"
):
    if output is None:
        output = [{"odno": "12345", "pdno": "005930"}]
    return httpx.Response(
        status_code=status_code,
        json={"rt_cd": rt_cd, "msg1": "정상", output_key: output},
        request=httpx.Request("GET", DOMAIN + path),
    )


def _post_response(path: str, *, status_code: int = 200, payload=None):
    if payload is None:
        payload = {"rt_cd": "0", "output": {"ODNO": "KIS-1"}}
    return httpx.Response(
        status_code=status_code,
        json=payload,
        request=httpx.Request("POST", DOMAIN + path),
    )


def _adapter(
    responses,
    *,
    tr_id_profile="mock",
    client=None,
    query_timeout_seconds=None,
    max_retries=3,
) -> KisOrderAdapter:
    return KisOrderAdapter(
        token_manager=_FakeTokenManager(),
        domain=DOMAIN,
        tr_id_profile=tr_id_profile,
        client=client or _FakeClient(responses),
        min_interval_seconds=0.0,
        max_retries=max_retries,
        retry_backoff_seconds=0.0,
        timeout_seconds=5.0,
        query_timeout_seconds=query_timeout_seconds,
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
    assert mock_adapter.tr_ids.daily_fills == "VTTC0081R"
    assert mock_adapter.tr_ids.balance == "VTTC8434R"
    assert real_adapter.tr_ids.buy == "TTTC0802U"
    assert real_adapter.tr_ids.sell == "TTTC0801U"
    assert real_adapter.tr_ids.daily_fills == "TTTC0081R"
    assert real_adapter.tr_ids.balance == "TTTC8434R"


def test_query_legs_use_headers_and_retry_transient_errors() -> None:
    client = _FakeClient(
        [
            httpx.ConnectError("boom", request=httpx.Request("GET", DOMAIN)),
            _response(
                DAILY_CCLD_PATH, output=[{"odno": "1", "pdno": "005930"}],
                output_key="output1",
            ),
            _response(
                BALANCE_PATH, output={"dnca_tot_amt": "1000000"}, output_key="output2"
            ),
        ]
    )
    adapter = _adapter([], client=client, query_timeout_seconds=15.0)

    account = KisOrderAccount("12345678", "01")
    daily = adapter.inquire_daily_ccld(account=account, ticker="005930")
    balance = adapter.inquire_balance(account=account)

    assert daily.health.status is SourceStatus.AVAILABLE
    assert daily.output == [{"odno": "1", "pdno": "005930"}]
    assert balance.health.status is SourceStatus.AVAILABLE
    assert len(client.calls) == 3
    first = client.calls[0]
    assert first["url"].endswith(DAILY_CCLD_PATH)
    assert first["headers"]["authorization"] == f"Bearer {ACCESS_TOKEN}"
    assert first["headers"]["appkey"] == APP_KEY
    assert first["headers"]["appsecret"] == APP_SECRET
    assert first["headers"]["tr_id"] == "VTTC0081R"
    assert first["params"]["CANO"] == "12345678"
    assert first["params"]["ACNT_PRDT_CD"] == "01"
    assert first["params"]["PDNO"] == "005930"
    assert first["params"]["SLL_BUY_DVSN_CD"] == "00"
    assert first["params"]["CCLD_DVSN"] == "00"
    assert first["params"]["CTX_AREA_FK100"] == ""
    assert first["params"]["CTX_AREA_NK100"] == ""
    assert first["params"]["EXCG_ID_DVSN_CD"] == "KRX"
    assert first["timeout"] == 15.0
    assert client.calls[2]["url"].endswith(BALANCE_PATH)
    assert client.calls[2]["headers"]["tr_id"] == "VTTC8434R"
    assert client.calls[2]["params"]["CANO"] == "12345678"
    assert client.calls[2]["params"]["ACNT_PRDT_CD"] == "01"


def test_paged_daily_query_uses_official_krx_exchange_parameter() -> None:
    client = _FakeClient(
        [
            _response(
                DAILY_CCLD_PATH,
                output=[],
                output_key="output1",
            )
        ]
    )
    adapter = _adapter([], client=client, query_timeout_seconds=15.0)

    result = adapter.query_daily_ccld_pages(
        account=KisOrderAccount("12345678", "01"),
        profile=PAGE_PROFILE,
        start_date=date(2026, 8, 11),
        end_date=date(2026, 8, 11),
        page_cap=1,
    )

    assert result.completeness is PageCompleteness.COMPLETE
    assert client.calls[0]["params"]["EXCG_ID_DVSN_CD"] == "KRX"
    assert client.calls[0]["timeout"] == 15.0


@pytest.mark.parametrize(
    "reason_code",
    [
        "AUTH_TIMEOUT",
        "AUTH_TRANSPORT_ERROR",
        "AUTH_HTTP_AUTH_ERROR",
        "AUTH_HTTP_RATE_LIMITED",
        "AUTH_HTTP_ERROR",
        "AUTH_RESPONSE_INVALID",
    ],
)
def test_paged_query_preserves_bounded_token_failure_reason(reason_code: str) -> None:
    health = SourceHealth(
        source="kis_auth",
        status=SourceStatus.UNAVAILABLE,
        reason="bounded auth failure",
    )
    token_manager = _FakeTokenManager(
        error=KisAuthError(health, reason_code=reason_code)
    )
    adapter = KisOrderAdapter(
        token_manager=token_manager,
        domain=DOMAIN,
        tr_id_profile="mock",
        client=_FakeClient([]),
        min_interval_seconds=0.0,
        retry_backoff_seconds=0.0,
    )

    result = adapter.query_daily_ccld_pages(
        account=KisOrderAccount("12345678", "01"),
        profile=PAGE_PROFILE,
        start_date=date(2026, 8, 13),
        end_date=date(2026, 8, 13),
        page_cap=1,
    )

    assert result.completeness is PageCompleteness.INCOMPLETE
    assert result.reason_code == reason_code
    assert result.page_count == 0


def test_malformed_query_output_fails_safe_without_secret_leakage() -> None:
    adapter = _adapter(
        [
            _response(
                DAILY_CCLD_PATH, output={"tot_ccld_qty": "not parsed in task 1"},
                output_key="output1",
            ),
            _response(BALANCE_PATH, output=None, rt_cd="1", output_key="output2"),
        ]
    )

    account = KisOrderAccount("12345678", "01")
    daily = adapter.inquire_daily_ccld(account=account, ticker="005930")
    balance = adapter.inquire_balance(account=account)

    assert daily.health.status is SourceStatus.UNAVAILABLE
    assert balance.health.status is SourceStatus.UNAVAILABLE
    assert_no_secret_leaked(repr(adapter), repr(daily), daily.health.reason, balance.health.reason)


def test_daily_order_query_accepts_textual_order_status_fields() -> None:
    adapter = _adapter(
        [
            _response(
                DAILY_CCLD_PATH,
                output=[
                    {
                        "odno": "12345",
                        "pdno": "005930",
                        "ord_qty": "1",
                        "ord_stat": "01",
                        "ord_stat_name": "접수",
                    }
                ],
                output_key="output1",
            )
        ]
    )

    result = adapter.inquire_daily_ccld(
        account=KisOrderAccount("12345678", "01"), ticker="005930"
    )

    assert result.health.status is SourceStatus.AVAILABLE
    assert result.output == [
        {
            "odno": "12345",
            "pdno": "005930",
            "ord_qty": "1",
            "ord_stat": "01",
            "ord_stat_name": "접수",
        }
    ]


def test_balance_query_accepts_output2_summary_list() -> None:
    adapter = _adapter(
        [
            _response(
                BALANCE_PATH,
                output=[{"dnca_tot_amt": "1000000"}],
                output_key="output2",
            )
        ]
    )

    result = adapter.inquire_balance(account=KisOrderAccount("12345678", "01"))

    assert result.health.status is SourceStatus.AVAILABLE
    assert result.output == [{"dnca_tot_amt": "1000000"}]


@pytest.mark.parametrize(
    ("responses", "expected_reason"),
    [
        (
            [
                httpx.ReadTimeout(
                    f"must not leak {ACCESS_TOKEN}",
                    request=httpx.Request("GET", DOMAIN),
                )
                for _ in range(3)
            ],
            "QUERY_TIMEOUT",
        ),
        (
            [
                httpx.ConnectError(
                    f"must not leak {APP_SECRET}",
                    request=httpx.Request("GET", DOMAIN),
                )
                for _ in range(3)
            ],
            "QUERY_TRANSPORT_ERROR",
        ),
        (
            [_response(DAILY_CCLD_PATH, status_code=401) for _ in range(3)],
            "QUERY_HTTP_AUTH_ERROR",
        ),
        (
            [_response(DAILY_CCLD_PATH, status_code=503) for _ in range(3)],
            "QUERY_HTTP_ERROR",
        ),
        (
            [_response(DAILY_CCLD_PATH, rt_cd="1", output_key="output1")],
            "PROVIDER_ERROR",
        ),
        (
            [
                httpx.Response(
                    200,
                    text=f"not-json {ACCESS_TOKEN}",
                    request=httpx.Request("GET", DOMAIN + DAILY_CCLD_PATH),
                )
            ],
            "PARSE_ERROR",
        ),
    ],
)
def test_paged_query_reports_bounded_non_secret_failure_category(
    responses, expected_reason: str
) -> None:
    adapter = _adapter(responses)

    result = adapter.query_daily_ccld_pages(
        account=KisOrderAccount("12345678", "01"),
        profile=PAGE_PROFILE,
        start_date=date(2026, 8, 11),
        end_date=date(2026, 8, 11),
        page_cap=1,
    )

    assert result.completeness is PageCompleteness.INCOMPLETE
    assert result.reason_code == expected_reason
    assert result.reason_code in {
        "QUERY_TIMEOUT",
        "QUERY_TRANSPORT_ERROR",
        "QUERY_HTTP_AUTH_ERROR",
        "QUERY_HTTP_ERROR",
        "PROVIDER_ERROR",
        "PARSE_ERROR",
    }
    assert_no_secret_leaked(repr(result), result.reason_code)


def _calendar_response(*rows, rt_cd="0"):
    return httpx.Response(
        200,
        json={"rt_cd": rt_cd, "msg1": "calendar", "output": list(rows)},
        request=httpx.Request("GET", DOMAIN + CHK_HOLIDAY_PATH),
    )


def test_mock_calendar_witness_normalizes_explicit_open_and_closed_days() -> None:
    client = _FakeClient(
        [
            _calendar_response({"bass_dt": "20260728", "opnd_yn": "Y"}),
            _calendar_response({"bass_dt": "20260729", "opnd_yn": "N"}),
        ]
    )
    adapter = _adapter([], client=client)

    assert adapter.fetch_trading_day(date(2026, 7, 28)) is True
    assert adapter.fetch_trading_day(date(2026, 7, 29)) is False
    assert [call["method"] for call in client.calls] == ["GET", "GET"]
    assert all(call["url"].endswith(CHK_HOLIDAY_PATH) for call in client.calls)
    assert all(call["headers"]["tr_id"] == "VTCA0903R" for call in client.calls)
    assert client.calls[0]["params"] == {
        "BASS_DT": "20260728",
        "CTX_AREA_NK": "",
        "CTX_AREA_FK": "",
    }


def test_mock_calendar_witness_fails_closed_for_unavailable_or_ambiguous_responses() -> None:
    cases = [
        _calendar_response({"bass_dt": "20260728", "opnd_yn": "Y"}, rt_cd="1"),
        _calendar_response({"bass_dt": "20260729", "opnd_yn": "Y"}),
        _calendar_response({"bass_dt": "20260728", "opnd_yn": ""}),
        _calendar_response(
            {"bass_dt": "20260728", "opnd_yn": "Y"},
            {"bass_dt": "20260728", "opnd_yn": "N"},
        ),
        httpx.Response(
            200,
            json={"rt_cd": "0", "output": {"bass_dt": "20260728", "opnd_yn": "Y"}},
            request=httpx.Request("GET", DOMAIN + CHK_HOLIDAY_PATH),
        ),
        httpx.ConnectError("provider details must not escape", request=httpx.Request("GET", DOMAIN)),
    ]
    for response in cases:
        adapter = _adapter([response, response, response])
        assert adapter.fetch_trading_day(date(2026, 7, 28)) is None


def test_mock_calendar_witness_retries_semantically_unavailable_payload() -> None:
    client = _FakeClient(
        [
            _calendar_response({"bass_dt": "20260729", "opnd_yn": "Y"}),
            _calendar_response({"bass_dt": "20260728", "opnd_yn": "Y"}),
        ]
    )
    adapter = _adapter([], client=client)

    assert adapter.fetch_trading_day(date(2026, 7, 28)) is True
    assert len(client.calls) == 2


def test_calendar_witness_refuses_real_target_without_network_or_order_capability() -> None:
    client = _FakeClient([])
    adapter = KisOrderAdapter(
        token_manager=_FakeTokenManager(),
        domain="https://openapi.koreainvestment.com:9443",
        tr_id_profile="real",
        client=client,
        min_interval_seconds=0.0,
    )

    assert adapter.fetch_trading_day(date(2026, 7, 28)) is None
    assert client.calls == []


def test_order_cash_body_headers_and_mode_tr_id() -> None:
    order = Order(Ticker("005930"), OrderSide.BUY, 3, Money(74_321, "KRW"))
    account = KisOrderAccount(cano="12345678", account_product_code="01")
    client = _FakeClient(
        [
            _post_response(HASHKEY_PATH, payload={"HASH": "server-hash"}),
            _post_response(ORDER_CASH_PATH, payload={"rt_cd": "0", "output": {"ODNO": "KIS-100"}}),
        ]
    )
    adapter = _adapter([], tr_id_profile="mock", client=client)

    result = adapter.place_order_cash(account=account, order=order, snapped_price=74_300)

    assert result.order_id == "KIS-100"
    hash_call, order_call = client.calls
    assert hash_call["url"].endswith(HASHKEY_PATH)
    assert hash_call["json"] == {
        "CANO": "12345678",
        "ACNT_PRDT_CD": "01",
        "PDNO": "005930",
        "ORD_DVSN": "00",
        "ORD_QTY": "3",
        "ORD_UNPR": "74300",
    }
    assert order_call["url"].endswith(ORDER_CASH_PATH)
    assert order_call["json"] == hash_call["json"]
    assert order_call["headers"]["tr_id"] == "VTTC0802U"
    assert order_call["headers"]["hashkey"] == "server-hash"
    assert order_call["timeout"] == 5.0

    real_client = _FakeClient(
        [
            _post_response(HASHKEY_PATH, payload={"HASH": "server-hash"}),
            _post_response(ORDER_CASH_PATH, payload={"rt_cd": "0", "output": {"ODNO": "KIS-101"}}),
        ]
    )
    real_adapter = _adapter([], tr_id_profile="real", client=real_client)

    real_adapter.place_order_cash(
        account=account,
        order=Order(Ticker("005930"), OrderSide.SELL, 3, Money(74_321, "KRW")),
        snapped_price=74_300,
    )

    assert real_client.calls[1]["headers"]["tr_id"] == "TTTC0801U"


def test_order_cash_post_not_retried() -> None:
    account = KisOrderAccount(cano="12345678", account_product_code="01")
    order = Order(Ticker("005930"), OrderSide.BUY, 1, Money(70_000, "KRW"))
    client = _FakeClient(
        [
            _post_response(HASHKEY_PATH, payload={"HASH": "server-hash"}),
            httpx.ConnectError("one failed order POST", request=httpx.Request("POST", DOMAIN)),
        ]
    )
    adapter = _adapter([], client=client)

    try:
        adapter.place_order_cash(account=account, order=order, snapped_price=70_000)
    except Exception as exc:  # noqa: BLE001 - exact exception type belongs to implementation.
        assert "order POST failed" in str(exc) or isinstance(exc, httpx.ConnectError)
    else:  # pragma: no cover - the implementation must fail safe here.
        raise AssertionError("order POST failure did not propagate")

    order_posts = [
        call for call in client.calls if call["method"] == "POST" and call["url"].endswith(ORDER_CASH_PATH)
    ]
    assert len(order_posts) == 1
    assert not hasattr(KisOrderAdapter.place_order_cash, "retry")


@pytest.mark.parametrize(
    ("order_response", "expected"),
    [
        (
            _post_response(ORDER_CASH_PATH, status_code=503),
            {
                "failure_category": "HTTP_ERROR",
                "failure_stage": "ORDER_POST",
                "http_status": 503,
            },
        ),
        (
            _post_response(
                ORDER_CASH_PATH,
                payload={
                    "rt_cd": "1",
                    "msg_cd": "APBK0918",
                    "msg1": f"must not persist {APP_SECRET}",
                    "output": {},
                },
            ),
            {
                "failure_category": "PROVIDER_ERROR",
                "failure_stage": "ORDER_POST",
                "rt_cd": "1",
                "msg_cd": "APBK0918",
            },
        ),
        (
            _post_response(
                ORDER_CASH_PATH,
                payload={"rt_cd": "0", "output": {}},
            ),
            {
                "failure_category": "MISSING_ORDER_ID",
                "failure_stage": "ORDER_POST",
            },
        ),
    ],
)
def test_order_cash_failure_exposes_only_bounded_safe_diagnostics(
    order_response, expected
) -> None:
    client = _FakeClient(
        [
            _post_response(HASHKEY_PATH, payload={"HASH": "server-hash"}),
            order_response,
        ]
    )
    adapter = _adapter([], client=client)

    with pytest.raises(KisOrderError) as caught:
        adapter.place_order_cash(
            account=KisOrderAccount("12345678", "01"),
            order=Order(Ticker("005930"), OrderSide.BUY, 1, Money(70_000, "KRW")),
            snapped_price=70_000,
        )

    assert caught.value.safe_diagnostics == expected
    persisted = repr(caught.value.safe_diagnostics)
    assert "msg1" not in persisted
    assert "output" not in persisted
    assert_no_secret_leaked(persisted)


def test_fill_parser_uses_confirmed_daily_ccld_fields() -> None:
    adapter = _adapter([])

    fills = adapter.parse_fill_status(
        [
            {
                "odno": "KIS-100",
                "pdno": "005930",
                "ord_qty": "5",
                "tot_ccld_qty": "2",
                "rmn_qty": "3",
            }
        ],
        order_id="KIS-100",
        ticker="005930",
    )

    assert fills.order_id == "KIS-100"
    assert fills.ordered_qty == 5
    assert fills.filled_qty == 2
    assert fills.remaining_qty == 3
