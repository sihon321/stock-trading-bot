---
phase: 10-advisory-risk-calibration-promotion-readiness
plan: 01
subsystem: calibration-evidence
tags: [sqlite, read-only, calibration, evidence-grading, policy-catalog]
requires:
  - phase: 09-kis-mock-soak-fault-drills
    provides: primary audit evidence, designated soak days, reconciliation comparisons, and durable freezes
provides:
  - immutable baseline and one-field-only calibration variant catalog
  - exact candidate values for confidence, position size, stop loss, and take profit
  - byte-preserving two-store calibration evidence projection
  - normal, excluded, unknown, and risk-case denominators with short-sample grading
affects: [10-02-counterfactual-evaluation, 10-03-calibration-cli, 10-04-promotion-readiness]
tech-stack:
  added: []
  patterns: [pure policy contracts, mode-ro query-only transactions, exact schema validation, provenance-separated denominators]
key-files:
  created: [trading_bot/calibration.py, trading_bot/calibration_reporting.py, tests/test_calibration.py, tests/test_calibration_reporting.py]
  modified: []
key-decisions:
  - "Treat one designated run as one calibration cycle and retain its decision rows as nested allowlisted observations."
  - "Grade from credited eligible days and integrity, never decision or drill row counts."
  - "Keep missing cash and average-price state explicitly unevaluable instead of reconstructing portfolio facts from incomplete audit data."
  - "Exclude reconciliation uncertainty, incomplete runs, broken references, and ticker freezes from normal comparison denominators."
patterns-established:
  - "Calibration policy modules carry no settings, filesystem, provider, or broker capability."
  - "Calibration evidence opens each owner independently in mode=ro/query_only and reconciles cross-store IDs in Python without ATTACH."
requirements-completed: [CAL-01, CAL-02, CAL-04]
coverage:
  - id: D1
    description: "The exact immutable baseline and one-variable-at-a-time candidate catalog rejects malformed or multi-field variants."
    requirement: CAL-01
    verification:
      - kind: unit
        ref: "tests/test_calibration.py"
        status: pass
    human_judgment: false
  - id: D2
    description: "Calibration evidence remains byte preserving and separates normal, excluded, unknown, and abnormal risk cases."
    requirement: CAL-02
    verification:
      - kind: integration
        ref: "tests/test_calibration_reporting.py"
        status: pass
    human_judgment: false
  - id: D3
    description: "Ten eligible days remain INSUFFICIENT even with 120 decisions and 50 drill rows, and missing portfolio state remains unevaluable."
    requirement: CAL-04
    verification:
      - kind: integration
        ref: "tests/test_calibration_reporting.py#test_denominator_uses_eligible_days_not_decision_or_drill_rows"
        status: pass
    human_judgment: false
duration: 7 min
completed: 2026-08-10
status: complete
---

# Phase 10 Plan 1: Calibration Inputs Summary

**An immutable one-field policy catalog and exact-schema read-only evidence projection now prevent short, abnormal, or structurally incomplete mock evidence from acquiring false calibration precision.**

## Performance

- **Duration:** 7 min
- **Started:** 2026-08-10T13:56:09+09:00
- **Completed:** 2026-08-10T14:03:07+09:00
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Locked the baseline and ten deterministic one-field variants across independent BUY/SELL confidence, maximum position, stop-loss, and take-profit fields.
- Added exact audit/soak schema validation and independent `mode=ro`/`query_only` transactions with no migration, `ATTACH`, configuration mutation, or broker capability.
- Projected one designated run as one observed cycle while retaining only bounded action, confidence, current-price, risk-override, cash, and average-price facts.
- Separated incomplete runs, broken primary references, reconciliation failure/UNKNOWN, ambiguity, active freezes, and safety latches from normal comparison evidence.
- Kept a 10-day campaign at `INSUFFICIENT` regardless of raw decision or drill volume and emitted `UNEVALUABLE_MISSING_PORTFOLIO_STATE` when cash or average prices are absent.

## Task Commits

Each TDD task was committed as a failing contract followed by its passing implementation:

1. **Task 1: Exact baseline, candidate catalog, and one-field invariant** — `828202d` (test), `ef6a518` (feat)
2. **Task 2: Read-only normal and abnormal evidence projection** — `0f2948b` (test), `aacb816` (feat)

## Files Created/Modified

- `trading_bot/calibration.py` — frozen policy, variant, evidence-grade, and source-count contracts plus the exact candidate catalog.
- `tests/test_calibration.py` — baseline values, catalog order, one-field invariant, numeric validation, and independence regressions.
- `trading_bot/calibration_reporting.py` — exact-schema read-only audit/soak projection, cross-store resolution, evidence grading, and risk cases.
- `tests/test_calibration_reporting.py` — byte/version preservation, abnormal filtering, broken references, short-sample denominator, and missing-schema tests.

## Decisions Made

- A calibration cycle is a designated run, not a decision row. Decision rows remain nested observations so a busy day cannot inflate the evidence denominator.
- `COMPLETED` mock `RUN` records with terminal credited designation are the only normal-cycle candidates; `COMPLETED_WITH_ERRORS` is not silently accepted.
- Missing portfolio state is recorded as an explicit unevaluable risk fact. Audit decisions are not used to invent available cash or held-position average prices.
- Twenty credited days can only become `SUFFICIENT` when integrity blockers are absent; ten days are always `INSUFFICIENT`.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - this plan is advisory and read-only.

## Next Phase Readiness

- Plan 10-02 can evaluate the immutable catalog against frozen replay fixtures and use this projection only for source counts and observed risk context.
- Promotion remains blocked: this plan does not complete Phase 9, enable real mode, mutate settings, or treat the current short sample as promotion evidence.

## Self-Check: PASSED

- All four TDD commits exist and all four planned source/test files are present.
- `15` focused tests pass across policy and evidence contracts.
- Python byte compilation and `git diff --check` pass.
- Existing unrelated working-tree changes and debug notes were not staged, modified, or reverted.

---
*Phase: 10-advisory-risk-calibration-promotion-readiness*
*Completed: 2026-08-10*
