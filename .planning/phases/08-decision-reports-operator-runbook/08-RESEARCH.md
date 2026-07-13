# Phase 8: Decision Reports & Operator Runbook - Research

**Researched:** 2026-07-13
**Domain:** Read-only SQLite evidence reporting, replay-result aggregation, operator preflight, and failure runbooks
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

### Daily report shape
- **D-01:** The default daily report shows a concise run/day summary first, followed by full detail for every candidate ticker; detail is not hidden behind an extra flag.
- **D-02:** Group ticker detail by `screen` or `run` invocation and retain actual processing order within each invocation so evidence remains traceable to its source run.
- **D-03:** Display no-trade and failure reasons as the stable machine-readable reason code together with a Korean human-readable explanation.
- **D-04:** Print reports to the terminal by default. When `--output` is supplied, save the same human-readable report to a file.

### Period and replay summaries
- **D-05:** Expose distinct Typer subcommands: `bot report daily`, `bot report period`, and `bot report replay`.
- **D-06:** Period selection uses an inclusive start/end range over the recorded KST trading date (`trading_date_kst`), not UTC invocation timestamps.
- **D-07:** Show total and determinate denominators side by side. Complete, incomplete, and unknown states remain explicit and must reconcile to the detail rows rather than disappearing from statistics.
- **D-08:** Show every replay stable result ID and verification status separately before aggregation. Aggregate only results whose schema, policy, and scenario basis are compatible; separate incompatible results and explain why they were not combined.
- **D-09:** Every replay report retains the statement that replay validates decision-policy paths and does not estimate profitability or investment performance.

### Daily operating sequence
- **D-10:** The documented default KST schedule is: 08:50 `bot status` preflight, 09:05 `bot screen` preview, 09:10 `bot run`, then immediate `bot report daily` review. These are manual operator steps, not scheduled automation.
- **D-11:** If mock-target identity, audit writability/evidence health, KRX trading-day/session state, or unresolved-order state cannot be confirmed, abort `bot run`. Read-only status and historical report access remain available.
- **D-12:** The 09:05 screen is a preview. `bot run` performs a fresh screen at execution time; the report makes differences between preview candidates and run candidates visible.
- **D-13:** The daily procedure is complete only after the run is terminal, every attempted ticker has one terminal outcome, order/no-trade evidence has been reviewed, and any ambiguous order is either absent or formally transferred into its triage procedure. Notification failure requires direct report review.

### Failure triage playbooks
- **D-14:** Organize the runbook as a per-failure response table plus stepwise checklists. Every entry states symptoms/reason codes, whether trading stops, evidence or commands to inspect, prohibited actions, the safe next action, and the resolution criterion.
- **D-15:** Never automatically rerun after data, API, or LLM failure. After confirming that audit evidence is healthy and no order may have been submitted, the operator may start a new run with a new `run_id` linked to the earlier run through `parent_run_id`.
- **D-16:** For ambiguous or duplicate orders, freeze new orders for the affected ticker, establish broker truth from KIS order/open-order/fill evidence, append reconciliation evidence, and resume only after the state is determinate. A duplicate is linked to the existing order and is never resubmitted.
- **D-17:** Audit persistence or evidence-integrity failure stops new trading. Notification failure remains fail-soft, but must be visible in the CLI report and manually reviewed before the daily procedure is considered complete.

### the agent's Discretion
- Choose the internal report models, query/service boundaries, SQL details, terminal table/wrapping style, output file extension, and exact CLI option names consistent with the existing synchronous Typer architecture.
- Define the Korean explanation catalog and replay-compatibility comparison mechanics, provided stable source codes/identities remain visible and all locked denominators and incompatibility reasons are explicit.

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within Phase 8. KIS mock soak/fault execution remains Phase 9; calibration and promotion readiness remain Phase 10; scheduling and a web dashboard remain future scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REP-01 | Operator can generate a daily decision report from SQLite showing candidates, signal decisions, confidence, order outcomes, and no-trade reasons. | A read-only evidence repository, typed report projection, stable processing order, Korean reason catalog, and one-render terminal/file path directly cover this behavior. [VERIFIED: `.planning/REQUIREMENTS.md`, `trading_bot/sqlite_audit.py`, `trading_bot/audit_models.py`] |
| REP-02 | Operator can generate period and replay summaries with explicit denominators, incomplete or unknown states, execution target, and reconciliation status. | Explicit evidence-state classification, reconciliation reduction over append-only events, inclusive KST-date queries, and integrity-checked replay compatibility groups cover the required fields without suppressing unknowns. [VERIFIED: `.planning/REQUIREMENTS.md`, `trading_bot/replay.py`, `trading_bot/sqlite_audit.py`] |
| RUN-01 | Operator can follow a runbook for `bot status`, `bot screen`, `bot run`, and report review at fixed market-session times. | A shared preflight result used by `status` and the mutable run boundary plus a command-accurate Korean runbook makes the 08:50/09:05/09:10 procedure executable and testable. [VERIFIED: `08-CONTEXT.md`, `trading_bot/cli.py`] |
| RUN-02 | Operator can follow documented failure triage for stale data, API failure, timeout, ambiguous order, duplicate order, notification failure, and audit failure. | Stable reason/event vocabularies already cover most failure classes; an append-only notification result closes the only material persistence gap, and a required runbook matrix can bind every failure to stop rules and resolution evidence. [VERIFIED: `trading_bot/audit_models.py`, `trading_bot/kis_broker.py`, `trading_bot/cli.py`] |
</phase_requirements>

