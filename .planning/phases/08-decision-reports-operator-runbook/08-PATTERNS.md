# Phase 8: Decision Reports & Operator Runbook - Pattern Map

**Mapped:** 2026-07-13
**Files analyzed:** 14 new/modified files
**Primary analogs found:** 5 / 5 implementation roles

## Scope Extracted from Context and Research

Phase 8 adds a read-only reporting slice, a shared fail-closed preflight, append-only notification evidence, and an operator runbook. The report path must remain offline and must preserve the existing run/ticker/order/replay identities. The expected file set is:

- Create `trading_bot/reporting.py`, `trading_bot/report_cli.py`, and `trading_bot/preflight.py`.
- Modify `trading_bot/audit_models.py`, `trading_bot/sqlite_audit.py`, and `trading_bot/cli.py`.
- Create `docs/operator-runbook.md`.
- Create `tests/test_reporting.py`, `tests/test_report_cli.py`, `tests/test_preflight.py`, and `tests/test_operator_runbook.py`.
- Extend `tests/test_sqlite_audit.py`, `tests/test_cli.py`, and `tests/test_notifier.py` for notification persistence and unchanged fail-soft behavior.

No source, test, state, roadmap, or plan file was modified while producing this map.

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `trading_bot/reporting.py` | service + immutable read models + renderer utility | batch, transform, read-only SQLite/file I/O | `trading_bot/replay.py` | role/data-flow match |
| `trading_bot/report_cli.py` | controller / Typer sub-application | request-response, file I/O | `trading_bot/cli.py` | exact controller match |
| `trading_bot/preflight.py` | policy service + immutable evidence models | request-response, transform | `trading_bot/market_cycle.py` | exact policy/evidence match |
| `trading_bot/audit_models.py` | model / stable vocabulary | event-driven evidence | existing contents of same file | exact extension point |
| `trading_bot/sqlite_audit.py` | migration + persistence service | CRUD, append-only event writes | existing contents of same file | exact extension point |
| `trading_bot/cli.py` | composition root / controller | request-response, event-driven | existing `run`, `screen`, `status`, `_safe_send` paths | exact extension point |
| `docs/operator-runbook.md` | operator documentation | manual workflow / decision table | command and reason contracts in `trading_bot/cli.py` and `audit_models.py` | semantic match |
| `tests/test_reporting.py` | unit/integration test | batch transform + SQLite reads | `tests/test_sqlite_audit.py`, `tests/test_replay.py` | combined role match |
| `tests/test_report_cli.py` | CLI integration test | request-response + file I/O | `tests/test_cli.py` | exact test style |
| `tests/test_preflight.py` | policy unit test | request-response / fail-closed transform | `tests/test_market_cycle.py` | exact test style |
| `tests/test_operator_runbook.py` | documentation contract test | file I/O / static validation | `tests/test_replay.py` strict-catalog assertions | partial data-flow match |
| `tests/test_sqlite_audit.py` | persistence regression test | CRUD + append-only events | existing contents of same file | exact extension point |
| `tests/test_cli.py` | CLI regression test | injected request-response | existing contents of same file | exact extension point |
| `tests/test_notifier.py` | adapter regression test | retrying request-response | existing contents of same file | exact extension point |

## Primary Analogs

The five strongest production analogs are:

1. `trading_bot/replay.py` — frozen models, deterministic transforms, explicit denominators, strict identity validation, and atomic file output.
2. `trading_bot/sqlite_audit.py` — additive schema migration, bound SQL, immediate commits, normalized JSON, append-only order evidence, and stable insertion order.
3. `trading_bot/cli.py` — synchronous Typer commands, bounded diagnostics, offline command boundary, dependency injection, and terminal run handling.
4. `trading_bot/market_cycle.py` — immutable typed evidence, `UNKNOWN` as a first-class state, injected providers, and fail-closed policy evaluation.
5. `trading_bot/audit_models.py` — provider-neutral `StrEnum` vocabularies, frozen dataclasses, and sanitized scalar evidence.

## Pattern Assignments

### `trading_bot/reporting.py` (service/models/renderer, batch transform and read-only file I/O)

**Primary analog:** `trading_bot/replay.py`

**Immutable normalized model pattern** (`trading_bot/replay.py:86-99`, `130-169`):

