# Phase 6: Audit Evidence & Cycle Boundaries - Research

**Researched:** 2026-07-11
**Domain:** SQLite audit lifecycle, append-only broker evidence, KRX cycle boundaries
**Confidence:** HIGH
**Execution note:** Produced via generic-agent workaround because typed `gsd-phase-researcher` dispatch was unavailable.

## User Constraints

### Run lifecycle and identity
- **D-01:** Record `bot screen` and `bot run` as runs. `bot status` is read-only and does not create a run.
- **D-02:** Use terminal run states `COMPLETED`, `COMPLETED_WITH_ERRORS`, `FAILED`, and `INTERRUPTED`; an in-progress run may use `RUNNING` but must eventually resolve to exactly one terminal state.
- **D-03:** At the start of the next `bot screen` or `bot run`, automatically close any abandoned `RUNNING` run as `INTERRUPTED`, recording recovery time and a normalized reason.
- **D-04:** Issue a new UUID `run_id` for every invocation. When an invocation is an explicit retry, link it to the prior invocation through optional `parent_run_id`; never overwrite a prior attempt.

### Ticker terminal outcomes
- **D-05:** Separate a bounded, stable `outcome_code` from the more specific `reason_code` and sanitized explanatory detail.
- **D-06:** Use run-kind-specific outcome vocabularies: screening outcomes describe selection/rejection/screening failure, while evaluation outcomes describe no-trade, suppression, submission, reconciliation, ambiguity, or execution failure.
- **D-07:** Every attempted ticker must receive exactly one terminal outcome row even when data collection, LLM invocation, parsing, risk evaluation, or order handling raises. Unknown/unavailable fields remain explicit `NULL`; failures record `failed_stage` and normalized reason.
- **D-08:** Preserve stable reason codes such as stale data, low confidence, malformed signal, provider timeout, KIS unavailability, and duplicate suppression. Store only sanitized diagnostic detail; do not store secrets, raw provider responses, tokens, or credentials.

### Order evidence chain
- **D-09:** Preserve the order path as append-only, timestamped events and retain a convenient final order-state summary on the ticker terminal outcome. Do not erase earlier evidence by updating one mutable order-history row.
- **D-10:** Assign `order_intent_id` when an order intent is created and a distinct `submission_id` for every broker submission attempt. Broker queries and reconciliation events link back to the originating intent.
- **D-11:** A submission whose acceptance cannot be determined terminates the ticker as `AMBIGUOUS_SUBMISSION`; it must not trigger a blind POST retry. Later broker inquiry appends reconciliation events to the original intent and attributes the observation to both the originating run and the later observing run.
- **D-12:** Duplicate suppression and reconciliation evidence stores normalized broker facts: observation time, KIS order ID, ticker, side, requested quantity, filled quantity, remaining quantity, and inquiry status. Duplicate suppression links the matching existing broker order. Raw KIS responses are not persisted.

### KRX cycle boundaries and freshness
- **D-13:** Permit order submission only during the conservative KRX regular-session continuous-trading window. Pre-open, after-hours, and auction windows are non-executable but their observed session state is recorded. Research/planning must confirm exact boundaries against authoritative KRX rules.
- **D-14:** During an open-market run, indicators and screening use bars only through the immediately preceding completed KRX trading day; never use the current incomplete daily bar. Record requested trading date, completed-bar cutoff, and actual last bar date.
- **D-15:** Re-fetch the KIS quote immediately before submission. At submission time the quote must be no more than 10 seconds old. Record both initial-context quote time and pre-submit quote observation time; stale quotes block the trade.
- **D-16:** If the KRX trading day or current session cannot be established, fail closed and place no order. Record KST observation time, trading date, session, executable/non-executable decision, normalized reason, and timing-policy version.

### Agent Discretion
- Choose schema/table names, enum implementation, migration mechanics, indexes, and internal service boundaries consistent with the existing SQLite and synchronous CLI patterns.
- Define the exhaustive initial code lists and event names, provided they preserve the semantic distinctions above and remain stable for downstream reports.
- Select an authoritative KRX calendar/session source and exact continuous-trading boundaries during research, with fail-closed behavior when unavailable.

### Deferred Ideas

None — discussion stayed within phase scope. Replay belongs to Phase 7, reports/runbook to Phase 8, mock soak/fault drills to Phase 9, and calibration/promotion readiness to Phase 10.

## Summary

