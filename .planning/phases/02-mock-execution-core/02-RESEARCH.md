# Phase 02: mock-execution-core - Research

**Researched:** 2026-07-01
**Domain:** Python mock trade execution, fail-safe signal parsing, deterministic risk controls, dry-run safety
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
## Implementation Decisions

### Signal Parser Behavior
- **D-01:** Malformed or schema-invalid signal input should raise an internal domain parse error. The execution chain must catch that error and convert it to HOLD/no-trade. No malformed or partial object may be repaired into a trade.
- **D-02:** Parser validation is strict for required fields and values but tolerant of extra JSON fields. Invalid cases include malformed JSON, missing required fields, unknown decision, confidence outside `0.0..1.0`, and empty reason. Extra fields are ignored.
- **D-03:** The parser only validates confidence range. BUY/SELL execution thresholds belong in the execution rules, not in parsing.
- **D-04:** Successful parsing should return a parsed wrapper rather than a bare `LLMSignal`. The wrapper should preserve the canonical `LLMSignal`, raw input, and non-sensitive diagnostics such as ignored extra fields or warnings.

### Execution and Risk Rules
- **D-05:** BUY and SELL use separate configurable confidence thresholds. Defaults should be `0.8` for BUY and `0.8` for SELL unless planning finds a stronger local default.
- **D-06:** BUY sizing should spend a configurable percentage of available cash, capped by a configurable maximum position value per ticker.
- **D-07:** Risk always wins over LLM actions. Stop-loss, take-profit, or kill-switch decisions suppress conflicting LLM actions and must be logged as overrides.
- **D-08:** Once the daily-loss threshold is breached, the kill switch blocks new BUY orders for the rest of the day while still allowing SELLs and risk exits.
- **D-09:** Stop-loss and take-profit evaluate current price against the position average price using configurable percentage thresholds.

### the agent's Discretion
The user did not delegate broad decisions wholesale. The planner may choose exact class/function names, diagnostic object shape, and test fixture organization consistent with the decisions above.

### Deferred Ideas (OUT OF SCOPE)
## Deferred Ideas

None - discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| EXEC-01 | System parses the validated signal and issues a BUY only when `decision == "BUY"` AND `confidence >= 0.8` | Put parser confidence-range validation in `signal_parser.py`, and put executable confidence threshold checks in `execution.py`; defaults come from Phase 2 D-03/D-05. [VERIFIED: .planning/phases/02-mock-execution-core/02-CONTEXT.md] |
| EXEC-02 | BUY position sizing is a configurable % of available capital, bounded by a max-position cap | Add execution/risk settings for percent-of-cash sizing and max-position-value cap; compute integer quantity from current price before creating an `Order`. [VERIFIED: .planning/phases/02-mock-execution-core/02-CONTEXT.md] |
| EXEC-03 | System issues a SELL on `decision == "SELL"` with confidence threshold for tickers currently held | Execution must query current position and emit SELL orders only when a position exists, signal decision is SELL, and SELL confidence meets the configured threshold. [VERIFIED: .planning/REQUIREMENTS.md] [VERIFIED: trading_bot/ports.py] |
| EXEC-05 | Dry-run mode logs the would-be decision and order without placing it | Dry-run must short-circuit before `Broker.place_order`; logs/audit entries record the intended decision/order and no broker mutation occurs. [VERIFIED: .planning/REQUIREMENTS.md] [VERIFIED: trading_bot/config.py] |
| RISK-01 | A rules-based stop-loss / take-profit net evaluates held positions independent of the LLM and can SELL on its own | Implement a pure risk function that accepts `Position`, current price, and thresholds and returns a risk exit decision without reading `LLMSignal`. [VERIFIED: .planning/REQUIREMENTS.md] [VERIFIED: .planning/phases/02-mock-execution-core/02-CONTEXT.md] |
| RISK-02 | When risk net and LLM signal conflict on the same ticker, risk takes precedence | Orchestrate `parse -> risk -> execute -> log` so risk exit decisions suppress same-ticker LLM actions and record an override reason. [VERIFIED: .planning/phases/02-mock-execution-core/02-CONTEXT.md] |
| RISK-03 | A daily-loss kill switch halts all new trading for the rest of the day once threshold is breached | Model kill switch as deterministic state input for the cycle; once breached, block new BUYs while still allowing SELLs and risk exits. [VERIFIED: .planning/phases/02-mock-execution-core/02-CONTEXT.md] |
</phase_requirements>

## Summary