```python
@dataclass(frozen=True)
class ReplayManifest:
    scenario_hash: str
    ohlcv_hash: str
    raw_signal_hash: str
    policy: Mapping[str, Any]
    # ... stable evidence fields ...

@dataclass(frozen=True)
class ReplayResult:
    manifest: ReplayManifest
    outcomes: tuple[Any, ...]
    observational_metadata: Mapping[str, Any]
```

Create frozen report rows and summaries in the same style. Keep run completeness, ticker completeness, target, notification delivery, and reconciliation as separate typed fields; do not collapse them into one success flag.

**Explicit-denominator reduction pattern** (`trading_bot/replay.py:324-385`):

```python
@dataclass(frozen=True)
class ReplayCount:
    numerator: int
    denominator: int

def build_replay_funnel(outcomes: Sequence[ReplayOutcome]) -> ReplayFunnel:
    total = len(outcomes)
    selected = sum(outcome.selected for outcome in outcomes)
    # ...
    if not total >= selected >= buy >= confidence >= risk >= sized >= eligible:
        raise ValueError("replay BUY-stage facts violate monotonic funnel invariants")
```

Derive daily/period totals from immutable detail rows, then assert `complete + incomplete + unknown == total`. For replay aggregation, retain the existing numerator/denominator objects and never infer a denominator from missing data.

**Strict identity and canonicalization pattern** (`trading_bot/replay.py:54-83`, `101-127`, `162-169`):

```python
def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        _canonical_value(value), sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")

def compute_result_id(...):
    return hashlib.sha256(canonical_json_bytes(document)).hexdigest()
```

Reuse `canonical_json_bytes()` and the shipped result-ID semantics when loading report replay inputs. Validate identity before reading funnels, deduplicate repeated paths by stable result ID, and form compatibility signatures only from locked schema/policy/scenario basis fields.

**Atomic output pattern** (`trading_bot/replay.py:172-217`):

```python
with tempfile.NamedTemporaryFile(
    mode="wb", dir=root, prefix=".replay-", suffix=".tmp", delete=False
) as temporary:
    temporary.write(payload)
    temporary.flush()
    os.fsync(temporary.fileno())
os.replace(temporary_name, target)
```

Render once to one newline-normalized UTF-8 string, pass that same string to `typer.echo`, and atomically persist the identical bytes for `--output`. Retain the symlink/path checks around this pattern.

**Read-only repository variation:** do not copy `sqlite_audit.connect()` because it creates directories, enables WAL, and migrates. Open an existing resolved path using SQLite URI `mode=ro`, set `row_factory = sqlite3.Row`, execute `PRAGMA query_only=ON`, validate `PRAGMA user_version`, and read all normalized tables in one explicit transaction with bound parameters. Fetch runs, outcomes, decisions, notification attempts, and order events separately; reduce them by stable IDs in Python to prevent one-to-many join multiplication.

### `trading_bot/report_cli.py` (Typer controller, request-response and file I/O)

**Primary analog:** `trading_bot/cli.py`

**Command declaration and option validation pattern** (`trading_bot/cli.py:523-554`, `614-623`):

```python
@app.command("run")
def run_command(
    ticker: Optional[str] = typer.Option(None, "--ticker", help="Run one 6-digit KRX ticker."),
) -> None:
    ...

@app.command("replay")
def replay_command(
    fixture: Path = typer.Argument(..., exists=True, dir_okay=False, readable=True),
    output: Path = typer.Option(..., "--output", file_okay=False),
) -> None:
    ...
```

Define a separate `report_app = typer.Typer(no_args_is_help=True, ...)`, register it from `cli.py` with `app.add_typer(report_app, name="report")`, and put `daily`, `period`, and `replay` under it. Keep exact date parsing and `start <= end` validation at the CLI boundary; pass validated values to pure report services.

**Offline command and bounded diagnostic pattern** (`trading_bot/cli.py:550-609`):

```python
try:
    raw = json.loads(fixture.read_text(encoding="utf-8"))
    # offline deterministic work
except (OSError, ValueError, RuntimeError, json.JSONDecodeError) as exc:
    typer.echo(f"Replay failed: {type(exc).__name__}: {str(exc)[:200]}", err=True)
    raise typer.Exit(2) from None
```

Report commands must not call `build_runtime()` or instantiate credential-validating `Settings`. Resolve the audit DB through a dedicated `ReportSettings` contract containing only `audit_db_path`, then use the read-only repository. Bound diagnostics and never echo raw replay/provider payloads, secrets, or webhook values.

