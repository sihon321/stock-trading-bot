---
phase: 09-kis-mock-soak-fault-drills
plan: 09
subsystem: proof-order
tags: [kis-mock, one-post, durable-evidence, reconciliation, fixture-safety]
requires:
  - phase: 09-kis-mock-soak-fault-drills
    provides: accepted authenticated mock profile, independent soak ledger, and query-only broker reconciliation
provides:
  - immutable non-credit PROOF_ORDER campaigns with frozen ambiguity policy
  - primary-audit intent/attempt read-back before a single-use mock POST capability
  - restart-safe reconciliation, freeze reconstruction, and cross-store ID validation
  - exact-confirmation mock-only CLI plus sanitized conflict-safe proof fixture export
affects: [09-10-authenticated-proof-checkpoint, phase-10-promotion-evidence]
tech-stack:
  added: []
  patterns: [single-use mutation capability, durable-before-external-effect, immutable proof policy, atomic exclusive fixture publication]
key-files:
  created: [trading_bot/soak_proof.py, tests/test_soak_proof.py]
  modified: [trading_bot/soak_models.py, trading_bot/soak_store.py, trading_bot/cli.py, tests/test_soak_store.py, tests/test_soak_reconcile.py, tests/test_soak_cli.py]
key-decisions:
  - "Proof orders live in a database-enforced PROOF_ORDER campaign whose credit_eligible flag is permanently false."
  - "The only POST capability is released after committed primary intent/attempt rows are independently read back, and restart can never mint another capability for that intent."
  - "Proof fixtures publish only after POST_SUBMISSION reconciliation and cross-store ID validation, with fixed allowlists and conflict-safe atomic bytes."
requirements-completed: [SOAK-01, SOAK-03]
coverage:
  - id: D1
    description: "Proof campaigns freeze profile and ambiguity policy fields and remain permanently ineligible for day credit through API and direct SQL paths."
    requirement: SOAK-01
    verification:
      - kind: integration
        ref: "tests/test_soak_store.py#test_proof_campaign_is_immutable_and_permanently_non_credit"
        status: pass
    human_judgment: false
  - id: D2
    description: "Committed primary attempt evidence is independently readable before exactly one POST, and restart rejects resubmission while rebuilding durable freezes."
    requirement: SOAK-03
    verification:
      - kind: integration
        ref: "tests/test_soak_proof.py#test_primary_attempt_is_read_back_before_exactly_one_post_and_restart_cannot_resubmit"
        status: pass
      - kind: integration
        ref: "tests/test_soak_proof.py#test_timeout_has_one_post_and_durable_ambiguity_freeze"
        status: pass
    human_judgment: false
  - id: D3
    description: "The proof CLI uses only the mock composition root after exact confirmation and negative gates create no campaign or submission capability."
    requirement: SOAK-01
    verification:
      - kind: integration
        ref: "tests/test_soak_cli.py -k 'proof_order or proof_confirmation'"
        status: pass
    human_judgment: false
  - id: D4
    description: "Proof fixture export is versioned, allowlisted, sanitized, idempotent for identical bytes, and refuses conflicting or synthetic evidence."
    requirement: SOAK-03
    verification:
      - kind: integration
        ref: "tests/test_soak_proof.py -k fixture"
        status: pass
    human_judgment: false
duration: 12 min
completed: 2026-07-16
status: complete
---

# Phase 9 Plan 9: Durable Mock Proof Order Summary

**A dedicated mock-only proof service now persists immutable non-credit policy and independently readable intent evidence before permitting one POST, then reconciles and exports only validated sanitized proof.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-16T09:31:00Z
- **Completed:** 2026-07-16T09:43:19Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments

- Added a schema-v2 `PROOF_ORDER` campaign contract with database-enforced `credit_eligible=false`, immutable accepted-profile facts, and immutable versioned ambiguity cadence.
- Added deterministic proof/run/intent/submission identities, committed primary audit evidence with independent read-back, and a single-use adapter guard that never retries POST.
- Routed accepted, rejected, and ambiguous outcomes through POST_SUBMISSION reconciliation, persisted ambiguity freezes, rebuilt active freezes on restart, and required stable primary/soak IDs before success.
- Wired `soak start --proof-order` through the narrow mock-only settings root with explicit bounded order fields, approved-profile validation, exact sanitized confirmation, and no general runtime construction.
- Added fixed-shape KIS-observed fixture projection and fsync-backed exclusive atomic publication that accepts identical bytes but never overwrites conflicts.

## Task Commits

Each TDD task was committed with a failing contract followed by its passing implementation:

1. **Task 1: Durable non-credit proof campaign and one-POST service** — `f4e0eb1` (test), `7653e01` (feat)
2. **Task 2: Explicit proof CLI and sanitized fixture export** — `51fd95f` (test), `fdb94b7` (feat)

## Files Created/Modified

- `trading_bot/soak_proof.py` — one-POST proof service, durable read-back, restart guard, cross-store validator, and fixture publisher.
- `trading_bot/soak_models.py` — stable proof campaign kind.
- `trading_bot/soak_store.py` — additive schema-v2 proof/non-credit constraints and create-or-load drift rejection.
- `trading_bot/cli.py` — explicit mock-only proof route and confirmation gate.
- `tests/test_soak_proof.py` — cardinality, restart, ambiguity, cross-ID, provenance, sanitation, and conflict tests.
- `tests/test_soak_store.py` — proof policy/non-credit API and direct-SQL immutability.
- `tests/test_soak_reconcile.py` — schema-version expectation for the additive proof campaign migration.
- `tests/test_soak_cli.py` — dedicated composition, exact confirmation, and zero-mutation negative gates.

## Decisions Made

- A proof campaign is a distinct immutable kind, not a regular soak day with a convention to withhold credit.
- Durable primary evidence is verified through a fresh read-only connection before the adapter wrapper is created, making ordering structural and observable.
- Restart identity is deterministic from immutable order inputs; an existing `SUBMISSION_ATTEMPTED` row permanently blocks another proof POST for that intent.
- Controller storage is topology-validated but never opened; primary and soak owners are linked only through stable identifiers.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated the reconciliation schema-version assertion for the additive proof migration**
- **Found during:** Task 1 focused verification
- **Issue:** The existing reconciliation ownership test correctly expected schema v1 before Plan 09-09 added the proof contract as schema v2.
- **Fix:** Updated the expected version while retaining the query-only primary and unopened-controller assertions.
- **Files modified:** `tests/test_soak_reconcile.py`
- **Verification:** Plan-focused 69-test suite and full 513-test suite passed.
- **Committed in:** `7653e01`

---

**Total deviations:** 1 auto-fixed (1 blocking compatibility assertion).
**Impact:** No scope change; the assertion now tracks the planned additive schema version.

## Issues Encountered

None.

## User Setup Required

None in this plan. The authenticated one-order action remains reserved for Plan 09-10.

## Next Phase Readiness

- Plan 09-10 can invoke the completed command at its explicit operator checkpoint.
- No authenticated proof order, cancellation, or external mutation was performed during Plan 09-09.

## Self-Check: PASSED

- All four RED/GREEN commits exist and all eight plan files are present.
- Plan verification passed: 69 tests.
- Full repository verification passed: 513 tests.
- Simulated accepted and ambiguous branches each recorded at most one POST; restart recorded zero additional POSTs.
- Unrelated working-tree changes and `.planning/debug/` were preserved and never staged.

---
*Phase: 09-kis-mock-soak-fault-drills*
*Completed: 2026-07-16*
