---
phase: 07-deterministic-replay-validation
plan: 06
subsystem: replay-validation
tags: [python, pytest, pandas, raw-ohlcv, deterministic-replay]
requires:
  - phase: 07-deterministic-replay-validation
    provides: deterministic replay, production screener ordering, and exact boundary evidence from plans 07-01 through 07-05
provides:
  - Strict cutoff-safe raw OHLCV fixture contract with explicit indicator windows
  - Shipped calculate_technicals to production screen_candidates replay composition
  - Adversarial raw-market sensitivity and zero-downstream-call future guard evidence
affects: [phase-08-reporting, replay-audit, REPLAY-01, REPLAY-04]
tech-stack:
  added: []
  patterns: [cutoff-before-transform, raw-input replay provenance, explicit indicator policy]
key-files:
  created: [.planning/phases/07-deterministic-replay-validation/07-06-SUMMARY.md]
  modified: [trading_bot/replay.py, tests/fixtures/replay/focused.json, tests/fixtures/replay/full_day.json, tests/test_replay.py, .planning/phases/07-deterministic-replay-validation/07-VALIDATION.md]
key-decisions:
  - "Replay fixtures carry four raw OHLCV rows with explicit 2/3-period indicator windows so every calculated tail is valid and deterministic."
  - "An explicit non-AVAILABLE fixture health overrides indicator health; otherwise the shipped IndicatorResult health controls screening."
patterns-established:
  - "Replay validates every nested timestamp and OHLC invariant before constructing a broker or invoking any production transform."
  - "Canonical replay technicals come only from trading_bot.indicators.calculate_technicals, never from fixture-authored derived fields."
requirements-completed: [REPLAY-01, REPLAY-04]
coverage:
  - id: D1
    description: Raw frozen OHLCV traverses the shipped indicator transform and production screener with explicit windows
    requirement: REPLAY-01
    verification:
      - kind: integration
        ref: "tests/test_replay.py#test_replay_calls_shipped_indicator_transform_with_explicit_policy"
        status: pass
      - kind: integration
        ref: "tests/test_replay.py#test_historical_input_materially_drives_production_screener_rank"
        status: pass
    human_judgment: false
  - id: D2
    description: Future OHLCV fails before indicator, screener, execution, or broker mutation
    requirement: REPLAY-04
    verification:
      - kind: integration
        ref: "tests/test_replay.py#test_future_ohlcv_fails_before_all_downstream_calls"
        status: pass
      - kind: integration
        ref: "tests/test_replay.py#test_fixture_rejects_future_rows_before_replay"
        status: pass
    human_judgment: false
duration: 7min
completed: 2026-07-13
status: complete
---

# Phase 7 Plan 06: Raw OHLCV Replay Gap Closure Summary

**Frozen raw OHLCV now flows through the shipped indicator transform and production screener, with future data rejected before every downstream decision or mutation seam.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-07-13T04:57:58Z
- **Completed:** 2026-07-13T05:04:58Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Replaced fixture-authored technical rows and unused step market rows with strict per-ticker raw OHLCV warm-up series and explicit `IndicatorConfig` windows.
- Wired cutoff-validated Korean-column DataFrames through the shipped `calculate_technicals` function exactly once per ticker before `screen_candidates`.
- Proved raw close/high/low/volume changes alter production rank and future OHLCV reaches zero indicator, screener, execution, or broker calls.

## Task Commits

Each task was committed atomically:

1. **Task 07-06-01 RED: Require raw OHLCV production indicator path** - `41e27e2` (test)
2. **Task 07-06-01 GREEN: Derive replay screening from raw OHLCV** - `16f343c` (feat)
3. **Task 07-06-02: Prove raw sensitivity and cutoff ordering** - `7a64429` (test)

## Files Created/Modified

- `trading_bot/replay.py` - Strict raw schema, indicator policy, cutoff-first projection, and shipped indicator-to-screener composition.
- `tests/fixtures/replay/focused.json` - Eleven focused boundaries backed by cutoff-safe raw warm-up series.
- `tests/fixtures/replay/full_day.json` - Three raw market histories whose calculated indicators determine production rank.
- `tests/test_replay.py` - Schema, shipped-call, raw mutation, and future call-order regressions.
- `.planning/phases/07-deterministic-replay-validation/07-VALIDATION.md` - Corrected executable F-001 and REPLAY-01 evidence.

## Decisions Made

- Used explicit small indicator windows in fixtures to keep checked-in warm-up histories compact while still exercising every shipped formula with a valid tail.
- Kept explicit stale/unavailable fixture health authoritative, while AVAILABLE fixture health delegates to the actual indicator result so calculation failure remains fail-closed.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - replay remains fully offline and requires no external service configuration.

## Verification

- Task 07-06-01 schema/production-transform selector: **19 passed**.
- Raw mutation and future-ordering selector: **3 passed**.
- Phase 7 production-contract suite: **148 passed**.
- Full repository suite: **406 passed**.

## Next Phase Readiness

F-001 is behaviorally closed. Phase 7 now has executable evidence for raw OHLCV provenance and is ready for independent goal re-verification.

## Self-Check: PASSED

- All declared artifacts exist.
- All three `07-06` task commits are present.
- Both task acceptance criteria and plan-level verification commands pass.
- User-owned dirty files remain unstaged and unchanged by this plan.

---
*Phase: 07-deterministic-replay-validation*
*Completed: 2026-07-13*
