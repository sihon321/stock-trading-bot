# Phase 9: KIS Mock Soak & Fault Drills - Pattern Map

**Mapped:** 2026-07-16
**Files analyzed:** 21 new/modified files
**Analogs found:** 21 / 21

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `trading_bot/soak_models.py` | model | event-driven / transform | `trading_bot/audit_models.py` | exact role, same evidence flow |
| `trading_bot/soak_config.py` | config / composition guard | request-response | `trading_bot/config.py` + `trading_bot/preflight.py` | exact role, stricter capability boundary |
| `trading_bot/soak_compat.py` | provider compatibility probe | paginated request-response / fixture export | `trading_bot/kis_order.py` + replay fixture conflict checks | combined analog, strengthened provenance/sanitization |
| `trading_bot/kis_order.py` | provider / adapter | request-response / paginated batch | existing `KisOrderAdapter` query legs | in-place extension; current contract is incomplete |
| `trading_bot/soak_store.py` | store | CRUD / append-only file-I/O | `trading_bot/sqlite_audit.py` | exact role and flow |
| `trading_bot/soak_reconcile.py` | service | request-response / transform / batch | `trading_bot/kis_broker.py` reconciliation path | exact domain, broader broker-truth projection |
| `trading_bot/soak_campaign.py` | service / state machine | event-driven / CRUD | `trading_bot/market_cycle.py` + `trading_bot/sqlite_audit.py` | role-match |
| `trading_bot/soak_drills.py` | service / registry | event-driven | `trading_bot/cli.py` injected-collaborator orchestration | role-match |
| `trading_bot/soak_controller.py` | store / controller | append-only file-I/O / event-driven | `trading_bot/sqlite_audit.py` | exact storage pattern, stronger durability policy |
| `trading_bot/soak_reporting.py` | read-only projection | CRUD-read / transform | `trading_bot/reporting.py` | exact role and flow |
| `trading_bot/cli.py` | controller / route | request-response | existing `report` sub-app and `run_cycle` composition | in-place extension |
| `docs/operator-runbook.md` | documentation | manual workflow | existing Phase 8 command/run/reconciliation sections | exact role |
| `tests/test_soak_config.py` | test | request-response | `tests/test_config.py` | exact role |
| `tests/test_soak_store.py` | test | CRUD / file-I/O | `tests/test_sqlite_audit.py` | exact role and flow |
| `tests/test_soak_reconcile.py` | test | request-response / batch | `tests/test_kis_order.py` + `tests/test_kis_broker.py` | exact domain |
| `tests/test_soak_campaign.py` | test | event-driven / CRUD | `tests/test_sqlite_audit.py` + `tests/test_reporting.py` | role-match |
| `tests/test_soak_drills.py` | test | event-driven / subprocess | `tests/test_kis_broker.py` + `tests/test_cli.py` | role-match; subprocess restart is new |
| `tests/test_soak_cli.py` | test | request-response | `tests/test_cli.py` | exact role and flow |
| `tests/test_soak_reporting.py` | test | read-only CRUD / transform | `tests/test_reporting.py` | exact role, strengthened to three stores |
| `tests/test_operator_runbook.py` | documentation contract test | static structure / registry parity | Phase 8 runbook tests + CLI discovery tests | role-match, strengthened registry-derived assertions |
| Sanitized authenticated mock fixtures under `tests/fixtures/kis_mock/` | test fixture | file-I/O / batch | `tests/fixtures/replay/*.json` and `_FakeClient` response queues | role-match; authenticated shapes are new |

## Pattern Assignments

### `trading_bot/soak_models.py` (model, event-driven / transform)

**Analog:** `trading_bot/audit_models.py`

Use `StrEnum` for every persisted vocabulary and frozen dataclasses for immutable evidence. Coerce enum fields and protect normalized mappings during `__post_init__`; do not leave persisted state as free-form strings.

**Stable enums and immutable evidence** (`trading_bot/audit_models.py:61-70`, `112-141`):

