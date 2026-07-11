# Stack Research

**Domain:** v1.1 operational confidence for an existing Korean-market LLM trading bot
**Researched:** 2026-07-11
**Confidence:** HIGH for local integration and dependency recommendations; MEDIUM for ecosystem comparisons

## Executive Summary

**Recommendation: add no runtime dependency for v1.1.** The shipped stack already contains every capability this milestone needs. Reuse Python standard-library `sqlite3`, `csv`, `json`, `statistics`, `datetime`, `zoneinfo`, `pathlib`, and `hashlib`; the pinned `typer==0.26.8` CLI; existing pandas/pykrx data frames; and `pytest==8.4.2`. Build small project modules for replay, reporting, policy metrics, and soak orchestration instead of adopting a backtesting or analytics framework.

The architectural change is additive, not a stack migration. Historical replay should inject point-in-time OHLCV rows and fixture signals into the existing pure screener and `execute_signal_cycle()` rules. It must never instantiate an LLM provider or KIS network adapter. Reports should query the existing SQLite audit store and render stable plain text through `typer.echo`, with optional CSV/JSON export from the standard library. Calibration should calculate descriptive threshold-grid metrics from replay/soak observations; it should recommend candidate settings but never mutate production settings or promote real trading automatically.

The current two-table audit schema needs evolution before it can prove a soak. Today it records run headers and successful per-ticker decisions, but ticker exceptions are only returned/notified, and a run has no terminal status, completion timestamp, source (`live`, `mock_soak`, `replay`), replay date, or policy snapshot. Add those fields plus durable per-ticker error/outcome records using forward-only, idempotent migrations. This is a data-model gap, not a reason to replace SQLite.

Keep the manual operator posture. A runbook is documentation plus deterministic CLI behavior; it does not justify APScheduler, cron integration, a daemon, a task queue, a notebook stack, or a dashboard. The v1.1 confidence claim should come from repeatable fixtures, explicit dates/clocks, persisted outcomes, and reviewable reports.

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | `>=3.10` (current project constraint) | Replay engine, report/calibration logic, KST handling | The standard library supplies SQLite access, CSV/JSON output, descriptive statistics, paths, hashing, and `zoneinfo`. Keep the existing compatibility floor; v1.1 needs no newer language feature. |
| SQLite via `sqlite3` | stdlib; runtime SQLite varies by Python build | Canonical run, decision, error, replay, and policy evidence | Existing store is already WAL-enabled and keyed by `run_id`. The expected personal-bot volume is small, read-mostly, and single-operator; SQL `GROUP BY`, filtered aggregates, indexes, and joins are sufficient. |
| Typer | `0.26.8` pinned locally | `bot replay`, `bot report`, and soak/readiness command surface | It is already the composition root and its `CliRunner` is already used in tests. Typed options and explicit exit codes cover dates, fixture paths, output formats, and fail-closed validation. |
| Existing pure domain core | current repository | Deterministic screener, execution gate, sizing, risk precedence | `screen_candidates()`, `evaluate_signal_action()`, `evaluate_position_risk()`, and `execute_signal_cycle()` already accept explicit values/config. Replaying these exact functions avoids a second implementation that could disagree with live behavior. |
| pytest | `8.4.2` pinned locally | Fixture replay and failure-matrix verification | Built-in fixtures, `tmp_path`, `monkeypatch`, and parametrization cover all required scenarios. No test plugin is needed. |

### Standard-Library Additions (No Installation)

| Module | Purpose | When to Use |
|--------|---------|-------------|
| `dataclasses` / `typing` | Frozen replay cases, report rows, policy snapshots, result protocols | Define explicit inputs/outputs for replay and reporting; do not pass loose dictionaries across the domain boundary. |
| `datetime` + `zoneinfo.ZoneInfo("Asia/Seoul")` | Trading-date windows and daily report grouping | Persist canonical UTC ISO-8601 timestamps, then convert to KST in Python before deriving the report date. Never depend on host local time. |
| `csv` | Fixture ingestion and report export | Use for human-reviewable OHLCV/signal fixtures and spreadsheet-friendly audit exports. Validate headers/types before use. |
| `json` | Fixture manifest, policy snapshot, machine-readable report | Use sorted keys and stable separators when hashing/serializing replay inputs. Reject unknown schema versions and malformed values. |
| `statistics` | Median/quantile-like descriptive summaries | Use for small calibration summaries. Explicitly implement or document percentile convention; avoid pretending descriptive metrics are predictive validation. |
| `hashlib` | Replay provenance | Hash canonical fixture contents plus policy/config snapshot so reruns can prove identical inputs. |
| `pathlib` | Fixture/output paths | Pair with Typer path validation; keep replay inputs read-only and outputs explicit. |
| `sqlite3.Row` | Named report query rows | Set `row_factory` on reporting connections to prevent fragile positional-column logic. |