### `trading_bot/preflight.py` (policy service and evidence models, fail-closed transform)

**Primary analog:** `trading_bot/market_cycle.py`

**Stable state + frozen evidence pattern** (`trading_bot/market_cycle.py:15-44`):

```python
class CalendarState(StrEnum):
    TRADING_DAY = "TRADING_DAY"
    CLOSED_DAY = "CLOSED_DAY"
    UNKNOWN = "UNKNOWN"

@dataclass(frozen=True)
class MarketCycleEvidence:
    observed_at_kst: datetime
    trading_date: date
    calendar_state: CalendarState
    session: MarketSession
    executable: bool
    reason: str
    policy_version: str = POLICY_VERSION
```

Model each preflight check as `PASS`, `BLOCK`, or `UNKNOWN`, with stable code, Korean explanation, sanitized evidence, and a trading-stop flag. Return an immutable aggregate result consumed by both `status` and `run`.

**Injected provider and fail-closed exception pattern** (`trading_bot/market_cycle.py:67-102`, `122-127`):

```python
def classify(self, observed_at: datetime) -> MarketCycleEvidence:
    try:
        trading_day = self._calendar.is_trading_day(kst.date())
    except Exception:
        return self._unknown(kst, "calendar unavailable")
    if trading_day is None:
        return self._unknown(kst, "calendar unavailable")
```

Inject mock-target, audit-health, KRX-session, and unresolved-intent readers. Provider errors become `UNKNOWN/BLOCK`, never PASS. Keep Phase 8 unresolved-order checking local to append-only audit evidence; do not claim authenticated broker truth reserved for Phase 9.

### `trading_bot/audit_models.py` and `trading_bot/sqlite_audit.py` (stable model + append-only persistence)

**Primary analogs:** their existing contents.

**Vocabulary and sanitization pattern** (`trading_bot/audit_models.py:34-68`, `70-92`, `95-124`):

```python
class OrderEventType(StrEnum):
    INTENT_CREATED = "INTENT_CREATED"
    SUBMISSION_AMBIGUOUS = "SUBMISSION_AMBIGUOUS"
    BROKER_OBSERVED = "BROKER_OBSERVED"
    RECONCILED = "RECONCILED"

def sanitize_detail(detail: Mapping[str, Any] | None) -> dict[str, Any]:
    # rejects raw/provider/credential shapes and permits scalar facts only
    ...

@dataclass(frozen=True)
class OrderEvent:
    order_intent_id: str
    origin_run_id: str
    observer_run_id: str
    ticker: str
    event_type: OrderEventType
```

Add notification kind/delivery status enums and a frozen notification-attempt model here. Store only sanitized category/status facts, never webhook URLs, message bodies, raw exceptions, or provider payloads.

**Additive migration pattern** (`trading_bot/sqlite_audit.py:94-136`):

```python
version = int(conn.execute("PRAGMA user_version").fetchone()[0])
if version > SCHEMA_VERSION:
    raise RuntimeError(f"unsupported audit schema version: {version}")
try:
    conn.execute("BEGIN IMMEDIATE")
    # additive DDL
    conn.execute("PRAGMA user_version = 2")
    conn.commit()
except Exception:
    conn.rollback()
    raise
```

Bump the schema additively and create a normalized notification-attempt table keyed to `run_id`, optional ticker, kind, stable delivery state/failure category, and observed time. Preserve old rows and idempotent reopen behavior.

**Bound append-only write pattern** (`trading_bot/sqlite_audit.py:251-268`):

```python
cursor = conn.execute(
    """INSERT INTO order_events (...) VALUES (?, ?, ..., ?)""",
    (..., json.dumps(detail, sort_keys=True), observed_at),
)
conn.commit()
return int(cursor.lastrowid)
```

Follow this for `append_notification_attempt()`: validate the enum, sanitize details, use placeholders, commit immediately, and return insertion ID. Do not overwrite earlier attempts.

### `trading_bot/cli.py` (composition integration and mutation gate)

**Primary analog:** existing `run_cycle()` lifecycle.

**Mutation-boundary placement** (`trading_bot/cli.py:329-381`):

