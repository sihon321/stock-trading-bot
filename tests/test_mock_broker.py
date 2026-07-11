"""Tests for the in-memory paper-account MockBroker (Plan 02-03, Task 1).

MockBroker must satisfy the existing synchronous :class:`~trading_bot.ports.Broker`
Protocol, mutate only in-memory state through explicit ``place_order`` calls, and
import no KIS/LLM/pykrx/HTTP/adapter code (T-02-09/T-02-10).
"""

import importlib
import inspect
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from trading_bot.domain import Money, Order, OrderSide, Position, Ticker
from trading_bot.mock_broker import MockBroker
from trading_bot.ports import Broker
from trading_bot.data_models import SourceHealth, SourceStatus
from trading_bot.kis_quote import KisQuoteResult


FORBIDDEN_MODULE_PREFIXES = (
    "anthropic",
    "openai",
    "pykrx",
    "requests",
    "httpx",
)

FORBIDDEN_LOCAL_MODULE_FRAGMENTS = (
    "adapter",
    "kis",
    "naver",
    "scrap",
    "config",
)


TICKER = Ticker("005930")


def _buy(quantity: int, price: float = 70000.0) -> Order:
    return Order(
        ticker=TICKER,
        side=OrderSide.BUY,
        quantity=quantity,
        limit_price=Money(price, "KRW"),
    )


def _sell(quantity: int, price: float = 72000.0) -> Order:
    return Order(
        ticker=TICKER,
        side=OrderSide.SELL,
        quantity=quantity,
        limit_price=Money(price, "KRW"),
    )


def test_mock_broker_satisfies_broker_protocol() -> None:
    broker = MockBroker(cash=Money(1_000_000.0, "KRW"))

    assert isinstance(broker, Broker)


def test_mock_broker_methods_are_synchronous() -> None:
    assert not inspect.iscoroutinefunction(MockBroker.get_position)
    assert not inspect.iscoroutinefunction(MockBroker.place_order)


def test_get_position_returns_seeded_position_without_external_calls() -> None:
    held = Position(ticker=TICKER, quantity=5, average_price=Money(70000.0, "KRW"))
    broker = MockBroker(cash=Money(1_000_000.0, "KRW"), positions=[held])

    assert broker.get_position(TICKER) == held
    assert broker.get_position(Ticker("000660")) is None


def test_consecutive_orders_return_deterministic_unique_ids() -> None:
    broker = MockBroker(cash=Money(10_000_000.0, "KRW"))

    first = broker.place_order(_buy(1))
    second = broker.place_order(_buy(1))
    third = broker.place_order(_buy(1))

    assert first != second != third
    assert first == "MOCK-1"
    assert second == "MOCK-2"
    assert third == "MOCK-3"


def test_buy_increases_position_and_reduces_cash() -> None:
    broker = MockBroker(cash=Money(1_000_000.0, "KRW"))

    broker.place_order(_buy(quantity=10, price=70000.0))

    position = broker.get_position(TICKER)
    assert position is not None
    assert position.quantity == 10
    # 1,000,000 - 10 * 70,000 = 300,000.
    assert broker.cash.amount == pytest.approx(300000.0)


def test_repeated_buys_average_the_entry_price() -> None:
    broker = MockBroker(cash=Money(10_000_000.0, "KRW"))

    broker.place_order(_buy(quantity=10, price=70000.0))
    broker.place_order(_buy(quantity=10, price=90000.0))

    position = broker.get_position(TICKER)
    assert position is not None
    assert position.quantity == 20
    # (10*70000 + 10*90000) / 20 = 80,000.
    assert position.average_price.amount == pytest.approx(80000.0)


def test_sell_reduces_position_and_increases_cash() -> None:
    held = Position(ticker=TICKER, quantity=10, average_price=Money(70000.0, "KRW"))
    broker = MockBroker(cash=Money(0.0, "KRW"), positions=[held])

    broker.place_order(_sell(quantity=4, price=72000.0))

    position = broker.get_position(TICKER)
    assert position is not None
    assert position.quantity == 6
    # 0 + 4 * 72,000 = 288,000.
    assert broker.cash.amount == pytest.approx(288000.0)