### Existing Libraries to Reuse

| Library | Version | Purpose in v1.1 | Integration Point |
|---------|---------|-----------------|-------------------|
| pandas | existing transitive dependency of `pykrx`/`ta` | OHLCV fixture DataFrames and rolling indicator inputs | Use only at the existing data/indicator boundary. Do not use pandas as the audit-report database layer. |
| pykrx | `1.2.8` pinned | Optional fixture acquisition outside deterministic replay | Fetch and freeze historical data in a separate preparation step; replay itself reads frozen fixtures and performs no network calls. |
| structlog | `25.5.0` pinned | Correlated operational diagnostics | Keep detailed network/LLM diagnostics in logs, linked by `correlation_id`; persist reportable status/reason fields in SQLite. |
| Pydantic | `2.13.4` pinned | Validate any new settings/fixture manifest model | Use for external/config boundaries where it is already standard. Keep hot replay row transforms as simple typed data unless validation adds value. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `pytest==8.4.2` | Unit, integration, replay-golden, and CLI tests | Use explicit fixtures and parameter matrices. Keep live KIS soak checks separately marked/manual because they are nondeterministic external integration tests. |
| `typer.testing.CliRunner` | CLI contract tests | Assert exit code, stdout, and stderr independently for `replay`, `report`, and readiness commands. |
| `tmp_path` + in-memory SQLite | Isolated test artifacts | Use a real temporary DB when migration/reopen/WAL behavior matters; use `:memory:` for pure query/writer tests. |

## Required Project Modules and Integration Points

These are local modules, not packages to install.

| Module/Change | Responsibility | Reuses |
|---------------|----------------|--------|
| `trading_bot/replay.py` | Load a versioned fixture manifest, iterate dates in stable order, run screener and fixture signal through execution/risk gates, emit typed replay outcomes | `screen_candidates`, `execute_signal_cycle`, `MockBroker`, existing config builders |
| `trading_bot/reporting.py` | Read-only audit queries, KST grouping, plain-text/CSV/JSON renderers | `sqlite3`, `csv`, `json`, `zoneinfo`, `typer.echo` |
| `trading_bot/calibration.py` | Compare observed outcomes across explicit policy candidates and produce evidence/recommendations | `statistics`, existing `ExecutionConfig`/`RiskConfig`; no settings writes |
| `trading_bot/soak.py` or a thin CLI service | Record planned run identity, execute one bounded mock cycle, finalize run status, evaluate checklist counters | Existing `run_cycle`, notifier, audit connection; no scheduler |
| `trading_bot/sqlite_audit.py` extensions | Forward-only schema migration, run finalization, per-ticker outcomes/errors, replay/policy metadata, report queries | Existing DB and correlation IDs |
| `trading_bot/cli.py` commands | Parse/validate operator inputs and delegate to services | Existing Typer app; keep domain/report logic out of command functions |

### Audit Schema Evolution

Prefer an idempotent migration mechanism (`schema_migrations(version INTEGER PRIMARY KEY, applied_at TEXT NOT NULL)`) over continuing to grow one `CREATE TABLE IF NOT EXISTS` script. Recommended additive data:

| Storage | Additions | Why |
|---------|-----------|-----|
| `runs` | `completed_at`, `status`, `run_kind`, `trading_date`, `error_count`, `policy_snapshot_json`, `input_fingerprint` | Distinguishes incomplete/failed/successful runs, replay from soak/live, and the exact policy/input used. |
| `outcomes` (preferred new table) | one row per attempted ticker: status, stage, reason/error type, candidate rank/score where applicable, final action/order fields, timestamps | Current `decisions` omits ticker failures, so soak reports cannot calculate attempted vs completed/error rates. A unified outcome table avoids overloading valid decisions with exceptions. |
| `decisions` | Keep for validated execution decisions; optionally add FK to outcome | Preserve v1.0 compatibility and existing reports/tests. Do not rewrite historical rows. |
| Indexes | `(run_kind, started_at)`, `(status, started_at)`, outcome `(run_id, ticker)`, decision `(created_at, final_action)` | Supports bounded daily and readiness queries without an analytics database. |

