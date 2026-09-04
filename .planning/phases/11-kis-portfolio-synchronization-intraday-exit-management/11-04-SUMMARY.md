---
phase: 11-kis-portfolio-synchronization-intraday-exit-management
plan: 04
subsystem: order-safety
tags: [kis, portfolio, exits, mutation-lease, reconciliation]
requires:
  - phase: 11-kis-portfolio-synchronization-intraday-exit-management
    provides: complete account snapshots, durable evaluation identity, and account mutation lease
provides:
  - one typed exit lifecycle for daily LLM and intraday risk SELL decisions
  - OPEN/PARTIAL reconciliation-only suppression for SELL and BUY
  - fresh portfolio and quote re-gating at the KIS money-moving boundary
  - final lease assertion, evidence-first single POST, and ambiguity preservation
affects: [11-05-intraday-watch, 11-06-operator-evidence]
tech-stack:
  added: []
  patterns: [shared-exit-reducer, affected-ticker-refresh, final-owner-assertion, evidence-before-effect]
key-files:
  created:
    - trading_bot/exit_manager.py
    - tests/test_exit_manager.py
  modified:
    - trading_bot/kis_broker.py
    - trading_bot/cli.py
key-decisions:
  - "Treat an OPEN or PARTIAL broker SELL as reconciliation-only authority; never derive a resubmittable remainder locally."
  - "Recalculate SELL quantity from current KIS orderable quantity and BUY affordability from current broker cash plus the refreshed quote."
  - "Hash the lease owner identifier before evidence and reassert ownership after all network refresh work."
patterns-established:
  - "Every Phase 11 KIS POST receives the current portfolio reader and lease through the guarded broker wrapper."
  - "Notification transport remains outside the money-moving boundary."
requirements-completed: [PORT-01, EXIT-01, EXIT-02]
coverage:
  - id: D1
    description: "Daily SELL, stop-loss, and take-profit share one no-oversell lifecycle."
    requirement: EXIT-01
    verification:
      - kind: unit
        ref: "tests/test_exit_manager.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "BUY and SELL refresh broker truth and quote, reassert lease ownership, persist attempt evidence, and POST at most once."
    requirement: EXIT-02
    verification:
      - kind: integration
        ref: "tests/test_exit_manager.py#test_money_boundary_refreshes_regates_asserts_and_posts_once"
        status: pass
      - kind: integration
        ref: "tests/test_kis_broker.py"
        status: pass
    human_judgment: false
duration: 12 min
completed: 2026-09-04
status: complete
---

# Phase 11 Plan 04: Shared Exit and KIS Money Boundary Summary

**Broker-authoritative daily/intraday exits with fresh affected-ticker truth, final lease ownership, limit-only pricing, and evidence-first single-shot KIS submission**

## Performance

- **Duration:** 12 min
- **Completed:** 2026-09-04
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Added a frozen typed exit trigger/result model shared by qualified daily LLM SELLs and the existing stop-loss/take-profit risk decisions.
- Made OPEN/PARTIAL broker SELLs reconciliation-only and BUY-blocking, with no local remaining-quantity arithmetic, cancellation, price chasing, or same-cycle resubmission.
- Added affected-ticker snapshot refresh, current quote repricing, quantity recalculation, account-scope verification, final lease assertion, and sanitized attempt linkage immediately before one KIS POST.
- Wired the Phase 11 CLI broker wrapper to provide its fresh portfolio reader and current lease at the final KIS boundary.

## Task Commits

1. **Task 1 RED: shared exit lifecycle contract** - `48cfc45`
2. **Task 1 GREEN: broker-authoritative exit reducer** - `8562c89`
3. **Task 2 RED: universal KIS money boundary contract** - `7b74a82`
4. **Task 2 GREEN: fresh lease-owned submissions** - `0e40bcc`

## Files Created/Modified

- `trading_bot/exit_manager.py` - shared exit triggers, dispositions, no-oversell evaluation, and submission bridge
- `tests/test_exit_manager.py` - lifecycle, ordering, changed-truth, lease-loss, and evidence-failure matrix
- `trading_bot/kis_broker.py` - current snapshot/quote re-gating and final ownership boundary
- `trading_bot/cli.py` - passes Phase 11 portfolio and lease authority to KISBroker

## Decisions Made

- Preserve legacy non-Phase-11 broker construction while requiring the refresh and lease collaborators as a pair whenever the Phase 11 boundary is active.
- Keep broker acknowledgement uncertainty single-shot and delegate later observations to the existing append-only reconciliation API.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Continued inline after executor quota exhaustion**
- **Found during:** Wave 4 dispatch
- **Issue:** The typed executor returned a usage-limit sentinel before producing any commit or SUMMARY.
- **Fix:** Verified no partial Plan 11-04 state existed, then used the documented sequential inline execution path.
- **Verification:** Safe-resume commit/SUMMARY checks were empty before implementation.

**2. [Rule 2 - Missing Critical] Wired the production Phase 11 wrapper**
- **Found during:** Task 2 integration
- **Issue:** A KISBroker-only boundary would not receive the live portfolio reader and lease from daily orchestration.
- **Fix:** Extended `_LeaseGuardedBroker` and its Phase 11 construction site to pass both collaborators at every POST.
- **Verification:** `tests/test_phase11_cli.py` and the full repository suite pass.

**Total deviations:** 2 auto-fixed (1 blocking, 1 missing critical). **Impact:** Both were necessary to complete the planned safety boundary; no trading authority was broadened.

## Issues Encountered

- The checkout contained pre-existing Phase 9/KIS changes in overlapping files. Only Phase 11 hunks were staged; those user edits remain unstaged.

## User Setup Required

None.

## Next Phase Readiness

- Plan 11-05 can invoke `evaluate_exit_candidate()`/`submit_exit()` from LLM-free intraday iterations.
- Current broker truth, quote freshness, lease ownership, and evidence persistence now fail closed before KIS mutation.

## Self-Check: PASSED

- Focused acceptance suite: 103 passed.
- Full repository suite: 776 passed.
- Created files and all four task commits verified.

---
*Phase: 11-kis-portfolio-synchronization-intraday-exit-management*
*Completed: 2026-09-04*
