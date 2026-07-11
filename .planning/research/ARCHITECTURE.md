# Architecture Research

**Domain:** Operational validation architecture for a personal KR-market trading bot
**Researched:** 2026-07-11
**Confidence:** HIGH for codebase integration; MEDIUM for replay methodology

## Recommendation

Build v1.1 as an **observability and validation layer around the existing decision core**, not as a second trading engine. Extract the per-ticker application workflow currently embedded in `cli.run_cycle` into a reusable `CycleService`, then give live runs, historical replay, and mock-soak runs different adapters for data, signals, brokers, clocks, and audit destinations.

Keep these safety-critical modules unchanged unless a failing characterization test proves a defect:

- `execution.py`: parse → risk precedence → confidence gate → sizing → dry-run/order boundary.
- `risk.py`: stop-loss, take-profit, and daily-loss rules.
- `kis_broker.py` and `kis_order.py`: query-before-POST reconciliation and KIS order transport.
- `mock_broker.py`: deterministic in-memory simulation.
- provider adapters and strict signal parsing.

The v1.1 architecture should add evidence, not authority. Replay and calibration may recommend policy changes, but they must never mutate runtime settings or enable real trading. The existing real-money confirmation gate remains the only promotion mechanism.

## Existing Seams That Matter

| Existing component | Current behavior | v1.1 implication |
|---|---|---|
| `cli.run_cycle` | Builds collaborators, screens, loops tickers, invokes the LLM cycle, writes decisions, isolates ticker failures, and notifies. | Extract orchestration without changing behavior; all v1.0 CLI tests become characterization tests. |
| `execute_signal_cycle` | Pure deterministic decision logic except for the injected `Broker`; dry-run gate is immediately before `place_order`. | Reuse unchanged in live, replay, and soak. This is the primary parity seam. |
| `MarketDataSource` | Combines historical OHLCV, indicators, current KIS quote, and news; stale required data fails closed. | Keep for live/soak. Replay needs a point-in-time adapter because a historical epoch must not request today's KIS quote or news. |
| `screen_candidates` | Pure screening transform over supplied rows and explicit date. | Reuse directly in replay with historical rows cut off at each epoch. |
| `MockBroker` | Deterministic in-memory portfolio and fills. | Reuse across all replay epochs in one experiment; do not recreate it per date. |
| `KISBroker` | Reconciles existing orders before POST and reads fills afterward; supports whichever KIS domain/TR-ID profile is supplied. | Reuse unchanged for KIS mock soak via an explicit mock-only factory. |
| `sqlite_audit` | Stores run headers and successful decision events; ticker exceptions are only returned/notified, not persisted. | Add versioned migrations and attempt/outcome evidence before reporting or soak. |
| `DataContext` | Defined in `trading_bot/domain.py`, not in the requested but absent `trading_bot/data_context.py`. | Replay builds the existing domain object; do not introduce a duplicate context schema. |

## Standard Architecture

### System Overview

```text
┌───────────────────────────────────────────────────────────────────────┐
│ Operator surfaces                                                     │
│ bot run/status/screen │ bot replay │ bot soak │ bot report/calibrate │
└──────────────┬────────┴──────┬─────┴─────┬────┴──────────┬────────────┘
               │               │           │               │
┌──────────────▼───────────────▼───────────▼───────────────▼────────────┐
│ Application services                                                  │
│ CycleService │ ReplayService │ SoakService │ Report/Calibration       │
└──────┬──────────────┬───────────────┬───────────────┬─────────────────┘
       │              │               │               │
┌──────▼──────────────▼───────────────▼───────────────▼─────────────────┐
│ Stable domain/core                                                    │
│ screen_candidates → signal parser → risk → execution → order intent  │
└──────┬──────────────┬───────────────┬───────────────┬─────────────────┘
       │              │               │               │
┌──────▼───────┐ ┌────▼─────────┐ ┌──▼───────────┐ ┌─▼────────────────┐
│ Data adapters │ │ Signal ports │ │ Broker ports │ │ Audit repository │
│ live/replay   │ │ LLM/fixture  │ │ memory/KIS   │ │ SQLite + queries │
└──────────────┘ └──────────────┘ └──────────────┘ └──────────────────┘
```

