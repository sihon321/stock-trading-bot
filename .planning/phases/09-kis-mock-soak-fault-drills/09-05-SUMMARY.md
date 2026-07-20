---
phase: 09-kis-mock-soak-fault-drills
plan: 05
subsystem: soak-campaign
tags: [kis-mock, campaign-accounting, reconciliation, cli, fail-closed]
requires:
  - phase: 09-kis-mock-soak-fault-drills
    provides: accepted mock profile, independent soak ledger, query-only reconciliation, and authenticated proof freeze
provides:
  - evidence-gated eligible-day accounting with immutable availability and safety latches
  - explicit mock-only soak start, run, resume, and read-only status commands
  - ordered STARTUP, RESUME, PRE_RUN, POST_SUBMISSION, and PRE_FINALIZE reconciliation gates
  - global active-freeze projection into the production decision and order path
affects: [09-06-fault-drills, 09-07-soak-reporting, phase-10-promotion-evidence]
tech-stack:
  added: []
  patterns: [mock-only capability root, reconciliation cardinality gate, evidence-derived day credit, global durable freeze preflight]
key-files:
  created: [trading_bot/soak_campaign.py, tests/test_soak_campaign.py]
  modified: [trading_bot/cli.py, tests/test_soak_cli.py]
key-decisions:
  - "A non-credit verdict is persisted as evidence but does not create a soak_days attempt row."
  - "All active soak freezes, including the authenticated 000660 proof ambiguity, are projected into the designated run preflight regardless of campaign ownership."
  - "POST_SUBMISSION reconciliation is triggered from accepted or ambiguous post-boundary order evidence and its cardinality must equal the declared submission count."
requirements-completed: [SOAK-01, SOAK-02, SOAK-03]
coverage:
  - id: D1
    description: "Only one complete designated terminal mock run on a confirmed KRX date can earn credit; zero-order and HOLD remain eligible."
    requirement: SOAK-02
    verification:
      - kind: integration
        ref: "tests/test_soak_campaign.py#test_day_credit_matrix_is_fail_closed_and_persisted_only_when_eligible"
        status: pass
    human_judgment: false
  - id: D2
    description: "Availability budget, irreversible safety failure, drill coverage, eligible-day credit, and ticker freezes remain independent durable dimensions."
    requirement: SOAK-02
    verification:
      - kind: integration
        ref: "tests/test_soak_campaign.py -k 'availability or safety or freeze'"
        status: pass
    human_judgment: false
  - id: D3
    description: "Explicit campaign commands use mock-only adapters and surround every mutation boundary with required reconciliation while resume has no submission call."
    requirement: SOAK-01
    verification:
      - kind: integration
        ref: "tests/test_soak_cli.py -k 'command_family or reconciliation or resume or status'"
        status: pass
    human_judgment: false
  - id: D4
    description: "The authenticated 000660 ambiguity remains restart-persistent, non-credit, and frozen."
    requirement: SOAK-03
    verification:
      - kind: integration
        ref: "read-only data/soak.db active-freeze query plus full 541-test suite"
        status: pass
    human_judgment: false
duration: 12 min
completed: 2026-07-20
status: complete
---

# Phase 9 Plan 5: Mock Soak Campaign Orchestration Summary

**A mock-only campaign service now grants eligible-day credit solely from complete durable evidence while explicit CLI orchestration reconciles broker truth around every submission and preserves all active ambiguity freezes.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-20T00:36:20Z
- **Completed:** 2026-07-20T00:48:10Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Added a campaign state machine that admits only confirmed KRX trading dates, persists stable non-credit verdicts without consuming attempts, credits complete HOLD/zero-order days, and limits each date to one designated terminal run.
- Kept availability-budget exhaustion, exhaustive D-09 safety failures, controlled drill coverage, day credit, and ticker freezes independent and restart-durable.
- Added exact `bot soak start`, `run`, `resume`, and read-only `status` commands using `SoakSettings`, pairwise-distinct stores, actual KIS mock adapters, and the shipped production decision/risk/sizing path.
- Enforced STARTUP/RESUME/PRE_RUN/POST_SUBMISSION/PRE_FINALIZE ordering and submission-to-reconciliation cardinality, with no execution call on resume.
- Projected every active soak freeze into designated-run preflight, preserving the authenticated `000660` ambiguity across campaign boundaries without release, reinterpretation, resubmission, or day credit.

## Task Commits

