---
phase: 09-kis-mock-soak-fault-drills
plan: 04
subsystem: broker-reconciliation
tags: [kis, reconciliation, pagination, ambiguity, restart-recovery]
requires:
  - phase: 09-kis-mock-soak-fault-drills
    provides: accepted authenticated mock profile and append-only campaign/freeze ledger
provides:
  - complete campaign-scoped normalized broker snapshots and dimensioned comparisons
  - bounded three-way ambiguity reconciliation with zero resubmission capability
  - restart-persistent ticker freeze reconstruction across isolated store owners
affects: [09-05-campaign-service, 09-07-reporting, 09-09-proof-order]
tech-stack:
  added: []
  patterns: [query-retry versus single-shot POST boundary, append-before-transition evidence, exact ambiguity cardinality]
key-files:
  created: [trading_bot/soak_reconcile.py]
  modified: [trading_bot/kis_order.py, trading_bot/soak_config.py, trading_bot/soak_models.py, tests/test_soak_reconcile.py]
key-decisions:
  - "Broker snapshots are complete only when every order/fill and balance page plus required cash summary fields normalize successfully."
  - "A bounded ambiguity window is determinate only when every observation agrees on zero matches or one stable broker order; mixed, multiple, or incomplete observations stay frozen."
  - "Reconciliation opens primary audit read-only and soak storage through their owning schemas while validating but never opening the controller database."
patterns-established:
  - "Normalized broker truth is filtered to campaign-touched IDs and tickers before append-only persistence."
  - "Ticker freeze release follows an appended same-subject determinate terminal broker observation and is independent from day credit."
requirements-completed: [SOAK-03]
coverage:
  - id: D1
    description: "Complete multi-page KIS order, fill, holding, and cash truth is normalized, campaign-scoped, persisted, and compared by independent evidence dimensions."
    requirement: SOAK-03
    verification:
      - kind: integration
        ref: "tests/test_soak_reconcile.py -k 'snapshot or pagination or comparison or unrelated or contradiction'"
        status: pass
    human_judgment: false
  - id: D2
    description: "Ambiguous submissions retain exact zero/one/multiple cardinality across a campaign-frozen bounded query window and perform no reconciliation POST."
    requirement: SOAK-03
    verification:
      - kind: integration
        ref: "tests/test_soak_reconcile.py tests/test_kis_broker.py -k 'ambiguous or partial or restart or post'"
        status: pass
    human_judgment: false
  - id: D3
    description: "Primary-audit origins and soak-owned truth remain linked by stable campaign/run/ticker/order/snapshot/comparison IDs while controller storage stays unopened."
    requirement: SOAK-03
    verification:
      - kind: integration
        ref: "tests/test_soak_reconcile.py#test_reconciliation_uses_primary_origin_and_soak_owner_without_opening_controller"
        status: pass
    human_judgment: false
  - id: D4
    description: "Partial and no-fill ticker freezes survive a fresh store connection and remain independent from reconciliation completeness and day credit."
    requirement: SOAK-03
    verification:
      - kind: integration
        ref: "tests/test_soak_reconcile.py#test_partial_fill_freeze_rebuild_survives_reopen_and_day_credit_is_separate"
        status: pass
    human_judgment: false
duration: 11 min
completed: 2026-07-16
status: complete
---

# Phase 9 Plan 4: Broker-Truth Reconciliation Summary

**A GET-only broker reconciler now proves complete campaign-scoped KIS truth, preserves exact ambiguity cardinality, and reconstructs unresolved ticker freezes across restarts without resubmission.**

## Performance

- **Duration:** 11 min
- **Started:** 2026-07-16T09:16:46Z
- **Completed:** 2026-07-16T09:27:46Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Collected all accepted-profile order/fill and balance pages into frozen normalized snapshots, discarded unrelated account rows, and rejected partial pagination or missing cash summary as incomplete truth.
- Compared requested, filled, remaining, state, holding, and available-cash dimensions independently; persisted snapshot and comparison IDs before permanently latching a complete contradiction as D-09 failure.
- Loaded immutable ambiguity cadence from the campaign row, appended every bounded observation, preserved exact no/one/multiple cardinality, and kept all reconciliation paths incapable of order POST.
- Rebuilt ambiguity and remaining-order ticker freezes from append-only transitions after a fresh connection while keeping reconciliation completeness and day credit separate.