```python
class OrderEventType(StrEnum):
    INTENT_CREATED = "INTENT_CREATED"
    DUPLICATE_CHECKED = "DUPLICATE_CHECKED"
    SUBMISSION_ATTEMPTED = "SUBMISSION_ATTEMPTED"
    SUBMISSION_ACCEPTED = "SUBMISSION_ACCEPTED"
    SUBMISSION_AMBIGUOUS = "SUBMISSION_AMBIGUOUS"
    BROKER_OBSERVED = "BROKER_OBSERVED"
    RECONCILED = "RECONCILED"

@dataclass(frozen=True)
class NotificationAttempt:
    # ... typed fields ...
    def __post_init__(self) -> None:
        object.__setattr__(self, "kind", NotificationKind(self.kind))
        object.__setattr__(self, "status", NotificationDeliveryStatus(self.status))
        clean = sanitize_detail(self.detail)
        object.__setattr__(self, "detail", MappingProxyType(clean))
```

Apply this to campaign status, day verdict, reconciliation stage/completeness/cardinality, ticker freeze state, drill fault/boundary/evidence class, containment result, and stable reason codes. D-09 requires a terminal campaign failure value with no reverse transition. D-17 requires distinct `CONTROLLED_INJECTION` and `KIS_OBSERVED` enum values.

**Sanitized scalar boundary** (`trading_bot/audit_models.py:84-109`):

```python
_FORBIDDEN_DETAIL_KEYS = {
    "raw", "payload", "response", "request", "app_key", "app_secret",
    "secret", "token", "authorization", "credential", "credentials",
}

def sanitize_detail(detail):
    # reject secret/provider-shaped keys and non-scalar values
    ...
```

All identity receipts, snapshots, observations, and drill results should use explicit typed fields plus sanitized scalar detail. Never place raw KIS bodies in these models.

---

### `trading_bot/soak_compat.py` (provider compatibility probe, paginated request-response / fixture export)

**Analogs:** query-only methods in `trading_bot/kis_order.py` and conflict-safe replay fixture identity checks.

Copy the adapter's bounded GET retry/rate-limit behavior and the replay fixtures' stable-content conflict semantics. Strengthen both analogs by making mutation capability absent, attaching explicit `SYNTHETIC` versus `KIS_OBSERVED` provenance, requiring complete pagination before acceptance, exporting allowlisted normalized shapes only, and validating the canonical three-path topology without opening any store during probe-only operation.

---

### `trading_bot/soak_config.py` (config / composition guard, request-response)

**Analog:** `trading_bot/config.py`, with the fail-closed result vocabulary from `trading_bot/preflight.py`.

Create an independent `BaseSettings` type, copying the credential-free/narrow settings form rather than subclassing or wrapping `Settings`. Its field graph must not contain `kis_real`, `trading_mode`, or `confirm_real_trading`.

**Narrow settings type** (`trading_bot/config.py:13-22`, `43-50`):

```python
class ReportSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_nested_delimiter="__",
        extra="ignore",
    )
    audit_db_path: Path = Path("./data/audit.db")

class KisCredentialGroup(BaseModel):
    domain: str
    app_key: SecretStr
    app_secret: SecretStr
    tr_id_profile: str
    label: str
```

The identity receipt renderer should copy the allowlisted-banner style, but persist `target`, sanitized domain class, account suffix, accepted TR profile version, campaign ID, and mock-isolation policy version rather than printing generic settings.

**Allowlisted output only** (`trading_bot/config.py:232-246`):

```python
def startup_banner(settings: Settings) -> str:
    active_kis = settings.active_kis
    return "\n".join((
        "Trading bot startup safety",
        f"Trading mode: {settings.trading_mode.value}",
        f"KIS environment: {active_kis.label}",
        "Secrets: REDACTED",
    ))
```

Return a typed PASS/BLOCK/UNKNOWN result with bounded scalar facts like `PreflightCheck`, and fail mutation on both BLOCK and UNKNOWN.

**Fail-closed normalized facts** (`trading_bot/preflight.py:74-93`, `111-116`):

```python
@dataclass(frozen=True)
class PreflightCheck:
    code: PreflightCode
    state: PreflightState
    facts: Mapping[str, Scalar]
    stops_run: bool

def _read(reader):
    try:
        return reader(), True
    except Exception:
        return None, False  # raw exception/provider text does not cross the boundary
```