Each TDD task was committed as a failing contract followed by its passing implementation:

1. **Task 1: Eligible-day campaign and irreversible safety state machine** — `25f6e81` (test), `38b722e` (feat)
2. **Task 2: Mock-only commands around reconciliation gates** — `e7f51f1` (test), `5c7e95e` (feat)

## Files Created/Modified

- `trading_bot/soak_campaign.py` — campaign admission, stable verdict derivation, availability accounting, safety latching, drill separation, finalization, and status.
- `tests/test_soak_campaign.py` — real-SQLite credit, non-credit, budget, safety, uniqueness, denominator, reconciliation, and freeze matrices.
- `trading_bot/cli.py` — narrow mock-only runtime, production order-event hook, ordered orchestration, and explicit campaign commands.
- `tests/test_soak_cli.py` — command discovery, stage ordering, reconciliation blocking, resume zero-submission, and read-only status contracts.

## Decisions Made

- Non-credit cases append a stable `DAY_NOT_CREDITED` event but never insert a `soak_days` row, so closed/unknown/preview/dry-run/drill/rerun/incomplete evidence cannot consume an eligible-day attempt.
- A designated run imports all currently active soak freezes into production preflight, not only freezes owned by its campaign. This keeps the authenticated proof ambiguity globally effective at the money-moving boundary.
- The order evidence sink invokes POST_SUBMISSION reconciliation only after `SUBMISSION_ACCEPTED` or `SUBMISSION_AMBIGUOUS`, and finalization refuses a mismatch between observed reconciliations and declared submission count.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Applied durable freezes across campaign boundaries**
- **Found during:** Task 2 mock-only runtime composition
- **Issue:** Campaign-scoped freeze reconstruction alone would not protect a regular soak campaign from the authenticated proof campaign's unresolved `000660` ambiguity.
- **Fix:** Reduced every active, unreleased soak freeze into the production preflight frozen-ticker map before the designated run can reach LLM or broker mutation.
- **Files modified:** `trading_bot/cli.py`, `tests/test_soak_cli.py`
- **Verification:** Read-only soak DB evidence still reports `000660` as `AMBIGUITY/FROZEN`; full repository suite passes.
- **Committed in:** `5c7e95e`

**2. [Rule 3 - Blocking] Used the existing project virtual environment for verification**
- **Found during:** Task 1 RED verification
- **Issue:** System Python 3.9 cannot import the installed pytest dependency set because it lacks the required typing APIs.
- **Fix:** Ran unchanged verification commands through the existing Python 3.14 `.venv` without installing or substituting packages.
- **Files modified:** None
- **Verification:** Plan-focused 89-test suite and complete 541-test suite pass.
- **Committed in:** N/A (execution environment only)

---

**Total deviations:** 2 auto-fixed (1 missing critical, 1 blocking environment issue).
**Impact:** Safety was strengthened without expanding broker authority, changing dependencies, or mutating authenticated proof evidence.

## Issues Encountered

- Ruff is not installed in the project environment. Python compilation, focused pytest coverage, diff checks, and the full repository suite were used instead; no package was installed.

## Authentication Gates

None. No external KIS request or order mutation was performed while implementing this plan.

## Known Stubs

None.

## User Setup Required

None. Campaign commands continue to use the existing `SOAK_` mock credentials, accepted-profile fixture, and isolated database paths.

## Next Phase Readiness

- Fault-drill plans can use the campaign service without affecting clean-day or availability accounting.
- Reporting can project stable persisted verdict codes and reconciliation stages.
- The authenticated `000660` proof remains non-credit and frozen; only same-subject determinate terminal broker evidence may release it.

## Self-Check: PASSED

- All four planned files exist and task commits `25f6e81`, `38b722e`, `e7f51f1`, and `5c7e95e` are present.
- Plan verification passed: 89 tests.
- Full repository regression passed: 541 tests.
- `data/soak.db` read-only evidence still contains `proof-order-20260720-000660-buy-1 / 000660 / AMBIGUITY / FROZEN`.
- No controller database was opened by ordinary campaign status or reconciliation composition.
- Pre-existing edits in `tests/test_market_cycle.py`, `tests/test_pykrx_adapter.py`, `trading_bot/data_source.py`, `trading_bot/pykrx_adapter.py`, and `.planning/debug/` were not staged, modified, or reverted.

---
*Phase: 09-kis-mock-soak-fault-drills*
*Completed: 2026-07-20*