Use parameterized SQL only. Reporting should open the DB read-only where practical and must not run migrations implicitly during a report command; migration belongs at controlled application startup or an explicit schema initializer.

## Deterministic Replay Contract

1. A replay case names a schema version, fixture ID, KRX trading date, ordered OHLCV/screener rows, fixture signal(s), starting cash/positions, and a complete execution/risk/screener policy snapshot.
2. Normalize rows and process dates/tickers in explicit stable order. The screener already tie-breaks by ticker; preserve that ordering downstream.
3. Use frozen historical inputs only. No pykrx, KIS, Naver, LLM, wall clock, random UUID, or notification call is allowed inside replay evaluation.
4. Inject `run_id`, `trading_date`, and timestamps (or a clock callable). Do not add `freezegun` to hide implicit time reads; remove those reads from replayable code.
5. Run fixture signals through the real parser and execution core. Do not construct an already-qualified action, because that would bypass strict JSON, confidence, risk, sizing, and no-trade reasons.
6. Default replay to simulation with `MockBroker`; prohibit a real broker type at the service boundary, not merely in the CLI.
7. Persist/emit an input fingerprint and policy snapshot. The same fixture + policy must produce the same selected tickers, actions, quantities, reasons, and ending mock state.

## Report Formatting Recommendation

Default to stable plain text from a pure renderer, printed with `typer.echo`. Provide `--format text|json|csv` and `--output PATH` only if needed by the requirement. Text output should include a run/day summary followed by deterministic rows ordered by KST date, start time, run ID, candidate rank, and ticker.

Do not optimize for terminal decoration. Stable, diffable output is more valuable during soak review than color, live tables, or auto-sized columns. If terminal readability later becomes a demonstrated problem, Rich can be added as presentation-only without changing report queries or models.

## Risk Calibration Stack

Use a bounded policy grid implemented with `itertools.product` over approved candidate values for:

- BUY/SELL confidence threshold
- cash fraction and max-position cap
- stop-loss and take-profit percentages

For each policy snapshot, rerun the identical frozen cases and report counts/rates such as qualified BUYs, no-trades by reason, risk exits, order intents, rejected/errored outcomes, turnover proxy, max position exposure, and—only when later prices are part of the fixture—clearly defined forward-return/drawdown summaries. Preserve raw counts beside percentages and enforce minimum sample-size warnings. Calibration output is advisory: promotion remains a human checklist decision.

Do not use an optimizer or statistical-learning library in v1.1. The data volume and milestone goal support transparent threshold sweeps, not fitted policy claims.

## Test Strategy

### Fixture Layout

```text
tests/fixtures/replay/
  manifest-v1.json
  20260701-market.csv
  20260701-signals.json
  20260702-market.csv
  20260702-signals.json
```

Small inline fixtures are preferable for unit tests; file fixtures should cover loader/schema/provenance and end-to-end replay. Keep source fixtures immutable and write generated outputs under `tmp_path`.

### Required Test Layers

| Layer | Cases | Technique |
|-------|-------|-----------|
| Pure replay unit | stable ordering, confidence boundary (`0.799...`, `0.8`), sizing floor, risk precedence, stop/take boundaries | `pytest.mark.parametrize`; direct pure-function calls |
| Fixture validation | missing columns, duplicate ticker/date, non-finite prices, stale date, unknown schema version, malformed signal | Temp fixture files; assert fail-closed result and no order |
| Replay determinism | identical fixture/policy run twice yields identical domain output and fingerprint | Inject run ID/clock; compare normalized results, not generated timestamps |
| Audit migration | upgrade a v1.0-shaped DB, reopen it, rerun migration, preserve old rows | `tmp_path` SQLite file; assert migration idempotence and indexes |
| Reporting | UTC timestamps crossing KST midnight, incomplete runs, ticker errors, no decisions, mixed dry/execute runs | Seed SQLite rows; golden text plus parsed JSON/CSV assertions |
| Soak failure matrix | duplicate/reconciled order, API 4xx/5xx, timeout, stale OHLCV/quote, malformed signal, notifier failure, interrupted run | Existing fakes plus parameterized fault doubles; assert durable terminal status/reason |
| CLI contract | invalid date/path/format, default safe mode, requested range, nonzero exit on incomplete evidence | Existing `CliRunner`; assert stdout/stderr and exit codes |
| Manual KIS mock soak | real token/account integration and KIS reconciliation behavior | Explicit opt-in marker and credentials; never part of default offline test suite |