---

### `trading_bot/kis_order.py` (provider / adapter, paginated request-response)

**Analog:** the existing `KisOrderAdapter`; extend its query leg and preserve its POST boundary.

The current structure is reusable, but the existing mock constants and payload parsing are explicitly not an implementation truth for Phase 9. Replace/version the profile only after authenticated characterization. Current code selects legacy mock IDs (`trading_bot/kis_order.py:148-164`) and reads one `body["output"]` (`432-446`), while Phase 9 research requires profile versioning, account/date/filter parameters, continuation headers/keys, `output1` holdings plus `output2` summary, page caps, loop detection, and explicit `INCOMPLETE` on any pagination/parse failure.

**Bounded retry belongs only to GET/query legs** (`trading_bot/kis_order.py:347-390`):

```python
@retry(
    reraise=True,
    stop=stop_after_attempt(self._max_retries),
    wait=wait_fixed(self._retry_backoff_seconds),
    retry=retry_if_exception_type(_TransientOrderQueryError),
)
def _attempt():
    return self._query_request(path=path, tr_id=tr_id, params=params, token=token)
```

Build a page-envelope result that retains normalized rows, page count, continuation/completeness state, and allowlisted response-profile facts. Rate-limit every continuation page through the existing `_respect_min_interval` mechanism (`518-528`).

**Never decorate or loop the order POST** (`trading_bot/kis_order.py:243-287`):

```python
def place_order_cash(...):
    # deliberately has no tenacity retry wrapper
    ...
    try:
        response = self._client.post(...)
    except Exception as exc:
        raise KisOrderError(f"order POST failed: {type(exc).__name__}") from exc
```

The compatibility probe must be read-only by default; the one proof order is an explicit operator checkpoint, not an automated test or hidden startup side effect.

---

### `trading_bot/soak_store.py` (store, CRUD / append-only file-I/O)

**Analog:** `trading_bot/sqlite_audit.py`.

Use additive versioned migration, one explicit transaction, rollback on every failure, foreign keys, uniqueness for one designated run per campaign/date, and immediate commit for externally meaningful evidence.

**Atomic additive migration** (`trading_bot/sqlite_audit.py:105-160`):

```python
def migrate(conn, *, fail_after_step=None):
    version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if version > SCHEMA_VERSION:
        raise RuntimeError(...)
    try:
        conn.execute("BEGIN IMMEDIATE")
        # CREATE/ALTER additive schema
        conn.execute("PRAGMA user_version = 3")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
```

Recommended campaign tables should separate immutable campaign policy, designated day/run facts, campaign events, broker snapshots/observations, touched records, comparison verdicts, ticker freezes, and drill references. Use constraints rather than application convention for immutable target/budget, one designated run per date, stable cross-IDs, and terminal failure. Observations and events append; only narrowly defined state transitions update latch/current-state rows.

**Validate before append and commit immediately** (`trading_bot/sqlite_audit.py:275-292`):

```python
def append_order_event(conn, event):
    OrderEventType(event.event_type)
    detail = sanitize_detail(event.detail)
    cursor = conn.execute("INSERT INTO order_events ...", (..., json.dumps(detail), ...))
    conn.commit()
    return int(cursor.lastrowid)
```

**Single terminal transition guard** (`trading_bot/sqlite_audit.py:221-239`):

```python
cursor = conn.execute(
    "UPDATE runs SET status = ?, finished_at = ? WHERE run_id = ? AND status = ?",
    (..., RunStatus.RUNNING.value),
)
if cursor.rowcount != 1:
    conn.rollback()
    raise ValueError("run is missing or already terminal")
conn.commit()
```

Use the same compare-and-transition shape for campaign permanent failure and drill terminal verdicts. Never provide a `FAILED -> ACTIVE` path.

---

### `trading_bot/soak_reconcile.py` (service, request-response / transform / batch)

**Analog:** `trading_bot/kis_broker.py`, especially append-before-mutation and later-observer attribution.