This is a small modular monolith. Do not add a message broker, workflow engine, scheduler, web dashboard, or full event-sourced trading platform for v1.1.

### Component Responsibilities

| Component | Status | Responsibility | Must not own |
|---|---|---|---|
| `CycleService` | **New** | Execute one explicit universe/date using injected data, signal, broker, policy, audit, clock, and notifier collaborators. Return a typed run result. | CLI parsing, concrete KIS construction, historical loops, report formatting. |
| `RunSpec` / `RunResult` | **New** | Immutable run metadata: run kind, trading date, execution target, campaign/experiment ID, policy snapshot, outcomes. | Secrets or mutable settings. |
| `ReplayService` | **New** | Iterate epochs chronologically, create point-in-time candidates/contexts, call `CycleService`, preserve simulated portfolio state, and calculate forward outcomes. | Live LLM, KIS quote/order calls, automatic calibration. |
| `ReplayDataSource` | **New adapter** | Expose only data available at an epoch; reuse `screen_candidates` and indicator transforms. | Future bars, current quotes, scraped current news. |
| `FixtureSignalProvider` | **New adapter** | Return deterministic strict signals from a versioned fixture/scenario keyed by date+ticker. | Network access or model calls. |
| `SoakService` | **New** | Run one manually triggered KIS mock cycle, attach campaign/scenario metadata, enforce mock-only invariants, and summarize evidence across days. | Scheduling or real credentials. |
| `KISMockBrokerFactory` | **New composition helper** | Build existing `KISBroker` with `settings.kis_mock`, mock account, shared token manager, and mock TR IDs. | Changes to `KISBroker.place_order`. |
| `FaultScenario` decorators | **New test adapters** | Deterministically inject timeout, stale data, unavailable query, and ambiguous order outcomes around data/order ports. | Production activation by free-form environment strings. |
| `AuditRepository` | **New interface/module** | Own schema migration, run lifecycle, attempt/outcome writes, and read queries. | Business decisions or report prose. |
| `DailyReportService` | **New** | Query immutable audit evidence and render text/Markdown/JSON daily reports. | Writes to audit facts. |
| `CalibrationService` | **New** | Run parameter grids over replay evidence and compare safety/coverage metrics; emit recommendations with sample sizes. | Editing `.env`, `Settings`, or promotion state. |
| Runbook/checklist docs | **New docs** | Fixed KST timing, commands, expected output, failure triage, evidence requirements, promotion checklist. | Executable policy. |
| `cli.py` | **Modified** | Remain composition root; delegate to services; add command groups. | Per-ticker business workflow after extraction. |
| `sqlite_audit.py` | **Modified** | Become a compatibility facade over migrations/repository during transition. | Report formatting. |
| `config.py` | **Minimally modified** | Add replay DB/report paths and typed soak options if needed. | A generic switch that can silently redirect real orders. |
| `execution.py`, `mock_broker.py`, `kis_broker.py`, `screener.py` | **Unchanged** | Continue as validated core/adapters. | v1.1 experiment-specific conditionals. |

## Recommended Project Structure

```text
trading_bot/
├── cli.py                         # Typer composition root only
├── application/
│   ├── cycle_service.py           # extracted v1.0 orchestration
│   ├── run_models.py              # RunSpec, RunResult, RunKind, ExecutionTarget
│   ├── replay_service.py          # chronological epoch loop
│   ├── soak_service.py            # one mock-only operational run
│   ├── reporting.py               # read models + renderers
│   └── calibration.py             # advisory parameter-grid analysis
├── replay/
│   ├── data_source.py             # point-in-time historical adapter
│   ├── fixture_provider.py        # deterministic signal adapter
│   ├── outcomes.py                # forward return/MFE/MAE calculations
│   └── fixtures/                  # versioned, reviewable signal scenarios
├── audit/
│   ├── migrations.py              # ordered transactional migrations
│   ├── repository.py              # writes and read queries
│   └── models.py                  # persisted run/attempt/read models
├── testing/
│   └── fault_adapters.py          # explicit synthetic soak scenarios
├── execution.py                   # unchanged safety core
├── risk.py                        # unchanged safety rules
├── screener.py                    # unchanged pure screener
├── mock_broker.py                 # unchanged simulation broker
└── kis_broker.py                  # unchanged reconciled KIS broker

docs/
├── RUNBOOK.md                     # daily KST operating procedure
└── REAL_MONEY_PROMOTION.md        # evidence-based manual checklist

tests/
├── test_cycle_service.py
├── test_replay.py
├── test_soak.py
├── test_audit_migrations.py
├── test_reporting.py
└── test_calibration.py
```

