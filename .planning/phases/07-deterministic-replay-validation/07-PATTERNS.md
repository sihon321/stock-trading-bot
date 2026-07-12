# Phase 7: Deterministic Replay Validation - Pattern Map

**Mapped:** 2026-07-12
**Files analyzed:** 4 new/modified file groups
**Analogs found:** 4 / 4

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `trading_bot/replay.py` | service, model, utility | batch, transform, file-I/O | `trading_bot/screener.py`, `trading_bot/execution.py`, `trading_bot/mock_broker.py`, `trading_bot/audit_models.py` | composite role-match |
| `trading_bot/cli.py` | controller | request-response, file-I/O | existing `screen_command` / `run_command` in the same file | exact |
| `tests/test_replay.py` | test | batch, transform, file-I/O | `tests/test_screener.py`, `tests/test_execution.py` | exact/role-match |
| `tests/fixtures/replay/**/*.json` | test fixture, config | file-I/O, batch | plain mapping builders in `tests/test_screener.py` and raw JSON signals in `tests/test_execution.py` | role-match |

## Pattern Assignments

### `trading_bot/replay.py` (service/model/utility, batch + transform + file-I/O)

**Primary analogs:** `trading_bot/screener.py`, `trading_bot/execution.py`, `trading_bot/mock_broker.py`, and `trading_bot/audit_models.py`.

The file is a new orchestration boundary, so no single exact analog exists. Compose the following established patterns rather than creating a second policy engine.

**Imports and immutable model pattern** (`trading_bot/screener.py:22-32`, `trading_bot/screener.py:48-90`):

```python
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping, Optional, Sequence, Tuple

from trading_bot.data_models import (
    DataSourceAuditEvent,
    SourceHealth,
    SourceStatus,
)

@dataclass(frozen=True)
class ScreenerCandidate:
    ticker: str
    market: str
    score: float
    trading_value: float
    technicals: Mapping[str, float] = field(default_factory=dict)
```

Apply this to versioned scenario, step, fill, state snapshot, manifest, funnel, verification, and replay-result models. Keep decision-critical objects frozen and accept explicit values; do not instantiate `Settings` or read the wall clock inside the engine.

**Pure transform and deterministic ordering pattern** (`trading_bot/screener.py:110-169`):

```python
def screen_candidates(
    trading_date: str,
    rows: Iterable[Mapping[str, Any]],
    config: ScreenerConfig,
) -> ScreenerResult:
    survivors: list[ScreenerCandidate] = []
    audits: list[DataSourceAuditEvent] = []
    # ... hard exclusions before scoring ...
    survivors.sort(key=lambda c: (-c.score, c.ticker))
    capped = tuple(survivors[: max(config.max_candidates, 0)])
    return ScreenerResult(
        trading_date=trading_date,
        candidates=capped,
        audit_events=tuple(audits),
    )
```

Replay must call this production function with cutoff-guarded fixture rows and consume its existing `(-score, ticker)` order. Full-day steps follow that order; focused scenarios start with fresh explicit state.

**Production decision pipeline and fail-closed parser pattern** (`trading_bot/execution.py:235-278`, `trading_bot/execution.py:283-339`):

```python
position = broker.get_position(ticker)
try:
    parsed = parse_signal(raw_signal)
except SignalParseError as exc:
    return _finalize_cycle(
        broker=broker,
        dry_run=dry_run,
        action=ExecutionAction.HOLD,
        order=None,
        reason="invalid signal payload; parser failed",
        # ...
    )

risk = evaluate_position_risk(position, current_price, risk_config)
if risk.action is RiskAction.SELL:
    # risk exit overrides the signal
    ...

if action_result.action is ExecutionAction.BUY and blocks_new_buy(
    daily_loss_state, risk_config
):
    # BUY is blocked, SELL/risk exits remain available
    ...
```

Call `execute_signal_cycle(..., dry_run=True)` for every raw fixture signal. Observe its parse/risk/confidence/sizing/order-intent facts. Never duplicate confidence, risk, or sizing rules in replay code.

**Explicit complete-fill accounting pattern** (`trading_bot/mock_broker.py:67-71`, `trading_bot/mock_broker.py:119-141`, `trading_bot/mock_broker.py:143-170`):

```python
def get_position(self, ticker: Ticker) -> Optional[Position]:
    return self._positions.get(ticker.value)

notional = order.quantity * order.limit_price.amount
if order.side is OrderSide.BUY:
    self._apply_buy(order, notional)
elif order.side is OrderSide.SELL:
    self._apply_sell(order, notional)

self._order_counter += 1
self._order_history.append(order)
return f"MOCK-{self._order_counter}"
```

Use a fresh `MockBroker` per focused scenario and a scenario-scoped instance per full-day replay. After the dry-run decision, invoke `place_order` only for fixture fill `COMPLETE`; `NONE` must skip it and preserve cash/positions. Inject a clock if construction requires it so no wall-clock fact enters identity.