```python
resolved_trading_date = trading_date or _today_kst()
# dependencies are resolved first
resolved_run_id = run_id or uuid.uuid4().hex
_ensure_audit_schema(resolved_audit_conn)
sqlite_audit.recover_abandoned_runs(resolved_audit_conn)
sqlite_audit.start_run(...)
```

Evaluate the shared preflight before `recover_abandoned_runs()` and `start_run()` for an executable run. Any required non-PASS result exits before creating or mutating a run. `status` renders the exact same result object. Historical report commands remain registered but independent of this live path.

**Terminal lifecycle pattern** (`trading_bot/cli.py:387-505`):

```python
try:
    # per-ticker isolation and terminal outcome persistence
    sqlite_audit.finish_run(..., status=RunStatus.COMPLETED)
except KeyboardInterrupt:
    sqlite_audit.finish_run(..., status=RunStatus.INTERRUPTED)
    raise
except BaseException:
    sqlite_audit.finish_run(..., status=RunStatus.FAILED)
    raise
```

Do not weaken this lifecycle. Reports interpret but never rewrite it.

**Fail-soft notification seam to extend** (`trading_bot/cli.py:229-233`, `484`, `507-513`):

```python
def _safe_send(notifier: Any, summary: str) -> bool:
    try:
        return bool(notifier.send(summary))
    except Exception:
        return False
```

Continue swallowing notification transport failure so trading results are unchanged, but record each immediate-error/final-summary attempt through the audit sink. If that audit write itself fails, apply the locked fail-closed audit rule; never invent a successful notification evidence row.

### `docs/operator-runbook.md` (manual operator workflow and triage catalog)

**Semantic sources:** `trading_bot/cli.py:523-707`, `trading_bot/audit_models.py:10-68`, and `trading_bot/market_cycle.py:15-44`.

Use actual command names and stable codes. Structure the document as:

1. Korean daily checklist with fixed KST times: 08:50 `bot status`, 09:05 `bot screen`, 09:10 `bot run`, immediate `bot report daily` review.
2. Completion checklist that requires terminal run/ticker evidence, order/no-trade review, ambiguous-order triage transfer, and direct report review after notification failure.
3. One failure table per required category. Every row must contain symptom/reason code, stop scope, evidence/commands, prohibited action, safe next action, and resolution criterion.
4. Explicit prohibitions: no automatic rerun, no blind resubmission, no profitability claim, and no continuation after audit-integrity uncertainty.

Document a parent-linked new manual run only after healthy evidence and confirmed no-submission; freeze only the affected ticker for ambiguous/duplicate orders until broker truth is determinate.

## Test Pattern Assignments

### `tests/test_reporting.py` and persistence extensions

**Analogs:** `tests/test_sqlite_audit.py` and `tests/test_replay.py`.

Use `tmp_path` with real SQLite files and write normalized evidence through production persistence functions, as in `tests/test_sqlite_audit.py:210-245`. Assert processing order by insertion `id`, not timestamp:

```python
first_id = sqlite_audit.append_order_event(conn, first)
second_id = sqlite_audit.append_order_event(conn, second)
assert first_id < second_id
assert conn.execute(
    "SELECT event_type, origin_run_id, observer_run_id FROM order_events ORDER BY id"
).fetchall() == [...]
```

Copy explicit invariant testing from `tests/test_replay.py:464-482`: check denominators, state reconciliation, sorted stable categories, and loud rejection of invalid cardinality. Add a database before/after byte or schema/version assertion showing report reads do not create or migrate a DB.

### `tests/test_report_cli.py` and CLI extensions

**Analog:** `tests/test_cli.py`.

Use `CliRunner` plus `monkeypatch` on the composition boundary, as in `tests/test_cli.py:490-523`:

```python
monkeypatch.setattr(
    cli, "build_runtime",
    lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("live builder called")),
)
result = CliRunner().invoke(cli.app, [...])
assert result.exit_code == 0, result.output
```

Verify nested command discovery, inclusive KST date options, summary-before-detail order, every ticker detail, preview/run differences, stable code plus Korean explanation, and byte-identical terminal/file output. Follow `tests/test_cli.py:542-552` for bounded invalid-input diagnostics.

### `tests/test_preflight.py`

**Analog:** `tests/test_market_cycle.py`.

