# Phase 3: Data Pipeline - Pattern Map

**Mapped:** 2026-07-01
**Files analyzed:** 18
**Analogs found:** 18 / 18

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `pyproject.toml` | config | dependency configuration | `pyproject.toml` | exact |
| `trading_bot/config.py` | config | request-response | `trading_bot/config.py` | exact |
| `trading_bot/data_models.py` | model | request-response | `trading_bot/domain.py`, `trading_bot/execution.py` | role-match |
| `trading_bot/data_source.py` | service/orchestrator | request-response | `trading_bot/execution.py`, `trading_bot/ports.py` | role-match |
| `trading_bot/indicators.py` | utility | transform | `trading_bot/risk.py` | role-match |
| `trading_bot/screener.py` | service/utility | batch, transform | `trading_bot/risk.py`, `trading_bot/execution.py` | role-match |
| `trading_bot/pykrx_adapter.py` | service/adapter | request-response, batch | `trading_bot/mock_broker.py`, `trading_bot/signal_parser.py` | partial |
| `trading_bot/kis_auth.py` | service/adapter | request-response, cached token | `trading_bot/config.py`, `trading_bot/mock_broker.py` | partial |
| `trading_bot/kis_quote.py` | service/adapter | request-response | `trading_bot/mock_broker.py`, `trading_bot/config.py` | partial |
| `trading_bot/naver_news.py` | service/adapter | request-response, transform | `trading_bot/signal_parser.py` | partial |
| `tests/test_pykrx_adapter.py` | test | request-response, batch | `tests/test_mock_broker.py`, `tests/test_signal_parser.py` | role-match |
| `tests/test_indicators.py` | test | transform | `tests/test_risk.py` | exact |
| `tests/test_screener.py` | test | batch, transform | `tests/test_risk.py`, `tests/test_execution.py` | role-match |
| `tests/test_kis_auth.py` | test | request-response, cached token | `tests/test_config.py`, `tests/test_mock_broker.py` | role-match |
| `tests/test_kis_quote.py` | test | request-response | `tests/test_mock_broker.py`, `tests/test_config.py` | role-match |
| `tests/test_naver_news.py` | test | request-response, transform | `tests/test_signal_parser.py` | role-match |
| `tests/test_data_source.py` | test | request-response | `tests/test_execution.py`, `tests/test_ports.py` | exact |
| `tests/test_ports.py` | test | import-boundary | `tests/test_ports.py` | exact |

## Pattern Assignments

### `pyproject.toml` (config, dependency configuration)

**Analog:** `pyproject.toml`

**Dependency block pattern** (lines 5-15):
```toml
[project]
name = "stock-trading-bot"
version = "0.1.0"
description = "Safety-first Korean-market stock trading bot foundation."
readme = ".planning/PROJECT.md"
requires-python = ">=3.9"
dependencies = [
    "pydantic-settings==2.11.0",
    "pydantic==2.13.4",
    "pytest==8.4.2",
]
```

**Apply:** update `requires-python` before adding current `pykrx`, because research says current `pykrx` requires Python `>=3.10`. Keep dependency pins explicit like existing pins.

---

### `trading_bot/config.py` (config, request-response)

**Analog:** `trading_bot/config.py`

**Imports and grouped credential pattern** (lines 5-10, 26-34):
```python
from enum import Enum
from typing import Optional

from pydantic import BaseModel, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class KisCredentialGroup(BaseModel):
    """One atomic KIS environment credential group."""

    domain: str
    app_key: SecretStr
    app_secret: SecretStr
    tr_id_profile: str
    label: str
```

**Settings/defaults pattern** (lines 36-69):
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

**Safety validator and active KIS pattern** (lines 70-86):
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

@property
def active_kis(self) -> KisCredentialGroup:
    """Return the whole selected KIS credential group."""

    if self.trading_mode is TradingMode.REAL:
        return self.kis_real
    return self.kis_mock
