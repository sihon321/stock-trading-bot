---
phase: 06-audit-evidence-cycle-boundaries
plan: 01
subsystem: database
tags: [sqlite, audit, krx, migration, evidence]
requires:
  - phase: 05
    provides: legacy runs/decisions audit schema and KIS execution adapters
provides:
  - Additive and transactional SQLite v2 evidence migration
  - Stable provider-neutral run, ticker outcome, and order event contracts
  - Pure KRX session, completed-bar cutoff, and quote freshness policy
affects: [06-02, 06-03, 06-04, replay, reporting, soak]
tech-stack:
  added: []
  patterns: [PRAGMA user_version migrations, append-only evidence, injected calendar policy]
key-files:
  created: [trading_bot/audit_models.py, trading_bot/market_cycle.py, tests/test_market_cycle.py]
  modified: [trading_bot/sqlite_audit.py, tests/test_sqlite_audit.py, tests/conftest.py]
key-decisions:
  - "Provider evidence is normalized into scalar allowlisted facts before persistence."
  - "KRX executable time is the half-open 09:00–15:20 KST continuous session."
patterns-established:
  - "Audit migrations are additive, explicit transactions keyed by PRAGMA user_version."
  - "Order evidence has insert-only writers and separate origin/observer run attribution."
requirements-completed: [EVID-01, EVID-02, EVID-03, EVID-04]
coverage:
  - id: D1
    description: Existing v1 audit databases migrate transactionally without evidence loss
    requirement: EVID-01
    verification:
      - kind: integration
        ref: tests/test_sqlite_audit.py#test_v1_migrates_to_v2_idempotently_without_row_loss
        status: pass
    human_judgment: false
  - id: D2
    description: One ticker outcome and ordered append-only order events are enforced
    requirement: EVID-02
    verification:
      - kind: integration
        ref: tests/test_sqlite_audit.py#test_unique_ticker_outcome_and_append_only_order_event_order
        status: pass
    human_judgment: false
  - id: D3
    description: Raw provider payload and credential-shaped evidence is rejected
    requirement: EVID-03
    verification:
      - kind: unit
        ref: tests/test_sqlite_audit.py#test_storage_rejects_raw_provider_and_credential_detail
        status: pass
    human_judgment: false
  - id: D4
    description: KRX session, completed-day, and inclusive ten-second quote policies fail closed
    requirement: EVID-04
    verification:
      - kind: unit
        ref: tests/test_market_cycle.py
        status: pass
    human_judgment: false
duration: 8min
completed: 2026-07-11
status: complete
---

# Phase 6 Plan 01: Evidence Schema and Market Cycle Summary

**Transactional SQLite v2 audit evidence and deterministic KRX cycle boundaries now provide the durable seams for later Phase 6 orchestration.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-07-11T12:06:00Z
- **Completed:** 2026-07-11T12:13:58Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments

- Preserved legacy runs and decisions through idempotent, rollback-safe v1-to-v2 migration.
- Added stable ticker outcome uniqueness and append-only normalized order events with dual-run attribution.
- Added pure KRX calendar/session, prior completed trading-day, and inclusive 10-second quote freshness contracts.

## Task Commits

1. **Task 06-01-01: Pin additive migration and evidence integrity behavior** - `6f80ed8`
2. **Task 06-01-02: Implement SQLite v2 contracts and migration** - `0b5c1ce`
3. **Task 06-01-03: Implement pure market-cycle contracts and deterministic fixtures** - `3fbdae3`

Additional compatibility fix: `bfd31c1`

## Files Created/Modified

- `trading_bot/audit_models.py` - Stable enums, frozen evidence records, and detail sanitizer.
- `trading_bot/sqlite_audit.py` - Additive migration and normalized evidence writers.
- `trading_bot/market_cycle.py` - Pure KRX cycle and quote freshness policy.
- `tests/test_sqlite_audit.py` - Migration, integrity, attribution, and sanitization coverage.
- `tests/test_market_cycle.py` - Deterministic KRX and quote boundary coverage.
- `tests/conftest.py` - Legacy v1 and normalized broker fixtures.

## Decisions Made

- Evidence detail accepts only normalized scalar facts and rejects credential/provider-payload-shaped keys.
- The KRX continuous window is `[09:00, 15:20)` KST; all uncertainty and other sessions fail closed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Restored the injected-connection schema compatibility surface**
- **Found during:** Overall full-suite verification
- **Issue:** Existing CLI tests initialize an injected SQLite connection through `sqlite_audit.SCHEMA`; removing that constant broke six established flows.
- **Fix:** Added an idempotent current-schema compatibility script while retaining `connect()`/`migrate()` as the versioned database path.
- **Files modified:** `trading_bot/sqlite_audit.py`
- **Verification:** Full suite passes: 345 tests.
- **Committed in:** `bfd31c1`

**Total deviations:** 1 auto-fixed (Rule 1)
**Impact on plan:** Compatibility was restored without changing the v2 migration or later-plan scope.

## Issues Encountered

- Ruff is not installed in the project virtual environment; the plan required pytest verification only, and all 345 tests pass.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plans 06-02 through 06-04 can build against durable run, outcome, order-event, and market-cycle contracts.
- No blocker remains for Wave 2.

## Self-Check: PASSED

- All created files exist.
- All task and compatibility commits exist.
- Targeted tests and the complete 345-test suite pass.

---
*Phase: 06-audit-evidence-cycle-boundaries*
*Completed: 2026-07-11*
