---
phase: 10-advisory-risk-calibration-promotion-readiness
plan: 03
subsystem: report-cli
tags: [typer, offline, calibration, deterministic-output, path-safety]
requires:
  - phase: 10-advisory-risk-calibration-promotion-readiness
    provides: deterministic counterfactual evaluator and canonical calibration report
provides:
  - credential-free bot report calibration command
  - strict fixture, baseline, campaign, and evidence validation
  - byte-identical terminal/file delivery with conflict-safe output
  - structural prohibition of live, broker, settings-write, and scheduling authority
affects: [10-04-promotion-readiness, operator-operations]
tech-stack:
  added: []
  patterns: [narrow offline CLI composition, content-addressed fixture identity, inherited atomic report writer]
key-files:
  created: []
  modified: [trading_bot/report_cli.py, tests/test_report_cli.py, tests/test_cli.py]
key-decisions:
  - "Require explicit audit, soak, campaign, and one-or-more replay fixture inputs; never fall back to credential-bearing Settings."
  - "Reject duplicate inodes/content, symlinks, duplicate scenario IDs, and replay calibration baselines that differ from the locked current policy."
  - "Use fixture SHA-256 identities in the canonical report and the existing atomic report text writer for optional output."
requirements-completed: [CAL-01, CAL-02, CAL-04]
coverage:
  - id: D1
    description: "Operators can run report calibration without credentials and see all policy groups with insufficient-evidence warnings."
    requirement: CAL-01
    verification:
      - kind: integration
        ref: "tests/test_report_cli.py#test_calibration_command_is_offline_and_renders_every_locked_group"
        status: pass
    human_judgment: false
  - id: D2
    description: "Terminal and saved output are deterministic and every fixture, database, and environment sentinel remains byte-identical."
    requirement: CAL-02
    verification:
      - kind: integration
        ref: "tests/test_report_cli.py#test_calibration_terminal_file_and_inputs_are_byte_identical"
        status: pass
    human_judgment: false
  - id: D3
    description: "The command exposes no real-mode, policy-write, broker-order, retry, or scheduling seam."
    requirement: CAL-04
    verification:
      - kind: unit
        ref: "tests/test_report_cli.py#test_calibration_controller_has_no_live_or_policy_mutation_seam and tests/test_cli.py#test_report_calibration_help_has_no_mutation_or_live_authority"
        status: pass
    human_judgment: false
duration: 4 min
completed: 2026-08-10
status: complete
---

# Phase 10 Plan 3: Offline Calibration CLI Summary

**`bot report calibration` now turns explicit replay and mock evidence into the canonical advisory report without credentials, live collaborators, configuration writes, or broker authority.**

## Performance

- **Duration:** 4 min
- **Started:** 2026-08-10T14:12:57+09:00
- **Completed:** 2026-08-10T14:16:00+09:00
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Registered the nested `report calibration` command with required replay fixtures, audit DB, soak DB, and campaign ID plus optional output.
- Validated existing regular non-symlink fixture inputs, duplicate inode/content, scenario identities, and exact calibration baseline before opening evidence.
- Composed only strict fixture loading, immutable variants, read-only evidence, deterministic evaluation/reporting, and the existing atomic delivery path.
- Proved cleared KIS/LLM credentials do not matter, repeated output bytes match, inputs and `.env` remain unchanged, and conflicts do not overwrite.
- Added help/source contracts excluding real-mode, confirmation, policy application, settings write, broker order, retry, and scheduling controls.

## Task Commits

1. **Tasks 1-2: Offline calibration command, deterministic output, and authority prohibition** — `232e6d9` (test), `5cc08d3` (feat)

## Files Created/Modified

- `trading_bot/report_cli.py` — strict fixture validation and credential-free calibration controller.
- `tests/test_report_cli.py` — successful offline invocation, byte preservation, output identity, invalid inputs, conflicts, and source-capability tests.
- `tests/test_cli.py` — nested discovery and forbidden-option help contract.

## Decisions Made

- Compatibility is defined by the exact locked five-field calibration baseline. Other scenario policy fields may legitimately vary inside boundary fixtures.
- Fixture identities are content hashes, not mutable path names.
- Output remains an operator artifact only; no result is persisted as an active policy or promotion state.

## Deviations from Plan

None - plan executed as specified.

## Issues Encountered

- The first compatibility check incorrectly required every focused boundary scenario to have identical non-calibration policy. It was narrowed to the intended locked calibration baseline before implementation completion.

## User Setup Required

None - existing audit/soak evidence and replay fixture paths are explicit command inputs.

## Next Phase Readiness

- Plan 10-04 can consume `calibration_id` in a separate read-only readiness assessment.
- Phase 9 remains incomplete, so any readiness result must remain `BLOCKED` regardless of advisory CLI success.

## Self-Check: PASSED

- Both TDD commits and all three planned files are present.
- The complete report CLI, top-level CLI, calibration, and calibration-reporting suite passes: 60 tests.
- Python byte compilation and `git diff --check` pass.
- Existing unrelated dirty files and debug notes were preserved.

---
*Phase: 10-advisory-risk-calibration-promotion-readiness*
*Completed: 2026-08-10*
