---
phase: 06-audit-evidence-cycle-boundaries
verified: 2026-07-11T13:20:00Z
status: gaps_found
score: 10/12 must-haves verified
behavior_unverified: 0
gaps:
  - id: EVID-02-screen-rejections
    severity: blocker
    requirement: EVID-02
    summary: "bot screen persists SELECTED candidates but drops the screener's rejected ticker audit events."
  - id: EVID-04-successful-quote-evidence
    severity: blocker
    requirement: EVID-04
    summary: "A successful KIS submission does not persist the pre-submit quote observation, check time, age, freshness verdict, or reason; mock executable orders do not perform the pre-submit refresh at all."
---

# Phase 6: Audit Evidence & Cycle Boundaries Verification Report

**Phase Goal:** Operators can trust that every cycle and ticker path is complete, attributable, and evaluated against explicit KRX timing and freshness boundaries.
**Verified:** 2026-07-11
**Status:** gaps_found
**Dispatch:** generic-agent workaround for `gsd-verifier` (typed dispatch unavailable)

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Every run has one terminal lifecycle state, KST date, kind, target, policy, and provenance. | ✓ VERIFIED | `cli.run_cycle` and `screen_command` recover, start, and terminalize runs; `runs` contains the required fields. `test_run_lifecycle_recovers_once_and_terminalizes_once` and `test_run_records_provenance_and_clean_terminal_state` pass. |
| 2 | Every attempted ticker has exactly one normalized terminal outcome, including screening rejection and failure paths. | ✗ FAILED | `screen_command` writes outcomes only for `_candidate_tickers(result)` (`cli.py` 571-582). It never consumes `ScreenerResult.audit_events`, although `screener.py` emits one `SKIP_CANDIDATE` event per excluded ticker. Rejected screening attempts therefore have no `REJECTED` row. |
| 3 | Each ticker's order intent is traceable through submission/reconciliation or to an attributed no-order reason. | ✓ VERIFIED | `KISBroker.place_order` emits intent, duplicate check, submission, and reconciliation events carrying run/ticker IDs; CLI persists one terminal ticker outcome with a normalized reason. Focused ambiguity/duplicate tests pass. |
| 4 | Every executable cycle exposes session, completed-bar cutoff, quote freshness, permitted window, reason, and timing-policy version. | ✗ FAILED | Run provenance stores session/cutoff/window and policy version, but a fresh pre-submit quote produces no freshness evidence: `SUBMISSION_ATTEMPTED` has empty detail. Only `FRESHNESS_BLOCKED` stores observed/check times and age. In mock mode `_build_broker` returns `MockBroker`, so executable mock orders never perform the pre-submit refresh. |
| 5 | A v1 audit database upgrades additively without row loss. | ✓ VERIFIED | Transactional `PRAGMA user_version` migration retains legacy runs/decisions; idempotence and rollback tests pass. |
| 6 | SQLite rejects duplicate run/ticker outcomes and event history is insert-oriented. | ✓ VERIFIED | `UNIQUE(run_id, ticker)` and FKs are present; `append_order_event` only inserts and ordering tests pass. No mutation API is exposed. |
| 7 | Wave-1 storage and pure KRX policy contracts are independently green. | ✓ VERIFIED | `tests/test_sqlite_audit.py` and `tests/test_market_cycle.py` pass in the focused run. |
| 8 | Screen/run identities are immutable; status is read-only; retries use a distinct `parent_run_id`. | ✓ VERIFIED | UUID identities are inserted once, parent UUID/existence is validated, and `status_command` performs no audit write. Lifecycle/retry tests pass. |
| 9 | Order intent and submission attempt identities are distinct and durable. | ✓ VERIFIED | `order_intent_id` is created before the duplicate query; a new `submission_id` is created for the single POST path; append-only chain test passes. |
| 10 | An indeterminate POST becomes ambiguous and is never blindly retried. | ✓ VERIFIED | One adapter call is wrapped once; any acknowledgement exception emits `SUBMISSION_AMBIGUOUS` and raises `AmbiguousSubmissionError`. `test_ambiguous_submission_is_not_retried` and linked-run evidence test pass. |
| 11 | Orders are permitted only on a confirmed KRX trading day during `09:00 <= KST < 15:20`. | ✓ VERIFIED | `MarketCyclePolicy.classify` fails closed on unknown calendar state and uses the required half-open continuous session; CLI blocks execute before ticker work when production cycle evidence is non-executable. Boundary tests pass. |
| 12 | Open-market indicators exclude the incomplete current daily bar. | ✓ VERIFIED | `build_runtime` obtains `previous_trading_day(now)` and wires that cutoff as both expected and accepted latest OHLCV date. Cutoff tests pass. |

**Score:** 10/12 truths verified

### Required Artifacts

