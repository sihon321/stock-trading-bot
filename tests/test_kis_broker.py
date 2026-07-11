"""Offline tests for the structural KIS Broker adapter."""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from conftest import make_settings
from trading_bot.data_models import SourceHealth, SourceStatus
from trading_bot.domain import Money, Order, OrderSide, Position, Ticker
from trading_bot.kis_order import FillStatus, KisOrderAccount, KisOrderQueryResult
from trading_bot.ports import Broker


def _query_result(output):
    return KisOrderQueryResult(
        output=output,
        health=SourceHealth(source="kis_order", status=SourceStatus.AVAILABLE, reason="ok"),
    )


class _FakeOrderAdapter:
    def __init__(
        self,
        *,
        daily_outputs=None,
        fill_statuses=None,
        post_results=None,
        post_exception: Exception | None = None,
    ) -> None:
        self.daily_outputs = list(daily_outputs or [])
        self.fill_statuses = list(fill_statuses or [])
        self.post_results = list(post_results or ["KIS-POSTED"])
        self.post_exception = post_exception
        self.post_attempts = 0
        self.seen_prices = []

    def inquire_daily_ccld(self, *, ticker=None, order_id=None):
        if self.daily_outputs:
            return _query_result(self.daily_outputs.pop(0))
        return _query_result([])

    def inquire_balance(self):
        return _query_result({"dnca_tot_amt": "1000000"})

    def place_order_cash(self, *, account, order, snapped_price):
        self.post_attempts += 1
        self.seen_prices.append(snapped_price)
        if self.post_exception is not None:
            raise self.post_exception
        order_id = self.post_results.pop(0)

        class _Result:
            def __init__(self, value: str) -> None:
                self.order_id = value

        return _Result(order_id)

    def parse_fill_status(self, output, *, order_id, ticker):
        if self.fill_statuses:
            return self.fill_statuses.pop(0)
        return FillStatus(
            order_id=order_id,
            ticker=ticker,
            ordered_qty=1,
            filled_qty=1,
            remaining_qty=0,
        )


def _order(quantity: int = 5, price: float = 74_321.0) -> Order:
    return Order(
        ticker=Ticker("005930"),
        side=OrderSide.BUY,
        quantity=quantity,
        limit_price=Money(price, "KRW"),
    )


def test_kis_broker_is_broker() -> None:
    from trading_bot.kis_broker import KISBroker

    broker = KISBroker(
        order_adapter=_FakeOrderAdapter(),
        account=KisOrderAccount("12345678", "01"),
        market_clock=lambda: True,
    )

    assert isinstance(broker, Broker)


def test_order_post_not_retried() -> None:
    from trading_bot.kis_broker import AmbiguousSubmissionError, KISBroker

    adapter = _FakeOrderAdapter(post_exception=RuntimeError("single POST failure"))
    broker = KISBroker(
        order_adapter=adapter,
        account=KisOrderAccount("12345678", "01"),
        market_clock=lambda: True,
    )

    with pytest.raises(AmbiguousSubmissionError, match="reconcile before retry"):
        broker.place_order(_order(quantity=1, price=70_000))

    assert adapter.post_attempts == 1