## Summary

Phase 8 should be planned as a read-model and operator-safety phase, not as a new trading pipeline. The existing `runs`, `decisions`, `ticker_outcomes`, and append-only `order_events` tables already contain the durable attribution needed for daily and period reports, while replay JSON already contains stable result identity, manifest inputs, explicit funnel denominators, verification checks, and the non-profitability disclaimer. Report commands should query those sources without creating runs or changing policy, project them into immutable report models, and render one deterministic UTF-8 text document that is both printed and optionally saved. [VERIFIED: `trading_bot/sqlite_audit.py`, `trading_bot/replay.py`, `trading_bot/cli.py`]

The main implementation gap is notification evidence. `_safe_send()` returns a boolean, but both call sites discard it and SQLite has no notification record, so a later report cannot distinguish notification success from failure or disabled delivery. D-17 therefore requires an additive schema migration and normalized append-only notification-attempt evidence before reporting can truthfully expose the state. Audit failure itself cannot be written reliably to a failing database, so it belongs in shared preflight/CLI failure behavior and the runbook, not in fabricated audit rows. [VERIFIED: `trading_bot/cli.py:229-233`, `trading_bot/cli.py:484`, `trading_bot/cli.py:507-513`, `trading_bot/sqlite_audit.py`]

The current `status` command is only a cash/mode snapshot and does not prove mock identity, audit health, KRX session state, or unresolved-order safety. Plan a shared preflight service whose typed checks drive both operator-readable `bot status` output and the `bot run` fail-closed decision. Keep historical reports independently available through a read-only SQLite connection even when preflight fails. [VERIFIED: `trading_bot/cli.py:697-706`, `08-CONTEXT.md` D-11]

**Primary recommendation:** Build Phase 8 in four seams: evidence/read models (including notification evidence), daily/period reporting, integrity-checked replay aggregation, then shared preflight plus a command-accurate Korean operator runbook. [VERIFIED: codebase and locked Phase 8 decisions]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Daily/period evidence selection | Database / Storage | API / Backend | SQLite owns durable facts; a read-only repository performs parameterized selection and integrity classification. [VERIFIED: `trading_bot/sqlite_audit.py`] |
| Report aggregation and reconciliation | API / Backend | Database / Storage | Python report services reduce normalized rows and append-only events without mutating the source database. [VERIFIED: synchronous service patterns in `trading_bot/replay.py`] |
| Human-readable CLI rendering | API / Backend | — | Typer is the local operator entry point; there is no browser or server tier. [VERIFIED: `trading_bot/cli.py`, `pyproject.toml`] |
| Replay file validation and compatibility | API / Backend | Database / Storage | Local JSON is untrusted input; the service validates structure and stable identity before aggregating in memory. [VERIFIED: `trading_bot/replay.py`] |
| Preflight and run abort decision | API / Backend | Database / Storage | The same typed checks must be shown by `status` and enforced before `run`; audit and unresolved-order checks read SQLite. [VERIFIED: `08-CONTEXT.md` D-11] |
| Operator procedure and triage | Documentation / Static | API / Backend | The runbook is static documentation, but every command, code, and resolution criterion must map to implemented CLI/evidence behavior. [VERIFIED: REP/RUN requirements and `08-CONTEXT.md`] |

## Project Constraints (from AGENTS.md)