**Persist attempted submission before the single POST; ambiguity is terminal for that attempt** (`trading_bot/kis_broker.py:190-214`):

```python
self._emit(OrderEvent(
    event_type=OrderEventType.SUBMISSION_ATTEMPTED,
    submission_id=submission_id,
    ...,
))
try:
    result = self._order_adapter.place_order_cash(...)
except Exception as exc:
    self._emit(OrderEvent(
        event_type=OrderEventType.SUBMISSION_AMBIGUOUS,
        submission_id=submission_id,
        broker_status="ACK_UNKNOWN",
        detail={"error_type": type(exc).__name__},
    ))
    raise AmbiguousSubmissionError(...) from None
```

**Later truth links origin and observer without rewriting the origin** (`trading_bot/kis_broker.py:248-267`):

```python
def reconcile_order(*, order_intent_id, origin_run_id, observer_run_id, ...):
    fill = self._read_fill_status(...)
    self._emit(OrderEvent(
        order_intent_id=order_intent_id,
        origin_run_id=origin_run_id,
        observer_run_id=observer_run_id,
        event_type=OrderEventType.BROKER_OBSERVED,
        ...,
    ))
```

Phase 9 should generalize this into a snapshot service that:

- queries every page of orders/fills and balance;
- projects only campaign-touched orders, holdings, and relevant account summary;
- appends every ambiguity-window observation;
- returns exactly `NO_MATCH_CONFIRMED`, `ONE_MATCH_DETERMINATE`, or `MULTIPLE_OR_INCONCLUSIVE`;
- never submits from a reconciliation branch;
- reconstructs ticker freezes from durable evidence on resume;
- distinguishes determinate partial/no-fill evidence from terminal order state.

The current `_find_existing_order` first-match loop (`trading_bot/kis_broker.py:284-307`) is only a starting parser pattern; do not copy its “return first match” cardinality into Phase 9.

---

### `trading_bot/soak_campaign.py` (service / state machine, event-driven / CRUD)

**Analogs:** pure injected policy in `trading_bot/market_cycle.py` and guarded transitions in `trading_bot/sqlite_audit.py`.

Eligibility must consume observed calendar evidence, not weekday arithmetic. Unknown provider state fails closed.

**Injected calendar and explicit unknown state** (`trading_bot/market_cycle.py:67-102`):

```python
class MarketCyclePolicy:
    def __init__(self, calendar: KRXCalendarProvider, ...):
        self._calendar = calendar

    def classify(self, observed_at):
        try:
            trading_day = self._calendar.is_trading_day(kst.date())
        except Exception:
            return self._unknown(kst, "calendar unavailable")
        if trading_day is None:
            return self._unknown(kst, "calendar unavailable")
        ...
```

Derive day credit only after the designated run is terminal and report/reconciliation evidence is complete. HOLD/zero-order can credit; preview, dry-run, drill, rerun, closed day, and incomplete evidence cannot. Keep availability consumption, credited-day count, safety latch, and drill coverage as independent dimensions.

---

### `trading_bot/soak_drills.py` (service / registry, event-driven)

**Analog:** injected collaborators in `trading_bot/cli.py`, but reachable only from the drill composition root.

Use one enum-keyed registry of immutable fault specifications: fault name, one injection boundary, expected containment, required reconciliation, recovery action, and prohibited-action assertions. Ordinary soak runtime constructors must not accept the registry, fault enum, environment switches, or generic injection flags.

**Dependency-injected orchestration seam** (`trading_bot/cli.py:451-468`, `483-514`):

```python
def run_cycle(*, data_source=None, llm_provider=None, broker=None,
              audit_conn=None, notifier=None, run_cycle=None, ...):
    fully_injected = all(
        item is not None
        for item in (data_source, llm_provider, broker, audit_conn, notifier)
    )
    ...
    cycle_fn = run_cycle or _run_llm_cycle
```

Copy the injection mechanics, not the public signature: `bot soak drill <fault>` constructs one faulting port internally after the controller contract is durable. `bot soak run` receives only non-faulting production collaborators.

---

### `trading_bot/soak_controller.py` (store / controller, append-only file-I/O)

