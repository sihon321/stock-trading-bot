---
phase: 09-kis-mock-soak-fault-drills
plan: 06
subsystem: fault-drills
tags: [sqlite, wal, fault-injection, restart-recovery, kis-mock, cli]
requires:
  - phase: 09-kis-mock-soak-fault-drills
    provides: mock-only campaign accounting, identity receipts, broker reconciliation, and persistent ticker freezes
provides:
  - independent FULL+WAL controller journal with durable-before-injection capability tokens
  - exhaustive immutable controlled-fault registry with exactly one activation boundary per drill
  - restart-durable containment, reconciliation, prohibited-action, and provenance evidence
  - exclusive bot soak drill command with accounting-neutral controlled execution
affects: [09-07-soak-reporting, 09-08-operator-runbook, phase-10-promotion-evidence]
tech-stack:
  added: []
  patterns: [durable capability before fault construction, append-only controller journal, single-use fault port, subprocess restart proof]
key-files:
  created: [trading_bot/soak_controller.py, trading_bot/soak_drills.py, tests/test_soak_drills.py]
  modified: [trading_bot/cli.py, tests/test_soak_cli.py]
key-decisions:
  - "A faulting collaborator is constructed only after the independent controller contract commits and survives a second-connection read-back."
  - "Controlled drills use one immutable FaultName-derived spec and a single-use port; only accepted-then-timeout crosses exactly one logical POST boundary."
  - "Controller and soak evidence link by stable IDs without ATTACH or cross-database atomicity claims, and controlled drills leave day credit and availability budget unchanged."
patterns-established:
  - "Durable capability gate: PREPARED contract -> COMMITTED row -> independent read-back -> CommittedDrillToken -> fault construction."
  - "Recovery verdicts are append-only and become PASSED only when every fault-specific D-22 observation is present and passing."
requirements-completed: [SOAK-04]
coverage:
  - id: D1
    description: "Independent controller evidence survives primary audit unavailability and process termination with FULL+WAL durability."
    requirement: SOAK-04
    verification:
      - kind: integration
        ref: "tests/test_soak_drills.py -k 'controller or journal or wal or restart or alias'"
        status: pass
    human_judgment: false
  - id: D2
    description: "All ten required faults have one immutable spec, one boundary, one activation, and an evidence-complete terminal verdict."
    requirement: SOAK-04
    verification:
      - kind: integration
        ref: "tests/test_soak_drills.py#test_every_controlled_drill_is_terminal_and_preserves_campaign_accounting"
        status: pass
    human_judgment: false
  - id: D3
    description: "Only bot soak drill exposes controlled fault authority while ordinary run and soak campaign runtimes remain injection-free."
    requirement: SOAK-04
    verification:
      - kind: integration
        ref: "tests/test_soak_cli.py#test_drill_is_the_only_cli_route_with_fault_authority"
        status: pass
    human_judgment: false
  - id: D4
    description: "Controlled and KIS-observed provenance stay separate, and controlled drills consume neither day credit nor availability budget."
    requirement: SOAK-04
    verification:
      - kind: integration
        ref: "tests/test_soak_drills.py -k 'provenance or accounting'"
        status: pass
    human_judgment: false
duration: 11 min
completed: 2026-07-20
status: complete
---

# Phase 9 Plan 6: Durable Fault Drill Controller Summary

**An independent FULL+WAL controller now commits and reads back each fault contract before a single-use drill port can activate, preserving restart-durable containment evidence without weakening campaign accounting or the authenticated 000660 freeze.**

## Performance

- **Duration:** 11 min
- **Started:** 2026-07-20T00:52:59Z
- **Completed:** 2026-07-20T01:03:59Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments

- Added a separately versioned controller database that validates all three store paths and inodes, opens only its own schema, verifies WAL plus synchronous FULL, and returns injection authority only after an independently observed commit.
- Made contracts, commit facts, observations, and terminal verdicts append-only; missing containment, primary-audit, reconciliation, restart, or prohibited-action evidence forces an irreversible FAILED verdict.
- Added exact immutable specs for stale data, malformed LLM, timed-out LLM, KIS API failure, accepted-then-timeout, throttling, partial/no fill, interruption, notification failure, and audit failure.
- Restricted controlled activation to `bot soak drill <fault>` and a drill-only builder; ordinary `run`, `_SoakRuntime`, and campaign commands gained no injection ports, flags, or environment switches.
- Verified exactly one activation per drill, exactly one logical POST only for accepted-then-timeout, subprocess termination/reopen for interruption and audit failure, query-only recovery, separated provenance, and unchanged day/budget accounting.

## Task Commits