Avoid snapshotting volatile banners, UUIDs, or timestamps. Golden files are appropriate only for normalized report/replay output with an intentional update process.

## Installation

No v1.1 package addition is recommended.

```bash
# Existing environment is sufficient.
python -m pytest

# If the project environment uses uv, sync the existing lock/manifest only.
uv sync
```

Do not add optional packages preemptively. If dependencies are later reorganized, move `pytest==8.4.2` from runtime `dependencies` to a development extra/group; that cleanup is sensible but not required to deliver v1.1.

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| stdlib `sqlite3` queries | DuckDB | Only after audit/replay history becomes large analytical data (for example Parquet collections or joins that are measurably awkward/slow in SQLite). |
| plain Typer text + CSV/JSON | Rich/Textual | Add Rich only when operators demonstrably need wrapped/colorized tables. Textual is inappropriate unless the product intentionally becomes an interactive TUI. |
| explicit clock/date injection | freezegun | Use only if legacy code with pervasive direct clock reads cannot be safely refactored. New replay code should accept time explicitly. |
| pytest fixtures/parametrization | Hypothesis | Add later for property-based invariants once concrete replay cases are stable and there is a specific state-space bug class to explore. |
| existing pandas at data boundary | Polars | Consider only if measured replay throughput is blocked by pandas. It would duplicate the existing pykrx/ta DataFrame ecosystem today. |
| transparent policy grid | NumPy/SciPy optimizer | Use only for a later, statistically designed research milestone with enough independent observations and explicit overfitting controls. |
| local replay harness | backtrader/vectorbt/zipline | Use in a future full portfolio backtest requiring fills, commissions, corporate actions, benchmark analytics, or multi-strategy accounting. v1.1 explicitly needs backtest-lite gate replay. |
| manual bounded cycle | APScheduler/Celery/Prefect | Add only if the product scope changes to unattended scheduling or distributed workflows. Current milestone retains operator-triggered cycles. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| A second execution/risk implementation inside replay | It can validate itself while disagreeing with production—the most dangerous false confidence. | Call the existing pure screener, parser, execution, and risk functions. |
| Live pykrx/KIS/LLM calls during deterministic replay | Vendor revisions, market state, latency, cost, and model nondeterminism make results irreproducible. | Acquire once, validate, freeze, version, and hash fixtures. |
| A full backtesting framework | Adds fill models, event engines, portfolio abstractions, and semantics outside the milestone; integration may bypass current gates. | Small replay service around existing functions and `MockBroker`. |
| Rich as a mandatory report dependency | Presentation does not solve missing outcome/status data and makes golden output less stable. | Plain text plus stdlib CSV/JSON. |
| DuckDB/Postgres | Additional storage/migration/operations burden without a concurrency or scale requirement. | Evolve the existing SQLite schema and indexes. |
| freezegun | Masks implicit clock coupling and is unnecessary because CLI already accepts explicit trading dates in key paths. | Inject date/time/run IDs into replay and report services. |
| Jupyter notebooks as the canonical calibration path | Harder to test, reproduce, review, and invoke from the operational CLI. | Pure calibration module with deterministic CLI output; notebooks may consume exported data later. |
| Automatic policy writes or real-money promotion | A favorable replay can be overfit or incomplete and must not bypass the deliberate safety gate. | Emit an evidence report and human checklist; require explicit config review/change. |
| CSV as the canonical audit store | Weak relational integrity and awkward updates/grouping for run/outcome status. | SQLite as source of truth; CSV only as fixture/export format. |
| Test-only custom KIS behavior in production modules | Risks shipping fault injection into the order path. | Protocol-compatible fakes/fault doubles under tests; manual mock-account probes through real adapters. |