If introducing `application/` in one step causes excessive import churn, place the new modules directly under `trading_bot/` first. The component boundaries matter more than the package nesting.

## Data Model Evolution

The current two-table schema cannot prove soak completeness: a selected ticker that fails during context construction never gets a `decisions` row, and `runs` has no completion state. Reporting would therefore undercount failures and overstate coverage.

Use ordered, transactional, additive migrations tracked with `PRAGMA user_version`. Preserve existing rows and existing `write_decision` behavior during migration.

### Recommended additions

| Record | Purpose | Key fields |
|---|---|---|
| Extended `runs` | Identify and close every invocation. | `run_kind`, `trading_date`, `execution_target`, `campaign_id`, `experiment_id`, `policy_snapshot_json`, `fixture_version`, `completed_at`, `status`, `error_count`. |
| New `run_attempts` | Persist every selected ticker before context/LLM/execution work starts. | `run_id`, `ticker`, `stage`, `status`, `error_code`, sanitized `error_detail`, `started_at`, `completed_at`, latency fields, optional `decision_id`. |
| Existing `decisions` | Preserve authoritative decision/order facts. | Existing fields plus optional stable `attempt_id`; avoid embedding raw prompts/news. |
| New `replay_outcomes` | Store labels used for evaluation, separate from decisions. | `decision_id`, horizon, forward return, MFE, MAE, simulated fill/exit reason. |
| New `calibration_runs` | Record what parameter grid and evidence window produced a recommendation. | immutable parameter JSON, source experiment IDs, sample count, metrics JSON, recommendation JSON, created_at. |

Do not put all data into `decisions`. Attempts, decisions, and later-observed outcomes have different lifecycles and confidence levels. In particular, a replay outcome is not known at decision time and must never be available to the replay signal/context path.

Routine reports should open a separate query-only connection with a busy timeout. For an exportable report bundle, first create a consistent SQLite snapshot using `sqlite3.Connection.backup`; do not copy only the main `.db` file while WAL is active.

## Architectural Patterns

### 1. Functional Core, Imperative Shell

**What:** Keep screening, signal parsing, risk evaluation, thresholding, sizing, and replay metrics pure. Keep KIS, pykrx, SQLite, clocks, files, and notifications in adapters/application services.

**Why here:** v1.0 already follows this pattern. v1.1 should increase reuse of the proven core instead of adding `if replay` or `if soak` branches inside it.

```python
spec = RunSpec(kind=RunKind.REPLAY, trading_date=epoch, execute=True)
result = cycle_service.run(
    spec,
    data_source=replay_data.at(epoch),
    signal_provider=fixture_provider,
    broker=portfolio_broker,
    audit=replay_audit,
)
```

### 2. Point-in-Time Replay by Construction

**What:** Advance one explicit epoch at a time. A replay adapter may read bars whose availability timestamp is at or before the epoch only. Screening, rolling indicators, joins, and outcome labels use separate views.

**Rules:**

- Sort and validate epochs once; reject duplicates and non-monotonic input.
- Feed the screener rows for date `D` and indicator windows ending at `D` (or the last data actually available at the chosen decision time).
- Compute labels from `D+1...` only after the decision has been persisted.
- Never use current KIS prices, current Naver news, or a live LLM in backtest-lite replay.
- Record fixture version, code version, policy snapshot, date range, and data fingerprint.
- Keep one `MockBroker` for the experiment so positions/cash carry forward.