Each TDD task was committed as a failing contract followed by its passing implementation:

1. **Task 1: Independent durable drill controller journal** — `f5674ce` (test), `a04fe27` (feat)
2. **Task 2: Named fault specs and exclusive drill command** — `a456f50` (test), `cb7f664` (feat)

## Files Created/Modified

- `trading_bot/soak_controller.py` — isolated schema migration, durable contract preparation/commit/read-back, sanitized observations, pending restart recovery, integrity checks, and one-way verdicts.
- `trading_bot/soak_drills.py` — exhaustive registry, committed-token-gated fault ports, accounting-neutral drill service, query-only reconciliation, and fresh-process restart checks.
- `trading_bot/cli.py` — sole public `bot soak drill <fault> --campaign-id ...` route.
- `tests/test_soak_drills.py` — topology, durability, migration rollback, immutable evidence, exact registry, activation/POST cardinality, provenance, accounting, and SIGTERM recovery tests.
- `tests/test_soak_cli.py` — exact command family and structural absence of ordinary-run fault authority.

## Decisions Made

- A committed row alone is insufficient injection authority: the controller opens a second connection, reads the exact contract back, and only then returns a frozen `CommittedDrillToken` used to construct the fault port.
- The controller never opens or attaches primary audit/soak databases. Cross-store facts are sanitized stable identifiers and scalar observations, so controller truth remains independent without overstating atomicity.
- Accepted-then-timeout is the sole controlled drill allowed to call the logical POST boundary, exactly once. Its recovery path and every other drill path have no resubmission capability.
- Controlled execution writes separate `CONTROLLED_INJECTION` provenance and a drill link but does not designate a day, consume availability budget, release a freeze, or alter the authenticated `000660` ambiguity contract.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Used the existing project virtual environment for verification**
- **Found during:** Task 1 RED verification
- **Issue:** The system Python is older than the dependency set used by the repository, while the existing project virtual environment provides Python 3.14 and pytest 8.4.
- **Fix:** Ran the unchanged pytest targets through `.venv/bin/python` without installing or substituting any package.
- **Files modified:** None
- **Verification:** Focused 72-test plan suite and complete 568-test repository suite pass.
- **Committed in:** N/A (execution environment only)

**2. [Rule 1 - Tracking Bug] Corrected the SDK progress percentage and stale activity label**
- **Found during:** Post-summary state self-check
- **Issue:** The state updater advanced to plan 7 and counted 25/27 completed plans, but wrote 60% from completed phases and retained the prior plan's activity description.
- **Fix:** Corrected the canonical state percentage to 93% and recorded 09-06 as the latest activity.
- **Files modified:** `.planning/STATE.md`
- **Verification:** STATE now reports plan 7 of 10, 25/27 completed plans, 93%, and `Completed 09-06 durable fault drill controller`.
- **Committed in:** Final tracking correction commit

---

**Total deviations:** 2 auto-fixed (1 blocking execution issue, 1 tracking bug).
**Impact on plan:** No product scope, dependency, broker authority, campaign semantics, or authenticated evidence changed.

## Issues Encountered

None beyond the existing system-Python mismatch documented above.

## Authentication Gates

None. The implementation and verification used deterministic local collaborators and did not perform a KIS request or order mutation.

## Known Stubs

None.

## User Setup Required

None. The drill command uses the existing mock-only `SOAK_` settings and requires an already-active campaign.

## Next Phase Readiness

- Reporting can aggregate drill outcomes by immutable fault and evidence class without combining controlled and KIS-observed denominators.
- Operator documentation can expose the exact ten accepted fault spellings and controller recovery semantics.
- The authenticated `000660` ambiguity remains frozen; this plan neither queried, resubmitted, reinterpreted, nor released it.

## Self-Check: PASSED

- All five planned files exist and task commits `f5674ce`, `a04fe27`, `a456f50`, and `cb7f664` are present.
- Plan verification passed: 72 tests across drill, CLI, campaign, and reconciliation coverage.
- Full repository regression passed: 568 tests.
- Controller/primary/soak alias rejection, WAL/FULL verification, second-connection read-back, SIGTERM restart reconstruction, missing-evidence failure, and terminal immutability all pass.
- Exact registry cardinality is 10; every controlled run activates once, only accepted-then-timeout records one POST, and all others record zero.
- Pre-existing edits in `tests/test_market_cycle.py`, `tests/test_pykrx_adapter.py`, `trading_bot/data_source.py`, `trading_bot/pykrx_adapter.py`, and `.planning/debug/` were not staged, modified, or reverted.

---
*Phase: 09-kis-mock-soak-fault-drills*
*Completed: 2026-07-20*
