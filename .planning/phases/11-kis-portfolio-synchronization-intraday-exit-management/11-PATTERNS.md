# Phase 11: KIS Portfolio Synchronization & Intraday Exit Management - Pattern Map

**Mapped:** 2026-09-02
**Files analyzed:** 21 new or modified files
**Analogs found:** 20 / 21
**Basis:** Current working tree, including pre-existing uncommitted Phase 9/KIS changes

## File Classification

| New/Modified File | Change | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|---|
| `trading_bot/portfolio.py` | create | model/service | batch + transform | `trading_bot/soak_reconcile.py` | exact |
| `trading_bot/portfolio_store.py` | create | store/migration | CRUD + event-driven | `trading_bot/sqlite_audit.py` | exact |
| `trading_bot/mutation_lease.py` | create | service/middleware | event-driven + CRUD | `trading_bot/sqlite_audit.py` | partial; no OS-lock analog |
| `trading_bot/exit_manager.py` | create | service | request-response + event-driven | `trading_bot/kis_broker.py` + `trading_bot/risk.py` | exact composition |
| `trading_bot/intraday.py` | create | service | batch + event-driven | `trading_bot/cli.py::run_cycle` | role-match |
| `trading_bot/kis_order.py` | modify | service/adapter | request-response | same file pagination and single-POST paths | exact |
| `trading_bot/kis_broker.py` | modify | service/adapter | request-response + event-driven | same file `place_order`/`reconcile_order` | exact |
| `trading_bot/cli.py` | modify | controller/route | request-response + batch | same file `run_cycle` and Typer commands | exact |
| `trading_bot/audit_models.py` | modify | model | transform + event-driven | same file frozen evidence contracts | exact |
| `trading_bot/config.py` | modify | config | transform | same file `Settings` validation | exact |
| `docs/operator-runbook.md` | modify | config/documentation | request-response | same file status/triage/checklist sections | exact |
| `tests/test_portfolio.py` | create | test | batch + transform | `tests/test_soak_reconcile.py` | exact |
| `tests/test_portfolio_store.py` | create | test | CRUD + event-driven | `tests/test_sqlite_audit.py` | exact |
| `tests/test_mutation_lease.py` | create | test | event-driven + CRUD | `tests/test_sqlite_audit.py` | role-match |
| `tests/test_exit_manager.py` | create | test | request-response + event-driven | `tests/test_kis_broker.py` + `tests/test_risk.py` | exact composition |
| `tests/test_intraday.py` | create | test | batch + event-driven | `tests/test_cli.py` | role-match |
| `tests/test_phase11_cli.py` | create | test | request-response + batch | `tests/test_cli.py` | exact |
| `tests/test_kis_order.py` | modify | test | request-response | same file page/query and POST tests | exact |
| `tests/test_kis_broker.py` | modify | test | request-response + event-driven | same file ambiguity/duplicate/partial tests | exact |
| `tests/test_config.py` | modify | test | transform | same file positive-policy validation tests | exact |
| `tests/test_operator_runbook.py` | modify | test | file-I/O + transform | same file structural runbook assertions | exact |

The file list comes from the research project's recommended structure and Wave 0 gaps, plus implied settings and operator-contract changes required by D-18 and the runbook integration recommendation. `portfolio_store.py` should own Phase 11 tables even when they live in the primary audit database; avoid spreading the new persistence API across `sqlite_audit.py` unless migration coupling makes a thin delegation necessary.

## Pattern Assignments

### `trading_bot/portfolio.py` and `tests/test_portfolio.py`

**Role/data flow:** immutable models and pure normalization; paginated KIS rows -> complete/incomplete account snapshot -> held-first evaluation targets.

**Analog:** `trading_bot/soak_reconcile.py`

**Frozen model pattern** (`trading_bot/soak_reconcile.py:98-160`):

```python
@dataclass(frozen=True)
class BrokerHolding:
    observation_id: str
    ticker: str
    quantity: int
    available_quantity: int
    average_price: float

@dataclass(frozen=True)
class BrokerSnapshot:
    snapshot_id: str
    campaign_id: str
    run_id: str
    stage: ReconciliationStage
    window: SnapshotWindow
    completeness: PageCompleteness
    reason_code: str
    orders: tuple[BrokerOrder, ...]
    fills: tuple[BrokerFill, ...]
    holdings: tuple[BrokerHolding, ...]
    account: BrokerAccountSummary
    observed_at: str
```

