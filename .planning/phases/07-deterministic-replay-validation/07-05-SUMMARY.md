---
phase: 07-deterministic-replay-validation
plan: 05
subsystem: replay-validation
tags: [python, pytest, deterministic-replay, canonical-json]
requires:
  - phase: 07-deterministic-replay-validation
    provides: production screener replay and progressive daily-loss state from plan 07-04
provides:
  - Exact one-to-one executable evidence for all eleven required replay boundaries
  - One complete deterministic result identity shared by helper, result object, and CLI
affects: [phase-08-reporting, replay-audit]
tech-stack:
  added: []
  patterns: [attributed boundary checks, canonical complete-evidence hashing]
key-files:
  created: [.planning/phases/07-deterministic-replay-validation/07-05-SUMMARY.md]
  modified: [trading_bot/replay.py, tests/fixtures/replay/focused.json, tests/test_replay.py, tests/test_cli.py, .planning/phases/07-deterministic-replay-validation/07-VALIDATION.md]
key-decisions:
  - "Expected future access is an explicitly marked rejection scenario; unmarked future rows still fail during fixture loading."
  - "Boundary verification passes only when the executed-ID Counter exactly equals the required-ID Counter."
patterns-established:
  - "Every canonical replay boundary carries boundary ID, scenario, ticker, stage, expected, and actual evidence."
requirements-completed: [REPLAY-02, REPLAY-04]
coverage:
  - id: D1
    description: Exact executable and attributed coverage of all eleven replay boundaries
    requirement: REPLAY-04
    verification:
      - kind: integration
        ref: "tests/test_replay.py#test_required_boundaries_have_exactly_one_executed_attributed_check"
        status: pass
    human_judgment: false
  - id: D2
    description: Unified complete deterministic replay result identity
    requirement: REPLAY-02
    verification:
      - kind: unit
        ref: "tests/test_replay.py#test_complete_result_helper_matches_replay_result"
        status: pass
      - kind: integration
        ref: "tests/test_cli.py#test_replay_command_is_offline_concise_and_writes_complete_json"
        status: pass
    human_judgment: false
duration: 12min
completed: 2026-07-13
status: complete
---

# Phase 7 Plan 05: Replay Gap Closure Summary

**All eleven safety boundaries now execute with exact attribution, while every public result-ID path hashes the same complete deterministic evidence.**

## Performance

- **Duration:** 12 min
- **Completed:** 2026-07-13
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Added the six missing focused cases: explicit HOLD, ordinary SELL, stale data, take-profit override, sizing edge, and expected future-access rejection.
- Enforced an exact required-to-executed boundary bijection that fails on missing, duplicate, unknown, or unattributed evidence.
- Delegated `ReplayResult.result_id` to the complete-evidence `compute_result_id` path and proved CLI filename stability.

## Task Commits

1. **Task 07-05-01: Execute and attribute every required boundary** - `1618e36`
2. **Task 07-05-02: Unify complete replay identity and close Phase 7 validation** - `6b4b279`

## Files Created/Modified

- `trading_bot/replay.py` - Boundary-aware outcomes/checks, expected rejection handling, exact coverage verification, and unified identity API.
- `tests/fixtures/replay/focused.json` - Eleven executable focused boundary scenarios.
- `tests/test_replay.py` - Completeness, fail-closed, attribution, equivalence, and identity sensitivity coverage.
- `tests/test_cli.py` - Stable repeated replay ID and filename regression coverage.
- `.planning/phases/07-deterministic-replay-validation/07-VALIDATION.md` - Executable F-001 through F-004 closure map.

## Decisions Made

- A future-access fixture must opt into `FUTURE_DATA_ACCESS` and contain a genuinely future-dated row; otherwise fixture loading fails.
- Stale rows are exercised through the production screener and attributed to the screening stage.

## Deviations from Plan

None - plan executed as specified.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Verification

- Targeted Phase 7 contract suite: **137 passed**.
- Full repository suite: **401 passed**.

## Next Phase Readiness

F-002 and F-004 are closed. Phase 7 is ready for independent goal verification and completion routing.

---
*Phase: 07-deterministic-replay-validation*
*Completed: 2026-07-13*
