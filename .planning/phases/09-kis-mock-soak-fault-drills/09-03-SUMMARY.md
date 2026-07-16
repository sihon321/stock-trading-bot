---
phase: 09-kis-mock-soak-fault-drills
plan: 03
subsystem: soak-persistence
tags: [sqlite, append-only, campaign-ledger, reconciliation, freeze-recovery]
requires:
  - phase: 09-kis-mock-soak-fault-drills
    provides: authenticated accepted KIS mock profile fingerprint and normalized field contract
provides:
  - independent versioned SQLite campaign and broker-evidence ledger
  - immutable campaign policy and irreversible failure accounting
  - restart-durable ambiguity and remaining-order freeze transitions
affects: [09-04-reconciliation, 09-05-campaign-service, 09-09-proof-order]
tech-stack:
  added: []
  patterns: [begin-immediate migration, append-only evidence triggers, immutable cross-store IDs, broker-evidence-gated freeze release]
key-files:
  created: [trading_bot/soak_store.py, tests/test_soak_store.py]
  modified: []
key-decisions:
  - "The soak ledger owns an independent schema and references primary-audit/controller facts only through stable IDs, never SQLite ATTACH."
  - "Availability exhaustion and D-09 safety failure use distinct immutable latches so one dimension cannot masquerade as or reset the other."
  - "Ticker freeze history is append-only; release requires same-subject, determinate, terminal broker evidence."
requirements-completed: [SOAK-02, SOAK-03]
coverage:
  - id: D1
    description: "The independent soak schema migrates atomically and preserves immutable policy plus append-only normalized evidence across connections."
    requirement: SOAK-03
    verification:
      - kind: integration
        ref: "tests/test_soak_store.py -k 'migration or immutable or append or reopen or unique'"
        status: pass
    human_judgment: false
  - id: D2
    description: "Campaign availability and safety accounting remain separate, monotonic, and irreversible after restart."
    requirement: SOAK-02
    verification:
      - kind: integration
        ref: "tests/test_soak_store.py -k 'campaign or budget or failure or restart'"
        status: pass
    human_judgment: false
  - id: D3
    description: "Ambiguity and remaining-order freezes survive restart and release only from determinate terminal broker evidence while day credit remains independent."
    requirement: SOAK-03
    verification:
      - kind: integration
        ref: "tests/test_soak_store.py -k 'freeze or restart'"
        status: pass
    human_judgment: false
duration: 10 min
completed: 2026-07-16
status: complete
---

# Phase 9 Plan 3: Durable Campaign Ledger Summary

**An independent SQLite ledger now makes soak policy, campaign accounting, normalized broker observations, and ticker-freeze recovery durable and tamper-resistant across connections and process restarts.**

## Performance

- **Duration:** 10 min
- **Started:** 2026-07-16T08:59:00Z
- **Completed:** 2026-07-16T09:09:44Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Added a rollback-safe, idempotent soak-only schema with immutable campaign policy, append-only evidence triggers, foreign keys, cross-ID/time indexes, and stable snapshot transactions.
- Kept availability budget use, permanent safety failure, designated-day credit, drill links, reconciliation completeness, and freeze state as independently persisted dimensions.
- Persisted sanitized campaign events, identity receipts, normalized snapshots, comparisons, ambiguity observations, and broker-evidence-gated freeze transitions with immediate commits and restart reconstruction.

## Task Commits

Each TDD task was committed with a failing contract followed by its passing implementation:

1. **Task 1: Migrate an append-only campaign and broker-evidence schema atomically** — `0c0a341` (test), `e86ddde` (feat)
2. **Task 2: Enforce campaign accounting and persistent freeze transitions in storage** — `946a1b1` (test), `1a47945` (feat)

## Files Created/Modified

- `trading_bot/soak_store.py` — independent schema migration, immutable campaign APIs, normalized snapshot persistence, accounting latches, and append-only freeze state machine.
- `tests/test_soak_store.py` — migration rollback/reopen, policy immutability, uniqueness, sanitization, cross-connection durability, budget/failure, and restart-freeze matrix.

## Decisions Made

- Kept the soak DB independent from the primary audit and controller DBs; only stable campaign/run/ticker/order/drill identifiers cross boundaries.
- Represented availability exhaustion separately from the safety-breach code while making both terminal failure causes immutable.
- Modeled freeze release as a new append-only transition rather than updating the original freeze fact.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - the already approved profile can be fingerprinted and stored without retaining credentials or raw KIS payloads.

## Next Phase Readiness

- Plan 09-04 can append complete campaign-scoped broker snapshots and comparisons into the ledger.
- Reconciliation services can reconstruct active ambiguity and remaining-order freezes without acquiring a submission capability.

## Self-Check: PASSED

- Both planned files exist and all four RED/GREEN task commits are present.
- Focused store/audit verification passed: 24 tests.
- Full repository suite passed: 499 tests.
- Unrelated working-tree changes and `.planning/debug/` were preserved and never staged.

---
*Phase: 09-kis-mock-soak-fault-drills*
*Completed: 2026-07-16*