Copy the frozen tuple-based value-object shape, but make the Phase 11 snapshot account-scoped rather than campaign/touched-scoped. Add explicit total and orderable quantities, cancellation evidence, recent-window identity, and unresolved-order coverage. Stable identities and timezone-aware observation times stay mandatory.

**Normalization/completeness pattern** (`trading_bot/soak_reconcile.py:421-544`):

```python
daily = adapter.query_daily_ccld_pages(...)
balance = adapter.query_balance_pages(...)
snapshot_id = str(uuid.uuid4())

quantity = _integer(row.get("hldg_qty"))
available = _integer(row.get("ord_psbl_qty"))
average = _number(row.get("pchs_avg_pric"))
if quantity is None or available is None or average is None:
    balance = type(balance)(
        rows=balance.rows,
        summary=balance.summary,
        page_count=balance.page_count,
        completeness=PageCompleteness.INCOMPLETE,
        reason_code="NORMALIZATION_ERROR",
    )

complete = (
    daily.completeness is PageCompleteness.COMPLETE
    and balance.completeness is PageCompleteness.COMPLETE
    and _number(balance.summary.get("dnca_tot_amt")) is not None
    and _number(balance.summary.get("tot_evlu_amt")) is not None
)
```

Preserve the distinction between a valid empty complete page sequence and incomplete/malformed evidence. Remove the touched-ticker filter at `soak_reconcile.py:438-445` for the account projection; do not broaden Phase 9's existing touched projection accidentally.

**Test pattern** (`tests/test_soak_reconcile.py:185-246`): build `BrokerPageEnvelope` fixtures directly, call the pure collector, assert page counts/normalized rows/completeness, and prove incomplete evidence yields `UNKNOWN` rather than a fabricated mismatch. Extend this matrix for zero holdings/orders, repeated tokens, page cap, missing summary, malformed numerics, cancellation conflicts, older unresolved orders, held-first ordering, and HELD/SCREENED overlap.

---

### `trading_bot/portfolio_store.py` and `tests/test_portfolio_store.py`

**Role/data flow:** append-only SQLite persistence for immutable portfolio observations, divergence facts, once-daily evaluations, watch observations, notification state projections, and their stable links.

**Analog:** `trading_bot/sqlite_audit.py`

**Migration pattern** (`trading_bot/sqlite_audit.py:105-160`):

```python
version = int(conn.execute("PRAGMA user_version").fetchone()[0])
if version > SCHEMA_VERSION:
    raise RuntimeError(f"unsupported audit schema version: {version}")
try:
    conn.execute("BEGIN IMMEDIATE")
    # additive CREATE TABLE / CREATE INDEX / ALTER TABLE operations
    conn.execute("PRAGMA user_version = 3")
    conn.commit()
except Exception:
    conn.rollback()
    raise
```

Use a short explicit transaction and additive schema changes. The daily evaluation header needs a database uniqueness constraint on `(trading_date_kst, ticker)`; evaluation events, snapshot facts, divergences, watch observations, and transition occurrences should be inserts. Persist the immutable canonical LLM input/hash before provider attempts, and finalize a STARTED-without-final record to unavailable HOLD during recovery.

**Append-and-commit pattern** (`trading_bot/sqlite_audit.py:275-332`):

```python
detail = sanitize_detail(event.detail)
cursor = conn.execute(
    """INSERT INTO order_events (...) VALUES (...)""",
    (..., json.dumps(detail, sort_keys=True), ...),
)
conn.commit()
```

Immediate commit is part of the money-moving safety boundary. Preserve normalized scalar-only JSON, origin/observer identities, and monotonic append order. A notification-attempt evidence write must raise to the caller; transport failure alone must not.

**Test pattern** (`tests/test_sqlite_audit.py:281-359`): open a second SQLite connection to prove commits are visible, assert IDs are ordered, assert invalid writes leave zero partial rows, inject migration failure, verify rollback, then reopen and retry migration successfully. Add uniqueness races and crash-recovery cases for daily evaluation and lease metadata.

---

### `trading_bot/mutation_lease.py` and `tests/test_mutation_lease.py`

**Role/data flow:** process-lifetime account mutation exclusion plus durable acquisition, heartbeat, loss, release, and recovery transitions.

**Closest partial analogs:** `trading_bot/sqlite_audit.py:203-239` for conditional terminal transitions and `trading_bot/cli.py:1097-1122` for a short `BEGIN IMMEDIATE` health probe.