**Analog:** `trading_bot/sqlite_audit.py`, with stronger initialization than the primary audit connection.

Copy explicit transactions/rollback and immediate commits, but use a separate resolved path and separate connection, verify that controller and primary audit paths cannot alias, verify `PRAGMA journal_mode=WAL` returned `wal`, set `PRAGMA synchronous=FULL`, commit and read back the drill contract before enabling injection, and expose `integrity_check`/restart reads.

The existing connection pattern (`trading_bot/sqlite_audit.py:163-171`) is the minimum baseline:

```python
conn = sqlite3.connect(str(db_path))
conn.execute("PRAGMA foreign_keys=ON")
conn.execute("PRAGMA journal_mode=WAL")
migrate(conn)
```

Phase 9 must additionally check the WAL result and set FULL synchronous. Do not use `ATTACH`; do not copy only the `.db` file while WAL is active.

---

### `trading_bot/soak_reporting.py` (read-only projection, CRUD-read / transform)

**Analog:** `trading_bot/reporting.py`.

Open the database strictly read-only, set query-only mode, validate exact schema capabilities, load a stable transaction snapshot, and derive verdicts without mutation.

**Read-only validated repository** (`trading_bot/reporting.py:274-337`):

```python
connection = sqlite3.connect(
    f"{self._path.as_uri()}?mode=ro", uri=True, isolation_level=None
)
connection.row_factory = sqlite3.Row
connection.execute("PRAGMA query_only=ON")
...
connection.execute("BEGIN")
sections = tuple(...)
connection.commit()
```

**Explicit denominators that reconcile** (`trading_bot/reporting.py:503-519`):

```python
complete = sum(row.ticker_state is EvidenceState.COMPLETE for row in candidates)
incomplete = sum(row.ticker_state is EvidenceState.INCOMPLETE for row in candidates)
unknown = sum(row.ticker_state is EvidenceState.UNKNOWN for row in candidates)
if complete + incomplete + unknown != total:
    raise ValueError("report evidence states do not reconcile")
```

Campaign reports should show credited/target eligible days, availability failures/budget, permanent safety status, designated vs non-credit runs, reconciliation completeness, active ticker freezes, and drill matrix. Controlled and observed evidence need separate counts and denominators; never aggregate them into one “faults passed” number.

---

### `trading_bot/cli.py` (controller / route, request-response)

**Analog:** existing nested `report` app registration and command wrappers.

Register a dedicated `soak_app` beside `report_app`, then expose `start`, `run`, `resume`, `status`, and `drill`. Keep each Typer handler thin: validate arguments, construct the mock-only or drill-only runtime, delegate to service, render bounded output, and map known failures to non-zero exits.

**Sub-app registration** (`trading_bot/cli.py:59-60`):

```python
app = typer.Typer(no_args_is_help=True, help="Manual stock-trading bot operator CLI.")
app.add_typer(report_app, name="report")
```

**Fail before mutation, then construct dependencies** (`trading_bot/cli.py:471-519`):

```python
resolved_settings = settings or Settings()
print(startup_banner(resolved_settings))
...
if not resolved_preflight.global_executable:
    raise SystemExit("preflight blocked: " + ",".join(blocking_codes))
...
resolved_run_id = run_id or uuid.uuid4().hex
_ensure_audit_schema(resolved_audit_conn)
sqlite_audit.recover_abandoned_runs(resolved_audit_conn)
sqlite_audit.start_run(...)
```

For soak, replace the generic banner/preflight with the full persisted identity receipt and authenticated reconciliation gates. On resume, reconcile before any campaign mutation and never delegate to a path that can blindly replay a POST.

---

### `docs/operator-runbook.md` (documentation, manual workflow)

**Analog:** existing command sequence and prohibited-retry guidance in the same file.

Add an operator-verifiable Phase 9 section in actual command order: authenticated compatibility probe, campaign start, designated daily run, resume, status/report review, each named drill, ambiguity/freeze triage, controller/audit recovery, and completion criteria. Clearly label the one operator-run mock proof order and the 20 eligible-day campaign as real external checkpoints that automated tests cannot substitute. Preserve explicit exclusions: no scheduling, no promotion, no profitability claim, and no automatic resubmission/policy mutation.