def test_full_sell_removes_the_position() -> None:
    held = Position(ticker=TICKER, quantity=5, average_price=Money(70000.0, "KRW"))
    broker = MockBroker(cash=Money(0.0, "KRW"), positions=[held])

    broker.place_order(_sell(quantity=5, price=72000.0))

    assert broker.get_position(TICKER) is None


def test_order_history_records_placed_orders_in_order() -> None:
    broker = MockBroker(cash=Money(10_000_000.0, "KRW"))
    first = _buy(1)
    second = _buy(2)

    broker.place_order(first)
    broker.place_order(second)

    assert broker.order_history == [first, second]


def test_state_is_unchanged_when_no_order_is_placed() -> None:
    held = Position(ticker=TICKER, quantity=5, average_price=Money(70000.0, "KRW"))
    broker = MockBroker(cash=Money(1_000_000.0, "KRW"), positions=[held])

    # Reading state must not mutate it.
    broker.get_position(TICKER)
    broker.get_position(Ticker("000660"))

    assert broker.cash.amount == pytest.approx(1_000_000.0)
    assert broker.get_position(TICKER) == held
    assert broker.order_history == []


def test_invalid_quantity_raises_and_does_not_mutate_state() -> None:
    broker = MockBroker(cash=Money(1_000_000.0, "KRW"))

    with pytest.raises(ValueError):
        broker.place_order(_buy(quantity=0))

    assert broker.cash.amount == pytest.approx(1_000_000.0)
    assert broker.order_history == []


def test_selling_more_than_held_raises_and_does_not_mutate_state() -> None:
    held = Position(ticker=TICKER, quantity=3, average_price=Money(70000.0, "KRW"))
    broker = MockBroker(cash=Money(0.0, "KRW"), positions=[held])

    with pytest.raises(ValueError):
        broker.place_order(_sell(quantity=5))

    assert broker.get_position(TICKER) == held
    assert broker.cash.amount == pytest.approx(0.0)
    assert broker.order_history == []


def test_mock_broker_import_has_no_forbidden_side_effects() -> None:
    before_import = set(sys.modules)
    importlib.import_module("trading_bot.mock_broker")

    loaded = set(sys.modules) - before_import
    for prefix in FORBIDDEN_MODULE_PREFIXES:
        assert prefix not in loaded
    forbidden_local = [
        name
        for name in loaded
        if name.startswith("trading_bot.")
        and any(fragment in name for fragment in FORBIDDEN_LOCAL_MODULE_FRAGMENTS)
    ]
    assert forbidden_local == []


@pytest.mark.parametrize(("age", "allowed"), [(10.0, True), (10.001, False)])
def test_mock_pre_submit_refresh_is_inclusive_and_blocks_without_mutation(age, allowed) -> None:
    from trading_bot.kis_broker import MarketClosedError

    now = datetime(2026, 7, 13, 10, 0, tzinfo=ZoneInfo("Asia/Seoul"))
    calls = []
    events = []

    def reader(ticker):
        calls.append(ticker)
        return KisQuoteResult(
            Money(70_000, "KRW"),
            SourceHealth(source="kis_quote", status=SourceStatus.AVAILABLE, reason="ok"),
            now - timedelta(seconds=age),
        )

    broker = MockBroker(
        cash=Money(1_000_000, "KRW"), pre_submit_quote_reader=reader,
        evidence_sink=events.append, clock=lambda: now,
    )
    if allowed:
        broker.place_order(_buy(1), order_intent_id="intent-mock", origin_run_id="run")
        assert broker.cash.amount == 930_000
    else:
        with pytest.raises(MarketClosedError):
            broker.place_order(_buy(1), order_intent_id="intent-mock", origin_run_id="run")
        assert broker.cash.amount == 1_000_000
        assert broker.order_history == []
    assert calls == ["005930"]
    assert events[0].detail["verdict"] == ("PASS" if allowed else "BLOCK")