```python
cursor = conn.execute(
    "UPDATE runs SET status = ?, finished_at = ? WHERE run_id = ? AND status = ?",
    (status.value, finished_at, run_id, RunStatus.RUNNING.value),
)
if cursor.rowcount != 1:
    conn.rollback()
    raise ValueError("run is missing or already terminal")
conn.commit()
```

Copy conditional-rowcount ownership checks: every renew and pre-POST assertion must affect exactly one row for the same account-scope hash and owner token. Use `BEGIN IMMEDIATE` only around metadata transitions, never around network calls or the watch lifetime.

There is **no existing OS-lock analog**. Implement the researched hybrid boundary directly: account-scope-hashed lock path, restrictive file creation, non-blocking `fcntl.flock(..., LOCK_EX | LOCK_NB)`, open descriptor retained for the command lifetime, durable state transitioned `ACQUIRING -> RECOVERY -> ACTIVE`, and durable release recorded before unlocking on normal shutdown. Heartbeat age alone never permits takeover.

Tests must use separate processes, not threads only: active rejection/no wait, crash releases kernel lock but retains durable owner, stale-owner recovery ordering, unresolved recovery block, token mismatch/lost ownership, and release ordering.

---

### `trading_bot/exit_manager.py` and `tests/test_exit_manager.py`

**Role/data flow:** shared daily-LLM/intraday-risk SELL coordinator; current snapshot + trigger -> broker refresh/gates -> one intent or reconcile-only result.

**Analogs:** `trading_bot/risk.py` for pure triggers and `trading_bot/kis_broker.py` for the mutation boundary.

**Pure trigger pattern** (`trading_bot/risk.py:59-97`):

```python
if position is None or position.quantity <= 0:
    return RiskDecision(RiskAction.HOLD, "no held position")
if entry <= 0 or price <= 0:
    return RiskDecision(RiskAction.HOLD, "non-positive price input")
if change_pct <= -abs(config.stop_loss_pct):
    return RiskDecision(RiskAction.SELL, "stop_loss")
if change_pct >= abs(config.take_profit_pct):
    return RiskDecision(RiskAction.SELL, "take_profit")
return RiskDecision(RiskAction.HOLD, "within risk bounds")
```

Do not duplicate threshold logic in the coordinator. Intraday calls this reducer without an LLM. Keep `blocks_new_buy()` BUY-only; daily loss must not block stop/take SELLs.

**Query-before-single-POST pattern** (`trading_bot/kis_broker.py:127-160,200-227`):

```python
self._preflight()
self._emit(OrderEvent(... event_type=OrderEventType.INTENT_CREATED, ...))
existing = self._find_existing_order(order)
self._emit(OrderEvent(... event_type=OrderEventType.DUPLICATE_CHECKED, ...))
if existing is not None:
    self._emit(OrderEvent(... event_type=OrderEventType.RECONCILED, ...))
    return existing

self._emit(OrderEvent(... event_type=OrderEventType.SUBMISSION_ATTEMPTED, ...))
try:
    result = self._order_adapter.place_order_cash(...)
except Exception as exc:
    self._emit(OrderEvent(... event_type=OrderEventType.SUBMISSION_AMBIGUOUS, ...))
    raise AmbiguousSubmissionError(...) from None
```

Before reaching this boundary, assert active lease ownership, complete account snapshot, no OPEN/PARTIAL same-ticker SELL, continuous session, unfrozen ticker, latest affected-ticker holding/open-order/fill truth, latest orderable quantity, and inclusive 10-second quote freshness. If truth changed, recalculate and rerun gates. Do not credit local SELL proceeds or calculate authoritative remaining holdings from local fills.

**Test pattern** (`tests/test_kis_broker.py:219-334`): count POST attempts, inspect ordered evidence events, prove timeout is one POST plus ambiguity, link later observer truth to the origin intent, prove duplicate means zero POST, and cover partial fill. Expand to open SELL suppressing both new SELL and BUY, latest orderable full-quantity SELL, determinate cancel allowing only a later independent intent, and portfolio refresh before POST.

---

### `trading_bot/intraday.py`, `tests/test_intraday.py`, and `tests/test_phase11_cli.py`

**Role/data flow:** independently audited one-shot iteration and foreground watch state machine.

**Analog:** `trading_bot/cli.py::run_cycle`

