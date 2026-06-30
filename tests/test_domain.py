import dataclasses
import importlib
import sys

from trading_bot.domain import (
    DataContext,
    Decision,
    LLMSignal,
    Money,
    Order,
    OrderSide,
    Position,
    Ticker,
)


FORBIDDEN_MODULE_PREFIXES = (
    "anthropic",
    "openai",
    "pykrx",
    "requests",
    "httpx",
)

FORBIDDEN_LOCAL_MODULE_FRAGMENTS = (
    "adapter",
    "broker",
    "execution",
    "kis",
    "naver",
    "scrap",
)


def test_domain_objects_are_stdlib_enums_and_frozen_dataclasses() -> None:
    ticker = Ticker("005930")
    cash = Money(70000.0, "KRW")
    order = Order(ticker=ticker, side=OrderSide.BUY, quantity=10, limit_price=cash)
    position = Position(ticker=ticker, quantity=10, average_price=cash)

    assert Decision.BUY.value == "BUY"
    assert Decision.SELL.value == "SELL"
    assert Decision.HOLD.value == "HOLD"
    assert OrderSide.BUY.value == "BUY"
    assert OrderSide.SELL.value == "SELL"
    assert dataclasses.is_dataclass(order)
    assert dataclasses.is_dataclass(position)

    try:
        order.quantity = 11
    except dataclasses.FrozenInstanceError:
        pass
    else:  # pragma: no cover - only reached by a mutable dataclass
        raise AssertionError("Order must be frozen")


def test_llm_signal_matches_strict_json_contract_shape() -> None:
    signal = LLMSignal(
        decision=Decision.BUY,
        confidence=0.82,
        reason="Momentum and volume both improved.",
    )

    assert dataclasses.is_dataclass(signal)
    assert signal.decision is Decision.BUY
    assert signal.confidence == 0.82
    assert signal.reason == "Momentum and volume both improved."
    assert set(signal.__dataclass_fields__) == {"decision", "confidence", "reason"}


def test_data_context_is_lightweight_ticker_context() -> None:
    context = DataContext(
        ticker=Ticker("005930"),
        current_price=Money(70500.0, "KRW"),
        technicals={"rsi": 55.0},
        news=["Samsung Electronics earnings preview"],
    )

    assert dataclasses.is_dataclass(context)
    assert context.ticker.value == "005930"
    assert context.current_price.amount == 70500.0
    assert context.technicals == {"rsi": 55.0}
    assert context.news == ["Samsung Electronics earnings preview"]


def test_domain_import_has_no_settings_or_adapter_side_effects() -> None:
    importlib.import_module("trading_bot.domain")

    loaded_modules = set(sys.modules)
    for prefix in FORBIDDEN_MODULE_PREFIXES:
        assert prefix not in loaded_modules

    forbidden_local = [
        name
        for name in loaded_modules
        if name.startswith("trading_bot.")
        and any(fragment in name for fragment in FORBIDDEN_LOCAL_MODULE_FRAGMENTS)
    ]
    assert forbidden_local == []
    assert "trading_bot.config" not in loaded_modules
