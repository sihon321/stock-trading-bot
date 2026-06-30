# Phase 02: mock-execution-core - Pattern Map

**Mapped:** 2026-07-01
**Files analyzed:** 9
**Analogs found:** 9 / 9

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `trading_bot/signal_parser.py` | utility | transform | `trading_bot/domain.py` + `trading_bot/config.py` | partial |
| `trading_bot/risk.py` | service | transform | `trading_bot/domain.py` | partial |
| `trading_bot/execution.py` | service | request-response | `trading_bot/ports.py` + `tests/test_ports.py` | role-match |
| `trading_bot/mock_broker.py` | service | CRUD | `tests/test_ports.py` | role-match |
| `trading_bot/config.py` | config | request-response | `trading_bot/config.py` | exact |
| `tests/test_signal_parser.py` | test | transform | `tests/test_domain.py` | role-match |
| `tests/test_risk.py` | test | transform | `tests/test_domain.py` | role-match |
| `tests/test_execution.py` | test | request-response | `tests/test_ports.py` + `tests/test_config.py` | role-match |
| `tests/test_mock_broker.py` | test | CRUD | `tests/test_ports.py` | role-match |

## Pattern Assignments

### `trading_bot/signal_parser.py` (utility, transform)

**Analog:** `trading_bot/domain.py` for stdlib immutable value objects; `trading_bot/config.py` for explicit validation errors.

**Imports pattern** (`trading_bot/domain.py` lines 3-7):
```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Sequence
```

**Core value-object pattern** (`trading_bot/domain.py` lines 69-75):
```python
@dataclass(frozen=True)
class LLMSignal:
    """Strict JSON-compatible LLM trading signal shape."""

    decision: Decision
    confidence: float
    reason: str
```

**Validation/error pattern** (`trading_bot/config.py` lines 54-62):
```python
@model_validator(mode="after")
def validate_safety_gates(self) -> "Settings":
    if self.trading_mode is TradingMode.REAL and not self.confirm_real_trading:
        raise ValueError(
            "TRADING_MODE=real requires CONFIRM_REAL_TRADING=yes before "
            "real trading configuration can start"
        )
    self._require_selected_llm_key()
    return self
```

**Apply to parser:** define `SignalParseError(ValueError)` and frozen `ParsedSignal`; import stdlib `json`; import `Decision` and `LLMSignal`; raise on malformed JSON, missing fields, unknown decision, confidence outside `0.0..1.0`, or blank reason. Preserve extras as diagnostics instead of mutating `LLMSignal`.

---

### `trading_bot/risk.py` (service, transform)

**Analog:** `trading_bot/domain.py`

**Imports pattern** (`trading_bot/domain.py` lines 3-7):
```python
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Sequence
```

**Enum/dataclass pattern** (`trading_bot/domain.py` lines 10-23, 50-57):
```python
class Decision(str, Enum):
    """Machine-checkable trading signal decisions."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class OrderSide(str, Enum):
    """Executable order sides."""

    BUY = "BUY"
    SELL = "SELL"


@dataclass(frozen=True)
class Position:
    """Current holding for a ticker."""

    ticker: Ticker
    quantity: int
    average_price: Money
```

**Apply to risk:** model risk outputs as frozen dataclasses and string enums in the same style. Keep functions pure: accept `Position | None`, `Money`, stop-loss/take-profit thresholds, and daily-loss state as explicit inputs; return a decision object rather than logging or placing orders.

---

### `trading_bot/execution.py` (service, request-response)

**Analog:** `trading_bot/ports.py` for synchronous semantic boundaries; `tests/test_ports.py` for structural fake broker usage.

**Imports pattern** (`trading_bot/ports.py` lines 3-7):
```python
from __future__ import annotations

from typing import Optional, Protocol, runtime_checkable

from trading_bot.domain import DataContext, LLMSignal, Order, Position, Ticker
```

**Broker boundary pattern** (`trading_bot/ports.py` lines 10-20):
```python
@runtime_checkable
class Broker(Protocol):
    """Broker operations needed by execution logic."""

    def get_position(self, ticker: Ticker) -> Optional[Position]:
        """Return the current position for a ticker, if any."""
        ...

    def place_order(self, order: Order) -> str:
        """Place an order and return the broker's order identifier."""
        ...
```

**Order construction pattern** (`tests/test_ports.py` lines 57-68):
```python
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
```

**Apply to execution:** consume `Broker` as a dependency, never a concrete adapter. Build `Order` intents from existing domain types, branch on `dry_run` before `broker.place_order`, catch `SignalParseError` at the orchestration boundary and convert to HOLD/no-order, and evaluate risk before LLM action.

