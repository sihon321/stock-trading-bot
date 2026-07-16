from datetime import date, datetime, timezone

import httpx

from test_kis_order import DOMAIN, _FakeClient, _FakeTokenManager
from trading_bot.kis_order import KisOrderAccount, KisOrderAdapter
from trading_bot.soak_compat import probe_mock_profile
from trading_bot.soak_models import (
    BrokerPageEnvelope,
    CompatibilityState,
    MockTrProfile,
    PageCompleteness,
    ReconciliationVerdict,
    SoakEvidenceClass,
)
from trading_bot.soak_reconcile import (
    AmbiguityPolicy,
    AmbiguousIntent,
    BrokerSnapshot,
    ComparisonState,
    ObservationWindow,
    SnapshotCampaign,
    SnapshotWindow,
    collect_broker_snapshot,
    compare_broker_truth,
    match_ambiguous_intent,
    persist_reconciliation,
    rebuild_ticker_freezes,
    reconcile_ambiguous_submission,
)
from trading_bot.soak_store import (
    connect_soak_store,
    create_campaign,
    freeze_ticker,
    load_campaign_state,
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


class _PageAdapter:
    def __init__(self, daily, balance) -> None:
        self.daily = daily
        self.balance = balance
        self.post_attempts = 0

    def query_daily_ccld_pages(self, **kwargs):
        return self.daily

    def query_balance_pages(self, **kwargs):
        return self.balance


def _campaign() -> SnapshotCampaign:
    return SnapshotCampaign(
        campaign_id="campaign-1",
        run_id="run-1",
        account=ACCOUNT,
        account_suffix="5678",
        profile=PROFILE,
    )


def _window() -> SnapshotWindow:
    return SnapshotWindow(date(2026, 7, 16), date(2026, 7, 16))


def test_snapshot_is_complete_only_after_all_pages_and_excludes_unrelated_rows() -> None:
    daily = BrokerPageEnvelope(
        rows=(
            {"odno": "ORDER-1", "pdno": "005930", "sll_buy_dvsn_cd": "02", "ord_qty": "5", "ord_unpr": "70000", "tot_ccld_qty": "2", "rmn_qty": "3", "ord_dt": "20260716", "ord_tmd": "101500"},
            {"odno": "OTHER", "pdno": "000660", "ord_qty": "99", "tot_ccld_qty": "99", "rmn_qty": "0"},
        ),
        page_count=2,
        completeness=PageCompleteness.COMPLETE,
        reason_code="COMPLETE",
    )
    balance = BrokerPageEnvelope(
        rows=(
            {"pdno": "005930", "hldg_qty": "2", "ord_psbl_qty": "2", "pchs_avg_pric": "70000"},
            {"pdno": "000660", "hldg_qty": "99", "ord_psbl_qty": "99", "pchs_avg_pric": "100000"},
        ),
        summary={"dnca_tot_amt": "900000", "tot_evlu_amt": "1040000"},
        page_count=3,
        completeness=PageCompleteness.COMPLETE,
        reason_code="COMPLETE",
    )
    adapter = _PageAdapter(daily, balance)

    snapshot = collect_broker_snapshot(
        adapter,
        _campaign(),
        "POST_SUBMISSION",
        _window(),
        {"order_ids": ("ORDER-1",), "tickers": ("005930",)},
    )

    assert snapshot.completeness is PageCompleteness.COMPLETE
    assert snapshot.daily_page_count == 2
    assert snapshot.balance_page_count == 3
    assert [order.order_id for order in snapshot.orders] == ["ORDER-1"]
    assert [holding.ticker for holding in snapshot.holdings] == ["005930"]
    assert snapshot.account.account_suffix == "5678"
    assert "000660" not in repr(snapshot)
    assert adapter.post_attempts == 0


def test_snapshot_incomplete_page_blocks_comparison_without_fabricating_disagreement() -> None:
    adapter = _PageAdapter(
        BrokerPageEnvelope(
            rows=(), page_count=1, completeness=PageCompleteness.INCOMPLETE,
            reason_code="PAGE_CAP_REACHED",
        ),
        BrokerPageEnvelope(
            rows=(), summary={"dnca_tot_amt": "1"}, page_count=1,
            completeness=PageCompleteness.COMPLETE, reason_code="COMPLETE",
        ),
    )

    snapshot = collect_broker_snapshot(
        adapter, _campaign(), "PRE_RUN", _window(), {"order_ids": (), "tickers": ()}
    )
    comparison = compare_broker_truth(
        {"campaign_id": "campaign-1", "run_id": "run-1", "requested_qty": 1}, snapshot
    )

    assert snapshot.completeness is PageCompleteness.INCOMPLETE
    assert comparison.verdict is ReconciliationVerdict.UNKNOWN
    assert all(dimension.state is ComparisonState.UNKNOWN for dimension in comparison.dimensions)


def test_complete_contradiction_is_dimensioned_and_permanently_latches_campaign(tmp_path) -> None:
    snapshot = BrokerSnapshot.from_normalized(
        snapshot_id="snapshot-contradiction",
        campaign=_campaign(),
        stage="PRE_FINALIZATION",
        window=_window(),
        orders=(
            {"order_id": "ORDER-1", "ticker": "005930", "side": "BUY", "ordered_qty": 5, "filled_qty": 2, "remaining_qty": 3, "snapped_price": 70000, "status": "PARTIAL"},
        ),
        holdings=({"ticker": "005930", "quantity": 2, "available_quantity": 2, "average_price": 70000},),
        account={"account_suffix": "5678", "available_cash": 900000, "total_value": 1040000},
    )
    comparison = compare_broker_truth(
        {
            "campaign_id": "campaign-1", "run_id": "run-1", "ticker": "005930",
            "order_intent_id": "intent-1", "order_id": "ORDER-1", "requested_qty": 5,
            "filled_qty": 1, "remaining_qty": 4, "order_state": "PARTIAL",
            "holding_quantity": 1, "available_cash": 910000,
        },
        snapshot,
    )
    assert comparison.verdict is ReconciliationVerdict.MISMATCHED
    assert {d.code for d in comparison.dimensions if d.state is ComparisonState.MISMATCHED} == {
        "FILLED_QTY_CONTRADICTION", "REMAINING_QTY_CONTRADICTION",
        "HOLDING_QTY_CONTRADICTION", "AVAILABLE_CASH_CONTRADICTION",
    }

    conn = connect_soak_store(tmp_path / "soak.db")
    create_campaign(
        conn, campaign_id="campaign-1", accepted_profile_fingerprint="sha256:test",
        accepted_profile_version=PROFILE.version, field_contract_version="fields-v1",
        ambiguity_policy_version="ambiguity-v1", ambiguity_window_seconds=60,
        ambiguity_poll_cadence_seconds=5, ambiguity_max_observations=12,
    )
    persist_reconciliation(conn, snapshot, comparison)
    state = load_campaign_state(conn, campaign_id="campaign-1")
    assert state["state"].value == "FAILED"
    assert state["safety_failure_code"] == "D09_BROKER_TRUTH_CONTRADICTION"
    persisted = conn.execute(
        "SELECT snapshot_id,run_id,ticker,order_intent_id FROM soak_comparisons"
    ).fetchone()
    assert tuple(persisted) == ("snapshot-contradiction", "run-1", "005930", "intent-1")


def _intent() -> AmbiguousIntent:
    return AmbiguousIntent(
        campaign_id="campaign-1",
        run_id="run-1",
        order_intent_id="intent-1",
        submission_id="submission-1",
        account_suffix="5678",
        ticker="005930",
        side="BUY",
        quantity=5,
        snapped_price=70000,
        submitted_at=datetime(2026, 7, 16, 1, 15, tzinfo=timezone.utc),
    )


def _ambiguity_snapshot(order_ids=(), *, complete=True, terminal=True) -> BrokerSnapshot:
    orders = tuple(
        {
            "order_id": order_id, "ticker": "005930", "side": "BUY",
            "ordered_qty": 5, "filled_qty": 5 if terminal else 2,
            "remaining_qty": 0 if terminal else 3, "snapped_price": 70000,
            "status": "FILLED" if terminal else "PARTIAL",
            "order_date": "20260716", "order_time": "101500",
        }
        for order_id in order_ids
    )
    return BrokerSnapshot.from_normalized(
        snapshot_id=f"snapshot-{'-'.join(order_ids) or 'none'}-{int(complete)}-{int(terminal)}",
        campaign=_campaign(), stage="POST_SUBMISSION", window=_window(), orders=orders,
        holdings=({"ticker": "005930", "quantity": 5 if terminal else 2, "available_quantity": 5 if terminal else 2, "average_price": 70000},),
        account={"account_suffix": "5678", "available_cash": 900000, "total_value": 1250000},
        completeness=PageCompleteness.COMPLETE if complete else PageCompleteness.INCOMPLETE,
        reason_code="COMPLETE" if complete else "QUERY_UNAVAILABLE",
    )


def test_ambiguity_matcher_preserves_exact_three_way_cardinality() -> None:
    window = ObservationWindow(
        started_at=datetime(2026, 7, 16, 1, 14, tzinfo=timezone.utc),
        ended_at=datetime(2026, 7, 16, 1, 16, tzinfo=timezone.utc),
        complete=True,
    )

    assert match_ambiguous_intent(_intent(), _ambiguity_snapshot(()), window).verdict is AmbiguityVerdict.NO_MATCH_CONFIRMED
    one = match_ambiguous_intent(_intent(), _ambiguity_snapshot(("ORDER-1",)), window)
    assert one.verdict is AmbiguityVerdict.ONE_MATCH_DETERMINATE
    assert one.matched_order_ids == ("ORDER-1",)
    assert match_ambiguous_intent(_intent(), _ambiguity_snapshot(("ORDER-1", "ORDER-2")), window).verdict is AmbiguityVerdict.MULTIPLE_OR_INCONCLUSIVE
    assert match_ambiguous_intent(_intent(), _ambiguity_snapshot(("ORDER-1",), complete=False), window).verdict is AmbiguityVerdict.MULTIPLE_OR_INCONCLUSIVE


class _SnapshotSequenceAdapter:
    def __init__(self, snapshots) -> None:
        self.snapshots = list(snapshots)
        self.post_attempts = 1
        self._active = None

    def query_daily_ccld_pages(self, **kwargs):
        self._active = self.snapshots.pop(0)
        rows = tuple(
            {
                "odno": order.order_id, "pdno": order.ticker,
                "sll_buy_dvsn_cd": "02", "ord_qty": str(order.ordered_qty),
                "ord_unpr": str(int(order.snapped_price)),
                "tot_ccld_qty": str(order.filled_qty), "rmn_qty": str(order.remaining_qty),
                "ord_dt": order.order_date, "ord_tmd": order.order_time,
            }
            for order in self._active.orders
        )
        return BrokerPageEnvelope(
            rows=rows, page_count=1, completeness=self._active.completeness,
            reason_code=self._active.reason_code,
        )

    def query_balance_pages(self, **kwargs):
        snapshot = self._active
        return BrokerPageEnvelope(
            rows=tuple(
                {"pdno": item.ticker, "hldg_qty": str(item.quantity), "ord_psbl_qty": str(item.available_quantity), "pchs_avg_pric": str(item.average_price)}
                for item in snapshot.holdings
            ),
            summary={"dnca_tot_amt": str(snapshot.account.available_cash), "tot_evlu_amt": str(snapshot.account.total_value)},
            page_count=1, completeness=snapshot.completeness, reason_code=snapshot.reason_code,
        )


def test_ambiguity_reconciliation_appends_every_observation_and_never_posts(tmp_path) -> None:
    conn = connect_soak_store(tmp_path / "soak.db")
    create_campaign(
        conn, campaign_id="campaign-1", accepted_profile_fingerprint="sha256:test",
        accepted_profile_version=PROFILE.version, field_contract_version="fields-v1",
        ambiguity_policy_version="ambiguity-v1", ambiguity_window_seconds=6,
        ambiguity_poll_cadence_seconds=2, ambiguity_max_observations=3,
    )
    freeze_ticker(
        conn, freeze_id="freeze-ambiguity", campaign_id="campaign-1",
        ticker="005930", freeze_kind="AMBIGUITY", order_intent_id="intent-1",
    )
    adapter = _SnapshotSequenceAdapter([
        _ambiguity_snapshot(("ORDER-1",)),
        _ambiguity_snapshot(("ORDER-1",)),
        _ambiguity_snapshot(("ORDER-1",)),
    ])
    sleeps = []

    result = reconcile_ambiguous_submission(
        conn=conn,
        adapter=adapter,
        campaign=_campaign(),
        intent=_intent(),
        query_window=_window(),
        sleeper=sleeps.append,
    )

    assert result.verdict is AmbiguityVerdict.ONE_MATCH_DETERMINATE
    assert result.matched_order_id == "ORDER-1"
    assert result.reconciliation_complete is True
    assert result.freeze_released is True
    assert conn.execute("SELECT COUNT(*) FROM soak_ambiguity_observations").fetchone()[0] == 3
    assert conn.execute("SELECT COUNT(*) FROM soak_snapshots").fetchone()[0] == 3
    assert sleeps == [2, 2]
    assert adapter.post_attempts == 1


def test_partial_fill_freeze_rebuild_survives_reopen_and_day_credit_is_separate(tmp_path) -> None:
    path = tmp_path / "soak.db"
    conn = connect_soak_store(path)
    create_campaign(
        conn, campaign_id="campaign-1", accepted_profile_fingerprint="sha256:test",
        accepted_profile_version=PROFILE.version, field_contract_version="fields-v1",
        ambiguity_policy_version="ambiguity-v1", ambiguity_window_seconds=60,
        ambiguity_poll_cadence_seconds=5, ambiguity_max_observations=12,
    )
    freeze_ticker(
        conn, freeze_id="freeze-partial", campaign_id="campaign-1", ticker="005930",
        freeze_kind="REMAINING_ORDER", order_intent_id="intent-1",
    )
    conn.close()

    reopened = connect_soak_store(path)
    rebuilt = rebuild_ticker_freezes(reopened, "campaign-1")

    assert rebuilt["005930"].freeze_kind == "REMAINING_ORDER"
    assert rebuilt["005930"].order_intent_id == "intent-1"
    assert rebuilt["005930"].reconciliation_complete is False
    assert load_campaign_state(reopened, campaign_id="campaign-1")["credited_days"] == 0