## Test Pattern Assignments

### `tests/test_soak_config.py`

Copy `monkeypatch`-driven environment isolation and exhaustive secret-leak assertions from `tests/test_config.py:111-154`. Add structural assertions that a `SoakSettings` instance/model schema has no real credential, real account, mode selector, or real confirmation field—not merely that mock wins selection.

```python
with pytest.raises(ValidationError) as exc_info:
    Settings()
diagnostic = str(exc_info.value)
assert_no_secret_leaked(diagnostic)
```

### `tests/test_soak_store.py`

Copy migration idempotency/rollback/reopen and append-order tests from `tests/test_sqlite_audit.py:183-260`, `347-397`. Add constraints for immutable target/budget, unique `(campaign_id, trading_date)`, append-only observations, and permanent failure transition. Use a second SQLite connection to prove commits are externally visible.

```python
with pytest.raises(RuntimeError, match="injected"):
    sqlite_audit.migrate(conn, fail_after_step="runs")
assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
reopened = sqlite_audit.connect(path)
```

### `tests/test_soak_reconcile.py`

Copy queued fake HTTP responses and exact request/header assertions from `tests/test_kis_order.py:101-139`, but build two-plus-page fixtures and verify continuation keys, page caps, repeat-token detection, `output1`/`output2`, campaign filtering, and `INCOMPLETE` failure. Copy ambiguity/later-observer and partial-fill assertions from `tests/test_kis_broker.py:190-218`, `246-276`.

```python
with pytest.raises(AmbiguousSubmissionError):
    broker.place_order(...)
assert adapter.post_attempts == 1
...
assert broker.last_reconciliation.remaining_qty == 3
```

### `tests/test_soak_campaign.py`

Use table-driven policy tests like the lifecycle matrix in `tests/test_reporting.py:211-220`, plus real SQLite state transitions. Cover HOLD/zero-order credit, closed/unknown dates, reruns, drill/dry-run exclusion, availability budget without clean-streak reset, budget exceed failure, and irreversibility of every D-09 breach.

### `tests/test_soak_drills.py`

Copy the ordered event-sequence assertion from `tests/test_kis_broker.py:168-187` and assert controller `PREPARED/COMMITTED` evidence precedes exactly one injection. For interruption/audit-failure cases, use a subprocess that exits after the durable checkpoint and a second process that runs resume; exception-only simulation is insufficient. Assert zero order POSTs except at the explicitly selected accepted-then-timeout boundary, and one POST there.

### `tests/test_soak_cli.py`

Copy `CliRunner` discovery and runtime-not-built guards from `tests/test_cli.py:267-282`, `353-364`. Verify one `soak` top-level group with exactly `start`, `run`, `resume`, `status`, `drill`; isolation/reconciliation failure must leave campaign/order tables unchanged except the allowed sanitized `MOCK_ISOLATION_BLOCKED` event when audit health is known.

```python
monkeypatch.setattr(
    cli, "build_runtime",
    lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("runtime built")),
)
invoked = CliRunner().invoke(cli.app, ["status"])
```

### `tests/test_soak_reporting.py`

Copy byte-for-byte non-mutation, `mode=ro`, `query_only`, exact schema-version, stable-transaction, and denominator checks from `tests/test_reporting.py`. Strengthen the analog by opening `primary_audit_db_path`, `soak_db_path`, and `controller_db_path` independently, rejecting every alias pair, resolving all cross-IDs to primary evidence, and treating missing/contradictory references as UNKNOWN/FAIL.

### `tests/test_operator_runbook.py`

Copy Phase 8's mechanically tested command-order and prohibited-action documentation style. Strengthen it by deriving the complete fault command set from canonical `FaultName`/`FAULT_REGISTRY`, checking read-only profile before the later durable proof-order checkpoint, and asserting separate backup/recovery instructions for all three database owners.

### Sanitized authenticated mock fixtures

Follow `_FakeClient` response-queue tests, but store only allowlisted normalized field/value shapes and continuation metadata. Fixtures must not contain app keys, tokens, full account numbers, raw headers, or unrelated holdings/orders. Synthetic fixtures verify code; they do not count as `KIS_OBSERVED` campaign evidence.

