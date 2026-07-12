---
phase: 07-deterministic-replay-validation
plan: 03
subsystem: replay
tags: [python, typer, deterministic-replay, safety, testing]
requires:
  - phase: 07-deterministic-replay-validation
    provides: frozen scenario runner and deterministic evidence identity
provides:
  - Explicit-denominator replay gate funnel and attributed expectation checks
  - Fully offline `bot replay` command with normalized JSON evidence
  - Non-profitability contract and completed Nyquist verification map
affects: [08-operator-reporting, 09-mock-account-soak, replay-validation]
tech-stack:
  added: []
  patterns: [normalized-outcome-derived metrics, thin offline CLI composition]
key-files:
  created: []
  modified: [trading_bot/replay.py, trading_bot/cli.py, tests/test_replay.py, tests/test_cli.py, .planning/phases/07-deterministic-replay-validation/07-VALIDATION.md]
key-decisions:
  - "All funnel counts are derived from normalized stage facts and expose explicit denominators."
  - "Replay evidence and CLI always state that policy-path validation is not profitability evidence."
patterns-established:
  - "Replay CLI imports and calls only frozen replay seams; it never builds live runtime collaborators."
  - "Only failed expectation checks expand to ticker-level operator detail."
requirements-completed: [REPLAY-01, REPLAY-02, REPLAY-03, REPLAY-04]
coverage:
  - id: D1
    description: Explicit-denominator policy funnel and attributed expectation verification
    requirement: REPLAY-03
    verification:
      - kind: unit
        ref: "tests/test_replay.py -k 'funnel or verification or disclaimer'"
        status: pass
    human_judgment: false
  - id: D2
    description: Offline replay CLI with concise anomaly-only output and normalized JSON
    requirement: REPLAY-01
    verification:
      - kind: integration
        ref: "tests/test_cli.py#test_replay_command_is_offline_concise_and_writes_complete_json"
        status: pass
    human_judgment: false
  - id: D3
    description: Complete Phase 7 automated verification map and non-profitability safeguards
    requirement: REPLAY-04
    verification:
      - kind: integration
        ref: "PYTHONUSERBASE=$PWD/.python-userbase .venv/bin/python -m pytest -q (391 passed)"
        status: pass
    human_judgment: false
duration: 2min
completed: 2026-07-12
status: complete
---

# Phase 7 Plan 03: Replay Policy Evidence and CLI Summary

**Deterministic gate funnels, attributed expectation checks, and a strictly offline replay CLI with normalized non-profitability evidence**

## Performance

- **Duration:** 2 min
- **Started:** 2026-07-12T01:44:39Z
- **Completed:** 2026-07-12T01:45:57Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Derived every BUY gate, action count, and bounded block reason from normalized outcomes with explicit denominators.
- Added `bot replay` without live runtime construction, with concise summaries and mismatch-only ticker detail.
- Persisted complete canonical JSON evidence with a mandatory non-profitability disclaimer; all 391 tests pass.

## Task Commits

1. **Task 07-03-01: Derive explicit-denominator gate funnels and expectation checks** - `01c987b`
2. **Task 07-03-02: Add the offline replay CLI and close the Nyquist verification map** - `640cc1a`

## Files Created/Modified

- `trading_bot/replay.py` - Normalized stage facts, funnel, verification, and deterministic disclaimer evidence.
- `trading_bot/cli.py` - Thin offline replay command and operator presentation.
- `tests/test_replay.py` - Funnel invariants, attributed checks, and disclaimer tests.
- `tests/test_cli.py` - Offline boundary, output JSON, mismatch, and invalid-input CLI coverage.
- `.planning/phases/07-deterministic-replay-validation/07-VALIDATION.md` - Completed task mapping and Wave 0 sign-off.

## Decisions Made

- Funnel denominators follow the preceding BUY stage while action and block summaries use all evaluated outcomes.
- Actual invocation timing stays outside deterministic evidence; the CLI currently emits no observational clock data.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

- Ruff was not installed in the project virtual environment, so no lint command was available. Targeted tests and the full 391-test suite passed.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Phase 8 can consume the normalized replay JSON to produce human-readable reports without changing replay identity.
- No blockers remain for Phase 7 verification.

---
*Phase: 07-deterministic-replay-validation*
*Completed: 2026-07-12*