---

### `trading_bot/mock_broker.py` (service, CRUD)

**Analog:** `tests/test_ports.py`

**Imports pattern** (`tests/test_ports.py` lines 1-6):
```python
import inspect
import sys
from typing import Optional

from trading_bot.domain import DataContext, Decision, LLMSignal, Money, Order, OrderSide, Position, Ticker
from trading_bot.ports import Broker, DataSource, LLMProvider
```

**Structural implementation pattern** (`tests/test_ports.py` lines 26-35):
```python
class FakeBroker:
    def __init__(self) -> None:
        self.orders = []

    def get_position(self, ticker: Ticker) -> Optional[Position]:
        return Position(ticker=ticker, quantity=1, average_price=Money(70000.0, "KRW"))

    def place_order(self, order: Order) -> str:
        self.orders.append(order)
        return "mock-order-id"
```

**Apply to mock broker:** implement the same `get_position` / `place_order` method names and synchronous behavior. Keep state in memory only, record orders deterministically, update cash/positions only when `place_order` is called, and avoid importing config, KIS, HTTP, or LLM packages.

---

### `trading_bot/config.py` (config, request-response)

**Analog:** `trading_bot/config.py`

**Settings pattern** (lines 36-53):
```python
class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
    )

    trading_mode: TradingMode = TradingMode.MOCK
    confirm_real_trading: bool = False
    llm_provider: LLMProviderName = LLMProviderName.CLAUDE
    anthropic_api_key: Optional[SecretStr] = None
    openai_api_key: Optional[SecretStr] = None
    kis_mock: KisCredentialGroup
    kis_real: KisCredentialGroup
    dry_run: bool = True
```

**Startup reporting pattern** (lines 93-107):
```python
def startup_banner(settings: Settings) -> str:
    """Build an allowlisted startup safety banner without secret values."""

    active_kis = settings.active_kis
    return "\n".join(
        (
            "Trading bot startup safety",
            f"Trading mode: {settings.trading_mode.value}",
            f"KIS environment: {active_kis.label}",
            f"LLM provider: {settings.llm_provider.value}",
            f"Dry run: {settings.dry_run}",
            f"Real trading confirmed: {settings.confirm_real_trading}",
            "Secrets: REDACTED",
        )
    )
```

**Apply to settings:** add execution/risk defaults as typed fields on `Settings`: BUY/SELL confidence thresholds default `0.8`, buy cash fraction, max position value, stop-loss percent, take-profit percent, and daily-loss threshold. Keep `extra="ignore"` and do not print secrets or new sensitive values.

---

### `tests/test_signal_parser.py` (test, transform)

**Analog:** `tests/test_domain.py`

**Domain assertion style** (lines 57-68):
```python
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
```

**Import-boundary pattern** (lines 86-101):
```python
def test_domain_import_has_no_settings_or_adapter_side_effects() -> None:
    before_import = set(sys.modules)
    importlib.import_module("trading_bot.domain")

    loaded_modules = set(sys.modules) - before_import
    for prefix in FORBIDDEN_MODULE_PREFIXES:
        assert prefix not in loaded_modules
```

**Apply to parser tests:** assert valid payloads return `ParsedSignal` containing canonical `LLMSignal`, raw input, and ignored-field diagnostics. Parametrize invalid payloads with `pytest.raises(SignalParseError)`. Add import-boundary assertions for `trading_bot.signal_parser`.

---

### `tests/test_risk.py` (test, transform)

**Analog:** `tests/test_domain.py`

**Frozen dataclass test style** (lines 35-55):
```python
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
```

**Apply to risk tests:** construct `Position`, `Money`, and risk config inputs directly; assert stop-loss and take-profit return SELL decisions without an `LLMSignal`; assert daily-loss kill switch blocks BUY only and allows SELL/risk exits.

---

### `tests/test_execution.py` (test, request-response)

**Analog:** `tests/test_ports.py` plus `tests/test_config.py`

**Fake dependency pattern** (`tests/test_ports.py` lines 26-35):
```python
class FakeBroker:
    def __init__(self) -> None:
        self.orders = []

    def get_position(self, ticker: Ticker) -> Optional[Position]:
        return Position(ticker=ticker, quantity=1, average_price=Money(70000.0, "KRW"))

    def place_order(self, order: Order) -> str:
        self.orders.append(order)
        return "mock-order-id"
```

