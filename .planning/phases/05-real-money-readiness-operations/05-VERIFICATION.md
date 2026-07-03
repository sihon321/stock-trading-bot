---
phase: 05-real-money-readiness-operations
verified: 2026-07-02T14:17:45Z
status: gaps_found
score: 14/15 must-haves verified
behavior_unverified: 0
overrides_applied: 0
gaps:
  - truth: "Every cycle's data context, LLM signal including confidence, risk decisions, and order outcome are written to a persistent, reviewable audit store"
    status: partial
    reason: "The SQLite schema and writer support confidence, but the production CLI path always writes confidence=None, so LLM confidence is not persisted end to end."
    artifacts:
      - path: "trading_bot/cli.py"
        issue: "run_cycle passes confidence=None to sqlite_audit.write_decision for every successful ticker."
      - path: "trading_bot/execution.py"
        issue: "ExecutionResult/CycleAuditEvent do not expose parsed signal confidence for the CLI to persist."
    missing:
      - "Carry parsed LLM signal confidence through the execution result/audit event or another production-safe result field."
      - "Update CLI audit writes and tests to assert stored confidence is non-null for parsed signals."
---

# Phase 5: Real-Money Readiness & Operations Verification Report

**Phase Goal:** The operator can run the full cycle on demand, every cycle is auditable and pushed to a notification channel, and real-money trading becomes possible only through an idempotent, reconciled KISBroker behind a deliberate promotion gate.
**Verified:** 2026-07-02T14:17:45Z
**Status:** gaps_found
**Re-verification:** No - initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|---|---|---|
| 1 | Manual CLI exposes `bot run`, `bot screen`, `bot status`; no scheduler/always-on loop | VERIFIED | `trading_bot/cli.py:29`, `352`, `377`, `391`; `pyproject.toml` registers `bot = "trading_bot.cli:app"`; scheduler scan found no scheduler package/loop. |
| 2 | `bot run` evaluates the screened universe by default and `--ticker` narrows to one code | VERIFIED | `trading_bot/cli.py:259-264`; `tests/test_cli.py:199-205`. |
| 3 | Dry-run is default, and real execute is refused without both config confirmation and `--live-confirm` | VERIFIED | `trading_bot/config.py:45-46`, `109-115`; `trading_bot/cli.py:236-242`; targeted tests passed. |
| 4 | Broker selection is mock in mock mode and KIS in real mode with one shared `KisTokenManager` | VERIFIED | `trading_bot/cli.py:103-117`, `128-149`, `160-180`; `tests/test_cli.py:208-247`. |
| 5 | KIS order path is direct REST, not `python-kis`, and reuses the shared token manager | VERIFIED | `trading_bot/kis_order.py` imports `KisTokenManager`; `pyproject.toml` has no `python-kis`; `build_kis_broker` requires caller-owned token manager at `trading_bot/kis_broker.py:216-247`. |
| 6 | Query-before-POST reconciles broker truth and skips duplicate orders | VERIFIED | `trading_bot/kis_broker.py:86-89`, `121-144`; `tests/test_kis_broker.py:107-130`; targeted test passed. |
| 7 | Order POST is single-shot, direct REST, mode-derived TR_ID, hashkey-backed, and not tenacity-retried | VERIFIED | `trading_bot/kis_order.py:243-287`, query retry is separate at `347-359`; `tests/test_kis_order.py:158-227`; targeted tests passed. |
| 8 | Partial fills are read back, requested-vs-filled is modeled, position reconciles to filled qty, no auto-chase POST | VERIFIED | `trading_bot/kis_order.py:289-324`; `trading_bot/kis_broker.py:96-109`, `156-195`; `tests/test_kis_broker.py:133-164`; targeted test passed. |
| 9 | Limit price is snapped to KRX tick band and market/stale preflight fails safe before POST | VERIFIED | `trading_bot/kis_order.py:123-145`; `trading_bot/kis_broker.py:111-115`; `tests/test_kis_broker.py:166-188`; targeted test passed. |
| 10 | Persistent SQLite audit store has normalized runs/decisions tables queryable by run and ticker | VERIFIED | `trading_bot/sqlite_audit.py:19-48`, `55-65`; `tests/test_sqlite_audit.py:24-80`; targeted test passed. |
| 11 | Audit rows include CycleAuditEvent fields, price, fill/order outcome, correlation id, and no raw prompt/response | FAILED | Schema/writer support these fields, but production CLI calls `write_decision(... confidence=None ...)` at `trading_bot/cli.py:298-307`; probe produced `('005930', 'BUY', None)`. |
| 12 | SQLite writer consumes frozen `CycleAuditEvent`, configurable gitignored DB path, WAL, per-row commit | VERIFIED | `trading_bot/sqlite_audit.py:55-65`, `89-147`; `trading_bot/config.py:103-107`; `.gitignore:11`; `tests/test_sqlite_audit.py:79-128`. |
| 13 | Notifier sends one consolidated per-run summary plus immediate error push | VERIFIED | `trading_bot/cli.py:317-342`; `trading_bot/notifier.py:125-165`; `tests/test_cli.py:250-269`; targeted test passed. |
| 14 | Discord notifier is fail-soft, bounded-retry, and secret-redacted | VERIFIED | `trading_bot/notifier.py:41-82`, `84-116`, `168-179`; `tests/test_notifier.py:41-105`; targeted test passed. |
| 15 | Phase 5 foundation exists: Typer dependency, adapter-free `Notifier` port, typed settings, audit DB gitignore | VERIFIED | `pyproject.toml:24`, `27-28`; `trading_bot/ports.py:41-47`; `trading_bot/config.py:103-107`; `.gitignore:11`. |