## Shared Patterns

### Fail closed on unknown external state

**Sources:** `trading_bot/preflight.py:119-209`, `trading_bot/market_cycle.py:74-102`

Apply to identity, audit health, KRX eligibility, pagination completeness, broker comparison, and restart reconstruction. Provider exceptions become stable UNKNOWN/BLOCK codes with sanitized facts, never permissive defaults or raw error payloads.

### Append before mutation; append later truth

**Sources:** `trading_bot/kis_broker.py:123-150`, `190-245`, `248-267`; `trading_bot/sqlite_audit.py:275-292`

Persist intent/attempt before order mutation, persist ambiguity immediately, and append broker observations with distinct origin/observer IDs. Never overwrite the originating event and never infer retry permission from a local client reference.

### Query retry versus POST no-retry

**Sources:** `trading_bot/kis_order.py:243-287`, `347-390`; `tests/test_kis_order.py:204-226`

Tenacity and rate limiting are permitted for idempotent authenticated queries. The order-cash POST remains exactly once; timeout becomes durable ambiguity plus freeze/reconciliation.

### Read-only reporting is demonstrably non-mutating

**Sources:** `trading_bot/reporting.py:274-337`; `tests/test_reporting.py:145-203`

Open SQLite with `mode=ro` and `query_only=ON`; tests compare database bytes before and after reporting. Report counts must reconcile and provenance classes remain separate.

### Evidence vocabulary and Korean operator explanation

**Sources:** `trading_bot/audit_models.py:13-82`; `trading_bot/reporting.py:152-164`, `829-865`; `trading_bot/preflight.py:234-242`

Persist stable English codes, render bounded Korean explanations and allowlisted facts at the CLI/report edge, and preserve UNKNOWN as a first-class state.

## No Analog Found

There is no existing implementation that proves all of the following together: structurally mock-only KIS composition, complete paginated account truth, immutable eligible-day campaign accounting, independent drill-controller durability, or process-kill restart reconstruction. The files above have strong local pattern analogs, but the planner must use `09-RESEARCH.md` for these new contracts rather than claiming an existing implementation already satisfies them.

In particular:

| New Contract | Why Existing Code Is Insufficient |
|---|---|
| Authenticated mock TR profile/fixtures | Current mock TR IDs and query payload/response assumptions diverge from current official examples. |
| Paginated broker snapshot completeness | Current adapter parses one `output` value and has no continuation envelope. |
| Independent controller journal | Existing audit DB is the component under test during audit-failure drills. |
| Subprocess interruption/restart drill | Existing tests simulate exceptions/in-process lifecycle recovery, not permanent process termination around injection boundaries. |

## Planner Guardrails

1. Put compatibility code first and authenticated read-only KIS profile acceptance immediately after it; implement durable storage/reconciliation next, and only then run the single proof order before campaigns.
2. Keep `SoakSettings` independent from `Settings`; composition-level unreachability is stronger than checking `trading_mode == mock`.
3. Do not expose fault arguments or ports on ordinary soak commands.
4. Keep controller and primary audit databases physically and logically separate; do not use SQLite `ATTACH`.
5. Do not grant day credit until terminal daily report and final authenticated reconciliation are complete.
6. Do not let determinate partial/no-fill evidence clear a still-open ticker freeze.
7. Automated/synthetic tests do not satisfy authenticated `KIS_OBSERVED` evidence or the 20 eligible-day campaign.

## Metadata

**Analog search scope:** `trading_bot/`, `tests/`, `docs/operator-runbook.md`
**Primary source files read:** `config.py`, `audit_models.py`, `sqlite_audit.py`, `kis_order.py`, `kis_broker.py`, `market_cycle.py`, `preflight.py`, `cli.py`, `reporting.py`
**Test patterns sampled:** `test_config.py`, `test_sqlite_audit.py`, `test_kis_order.py`, `test_kis_broker.py`, `test_cli.py`, `test_reporting.py`
**Pattern extraction date:** 2026-07-16