```

**Apply:** add Phase 3 settings here, not in adapters: `screener_max_candidates`, market inclusion, liquidity floors, KIS min interval/retry/token refresh margin, OHLCV adjusted policy, and Naver enabled/checkpoint flag. Preserve `active_kis` as the only selected credential source.

---

### `trading_bot/data_models.py` (model, request-response)

**Analog:** `trading_bot/domain.py` and `trading_bot/execution.py`

**Frozen domain dataclass pattern** (`trading_bot/domain.py` lines 5-7, 59-66):
```python
from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Sequence

@dataclass(frozen=True)
class DataContext:
    """Ticker-oriented context passed to an LLM provider."""

    ticker: Ticker
    current_price: Money
    technicals: Mapping[str, float] = field(default_factory=dict)
    news: Sequence[str] = field(default_factory=tuple)
```

**Machine-checkable audit/result pattern** (`trading_bot/execution.py` lines 41-75, 78-93):
```python
class ExecutionAction(str, Enum):
    """Final action produced by the execution core."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"

@dataclass(frozen=True)
class CycleAuditEvent:
    """Machine-checkable record of a single decision cycle (D-07 repudiation)."""

    ticker: str
    parsed_decision: Optional[str]
    parse_error: Optional[str]
    risk_override: bool
    override_reason: str
    final_action: str
    order_reason: str
    dry_run: bool = True
    broker_order_id: Optional[str] = None

@dataclass(frozen=True)
class ExecutionResult:
    """Immutable outcome of a decision cycle."""

    action: ExecutionAction
    order: Optional[Order]
    reason: str
    risk_override: bool = False
    override_reason: Optional[str] = None
    audit: Optional[CycleAuditEvent] = None
    broker_order_id: Optional[str] = None
```

**Apply:** define frozen dataclasses/enums for `SourceStatus`, `DataAction` (`BUILD_CONTEXT`, `SKIP_CANDIDATE`, `FORCE_HOLD`), `SourceHealth`, adapter results, and `DataSourceAuditEvent`. Keep raw vendor payloads out of `DataContext`.

---

### `trading_bot/data_source.py` (service/orchestrator, request-response)

**Analog:** `trading_bot/execution.py` and `trading_bot/ports.py`

**Protocol boundary to satisfy** (`trading_bot/ports.py` lines 32-38):
```python
@runtime_checkable
class DataSource(Protocol):
    """Market data context boundary."""

    def build_context(self, ticker: Ticker) -> DataContext:
        """Build ticker-oriented context for signal generation."""
        ...
```

**Orchestration ordering pattern** (`trading_bot/execution.py` lines 221-249, 268-323):
```python
def execute_signal_cycle(
    raw_signal: str,
    ticker: Ticker,
    current_price: Money,
    available_cash: float,
    broker: Broker,
    execution_config: ExecutionConfig,
    risk_config: RiskConfig,
    daily_loss_state: DailyLossState,
    dry_run: bool = True,
) -> ExecutionResult:
    position = broker.get_position(ticker)

    # 1. Parse fail-safe: malformed input becomes HOLD / no-order (D-01).
    try:
        parsed = parse_signal(raw_signal)
    except SignalParseError as exc:
        return _finalize_cycle(...)

    # 2. Risk first: a risk exit overrides any same-ticker LLM action (D-07).
    risk = evaluate_position_risk(position, current_price, risk_config)
    if risk.action is RiskAction.SELL:
        ...

    # 3. LLM action evaluation, gated by the daily-loss kill switch (D-08).
    action_result = evaluate_signal_action(...)
```

**Audit finalization pattern** (`trading_bot/execution.py` lines 173-218):
```python
def _finalize_cycle(
    *,
    broker: Broker,
    dry_run: bool,
    action: ExecutionAction,
    order: Optional[Order],
    reason: str,
    ticker: Ticker,
    parsed_decision: Optional[str],
    parse_error: Optional[str],
    risk_override: bool,
    override_reason: str,
    order_reason: str,
) -> ExecutionResult:
    broker_order_id: Optional[str] = None
    if not dry_run and order is not None:
        broker_order_id = broker.place_order(order)

    audit = CycleAuditEvent(...)
    return ExecutionResult(...)
```

**Apply:** build a thin synchronous orchestrator that queries pykrx/indicators/KIS/news in a fixed order, normalizes each unavailable/stale result, emits/prints audit warnings, and returns compact `DataContext` only when safe. Do not import this concrete orchestrator from `ports.py`.

---

### `trading_bot/indicators.py` (utility, transform)

**Analog:** `trading_bot/risk.py`

**Pure transform imports and dataclasses** (lines 11-17, 27-57):
```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from trading_bot.domain import Money, Position

@dataclass(frozen=True)
class RiskConfig:
    """Configurable stop-loss / take-profit percentages (D-09)."""

    stop_loss_pct: float
    take_profit_pct: float

@dataclass(frozen=True)
class RiskDecision:
    """Immutable risk outcome with a machine-checkable action and reason."""

    action: RiskAction
    reason: str
```

**Fail-safe numeric validation pattern** (lines 59-85):
```python
def evaluate_position_risk(
    position: Optional[Position],
    current_price: Money,
    config: RiskConfig,
) -> RiskDecision:
    if position is None or position.quantity <= 0:
        return RiskDecision(RiskAction.HOLD, "no held position")

    entry = position.average_price.amount
    price = current_price.amount
    if entry <= 0 or price <= 0:
        return RiskDecision(RiskAction.HOLD, "non-positive price input")

    change_pct = (price - entry) / entry
    if change_pct <= -abs(config.stop_loss_pct):
        return RiskDecision(RiskAction.SELL, "stop_loss")
    if change_pct >= abs(config.take_profit_pct):
        return RiskDecision(RiskAction.SELL, "take_profit")
    return RiskDecision(RiskAction.HOLD, "within risk bounds")
```

**Apply:** keep indicator calculations pure: explicit OHLCV input, explicit config/window values, flat `dict[str, float]` output, and no settings/network/logging. Validate missing/NaN/non-positive rows before returning values.

---

### `trading_bot/screener.py` (service/utility, batch + transform)

**Analog:** `trading_bot/risk.py` and `trading_bot/execution.py`

**Pure rule function pattern** (`trading_bot/risk.py` lines 88-97):
```python
def blocks_new_buy(daily_loss_state: DailyLossState, config: RiskConfig) -> bool:
    """Return True when the daily-loss kill switch blocks new BUY actions (D-08)."""

    del config  # kill-switch arming depends only on the daily-loss state.
    return daily_loss_state.realized_loss >= daily_loss_state.threshold
```

**Qualified action then no-order fallback pattern** (`trading_bot/execution.py` lines 289-323):
```python
action_result = evaluate_signal_action(
    parsed_decision, confidence, position, execution_config
)

if action_result.action is ExecutionAction.BUY and blocks_new_buy(
    daily_loss_state, risk_config
):
    return _finalize_cycle(...)

order = build_order_intent(...)
final_action = action_result.action
order_reason = action_result.reason
if order is None and final_action is not ExecutionAction.HOLD:
    final_action = ExecutionAction.HOLD
    order_reason = f"{action_result.reason}; no valid order quantity"
```

**Apply:** separate hard exclusions from ranking. First filter stale/bad/suspended/low-liquidity tickers into audit events, then rank survivors by volatility-breakout inputs. Pass an asserted trading date into every adapter call to avoid lookahead.

---

### `trading_bot/pykrx_adapter.py` (service/adapter, request-response + batch)

**Analog:** `trading_bot/mock_broker.py` and `trading_bot/signal_parser.py`

**Synchronous adapter class pattern** (`trading_bot/mock_broker.py` lines 25-38, 50-61):
```python
class MockBroker:
    """Deterministic in-memory paper broker satisfying the ``Broker`` Protocol."""

    def __init__(
        self,
        cash: Money,
        positions: Optional[Sequence[Position]] = None,
    ) -> None:
        self._cash = cash
        self._positions: Dict[str, Position] = {
            position.ticker.value: position for position in (positions or ())
        }
        self._order_history: List[Order] = []
        self._order_counter = 0

    def get_position(self, ticker: Ticker) -> Optional[Position]:
        """Return the in-memory position for ``ticker`` without side effects."""
        return self._positions.get(ticker.value)
```

**Boundary exception normalization pattern** (`trading_bot/signal_parser.py` lines 56-68):
```python
try:
    payload = json.loads(raw_input)
except (json.JSONDecodeError, TypeError) as exc:
    raise SignalParseError(f"raw signal is not valid JSON: {exc}") from exc

if not isinstance(payload, dict):
    raise SignalParseError(
        f"raw signal must be a JSON object, got {type(payload).__name__}"
    )

missing = [name for name in _REQUIRED_FIELDS if name not in payload]
if missing:
    raise SignalParseError(f"raw signal missing required field(s): {missing}")
```

**Apply:** this is the first real pykrx adapter, so no exact network analog exists. Keep pykrx imports isolated in this file, convert empty/stale/bad frames to typed source-health results, and do not let pykrx exceptions escape into `data_source.py`.

---

### `trading_bot/kis_auth.py` (service/adapter, request-response + cached token)

**Analog:** `trading_bot/config.py` and `trading_bot/mock_broker.py`

**Secret-safe credential access pattern** (`trading_bot/config.py` lines 80-86, 109-123):
```python
@property
def active_kis(self) -> KisCredentialGroup:
    """Return the whole selected KIS credential group."""

    if self.trading_mode is TradingMode.REAL:
        return self.kis_real
    return self.kis_mock

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

**Stateful boundary pattern** (`trading_bot/mock_broker.py` lines 33-38, 83-85):
```python
self._cash = cash
self._positions: Dict[str, Position] = {
    position.ticker.value: position for position in (positions or ())
}
self._order_history: List[Order] = []
self._order_counter = 0

self._order_counter += 1
self._order_history.append(order)
return f"MOCK-{self._order_counter}"
```

**Apply:** cache token/expiry in one shared manager instance. Use `settings.active_kis`, never separate active app key/secret fields. Redact token/appsecret from logs, audit only non-secret failure reasons, and keep retry bounded.

---

### `trading_bot/kis_quote.py` (service/adapter, request-response)

**Analog:** `trading_bot/mock_broker.py` and `trading_bot/config.py`

**Protocol-like adapter method pattern** (`trading_bot/mock_broker.py` lines 50-61):
```python
def get_position(self, ticker: Ticker) -> Optional[Position]:
    """Return the in-memory position for ``ticker`` without side effects."""
    return self._positions.get(ticker.value)

def place_order(self, order: Order) -> str:
    """Apply ``order`` to in-memory state and return a deterministic order ID.

    Raises:
        ValueError: If quantity is non-positive, currencies mismatch, a BUY
            exceeds available cash, or a SELL exceeds the held quantity. On any
            such rejection no state is mutated.
    """
```

**Input validation pattern before mutation/use** (`trading_bot/mock_broker.py` lines 63-81):
```python
if order.quantity <= 0:
    raise ValueError(
        f"order quantity must be positive, got {order.quantity}"
    )
if order.limit_price.currency != self._cash.currency:
    raise ValueError(
        "order currency "
        f"{order.limit_price.currency!r} does not match account currency "
        f"{self._cash.currency!r}"
    )

notional = order.quantity * order.limit_price.amount
```

**Apply:** isolate `httpx` and KIS endpoint details here. Validate KIS response fields before constructing `Money`; non-numeric/zero/missing price becomes unavailable source health, not `Money(0)`.

---

### `trading_bot/naver_news.py` (service/adapter, request-response + transform)

**Analog:** `trading_bot/signal_parser.py`

**Untrusted input validation pattern** (lines 47-83):
```python
def parse_signal(raw_input: str) -> ParsedSignal:
    """Parse ``raw_input`` into a :class:`ParsedSignal` or fail closed."""

    try:
        payload = json.loads(raw_input)
    except (json.JSONDecodeError, TypeError) as exc:
        raise SignalParseError(f"raw signal is not valid JSON: {exc}") from exc

    if not isinstance(payload, dict):
        raise SignalParseError(
            f"raw signal must be a JSON object, got {type(payload).__name__}"
        )

    missing = [name for name in _REQUIRED_FIELDS if name not in payload]
    if missing:
        raise SignalParseError(f"raw signal missing required field(s): {missing}")

    decision = _parse_decision(payload["decision"])
    confidence = _parse_confidence(payload["confidence"])
    reason = _parse_reason(payload["reason"])
```

**Text field sanitizer/validator pattern** (lines 116-119):
```python
def _parse_reason(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SignalParseError("reason must be a non-empty string")
    return value
```

**Apply:** treat scraped HTML/news as untrusted text like raw LLM JSON. Strip markup/control or prompt-like instructions, cap string length/count, and fail soft to empty news when disabled, disallowed, throttled, or DOM parsing fails.

---

### Test Files (test role patterns)

**Analog:** current pytest suite.

**Frozen dataclass test pattern** (`tests/test_risk.py` lines 51-59):
```python
def test_risk_result_objects_are_frozen_dataclasses_and_string_enums() -> None:
    decision = RiskDecision(action=RiskAction.SELL, reason="stop_loss")

    assert dataclasses.is_dataclass(decision)
    assert isinstance(RiskAction.SELL, str)
    assert RiskAction.HOLD.value == "HOLD"
    assert RiskAction.SELL.value == "SELL"
    with pytest.raises(dataclasses.FrozenInstanceError):
        decision.reason = "mutated"  # type: ignore[misc]
```

**Parametrized fail-safe test pattern** (`tests/test_risk.py` lines 96-100):
```python
@pytest.mark.parametrize("entry, price", [(0.0, 70000.0), (-1.0, 70000.0), (70000.0, 0.0), (70000.0, -5.0)])
def test_non_positive_prices_hold_safely_rather_than_trade(entry: float, price: float) -> None:
    decision = evaluate_position_risk(_position(entry), Money(price, "KRW"), _config())

    assert decision.action is RiskAction.HOLD
```

**Structural protocol test pattern** (`tests/test_ports.py` lines 47-54, 83-94):
```python
class FakeDataSource:
    def build_context(self, ticker: Ticker) -> DataContext:
        return DataContext(
            ticker=ticker,
            current_price=Money(70000.0, "KRW"),
            technicals={"rsi": 50.0},
            news=[],
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
```

**Import-boundary test pattern** (`tests/test_ports.py` lines 9-23, 97-112):
```python
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

def test_ports_import_domain_types_without_concrete_adapters() -> None:
    before_import = set(sys.modules)
    __import__("trading_bot.ports")

    loaded_modules = set(sys.modules) - before_import
    for prefix in FORBIDDEN_MODULE_PREFIXES:
        assert prefix not in loaded_modules
```

**Secret-leak test pattern** (`tests/test_config.py` lines 15-22, 78-99):
```python
SECRET_VALUES = (
    "mock-app-key-secret",
    "mock-app-secret-secret",
    "real-app-key-secret",
    "real-app-secret-secret",
    "anthropic-api-key-secret",
    "openai-api-key-secret",
)

def assert_no_secret_leaked(*texts: str) -> None:
    combined = "\n".join(texts)
    for secret in SECRET_VALUES:
        assert secret not in combined

def test_settings_load_secrets_without_repr_banner_or_log_leaks(...):
    ...
    assert_no_secret_leaked(repr(settings), startup_banner(settings), caplog.text)
```

**Apply per test file:**
- `tests/test_pykrx_adapter.py`: copy import-boundary and parametrized fail-safe style; use fake pykrx callables/frames, no live network.
- `tests/test_indicators.py`: copy `tests/test_risk.py` pure function style; assert NaN/missing/non-positive data fails safe.
- `tests/test_screener.py`: copy risk/execution branch tests; assert hard exclusions happen before ranking.
- `tests/test_kis_auth.py`: copy config secret-leak tests and mock broker stateful tests; fake HTTP client responses.
- `tests/test_kis_quote.py`: copy validation/no-side-effect style; fake token manager and HTTP responses.
- `tests/test_naver_news.py`: copy signal parser untrusted input tests; malformed HTML/prompt-like strings sanitize or fail soft.
- `tests/test_data_source.py`: copy execution orchestrator tests; fake adapters for available/stale/unavailable branches and audit events.
- `tests/test_ports.py`: extend forbidden local fragments if needed, but keep ports adapter-free.

## Shared Patterns

### Core Modules Stay Adapter-Free
**Source:** `tests/test_execution.py` lines 710-733
**Apply to:** `trading_bot/domain.py`, `trading_bot/ports.py`, `trading_bot/risk.py`, `trading_bot/indicators.py`, `trading_bot/screener.py`, and any pure transform.
```python
def test_phase2_core_modules_import_no_forbidden_dependencies() -> None:
    """T-02-10: parser, risk, execution, mock broker stay adapter/external-free."""
    core_modules = (
        "trading_bot.signal_parser",
        "trading_bot.risk",
        "trading_bot.execution",
        "trading_bot.mock_broker",
    )

    before_import = set(sys.modules)
    for name in core_modules:
        importlib.import_module(name)
    loaded = set(sys.modules) - before_import

    for prefix in FORBIDDEN_MODULE_PREFIXES:
        assert prefix not in loaded, f"{prefix} leaked into Phase 2 core imports"
```

### Fail Closed on Bad Data
**Source:** `trading_bot/risk.py` lines 72-85 and `trading_bot/execution.py` lines 247-263
**Apply to:** data source orchestrator, adapters, indicators, screener.
```python
if entry <= 0 or price <= 0:
    return RiskDecision(RiskAction.HOLD, "non-positive price input")

try:
    parsed = parse_signal(raw_signal)
except SignalParseError as exc:
    return _finalize_cycle(
        broker=broker,
        dry_run=dry_run,
        action=ExecutionAction.HOLD,
        order=None,
        reason="invalid signal payload; parser failed",
        ticker=ticker,
        parsed_decision=None,
        parse_error=str(exc),
        risk_override=False,
        override_reason="",
        order_reason="invalid signal payload",
    )
```

### Compact LLM Boundary
**Source:** `trading_bot/domain.py` lines 59-66
**Apply to:** `data_source.py`, `data_models.py`, `naver_news.py`, `indicators.py`.
```python
@dataclass(frozen=True)
class DataContext:
    """Ticker-oriented context passed to an LLM provider."""

    ticker: Ticker
    current_price: Money
    technicals: Mapping[str, float] = field(default_factory=dict)
    news: Sequence[str] = field(default_factory=tuple)
```

### Secret Redaction
**Source:** `trading_bot/config.py` lines 109-123 and `tests/test_config.py` lines 78-99
**Apply to:** KIS auth, KIS quote, startup/config tests, audit output.
```python
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

### Synchronous Semantic Ports
**Source:** `trading_bot/ports.py` lines 10-38
**Apply to:** concrete data source must structurally satisfy `DataSource`; do not make port methods async.
```python
@runtime_checkable
class DataSource(Protocol):
    """Market data context boundary."""

    def build_context(self, ticker: Ticker) -> DataContext:
        """Build ticker-oriented context for signal generation."""
        ...
```

## No Exact Analog Found

These files have no exact implementation analog because Phase 3 introduces the first real external market-data adapters. Use the closest patterns above plus `03-RESEARCH.md` provider details.

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `trading_bot/pykrx_adapter.py` | service/adapter | request-response, batch | No existing pykrx/pandas adapter exists; isolate vendor imports and normalize failures. |
| `trading_bot/kis_auth.py` | service/adapter | request-response, cached token | No existing HTTP token manager exists; reuse config secret patterns and bounded stateful class style. |
| `trading_bot/kis_quote.py` | service/adapter | request-response | No existing KIS HTTP quote adapter exists; reuse validation/fail-safe result patterns. |
| `trading_bot/naver_news.py` | service/adapter | request-response, transform | No existing HTML scraper exists; reuse untrusted-input parser/sanitizer patterns. |

## Metadata

**Analog search scope:** `trading_bot/`, `tests/`, `pyproject.toml`, `.planning/phases/03-data-pipeline/03-CONTEXT.md`, `.planning/phases/03-data-pipeline/03-RESEARCH.md`
**Files scanned:** 16 source/test/config files plus 2 phase artifacts
**Pattern extraction date:** 2026-07-01