## Task Commits

Each TDD task was committed with a failing contract followed by its passing implementation:

1. **Task 1: Collect and compare complete campaign-scoped broker snapshots** — `5c5a2eb` (test), `777943f` (feat)
2. **Task 2: Reconcile ambiguity and rebuild ticker freezes without resubmission** — `cdb5426` (test), `359485e` (feat)

## Files Created/Modified

- `trading_bot/soak_reconcile.py` — frozen broker truth, comparison dimensions, ambiguity policy/cardinality, append ordering, primary-origin reads, isolated store handles, and restart freeze reconstruction.
- `trading_bot/kis_order.py` — accepted-profile allowlist additions for stable broker organization, fill, and order-state fields while retaining bounded GET retry and single-shot POST.
- `trading_bot/soak_config.py` — reusable canonical three-store path/inode topology validator.
- `trading_bot/soak_models.py` — explicit RESUME and PRE_FINALIZE reconciliation stages.
- `tests/test_soak_reconcile.py` — campaign scoping, completeness, contradiction, cardinality, zero-POST, store ownership, and restart coverage.

## Decisions Made

- A complete KIS response is not a complete reconciliation snapshot unless both paginated inquiry families and required normalized cash fields are complete.
- An accepted-then-timeout origin may have one historical POST, but every later ambiguity observation is inquiry-only and cannot authorize an automatic retry.
- One determinate partial/no-fill match establishes broker identity but does not release the unresolved ticker freeze until terminal broker truth is appended.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Extracted and enforced the canonical three-store topology at reconciliation open**
- **Found during:** Task 2 (restart reconciliation and store ownership)
- **Issue:** The plan required primary-audit reads, soak-owned writes, and an unopened controller path, but the existing topology check was embedded only inside `SoakSettings` validation and could not guard direct reconciliation store construction.
- **Fix:** Added reusable path/inode validation and an owner-specific opener that sets primary audit `query_only`, opens the soak schema normally, and never opens or creates the controller DB.
- **Files modified:** `trading_bot/soak_config.py`, `trading_bot/soak_reconcile.py`, `tests/test_soak_reconcile.py`
- **Verification:** The store-ownership integration test resolves primary order origin IDs, confirms soak schema ownership, and confirms controller absence.
- **Committed in:** `359485e`

---

**Total deviations:** 1 auto-fixed (1 missing critical).
**Impact on plan:** The addition closes the required trust boundary without changing architecture or introducing a dependency.

## Issues Encountered

- Ruff is not installed in the project runtime, so verification used Python compilation, focused pytest contracts, and the complete repository suite. No package was installed.

## User Setup Required

None - reconciliation consumes the already approved mock profile and existing local store paths.

## Next Phase Readiness

- Plan 09-05 can invoke STARTUP, RESUME, PRE_RUN, POST_SUBMISSION, and PRE_FINALIZE reconciliation stages through the query-only service.
- Plan 09-09 can reuse exact ambiguity cardinality, primary/soak stable IDs, and restart freeze reconstruction for the separately gated proof order.
- No blocker remains; controller ownership is validated but intentionally unopened by ordinary reconciliation.

## Self-Check: PASSED

- All five created/modified plan files exist and the four RED/GREEN commits are present.
- Focused plan verification passed: 38 tests.
- Full repository regression passed: 506 tests.
- No raw KIS payload, credential, full account identifier, or unrelated account row is persisted.
- Reconciliation performs GET inquiries only; the existing order POST remains single-shot and undecorated by retry.
- Unrelated working-tree changes and `.planning/debug/` were preserved and never staged.

---
*Phase: 09-kis-mock-soak-fault-drills*
*Completed: 2026-07-16*
