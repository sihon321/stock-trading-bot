---
phase: 10-advisory-risk-calibration-promotion-readiness
plan: 04
subsystem: promotion-readiness
tags: [fail-closed, readiness, canonical-identity, manual-promotion, runbook]
requires:
  - phase: 10-advisory-risk-calibration-promotion-readiness
    provides: canonical calibration report and credential-free report CLI
  - phase: 09-kis-mock-soak-fault-drills
    provides: campaign, reconciliation, freeze, and cross-store evidence
provides:
  - pure nine-gate READY/BLOCKED assessment with PASS/BLOCK/UNKNOWN checks
  - snapshot-bound SHA-256 assessment identity
  - credential-free bot report readiness command
  - mechanically tested separate manual promotion runbook boundary
affects: [phase-10-verification, real-money-promotion-review]
tech-stack:
  added: []
  patterns: [pure fail-closed reducer, no-waiver objective gates, non-authorizing readiness snapshot]
key-files:
  created: [trading_bot/promotion_readiness.py, tests/test_promotion_readiness.py]
  modified: [trading_bot/report_cli.py, docs/operator-runbook.md, tests/test_cli.py, tests/test_operator_runbook.py]
key-decisions:
  - "Any BLOCK or UNKNOWN produces BLOCKED; manual approval cannot override an objective failure."
  - "Require 20/20 credited days, no safety latch, no incomplete/unknown reconciliation, no active freeze, and no cross-store unknown for SOAK_ACCEPTED."
  - "Treat READY as a read-only assessment, never an authorization token or persisted promotion state."
requirements-completed: [CAL-03, CAL-04]
coverage:
  - id: D1
    description: "All nine gates independently fail closed and current short/safety-failed evidence cannot be waived."
    requirement: CAL-03
    verification:
      - kind: unit
        ref: "tests/test_promotion_readiness.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "Readiness identity changes with evidence, policy, or acknowledgement facts while resolved history remains warning-only."
    requirement: CAL-03
    verification:
      - kind: unit
        ref: "tests/test_promotion_readiness.py#test_unknown_blocks_resolved_history_warns_and_identity_is_snapshot_bound"
        status: pass
    human_judgment: false
  - id: D3
    description: "CLI and runbook preserve a separate manual real-mode boundary with no settings, order, waiver, scheduling, or profitability authority."
    requirement: CAL-04
    verification:
      - kind: integration
        ref: "tests/test_cli.py tests/test_operator_runbook.py tests/test_report_cli.py"
        status: pass
    human_judgment: false
duration: 6 min
completed: 2026-08-10
status: complete
---

# Phase 10 Plan 4: Promotion Readiness Summary

**A canonical nine-gate readiness assessment now reports only evidence-linked READY/BLOCKED while the current incomplete Phase 9 campaign remains unwaivably blocked and real activation stays separate.**

## Performance

- **Duration:** 6 min
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments

- Added immutable readiness evidence/check/assessment contracts and all nine stable gate codes.
- Made every non-PASS state block, including short soak, safety latch, reconciliation uncertainty, active freeze, unresolved order, stale calibration, policy mismatch, or missing acknowledgement.
- Bound assessment identity to normalized evidence, policy snapshot, checks, warnings, and acknowledgements.
- Added `bot report readiness` over strict replay, calibration, audit, soak, controller, campaign, and policy inputs with no live composition.
- Documented evidence order, current blocker semantics, snapshot invalidation, policy freeze, rollback, kill, approval, and separate future manual real-mode procedure.

## Task Commits

1. **Task 1: Fail-closed readiness reducer** — `ea0eedc` (test), `40e09e4` (feat)
2. **Task 2: Read-only CLI and manual runbook boundary** — `4b1e247` (test/docs), `5e89be4` (feat)

## Files Created/Modified

- `trading_bot/promotion_readiness.py` — pure reducer, canonical identity, and deterministic renderer.
- `trading_bot/report_cli.py` — explicit readiness inputs and read-only composition.
- `docs/operator-runbook.md` — Phase 10 checklist and separate manual activation boundary.
- `tests/test_promotion_readiness.py`, `tests/test_cli.py`, `tests/test_operator_runbook.py` — gate matrix, discovery, and documentation contracts.

## Decisions Made

- Objective Phase 9 failures are evaluated before and independently of operator acknowledgements; there is no waiver argument.
- Determinately resolved historical ambiguity is a warning, while active freeze/ambiguity blocks.
- An otherwise `READY` synthetic normalized assessment still cannot change settings or trading mode.

## Deviations from Plan

- The report-completeness input is conservatively derived from excluded/unknown campaign cycles rather than re-querying a separate rendered daily/period text interval. It remains fail-closed and identity-bound.

## Issues Encountered

- Full pytest collection still fails in pre-existing `tests/test_soak_campaign.py` because its `CandidateReportRow` fixture omits required `reason_detail`. This defect was anticipated by the plan and was not changed.

## User Setup Required

None for assessment. Actual real-money activation remains prohibited and separate.

## Next Phase Readiness

- Phase 10 implementation is complete and ready for verification.
- Phase 9 remains 9/10 with external soak acceptance incomplete, so promotion remains `BLOCKED`.

## Self-Check: PASSED

- Focused Phase 10 and affected reporting/replay/soak suite: 166 passed.
- Full suite excluding the known collection-defective file: 664 passed.
- Python byte compilation and `git diff --check` pass.
- No KIS request, order, settings write, or real-mode action occurred.

---
*Phase: 10-advisory-risk-calibration-promotion-readiness*
*Completed: 2026-08-10*