A full event queue is unnecessary for daily OHLCV backtest-lite. A deterministic chronological loop gives the important property without creating a second platform.

### 3. Explicit Execution Target, Not Implicit “Mock”

The current `TradingMode.MOCK` path constructs the in-memory `MockBroker`. That is safe, but it is not a KIS mock-account soak. Distinguish evidence sources explicitly:

| Target | Data | Signal | Broker | Orders possible |
|---|---|---|---|---|
| `DRY_RUN` | Live or replay | LLM or fixture | Any injected broker | No; core dry-run gate blocks POST. |
| `SIMULATED` | Replay/live fixture | Fixture | `MockBroker` | In-memory only. |
| `KIS_MOCK` | Live | Configured LLM or fixture scenario | Existing `KISBroker` using mock credentials/TR IDs | KIS mock only. |
| `KIS_REAL` | Live | Configured LLM | Existing real KIS composition | Existing confirmation gates only. |

For v1.1, expose `KIS_MOCK` only through `bot soak run` (or an equally explicit command), assert `TradingMode.MOCK`, and reject real domains/TR profiles before constructing the service. Leave `bot run` broker resolution unchanged until soak evidence justifies consolidation.

### 4. Append Evidence, Then Render

Persist structured facts first; reports are pure projections. A report renderer must not infer “no error” from a missing row. It should derive counts from `run_attempts`, join decisions when present, and show incomplete runs prominently.

### 5. Calibration as a One-Way Advisory Boundary

Calibration reads replay/soak snapshots and emits a candidate policy plus evidence. The operator reviews it and changes configuration in a separate deliberate action.

```text
Audit snapshot → parameter grid replay → metrics → recommendation artifact
                                                    │
                                                    └── human review only
Settings / real-money gate ←──────────────────────────── no automatic write
```

Evaluate confidence threshold, position cap, stop-loss, and take-profit together only after the replay ledger preserves cash and positions across epochs. Report sample size, no-trade rate, turnover, max drawdown, adverse/favorable excursion, rejected-order/error rate, and sensitivity around the proposed value. Do not optimize only for return.

## Data Flow Changes

### Existing live flow after extraction

```text
bot run
  → existing runtime factory
  → CycleService.run(RunKind.LIVE)
  → screen/build DataContext → live LLM → execute_signal_cycle
  → existing broker → audit run_attempt + decision → notification
```

Behavior remains the same; only orchestration moves out of `cli.py` and failures gain durable attempt records.

### Historical replay flow

```text
bot replay --from D1 --to DN --fixture baseline-v1
  → open separate replay DB
  → create experiment + policy/fixture/data fingerprints
  → for D1...DN in ascending order
      → ReplayDataSource.at(D)
      → screen_candidates(D, rows_available_at_D)
      → build DataContext from point-in-time bars
      → FixtureSignalProvider(date, ticker)
      → unchanged execute_signal_cycle(dry_run=False, broker=shared MockBroker)
      → persist attempt + decision
      → after decision: compute/store forward outcome in separate table
  → aggregate experiment metrics/report
```

`dry_run=False` is correct inside replay because the injected broker is in-memory and must mutate to model portfolio state. Safety comes from construction: replay service must reject any non-`MockBroker`/simulation broker and must not import KIS factories.

### KIS mock soak flow

```text
bot soak run --campaign C [--scenario normal]
  → assert TradingMode.MOCK + mock domain + mock TR profile + mock account
  → build live data/provider + existing KISBroker against KIS mock
  → CycleService.run(RunKind.SOAK, ExecutionTarget.KIS_MOCK)
  → persist every attempt, reconciliation, timing, and failure stage
  → render one-run summary; later `bot report soak --campaign C`
```

Duplicate-order evidence should come from repeating a controlled mock order and observing `KISBroker` query-before-POST reconciliation. API failure, stale data, and timeout scenarios should use explicit fault adapters in offline/integration tests unless the external mock API naturally produces them; synthetic evidence must be labeled `synthetic` and never presented as KIS-observed evidence.

### Reporting and promotion flow