**Log capture pattern** (`tests/test_config.py` lines 77-92):
```python
def test_settings_load_secrets_without_repr_banner_or_log_leaks(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    set_base_env(monkeypatch)
    settings = Settings()

    with caplog.at_level(logging.INFO):
        logging.getLogger("trading_bot.config").info(startup_banner(settings))
```

**Apply to execution tests:** use fake brokers or `MockBroker` fixtures to assert confidence gates, BUY sizing, SELL requires held position, parser failure becomes HOLD/no-order, risk override suppresses LLM action, and dry-run logs intended order without calling `place_order`.

---

### `tests/test_mock_broker.py` (test, CRUD)

**Analog:** `tests/test_ports.py`

**Protocol conformance pattern** (lines 57-68):
```python
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
```

**Synchronous boundary pattern** (lines 90-94):
```python
def test_ports_are_synchronous_semantic_protocols() -> None:
    assert not inspect.iscoroutinefunction(Broker.get_position)
    assert not inspect.iscoroutinefunction(Broker.place_order)
    assert not inspect.iscoroutinefunction(LLMProvider.generate_signal)
    assert not inspect.iscoroutinefunction(DataSource.build_context)
```

**Apply to mock broker tests:** assert `MockBroker` is an instance of `Broker`, methods are synchronous, order IDs are deterministic, BUY/SELL mutate in-memory state only through `place_order`, and no external adapter modules load.

## Shared Patterns

### Immutable Domain Objects
**Source:** `trading_bot/domain.py` lines 25-75  
**Apply to:** `signal_parser.py`, `risk.py`, `execution.py`, tests
```python
@dataclass(frozen=True)
class Order:
    """Order intent produced by execution logic."""

    ticker: Ticker
    side: OrderSide
    quantity: int
    limit_price: Money
```

### Synchronous Semantic Ports
**Source:** `trading_bot/ports.py` lines 10-20  
**Apply to:** `execution.py`, `mock_broker.py`, `tests/test_execution.py`, `tests/test_mock_broker.py`
```python
@runtime_checkable
class Broker(Protocol):
    """Broker operations needed by execution logic."""

    def get_position(self, ticker: Ticker) -> Optional[Position]:
        """Return the current position for a ticker, if any."""
        ...

    def place_order(self, order: Order) -> str:
        """Place an order and return the broker's order identifier."""
        ...
```

### Import Boundary Tests
**Source:** `tests/test_ports.py` lines 97-112  
**Apply to:** all new core modules
```python
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
```

### Settings Environment Tests
**Source:** `tests/test_config.py` lines 24-69  
**Apply to:** config threshold/cap additions
```python
ENV_KEYS = (
    "TRADING_MODE",
    "CONFIRM_REAL_TRADING",
    "LLM_PROVIDER",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "KIS_MOCK__DOMAIN",
    "KIS_MOCK__APP_KEY",
    "KIS_MOCK__APP_SECRET",
    "KIS_MOCK__TR_ID_PROFILE",
    "KIS_MOCK__LABEL",
    "KIS_REAL__DOMAIN",
    "KIS_REAL__APP_KEY",
    "KIS_REAL__APP_SECRET",
    "KIS_REAL__TR_ID_PROFILE",
    "KIS_REAL__LABEL",
    "DRY_RUN",
)
```

Add new env keys for execution/risk settings to this helper when extending `Settings`, then assert defaults and overrides.

### Pytest Configuration
**Source:** `pyproject.toml` lines 20-23  
**Apply to:** all Phase 2 tests
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
addopts = "-ra"
```

Use `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` for full validation, matching research.

## No Analog Found

No file is completely without a local analog, but several have only partial analogs because Phase 1 contains foundations rather than execution logic.

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `trading_bot/signal_parser.py` | utility | transform | No existing raw JSON parser; copy domain dataclass style and config validation style, then use RESEARCH.md parser example. |
| `trading_bot/risk.py` | service | transform | No existing risk service; copy domain value-object style and keep pure functions per RESEARCH.md. |
| `trading_bot/execution.py` | service | request-response | No existing orchestrator; copy port dependency style and fake broker tests, then apply RESEARCH.md dry-run/risk-first ordering. |

## Metadata

**Analog search scope:** `trading_bot/`, `tests/`, `pyproject.toml`, Phase 2 context/research  
**Files scanned:** 9 source/test/config files plus 2 phase artifacts  
**Pattern extraction date:** 2026-07-01  
**Project instructions:** no root `AGENTS.md` found; project skill directories contain GSD workflow skills, with no implementation-specific `rules/*.md` found in research.