- Use Python and preserve the Korea-only `pykrx`/KIS domain; do not introduce a non-Python reporting path. [VERIFIED: `AGENTS.md`]
- Preserve strict machine-checkable LLM signal handling; unparseable output fails safe and must never become a trade. Reports consume evidence and do not alter that gate. [VERIFIED: `AGENTS.md`]
- Keep KIS mock as the first target and real-money promotion deliberate and separately gated. [VERIFIED: `AGENTS.md`]
- Preserve the BUY execution threshold `confidence >= 0.8`; report/calibration code must not mutate it. [VERIFIED: `AGENTS.md`]
- Use the existing stack: stdlib SQLite, synchronous Typer CLI, structured audit evidence, and current Python tests; no scheduler is part of v1. [VERIFIED: `AGENTS.md`, `pyproject.toml`]
- Preserve immediate, normalized, sanitized audit evidence; do not persist raw provider responses, credentials, tokens, or untrusted instructions. [VERIFIED: `AGENTS.md`, `trading_bot/audit_models.py`]
- Do not use unmaintained `mojito2`, default TA-Lib, mainline `pandas-ta`, assistant-prefill JSON forcing, hardcoded secrets, or automatic scheduling. None is needed by Phase 8. [VERIFIED: `AGENTS.md`]
- Repository edits must occur through a GSD workflow; this research was initiated by `$gsd-plan-phase 8`. [VERIFIED: `AGENTS.md`]
- Follow existing code patterns because standalone conventions and architecture maps are not yet established. [VERIFIED: `AGENTS.md`]

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | Project `>=3.10`; available `3.14.3` | Typed report models, aggregation, rendering, filesystem safety | Required project runtime; all existing pipelines are synchronous Python. [VERIFIED: `pyproject.toml`, local version probe] |
| `sqlite3` | stdlib; available SQLite `3.51.3` | Read-only report snapshots, parameterized queries, schema introspection | Existing audit persistence uses stdlib SQLite; Python officially supports placeholders, row factories, and URI `mode=ro`. [CITED: https://docs.python.org/3.10/library/sqlite3.html] |
| `typer` | `0.26.8` | `report daily`, `report period`, `report replay`, and status output | Already pinned and used by the operator CLI; official nested command groups use `app.add_typer()`. [VERIFIED: `pyproject.toml`, local import probe] [CITED: https://typer.tiangolo.com/tutorial/subcommands/name-and-help/] |
| `dataclasses` / `enum` | stdlib | Immutable report, evidence-state, reconciliation, compatibility, and preflight models | Matches existing audit/replay contracts and avoids a new dependency. [VERIFIED: `trading_bot/audit_models.py`, `trading_bot/replay.py`] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `json` / `hashlib` | stdlib | Parse replay files, canonicalize compatibility inputs, verify embedded result IDs | Reuse the same canonical JSON and SHA-256 identity semantics already shipped in replay. [VERIFIED: `trading_bot/replay.py`] |
| `pathlib`, `tempfile`, `os.replace` | stdlib | Safe UTF-8 report output | Reuse the existing atomic output and symlink/path checks rather than direct unguarded writes. [VERIFIED: `trading_bot/replay.py:write_replay_result`] |
| `pytest` + `typer.testing.CliRunner` | `8.4.2` + pinned Typer | Unit/integration tests for repositories, renderers, subcommands, output files, preflight, and runbook contract | Existing tests already inject collaborators and run CLI commands deterministically. [VERIFIED: `tests/test_cli.py`, local import probe] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Plain deterministic text renderer | Rich tables | Typer may expose Rich transitively, but Rich is not a direct project dependency and terminal-width behavior complicates byte-identical file output. Keep a plain renderer for predictable Korean text and exact tests. [VERIFIED: `pyproject.toml`; derived recommendation] |
| Python aggregation over normalized rows | Large multi-join SQL aggregates | Large joins can multiply decision/order-event rows and hide cardinality corruption. Fetch ordered normalized records with bounded queries, group in Python, and surface anomalies explicitly. [VERIFIED: schema relationships in `trading_bot/sqlite_audit.py`; derived recommendation] |
| New reporting framework | Existing stdlib/Typer stack | A framework would add dependency and output variability without solving the project-specific evidence semantics. [VERIFIED: current stack and Phase 8 scope] |

**Installation:** No new package installation is required for Phase 8. [VERIFIED: `pyproject.toml`, local environment probe]

## Package Legitimacy Audit

Not applicable. The recommended design installs no external packages and uses only pinned project dependencies plus the Python standard library. [VERIFIED: Standard Stack above]

## Architecture Patterns

### System Architecture Diagram

```text
SQLite audit.db (immutable facts) ──read-only snapshot──┐
                                                       ├─> evidence repository
Replay result JSON files ──validate + verify result ID─┘         │
                                                                 v
                                              immutable report models
                                                │              │
                                    classify integrity      compatibility groups
                                    + reconciliation        + explicit funnels
                                                └──────┬───────┘
                                                       v
                                             deterministic text renderer
                                                │              │
                                          typer.echo      atomic UTF-8 file

Settings + KRX observation + audit health + unresolved intents
                              │
                              v
                     shared typed preflight
                       │              │
                 `bot status`     `bot run` gate
                       │              ├─ PASS -> existing run pipeline
                       │              └─ BLOCK/UNKNOWN -> no run
                       v
                operator runbook and triage checklists
```

The report path is read-only and must never call `build_runtime()`, create a run, reconcile a broker, or mutate settings. The preflight path may inspect live/session state for `status` and `run`, but historical reports remain available when it fails. [VERIFIED: `08-CONTEXT.md` D-11 and existing offline replay boundary]

### Recommended Project Structure

```text
trading_bot/
├── reporting.py          # report models, SQLite repository, aggregation, renderers
├── report_cli.py         # nested Typer report app and CLI-only validation/output
├── preflight.py          # typed checks shared by status and run gate
├── sqlite_audit.py       # additive notification evidence + read-only connection seam
├── audit_models.py       # stable notification/preflight evidence vocabularies
└── cli.py                # register report app; integrate status/run preflight
docs/
└── operator-runbook.md   # Korean daily procedure and failure triage matrix
tests/
├── test_reporting.py
├── test_report_cli.py
├── test_preflight.py
└── test_operator_runbook.py
```

Keep report domain/query/render code out of the already-large `cli.py`; Typer officially supports registering a separately defined sub-application. [CITED: https://typer.tiangolo.com/tutorial/one-file-per-command/] [VERIFIED: `trading_bot/cli.py` size and responsibilities]

### Pattern 1: Read-only snapshot repository

**What:** Open existing audit files with SQLite URI `mode=ro`, set `row_factory = sqlite3.Row`, enable `PRAGMA query_only=ON`, validate `PRAGMA user_version`, and execute all report reads in one explicit read transaction. Never run migrations from a report command. [CITED: https://docs.python.org/3.10/library/sqlite3.html]

**When to use:** Every daily and period report, including when trading preflight is blocked. [VERIFIED: `08-CONTEXT.md` D-11]

**Example:**

```python
# Source: Python sqlite3 official documentation; adapted to this repository.
uri = Path(path).resolve().as_uri() + "?mode=ro"
conn = sqlite3.connect(uri, uri=True)
conn.row_factory = sqlite3.Row
conn.execute("PRAGMA query_only=ON")
conn.execute("BEGIN")
rows = conn.execute(
    "SELECT * FROM runs WHERE trading_date_kst BETWEEN ? AND ? ORDER BY started_at, run_id",
    (start_yyyymmdd, end_yyyymmdd),
).fetchall()
```

Dates are bound parameters, never interpolated SQL. The range is inclusive because SQL `BETWEEN` includes both endpoints and stored dates are fixed-width `YYYYMMDD`. [CITED: https://docs.python.org/3.10/library/sqlite3.html] [VERIFIED: `trading_bot/cli.py` date storage]

### Pattern 2: Fetch normalized rows separately, reduce in Python

**What:** Query runs, ticker outcomes, decisions, notification attempts, and order events separately using stable IDs. Build mappings by `(run_id, ticker)` and `order_intent_id`; detect duplicate decisions, missing outcomes, unknown enum values, and broken origin/observer references instead of allowing joins to multiply or erase them. [VERIFIED: `trading_bot/sqlite_audit.py` schema]

**When to use:** Daily/period detail and denominator calculation. [VERIFIED: REP-01/REP-02]

**Ordering rule:** Order runs by `(started_at, run_id)` and ticker details by `ticker_outcomes.id`. The outcome row is written in actual screen/run processing order, and order-event history is append ordered by `order_events.id`. [VERIFIED: `trading_bot/cli.py:380-487`, `trading_bot/cli.py:647-683`, `tests/test_sqlite_audit.py:210-245`]

### Pattern 3: Explicit evidence state, never inferred completeness

**What:** Give every displayed run/ticker/order a separate `COMPLETE`, `INCOMPLETE`, or `UNKNOWN` evidence state and keep execution target and reconciliation status as independent fields. Recognized terminal status is not enough to claim broker reconciliation; append-only order evidence decides that field. [VERIFIED: `RunStatus`, `TickerOutcome`, and `OrderEvent` contracts]

**When to use:** Every summary numerator/denominator and detail row. [VERIFIED: D-07]

**Recommended rules:**

- `COMPLETED` and `COMPLETED_WITH_ERRORS` are terminal runs; `RUNNING`, `FAILED`, and `INTERRUPTED` remain explicitly incomplete for the daily-procedure completeness denominator. Unknown/missing/legacy lifecycle values are `UNKNOWN`. [VERIFIED: `RunStatus`; derived classification]
- A ticker row with a recognized terminal outcome remains traceable even when decision fields are legitimately null; missing expected decisions, duplicate decisions, invalid JSON, or unrecognized codes become integrity warnings rather than disappearing. [VERIFIED: Phase 6 outcome contract]
- Reconciliation is `DETERMINATE` only when the latest applicable append-only evidence establishes accepted/reconciled/filled/no-fill/duplicate broker truth; `SUBMISSION_AMBIGUOUS` without later broker evidence is `UNKNOWN`, and no order intent is `NOT_APPLICABLE`. [VERIFIED: `OrderEventType`, `trading_bot/kis_broker.py`]
- Every summary prints both `total` and `determinate` and proves that displayed state counts sum to the total. [VERIFIED: D-07]

### Pattern 4: Preview/run pairing without rewriting history

**What:** For each RUN, pair the nearest earlier SCREEN on the same `trading_date_kst` and target. Show `preview_only`, `run_only`, and `shared` candidate sets while retaining both run IDs and each run's original detail order. If no unambiguous earlier preview exists, show pairing as unknown rather than guessing. [VERIFIED: D-02, D-12; derived comparison rule]

**When to use:** Daily report candidate-difference section. [VERIFIED: D-12]

### Pattern 5: Replay integrity then compatibility grouping

**What:** Parse each normalized result document, validate required structure/types, recompute `sha256(canonical_json_bytes(document["evidence"]))`, and require it to equal `result_id` before aggregation. Display every valid stable ID separately. Group unique result IDs only when the top-level result schema, fixture schema version, canonical policy, scenario/OHLCV/raw-signal hashes, evaluation time, and trading-date basis match; report each mismatching field as the incompatibility reason. [VERIFIED: `ReplayResult.normalized_bytes`, `compute_result_id`, D-08; derived compatibility signature]

**When to use:** `bot report replay RESULT...`. [VERIFIED: D-05, D-08]

Repeated paths or duplicate files with the same stable ID must be identified but counted once in aggregate denominators; otherwise a user can double totals without adding evidence. [VERIFIED: stable identity semantics in `trading_bot/replay.py`; derived safeguard]

### Pattern 6: Render once, deliver twice

**What:** Render the complete report to one newline-normalized string. Print that string by default; if `--output` is present, atomically save the exact same UTF-8 bytes and still print the report unless the locked CLI contract is changed. Stable codes remain alongside Korean explanations. [VERIFIED: D-03, D-04; existing atomic pattern in `write_replay_result`]

**When to use:** All three report subcommands. [VERIFIED: D-05]

### Pattern 7: Shared typed preflight

**What:** Represent each required check as `PASS`, `BLOCK`, or `UNKNOWN`, with a stable code, Korean explanation, sanitized evidence, and trading-stop decision. `status` renders all checks; `run` consumes the same result and exits before `start_run` when any required check is not `PASS`. [VERIFIED: D-11]

**Required checks:** mock-target identity, audit integrity/writable transaction, positive KRX trading-day/session observation, and no locally unresolved ambiguous order intent. Audit health should include schema support, `PRAGMA quick_check`, and a rollback-only write transaction so the check does not create evidence rows. [VERIFIED: D-11; derived implementation]

Broker-truth inquiry for mock soak remains Phase 9. Phase 8 preflight must label local-only unresolved-order evidence honestly and must not claim KIS reconciliation that it did not perform. [VERIFIED: phase boundary and Phase 9 roadmap]

### Pattern 8: Persist notification attempts append-only

**What:** Add a normalized notification-attempt contract/table keyed to `run_id`, optional ticker, notification kind, stable delivery status, sanitized failure category, and observed time. Capture the boolean/exception outcome from both immediate-error and final-summary sends without storing the webhook or message body. [VERIFIED: D-17, existing `_safe_send` gap]

**When to use:** Every current `_safe_send` call. Reports show failed/unavailable notifications and require direct review; trading results remain unchanged because notifications are fail-soft. [VERIFIED: `trading_bot/cli.py`, D-17]

### Anti-Patterns to Avoid

- **Reporting through `build_runtime()`:** It constructs live KIS, pykrx, LLM, notifier, and market-cycle collaborators; reports must be usable offline and under failed preflight. Use Settings only to locate the DB, then a read-only connection. [VERIFIED: `trading_bot/cli.py:185-225`]
- **One giant SQL join:** Multiple order events multiply ticker/decision rows and make totals lie. Fetch normalized tables independently and reconcile cardinality in Python. [VERIFIED: schema cardinalities]
- **Treating null as zero or HOLD:** Null is unknown/unavailable evidence, not a negative outcome. [VERIFIED: Phase 6 D-07 and Phase 8 D-07]
- **Using latest timestamp alone for processing order:** Preserve insertion IDs within each run; timestamps can collide and are observational. [VERIFIED: schema IDs and write order]
- **Aggregating replay files before identity verification:** A forged/malformed result can corrupt denominators and compatibility claims. Verify structure and stable ID first. [VERIFIED: replay identity contract]
- **Pairing a screen after a run:** Preview comparison must use an earlier same-day/same-target screen or state that no valid preview exists. [VERIFIED: D-10, D-12]
- **Silent report output overwrite or symlink following:** Reuse the existing atomic/path-safe output posture. [VERIFIED: `write_replay_result`]
- **Document-only preflight:** If `status` and `run` use different logic, the operator can see PASS but still run under different conditions. Share one result object and enforce it at the mutation boundary. [VERIFIED: D-11; derived safety rule]
- **Inventing audit evidence after an audit failure:** If persistence health is unknown, stop new trading and report through stderr/status/runbook; do not pretend a failed sink recorded the failure. [VERIFIED: D-17]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SQL value escaping | String-formatted date/path filters | SQLite placeholders | Officially supported and prevents injection. [CITED: https://docs.python.org/3.10/library/sqlite3.html] |
| Nested command parsing | Manual argv dispatch | Typer sub-app with `app.add_typer()` | Already pinned and officially supported. [CITED: https://typer.tiangolo.com/tutorial/subcommands/name-and-help/] |
| Replay canonicalization/identity | A second JSON serializer or ad hoc hash | `canonical_json_bytes()` and existing SHA-256 evidence identity | Prevents divergent compatibility and integrity semantics. [VERIFIED: `trading_bot/replay.py`] |
| Reason/status vocabulary | Free-text-only classifications | Existing enums plus one Korean explanation catalog | Stable source codes are required and already persisted. [VERIFIED: `trading_bot/audit_models.py`, D-03] |
| Reconciliation history | Mutable “latest order” row | Existing append-only `order_events`, reduced for display | Preserves origin/observer attribution and ambiguity history. [VERIFIED: Phase 6 and `sqlite_audit.py`] |
| Atomic output | Direct writes to arbitrary paths | Existing `NamedTemporaryFile` + `fsync` + `os.replace` safety pattern | Avoids partial output and path/symlink ambiguity. [VERIFIED: `trading_bot/replay.py:write_replay_result`] |

**Key insight:** The hard part is not formatting tables; it is preserving evidence cardinality, provenance, unknown states, and recovery semantics while producing a human view. Reuse the shipped contracts and make integrity anomalies visible. [VERIFIED: REP-01/REP-02 and Phase 6/7 contracts]

## Common Pitfalls

### Pitfall 1: Notification failure is unknowable after process exit

**What goes wrong:** The report claims notification success or omits the state entirely. [VERIFIED: current schema]

**Why it happens:** `_safe_send()` returns a boolean but its result is discarded, and no table stores notification attempts. [VERIFIED: `trading_bot/cli.py`]

**How to avoid:** Add append-only sanitized notification evidence before implementing final report completeness. [VERIFIED: D-17; derived fix]

**Warning signs:** Tests can simulate a failing notifier but cannot recover that fact from SQLite. [VERIFIED: `tests/test_cli.py:test_immediate_error_push`]

### Pitfall 2: Read-only commands accidentally migrate or create a DB

**What goes wrong:** `bot report` changes `user_version`, creates a missing file, or fails because live credentials are unavailable. [VERIFIED: behavior of current `sqlite_audit.connect()` and `build_runtime()`]

**Why it happens:** The current connect seam creates directories, enables WAL, and migrates automatically. [VERIFIED: `trading_bot/sqlite_audit.py:connect`]

**How to avoid:** Add a separate read-only URI connection and schema-capability inspection; never call migrations from report commands. [CITED: https://docs.python.org/3.10/library/sqlite3.html]

**Warning signs:** A report test changes DB bytes/user_version or succeeds on a nonexistent path by creating it. [VERIFIED: derived verification]

### Pitfall 3: Join multiplication corrupts denominators

**What goes wrong:** One ticker with five order events counts as five candidates or decisions. [VERIFIED: one-to-many schema]

**Why it happens:** Joining `ticker_outcomes`, `decisions`, and `order_events` before aggregation multiplies rows. [VERIFIED: `sqlite_audit.py`]

**How to avoid:** Fetch by stable keys, reduce separately, assert expected cardinalities, then derive totals from immutable report rows. [VERIFIED: derived architecture]

**Warning signs:** Summary totals do not equal detail row counts or change when reconciliation events are appended. [VERIFIED: D-07]

### Pitfall 4: Terminal run is confused with complete evidence

**What goes wrong:** A FAILED/INTERRUPTED or legacy run is counted as fully reviewed, or an ambiguous submission is called reconciled. [VERIFIED: lifecycle and order-event distinctions]

**Why it happens:** A single status field is used as a proxy for all evidence dimensions. [VERIFIED: schema]

**How to avoid:** Model run completeness, ticker completeness, execution target, notification delivery, and reconciliation separately. [VERIFIED: REP-02, D-07, D-13]

**Warning signs:** The report has only one “success/failure” column or no unknown count. [VERIFIED: requirements]

### Pitfall 5: Replay aggregation mixes incomparable evidence

**What goes wrong:** Different fixtures/policies/schemas are summed, or a repeated result file doubles counts. [VERIFIED: D-08]

**Why it happens:** Aggregation starts from funnel values without validating identity and compatibility inputs. [VERIFIED: replay JSON structure]

**How to avoid:** Verify each stable ID, deduplicate by ID, calculate a canonical compatibility signature, and list mismatching fields. [VERIFIED: replay identity contract; derived rule]

**Warning signs:** One aggregate is produced for all input files with no incompatibility section. [VERIFIED: D-08]

### Pitfall 6: Preview/run differences are paired incorrectly

**What goes wrong:** A later screen is shown as the preview for an earlier run or cross-target candidates are compared. [VERIFIED: possible from multiple immutable same-day runs]

**Why it happens:** Pairing uses date only. [VERIFIED: runs schema supports many runs per date]

**How to avoid:** Pair nearest earlier SCREEN with same date and target; otherwise show unknown/unpaired. [VERIFIED: D-12; derived rule]

**Warning signs:** Pairing ignores `started_at`, target, or run IDs. [VERIFIED: runs schema]

### Pitfall 7: Status says healthy but run uses different checks

**What goes wrong:** Operator follows the runbook yet `run` starts with unresolved ambiguity or unhealthy audit evidence. [VERIFIED: current status lacks D-11 checks]

**Why it happens:** Status is presentation-only and preflight logic is duplicated or absent. [VERIFIED: `trading_bot/cli.py:697-706`]

**How to avoid:** One typed preflight evaluator, injected dependencies for tests, and mandatory consumption before `start_run`. [VERIFIED: derived from D-11]

**Warning signs:** `status` and `run` tests mock unrelated functions or disagree on blocking codes. [VERIFIED: derived verification]

## Code Examples

### Register the report command group

```python
# Source: official Typer subcommand documentation.
report_app = typer.Typer(no_args_is_help=True, help="감사 증거 보고서")
app.add_typer(report_app, name="report")

@report_app.command("daily")
def daily(...):
    ...
```

[CITED: https://typer.tiangolo.com/tutorial/subcommands/name-and-help/]

### Preserve one renderer for terminal and file

```python
# Source: derived from D-04 and the repository's deterministic replay output pattern.
document = render_daily_report(report)
typer.echo(document, nl=False)
if output is not None:
    write_text_atomically(output, document.encode("utf-8"))
```

[VERIFIED: D-04, `trading_bot/replay.py:write_replay_result`]

### Verify normalized replay identity before reading funnels

```python
# Source: existing ReplayResult.normalized_bytes()/compute_result_id semantics.
document = json.loads(path.read_text(encoding="utf-8"))
expected = hashlib.sha256(canonical_json_bytes(document["evidence"])).hexdigest()
if document.get("result_id") != expected:
    raise ValueError("replay result identity mismatch")
```

[VERIFIED: `trading_bot/replay.py`]

### Reduce latest order evidence without losing history

```python
# Source: existing append-only order event schema and tests.
events_by_intent: dict[str, list[OrderEventRow]] = defaultdict(list)
for event in sorted(events, key=lambda item: item.id):
    events_by_intent[event.order_intent_id].append(event)
latest = {intent: history[-1] for intent, history in events_by_intent.items()}
```

[VERIFIED: `tests/test_sqlite_audit.py:test_unique_ticker_outcome_and_append_only_order_event_order`]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Mutable/minimal run and decision audit | Versioned run lifecycle, terminal ticker outcome, append-only order events | Phase 6 | Phase 8 can build read models rather than redesign execution evidence. [VERIFIED: Phase 6 artifacts and schema v2] |
| Live-provider replay or ad hoc output | Deterministic normalized replay JSON with stable ID and explicit funnel | Phase 7 | Replay reports can validate and aggregate frozen evidence offline. [VERIFIED: Phase 7 artifacts] |
| Minimal status snapshot | Shared, explicit operator preflight | Phase 8 required change | `status` becomes actionable and `run` enforces the same gates. [VERIFIED: D-11 and current status gap] |
| Ephemeral notifier boolean | Persisted sanitized notification attempt | Phase 8 required change | Daily completeness can truthfully expose fail-soft notification failures. [VERIFIED: D-17 and current code gap] |

**Deprecated/outdated:**

- Treating `status` as cash/mode only is insufficient for the locked Phase 8 preflight contract. [VERIFIED: current `status_command`, D-11]
- Treating replay output as a single trusted file is insufficient for Phase 8 multi-result compatibility aggregation. [VERIFIED: current `replay_command`, D-08]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| — | None. Recommendations are derived from locked decisions, current production/test contracts, or cited official documentation. | — | — |

## Open Questions

1. **No unresolved product decision blocks planning.**
   - What we know: The user delegated internal models, SQL, rendering, output extension, CLI option names, Korean catalog, and replay compatibility mechanics. [VERIFIED: Agent Discretion]
   - What's unclear: Exact labels and final file names are implementation choices, not missing product decisions. [VERIFIED: context]
   - Recommendation: Planner should lock the prescriptive defaults in this research and test their observable behavior. [VERIFIED: derived recommendation]

2. **Broker-truth preflight remains intentionally bounded in Phase 8.**
   - What we know: Phase 8 must block on unresolved-order uncertainty, while authenticated KIS mock soak/restart/fault semantics belong to Phase 9. [VERIFIED: Phase 8/9 roadmap boundaries]
   - What's unclear: Full broker inquiry behavior is deferred and must not be fabricated here. [VERIFIED: roadmap]
   - Recommendation: Phase 8 status checks local append-only ambiguity/reconciliation evidence and labels any unconfirmed broker state `UNKNOWN/BLOCK`; Phase 9 later adds authenticated broker-truth checks. [VERIFIED: derived scope-safe recommendation]

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python | All Phase 8 code/tests | ✓ | 3.14.3 (`pyproject` supports >=3.10) | — [VERIFIED: local probe, `pyproject.toml`] |
| SQLite stdlib binding | Daily/period audit reports | ✓ | SQLite 3.51.3 | — [VERIFIED: local probe] |
| Typer | Nested report CLI | ✓ via project user base | 0.26.8 | — [VERIFIED: local probe] |
| pytest | Nyquist verification | ✓ via project user base | 8.4.2 | — [VERIFIED: local probe] |
| `uv` | Optional dependency runner | ✗ | — | Use configured `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest`. [VERIFIED: local probe, `.planning/config.json`] |
| KIS/pykrx network | Implementation tests/reporting | Not required | — | Inject preflight collaborators; historical reports are offline. [VERIFIED: existing testing patterns and Phase 8 boundary] |

**Missing dependencies with no fallback:** None. [VERIFIED: local probe]

**Missing dependencies with fallback:** `uv` is absent, but the configured Python user-base command runs the relevant suite successfully. [VERIFIED: 70 relevant tests passed in 1.61s]

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.4.2 with Typer `CliRunner` [VERIFIED: local probe, tests] |
| Config file | `pyproject.toml` (`testpaths = ["tests"]`, `pythonpath = ["."]`) [VERIFIED: `pyproject.toml`] |
| Quick run command | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_reporting.py tests/test_report_cli.py tests/test_preflight.py tests/test_operator_runbook.py` [VERIFIED: project test command pattern] |
| Full suite command | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` [VERIFIED: `.planning/config.json`] |

The existing relevant baseline is green: `tests/test_sqlite_audit.py tests/test_cli.py tests/test_replay.py tests/test_notifier.py` produced 70 passes in 1.61 seconds. [VERIFIED: local test run 2026-07-13]

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REP-01 | Daily report shows summary, all ticker details in run/process order, decision/confidence/order/no-trade code + Korean text, and byte-identical optional file | unit + CLI integration | `python3 -m pytest -q tests/test_reporting.py tests/test_report_cli.py -k daily` | ❌ Wave 0 |
| REP-02 | Inclusive KST range, target, total/determinate/state reconciliation, append-only order reconciliation, replay integrity/compatibility/dedup/disclaimer | unit + CLI integration | `python3 -m pytest -q tests/test_reporting.py tests/test_report_cli.py -k 'period or replay'` | ❌ Wave 0 |
| RUN-01 | Shared status/run preflight blocks unknown safety checks; documented 08:50/09:05/09:10/report sequence and completion criteria exist | unit + CLI + doc contract | `python3 -m pytest -q tests/test_preflight.py tests/test_operator_runbook.py` | ❌ Wave 0 |
| RUN-02 | Each required failure has code, stop rule, prohibited action, safe next action, and resolution criterion; notification failure persists while audit failure blocks | unit + CLI + doc contract | `python3 -m pytest -q tests/test_preflight.py tests/test_operator_runbook.py -k failure` | ❌ Wave 0 |

Use the configured `PYTHONUSERBASE` prefix in actual plan verification commands; the shortened table commands describe test selection only. [VERIFIED: environment probe]

### Sampling Rate

- **Per task commit:** Run the new test file(s) for that task plus the directly affected existing file (`test_sqlite_audit.py`, `test_cli.py`, `test_replay.py`, or `test_notifier.py`). [VERIFIED: existing suite speed]
- **Per wave merge:** Run all four new Phase 8 test files and the four relevant existing files. [VERIFIED: baseline 1.61s]
- **Phase gate:** Full configured suite green before `$gsd-verify-work 8`. [VERIFIED: GSD workflow configuration]

### Wave 0 Gaps

- [ ] `tests/test_reporting.py` — SQLite fixtures, evidence-state classification, processing order, preview diff, period denominators, reconciliation reduction, Korean reasons.
- [ ] `tests/test_report_cli.py` — nested commands, input validation, read-only behavior, terminal/file equality, replay compatibility and integrity errors.
- [ ] `tests/test_preflight.py` — mock/audit/KRX/unresolved-order PASS/BLOCK/UNKNOWN and shared status/run enforcement.
- [ ] `tests/test_operator_runbook.py` — required schedule, commands, completion checklist, all RUN-02 failure rows, prohibited reruns/resubmissions, and resolution criteria.
- [ ] Existing `tests/test_sqlite_audit.py`, `tests/test_cli.py`, and `tests/test_notifier.py` need additive coverage for notification persistence and unchanged fail-soft execution semantics.

No framework installation or pytest configuration change is needed. [VERIFIED: environment and baseline test run]

## Security Domain

Security enforcement is enabled at ASVS level 1 and blocks high-severity findings. [VERIFIED: `.planning/config.json`]

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No new auth | Phase 8 must not read or print credential values; existing Settings/KIS selection remains authoritative. [VERIFIED: phase scope] |
| V3 Session Management | No | Local synchronous CLI has no user session. [VERIFIED: architecture] |
| V4 Access Control | Limited | Reports are local-file readers and must not broaden real-trading authority or mutate settings. [VERIFIED: CAL-04 boundary] |
| V5 Input Validation | Yes | Strict `YYYYMMDD` dates, start <= end, SQLite placeholders, regular-file replay validation, strict JSON structure/types, result-ID recomputation. [CITED: https://docs.python.org/3.10/library/sqlite3.html] [VERIFIED: replay identity contract] |
| V6 Cryptography | Limited | Reuse existing SHA-256 stable identity via `hashlib`; do not design new cryptography or treat the hash as authentication. [VERIFIED: `trading_bot/replay.py`] |
| V12 Files and Resources | Yes | Reject symlink/path escape ambiguity, use read-only SQLite URI, atomic UTF-8 output, and bounded diagnostics without replay/provider payload echo. [VERIFIED: existing replay output security pattern] |
| V14 Configuration | Yes | Reports may read `audit_db_path` but must not mutate policy, trading mode, or promotion state. [VERIFIED: requirements and settings] |

### Known Threat Patterns for Python/SQLite CLI

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection through dates/options | Tampering | Strict date parsing and bound placeholders. [CITED: https://docs.python.org/3.10/library/sqlite3.html] |
| Report command mutates/creates audit DB | Tampering | URI `mode=ro`, `query_only`, no migration/build-runtime calls, and before/after DB-byte tests. [CITED: https://docs.python.org/3.10/library/sqlite3.html] |
| Forged replay result ID or malformed funnel | Tampering | Recompute stable ID, validate structure/count invariants, reject before aggregation. [VERIFIED: `trading_bot/replay.py`] |
| Symlink/path traversal on replay or output | Tampering / Information Disclosure | Reuse resolved-parent, regular-file, symlink refusal, and atomic replace checks. [VERIFIED: `write_replay_result`] |
| Secret/raw payload leakage in reports | Information Disclosure | Render only normalized sanitized columns; never print raw exceptions, provider JSON, webhook, tokens, or credential fields. [VERIFIED: `sanitize_detail`, replay bounded diagnostics] |
| Join multiplication or dropped unknowns | Tampering / Repudiation | Separate normalized queries, cardinality checks, explicit unknowns, and summary/detail reconciliation tests. [VERIFIED: REP-02] |
| Blind rerun/resubmission from runbook | Tampering / Repudiation | Stable prohibited-action text, parent-linked manual retry, affected-ticker freeze, broker truth before resume. [VERIFIED: D-15/D-16] |

## Sources

### Primary (HIGH confidence)

- `.planning/phases/08-decision-reports-operator-runbook/08-CONTEXT.md` — locked report, aggregation, operation, and triage decisions. [VERIFIED: project source]
- `.planning/REQUIREMENTS.md` and `.planning/ROADMAP.md` — REP-01/02, RUN-01/02, success criteria, and Phase 9/10 boundaries. [VERIFIED: project source]
- `trading_bot/audit_models.py`, `trading_bot/sqlite_audit.py`, `trading_bot/cli.py`, `trading_bot/replay.py`, `trading_bot/kis_broker.py` — current evidence, CLI, replay, and reconciliation contracts. [VERIFIED: codebase]
- `tests/test_sqlite_audit.py`, `tests/test_cli.py`, `tests/test_replay.py`, `tests/test_notifier.py` — current invariants and injected-collaborator test patterns. [VERIFIED: codebase]
- Python 3.10 sqlite3 official documentation — placeholders, row factories, URI/read-only connections. [CITED: https://docs.python.org/3.10/library/sqlite3.html]
- Typer official subcommand documentation — nested command apps and `add_typer`. [CITED: https://typer.tiangolo.com/tutorial/subcommands/name-and-help/]

### Secondary (MEDIUM confidence)

- Typer official one-file-per-command guide — separate sub-app/module organization. [CITED: https://typer.tiangolo.com/tutorial/one-file-per-command/]
- pytest official temporary-path documentation — unique filesystem isolation; the current project already demonstrates `tmp_path` extensively. [CITED: https://docs.pytest.org/en/8.4.x/how-to/tmp_path.html]

### Tertiary (LOW confidence)

- None.

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — no new dependencies; versions and availability were verified against `pyproject.toml` and the local project user base.
- Architecture: HIGH — derived from locked decisions and current normalized schema/CLI/replay contracts.
- Pitfalls: HIGH — the notification, read-only, join-cardinality, status, and replay-integrity gaps are directly observable in code and tests.
- External documentation: MEDIUM — official pages were fetched through web fallback because Context7/`ctx7` was unavailable; the research-plan cache was populated through the GSD seam.

**Research date:** 2026-07-13
**Valid until:** 2026-08-12 (stable internal architecture; re-check if schema or replay result format changes)
