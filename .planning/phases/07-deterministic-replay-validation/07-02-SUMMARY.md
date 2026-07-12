---
phase: 07-deterministic-replay-validation
plan: 02
subsystem: testing
tags: [replay, deterministic, canonical-json, sha256, filesystem-safety]
requires:
  - phase: 07-deterministic-replay-validation
    provides: strict replay fixtures, offline runner, and ordered outcomes from plan 07-01
provides:
  - Complete deterministic replay manifest with separate fixture and dirty-code evidence
  - Stable SHA-256 identity over canonical manifest and ordered outcomes
  - Atomic normalized JSON persistence with traversal, symlink, and conflict safeguards
affects: [07-03, replay-cli, replay-validation]
tech-stack:
  added: []
  patterns: [strict canonical JSON evidence, deterministic-observational metadata separation, safe atomic evidence output]
key-files:
  created: []
  modified: [trading_bot/replay.py, tests/test_replay.py]
key-decisions:
  - "Hash Git HEAD and normalized replay-relevant tracked diff separately so dirty executions remain attributable."
  - "Compute result identity before embedding it and exclude invocation metadata to avoid circular or run-specific identity."
patterns-established:
  - "Canonical evidence uses sorted compact UTF-8 JSON with non-finite numbers rejected."
  - "Replay output reruns are idempotent only when existing bytes match exactly; differing content fails closed."
requirements-completed: [REPLAY-01, REPLAY-02, REPLAY-03, REPLAY-04]
coverage:
  - id: D1
    description: Complete deterministic manifest and clean/dirty tracked code evidence
    requirement: REPLAY-02
    verification:
      - kind: unit
        ref: "tests/test_replay.py#test_manifest_records_complete_deterministic_evidence"
        status: pass
      - kind: unit
        ref: "tests/test_replay.py#test_dirty_relevant_tracked_content_changes_manifest_but_untracked_does_not"
        status: pass
    human_judgment: false
  - id: D2
    description: Stable result identity changes for every deterministic input and ordered outcome but not observational metadata
    requirement: REPLAY-02
    verification:
      - kind: unit
        ref: "tests/test_replay.py#test_each_manifest_input_changes_result_identity"
        status: pass
      - kind: unit
        ref: "tests/test_replay.py#test_result_identity_is_repeatable_order_sensitive_and_metadata_independent"
        status: pass
    human_judgment: false
  - id: D3
    description: Normalized replay evidence persists atomically without path escape or silent conflicting overwrite
    requirement: REPLAY-02
    verification:
      - kind: unit
        ref: "tests/test_replay.py#test_output_is_normalized_idempotent_and_conflict_safe"
        status: pass
      - kind: unit
        ref: "tests/test_replay.py#test_output_rejects_traversal_and_symlink_escape"
        status: pass
    human_judgment: false
duration: 10min
completed: 2026-07-12
status: complete
---

# Phase 7 Plan 02: Reproducible Replay Evidence Summary

**Canonical manifests now bind frozen inputs and attributable Git state to ordered replay outcomes, while safe normalized JSON keeps observational run metadata outside stable identity.**

## Performance

- **Duration:** 10 min
- **Completed:** 2026-07-12
- **Tasks:** 2
- **Files modified:** 2 implementation/test files

## Accomplishments

- Added a complete frozen manifest with separate scenario, OHLCV, raw-signal, policy, initial-state, evaluation-time, schema, HEAD, and relevant tracked-diff evidence.
- Added strict canonical serialization and stable SHA-256 result IDs that preserve outcome order while ignoring invocation metadata.
- Added atomic normalized JSON output with idempotent same-content reruns and fail-closed traversal, symlink, and content-conflict handling.
- Verified all deterministic manifest inputs independently affect identity and the complete replay suite passes offline.

## Task Commits

Each TDD task was committed atomically as RED then GREEN, with final sensitivity coverage:

1. **Task 07-02-01 RED: manifest evidence tests** - `114c992`
2. **Task 07-02-01 GREEN: canonical manifest implementation** - `a01e662`
3. **Task 07-02-02 RED: identity and output tests** - `e33775e`
4. **Task 07-02-02 GREEN: stable identity and safe writer** - `7bdcd13`
5. **Task 07-02-02 coverage: every manifest input mutation** - `bc7e142`

## Files Created/Modified

- `trading_bot/replay.py` - Canonical JSON, complete manifest, Git code-state evidence, stable result contract, and safe writer.
- `tests/test_replay.py` - Manifest completeness, dirty-state, mutation sensitivity, metadata separation, repeatability, and filesystem safety tests.

## Decisions Made

- Replay-relevant tracked changes are normalized from `git diff --binary HEAD` and hashed independently from HEAD; untracked outputs never enter identity.
- Result identity hashes only the manifest and ordered normalized outcomes; invocation time, duration, and output path remain persisted observational metadata.
- Existing output is accepted only when byte-identical, preserving repeat-run idempotence without silently replacing conflicting evidence.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

Optional Ruff and mypy executables were not installed in the existing virtual environment. The plan-required pytest verification completed successfully with 25 tests passing.

## User Setup Required

None - implementation uses only Python standard library and local Git evidence.

## Next Phase Readiness

Plan 07-03 can consume `ReplayResult` and its normalized evidence for the CLI summary, mismatch details, and gate funnel without introducing a second identity format.

## Self-Check: PASSED

- `trading_bot/replay.py` and `tests/test_replay.py` exist.
- Commits `114c992`, `a01e662`, `e33775e`, `7bdcd13`, and `bc7e142` exist.
- `.venv/bin/python -m pytest -q tests/test_replay.py`: 25 passed.

---
*Phase: 07-deterministic-replay-validation*
*Completed: 2026-07-12*