```text
operational/replay DB → query-only repository or backup snapshot
  → daily report / soak report / calibration report
  → immutable Markdown + JSON output
  → operator completes promotion checklist
  → separate explicit config change (existing real gate remains intact)
```

## Audit Report Contract

A daily report should show, at minimum:

1. Date, run IDs, run kind, execution target, mode, dry-run flag, completion status.
2. Candidate count and every candidate attempt, including pre-decision failures.
3. Parsed decision, confidence, final action, risk override, and no-trade reason.
4. Requested/filled quantity, broker order ID, and reconciliation outcome.
5. Errors grouped by stage (`screen`, `context`, `signal`, `risk`, `order-query`, `order-post`, `fill-readback`, `audit`, `notify`).
6. Policy and fixture versions used.
7. Explicit completeness warnings for open/incomplete runs or missing attempts.

Render both Markdown for the operator and JSON for tests/future tooling. The renderer should accept typed read models, not execute ad hoc SQL inline in Typer callbacks.

## Runbook and Promotion Checklist Boundary

The runbook is a first-class deliverable but remains documentation:

- Fixed Asia/Seoul timing and what “data for date D” means before/after market close.
- Exact `screen`, `status`, dry-run, KIS mock soak, report, and backup commands.
- Expected success markers and where the audit DB/log/report files live.
- Stage-based triage for authentication, throttling, stale/missing data, LLM timeout, ambiguous order result, notification failure, and SQLite lock/disk errors.
- “Stop and do not rerun order POST” guidance for ambiguous KIS execution; reconcile first.

The promotion checklist consumes evidence but does not alter code paths. Require a minimum completed-soak window, zero unresolved ambiguous orders, duplicate prevention evidence, failure-scenario evidence, report completeness, reviewed calibration sensitivity, backup/restore test, secret/log review, and an explicit rollback procedure. Any threshold/count should be a roadmap/product decision, not hard-coded by architecture research.

## Suggested Build Order

### Phase 1 — Audit completeness and cycle extraction

1. Add characterization tests around current `cli.run_cycle`, real confirmation, dry-run, ticker isolation, and broker selection.
2. Add transactional schema migrations and `run_attempts`; backfill compatibility for existing databases.
3. Extract `CycleService` and typed run models while keeping `bot run/screen/status` behavior unchanged.
4. Persist run completion/failure state in `finally` paths.

**Why first:** Replay, soak, and reports all depend on complete, stable run evidence. This phase has no reason to touch KIS order semantics.

### Phase 2 — Deterministic replay foundation

1. Add fixture signal provider and point-in-time replay data adapter.
2. Reuse pure screener/indicator/execution functions with a shared `MockBroker`.
3. Use a separate replay DB and store experiment provenance/outcomes.
4. Add no-look-ahead, determinism, and “no external calls” tests.

**Why second:** It validates policy plumbing cheaply before spending LLM calls or exercising KIS mock orders.

### Phase 3 — Reporting and runbook baseline

1. Add repository read models and daily/replay Markdown+JSON renderers.
2. Document daily commands, KST timing, backups, and failure-stage triage.
3. Test reports against complete, partial, failed, old-schema, and empty databases.

**Why here:** Operators need understandable evidence before a multi-day soak begins; building reports after soak risks collecting unusable data.

### Phase 4 — KIS mock soak and fault evidence

1. Add explicit mock-only KIS broker composition and soak command.
2. Add campaign metadata and N-day aggregation without adding a scheduler.
3. Exercise normal, duplicate/reconciliation, API unavailable, stale data, timeout, and partial/ambiguous fill paths.
4. Keep synthetic and externally observed scenarios distinguishable.

**Why after reporting:** Each soak day becomes immediately reviewable, and schema gaps appear before weeks of operation.

### Phase 5 — Risk calibration and promotion readiness

1. Add parameter-grid replay and sensitivity metrics.
2. Produce advisory recommendations tied to immutable evidence IDs.
3. Strengthen the real-money promotion checklist and rollback steps.
4. Do not modify the real broker/order path; any later policy change is a separate reviewed change with regression tests.

**Why last:** Calibration without enough replay/soak observations is false precision.

