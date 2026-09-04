---
phase: 11-kis-portfolio-synchronization-intraday-exit-management
plan: 02
subsystem: mutation-safety
tags: [flock, sqlite, recovery, ownership, kis]
requires:
  - phase: 11-kis-portfolio-synchronization-intraday-exit-management
    provides: complete portfolio snapshots and independently versioned Phase 11 evidence storage
provides:
  - non-blocking account-scoped process mutation exclusion
  - durable owner-token lease and transition evidence
  - crash recovery gate requiring newly persisted complete broker truth
  - reconciliation-before-release shutdown paths
affects: [11-03-daily-orchestration, 11-04-order-boundary, 11-05-intraday-watch]
tech-stack:
  added: []
  patterns: [hybrid-flock-sqlite-lease, conditional-owner-token-update, recovery-only-restart]
key-files:
  created:
    - trading_bot/mutation_lease.py
    - tests/test_mutation_lease.py
  modified:
    - trading_bot/portfolio_store.py
    - trading_bot/audit_models.py
    - tests/test_portfolio_store.py
key-decisions:
  - "Preserve canonical 64-character account hashes and hash any raw scope before constructing a lock path or durable row."
  - "Only a missing or durably RELEASED predecessor can activate directly; every other predecessor state enters recovery-only."
  - "Recovery persists a newly observed complete mutation-capable portfolio snapshot before reconciliation and ACTIVE transition."
patterns-established:
  - "Money-moving code must call assert_active_owner after refresh and immediately before POST."
  - "Shutdown reconciles submitted work and terminalizes its cycle before the durable lease releases and the kernel descriptor closes."
requirements-completed: [PORT-01, EXIT-02]
coverage:
  - id: D1
    description: "Exactly one local process obtains immediate ACTIVE account mutation ownership while competitors fail without waiting or exposing secrets."
    requirement: EXIT-02
    verification:
      - kind: integration
        ref: "tests/test_mutation_lease.py#test_exclusive_process_owner_is_immediate_and_metadata_is_bounded"
        status: pass
    human_judgment: false
  - id: D2
    description: "Owner-token loss removes POST authority and normal release persists terminal evidence before unlocking."
    requirement: EXIT-02
    verification:
      - kind: unit
        ref: "tests/test_mutation_lease.py#test_active_owner_and_renew_require_exact_token_and_active_state"
        status: pass
      - kind: unit
        ref: "tests/test_mutation_lease.py#test_release_is_durable_before_kernel_unlock"
        status: pass
    human_judgment: false
  - id: D3
    description: "Crash recovery remains non-mutable until prior cycles terminalize, a new complete portfolio snapshot is persisted, and every prior broker subject is determinate."
    requirement: PORT-01
    verification:
      - kind: integration
        ref: "tests/test_mutation_lease.py#test_crashed_owner_enters_recovery_before_fresh_broker_callbacks"
        status: pass
      - kind: integration
        ref: "tests/test_mutation_lease.py#test_recovery_blocked_never_grants_post_authority"
        status: pass
    human_judgment: false
duration: 7 min
completed: 2026-09-04
status: complete
---

# Phase 11 Plan 02: Account Mutation Lease and Recovery Boundary Summary

**Hashed non-blocking `flock` ownership backed by a durable SQLite recovery state machine that grants POST authority only after fresh complete broker reconciliation**

## Performance

- **Duration:** 7 min
- **Started:** 2026-09-04T06:47:35Z
- **Completed:** 2026-09-04T06:54:40Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Added one account-wide, no-wait process lock with owner-only permissions, sanitized busy metadata, and an open descriptor retained for the lease lifetime.
- Added durable ACQUIRING, RECOVERY, ACTIVE, LOST, RECOVERY_BLOCKED, and RELEASED transitions with exact owner-token conditional writes and attributable origin/observer events.
- Added conservative crash recovery that persists new complete account truth and requires every prior order subject to be determinate before ACTIVE authority is possible.
- Added shared ownership-loss and normal shutdown paths that reconcile submitted work, preserve terminal evidence, and only then release the kernel lock.

## Task Commits

1. **Task 1 RED: account mutation exclusion contract** - `09c53fc`
2. **Task 1 GREEN: account-scoped mutation ownership** - `b96f628`
3. **Task 2 RED: crash recovery and shutdown contract** - `fc8919e`
4. **Task 2 GREEN: abandoned-owner broker recovery gate** - `b4be75e`

## Files Created/Modified

- `trading_bot/mutation_lease.py` - Hybrid process lock, durable owner guard, recovery state machine, and ordered shutdown helpers.
- `trading_bot/portfolio_store.py` - Phase 11 schema v2 lease rows, append-only transition events, and migration path.
- `trading_bot/audit_models.py` - Stable mutation lease state and event vocabularies.
- `tests/test_mutation_lease.py` - Real multiprocess exclusion/crash tests plus recovery, ownership-loss, permissions, and release-order coverage.
- `tests/test_portfolio_store.py` - Schema-version and expected-table assertions updated for the v2 lease migration.

## Decisions Made

- Kept an already canonical lowercase SHA-256 account scope unchanged while hashing any non-hash input, so no raw CANO can reach filenames or durable scope columns.
- Treated every non-RELEASED predecessor as abandoned evidence requiring recovery, regardless of heartbeat age; heartbeat remains diagnostic only.
- Required recovery snapshots to match the account scope, be complete and mutation-capable, and be observed after the successor acquired its kernel lock.
- Made recovery itself persist the fresh snapshot before reconciling prior subjects, so ACTIVE transition ordering is enforced by the lease API rather than caller convention.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Advanced the existing portfolio schema regression assertion**
- **Found during:** Task 1 verification
- **Issue:** Adding the planned lease tables advanced the Phase 11 schema owner to v2, while the Plan 11-01 migration test still asserted v1 and omitted the new tables.
- **Fix:** Updated that directly affected assertion and expected table set without changing unrelated portfolio behavior.
- **Files modified:** `tests/test_portfolio_store.py`
- **Verification:** `tests/test_portfolio_store.py` passes with migration rollback and retry coverage intact.
- **Committed in:** `b96f628`

**Total deviations:** 1 auto-fixed (1 Rule 3)
**Impact on plan:** The adjustment is limited to the schema contract directly changed by this plan.

## Issues Encountered

- The optional local Ruff invocation was unavailable in the configured Python environment; plan-required pytest verification, bytecode compilation, diff checks, and the full regression suite all passed.

## Verification

- Task 1 focused command: 5 passed, 4 deselected.
- Task 2 focused command: 14 passed.
- Combined plan command: 29 passed.
- Full repository regression suite: 751 passed.
- Python bytecode compilation and whitespace/error diff checks passed.

## Known Stubs

None.

## Self-Check: PASSED

- Both created files and all modified schema/contract files exist.
- All four RED/GREEN commits exist in git history.
- No tracked files were deleted by any plan commit.
- Every task and plan verification command exits successfully.

## Next Phase Readiness

Ready for Plan 11-03 to acquire this lease around daily orchestration and use `assert_active_owner()` at the current money-moving boundary.