**Score:** 14/15 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `trading_bot/cli.py` | Typer CLI and operations wiring | PARTIAL | Substantive and wired; drops confidence before audit write. |
| `trading_bot/kis_order.py` | Direct REST KIS order/query adapter | VERIFIED | Query retry split, single-shot order POST, TR_ID selection, fill parsing, tick snap. |
| `trading_bot/kis_broker.py` | Reconciled `Broker` implementation | VERIFIED | Query-before-POST, duplicate skip, partial-fill position reconciliation, preflight guard. |
| `trading_bot/sqlite_audit.py` | Persistent two-table audit writer | VERIFIED | WAL, normalized schema, per-row commit, no raw prompt/response columns. |
| `trading_bot/notifier.py` | Fail-soft Discord notifier | VERIFIED | Consolidated formatting, bounded retry, no secret in body/repr/log assertions. |
| `trading_bot/config.py` / `trading_bot/ports.py` | Settings and `Notifier` port | VERIFIED | Typed audit/webhook/order settings; adapter-free runtime-checkable port. |
| `tests/test_cli.py`, `tests/test_kis_order.py`, `tests/test_kis_broker.py`, `tests/test_sqlite_audit.py`, `tests/test_notifier.py` | Offline behavior coverage | PARTIAL | Named safety tests pass; no CLI test asserts confidence persists end to end. |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| CLI dry-run default | execution dry-run gate | `dry_run = not execute` passed to `run_llm_cycle` | VERIFIED | `trading_bot/cli.py:236`, `281-290`; `tests/test_cli.py:151-160`. |
| Real execute gate | order path | refuse before collaborator use when real+execute lacks `--live-confirm` | VERIFIED | `trading_bot/cli.py:236-242`; test proves broker orders stay empty. |
| CLI | KIS broker + quote adapter | one `KisTokenManager` is constructed and passed into both | VERIFIED | `trading_bot/cli.py:160-180`. |
| KISBroker | KIS adapter | `place_order` performs query-before-POST then single POST then fill readback | VERIFIED | `trading_bot/kis_broker.py:82-109`. |
| CLI | SQLite audit | `start_run` and `write_decision` called per successful ticker | PARTIAL | Connected, but confidence argument is always `None`. |
| CLI | Notifier | immediate error send and final consolidated send | VERIFIED | `trading_bot/cli.py:317-342`. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|---|---|---|---|---|
| `trading_bot/cli.py` | candidate tickers | `data_source.screen_daily_candidates` or `--ticker` | Yes | FLOWING |
| `trading_bot/cli.py` | context/current price | `data_source.build_context(Ticker(symbol))` | Yes | FLOWING |
| `trading_bot/cli.py` | audit confidence | intended parsed LLM signal confidence | No | HOLLOW - hardcoded `None` at production write site. |
| `trading_bot/kis_broker.py` | fills/positions | `read_fill_status` after POST | Yes | FLOWING |
| `trading_bot/notifier.py` | notification body | accumulated per-ticker outcomes | Yes | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| CLI live gate, dry-run, isolation, immediate error push | `pytest -q tests/test_cli.py::test_real_execute_requires_live_confirm ... ::test_immediate_error_push` | 4 passed | PASS |
| KIS order no-retry, TR_ID/hashkey/body, fill parsing, duplicate skip, partial fill, market guard | `pytest -q tests/test_kis_order.py::test_order_cash_post_not_retried ... tests/test_kis_broker.py::test_tick_snap_and_market_guard` | 7 passed | PASS |
| Audit and notifier behavior | `pytest -q tests/test_sqlite_audit.py::test_two_table_write ... tests/test_notifier.py::test_fail_soft` | 4 passed | PASS |
| Typer app import | `python3 -c "from trading_bot.cli import app; print(app)"` | printed Typer object | PASS |
| CLI audit confidence end-to-end | injected one-ticker dry-run probe, queried `decisions` table | stored `confidence` was `NULL` | FAIL |