**Stable bounded outcome vocabulary pattern** (`trading_bot/audit_models.py:23-55`, `trading_bot/audit_models.py:76-105`):

```python
class ReasonCode(StrEnum):
    COMPLETED = "COMPLETED"
    HOLD_SIGNAL = "HOLD_SIGNAL"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    STALE_OHLCV = "STALE_OHLCV"
    MALFORMED_SIGNAL = "MALFORMED_SIGNAL"

@dataclass(frozen=True)
class TickerOutcome:
    run_id: str
    ticker: str
    outcome_code: TickerOutcomeCode
    reason_code: ReasonCode
    detail: Mapping[str, Any] | None = None
    failed_stage: FailedStage | None = None
```

Replay needs its own normalized per-stage facts but should reuse compatible `ReasonCode` / `FailedStage` values and `sanitize_detail` semantics where possible. Add replay-only bounded enums/models in `replay.py`; do not stretch free-text `CycleAuditEvent` into the result schema.

**Validation/error pattern:** validate fixture schema version, bounded fill values, six-digit tickers, finite numbers, required mappings, and evaluation cutoffs before any production call. Raise replay-specific `ValueError` subclasses with stable, non-secret messages. Future-data requests must raise a dedicated `FutureDataAccessError`, not silently return an empty sequence.

**Canonical evidence pattern (new primitive grounded in research):** serialize the deterministic identity document with `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)` and SHA-256. Hash manifest inputs plus ordered normalized outcomes. Invocation timestamp, duration, and output path belong only in a wrapper metadata document.

---

### `trading_bot/cli.py` (controller, request-response + file-I/O)

**Analog:** existing Typer command wrappers in the same file.

**Thin command registration pattern** (`trading_bot/cli.py:521-545`):

```python
@app.command("run")
def run_command(
    ticker: Optional[str] = typer.Option(None, "--ticker", help="Run one 6-digit KRX ticker."),
    execute: bool = typer.Option(False, "--execute", help="Place orders; omitted means dry-run."),
) -> None:
    try:
        result = run_cycle(ticker=ticker, execute=execute, live_confirm=False)
    except SystemExit as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from None
    typer.echo(f"Run {result['run_id']} complete: {len(result['outcomes'])} tickers")
```

Add `@app.command("replay")` as a thin adapter taking fixture bundle path and output path/options. It should call the offline replay API directly, never `build_runtime`, `_today_kst`, SQLite, provider, KIS, Naver, or pykrx composition.

**Option validation and output pattern** (`trading_bot/cli.py:80-87`, `trading_bot/cli.py:548-560`, `trading_bot/cli.py:625-628`):

```python
def _validate_ticker(ticker: str) -> str:
    if len(ticker) != 6 or not ticker.isdigit():
        raise typer.BadParameter("ticker must be a 6-digit KRX code")
    return ticker

resolved_trading_date = trading_date or _today_kst()
# ...
for symbol in candidates:
    typer.echo(symbol)
```

For replay, reject invalid paths/options with `typer.BadParameter`, print the stable result ID, scenario-level action/blocked counts, funnel denominators, verification status, and non-profitability disclaimer. Emit ticker detail only for failed checks or expectation differences. Persist normalized JSON in the replay API/utility layer, not by embedding orchestration in the command.

---

### `tests/test_replay.py` (test, batch + transform + file-I/O)

**Analogs:** `tests/test_screener.py` and `tests/test_execution.py`.

**Small explicit fixture builders** (`tests/test_screener.py:62-114`):

```python
def _config(**overrides: object) -> ScreenerConfig:
    defaults = dict(
        max_candidates=20,
        markets=("KOSPI", "KOSDAQ"),
        min_trading_value=1_000_000_000.0,
        min_volume_ratio=1.0,
        excluded_states=("HALTED", "DELISTING", "ADMIN"),
    )
    defaults.update(overrides)
    return ScreenerConfig(**defaults)

def _row(ticker: str, *, market: str = "KOSPI", ...) -> dict:
    return dict(ticker=ticker, market=market, ...)
```

Use focused builders for unit-level schema, cutoff, canonicalization, funnel, and state tests. Use checked-in JSON bundles only for requirement catalogs and full-day integration cases.

**Raw signal boundary and threshold assertions** (`tests/test_execution.py:59-105`):

```python
def _signal(decision: str, confidence: float, reason: str = "test reason") -> str:
    return json.dumps({"decision": decision, "confidence": confidence, "reason": reason})

at_threshold = evaluate_signal_action(
    parsed_decision="BUY", confidence=0.8, position=None, config=config
)
below = evaluate_signal_action(
    parsed_decision="BUY", confidence=0.79, position=None, config=config
)
assert at_threshold.action is ExecutionAction.BUY
assert below.action is ExecutionAction.HOLD
```