@pytest.mark.parametrize(("age", "allowed"), [(10.0, True), (10.001, False)])
def test_pre_submit_quote_is_refetched_and_ten_seconds_is_inclusive(age, allowed) -> None:
    from trading_bot.kis_broker import KISBroker, MarketClosedError
    from trading_bot.kis_quote import KisQuoteResult

    now = datetime(2026, 7, 13, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    calls = []

    def quote_reader(ticker):
        calls.append(ticker)
        return KisQuoteResult(
            Money(70_000, "KRW"),
            SourceHealth(source="kis_quote", status=SourceStatus.AVAILABLE, reason="ok"),
            now - timedelta(seconds=age),
        )

    adapter = _FakeOrderAdapter()
    broker = KISBroker(
        order_adapter=adapter, account=KisOrderAccount("12345678", "01"),
        market_clock=lambda: True, pre_submit_quote_reader=quote_reader, clock=lambda: now,
    )
    if allowed:
        broker.place_order(_order(quantity=1))
    else:
        with pytest.raises(MarketClosedError, match="stale"):
            broker.place_order(_order(quantity=1))
    assert calls == ["005930"]
    assert adapter.post_attempts == int(allowed)


def test_successful_freshness_evidence_precedes_submission() -> None:
    from trading_bot.kis_broker import KISBroker
    from trading_bot.kis_quote import KisQuoteResult

    now = datetime(2026, 7, 13, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    events = []
    broker = KISBroker(
        order_adapter=_FakeOrderAdapter(), account=KisOrderAccount("12345678", "01"),
        market_clock=lambda: True, clock=lambda: now, evidence_sink=events.append,
        pre_submit_quote_reader=lambda ticker: KisQuoteResult(
            Money(70_000, "KRW"),
            SourceHealth(source="kis_quote", status=SourceStatus.AVAILABLE, reason="ok"),
            now - timedelta(seconds=10),
        ),
    )

    broker.place_order(_order(quantity=1), order_intent_id="intent-fresh")

    kinds = [event.event_type.value for event in events]
    assert kinds.index("FRESHNESS_CHECKED") < kinds.index("SUBMISSION_ATTEMPTED")
    detail = next(event.detail for event in events if event.event_type.value == "FRESHNESS_CHECKED")
    assert detail == {
        "observed_at": (now - timedelta(seconds=10)).isoformat(),
        "checked_at": now.isoformat(), "age_seconds": 10.0,
        "verdict": "PASS", "reason": "fresh", "policy_version": "quote-freshness-v1",
    }


def test_append_only_evidence_has_stable_intent_and_distinct_submission() -> None:
    from trading_bot.kis_broker import KISBroker

    events = []
    broker = KISBroker(
        order_adapter=_FakeOrderAdapter(), account=KisOrderAccount("12345678", "01"),
        market_clock=lambda: True, evidence_sink=events.append,
    )
    broker.place_order(
        _order(quantity=1), order_intent_id="intent-1",
        origin_run_id="origin", observer_run_id="origin",
    )
    assert [event.event_type.value for event in events] == [
        "INTENT_CREATED", "DUPLICATE_CHECKED", "SUBMISSION_ATTEMPTED",
        "SUBMISSION_ACCEPTED", "RECONCILED",
    ]
    assert {event.order_intent_id for event in events} == {"intent-1"}
    submissions = {event.submission_id for event in events if event.submission_id}
    assert len(submissions) == 1
    assert all("response" not in (event.detail or {}) for event in events)


def test_ambiguous_evidence_is_single_shot_and_later_observation_links_runs() -> None:
    from trading_bot.kis_broker import AmbiguousSubmissionError, KISBroker

    events = []
    adapter = _FakeOrderAdapter(post_exception=TimeoutError("do not persist this body"))
    broker = KISBroker(
        order_adapter=adapter, account=KisOrderAccount("12345678", "01"),
        market_clock=lambda: True, evidence_sink=events.append,
    )
    with pytest.raises(AmbiguousSubmissionError) as caught:
        broker.place_order(
            _order(), order_intent_id="intent-a", origin_run_id="origin",
            observer_run_id="origin",
        )
    assert adapter.post_attempts == 1
    assert events[-1].event_type.value == "SUBMISSION_AMBIGUOUS"
    assert "do not persist" not in repr(events[-1].detail)

    adapter.post_exception = None
    broker.reconcile_order(
        order_intent_id="intent-a", origin_run_id="origin", observer_run_id="observer",
        ticker="005930", broker_order_id="KIS-LATER",
        submission_id=caught.value.submission_id,
    )
    observed = events[-1]
    assert observed.origin_run_id == "origin"
    assert observed.observer_run_id == "observer"
    assert observed.order_intent_id == "intent-a"


def test_reconcile_skips_duplicate() -> None:
    from trading_bot.kis_broker import KISBroker

    adapter = _FakeOrderAdapter(
        daily_outputs=[
            [
                {
                    "odno": "KIS-EXISTING",
                    "pdno": "005930",
                    "ord_qty": "5",
                    "tot_ccld_qty": "0",
                    "rmn_qty": "5",
                }
            ]
        ]
    )
    broker = KISBroker(
        order_adapter=adapter,
        account=KisOrderAccount("12345678", "01"),
        market_clock=lambda: True,
    )

    assert broker.place_order(_order()) == "KIS-EXISTING"
    assert adapter.post_attempts == 0


def test_partial_fill_reconciled() -> None:
    from trading_bot.kis_broker import KISBroker

    adapter = _FakeOrderAdapter(
        fill_statuses=[
            FillStatus(
                order_id="KIS-POSTED",
                ticker="005930",
                ordered_qty=5,
                filled_qty=2,
                remaining_qty=3,
            )
        ]
    )
    broker = KISBroker(
        order_adapter=adapter,
        account=KisOrderAccount("12345678", "01"),
        market_clock=lambda: True,
    )

    assert broker.place_order(_order()) == "KIS-POSTED"
    assert adapter.post_attempts == 1
    assert broker.get_position(Ticker("005930")) == Position(
        ticker=Ticker("005930"),
        quantity=2,
        average_price=Money(74_300, "KRW"),
    )
    assert broker.last_reconciliation is not None
    assert broker.last_reconciliation.requested_qty == 5
    assert broker.last_reconciliation.filled_qty == 2
    assert broker.last_reconciliation.remaining_qty == 3


def test_tick_snap_and_market_guard() -> None:
    from trading_bot.kis_broker import KISBroker, MarketClosedError

    adapter = _FakeOrderAdapter()
    broker = KISBroker(
        order_adapter=adapter,
        account=KisOrderAccount("12345678", "01"),
        market_clock=lambda: True,
    )

    broker.place_order(_order(quantity=1, price=74_321))
    assert adapter.seen_prices == [74_300]

    closed_adapter = _FakeOrderAdapter()
    closed_broker = KISBroker(
        order_adapter=closed_adapter,
        account=KisOrderAccount("12345678", "01"),
        market_clock=lambda: False,
    )

    with pytest.raises(MarketClosedError):
        closed_broker.place_order(_order(quantity=1, price=74_321))
    assert closed_adapter.post_attempts == 0


def test_build_kis_broker_requires_shared_token_manager() -> None:
    from trading_bot.kis_broker import build_kis_broker

    settings = make_settings()

    with pytest.raises(ValueError, match="shared KisTokenManager"):
        build_kis_broker(settings, token_manager=None)