Phase 2 should extend the existing foundation with a small, dependency-light execution core: `signal_parser.py`, `risk.py`, `execution.py`, `mock_broker.py`, and focused tests. The existing domain layer already provides frozen dataclass/enums for `LLMSignal`, `Order`, `Position`, `Money`, and `Ticker`, and existing ports already define a synchronous `Broker` Protocol. [VERIFIED: trading_bot/domain.py] [VERIFIED: trading_bot/ports.py]

The safety-critical ordering is parser fail-closed first, risk net second, execution rules third, and broker/dry-run side effect last. Parser errors must be internal exceptions that the execution chain maps to HOLD/no-trade, never best-effort repairs. Risk has veto power over LLM actions on the same ticker, and dry-run must skip `Broker.place_order` entirely. [VERIFIED: .planning/phases/02-mock-execution-core/02-CONTEXT.md]

**Primary recommendation:** Use only existing Python stdlib, existing `pydantic-settings` config, and existing `pytest`; add no new external packages for Phase 2. [VERIFIED: pyproject.toml] [VERIFIED: local test run]

## Project Constraints (from AGENTS.md)

No root `AGENTS.md` or `.codex/AGENTS.md` was found by `rg --files -g 'AGENTS.md' -g '.codex/AGENTS.md'`; therefore there are no additional project instruction directives beyond `.planning/*` and the existing code/tests for this phase. [VERIFIED: codebase grep]

