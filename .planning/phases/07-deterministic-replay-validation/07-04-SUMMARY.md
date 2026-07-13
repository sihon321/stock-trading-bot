---
phase: 07-deterministic-replay-validation
plan: 04
subsystem: replay
tags: [deterministic-replay, screener, point-in-time, risk]
requires:
  - phase: 07-03
    provides: offline replay runner and normalized evidence
provides:
  - ticker-attributed historical records as production screener inputs
  - explicit full-day daily-loss transitions consumed by later decisions
affects: [07-05, phase-08-reporting]
tech-stack:
  added: []
  patterns: [authoritative frozen history projection, monotonic explicit state facts]
key-files:
  created: []
  modified: [trading_bot/replay.py, tests/test_replay.py, tests/fixtures/replay/focused.json, tests/fixtures/replay/full_day.json]
key-decisions:
  - "The latest cutoff-safe ticker-attributed historical record is the sole production screener row source."
  - "Daily loss changes are explicit monotonic fixture facts applied after each full-day step, never inferred P&L."
patterns-established:
  - "Replay provenance: derive screened rows from frozen history and reject missing ticker attribution."
requirements-completed: [REPLAY-01, REPLAY-04]
coverage:
  - id: D1
    description: Historical fixture mutations materially change production screener rank.
    requirement: REPLAY-01
    verification:
      - kind: integration
        ref: tests/test_replay.py#test_historical_input_materially_drives_production_screener_rank
        status: pass
    human_judgment: false
  - id: D2
    description: Full-day replay advances explicit daily loss and blocks a later qualified BUY.
    requirement: REPLAY-04
    verification:
      - kind: integration
        ref: tests/test_replay.py#test_full_day_daily_loss_progresses_and_blocks_later_buy
        status: pass
    human_judgment: false
duration: 12min
completed: 2026-07-13
status: complete
---

# Phase 7 Plan 04 Summary

**Frozen ticker history now directly drives production screening, while explicit step loss facts advance full-day risk state and block later BUYs.**

## Performance

- **Duration:** 12 min
- **Completed:** 2026-07-13
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Removed the hollow `market_history`/`market_row` split by projecting the latest cutoff-safe historical record per ticker into `screen_candidates`.
- Added a mutation regression proving relevant historical technical changes alter production rank while deterministic ticker tie ordering remains intact.
- Added bounded, finite, monotonic full-day `realized_loss_after` facts and observable outcome state; a later otherwise-qualified BUY is risk-blocked.

## Task Commits

1. **Tasks 07-04-01 and 07-04-02: historical provenance and state progression** - `dbf33de`

The two tightly coupled schema changes were committed together because the shared full-day fixture is the executable contract for both provenance and state progression.

## Files Created/Modified

- `trading_bot/replay.py` - authoritative historical projection and daily-loss state transition contract.
- `tests/fixtures/replay/focused.json` - ticker-attributed historical screener records.
- `tests/fixtures/replay/full_day.json` - ranked complete/no-fill scenario with explicit loss progression and later BUY block.
- `tests/test_replay.py` - historical mutation and state progression regressions.

## Decisions Made

- Retained the legacy `market_row` fixture field for schema compatibility, but the runner no longer reads it; historical records are authoritative.
- Capped explicit loss facts at the configured threshold because values beyond the policy gate add no decision evidence and broaden tampering surface.

## Deviations from Plan

None - plan executed as specified. The pure history projection option was used without adding dependencies.

## Issues Encountered

The full-day fixture needed a third ranked candidate so loss progression could be observed independently from the complete/no-fill mutation checks; it was added within the planned fixture scope.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

F-001 and F-003 now have executable regression evidence. Plan 07-05 can complete boundary-catalog and identity unification work.

---
*Phase: 07-deterministic-replay-validation*
*Completed: 2026-07-13*
