# Phase 6: Audit Evidence & Cycle Boundaries - Pattern Map

**Mapped:** 2026-07-11
**Execution note:** Generic-agent workaround used because typed `gsd-pattern-mapper` dispatch was unavailable.
**Files analyzed:** 14 new/modified files
**Analogs found:** 14 / 14

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `trading_bot/audit_models.py` (new) | model | event-driven / transform | `trading_bot/data_models.py` | exact |
| `trading_bot/market_cycle.py` (new) | service / policy | transform | `trading_bot/data_models.py`, `trading_bot/kis_broker.py` | role-match |
| `trading_bot/sqlite_audit.py` | migration / store | CRUD / append-only | current file | exact |
| `trading_bot/cli.py` | controller / coordinator | batch / event-driven | current `run_cycle` | exact |
| `trading_bot/execution.py` | service | transform / request-response | `_finalize_cycle` | exact |
| `trading_bot/kis_broker.py` | service / provider | request-response / event-driven | current `KISBroker.place_order` | exact |
| `trading_bot/kis_quote.py` | provider | request-response | current `KisQuoteAdapter` | exact |
| `trading_bot/data_source.py` | service | batch / transform | current `MarketDataSource` | exact |
| `trading_bot/pykrx_adapter.py` | provider | request-response / batch | current `PykrxOhlcvAdapter` | exact |
| `tests/test_market_cycle.py` (new) | test | transform / boundary | `tests/test_data_source.py` | role-match |
| `tests/test_sqlite_audit.py` | test | CRUD / migration | current file | exact |
| `tests/test_cli.py` | test | batch / event-driven | current file | exact |
| `tests/test_kis_broker.py` | test | request-response / event-driven | current file | exact |
| `tests/test_kis_quote.py` | test | request-response / boundary | current file | exact |

## Pattern Assignments

### `trading_bot/audit_models.py` (model, event-driven / transform)

**Analog:** `trading_bot/data_models.py`

Use string enums for stable machine codes and frozen dataclasses for normalized, non-secret evidence. Keep this model module free of vendor imports.

**Enum and immutable evidence pattern** (`trading_bot/data_models.py:21-35`, `48-65`, `81-97`):

```python
class SourceStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"

@dataclass(frozen=True)
class DataSourceAuditEvent:
    ticker: str
    source: str
    status: str
    reason: str
    action: str
    observed_date: Optional[str] = None
    expected_date: Optional[str] = None
```

Apply this to `RunStatus`, `RunKind`, ticker outcomes/reasons/stages, order-event types, and their evidence dataclasses. Persist only allowlisted normalized fields.

### `trading_bot/market_cycle.py` (service/policy, transform)

**Analogs:** `trading_bot/data_models.py`, `trading_bot/kis_broker.py`

Preserve the pure policy style of `resolve_data_action`, but replace the broker's current boolean weekday clock with a typed result containing KST observation, confirmed trading date, session, executable flag/reason, and policy version.

**Pure decision pattern** (`trading_bot/data_models.py:116-128`):

```python
def resolve_data_action(health: SourceHealth, role: TickerRole) -> DataAction:
    if health.status is SourceStatus.AVAILABLE:
        return DataAction.BUILD_CONTEXT
    if role is TickerRole.HOLDING:
        return DataAction.FORCE_HOLD
    return DataAction.SKIP_CANDIDATE
```

**Clock injection seam to retain and strengthen** (`trading_bot/kis_broker.py:54-69`, `111-115`):

```python
def __init__(..., market_clock: Optional[Callable[[], bool]] = None,
             data_fresh: Optional[Callable[[], bool]] = None) -> None:
    self._market_clock = market_clock or _default_market_clock
    self._data_fresh = data_fresh or _default_data_fresh

def _preflight(self) -> None:
    if not self._market_clock():
        raise MarketClosedError("KIS order skipped: market is closed")
    if not self._data_fresh():
        raise MarketClosedError("KIS order skipped: market data is stale")
```

Use aware `ZoneInfo("Asia/Seoul")` timestamps and half-open continuous trading `[09:00, 15:20)`. Calendar uncertainty must produce a typed non-executable result, never a weekday fallback.

### `trading_bot/sqlite_audit.py` (migration/store, CRUD + append-only)

**Analog:** current `trading_bot/sqlite_audit.py`

Evolve the existing central sink; do not create a parallel DB layer. Preserve parameterized statements and immediate commit semantics for terminal/outbound evidence while adding `PRAGMA foreign_keys=ON`, `PRAGMA user_version`, ordered additive migrations, and uniqueness/foreign-key constraints.

**Connection/schema anchor** (`trading_bot/sqlite_audit.py:55-65`):

```python
conn = sqlite3.connect(str(db_path))
conn.execute("PRAGMA journal_mode=WAL;")
conn.executescript(SCHEMA)
conn.commit()
```

**Parameterized immediate write** (`trading_bot/sqlite_audit.py:107-147`):

