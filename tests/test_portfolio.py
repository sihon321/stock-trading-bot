from __future__ import annotations

from datetime import date, datetime, timezone

from trading_bot.kis_order import KisOrderAccount
from trading_bot.portfolio import (
    DivergenceSeverity,
    EvaluationProvenance,
    HeldPositionContext,
    PortfolioCompleteness,
    build_evaluation_universe,
    build_held_position_context,
    collect_portfolio_snapshot,
    evaluate_ticker_evidence,
    held_first_targets,
)
from trading_bot.screener import ScreenerCandidate
from trading_bot.soak_models import BrokerPageEnvelope, MockTrProfile, PageCompleteness


PROFILE = MockTrProfile(
    version="portfolio-test-v1",
    buy_tr_id="VTTC0012U",
    sell_tr_id="VTTC0011U",
    daily_ccld_tr_id="VTTC0081R",
    balance_tr_id="VTTC8434R",
)
ACCOUNT = KisOrderAccount("12345678", "01")


class FakeAdapter:
    def __init__(self, daily: list[BrokerPageEnvelope], balance: BrokerPageEnvelope):
        self.daily = list(daily)
        self.balance = balance
        self.daily_calls: list[dict] = []
        self.post_attempts = 0

    def query_daily_ccld_pages(self, **kwargs):
        self.daily_calls.append(kwargs)
        return self.daily.pop(0)

    def query_balance_pages(self, **kwargs):
        return self.balance


def envelope(*rows, summary=None, complete=True, reason="COMPLETE"):
    return BrokerPageEnvelope(
        rows=rows,
        summary=summary or {},
        page_count=1,
        completeness=PageCompleteness.COMPLETE if complete else PageCompleteness.INCOMPLETE,
        reason_code=reason,
    )


def collect(adapter, *, unresolved=()):
    return collect_portfolio_snapshot(
        adapter=adapter,
        account=ACCOUNT,
        profile=PROFILE,
        trading_date=date(2026, 9, 4),
        previous_trading_date=date(2026, 9, 3),
        account_scope_hash="account-scope-sha256",
        local_unresolved=unresolved,
        observed_at=datetime(2026, 9, 4, 1, 0, tzinfo=timezone.utc),
    )


def test_complete_empty_account_is_mutable_without_fabricated_rows():
    adapter = FakeAdapter(
        [envelope()],
        envelope(summary={"dnca_tot_amt": "0", "tot_evlu_amt": "0"}),
    )

    snapshot = collect(adapter)

    assert snapshot.completeness is PortfolioCompleteness.COMPLETE
    assert snapshot.mutation_capable is True
    assert snapshot.holdings == snapshot.orders == snapshot.fills == ()
    assert snapshot.account.available_cash == 0
    assert snapshot.account.total_evaluation == 0
    assert adapter.post_attempts == 0
    assert "12345678" not in repr(snapshot)


def test_account_projection_retains_all_rows_and_explicit_partial_cancel():
    adapter = FakeAdapter(
        [
            envelope(
                {
                    "odno": "CHILD-1",
                    "orgn_odno": "ORIGINAL-1",
                    "pdno": "005930",
                    "sll_buy_dvsn_cd": "01",
                    "ord_qty": "10",
                    "tot_ccld_qty": "3",
                    "rmn_qty": "5",
                    "cncl_cfrm_qty": "2",
                    "cncl_yn": "Y",
                    "rjct_qty": "0",
                    "ord_unpr": "70000",
                },
                {
                    "odno": "ORDER-2",
                    "pdno": "000660",
                    "sll_buy_dvsn_cd": "02",
                    "ord_qty": "1",
                    "tot_ccld_qty": "1",
                    "rmn_qty": "0",
                    "ord_unpr": "120000",
                },
            )
        ],
        envelope(
            {"pdno": "005930", "hldg_qty": "8", "ord_psbl_qty": "5", "pchs_avg_pric": "65000"},
            {"pdno": "000660", "hldg_qty": "1", "ord_psbl_qty": "1", "pchs_avg_pric": "110000"},
            summary={"dnca_tot_amt": "900000", "tot_evlu_amt": "1900000"},
        ),
    )

    snapshot = collect(adapter)

    assert [item.ticker for item in snapshot.holdings] == ["000660", "005930"]
    assert [item.order_id for item in snapshot.orders] == ["CHILD-1", "ORDER-2"]
    partial = snapshot.orders[0]
    assert partial.original_order_id == "ORIGINAL-1"
    assert partial.cancelled_quantity == 2
    assert partial.remaining_quantity == 5
    assert partial.status == "PARTIAL"
    assert snapshot.fills[0].quantity == 3
    assert snapshot.completeness is PortfolioCompleteness.COMPLETE


def test_missing_required_numeric_or_conflicting_state_fails_closed():
    malformed = FakeAdapter(
        [envelope()],
        envelope(
            {"pdno": "005930", "hldg_qty": "1", "ord_psbl_qty": "", "pchs_avg_pric": "1"},
            summary={"dnca_tot_amt": "1", "tot_evlu_amt": "1"},
        ),
    )
    contradiction = FakeAdapter(
        [
            envelope(
                {
                    "odno": "ORDER-1", "pdno": "005930", "sll_buy_dvsn_cd": "01",
                    "ord_qty": "2", "tot_ccld_qty": "2", "rmn_qty": "1",
                    "ord_stat_name": "체결", "ord_unpr": "1",
                }
            )
        ],
        envelope(summary={"dnca_tot_amt": "1", "tot_evlu_amt": "1"}),
    )

    first = collect(malformed)
    second = collect(contradiction)

    assert first.completeness is PortfolioCompleteness.INCOMPLETE
    assert first.mutation_capable is False
    assert second.completeness is PortfolioCompleteness.UNKNOWN
    assert second.orders[0].status == "UNKNOWN"
    assert second.mutation_capable is False


