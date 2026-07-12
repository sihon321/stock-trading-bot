---
phase: 07-deterministic-replay-validation
plan: 01
subsystem: testing
tags: [replay, deterministic, offline, fixtures, risk]
requires:
  - phase: 06-audit-evidence-cycle-boundaries
    provides: production screener, parser, risk, sizing, and execution seams
provides:
  - Strict versioned replay fixture contracts and future-data guard
  - Offline production-path replay runner with deterministic fill state
  - Focused boundary and full-day ranked fixture bundles
affects: [07-02, 07-03, replay-validation]
tech-stack:
  added: []
  patterns: [strict frozen fixture boundary, pure production-seam replay composition]
key-files:
  created: [trading_bot/replay.py, tests/test_replay.py, tests/fixtures/replay/focused.json, tests/fixtures/replay/full_day.json]
  modified: []
key-decisions:
  - "Reject incomplete boundary catalogs at fixture-load time."
  - "Apply COMPLETE intents only after dry-run evaluation; NONE never mutates state."
patterns-established:
  - "Replay inputs are explicit and time-guarded before policy evaluation."
  - "Full-day processing delegates ordering to the production screener."
requirements-completed: [REPLAY-01, REPLAY-02, REPLAY-03, REPLAY-04]
coverage:
  - id: D1
    description: Strict frozen fixture loading and fail-loud future-data rejection
    requirement: REPLAY-04
    verification:
      - kind: unit
        ref: tests/test_replay.py
        status: pass
    human_judgment: false
  - id: D2
    description: Offline scenarios traverse production screening and execution gates with deterministic state
    requirement: REPLAY-01
    verification:
      - kind: integration
        ref: ".venv/bin/python -m pytest -q tests/test_replay.py tests/test_screener.py tests/test_execution.py"
        status: pass
    human_judgment: false
duration: 12min
completed: 2026-07-12
status: complete
---

# Phase 7 Plan 01: Deterministic Replay Engine Summary

**Strict frozen fixtures now traverse the production screener and execution policy entirely offline with deterministic fill state and fail-loud look-ahead protection.**

## Performance

- **Duration:** 12 min
- **Completed:** 2026-07-12T01:35:22Z
- **Tasks:** 2
- **Files modified:** 4 implementation/test files

## Accomplishments

- Added immutable replay scenario, step, and normalized outcome contracts with strict schema validation.
- Added cutoff-guarded historical data and a mechanically complete Phase 7 boundary catalog.
- Added focused isolated-state and ranked full-day fixtures using production screening, parsing, risk, sizing, and execution seams.
- Verified COMPLETE mutates immediately while NONE preserves cash, positions, and order history.

## Task Commits

The tightly coupled TDD tasks were committed together after the complete integration suite passed:

1. **Tasks 07-01-01 and 07-01-02: replay contracts, fixtures, runner, and tests** - `d77b63c`

## Files Created/Modified

- `trading_bot/replay.py` - Strict loader, historical guard, replay contracts, and offline runner.
- `tests/test_replay.py` - Contract, look-ahead, boundary, ordering, and fill-state tests.
- `tests/fixtures/replay/focused.json` - Focused policy-boundary fixture bundle.
- `tests/fixtures/replay/full_day.json` - Out-of-order multi-ticker COMPLETE/NONE scenario.

## Decisions Made

- Boundary names are mandatory bundle metadata, so a silently incomplete frozen catalog cannot load.
- Fixture rows are converted to production `SourceHealth` objects only after cutoff validation.

## Deviations from Plan

None - plan executed within the specified production seams and scope.

## Issues Encountered

None.

## User Setup Required

None - no external services or dependencies are used.

## Next Phase Readiness

Plan 07-02 can hash the strict input contracts and ordered normalized outcomes. Plan 07-03 can consume the same outcomes for CLI and funnel evidence.

---
*Phase: 07-deterministic-replay-validation*
*Completed: 2026-07-12*
