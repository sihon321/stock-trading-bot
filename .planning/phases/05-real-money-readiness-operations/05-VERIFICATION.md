---
phase: 05-real-money-readiness-operations
verified: 2026-07-03T10:20:00Z
status: human_needed
score: 15/15 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 14/15
  gaps_closed:
    - "Every cycle's data context, LLM signal including confidence, risk decisions, and order outcome are written to a persistent, reviewable audit store (OPS-02)"
  gaps_remaining: []
  regressions: []
human_verification:
  - test: "With live KIS mock credentials and an open market session, run `bot run --ticker <code> --execute --live-confirm` under `TRADING_MODE=real` and `CONFIRM_REAL_TRADING=yes`."
    expected: "The order appears in KIS broker truth; re-running after a transport uncertainty reconciles and skips the duplicate POST (idempotent, query-before-POST)."
    why_human: "Requires live KIS credentials, the external KIS service, and market/session state — cannot be exercised offline."
  - test: "Set `DISCORD_WEBHOOK_URL`, run a dry-run cycle, and inspect the Discord channel."
    expected: "One consolidated per-run summary arrives; on a forced per-ticker error, an immediate error message also arrives."
    why_human: "Requires an external Discord webhook and real network delivery."
---

# Phase 5: Real-Money Readiness & Operations Verification Report

**Phase Goal:** The operator can run the full cycle on demand, every cycle is auditable and pushed to a notification channel, and real-money trading becomes possible only through an idempotent, reconciled KISBroker behind a deliberate promotion gate.
**Verified:** 2026-07-03T10:20:00Z
**Status:** human_needed
**Re-verification:** Yes — after gap-closure plan 05-05 (OPS-02 confidence persistence)

## Re-Verification Summary

The prior 05-VERIFICATION.md recorded a single blocking gap: the parsed LLM signal's `confidence` was never persisted end-to-end because `cli.py` hardcoded `confidence=None` at the audit write site (former line 302). Plan 05-05 threaded `parsed.signal.confidence` through a new `ExecutionResult.confidence` field out of `execute_signal_cycle`, made the CLI read `result.confidence` at the write site, and added an end-to-end SQLite round-trip test.

**Verdict: the gap is genuinely closed in the codebase.** Confirmed by reading the actual source (not the SUMMARY) and by an independent mutation test proving the fix is load-bearing. All 15 must-haves now verify. The two remaining `human_needed` items are the same external-dependency checks flagged in the prior verification (live KIS order path, Discord delivery); they were never automated blockers and are unchanged.

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|---|---|---|
| 1 | Manual CLI exposes `bot run`, `bot screen`, `bot status`; no scheduler/always-on loop | VERIFIED (regression) | Unchanged from prior verify; `pyproject.toml` registers `bot`; no scheduler package. |
| 2 | `bot run` evaluates screened universe by default and `--ticker` narrows to one code | VERIFIED (regression) | `trading_bot/cli.py:259-264`; universe loop intact. |
| 3 | Dry-run is default; real execute refused without config confirmation and `--live-confirm` | VERIFIED (regression) | `trading_bot/cli.py:236-242`; `test_real_execute_requires_live_confirm` passed; `test_dry_run_default_no_orders` passed. |
| 4 | Broker is mock in mock mode and KIS in real mode with one shared `KisTokenManager` | VERIFIED (regression) | Unchanged; broker-selection wiring intact. |
| 5 | KIS order path is direct REST (not `python-kis`) and reuses the shared token manager | VERIFIED (regression) | Unchanged; `pyproject.toml` has no `python-kis`. |
| 6 | Query-before-POST reconciles broker truth and skips duplicate orders | VERIFIED (regression) | `tests/test_kis_broker.py` full file passed. |
| 7 | Order POST is single-shot, direct REST, mode-derived TR_ID, hashkey-backed, not tenacity-retried | VERIFIED (regression) | `test_order_cash_post_not_retried` passed. |
| 8 | Partial fills are read back; requested-vs-filled modeled; position reconciles to filled qty; no auto-chase POST | VERIFIED (regression) | `tests/test_kis_broker.py` full file passed. |
| 9 | Limit price snapped to KRX tick band; market/stale preflight fails safe before POST | VERIFIED (regression) | `tests/test_kis_broker.py` full file passed. |
| 10 | Persistent SQLite audit store has normalized runs/decisions tables queryable by run and ticker | VERIFIED (regression) | `trading_bot/sqlite_audit.py:19-48`; `test_two_table_write` passed. |
| 11 | Audit rows include CycleAuditEvent fields, price, fill/order outcome, correlation id, confidence, and no raw prompt/response | VERIFIED (gap closed) | `cli.py:302` now `confidence=result.confidence`; `sqlite_audit.py:133` binds it to the REAL column; end-to-end test reads back non-null 0.95; mutation test confirms load-bearing. |
| 12 | SQLite writer consumes frozen `CycleAuditEvent`, configurable gitignored DB path, WAL, per-row commit | VERIFIED (regression) | `sqlite_audit.py:55-65,89-147`; `CycleAuditEvent` (execution.py:59-75) unchanged and still frozen; `test_two_table_write` passed. |
| 13 | Notifier sends one consolidated per-run summary plus immediate error push | VERIFIED (regression) | `test_immediate_error_push` passed. |
| 14 | Discord notifier is fail-soft, bounded-retry, secret-redacted | VERIFIED (regression) | `test_fail_soft` passed. |
| 15 | Confidence rides `ExecutionResult` (not `CycleAuditEvent`); parse-error path leaves it NULL (fail-safe, D-10/D-11) | VERIFIED (gap closed) | `execution.py:94,220`; three parsed call-sites pass `confidence=confidence` (lines 290,313,340), parse-error site (254-266) omits it; fail-safe asserted in end-to-end test (failing ticker writes no row). |