Parameterize the catalog across threshold-at/below, HOLD, SELL, malformed JSON, stale OHLCV, stop-loss/take-profit override, daily-loss block, zero sizing, and look-ahead rejection. Assert stage booleans and terminal reason codes, not only final action.

**Fail-loud side-effect guard** (`tests/test_execution.py:41-56`, `tests/test_execution.py:184-201`):

```python
class RecordingBroker:
    def place_order(self, order: Order) -> str:
        self.placed.append(order)
        raise AssertionError("place_order must not be called")

result = execute_signal_cycle(raw_signal="{not valid json", ...)
assert result.action is ExecutionAction.HOLD
assert result.order is None
assert broker.placed == []
```

Monkeypatch every live builder/import boundary to raise in integration and CLI tests. Repeat identical replay runs and assert identical deterministic document bytes and result ID, while observational metadata may differ. Reorder independent scenario files and assert stable sorting; reorder a full-day fixture contrary to screen rank and assert production rank wins.

---

### `tests/fixtures/replay/**/*.json` (fixture/config, file-I/O + batch)

**Analog:** mapping shapes in `tests/test_screener.py:84-114` and raw JSON generation in `tests/test_execution.py:81-82`.

Use a versioned JSON bundle with explicit scenario metadata, fixed evaluation/trading time, policy snapshot, initial cash/positions/daily loss, OHLCV/derived screener rows through the cutoff, per-ticker raw signal strings, fill (`COMPLETE` or `NONE`), and expected normalized outcomes. Preserve raw malformed signals as strings so they traverse the production parser.

Keep fixture-controlled output paths out of the schema. Store focused cases separately from full-day cases. Include future sentinel data only behind the cutoff guard test path; ordinary policy evaluation must never receive it.

## Shared Patterns

### Pure, explicit decision inputs

**Sources:** `trading_bot/screener.py:110-169`, `trading_bot/risk.py:59-97`, `trading_bot/execution.py:235-355`  
**Apply to:** replay engine, cutoff store, manifest construction, tests.

All policy inputs are arguments. No implicit settings, current date, provider, DB, or network access is allowed in the replay engine.

### Fail closed before action

**Sources:** `trading_bot/screener.py:134-143`, `trading_bot/execution.py:262-278`, `trading_bot/risk.py:72-85`  
**Apply to:** fixture validation, future access, malformed signals, stale data, invalid sizing.

Unsafe inputs become explicit rejection/HOLD evidence or a fixture-validation failure before state mutation.

### Stable ordering and immutable output

**Sources:** `trading_bot/screener.py:48-90`, `trading_bot/screener.py:161-169`  
**Apply to:** candidates, outcomes, checks, blocked reasons, funnel serialization.

Use frozen dataclasses and tuples for public replay results. Sort candidates by production score/ticker contract and define stable ordering for every mapping converted to JSON.

### Scenario-scoped state mutation

**Source:** `trading_bot/mock_broker.py:31-69`, `trading_bot/mock_broker.py:119-192`  
**Apply to:** full-day replay only.

Mutation happens only through an explicit `COMPLETE` fill after decision evaluation. A `NONE` fill must leave before/after state identical. Never share state across focused bundles.

### CLI testing without external systems

**Source:** `tests/test_cli.py:195-247`  
**Apply to:** `replay` command tests.

Use `CliRunner`, monkeypatch composition points, assert stdout/stderr separately, and verify no live builder is reachable.

## No Analog Found

| File/Concern | Role | Data Flow | Reason / Planner Guidance |
|---|---|---|---|
| Canonical identity and dirty-worktree hashing within `trading_bot/replay.py` | utility | transform, subprocess | No existing content-addressed result implementation. Follow `07-RESEARCH.md`: canonical stdlib JSON + SHA-256; hash HEAD plus normalized tracked worktree diff and document the scope. |
| Future-access guarded historical view within `trading_bot/replay.py` | service | request-response | No existing point-in-time query guard. Implement the explicit `FutureDataAccessError` pattern from research and test both supplied-row validation and requested-date rejection. |
| Explicit-denominator gate funnel within `trading_bot/replay.py` | model/utility | batch, transform | Existing code records terminal outcomes but not per-stage funnel facts. Derive counters from normalized per-ticker stage booleans and assert monotonic invariants. |

## Metadata

**Analog search scope:** `trading_bot/`, `tests/`, Phase 7 context/research, project `AGENTS.md`  
**Source files scanned:** 29 Python files; 9 primary analog files inspected  
**Primary analogs extracted:** 7 (`screener.py`, `execution.py`, `risk.py`, `mock_broker.py`, `audit_models.py`, `test_screener.py`, `test_execution.py`, plus CLI/test excerpts)  
**Pattern extraction date:** 2026-07-12