```python
cursor = conn.execute(
    """INSERT INTO decisions (...) VALUES (?, ?, ..., ?)""",
    (...),
)
conn.commit()
return int(cursor.lastrowid)
```

Add repository functions for abandoned-run recovery, run start/finalize, exactly-one ticker outcome, cycle evidence, and append-only order events. Keep legacy `decisions` readable; test a v1-shaped database migration rather than fabricating completeness for old rows.

### `trading_bot/cli.py` (controller/coordinator, batch + event-driven)

**Analog:** current `run_cycle`

Retain collaborator injection and per-ticker isolation, but move run recovery/start before screening and guarantee run finalization at the outer invocation boundary. Create a ticker outcome accumulator before any source call and persist exactly once in `finally`.

**Composition/injection pattern** (`trading_bot/cli.py:222-264`):

```python
def run_cycle(*, settings=None, data_source=None, llm_provider=None,
              broker=None, audit_conn=None, notifier=None,
              run_cycle=None, trading_date=None, run_id=None, ...) -> dict[str, Any]:
    ...
    resolved_data_source = data_source if data_source is not None else runtime.data_source
    cycle_fn = run_cycle or _run_llm_cycle
```

**Existing correlation and isolation seam** (`trading_bot/cli.py:282-340`):

```python
for symbol in tickers:
    correlation_id = f"{resolved_run_id}:{symbol}"
    try:
        context = resolved_data_source.build_context(Ticker(symbol))
        result = cycle_fn(...)
        sqlite_audit.write_decision(...)
    except Exception as exc:
        error_count += 1
        ...
        _safe_send(...)
        continue
```

Replace the exception-only in-memory outcome with normalized persisted terminal evidence. Apply the same run coordinator to `screen_command`; leave `status_command` read-only. Accept explicit optional `parent_run_id` and never infer retry relationships.

### `trading_bot/execution.py` (service, transform / request-response)

**Analog:** `_finalize_cycle`

Keep the single side-effect boundary and frozen `ExecutionResult`/audit shapes. Generate order intent identity before broker invocation and pass contextual evidence to the broker event sink without weakening the dry-run gate.

**Single broker mutation point** (`trading_bot/execution.py:174-220`):

```python
broker_order_id: Optional[str] = None
if not dry_run and order is not None:
    broker_order_id = broker.place_order(order)

audit = CycleAuditEvent(..., broker_order_id=broker_order_id)
return ExecutionResult(..., audit=audit, broker_order_id=broker_order_id)
```

### `trading_bot/kis_broker.py` (service/provider, request-response + event-driven)

**Analog:** current `KISBroker.place_order`

Keep query-before-POST and one POST attempt. Add an injected `OrderEventSink`, generate `order_intent_id` before duplicate inquiry and `submission_id` before POST, then emit append-only normalized events around every transition.

**Safe ordering pattern** (`trading_bot/kis_broker.py:79-109`):

```python
self._preflight()
snapped_price = snap_to_tick(order.limit_price.amount, side=order.side)
existing = self._find_existing_order(order)
if existing is not None:
    return existing
result = self._order_adapter.place_order_cash(...)
fill = self._read_fill_status(...)
self._reconcile_position(...)
```

**Normalized duplicate matching** (`trading_bot/kis_broker.py:121-144`): parse broker rows into order ID/ticker/quantity/side and compare explicit fields. Extend emitted evidence with requested, filled and remaining quantities and the matched order. Never persist the raw row.

Transport failure after POST begins is `AMBIGUOUS_SUBMISSION`; it must append an ambiguity event and must not issue a second POST. Later inquiry writes a reconciliation event with both originating and observing run IDs.

### `trading_bot/kis_quote.py` (provider, request-response)

**Analog:** current `KisQuoteAdapter`

Extend the frozen result with aware `observed_at`; inject a wall clock and assign the timestamp only after a valid price is parsed. Preserve normalized unavailability and secret-safe transport error text.

**Typed result and normalized failure** (`trading_bot/kis_quote.py:46-63`):

```python
@dataclass(frozen=True)
class KisQuoteResult:
    price: Optional[Money]
    health: SourceHealth

def _unavailable(reason: str) -> KisQuoteResult:
    return KisQuoteResult(price=None, health=SourceHealth(..., reason=reason))
```

**Sanitized transport handling** (`trading_bot/kis_quote.py:161-177`):

```python
except Exception as exc:
    raise _TransientQuoteError(
        f"quote request failed: {type(exc).__name__}"
    ) from None
```

The broker pre-submit path must re-fetch and accept only `0 <= age <= 10s`; negative or unavailable timestamps fail closed. Store initial and pre-submit observations separately.

### `trading_bot/data_source.py` and `trading_bot/pykrx_adapter.py`

**Analogs:** current typed source-health and explicit-date adapter seams.