## Risk Boundaries and Invariants

| Boundary | Required invariant | Verification |
|---|---|---|
| Replay ↔ external systems | Replay cannot construct KIS, pykrx-current, news-current, or live LLM adapters. | Import/spy tests asserting zero network calls; type/factory allowlist. |
| Replay time | No datum with availability after epoch D reaches screening/context/signal. | Future-row perturbation test: changing D+1 onward cannot change decision at D. |
| Replay broker | Portfolio mutation is allowed only in the in-memory simulator. | Reject KIS broker types; test carried cash/positions across epochs. |
| Soak credentials | Soak accepts mock domain, mock TR profile, and mock account only. | Constructor assertions before token/order adapter creation. |
| Real execution | Existing `TradingMode.REAL` + confirmation + CLI live confirmation remain required. | Preserve existing tests; add negative tests from every new command. |
| Fault injection | Fault scenarios cannot be enabled accidentally in normal live/real composition. | Separate test module/factory and explicit enum; no permissive string dispatch. |
| Calibration | Analysis cannot write settings or invoke a broker. | Read-only repository and filesystem output only; dependency tests. |
| Audit | Every selected ticker gets an attempt terminal state, even if no decision exists. | Count equality and crash/exception tests. |
| Reporting | Missing evidence is displayed as unknown/incomplete, never inferred as success. | Golden reports for partial runs. |
| Sensitive data | Audit/report stores no secrets, raw auth headers, or unsanitized third-party content. | Schema and redaction tests. |

## Anti-Patterns

### Forking the execution rules for replay

**Why wrong:** A replay-only threshold/sizing implementation can pass while production behaves differently.
**Instead:** Call the unchanged `execute_signal_cycle` with different adapters.

### Reusing `MarketDataSource` unchanged for historical dates

**Why wrong:** It fetches a current KIS quote and current news, creating temporal leakage.
**Instead:** A replay-specific point-in-time data adapter builds the same `DataContext` contract.

### Treating `TradingMode.MOCK` as proof of KIS mock usage

**Why wrong:** Current CLI mock mode constructs `MockBroker`; no KIS mock order is sent.
**Instead:** Record `execution_target` separately and expose an explicit mock-only soak path.

### Recording only decisions

**Why wrong:** Context/LLM/order failures disappear from SQLite and reports overstate success.
**Instead:** Persist an attempt before each ticker pipeline and finalize its stage/status.

### Auto-tuning production settings

**Why wrong:** It turns noisy historical evidence into execution authority and can optimize to leakage or small samples.
**Instead:** Produce a reviewed recommendation artifact with sensitivity and sample-size warnings.

### Copying a WAL database file directly

**Why wrong:** The `.db` file alone may omit committed pages still represented in `-wal`.
**Instead:** Use SQLite's online backup API for a consistent report/export snapshot.

## Scaling Considerations

| Scale | Architecture adjustment |
|---|---|
| Personal bot, tens of tickers/day | SQLite WAL, synchronous services, one process, explicit CLI commands. Recommended v1.1 target. |
| Multi-year daily replay | Batch commits per epoch/transaction, indexes on run kind/date/campaign/ticker, optional Parquet only for large immutable market datasets. Keep audit facts in SQLite. |
| Multiple concurrent operators/processes | Add connection timeouts and short transactions first. Move audit persistence to Postgres only if measured lock contention appears. |
| Intraday/high-frequency future | Revisit event-driven clock/feed/execution simulation and transaction-cost models; out of scope for this milestone. |

The first likely bottleneck is pykrx historical retrieval and repeated indicator calculation, not SQLite. Cache immutable raw market data by source/date/fingerprint before changing database technology.

## Integration Points

### Internal boundaries