### Probe Execution

No phase-declared or conventional `scripts/*/tests/probe-*.sh` probes were found.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| OPS-01 | 05-04 | Manual full-cycle CLI, no scheduler | SATISFIED | CLI run/screen/status, universe loop, no scheduler scan, tests pass. |
| OPS-02 | 05-03 / 05-04 | Persist data context, LLM signal, risk decisions, order outcome | BLOCKED | Audit store exists, but LLM signal confidence is not persisted by production CLI path. |
| OPS-03 | 05-03 / 05-04 | Push decision/order outcome to operator | SATISFIED | Discord notifier behind port, consolidated summary and immediate error push tests pass. |
| EXEC-04 | 05-02 | KIS idempotent reconciled order path, no blind retry, partial fills | SATISFIED | Direct REST adapter, query-before-POST, single-shot POST, partial fill tests pass. |
| CFG-04 | 05-01 / 05-04 | Mock default and deliberate real promotion | SATISFIED | Settings mock default, config real confirmation, CLI `--live-confirm` gate, tests pass. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---:|---|---|---|
| `trading_bot/cli.py` | 302 | Hardcoded `confidence=None` in production audit write | BLOCKER | Prevents complete per-cycle audit of the LLM signal. |

### Human Verification Required

These are not counted as automated blockers while the audit gap remains, but they still require operator validation before real external operation:

1. **KIS mock-account live order path**
   **Test:** With live KIS mock credentials and an open market session, run `bot run --ticker <code> --execute --live-confirm` under `TRADING_MODE=real` and `CONFIRM_REAL_TRADING=yes`.
   **Expected:** The order appears in KIS broker truth; re-running after a transport uncertainty reconciles and skips duplicate POST.
   **Why human:** Requires live KIS credentials, external KIS service, and market/session state.

2. **Discord delivery**
   **Test:** Set `DISCORD_WEBHOOK_URL`, run a dry-run cycle, and inspect the Discord channel.
   **Expected:** One consolidated summary arrives; on a forced per-ticker error, an immediate error message also arrives.
   **Why human:** Requires an external Discord webhook and network delivery.

### Gaps Summary

Phase 05 is largely implemented and the high-risk real-money controls are covered by offline behavior tests: manual CLI, dry-run default, real-money gate, single-shot KIS POST, query-before-POST reconciliation, partial-fill reconciliation, broker selection, audit store, and fail-soft notification all exist and are wired.

The blocking gap is audit completeness. The database schema and unit-level writer support confidence, but the production CLI path writes `None` for confidence every time. That means OPS-02 and the roadmap criterion for every cycle's LLM signal to be auditable are only partially achieved.

---

_Verified: 2026-07-02T14:17:45Z_
_Verifier: the agent (gsd-verifier)_