Continue returning structured health/audit evidence rather than leaking vendor payloads into `DataContext`. Resolve the immediately preceding confirmed KRX trading day through an injected calendar provider, pass it as request end/freshness cutoff, and record requested date, completed-bar cutoff, and actual last bar. A returned bar later than cutoff is non-tradeable.

**Evidence boundary pattern** (`trading_bot/data_models.py:81-97`): `DataSourceAuditEvent` already separates ticker/source/status/reason/action and observed/expected dates from compact model context.

### Tests

#### `tests/test_market_cycle.py` (new)

Follow table-driven pure-policy tests from the data-source suite: use fixed aware KST datetimes and fake calendar results. Cover 08:59:59, 09:00:00, 15:19:59, 15:20:00, 15:30:00, weekend, holiday, calendar unavailable, prior trading-day cutoff, future returned bar, quote ages -1/0/10/>10 seconds.

#### `tests/test_sqlite_audit.py`

Reuse direct SQLite assertions and temporary DB setup (`tests/test_sqlite_audit.py:24-80`). Add v1-to-current migration, `PRAGMA user_version`, foreign keys, abandoned recovery, terminal-state transition rules, `UNIQUE(run_id,ticker)`, append-only event ordering, and legacy decisions readability.

#### `tests/test_cli.py`

Reuse injected in-memory connections/fakes and the current ticker-error-isolation test seam. Assert both `screen` and `run` terminalize, status creates no run, every attempted ticker has one outcome even on each stage failure, partial errors yield `COMPLETED_WITH_ERRORS`, outer failure yields `FAILED`, and explicit retry stores `parent_run_id`.

#### `tests/test_kis_broker.py`

Extend the current adapter fake and call counters (`tests/test_kis_broker.py:21-67`). Preserve the existing proof that a failing POST is attempted once (`91-105`) and duplicate inquiry suppresses POST (`107-130`). Add ordered event-sink assertions, IDs generated before calls, ambiguity classification, normalized broker facts, later observing-run attribution, and pre-submit quote freshness.

#### `tests/test_kis_quote.py`

Extend frozen-result, fake-client, retry, and secret-leak tests. Inject a fixed clock and assert `observed_at` exists only for a successfully parsed quote and is aware/KST (or consistently UTC-aware).

## Shared Patterns

### Immutable normalized evidence

**Source:** `trading_bot/data_models.py:21-97`, `trading_bot/execution.py:41-94`

Use `str, Enum` for stable codes and `@dataclass(frozen=True)` for internal evidence. Keep raw KIS/LLM responses, credentials, tokens and headers out of SQLite.

### Fail closed, isolate ticker, fail soft only for notification

**Source:** `trading_bot/cli.py:191-195`, `284-340`; `trading_bot/kis_broker.py:111-115`

Trading/calendar/quote uncertainty blocks mutation and becomes normalized evidence. One ticker failure does not stop later tickers. Notification failure alone is swallowed and must not affect durable audit state.

### Dependency injection for deterministic boundaries

**Source:** `trading_bot/cli.py:222-264`, `trading_bot/kis_broker.py:54-69`, `trading_bot/kis_quote.py:85-109`

Inject clock, calendar, quote reader, broker adapter, event sink and audit connection. Avoid deep `datetime.now()` calls in policy code.

### Parameterized SQLite writes and immediate durability

**Source:** `trading_bot/sqlite_audit.py:68-147`

All diagnostic strings are bound parameters. Terminal outcomes and order transitions commit promptly. Migrations use explicit transaction boundaries; do not assume `executescript()` participates in an already-open transaction.

### No blind broker POST retry

**Source:** `trading_bot/kis_broker.py:79-109`; proof in `tests/test_kis_broker.py:91-105`

Query before POST, assign submission identity before POST, attempt POST once, and reconcile ambiguity by inquiry.

## No Analog Found

No Phase 6 file is wholly without an analog. `market_cycle.py` and `audit_models.py` are new modules, but their pure-policy, frozen-model, and injected-clock shapes have strong in-repository precedents. The migration versioning and append-only event schema should use the concrete patterns in `06-RESEARCH.md` where the current v1 implementation has no equivalent.

## Plan Ownership Reconciliation

- `audit_models.py` is owned by Plan 06-01 and contains vendor-free enums, frozen evidence records, and sanitization; `sqlite_audit.py` remains persistence-only.
- `execution.py` is owned by Plan 06-03 for creating the order intent at the existing single money-moving boundary; `kis_broker.py` owns broker submission and reconciliation events.
- `pykrx_adapter.py` is intentionally unchanged in Phase 6. Its existing requested-range API already transports the cutoff selected by `MarketCyclePolicy`; Plan 06-04 verifies the exact end date at the data-source/adapter seam rather than duplicating calendar policy inside the provider.

## Metadata

**Analog search scope:** `trading_bot/`, `tests/`, Phase 6 context/research/validation
**Source files scanned:** 36 Python files; 8 primary analogs inspected in detail
**Pattern extraction date:** 2026-07-11
**Dispatch:** generic-agent workaround for `gsd-pattern-mapper`