Use small injected fakes and parameterized boundary tables (`tests/test_market_cycle.py:19-55`). Assert every dependency outcome across PASS/BLOCK/UNKNOWN and confirm exceptions become UNKNOWN/BLOCK. Add a spy proving `run` does not call `start_run`, broker, LLM, or screening when any required check is non-PASS; confirm `status` and `run` consume the same result vocabulary.

### `tests/test_operator_runbook.py`

Treat the runbook as a stable contract catalog. Read it from a repository-relative `Path`, assert all four times/commands, completion criteria, required reason/failure codes, and required column labels. Mirror the strict-set style in `tests/test_replay.py:207-240` and the exact boundary-bijection checks in `tests/test_replay.py:297-323` so missing, duplicate, or unknown triage entries fail loudly.

### Notification regression tests

Preserve existing fail-soft adapter expectations from `tests/test_notifier.py:89-115`: `send()` returns False, retries are bounded, secrets do not appear in logs/repr, and no webhook produces a no-op notifier. Extend `tests/test_cli.py:468-487` to assert each immediate and final attempt is persisted while run outcome/status remains unchanged.

## Shared Patterns

### Stable codes plus Korean explanations

**Source:** enum vocabularies in `trading_bot/audit_models.py:10-68`.

Use enum values as keys in one Korean explanation catalog. Render `CODE — 한글 설명`; never replace the code with localized free text. Unknown persisted codes must render as explicit `UNKNOWN` with the original value bounded and visible, not become HOLD or zero.

### Evidence cardinality and ordering

**Source:** uniqueness and append ordering in `trading_bot/sqlite_audit.py:66-82`, `227-268`.

- One terminal ticker outcome per `(run_id, ticker)`.
- Zero or one expected decision per terminal ticker, with duplicates/missing rows surfaced as integrity warnings.
- Many append-only order and notification events ordered by integer insertion ID.
- Runs ordered by `(started_at, run_id)` and ticker detail by `ticker_outcomes.id`.
- Preview pairing uses the nearest earlier SCREEN on the same KST date and target; otherwise report unpaired/unknown.

### Fail-closed versus fail-soft

**Sources:** `trading_bot/market_cycle.py:74-102`, `trading_bot/cli.py:229-233`, `trading_bot/notifier.py:74-82`.

- Missing/exceptional decision-critical evidence becomes UNKNOWN/BLOCK and prevents `run` mutation.
- Notification transport stays fail-soft, but its attempt is persisted and daily completion requires direct report review.
- Audit persistence/integrity uncertainty blocks new trading and cannot be papered over with synthetic evidence.

### Validation and security

- Bind all SQL values; do not interpolate dates or IDs.
- Strictly parse CLI `YYYY-MM-DD`, convert to stored `YYYYMMDD`, require inclusive `start <= end`, and reject malformed replay structures before aggregation.
- Refuse ambiguous symlink/path output, write atomically, and do not overwrite conflicting content silently.
- Render only normalized sanitized fields; never raw exceptions, provider payloads, credentials, tokens, webhook URLs, or full message bodies.
- Keep all report commands offline and read-only; they must work even when preflight blocks live trading.

## Anti-Patterns to Avoid

- Calling `build_runtime()` from any report path.
- Reusing the migrating `sqlite_audit.connect()` for historical report reads.
- One giant SQL join across decisions, outcomes, and order events.
- Treating null/legacy/unrecognized values as zero, HOLD, complete, or reconciled.
- Pairing a later screen or a screen from another target with a run.
- Aggregating replay funnels before verifying result identity and compatibility, or counting duplicate stable IDs twice.
- Duplicating preflight logic between `status` and `run`.
- Starting a run before preflight has passed.
- Automatically rerunning data/API/LLM failures or resubmitting ambiguous/duplicate orders.
- Claiming replay measures profitability, returns, win rate, or investment performance.

## Planner Handoff

The safest plan order follows the data dependencies:

1. Extend stable audit vocabularies/schema and notification-attempt persistence with migration tests.
2. Build the read-only reporting repository, immutable models, evidence classification, replay validation/compatibility, and deterministic renderer with unit tests.
3. Add the nested report CLI and atomic terminal/file delivery with offline CLI tests.
4. Build one typed preflight evaluator, wire it into both `status` and the pre-`start_run` mutation gate, and persist notification outcomes.
5. Write and contract-test the Korean operator runbook against the shipped command/code vocabulary.

Keep the report implementation separate from the already-large `cli.py`; only registration and enforcement hooks belong in the composition root.