**Injected orchestration/lifecycle pattern** (`trading_bot/cli.py:1303-1322,1369-1413`):

```python
def run_cycle(*, settings=None, data_source=None, llm_provider=None, broker=None,
              audit_conn=None, notifier=None, run_cycle=None, trading_date=None,
              run_id=None, ...):
    """Run the screened universe with injected or production collaborators."""
    ...
    sqlite_audit.start_run(...)
    if hasattr(resolved_broker, "set_evidence_sink"):
        def persist_order_event(event):
            sqlite_audit.append_order_event(resolved_audit_conn, event)
        resolved_broker.set_evidence_sink(persist_order_event)
```

Keep `intraday.py` independent of Typer. Inject clock, sleeper, snapshot service, quote reader, lease, exit coordinator, audit store, and stop-request reader. Every loop iteration gets a separate cycle identity and terminal outcome; no transaction or snapshot grants authority to the next iteration.

**Error/interruption pattern** (`trading_bot/cli.py:1512-1570`): isolate attributable ticker failures, persist terminal outcome in `finally`, terminalize the run as `INTERRUPTED` on interruption and `FAILED` on other escaping `BaseException`. Phase 11 must strengthen interruption: request stop via a signal flag, stop new POSTs at safe checkpoints, reconcile submitted intents within the bounded window, persist unresolved state, then release lease.

**Typer command pattern** (`trading_bot/cli.py:1847-1871`):

```python
@app.command("run")
def run_command(...):
    try:
        result = run_cycle(...)
    except SystemExit as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(2) from None
    typer.echo(f"Run {result['run_id']} complete: ...")
```

Add an `intraday` Typer sub-app with thin `check` and `watch` wrappers. The service owns the state machine (`PREFLIGHT_READ_ONLY`, `RECOVERY_ONLY`, `ACTIVE`, `RECONCILE_ONLY`, `STOPPING`, `TERMINAL`). Tests should invoke services directly for time matrices and use `CliRunner` only for wiring, options, exit codes, Korean rendering, and the proof that no LLM collaborator is built/called.

---

### Existing adapter and contract modifications

#### `trading_bot/kis_order.py` / `tests/test_kis_order.py`

Copy the current complete-page query contract (`trading_bot/kis_order.py:464-621`): positive page cap, allowlisted normalized scalars, explicit provider/parse/repeated-token/page-cap incompleteness, and continuation through `tr_cont`. Extend the daily-row allowlist at lines 505-509 with official cancellation/rejection/original-order identity fields; do not persist raw responses. Preserve bounded retry on `_fetch_query_page` (`lines 770-797`) and no retry on `place_order_cash` (`lines 624-675`).

#### `trading_bot/kis_broker.py` / `tests/test_kis_broker.py`

Retain intent/submission IDs, ordered evidence, fresh-quote check, single-shot POST, ambiguity, and later `BROKER_OBSERVED` append (`trading_bot/kis_broker.py:121-280`). Replace in-memory position authority after partial fill/restart with the latest complete portfolio truth; expose/inject the Phase 11 pre-POST portfolio refresh and lease ownership assertion.

#### `trading_bot/audit_models.py`

Extend stable `StrEnum` vocabularies and frozen dataclasses following `trading_bot/audit_models.py:13-82,113-196`. Validate bounded stable codes and timezone-aware observations in `__post_init__`; wrap normalized mappings with `MappingProxyType`. Reuse `sanitize_detail()` (`lines 92-110`) so account numbers, tokens, payloads, messages, and non-scalar provider objects never enter evidence.

#### `trading_bot/config.py` / `tests/test_config.py`

Add watch cadence, minimum cadence, reconciliation timeout/poll interval, heartbeat, and long-open warning settings beside existing operational fields. Follow `trading_bot/config.py:140-174`: a single post-model safety validator calls a focused helper and rejects every non-positive bound. Enforce configured cadence `>=` minimum; Phase 11 research recommends both default and minimum as 60 seconds.

#### `docs/operator-runbook.md` / `tests/test_operator_runbook.py`

Extend the existing command sequence, completion checklist, triage table, and recovery checklist (`docs/operator-runbook.md:20-80`). Document `intraday check/watch`, pre-open read-only behavior, 15:20 mutation cutoff, 15:30 exit, Ctrl-C reconciliation, lease-active inspection, stale-owner recovery, open/PARTIAL SELL observation, and the explicit prohibitions on cancellation, market orders, price chasing, and blind resubmission. Follow `tests/test_operator_runbook.py:19-45`: read the real Markdown file and assert headings, stable codes, commands, and table columns structurally.