**Score:** 15/15 truths verified (0 present, behavior-unverified)

### Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `trading_bot/execution.py` | Threads parsed confidence via `ExecutionResult` without touching frozen `CycleAuditEvent` | VERIFIED | `ExecutionResult.confidence` appended last (line 94); `_finalize_cycle` keyword threaded (line 220); three parsed branches pass it, parse-error branch omits it; `CycleAuditEvent` (59-75) byte-identical, still `frozen=True`. |
| `trading_bot/cli.py` | Reads `result.confidence` at the audit write and outcome sites | VERIFIED | Line 205 `_outcome_from_result` reads `result.confidence`; line 302 `write_decision(confidence=result.confidence)`; line 324 error path keeps `None` (correct — no parsed signal). |
| `trading_bot/sqlite_audit.py` | Persistent two-table audit writer with confidence REAL column | VERIFIED | `confidence REAL` column (line 33); bound at line 133; WAL, per-row commit. Unchanged this plan; sink was already ready. |
| `tests/test_cli.py` | End-to-end confidence-persistence test through the real write sink | VERIFIED | `test_confidence_persisted_end_to_end` (199-247) drives real `_run_llm_cycle -> execute_signal_cycle`, round-trips SQLite, asserts non-null 0.95 and NULL-on-failure. |
| `trading_bot/kis_order.py`, `trading_bot/kis_broker.py`, `trading_bot/notifier.py`, `trading_bot/config.py`, `trading_bot/ports.py` | Prior-phase artifacts | VERIFIED (regression) | Unchanged since prior verify; targeted safety tests re-passed. |

### Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| `parsed.signal.confidence` | `ExecutionResult.confidence` | `_finalize_cycle(confidence=confidence)` from parsed branches | VERIFIED | `execution.py:269,290,313,340,220`. |
| `ExecutionResult.confidence` | `decisions.confidence` column | `write_decision(confidence=result.confidence)` | VERIFIED | `cli.py:302` -> `sqlite_audit.py:133`; end-to-end test reads back 0.95. |
| LLM signal | real cycle path | `run_llm_cycle` serializes `signal.confidence` to raw_signal JSON, `execute_signal_cycle` re-parses | VERIFIED | `llm_provider.py:358-366`; confidence survives serialize/parse round-trip. |
| Parse-error path | `decisions.confidence` NULL | parse-error `_finalize_cycle` never sets confidence | VERIFIED | `execution.py:254-266`; test asserts failing ticker writes no row (no spurious non-null). |
| CLI dry-run / live gate / broker / notifier | prior links | (unchanged) | VERIFIED (regression) | Targeted tests re-passed. |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|---|---|---|---|---|
| `trading_bot/cli.py` | audit confidence | `result.confidence` from `execute_signal_cycle` (was hardcoded `None`) | Yes | FLOWING — end-to-end test reads back non-null 0.95 |
| `trading_bot/cli.py` | candidate tickers / context | screener / `build_context` | Yes | FLOWING |
| `trading_bot/kis_broker.py` | fills/positions | `read_fill_status` after POST | Yes | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Confidence persists end-to-end through real cycle + SQLite | `pytest -q tests/test_cli.py::test_confidence_persisted_end_to_end` | 1 passed (stored confidence == 0.95) | PASS |
| Fix is load-bearing (not tautological) | Reverted `cli.py:302` to `confidence=None`; re-ran the test | 1 failed (`assert None is not None`); restored, clean tree | PASS |
| Safety-critical regression (live gate, dry-run, error push, broker reconciliation, single-shot POST, two-table write, fail-soft) | `pytest -q test_cli::{...} test_kis_broker test_kis_order::test_order_cash_post_not_retried test_sqlite_audit::test_two_table_write test_notifier::test_fail_soft` | 12 passed | PASS |
| Full suite | `pytest -q` (Python 3.14, PYTHONUSERBASE) | 305 passed | PASS |

