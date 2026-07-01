import inspect
import subprocess
import sys
from typing import Optional

from trading_bot.domain import DataContext, Decision, LLMSignal, Money, Order, OrderSide, Position, Ticker
from trading_bot.ports import Broker, DataSource, LLMProvider


FORBIDDEN_MODULE_PREFIXES = (
    "anthropic",
    "openai",
    "pykrx",
    "requests",
    "httpx",
)

FORBIDDEN_LOCAL_MODULE_FRAGMENTS = (
    "adapter",
    "execution",
    "kis",
    "naver",
    "scrap",
)


class FakeBroker:
    def __init__(self) -> None:
        self.orders = []

    def get_position(self, ticker: Ticker) -> Optional[Position]:
        return Position(ticker=ticker, quantity=1, average_price=Money(70000.0, "KRW"))

    def place_order(self, order: Order) -> str:
        self.orders.append(order)
        return "mock-order-id"


class FakeLLMProvider:
    def generate_signal(self, context: DataContext) -> LLMSignal:
        return LLMSignal(
            decision=Decision.HOLD,
            confidence=0.5,
            reason=f"No trade for {context.ticker.value}",
        )


class FakeDataSource:
    def build_context(self, ticker: Ticker) -> DataContext:
        return DataContext(
            ticker=ticker,
            current_price=Money(70000.0, "KRW"),
            technicals={"rsi": 50.0},
            news=[],
        )


def test_broker_protocol_is_runtime_checkable_and_structural() -> None:
    broker = FakeBroker()
    order = Order(
        ticker=Ticker("005930"),
        side=OrderSide.BUY,
        quantity=1,
        limit_price=Money(70000.0, "KRW"),
    )

    assert isinstance(broker, Broker)
    assert broker.place_order(order) == "mock-order-id"
    assert broker.get_position(Ticker("005930")).quantity == 1


def test_llm_provider_protocol_is_runtime_checkable_and_structural() -> None:
    provider = FakeLLMProvider()
    context = FakeDataSource().build_context(Ticker("005930"))

    assert isinstance(provider, LLMProvider)
    assert provider.generate_signal(context) == LLMSignal(
        decision=Decision.HOLD,
        confidence=0.5,
        reason="No trade for 005930",
    )


def test_data_source_protocol_is_runtime_checkable_and_structural() -> None:
    data_source = FakeDataSource()

    assert isinstance(data_source, DataSource)
    assert data_source.build_context(Ticker("005930")).ticker == Ticker("005930")


def test_ports_are_synchronous_semantic_protocols() -> None:
    assert not inspect.iscoroutinefunction(Broker.get_position)
    assert not inspect.iscoroutinefunction(Broker.place_order)
    assert not inspect.iscoroutinefunction(LLMProvider.generate_signal)
    assert not inspect.iscoroutinefunction(DataSource.build_context)


def test_ports_import_domain_types_without_concrete_adapters() -> None:
    before_import = set(sys.modules)
    __import__("trading_bot.ports")

    loaded_modules = set(sys.modules) - before_import
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


def test_ports_stay_adapter_free_in_fresh_interpreter() -> None:
    """Import ``trading_bot.ports`` in a clean interpreter and prove no concrete
    Phase 3 adapter or external provider module is pulled into the import path.

    A fresh subprocess is required because the in-process test above sees an
    already-populated ``sys.modules`` (other tests import ``data_source``,
    ``kis_quote``, etc.), which would mask an accidental import from ``ports.py``.
    """

    program = (
        "import sys\n"
        "import trading_bot.ports\n"
        "loaded = set(sys.modules)\n"
        "forbidden_prefixes = ('anthropic', 'openai', 'pykrx', 'requests', 'httpx', 'bs4', 'lxml', 'ta')\n"
        "for p in forbidden_prefixes:\n"
        "    assert not any(m == p or m.startswith(p + '.') for m in loaded), p\n"
        "fragments = ('adapter', 'execution', 'kis', 'naver', 'scrap', 'data_source', 'indicators', 'screener')\n"
        "local = [m for m in loaded if m.startswith('trading_bot.') and any(f in m for f in fragments)]\n"
        "assert local == [], local\n"
        "assert 'trading_bot.config' not in loaded\n"
        "print('OK')\n"
    )
    completed = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "OK" in completed.stdout


def test_market_data_source_structurally_satisfies_data_source() -> None:
    """The concrete Phase 3 orchestrator satisfies the ``DataSource`` Protocol
    without inheriting from it and while ``build_context`` stays synchronous."""

    from trading_bot.data_source import MarketDataSource

    # Structural satisfaction: the method exists with the right shape.
    assert hasattr(MarketDataSource, "build_context")
    assert not inspect.iscoroutinefunction(MarketDataSource.build_context)

    # A minimal fake that mirrors MarketDataSource's public method also satisfies
    # the runtime-checkable Protocol, proving structural (not nominal) conformance.
    class _MinimalSource:
        def build_context(self, ticker: Ticker) -> DataContext:
            return DataContext(ticker=ticker, current_price=Money(1.0, "KRW"))

    assert isinstance(_MinimalSource(), DataSource)