## Shared Patterns

### Complete evidence grants mutation authority; incomplete evidence blocks it

**Sources:** `trading_bot/kis_order.py:540-621`, `trading_bot/soak_reconcile.py:509-544`

Every required dimension must be explicit and normalized. `UNKNOWN` and `INCOMPLETE` are not empty/zero and never become executable. Read queries can retry within bounds; POST never retries.

### Stable identity and append-only evidence

**Sources:** `trading_bot/kis_broker.py:133-258`, `trading_bot/sqlite_audit.py:275-332`

Create identities before effects, persist `SUBMISSION_ATTEMPTED` immediately before POST, append later broker observations with both origin and observer identities, sanitize, and commit immediately. Never overwrite intent/history with current broker state.

### Fail-soft transport, fail-closed evidence

**Source:** `trading_bot/cli.py:1041-1086`

```python
try:
    delivered = bool(notifier.send(summary))
except Exception:
    status, failure_category = NotificationDeliveryStatus.FAILED, "TRANSPORT_EXCEPTION"

# Deliberately outside the fail-soft envelope:
sqlite_audit.append_notification_attempt(conn, NotificationAttempt(...))
```

For Phase 11, notify only begin/change/recovery state transitions and safety events. Append every watch observation and update occurrence/duration projection even when no notification is sent.

### Deterministic pure domain logic

**Source:** `trading_bot/risk.py:1-97`

Pure reducers accept explicit frozen inputs and return stable decisions; they do not import settings, SQLite, network clients, CLI, or LLM types. Apply this to held-first union, divergence classification, exit trigger reduction, session phase calculation, and notification-state transition reduction.

### Synchronous injection for tests

**Source:** `trading_bot/cli.py:1303-1367`

Production builders fill missing collaborators; tests inject all collaborators and clocks. Avoid real sleeps, wall-clock timing, KIS credentials, signals, or LLM calls in unit tests.

### Error isolation and terminalization

**Source:** `trading_bot/cli.py:1512-1570`

Per-ticker market/LLM failure is attributable and siblings continue. Account-truth, lease, or audit failure blocks mutation account-wide. Every started cycle reaches a terminal status, including interruption and abandoned-process recovery.

## No Analog Found

| File/Concern | Role | Data Flow | Reason |
|---|---|---|---|
| `trading_bot/mutation_lease.py` OS lock half | middleware/service | event-driven | Repository has SQLite transaction and recovery patterns, but no `fcntl`/process-lifetime lock implementation. Use the researched hybrid `flock` + durable metadata design and multiprocessing tests. |

## Planner Guardrails

- Build portfolio completeness/cancellation normalization before lease-enabled orchestration, and both before watch/CLI work.
- Account-wide incomplete truth or unattributable unresolved order risk blocks all mutation; per-held-ticker market evidence failure records `DATA_INCOMPLETE/HOLD` and allows siblings.
- One logical LLM evaluation per KRX trading date/ticker is a durable uniqueness rule, including crash-finalized unavailable HOLD. Same-day reuse reruns every current safety gate.
- Held positions are processed first; screened-only candidates use broker-observed cash/positions after held processing. Never project SELL proceeds locally.
- OPEN/PARTIAL SELL means reconcile-only. Cancellation is observed, never POSTed by this phase. A new intent is possible only in a later independent complete cycle.
- Watch is foreground/manual: default/minimum 60 seconds, read-only before continuous session, no new POST from 15:20, reconciliation through 15:30, then exit.
- Mutation lease is account-scoped across `run`, `intraday check`, and `intraday watch`; it is non-blocking, never stolen by heartbeat age, and checked before every POST.
- Preserve repository spelling compatibility for existing `CANCELLED`; if accepting `CANCELED`, use an explicit alias/migration rather than two semantic states.

## Metadata

**Analog search scope:** `trading_bot/`, `tests/`, `docs/`
**Strong analogs extracted:** `soak_reconcile.py`, `sqlite_audit.py`, `kis_broker.py`, `risk.py`, `cli.py`
**Supporting contracts inspected:** `audit_models.py`, `kis_order.py`, `config.py`, `operator-runbook.md`, and corresponding tests
**Pattern extraction date:** 2026-09-02

