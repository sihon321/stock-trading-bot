from datetime import date

import httpx

from test_kis_order import DOMAIN, _FakeClient, _FakeTokenManager
from trading_bot.kis_order import KisOrderAccount, KisOrderAdapter
from trading_bot.soak_compat import probe_mock_profile
from trading_bot.soak_models import (
    CompatibilityState,
    MockTrProfile,
    PageCompleteness,
    SoakEvidenceClass,
)


PROFILE = MockTrProfile(
    version="official-example-v1",
    buy_tr_id="VTTC0012U",
    sell_tr_id="VTTC0011U",
    daily_ccld_tr_id="VTTC0081R",
    balance_tr_id="VTTC8434R",
)
ACCOUNT = KisOrderAccount(cano="12345678", account_product_code="01")


def _response(path: str, payload: dict, *, more: bool = False) -> httpx.Response:
    return httpx.Response(
        200,
        json={"rt_cd": "0", **payload},
        headers={"tr_cont": "M" if more else "D"},
        request=httpx.Request("GET", DOMAIN + path),
    )


def _adapter(responses: list[httpx.Response]) -> tuple[KisOrderAdapter, _FakeClient]:
    client = _FakeClient(responses)
    return (
        KisOrderAdapter(
            token_manager=_FakeTokenManager(),
            domain=DOMAIN,
            tr_id_profile="mock",
            client=client,
            min_interval_seconds=0,
            retry_backoff_seconds=0,
        ),
        client,
    )


def test_daily_query_follows_every_page_and_sends_full_contract() -> None:
    adapter, client = _adapter(
        [
            _response("/daily", {"output1": [{"odno": "1", "pdno": "005930", "ord_qty": "2"}], "ctx_area_fk100": "FK", "ctx_area_nk100": "NK"}, more=True),
            _response("/daily", {"output1": [{"odno": "2", "pdno": "005930", "tot_ccld_qty": "1"}], "ctx_area_fk100": "", "ctx_area_nk100": ""}),
        ]
    )

    envelope = adapter.query_daily_ccld_pages(
        account=ACCOUNT,
        profile=PROFILE,
        start_date=date(2026, 7, 15),
        end_date=date(2026, 7, 16),
        ticker="005930",
        side_code="00",
        fill_code="00",
        page_cap=3,
    )

    assert envelope.completeness is PageCompleteness.COMPLETE
    assert envelope.page_count == 2
    assert [row["odno"] for row in envelope.rows] == ["1", "2"]
    first, second = client.calls
    assert first["headers"]["tr_id"] == "VTTC0081R"
    expected = {
        "CANO": "12345678", "ACNT_PRDT_CD": "01", "INQR_STRT_DT": "20260715",
        "INQR_END_DT": "20260716", "SLL_BUY_DVSN_CD": "00", "CCLD_DVSN": "00",
        "PDNO": "005930", "CTX_AREA_FK100": "", "CTX_AREA_NK100": "",
    }
    assert expected.items() <= first["params"].items()
    assert second["params"]["CTX_AREA_FK100"] == "FK"
    assert second["params"]["CTX_AREA_NK100"] == "NK"


def test_balance_normalizes_output1_and_output2() -> None:
    adapter, _ = _adapter([
        _response("/balance", {"output1": [{"pdno": "005930", "hldg_qty": "3"}], "output2": [{"dnca_tot_amt": "1000"}]})
    ])

    envelope = adapter.query_balance_pages(account=ACCOUNT, profile=PROFILE, page_cap=2)

    assert envelope.completeness is PageCompleteness.COMPLETE
    assert envelope.rows[0] == {"pdno": "005930", "hldg_qty": "3"}
    assert envelope.summary == {"dnca_tot_amt": "1000"}


def test_repeated_token_and_page_cap_are_explicitly_incomplete() -> None:
    repeated, _ = _adapter([
        _response("/daily", {"output1": [], "ctx_area_fk100": "FK", "ctx_area_nk100": "NK"}, more=True),
        _response("/daily", {"output1": [], "ctx_area_fk100": "FK", "ctx_area_nk100": "NK"}, more=True),
    ])
    capped, _ = _adapter([
        _response("/daily", {"output1": [], "ctx_area_fk100": "FK", "ctx_area_nk100": "NK"}, more=True),
    ])

    kwargs = dict(account=ACCOUNT, profile=PROFILE, start_date=date(2026, 7, 16), end_date=date(2026, 7, 16))
    assert repeated.query_daily_ccld_pages(**kwargs, page_cap=4).reason_code == "REPEATED_CONTINUATION_TOKEN"
    assert capped.query_daily_ccld_pages(**kwargs, page_cap=1).reason_code == "PAGE_CAP_REACHED"


def test_probe_is_read_only_and_synthetic_evidence_cannot_be_accepted() -> None:
    adapter, client = _adapter([
        _response("/daily", {"output1": [], "ctx_area_fk100": "", "ctx_area_nk100": ""}),
        _response("/balance", {"output1": [], "output2": [{"dnca_tot_amt": "1000"}]}),
    ])

    result = probe_mock_profile(
        adapter,
        ACCOUNT,
        (PROFILE,),
        (date(2026, 7, 16), date(2026, 7, 16)),
        evidence_class=SoakEvidenceClass.SYNTHETIC,
    )

    assert result.state is CompatibilityState.UNKNOWN
    assert result.evidence_class is SoakEvidenceClass.SYNTHETIC
    assert all(call["method"] == "GET" for call in client.calls)
    assert "12345678" not in repr(result)