def test_older_unresolved_is_queried_to_origin_and_unattributed_blocks_account():
    adapter = FakeAdapter(
        [envelope(), envelope()],
        envelope(summary={"dnca_tot_amt": "1", "tot_evlu_amt": "1"}),
    )

    snapshot = collect(
        adapter,
        unresolved=(
            {
                "order_intent_id": "intent-1", "broker_order_id": "OLD-1",
                "ticker": "005930", "side": "SELL", "quantity": 2,
                "origin_date": date(2026, 8, 20),
            },
        ),
    )

    assert adapter.daily_calls[1]["start_date"] == date(2026, 8, 20)
    assert snapshot.completeness is PortfolioCompleteness.UNKNOWN
    assert snapshot.divergences[0].severity is DivergenceSeverity.BLOCKING
    assert snapshot.divergences[0].code == "UNATTRIBUTED_UNRESOLVED_ORDER"


def test_held_first_union_deduplicates_overlap_and_preserves_provenance():
    targets = held_first_targets(("005930", "000660"), ("035420", "005930"))

    assert [item.ticker for item in targets] == ["005930", "000660", "035420"]
    assert targets[0].provenance == (
        EvaluationProvenance.HELD,
        EvaluationProvenance.SCREENED,
    )
    assert targets[-1].provenance == (EvaluationProvenance.SCREENED,)


def test_snapshot_universe_sorts_holdings_then_preserves_screen_rank_and_overlap():
    adapter = FakeAdapter(
        [envelope()],
        envelope(
            {"pdno": "005930", "hldg_qty": "8", "ord_psbl_qty": "5", "pchs_avg_pric": "65000"},
            {"pdno": "000660", "hldg_qty": "1", "ord_psbl_qty": "1", "pchs_avg_pric": "110000"},
            summary={"dnca_tot_amt": "900000", "tot_evlu_amt": "1900000"},
        ),
    )
    candidates = (
        ScreenerCandidate("035420", "KOSPI", 9.0, 1_000_000.0),
        ScreenerCandidate("005930", "KOSPI", 8.0, 1_000_000.0),
        ScreenerCandidate("068270", "KOSPI", 7.0, 1_000_000.0),
    )

    universe = build_evaluation_universe(collect(adapter), candidates)

    assert universe.executable is True
    assert [target.ticker for target in universe.targets] == [
        "000660", "005930", "035420", "068270"
    ]
    assert universe.targets[1].provenance == (
        EvaluationProvenance.HELD,
        EvaluationProvenance.SCREENED,
    )
    assert len({target.ticker for target in universe.targets}) == 4


def test_incomplete_account_universe_is_visible_but_not_executable():
    adapter = FakeAdapter(
        [envelope()],
        envelope(
            {"pdno": "005930", "hldg_qty": "8", "ord_psbl_qty": "", "pchs_avg_pric": "65000"},
            summary={"dnca_tot_amt": "900000", "tot_evlu_amt": "1900000"},
        ),
    )

    universe = build_evaluation_universe(collect(adapter), ())

    assert universe.executable is False
    assert universe.reason_code == "ACCOUNT_DATA_INCOMPLETE"


def test_held_context_uses_normalized_position_and_open_sell_quantity():
    adapter = FakeAdapter(
        [
            envelope(
                {
                    "odno": "SELL-1", "pdno": "005930", "sll_buy_dvsn_cd": "01",
                    "ord_qty": "4", "tot_ccld_qty": "1", "rmn_qty": "3",
                    "ord_unpr": "70000",
                }
            )
        ],
        envelope(
            {"pdno": "005930", "hldg_qty": "8", "ord_psbl_qty": "5", "pchs_avg_pric": "65000"},
            summary={"dnca_tot_amt": "900000", "tot_evlu_amt": "1900000"},
        ),
    )

    held = build_held_position_context(collect(adapter), "005930", current_price=71500.0)

    assert held == HeldPositionContext(
        average_price=65000.0,
        total_quantity=8,
        orderable_quantity=5,
        current_price=71500.0,
        unrealized_return=0.1,
        open_sell_quantity=3,
    )


def test_ticker_market_gap_is_attributable_without_blocking_sibling():
    adapter = FakeAdapter(
        [envelope()],
        envelope(
            {"pdno": "005930", "hldg_qty": "8", "ord_psbl_qty": "5", "pchs_avg_pric": "65000"},
            {"pdno": "000660", "hldg_qty": "1", "ord_psbl_qty": "1", "pchs_avg_pric": "110000"},
            summary={"dnca_tot_amt": "900000", "tot_evlu_amt": "1900000"},
        ),
    )
    universe = build_evaluation_universe(collect(adapter), ())

    missing = evaluate_ticker_evidence(universe, universe.targets[0], market_evidence_available=False)
    sibling = evaluate_ticker_evidence(universe, universe.targets[1], market_evidence_available=True)

    assert (missing.status, missing.decision, missing.reason_code) == (
        "DATA_INCOMPLETE", "HOLD", "MARKET_DATA_INCOMPLETE"
    )
    assert missing.executable is False
    assert sibling.executable is True