| Boundary | Communication | Notes |
|---|---|---|
| Typer ↔ application services | Typed command options → `RunSpec` | Keep callbacks thin and testable. |
| CycleService ↔ execution | Existing direct function call | Preserve the exact config/risk/dry-run inputs. |
| ReplayService ↔ CycleService | One explicit epoch/universe at a time | Shared simulation broker across epochs. |
| SoakService ↔ KISBroker factory | Mock-only typed factory | Validate all mock bindings atomically. |
| Services ↔ audit | Repository methods | No inline schema SQL outside audit package. |
| Report/calibration ↔ audit | Query-only read models or backup snapshot | Never share a long write transaction. |
| Docs ↔ CLI | Document tested commands/help output | Add doc tests or smoke scripts for command drift. |

### External services

| Service | v1.1 use | Boundary |
|---|---|---|
| pykrx | Historical daily data and replay rows | Cache/fingerprint; enforce point-in-time cutoff. |
| KIS quote API | Live/soak context only | Existing fail-closed freshness behavior. |
| KIS mock order API | Soak only | Existing reconciliation, no blind POST retry. |
| Anthropic/OpenAI | Normal live/soak only when explicitly selected | Replay uses fixture provider; strict schema remains. |
| Naver Finance | Live/soak optional news only | Exclude from historical replay unless point-in-time archives exist. |
| SQLite | Operational and replay evidence | Separate DB paths; migration/versioning; backup snapshots. |

## Confidence Assessment

| Area | Confidence | Basis |
|---|---|---|
| Existing integration seams | HIGH | Direct inspection of CLI, execution, data, broker, screener, audit, and tests. |
| New/modified component boundaries | HIGH | Follow existing ports/adapters and dependency injection patterns. |
| Audit migration/report strategy | HIGH | Codebase need plus official SQLite/Python behavior; provider seam confidence classified MEDIUM, cross-checked with primary docs. |
| Replay point-in-time architecture | MEDIUM | Strong general pattern and code fit; exact pykrx historical availability/corporate-action behavior needs phase-specific validation. |
| Risk metrics/calibration thresholds | MEDIUM | Architecture is clear, but acceptable sample sizes and promotion thresholds are product/risk decisions. |

## Open Questions for Phase Research

- Define the precise replay decision timestamp: previous close, same-day post-close, or next-session pre-open. This determines legal OHLCV windows and fill assumptions.
- Verify pykrx's handling of delisted symbols, adjusted prices, corporate actions, and historical universe membership before interpreting replay performance.
- Decide whether fixture signals are fixed globally, generated from deterministic technical rules, or supplied as per-date/per-ticker files. Store the choice as a versioned artifact.
- Define the KIS mock account identifiers and whether its daily order query reliably exposes duplicate/partial-fill evidence across separate invocations.
- Set minimum soak duration, acceptable unresolved error count, and calibration sample-size gates during requirements planning.

## Sources

### Codebase (HIGH)

- `.planning/PROJECT.md`, `.planning/MILESTONES.md`, `.planning/ROADMAP.md`
- `trading_bot/cli.py`, `execution.py`, `sqlite_audit.py`, `mock_broker.py`, `kis_broker.py`, `screener.py`, `data_source.py`, `domain.py`
- `tests/test_cli.py`, `tests/test_sqlite_audit.py`, and KIS order/config tests located through code search

### External (MEDIUM; fetched through research seam fallback and cross-checked)

- [SQLite `PRAGMA user_version`](https://www.sqlite.org/pragma.html#pragma_user_version) — application-owned schema version integer.
- [SQLite write-ahead logging](https://www.sqlite.org/wal.html) — concurrent read/write behavior, read-only considerations, and WAL lifecycle.
- [SQLite Online Backup API](https://www.sqlite.org/backup.html) — consistent database snapshots.
- [Python `sqlite3.Connection.backup`](https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.backup) — backup while other clients access the database.
- [Event-Driven Backtesting with Python](https://www.quantstart.com/articles/Event-Driven-Backtesting-with-Python-Part-I/) — adapter reuse and chronological data delivery to reduce look-ahead bias.
- [Look-Ahead-Freedom as Temporal Non-Interference](https://arxiv.org/abs/2607.04958) — availability cutoffs and causal joins/resampling; recent preprint, used as supporting rather than sole authority.

---
*Architecture research for: Stock Trading Bot v1.1 Mock Soak & Replay Validation*
*Researched: 2026-07-11*