Phase 6 should evolve the existing SQLite sink rather than replace it. The current seams are useful but incomplete: `sqlite_audit.py` creates only `runs` and `decisions`; `run_cycle` starts a run but never finalizes it; the ticker exception branch returns an in-memory error without persisting it; `screen` creates no run; and `KISBroker.last_reconciliation` exposes only the latest mutable summary. [VERIFIED: codebase inspection]

Implement a versioned, additive SQLite migration that introduces lifecycle-rich `runs`, exactly-one `ticker_outcomes`, and append-only `order_events`. Put orchestration around both mutating CLI commands, use typed policy/evidence records, and inject clocks/calendar/quote readers so all boundary behavior is deterministic under test. Preserve compatibility with existing `decisions` data during the migration; downstream replay and reports need stable identifiers and normalized codes, not a destructive rewrite. [VERIFIED: codebase inspection]

KRX's official materials identify the equity continuous-auction interval as 09:00–15:20 and the closing auction as 15:20–15:30; therefore the executable predicate is `09:00:00 <= KST time < 15:20:00` on a confirmed KRX trading day. KRX also defines holidays beyond weekends, including statutory holidays, Labor Day, year-end closure, and exchange-designated closures, so weekday arithmetic alone is unsafe. [CITED: https://global.krx.co.kr/contents/GLB/06/0602/0602020204/GLB0602020204T7.jsp] [CITED: https://global.krx.co.kr/contents/GLB/06/0602/0602010201/GLB0602010201T1.jsp]

**Primary recommendation:** Build the phase in four vertical steps: schema/migrations and code vocabularies; run/ticker orchestration; append-only broker evidence; then authoritative time/bar/quote gates with end-to-end audit tests.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|---|---|---|---|
| Run lifecycle and ticker terminality | CLI / application orchestration | SQLite storage | CLI owns invocation boundaries; storage enforces durable attribution and uniqueness. |
| Audit schema and migration | Database / storage | Application models | SQLite owns integrity; Python models provide stable code vocabulary. |
| Order intent/submission/reconciliation evidence | Broker application service | SQLite storage | Broker path observes each transition; sink persists immutable events. |
| KRX session and completed-bar policy | Domain policy service | pykrx adapter | Policy decides executable/cutoff state; adapter fetches only the requested range. |
| Quote freshness gate | Execution/broker preflight | KIS quote adapter | Gate must occur immediately before POST; adapter supplies value plus observation timestamp. |

## Project Constraints (from AGENTS.md)

