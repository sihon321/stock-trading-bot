---
phase: quick-260727-d5y
plan: 01
subsystem: reporting
tags: [python, sqlite, soak, reconciliation, safety]
requires:
  - phase: 09-kis-mock-soak-fault-drills
    provides: Read-only soak evidence and reconciliation records
provides:
  - Campaign-scoped RESUME comparison validation anchored to snapshot and primary intent evidence
affects: [soak-reporting, reconciliation-safety]
tech-stack:
  added: []
  patterns:
    - Stage-aware comparison validation remains scoped to read-only report aggregation.
key-files:
  created: []
  modified:
    - trading_bot/soak_reporting.py
    - tests/test_soak_reporting.py
key-decisions:
  - "Only comparisons with run_id resume may use campaign evidence, and only with a same-campaign RESUME snapshot plus a durable primary intent."
patterns-established:
  - "Reserved campaign operation identities require evidence-specific validation, not generic primary-run validation."
requirements-completed: [QUICK-RESUME-COMPARISON-01]
coverage:
  - id: D1
    description: Valid RESUME comparison evidence contributes COMPLETE without cross-store UNKNOWN.
    requirement: QUICK-RESUME-COMPARISON-01
    verification:
      - kind: unit
        ref: tests/test_soak_reporting.py#test_campaign_scoped_resume_comparisons_require_snapshot_and_primary_intent
        status: pass
    human_judgment: false
  - id: D2
    description: Missing, malformed, and ordinary non-primary comparison references remain fail-closed UNKNOWN.
    requirement: QUICK-RESUME-COMPARISON-01
    verification:
      - kind: unit
        ref: tests/test_soak_reporting.py#test_malformed_campaign_scoped_resume_comparisons_fail_closed
        status: pass
      - kind: unit
        ref: tests/test_soak_reporting.py#test_comparison_with_ordinary_missing_run_remains_cross_store_unknown
        status: pass
    human_judgment: false
duration: 6min
completed: 2026-07-27
status: complete
---

# Quick Task 260727-d5y: Campaign-Scoped RESUME Comparisons Summary

**Read-only soak reporting now recognizes a terminal RESUME comparison only when matching campaign snapshot evidence and a durable primary order intent prove its provenance.**

## Performance

- **Duration:** 6 min
- **Completed:** 2026-07-27T00:34:48Z
- **Tasks:** 1
- **Files modified:** 2

## Accomplishments

- Added a comparison-only provenance validator that accepts the reserved `resume` identity through a same-campaign RESUME snapshot and primary intent.
- Kept generic primary-reference validation for all ordinary comparison references, snapshots, drill links, and other evidence types.
- Added regression coverage for valid RESUME evidence, malformed campaign evidence, missing intent evidence, ordinary missing runs, byte preservation, and the active `000660` AMBIGUITY freeze.

## Task Commits

1. **Task 1: Add the report-level RESUME comparison provenance contract and implement its narrow validator** - `5105ee8` (fix)

## Files Created/Modified

- `trading_bot/soak_reporting.py` - Validates campaign-scoped RESUME comparisons before report aggregation.
- `tests/test_soak_reporting.py` - Exercises anchored and fail-closed comparison evidence paths.

## Decisions Made

- The reserved `resume` run identity is never accepted by generic primary-run validation; it requires both same-campaign RESUME snapshot evidence and a known primary intent.
- Report aggregation remains read-only and does not affect ticker freezes or order execution.

## Verification

- `.venv/bin/python -m pytest tests/test_soak_reporting.py::test_campaign_scoped_resume_comparisons_require_snapshot_and_primary_intent tests/test_soak_reporting.py -q` — 15 passed.
- `.venv/bin/python -m pytest tests/test_soak_reconcile.py tests/test_soak_proof.py -q` — 15 passed.
- `.venv/bin/python -m pytest -q` — 589 passed.
- `git diff --check -- trading_bot/soak_reporting.py tests/test_soak_reporting.py` — passed.

## Deviations from Plan

None - plan executed exactly as written. The persistence foreign key prevents creating an unresolvable non-null snapshot ID through the supported store API; the missing snapshot-ID regression covers the report's fail-closed branch.

## Known Stubs

None.

## Next Phase Readiness

The report classifies only fully anchored campaign RESUME comparisons as complete while preserving ambiguity freeze visibility and order safety.

## Self-Check: PASSED

- `trading_bot/soak_reporting.py` and `tests/test_soak_reporting.py` exist in task commit `5105ee8`.
- The requested SUMMARY exists and remains intentionally uncommitted per task instructions.