### Probe Execution

No phase-declared or conventional `scripts/*/tests/probe-*.sh` probes were found. The prior verification's ad-hoc failing probe (audit confidence NULL) is now replaced by the committed `test_confidence_persisted_end_to_end` regression test, which observes non-null 0.95.

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|---|---|---|---|---|
| OPS-01 | 05-04 | Manual full-cycle CLI, no scheduler | SATISFIED | CLI run/screen/status, universe loop, no scheduler; tests pass. |
| OPS-02 | 05-03 / 05-04 / 05-05 | Persist data context, LLM signal (incl. confidence), risk decisions, order outcome | SATISFIED | Gap closed — `decisions.confidence` now non-null end-to-end for parsed signals; end-to-end + mutation test confirm. |
| OPS-03 | 05-03 / 05-04 | Push decision/order outcome to operator | SATISFIED | Discord notifier behind port; consolidated summary + immediate error push tests pass. |
| EXEC-04 | 05-02 | KIS idempotent reconciled order path, no blind retry, partial fills | SATISFIED | Direct REST adapter, query-before-POST, single-shot POST, partial-fill tests pass. |
| CFG-04 | 05-01 / 05-04 | Mock default and deliberate real promotion | SATISFIED | Settings mock default, config real confirmation, CLI `--live-confirm` gate, tests pass. |

All 5 requirement IDs declared in phase plans are accounted for in REQUIREMENTS.md and mapped to Phase 5 (`Complete`). No orphaned Phase 5 requirements found.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|---|---:|---|---|---|
| — | — | Prior BLOCKER (`cli.py:302` hardcoded `confidence=None`) is RESOLVED | — | Write site now reads `result.confidence`; remaining `confidence=None` (cli.py:324) is the error-path fail-safe (no parsed signal) and is correct. |

No debt markers (`TBD`/`FIXME`/`XXX`/`TODO`/`HACK`) found in files modified by 05-05 (`execution.py`, `cli.py`, `tests/test_cli.py`).

### Human Verification Required

These require external services and were never automated blockers. They persist unchanged from the prior verification.

1. **KIS mock-account live order path**
   **Test:** With live KIS mock credentials and an open market session, run `bot run --ticker <code> --execute --live-confirm` under `TRADING_MODE=real` and `CONFIRM_REAL_TRADING=yes`.
   **Expected:** The order appears in KIS broker truth; re-running after a transport uncertainty reconciles and skips the duplicate POST.
   **Why human:** Requires live KIS credentials, external KIS service, and market/session state.

2. **Discord delivery**
   **Test:** Set `DISCORD_WEBHOOK_URL`, run a dry-run cycle, and inspect the Discord channel.
   **Expected:** One consolidated summary arrives; on a forced per-ticker error, an immediate error message also arrives.
   **Why human:** Requires an external Discord webhook and network delivery.

### Gaps Summary

No blocking gaps remain. The single OPS-02 gap from the prior verification is closed and independently verified against the codebase (not merely claimed in SUMMARY):

- The production write path now carries the parsed LLM signal confidence (`ExecutionResult.confidence` -> `write_decision(confidence=result.confidence)` -> `decisions.confidence`).
- The fail-safe is preserved: confidence is NULL only when there is no parsed signal (parse-error branch omits it; failing tickers write no decisions row).
- `CycleAuditEvent` remained a frozen stdlib dataclass with no new field (D-11 honored).
- The end-to-end test is not tautological — reverting the fix makes it fail; restoring it passes.
- Full suite: 305 passed.

Phase goal achieved at the code level. Status is `human_needed` solely because of the two external-dependency checks (live KIS order execution and Discord delivery) that cannot be exercised offline.

---

_Verified: 2026-07-03T10:20:00Z_
_Verifier: Claude (gsd-verifier)_