| Artifact | Status | Details |
|----------|--------|---------|
| `trading_bot/sqlite_audit.py` | ✓ EXISTS + SUBSTANTIVE + WIRED | Versioned migration, lifecycle/outcome/event writers, SQLite constraints; used by CLI and broker sink. |
| `trading_bot/audit_models.py` | ✓ EXISTS + SUBSTANTIVE + WIRED | Frozen normalized records, stable enums, and provider/credential detail rejection. |
| `trading_bot/market_cycle.py` | ✓ EXISTS + SUBSTANTIVE + WIRED | Calendar/session, cutoff, and quote-age policy; wired by runtime and KIS broker. |
| `trading_bot/cli.py` | ⚠ PARTIAL | Lifecycle and run ticker terminalization are wired, but screen rejection events are not persisted and successful quote-freshness evidence is absent. |
| `trading_bot/kis_broker.py` | ⚠ PARTIAL | Intent/submission/ambiguity chain is wired; successful freshness checks are not represented in emitted evidence and mock execution bypasses the refresh. |
| Phase 6 test files | ⚠ PARTIAL | 46 focused tests pass, but none asserts rejected-screen persistence or successful/mock pre-submit freshness evidence. |

### Key Link Verification

| From | To | Status | Details |
|------|----|--------|---------|
| SQLite migration | `PRAGMA user_version` | ✓ WIRED | Explicit transaction sets version 2 only after additive schema work. |
| `ticker_outcomes` | `runs` | ✓ WIRED | FK plus `UNIQUE(run_id, ticker)`. |
| CLI run coordinator | lifecycle/outcome writers | ✓ WIRED | Recovery/start/finalize envelope and per-ticker `finally` writer are present. |
| Screener rejection audits | `ticker_outcomes` | ✗ NOT WIRED | `screen_command` ignores `result.audit_events`. |
| `KISBroker.place_order` | SQLite order events | ✓ WIRED | CLI injects a synchronous `append_order_event` sink. |
| Successful pre-submit quote check | durable evidence | ✗ NOT WIRED | No event stores successful observation/check/age/freshness facts. |

## Requirements Coverage

| Requirement | Status | Blocking Issue |
|-------------|--------|----------------|
| EVID-01 | ✓ SATISFIED | - |
| EVID-02 | ✗ BLOCKED | Rejected tickers attempted by `bot screen` are omitted from terminal outcomes. |
| EVID-03 | ✓ SATISFIED | - |
| EVID-04 | ✗ BLOCKED | Successful pre-submit quote freshness is not queryable; mock executable orders bypass the refresh. |

**Coverage:** 2/4 requirements satisfied

## Security and Integrity Checks

- `sanitize_detail` rejects raw payload, response, token, secret, credential, and related key shapes at run/outcome/order-event storage boundaries.
- Ambiguous provider exceptions persist only normalized `error_type`; raw exception bodies are not stored.
- `test_storage_rejects_raw_provider_and_credential_detail` and normalized broker fixture checks pass.
- No `TBD`, `FIXME`, or `XXX` debt markers were found in the Phase 6 implementation/test files.

## Automated Verification

- Focused: `.venv/bin/pytest tests/test_sqlite_audit.py tests/test_market_cycle.py tests/test_cli.py tests/test_kis_broker.py -q` → **46 passed**.
- Full suite (run once): `.venv/bin/pytest -q` → **356 passed in 13.44s**.
- No phase probe scripts were present.

## Disconfirmation Pass

- **Partially met requirement:** EVID-04 has run/session/cutoff evidence, but lacks the successful pre-submit freshness facts and mock enforcement.
- **Misleading green test:** `test_pre_submit_quote_is_refetched_and_ten_seconds_is_inclusive` proves POST gating, but never asserts that a successful freshness decision is persisted.
- **Uncovered error/completeness path:** Screen tests assert selected output/progress only; none verifies `ScreenerResult.audit_events` become `REJECTED`/`SCREEN_ERROR` terminal rows.

## Planning Metadata Debt

`.planning/STATE.md` contains two duplicate `[Phase ?]` decision entries for ambiguity and origin/observer reconciliation. This is metadata cleanup debt only; it does not independently affect the Phase 6 product-goal verdict.

## Gaps Summary

### Critical Gaps (Block Progress)

1. **Screened-out tickers disappear from the completeness authority**
   - Missing: Translate each screener exclusion audit into exactly one `REJECTED` terminal outcome (and preserve normalized reason/detail); cover whole-screen failures consistently.
   - Impact: Operators cannot account for every ticker attempted by `bot screen`, violating EVID-02 and the phase goal.
   - Fix: Persist selected and rejected outcomes from the complete screener result and add an integration test proving one row per considered ticker.

2. **Successful executable orders lack durable pre-submit freshness evidence**
   - Missing: Persist the pre-submit quote observation time, check time, computed age, freshness verdict/reason, and policy version on the successful path; enforce/evidence equivalent freshness for executable mock cycles.
   - Impact: Operators cannot verify which quote freshness boundary justified an accepted order, violating EVID-04.
   - Fix: Emit a normalized successful freshness event before `SUBMISSION_ATTEMPTED`, wire mock execution through the same non-mutating freshness gate, and test the stored run/ticker/order chain.

## Recommended Fix Plan

### 06-05-PLAN.md: Close evidence completeness gaps

1. Persist selected, rejected, and screening-error terminal outcomes from the complete screener evidence set.
2. Add durable successful pre-submit quote freshness evidence and apply the same executable-cycle freshness contract to mock execution.
3. Add focused integration tests for both missing chains, then rerun the full suite and raw/secret exclusion checks.

---
*Verified: 2026-07-11*
*Verifier: generic-agent workaround for gsd-verifier*