## Stack Patterns by Variant

**Offline replay / calibration:**
- Frozen fixture inputs, `MockBroker`, injected clock/run ID, notifications disabled.
- No network-capable collaborator may be constructed.

**Daily mock soak:**
- Existing real market/LLM adapters as configured, mock trading mode, bounded single cycle, durable start/finalize records.
- Record every attempted ticker including failures; reconcile duplicate/ambiguous orders through the existing KIS logic.

**Audit review:**
- Read-only SQLite connection, explicit KST report window, deterministic text/CSV/JSON renderer.
- Report incomplete runs and missing evidence prominently instead of silently excluding them.

**Real-money readiness:**
- Query completed mock soak and replay evidence against explicit checklist thresholds.
- Output pass/fail/insufficient-evidence per criterion; never switch `TRADING_MODE` or credentials.

## Version Compatibility

| Package/Runtime | Compatible With | Notes |
|-----------------|-----------------|-------|
| Python `>=3.10` | `zoneinfo`, dataclass slots if desired, current project APIs | Keep code on the declared floor. The local shell interpreter observed during research was Python 3.14.3 with SQLite 3.51.3, but deployed SQLite features must not assume that exact build. |
| SQLite | Basic joins, aggregates, indexes, ISO text timestamps | Restrict core queries/migrations to widely available SQLite features under Python 3.10 builds. Test the actual runtime via `sqlite3.sqlite_version`; do not require recent JSON/window extensions unless explicitly guarded. |
| Typer `0.26.8` | Existing `app.command` and `CliRunner` patterns | Add commands to the current app; avoid a parallel CLI framework. |
| pytest `8.4.2` | Python `>=3.10` project floor | Existing tests already use `tmp_path`, `monkeypatch`, parametrization, and `CliRunner`; continue those conventions. |
| pandas / pykrx / ta | Existing OHLCV/indicator pipeline | Freeze fixture schema at the project adapter boundary, not as pickled DataFrames, to avoid library-version-dependent serialization. |
| Existing audit DB | Additive v1.1 migration | Preserve v1.0 `runs` and `decisions`; migrations must be idempotent and tested from a v1.0 fixture DB. |

## Sources

- Local `pyproject.toml`, `.planning/PROJECT.md`, `.planning/MILESTONES.md`, `.planning/ROADMAP.md` — shipped stack, pinned versions, milestone scope — **HIGH**
- Local `trading_bot/cli.py` and `tests/test_cli.py` — Typer command composition, explicit trading date, injectable collaborators, existing `CliRunner` practice — **HIGH**
- Local `trading_bot/sqlite_audit.py` and `tests/test_sqlite_audit.py` — two-table schema, WAL, persisted fields, and current failure-evidence gap — **HIGH**
- Local `trading_bot/execution.py`, `risk.py`, `screener.py`, and `mock_broker.py` — pure deterministic seams and production-rule reuse — **HIGH**
- [Python `sqlite3` documentation](https://docs.python.org/3/library/sqlite3.html) — parameterized SQL, transactions, row factories, in-memory/disk connections — **MEDIUM** (official source via websearch seam)
- [Python `csv` documentation](https://docs.python.org/3/library/csv.html), [JSON documentation](https://docs.python.org/3/library/json.html), [statistics documentation](https://docs.python.org/3/library/statistics.html), and [zoneinfo documentation](https://docs.python.org/3/library/zoneinfo.html) — no-dependency export, summaries, and KST conversion — **MEDIUM**
- [SQLite date/time documentation](https://www.sqlite.org/lang_datefunc.html) — available SQL date functions and portability considerations — **MEDIUM**
- [pytest fixtures](https://docs.pytest.org/en/stable/explanation/fixtures.html), [parametrization](https://docs.pytest.org/en/stable/how-to/parametrize.html), and [monkeypatch guidance](https://docs.pytest.org/en/stable/how-to/monkeypatch.html) — deterministic fixture and fault-injection patterns — **MEDIUM**
- [Typer testing documentation](https://typer.tiangolo.com/tutorial/testing/) — `CliRunner`, exit-code, stdout, and stderr testing — **MEDIUM**

---
*Stack research for: Stock Trading Bot v1.1 Mock Soak & Replay Validation*
*Researched: 2026-07-11*