- Python, Korea-only `pykrx` + KIS architecture; strict JSON trade signal; fail safe on unparseable output. [VERIFIED: AGENTS.md]
- Mock KIS account remains the first target and real-money promotion remains deliberate and gated. [VERIFIED: AGENTS.md]
- BUY requires confidence `>= 0.8`; lower-confidence and HOLD signals never trade. [VERIFIED: AGENTS.md]
- Continue using stdlib `sqlite3`, synchronous Typer CLI, structured logging, Pydantic settings, and existing adapter boundaries. [VERIFIED: AGENTS.md and codebase inspection]
- Do not introduce `mojito2`, TA-Lib as default, assistant-prefill JSON forcing, raw secrets, or direct edits outside a GSD workflow. [VERIFIED: AGENTS.md]

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---|---:|---|---|
| Python stdlib `sqlite3` | Python 3.10+ project contract | migrations, constraints, atomic writes | Already shipped; supports explicit transactions, WAL, FK checks, and parameterized SQL. [CITED: https://docs.python.org/3/library/sqlite3.html] |
| `zoneinfo` + `datetime` | stdlib | KST-aware session calculations | Already used and dependency-free; injectable `now` makes tests deterministic. [VERIFIED: codebase inspection] |
| `pykrx` | 1.2.8 pinned | daily OHLCV and observed KRX dates | Existing isolated adapter; use as data transport, not as the sole authority for session policy. [VERIFIED: pyproject.toml and codebase inspection] |
| Existing KIS REST adapters | repository code | quote refresh and broker truth | Existing auth, rate limiting, non-retried POST, and inquiry paths should be extended rather than duplicated. [VERIFIED: codebase inspection] |

### Supporting

| Library | Version | Purpose | When to Use |
|---|---:|---|---|
| Pydantic | 2.13.4 pinned | validate policy snapshots and normalized evidence payloads at boundaries | Use for serialized/config-facing models; frozen dataclasses remain appropriate for internal value objects. [VERIFIED: pyproject.toml] |
| pytest | 8.4.2 pinned | deterministic lifecycle, migration, and timing tests | Existing suite and fixtures already inject collaborators. [VERIFIED: `.venv/bin/python -m pytest --version`] |

**Installation:** No new package is required. This avoids a new package-legitimacy gate and keeps the phase within the established stack.

## Package Legitimacy Audit

No external packages are added in this phase; not applicable.

## Architecture Patterns

### System Architecture Diagram

```text
bot screen / bot run
        |
        v
Run coordinator: recover abandoned runs -> start RUNNING -> snapshot policy/provenance
        |
        +--> KRX cycle policy -> session evidence + completed-bar cutoff
        |
        +--> one ticker scope per attempted ticker
                 |
                 +--> data / LLM / risk -> exactly one terminal ticker_outcome
                 |
                 +--> order intent -> duplicate inquiry -> submission -> reconciliation
                                      | append-only order_events |
                                      +--------------------------> SQLite audit store
        |
        v
finally: terminalize run (COMPLETED / WITH_ERRORS / FAILED / INTERRUPTED)
```

### Recommended Project Structure

```text
trading_bot/
├── audit_models.py       # stable enums/value records and sanitization
├── sqlite_audit.py       # migrations plus lifecycle/outcome/event repository
├── market_cycle.py       # injected KST clock, KRX day/session/cutoff policy
├── cli.py                # run coordinator and per-ticker terminalization
├── kis_quote.py          # quote observation timestamp
└── kis_broker.py         # event-emitting order path and pre-submit gate
tests/
├── test_sqlite_audit.py
├── test_market_cycle.py
├── test_cli.py
└── test_kis_broker.py
```

### Pattern 1: Versioned additive SQLite migration

Use `PRAGMA user_version` and ordered migration functions inside an explicit transaction. Existing installations may already contain v1 `runs`/`decisions`, so inspect columns before adding fields and create new tables/indexes idempotently. Enable `PRAGMA foreign_keys=ON` on every connection; SQLite foreign-key enforcement is connection-local. [CITED: https://www.sqlite.org/pragma.html#pragma_user_version] [CITED: https://www.sqlite.org/foreignkeys.html]

Recommended tables:

- `runs`: `run_id`, optional `parent_run_id`, `run_kind`, `status`, `started_at`, `ended_at`, `kst_trading_date`, execution target/mode, dry-run, policy snapshot JSON, input provenance JSON, recovery reason/time.
- `ticker_outcomes`: one row per `(run_id, ticker)` with run-kind-specific `outcome_code`, `reason_code`, sanitized detail, `failed_stage`, final order-state summary, quote/bar/session references. Enforce `UNIQUE(run_id, ticker)`.
- `order_events`: immutable event ID, originating run/ticker, observing run, `order_intent_id`, optional `submission_id`, event type/time, normalized broker facts, matched existing intent/order. Append only through repository API.
- `cycle_evidence`: one record per run or executable ticker scope containing KST observation, trading day, session, executable flag/reason, policy version, requested date, completed-bar cutoff, actual last bar, initial quote time, pre-submit quote time, and quote age.

Keep legacy `decisions` readable during migration; either backfill `ticker_outcomes` once with an explicit migration marker or dual-read it only for old runs. Do not silently reinterpret old rows as complete Phase 6 evidence. [VERIFIED: codebase inspection]

### Pattern 2: Exactly-once terminal outcome via ticker scope

Create a per-ticker accumulator before any data call. Every success/skip/failure branch assigns its normalized terminal code, and one `finally` block persists it. The unique constraint catches accidental double writes; a missing row is detected by run finalization comparing attempted count with outcome count. [VERIFIED: codebase inspection of current missing exception write]

### Pattern 3: Append-only event observer at the broker seam

Inject an `OrderEventSink`/callback into `KISBroker`. Emit after durable local decisions: `INTENT_CREATED`, `DUPLICATE_INQUIRY_STARTED`, `DUPLICATE_SUPPRESSED`, `SUBMISSION_STARTED`, `SUBMISSION_ACCEPTED`, `SUBMISSION_AMBIGUOUS`, `RECONCILIATION_OBSERVED`. Generate `submission_id` before the POST so transport failures remain attributable. Never catch a transport exception and issue another POST; classify inability to determine acceptance as ambiguity, then require inquiry-based reconciliation. [VERIFIED: current tests already assert POST is not retried]

### Pattern 4: Pure market-cycle decision plus injected evidence sources

Represent session classification as a pure function of timezone-aware KST datetime plus a confirmed trading-day result. Use half-open boundaries: continuous trading is `[09:00, 15:20)`, closing auction `[15:20, 15:30]`; all non-continuous states are non-executable. Keep `policy_version` stable in stored evidence. [CITED: https://global.krx.co.kr/contents/GLB/06/0602/0602020204/GLB0602020204T7.jsp]

For open-market runs, resolve the immediately preceding confirmed trading day before requesting OHLCV. Pass that date as both request end and freshness cutoff, then record the returned last bar. If a confirmed prior trading day cannot be obtained, return `CALENDAR_UNAVAILABLE` and block execution. KRX's official holiday rules are the authority for semantics; the implementation should isolate the calendar provider so special KRX closure data can be updated/tested without changing execution logic. [CITED: https://global.krx.co.kr/contents/GLB/06/0602/0602010201/GLB0602010201T1.jsp]

### Pattern 5: Quote timestamp captured at observation, checked at POST boundary

Extend `KisQuoteResult` with an aware `observed_at` assigned only after a valid response is parsed. Before broker POST, fetch again, calculate `age = submit_check_time - observed_at`, require `0 <= age <= 10s`, and use the refreshed price consistently for tick snapping/order validation. Persist both context and pre-submit timestamps even when stale/failed. A negative age is clock-invalid and must fail closed. [VERIFIED: current quote result lacks a timestamp]

### Anti-Patterns to Avoid

- Updating one order-history row: destroys the path needed by EVID-03.
- Generating `submission_id` after POST: loses attribution on timeouts.
- Treating every POST exception as definitive rejection: transport failure can leave acceptance unknown.
- Finalizing a run only on the happy return path: `KeyboardInterrupt`, `SystemExit`, or an outer failure leaves `RUNNING` stranded.
- Weekday-only market clock or inclusive `<= 15:30`: admits holidays and closing auction.
- Using `datetime.now()` deep inside adapters: prevents deterministic boundary tests and coherent evidence timestamps.
- Persisting `str(exc)` unfiltered: may leak response details or credentials.
- Reusing the initial context quote for submission: violates D-15 after a slow LLM response.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---|---|---|---|
| SQL escaping | string-formatted statements | `sqlite3` parameter substitution | Prevents injection and quoting errors. [CITED: https://docs.python.org/3/library/sqlite3.html] |
| Timezone offsets | manual UTC+9 arithmetic | `ZoneInfo("Asia/Seoul")` | Handles aware datetime semantics consistently. [VERIFIED: existing code pattern] |
| Provider-response storage | raw KIS/LLM JSON archival | normalized typed fields + sanitized detail | Satisfies D-08/D-12 and stabilizes downstream reports. |
| Calendar logic scattered across CLI/broker | repeated weekday/time checks | one injected `MarketCyclePolicy` | Avoids policy drift and enables fail-closed testing. |

## Runtime State Inventory

| Category | Items Found | Action Required |
|---|---|---|
| Stored data | `./data/audit.db` configured; current schema has `runs` and `decisions` | Add idempotent migration and preserve old rows; test migration from an actual v1-shaped fixture. |
| Live service config | No long-running service/scheduler in project; CLI is manual | None. [VERIFIED: codebase and AGENTS.md] |
| OS-registered state | None found in repository; no scheduler is part of v1 | None. [VERIFIED: codebase inspection] |
| Secrets/env vars | `.env` exists; KIS credentials/account configuration are environment-backed | Do not migrate or copy secrets into audit snapshots; snapshot only safe policy/provenance fields. |
| Build artifacts | `.venv`, egg-info, pytest cache present | No migration; use `.venv/bin/python` for verification. |

## Common Pitfalls

### Pitfall 1: Lifecycle recovery races
**What goes wrong:** A second invocation marks a genuinely active run interrupted.
**How to avoid:** Within a write transaction, recover prior `RUNNING` rows before inserting the new run; because this is a personal synchronous CLI, document single-process ownership and use SQLite locking. Add process/host metadata only as diagnostic provenance, not as proof of liveness.

### Pitfall 2: `executescript()` transaction surprise
**What goes wrong:** Migration code assumes an outer transaction remains intact.
**How to avoid:** Python documents that `executescript()` implicitly commits a pending transaction; migration functions should control boundaries explicitly and test rollback on injected failure. [CITED: https://docs.python.org/3/library/sqlite3.html]

### Pitfall 3: Outcome vocabulary drift
**What goes wrong:** reports later depend on free-text variants.
**How to avoid:** central enums/constants plus DB CHECK constraints where migrations permit; separate coarse `outcome_code` from stable `reason_code` and sanitized detail.

### Pitfall 4: Ambiguous exception classification
**What goes wrong:** validation failures and transport failures are both labeled ambiguity.
**How to avoid:** ambiguity applies only after a submission attempt crosses the broker boundary and acceptance cannot be determined. Preflight/serialization/auth failures are execution failures with their own stages/codes.

### Pitfall 5: Wrong daily-bar cutoff
**What goes wrong:** an open-market run requests today's partial bar or a weekend-minus-one-day date.
**How to avoid:** ask the calendar abstraction for the previous confirmed KRX trading day; record requested date, cutoff, and observed last bar, and reject any observed bar after cutoff.

## Code Examples

### Explicit migration transaction

```python
# Sources: Python sqlite3 and SQLite PRAGMA documentation
conn.execute("PRAGMA foreign_keys = ON")
version = conn.execute("PRAGMA user_version").fetchone()[0]
with conn:
    if version < 2:
        migrate_v1_to_v2(conn)
        conn.execute("PRAGMA user_version = 2")
```

### Half-open executable interval

```python
CONTINUOUS_START = time(9, 0)
CONTINUOUS_END = time(15, 20)
executable = is_confirmed_trading_day and CONTINUOUS_START <= observed.time() < CONTINUOUS_END
```

### Exactly-one outcome shape

```python
outcome = TickerOutcome.pending(run_id=run_id, ticker=ticker)
try:
    outcome = evaluate_ticker(...)
except Exception as exc:
    outcome = classify_failure(outcome, stage=current_stage, exc=exc)
finally:
    audit.write_ticker_outcome(conn, outcome)  # UNIQUE(run_id, ticker)
```

## State of the Art

| Old Approach | Required Phase 6 Approach | Impact |
|---|---|---|
| Two-table run/decision snapshot | versioned lifecycle/outcome/event evidence model | complete attribution and downstream reportability |
| Mutable `last_reconciliation` | append-only events plus final summary | preserves duplicate/submission/fill history |
| weekday 09:00–15:30 boolean | confirmed KRX day + classified session, executable 09:00–15:20 | excludes closing auction and special closures |
| untimestamped quote | observation timestamp + pre-submit refresh/10s gate | proves freshness at order boundary |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|---|---|---|
| A1 | The CLI remains single-process for Phase 6. | Pitfall 1 | Concurrent invocations would require stronger ownership/lease semantics. |
| A2 | Existing v1 audit rows may remain legacy-incomplete rather than being fabricated into full Phase 6 evidence. | Migration | Downstream consumers must recognize schema/evidence version. |

## Open Questions (RESOLVED)

1. **How will explicit retry `parent_run_id` be supplied?**
   - **RESOLVED:** Add optional `--parent-run-id` to `screen` and `run`, validate that it is a UUID referencing an existing run, reject self-reference, and never infer retry relationships from date/ticker similarity. Every retry remains a new run UUID.
2. **What is the runtime source for special KRX closure dates?**
   - **RESOLVED:** Define an injected `KRXCalendarProvider`; its production implementation confirms dates from KRX-observed dates through the existing pykrx seam for the current invocation. It authorizes submission only when both the current and previous completed trading day are positively confirmed. Provider error, missing/stale observation, or inability to distinguish a special closure returns `UNKNOWN`/`CALENDAR_UNAVAILABLE` and blocks submission. There is no weekday fallback. Tests cover statutory holidays, Labor Day, year-end closure, exchange-designated closure, and provider failure. Official KRX rules are the semantic authority; the adapter is observation transport only.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|---|---|---:|---|---|
| Project virtualenv Python | tests/runtime | yes | 3.14.3 | project supports >=3.10 |
| pytest | validation | yes in `.venv` | 8.4.2 | none needed |
| SQLite stdlib | audit persistence | yes | bundled with Python | none needed |
| Live KIS/KRX network | production observation | not required for plan/tests | — | injected offline fakes |

## Validation Architecture

### Test Framework

| Property | Value |
|---|---|
| Framework | pytest 8.4.2 |
| Config file | `pyproject.toml` |
| Quick run command | `.venv/bin/python -m pytest -q tests/test_sqlite_audit.py tests/test_market_cycle.py tests/test_kis_broker.py tests/test_cli.py` |
| Full suite command | `PYTHONUSERBASE="$PWD/.python-userbase" .venv/bin/python -m pytest -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|---|---|---|---|---|
| EVID-01 | both run kinds terminalize, recover abandoned runs, snapshot policy/provenance | integration | `.venv/bin/python -m pytest -q tests/test_sqlite_audit.py tests/test_cli.py` | extend existing |
| EVID-02 | every attempted ticker has exactly one normalized outcome on every branch | integration/parameterized | `.venv/bin/python -m pytest -q tests/test_cli.py` | extend existing |
| EVID-03 | intent/submission/reconciliation and ambiguity are append-only and correctly attributed | unit/integration | `.venv/bin/python -m pytest -q tests/test_kis_broker.py tests/test_sqlite_audit.py` | extend existing |
| EVID-04 | session boundaries, prior completed bar, and 10-second quote gate | unit/boundary | `.venv/bin/python -m pytest -q tests/test_market_cycle.py tests/test_kis_quote.py tests/test_kis_broker.py` | `test_market_cycle.py` Wave 0 |

### Sampling Rate

- **Per task commit:** targeted files listed above.
- **Per wave merge:** full suite.
- **Phase gate:** full suite green plus migration test against v1 schema fixture.

### Wave 0 Gaps

- [ ] `tests/test_market_cycle.py` — KRX day/session boundary and completed-bar cutoff fixtures.
- [ ] Add v1-to-v2 migration, interrupted recovery, and constraints fixtures to `tests/test_sqlite_audit.py`.
- [ ] Add clock, quote observation, ambiguity, and event-sink fakes to shared/local test fixtures.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---|---|---|
| V2 Authentication | no new auth | Existing shared KIS token manager remains unchanged. |
| V3 Session Management | no | CLI runs are audit lifecycles, not user sessions. |
| V4 Access Control | yes, safety authority | Only `--execute` plus existing real-mode confirmation reaches broker mutation; audit/reconciliation code must not broaden authority. |
| V5 Input Validation | yes | Pydantic/value types, enum vocabularies, DB constraints, parameterized SQL, ticker/date/parent ID validation. |
| V6 Cryptography | no | No new cryptographic operation. |

### Known Threat Patterns for Python/SQLite trading audit

| Pattern | STRIDE | Standard Mitigation |
|---|---|---|
| SQL injection through diagnostic/provider text | Tampering | parameterized statements only |
| audit truncation after exception | Repudiation | ticker `finally` write and run terminalization/recovery |
| secret/raw response persistence | Information disclosure | normalized allowlist serializer and sanitizer |
| duplicate/ambiguous POST | Tampering / financial impact | submission ID before POST, no blind retry, inquiry reconciliation |
| time/calendar spoof or uncertainty | Spoofing / tampering | timezone-aware injected clock, policy version, fail closed on unknown calendar/session |

## Sources

### Primary (HIGH confidence)

- https://global.krx.co.kr/contents/GLB/06/0602/0602020204/GLB0602020204T7.jsp — official KRX continuous auction 09:00–15:20 and closing auction 15:20–15:30.
- https://global.krx.co.kr/contents/GLB/06/0602/0602010201/GLB0602010201T1.jsp — official KRX regular/off-hours and holiday rules.
- https://docs.python.org/3/library/sqlite3.html — Python transaction behavior, parameterized SQL, `executescript` behavior.
- https://www.sqlite.org/pragma.html#pragma_user_version — schema version storage.
- https://www.sqlite.org/foreignkeys.html — connection-local foreign-key enforcement.
- Repository source/tests listed in `06-CONTEXT.md` — present seams and verified gaps.

### Secondary (MEDIUM confidence)

- None required.

### Tertiary (LOW confidence)

- Assumptions A1–A2 only.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — unchanged pinned/stdlib stack verified locally.
- Architecture: HIGH — derived from current code seams and locked decisions.
- KRX boundaries: HIGH — official exchange sources.
- Calendar runtime provider: MEDIUM — authority semantics are clear, but the repository lacks a current official machine-readable calendar integration.
- Pitfalls: HIGH — current gaps reproduced by direct code inspection and official SQLite behavior.

**Research date:** 2026-07-11
**Valid until:** 2026-08-10 for implementation patterns; re-check KRX hours before production deployment.