No project-specific `rules/*.md` files were found under `.codex/skills` or `.agents/skills`; the local skill files are GSD workflow skills, not Python package implementation conventions. [VERIFIED: codebase grep]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|--------------|----------------|-----------|
| Fail-safe signal parsing | Core domain/application package | Test suite | Raw strings enter as untrusted input and must become either a validated `LLMSignal` wrapper or HOLD/no-trade before execution logic can act. [VERIFIED: .planning/phases/02-mock-execution-core/02-CONTEXT.md] |
| Confidence-gated execution | Core application package | Config settings | BUY/SELL thresholds and sizing are deterministic execution rules, not parser or LLM responsibilities. [VERIFIED: .planning/phases/02-mock-execution-core/02-CONTEXT.md] |
| Stop-loss/take-profit risk net | Core application package | Mock broker state | Risk decisions are pure and LLM-independent; broker state supplies positions but does not own risk math. [VERIFIED: .planning/REQUIREMENTS.md] |
| Daily-loss kill switch | Core application package | Cycle state / future audit store | The kill switch gates new BUYs for the day while allowing SELL/risk exits; durable persistence can come later. [VERIFIED: .planning/phases/02-mock-execution-core/02-CONTEXT.md] |
| Mock paper account | Broker adapter tier | In-memory state | `MockBroker` should satisfy the existing `Broker` Protocol and mutate only in memory during non-dry-run tests. [VERIFIED: trading_bot/ports.py] |
| Dry-run behavior | Execution boundary | Logging/audit output | Dry-run belongs immediately before side effects so all upstream decisions are visible but no order call/state mutation occurs. [VERIFIED: .planning/REQUIREMENTS.md] |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `json` | Python 3.9.6 local | Parse raw signal JSON and raise `JSONDecodeError` on malformed JSON | Avoids a new parser dependency; official docs define `loads()` and decode failures. [CITED: https://docs.python.org/3/library/json.html] [VERIFIED: `python3 --version`] |
| Python stdlib `dataclasses`, `enum` | Python 3.9.6 local | Immutable execution/risk decision records and existing domain objects | Existing `trading_bot.domain` uses frozen dataclasses and enums; `dataclass(frozen=True)` prevents field assignment after construction. [VERIFIED: trading_bot/domain.py] [CITED: https://docs.python.org/3/library/dataclasses.html] |
| Python stdlib `typing.Protocol` | Python 3.9.6 local | Preserve structural, synchronous broker ports | Existing `Broker` is runtime-checkable and synchronous; Protocol supports structural subtyping. [VERIFIED: trading_bot/ports.py] [CITED: https://docs.python.org/3/library/typing.html] |
| Existing `pydantic-settings` | 2.11.0 installed | Add execution/risk configuration fields to `Settings` | Phase 1 already uses typed settings; add thresholds/caps there instead of a second config system. [VERIFIED: trading_bot/config.py] [VERIFIED: local import probe] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Existing `pytest` | 8.4.2 installed | Parser, risk, execution, mock broker, dry-run, and import-boundary tests | Use for all Phase 2 automated validation; `monkeypatch` and `caplog` are official pytest fixtures for scoped mutation and log assertions. [VERIFIED: local import probe] [CITED: https://docs.pytest.org/en/stable/how-to/monkeypatch.html] [CITED: https://docs.pytest.org/en/stable/how-to/logging.html] |
| Existing `pydantic` | 2.13.4 installed | Backing dependency for `Settings` additions | Do not introduce Pydantic domain models; use it only where Phase 1 already uses it for settings. [VERIFIED: pyproject.toml] [VERIFIED: trading_bot/config.py] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| stdlib `json` plus explicit validation | Pydantic model for `LLMSignal` parsing | Rejected for Phase 2 because the current domain contract is stdlib dataclasses/enums and parser behavior is small enough to validate explicitly. [VERIFIED: trading_bot/domain.py] [ASSUMED] |
| In-memory `MockBroker` | SQLite-backed state store | Rejected for this phase because Phase 2 requires hand-written signals and zero external calls; persistent audit/store appears in later operations work. [VERIFIED: .planning/ROADMAP.md] |
| Pure risk functions | Broker-owned risk checks | Rejected because risk must be LLM-independent, deterministic, and reusable by future real broker execution. [VERIFIED: .planning/REQUIREMENTS.md] |

**Installation:**
```bash
# No new packages for Phase 2.
# Use the existing workspace-local dependency setup:
PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q
```

**Version verification performed:**
```bash
python3 --version                         # Python 3.9.6
PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest --version  # pytest 8.4.2
PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pip index versions pytest
PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pip index versions pydantic
PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pip index versions pydantic-settings
```

## Package Legitimacy Audit

No new external packages should be installed for this phase. [VERIFIED: pyproject.toml] [VERIFIED: .planning/phases/02-mock-execution-core/02-CONTEXT.md]

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| none | PyPI | n/a | n/a | n/a | n/a | No install required. [VERIFIED: local research] |

**Packages removed due to [SLOP] verdict:** none. [VERIFIED: local research]
**Packages flagged as suspicious [SUS]:** none for Phase 2 because no packages are added. [VERIFIED: local research]

## Architecture Patterns

### System Architecture Diagram

```text
hand-written raw signal JSON
        |
        v
parse_signal(raw)
        |
        +-- malformed/schema-invalid --> SignalParseError
        |                                |
        |                                v
        |                         HOLD/no-trade execution result
        |
        v
ParsedSignal(signal, raw, diagnostics)
        |
        v
load cycle inputs: ticker, current price, available cash, existing position, daily P/L
        |
        v
risk.evaluate_position(position, price, risk_config, daily_state)
        |
        +-- stop-loss/take-profit/kill-switch exit --> risk SELL decision
        |                                             |
        |                                             v
        |                                  suppress same-ticker LLM action
        |
        v
execution.evaluate_signal(parsed_signal, position, cash, price, execution_config)
        |
        +-- no qualified action --> HOLD/no order
        |
        v
Order intent
        |
        v
dry_run?
        |
        +-- yes --> log intended order only, do not call Broker.place_order
        |
        +-- no  --> MockBroker.place_order(order) -> in-memory cash/position update
        |
        v
cycle log/audit event with parse diagnostics, risk override, decision, order outcome
```

### Recommended Project Structure

```text
trading_bot/
├── config.py           # extend Settings with execution/risk defaults
├── domain.py           # existing domain types; add small frozen result dataclasses only if shared
├── ports.py            # existing Broker Protocol remains synchronous
├── signal_parser.py    # raw JSON -> ParsedSignal or SignalParseError
├── risk.py             # pure stop-loss/take-profit/kill-switch decisions
├── execution.py        # parse/risk/execute/log orchestration and dry-run gate
└── mock_broker.py      # in-memory Broker implementation for paper account tests
tests/
├── test_signal_parser.py
├── test_risk.py
├── test_execution.py
└── test_mock_broker.py
```

### Pattern 1: Strict Parser With Tolerant Extras

**What:** Parse JSON into `LLMSignal` only when `decision`, `confidence`, and `reason` are present and valid; record ignored extra keys in diagnostics. [VERIFIED: .planning/phases/02-mock-execution-core/02-CONTEXT.md]

**When to use:** Every raw signal payload before any execution decision is evaluated. [VERIFIED: .planning/REQUIREMENTS.md]

**Example:**
```python
# Source: Python json docs and Phase 2 CONTEXT decisions
import json
from dataclasses import dataclass
from typing import Tuple

from trading_bot.domain import Decision, LLMSignal


class SignalParseError(ValueError):
    pass


@dataclass(frozen=True)
class ParsedSignal:
    signal: LLMSignal
    raw_input: str
    ignored_fields: Tuple[str, ...] = ()


def parse_signal(raw_input: str) -> ParsedSignal:
    try:
        payload = json.loads(raw_input)
    except json.JSONDecodeError as exc:
        raise SignalParseError("malformed JSON signal") from exc

    if not isinstance(payload, dict):
        raise SignalParseError("signal must be a JSON object")

    required = {"decision", "confidence", "reason"}
    missing = required - payload.keys()
    if missing:
        raise SignalParseError("missing required signal fields")

    try:
        decision = Decision(payload["decision"])
    except ValueError as exc:
        raise SignalParseError("unknown decision") from exc

    confidence = payload["confidence"]
    reason = payload["reason"]
    if not isinstance(confidence, (int, float)) or not 0.0 <= float(confidence) <= 1.0:
        raise SignalParseError("confidence must be between 0.0 and 1.0")
    if not isinstance(reason, str) or not reason.strip():
        raise SignalParseError("reason must be a non-empty string")

    ignored = tuple(sorted(set(payload) - required))
    return ParsedSignal(
        signal=LLMSignal(decision=decision, confidence=float(confidence), reason=reason),
        raw_input=raw_input,
        ignored_fields=ignored,
    )
```

### Pattern 2: Pure Risk Decision Before LLM Execution

**What:** Risk evaluation returns a value object such as `RiskDecision(action, reason)` and does not call brokers, logs, settings, or LLM providers. [VERIFIED: .planning/REQUIREMENTS.md]

**When to use:** At the start of each ticker cycle for any held position, before LLM action is executed. [VERIFIED: .planning/phases/02-mock-execution-core/02-CONTEXT.md]

**Example:**
```python
# Source: Phase 2 CONTEXT risk decisions
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from trading_bot.domain import Money, OrderSide, Position


class RiskAction(str, Enum):
    HOLD = "HOLD"
    SELL = "SELL"


@dataclass(frozen=True)
class RiskDecision:
    action: RiskAction
    reason: str


def evaluate_position_risk(
    position: Optional[Position],
    current_price: Money,
    stop_loss_pct: float,
    take_profit_pct: float,
) -> RiskDecision:
    if position is None or position.quantity <= 0:
        return RiskDecision(RiskAction.HOLD, "no held position")

    entry = position.average_price.amount
    change_pct = (current_price.amount - entry) / entry
    if change_pct <= -abs(stop_loss_pct):
        return RiskDecision(RiskAction.SELL, "stop_loss")
    if change_pct >= abs(take_profit_pct):
        return RiskDecision(RiskAction.SELL, "take_profit")
    return RiskDecision(RiskAction.HOLD, "within risk bounds")
```

### Pattern 3: Dry-Run Side-Effect Gate

**What:** Build the decision and order intent, then branch before broker placement; dry-run logs the would-be order and leaves broker state untouched. [VERIFIED: .planning/REQUIREMENTS.md]

**When to use:** Every order path, including LLM BUY/SELL and risk exits. [VERIFIED: .planning/phases/02-mock-execution-core/02-CONTEXT.md]

**Example:**
```python
# Source: Phase 2 EXEC-05 requirement and existing Broker Protocol
from typing import Optional

from trading_bot.domain import Order
from trading_bot.ports import Broker


def submit_order_or_dry_run(
    broker: Broker,
    order: Optional[Order],
    dry_run: bool,
) -> Optional[str]:
    if order is None:
        return None
    if dry_run:
        return "dry-run:order-not-placed"
    return broker.place_order(order)
```

### Anti-Patterns to Avoid

- **Repairing malformed signals into trades:** Do not coerce missing fields, unknown decisions, invalid confidence, or empty reasons into BUY/SELL; parser failure maps to HOLD/no-trade. [VERIFIED: .planning/phases/02-mock-execution-core/02-CONTEXT.md]
- **Putting BUY/SELL confidence thresholds in parsing:** Parser validates only `0.0..1.0`; execution owns configurable action thresholds. [VERIFIED: .planning/phases/02-mock-execution-core/02-CONTEXT.md]
- **Letting LLM actions override risk exits:** Stop-loss, take-profit, and kill-switch decisions suppress same-cycle LLM actions and must be logged as overrides. [VERIFIED: .planning/phases/02-mock-execution-core/02-CONTEXT.md]
- **Calling `Broker.place_order` in dry-run:** Dry-run must log intended decisions/orders and perform zero order calls and zero external state mutation. [VERIFIED: .planning/REQUIREMENTS.md]
- **Importing real adapters into core modules:** Phase 2 must stay free of KIS, pykrx, OpenAI, Anthropic, `requests`, and concrete external calls. [VERIFIED: .planning/ROADMAP.md] [VERIFIED: tests/test_domain.py] [VERIFIED: tests/test_ports.py]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| JSON tokenization/parsing | String splitting or regex parser | Python stdlib `json.loads` | Official parser raises `JSONDecodeError` for malformed JSON and handles JSON syntax edge cases. [CITED: https://docs.python.org/3/library/json.html] |
| Immutable result objects | Mutable dicts passed between parser/risk/execution | Frozen `dataclass` objects | Existing domain uses frozen dataclasses, and immutable results make test assertions and side-effect boundaries explicit. [VERIFIED: trading_bot/domain.py] [CITED: https://docs.python.org/3/library/dataclasses.html] |
| Mock broker interface | Vendor-shaped KIS mock methods | Existing `Broker` Protocol | The port already defines semantic `get_position` and `place_order` operations for adapter-independent execution. [VERIFIED: trading_bot/ports.py] |
| Test log/environment helpers | Custom log capture or env cleanup | pytest `caplog` and `monkeypatch` | Official pytest fixtures provide scoped log capture and mutation cleanup. [CITED: https://docs.pytest.org/en/stable/how-to/logging.html] [CITED: https://docs.pytest.org/en/stable/how-to/monkeypatch.html] |

**Key insight:** The complex part is not order math; it is preserving safety boundaries so no invalid input, LLM preference, or dry-run path can cross into a broker mutation. [VERIFIED: .planning/REQUIREMENTS.md]

## Common Pitfalls

### Pitfall 1: Parser Becomes a Trade Repair Layer
**What goes wrong:** A partial JSON object is accepted and defaults into a BUY/SELL path. [VERIFIED: .planning/phases/02-mock-execution-core/02-CONTEXT.md]
**Why it happens:** Parser code mixes structural validation, defaulting, and execution policy. [ASSUMED]
**How to avoid:** Raise `SignalParseError` for malformed/schema-invalid input and catch it only at the execution-chain boundary as HOLD/no-trade. [VERIFIED: .planning/phases/02-mock-execution-core/02-CONTEXT.md]
**Warning signs:** Tests assert repaired values instead of no-trade outcomes for bad input. [ASSUMED]

### Pitfall 2: Risk Runs After Broker Placement
**What goes wrong:** A BUY/SELL order is placed before stop-loss, take-profit, or kill-switch logic has vetoed it. [VERIFIED: .planning/REQUIREMENTS.md]
**Why it happens:** Executor is written as signal-first instead of risk-first. [ASSUMED]
**How to avoid:** Evaluate risk before signal execution and represent risk overrides explicitly in the cycle result. [VERIFIED: .planning/phases/02-mock-execution-core/02-CONTEXT.md]
**Warning signs:** `Broker.place_order` appears before risk evaluation in the orchestration path. [ASSUMED]

### Pitfall 3: Dry-Run Mutates Mock State
**What goes wrong:** Tests pass because no real broker is called, but mock cash/positions still change in dry-run. [VERIFIED: .planning/REQUIREMENTS.md]
**Why it happens:** Dry-run is implemented inside the mock broker instead of before `place_order`. [ASSUMED]
**How to avoid:** Put dry-run branching in execution code before any broker method call. [VERIFIED: .planning/REQUIREMENTS.md]
**Warning signs:** Dry-run tests inspect changed `MockBroker.orders`, cash, or positions. [ASSUMED]

### Pitfall 4: Daily-Loss Kill Switch Blocks Risk Exits
**What goes wrong:** Once breached, the system refuses SELLs that would reduce exposure. [VERIFIED: .planning/phases/02-mock-execution-core/02-CONTEXT.md]
**Why it happens:** Kill switch is modeled as "halt all orders" rather than "halt new BUYs." [VERIFIED: .planning/phases/02-mock-execution-core/02-CONTEXT.md]
**How to avoid:** Model kill switch as a BUY gate only; allow SELL signals and risk exits. [VERIFIED: .planning/phases/02-mock-execution-core/02-CONTEXT.md]
**Warning signs:** Tests expect all actions to be blocked after daily-loss breach. [ASSUMED]

### Pitfall 5: Import Boundary Regressions
**What goes wrong:** Core modules import requests, KIS adapters, LLM SDKs, or data adapters during tests. [VERIFIED: tests/test_domain.py] [VERIFIED: tests/test_ports.py]
**Why it happens:** Mock execution code is placed in foundational domain/ports modules or reaches into future adapters. [ASSUMED]
**How to avoid:** Keep domain/ports import-clean tests and add equivalent import-boundary assertions for parser/risk/execution. [VERIFIED: tests/test_domain.py] [VERIFIED: tests/test_ports.py]
**Warning signs:** `sys.modules` shows `requests`, `openai`, `anthropic`, `pykrx`, or local adapter modules after importing Phase 2 core. [VERIFIED: tests/test_domain.py]

## Code Examples

Verified patterns from official sources and local code:

### Convert Parser Failure To HOLD At Boundary
```python
# Source: Phase 2 CONTEXT D-01 and Python json docs
from trading_bot.domain import Decision, LLMSignal
from trading_bot.signal_parser import SignalParseError, parse_signal


def parse_or_hold(raw_signal: str) -> LLMSignal:
    try:
        return parse_signal(raw_signal).signal
    except SignalParseError:
        return LLMSignal(
            decision=Decision.HOLD,
            confidence=0.0,
            reason="invalid signal payload",
        )
```

### Configurable BUY Sizing With Max Cap
```python
# Source: Phase 2 CONTEXT D-06
def calculate_buy_quantity(
    available_cash: float,
    current_price: float,
    capital_fraction: float,
    max_position_value: float,
) -> int:
    budget = min(available_cash * capital_fraction, max_position_value)
    if current_price <= 0:
        return 0
    return int(budget // current_price)
```

### Mock Broker Satisfying Existing Port
```python
# Source: trading_bot.ports Broker Protocol
from typing import Dict, Optional

from trading_bot.domain import Money, Order, OrderSide, Position, Ticker


class MockBroker:
    def __init__(self, cash: Money, positions: Optional[Dict[Ticker, Position]] = None) -> None:
        self.cash = cash
        self.positions = dict(positions or {})
        self.orders = []

    def get_position(self, ticker: Ticker) -> Optional[Position]:
        return self.positions.get(ticker)

    def place_order(self, order: Order) -> str:
        self.orders.append(order)
        return f"mock-{len(self.orders)}"
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| LLM output trusted as execution input | Strict parser plus deterministic execution rules | Locked in Phase 2 context on 2026-07-01 | Malformed output can only become HOLD/no-trade. [VERIFIED: .planning/phases/02-mock-execution-core/02-CONTEXT.md] |
| LLM owns sizing or stops | Configurable deterministic sizing, stop-loss, take-profit, and kill switch | Locked in project requirements on 2026-06-30 | Trade math is outside LLM control. [VERIFIED: .planning/REQUIREMENTS.md] |
| Real broker first | Mock broker/dry-run first | Roadmap Phase 2 before Phase 5 | Execution core is testable with zero external calls and zero financial risk before real KIS order placement exists. [VERIFIED: .planning/ROADMAP.md] |

**Deprecated/outdated:**
- Repairing invalid LLM output into a partial trade object: replaced by parser exception plus HOLD/no-trade boundary mapping. [VERIFIED: .planning/phases/02-mock-execution-core/02-CONTEXT.md]
- Blind order placement during dry-run: replaced by pre-broker dry-run short-circuit. [VERIFIED: .planning/REQUIREMENTS.md]
- Adapter-shaped mock broker APIs: replaced by the existing semantic `Broker` Protocol. [VERIFIED: trading_bot/ports.py]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Explicit validation with stdlib `json` is preferable to adding a Pydantic domain parser for Phase 2. | Standard Stack | Planner might choose a validation style that diverges from local stdlib domain patterns. |
| A2 | Parser/defaulting bugs usually happen when validation and execution policy are mixed. | Common Pitfalls | Tests might miss a repair-into-trade path if planner does not isolate parser behavior. |
| A3 | Risk-after-execution bugs usually happen when the orchestrator is signal-first. | Common Pitfalls | Planner might order tasks around LLM execution before risk override tests. |
| A4 | Dry-run mutation bugs usually happen when dry-run is implemented inside the broker. | Common Pitfalls | Planner might allow mock state mutation in dry-run. |
| A5 | Import-boundary regressions usually happen when core code reaches into future adapter modules. | Common Pitfalls | Planner might place Phase 2 code in modules that import future dependencies. |

## Open Questions

1. **Should `MockBroker` track cash/position mutation beyond recording placed orders?**
   - What we know: Phase 2 needs a MockBroker paper account and end-to-end parse -> risk -> execute -> log chain. [VERIFIED: .planning/ROADMAP.md]
   - What's unclear: The exact depth of paper-account accounting is not locked. [VERIFIED: .planning/phases/02-mock-execution-core/02-CONTEXT.md]
   - Recommendation: Implement minimal deterministic in-memory accounting for BUY/SELL quantities/cash plus order recording, and keep complex fill/idempotency modeling deferred to Phase 5. [ASSUMED]

2. **Where should daily-loss state live in Phase 2?**
   - What we know: The kill switch must block new BUYs for the rest of the day after threshold breach. [VERIFIED: .planning/phases/02-mock-execution-core/02-CONTEXT.md]
   - What's unclear: No durable audit/store is in Phase 2 scope. [VERIFIED: .planning/ROADMAP.md]
   - Recommendation: Represent daily-loss state as explicit cycle input to pure execution/risk functions and mock broker fixtures; defer durable persistence. [ASSUMED]

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python | Core implementation and tests | yes | 3.9.6 | none. [VERIFIED: `python3 --version`] |
| pytest | Validation architecture | yes via `PYTHONUSERBASE="$PWD/.python-userbase"` | 8.4.2 | Use the workspace-local user base documented by Phase 1; system `python3 -m pytest` alone did not report pytest. [VERIFIED: local command] |
| pydantic-settings | Existing `Settings` extension | yes via workspace user base | 2.11.0 | No fallback needed because it is already in project dependencies. [VERIFIED: local import probe] |
| pydantic | Existing `Settings` backing library | yes via workspace user base | 2.13.4 | No fallback needed because it is already in project dependencies. [VERIFIED: local import probe] |
| Network / broker / LLM SDKs | Phase 2 runtime | not required | n/a | Phase 2 must make zero external calls. [VERIFIED: .planning/ROADMAP.md] |

**Missing dependencies with no fallback:**
- None for Phase 2. [VERIFIED: local environment audit]

**Missing dependencies with fallback:**
- System-level pytest import is not reliable without `PYTHONUSERBASE`; use `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q`. [VERIFIED: local command]

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.4.2. [VERIFIED: local command] |
| Config file | `pyproject.toml` with `testpaths = ["tests"]`, `pythonpath = ["."]`, and `addopts = "-ra"`. [VERIFIED: pyproject.toml] |
| Quick run command | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest tests/test_signal_parser.py tests/test_risk.py tests/test_execution.py tests/test_mock_broker.py -q` [VERIFIED: local test infrastructure] |
| Full suite command | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` [VERIFIED: local command] |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| EXEC-01 | BUY only when parsed decision is BUY and confidence meets BUY threshold | unit | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest tests/test_execution.py::test_buy_requires_buy_decision_and_threshold -q` | no, Wave 0. [VERIFIED: codebase grep] |
| EXEC-02 | BUY quantity uses percent of cash bounded by max-position cap | unit | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest tests/test_execution.py::test_buy_sizing_uses_cash_percent_and_max_cap -q` | no, Wave 0. [VERIFIED: codebase grep] |
| EXEC-03 | SELL only for held positions and only when SELL confidence meets threshold | unit | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest tests/test_execution.py::test_sell_requires_position_and_threshold -q` | no, Wave 0. [VERIFIED: codebase grep] |
| EXEC-05 | Dry-run logs intended decision/order and never calls `place_order` | unit | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest tests/test_execution.py::test_dry_run_skips_broker_place_order_and_logs_intent -q` | no, Wave 0. [VERIFIED: codebase grep] |
| RISK-01 | Stop-loss/take-profit can independently emit SELL for held positions | unit | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest tests/test_risk.py::test_stop_loss_and_take_profit_emit_sell_without_llm -q` | no, Wave 0. [VERIFIED: codebase grep] |
| RISK-02 | Risk decision suppresses conflicting same-ticker LLM action and logs override | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest tests/test_execution.py::test_risk_override_suppresses_llm_action -q` | no, Wave 0. [VERIFIED: codebase grep] |
| RISK-03 | Daily-loss breach blocks new BUYs but allows SELL/risk exits | unit | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest tests/test_risk.py::test_daily_loss_blocks_buys_but_allows_exits -q` | no, Wave 0. [VERIFIED: codebase grep] |

### Sampling Rate

- **Per task commit:** `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest tests/test_signal_parser.py tests/test_risk.py tests/test_execution.py tests/test_mock_broker.py -q` [VERIFIED: local test infrastructure]
- **Per wave merge:** `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` [VERIFIED: local test run]
- **Phase gate:** Full suite green before `$gsd-verify-work`. [VERIFIED: .planning/config.json]

### Wave 0 Gaps

- [ ] `tests/test_signal_parser.py` - covers parser validity, extra-field diagnostics, and malformed/schema-invalid HOLD boundary for EXEC-01 and parser decisions. [VERIFIED: codebase grep]
- [ ] `tests/test_risk.py` - covers stop-loss, take-profit, risk precedence inputs, and daily-loss BUY gate for RISK-01/RISK-03. [VERIFIED: codebase grep]
- [ ] `tests/test_execution.py` - covers confidence thresholds, sizing cap, dry-run, risk override logging, and end-to-end chain for EXEC-01/02/03/05/RISK-02. [VERIFIED: codebase grep]
- [ ] `tests/test_mock_broker.py` - covers in-memory broker state, `Broker` Protocol conformance, and no external calls for mock execution. [VERIFIED: codebase grep]
- [ ] Phase 2 import-boundary assertions - ensure parser/risk/execution/mock broker do not import KIS, LLM, pykrx, requests/httpx, or future concrete adapters. [VERIFIED: tests/test_domain.py] [VERIFIED: tests/test_ports.py]

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | no | No auth is implemented in Phase 2; real KIS auth remains deferred. [VERIFIED: .planning/ROADMAP.md] |
| V3 Session Management | no | No sessions are implemented in Phase 2. [VERIFIED: .planning/ROADMAP.md] |
| V4 Access Control | no | Local mock core has no user access-control surface. [VERIFIED: .planning/ROADMAP.md] |
| V5 Input Validation | yes | Strict JSON parser plus explicit required-field/value checks; invalid input maps to HOLD/no-trade. [VERIFIED: .planning/phases/02-mock-execution-core/02-CONTEXT.md] |
| V6 Cryptography | no | No cryptography is implemented in Phase 2. [VERIFIED: .planning/ROADMAP.md] |

### Known Threat Patterns for Python Mock Execution Core

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malformed or adversarial LLM signal causes unintended trade | Tampering | Strict parser, `SignalParseError`, and HOLD/no-trade boundary mapping. [VERIFIED: .planning/phases/02-mock-execution-core/02-CONTEXT.md] |
| LLM signal bypasses deterministic risk controls | Elevation of privilege | Evaluate risk first and let risk override same-ticker LLM action. [VERIFIED: .planning/phases/02-mock-execution-core/02-CONTEXT.md] |
| Dry-run places or records real/mutating orders | Tampering | Branch before `Broker.place_order`; assert zero calls and zero state mutation in tests. [VERIFIED: .planning/REQUIREMENTS.md] |
| Audit/log omits risk override reason | Repudiation | Include parse diagnostics, risk override reason, decision, and order outcome in cycle result/log record. [VERIFIED: .planning/phases/02-mock-execution-core/02-CONTEXT.md] |
| Core imports external adapters with side effects | Information disclosure / Tampering | Preserve import-boundary tests that fail on LLM/KIS/data adapter imports. [VERIFIED: tests/test_domain.py] [VERIFIED: tests/test_ports.py] |

## Sources

### Primary (HIGH confidence)
- `.planning/phases/02-mock-execution-core/02-CONTEXT.md` - Locked Phase 2 parser, execution, risk, dry-run, and scope decisions. [VERIFIED: local file]
- `.planning/REQUIREMENTS.md` - EXEC-01/02/03/05 and RISK-01/02/03 requirement definitions. [VERIFIED: local file]
- `trading_bot/domain.py` - Existing domain objects and frozen dataclass/enums. [VERIFIED: local file]
- `trading_bot/ports.py` - Existing synchronous `Broker`, `LLMProvider`, and `DataSource` Protocols. [VERIFIED: local file]
- `trading_bot/config.py` - Existing `Settings.dry_run` and typed config pattern. [VERIFIED: local file]
- `tests/test_domain.py`, `tests/test_ports.py`, `tests/test_config.py` - Existing import-boundary and safety test conventions. [VERIFIED: local file]

### Secondary (MEDIUM confidence)
- Python `json` documentation - `json.loads` and `JSONDecodeError` behavior. [CITED: https://docs.python.org/3/library/json.html]
- Python `dataclasses` documentation - `dataclass(frozen=True)` behavior. [CITED: https://docs.python.org/3/library/dataclasses.html]
- Python `typing` documentation - Protocol and runtime-checkable structural typing. [CITED: https://docs.python.org/3/library/typing.html]
- pytest monkeypatch documentation - scoped test mutation fixture. [CITED: https://docs.pytest.org/en/stable/how-to/monkeypatch.html]
- pytest logging documentation - `caplog` log capture. [CITED: https://docs.pytest.org/en/stable/how-to/logging.html]

### Tertiary (LOW confidence)
- Assumptions A1-A5 in the Assumptions Log are engineering judgments based on the local architecture and should be reviewed during planning. [ASSUMED]

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - No new packages are recommended; existing versions and local test execution were verified. [VERIFIED: pyproject.toml] [VERIFIED: local command]
- Architecture: HIGH - Phase ordering and responsibilities are locked by Phase 2 context, requirements, and existing code boundaries. [VERIFIED: .planning/phases/02-mock-execution-core/02-CONTEXT.md] [VERIFIED: trading_bot/domain.py] [VERIFIED: trading_bot/ports.py]
- Pitfalls: MEDIUM - Safety pitfalls are grounded in locked requirements, while root-cause explanations are marked as assumptions. [VERIFIED: .planning/REQUIREMENTS.md] [ASSUMED]

**Research date:** 2026-07-01
**Valid until:** 2026-07-31 for local architecture decisions; re-check package/test versions if dependencies change. [ASSUMED]
