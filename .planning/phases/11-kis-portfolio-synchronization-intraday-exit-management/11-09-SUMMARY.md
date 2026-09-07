---
phase: 11-kis-portfolio-synchronization-intraday-exit-management
plan: 09
subsystem: intraday mutation lifecycle and transition evidence
tags: [lease, intraday, reconciliation, sqlite, transition-evidence]
requires:
  - phase: 11-08
    provides: shared shutdown lifecycle and durable transition projection
provides:
  - typed ownership-loss shutdown with unresolved reconciliation evidence
  - restart-stable risk and broker-truth transition identities
affects: [mutation_lease, intraday, portfolio_store, operator-alerts]
tech-stack:
  added: []
  patterns: [typed-fail-closed-shutdown, fact-derived-transition-subjects]
key-files:
  created: []
  modified:
    - trading_bot/mutation_lease.py
    - trading_bot/intraday.py
    - tests/test_intraday.py
    - tests/test_mutation_lease.py
    - tests/test_phase11_transitions.py
key-decisions:
  - "A state-bearing ownership loss requires a real active-cycle terminalizer; it may not manufacture a no-op terminal callback."
  - "Repeatable risk and broker-truth transition subjects derive from durable facts, while iteration IDs remain audit attribution only."
requirements-completed: [EXIT-02]
coverage:
  - id: D1
    description: Typed intraday lease loss terminalizes, reconciles, persists unresolved evidence, releases, and unlocks without a later POST.
    requirement: EXIT-02
    verification:
      - kind: integration
        ref: tests/test_intraday.py#test_typed_ownership_loss_terminalizes_reconciles_persists_and_unlocks
        status: pass
      - kind: unit
        ref: tests/test_mutation_lease.py#test_ownership_loss_forwards_unresolved_persistence_for_indeterminate_reconcile
        status: pass
    human_judgment: false
  - id: D2
    description: Equivalent production risk and broker-truth facts retain one transition identity across restart-like iterations while changed facts remain distinct.
    requirement: EXIT-02
    verification:
      - kind: integration
        ref: tests/test_phase11_transitions.py#test_recurring_production_risk_and_broker_truth_subjects_are_restart_stable
        status: pass
      - kind: integration
        ref: tests/test_phase11_transitions.py#test_changed_production_risk_and_broker_truth_facts_remain_distinct
        status: pass
    human_judgment: false
metrics:
  tasks_completed: 2
  tests: 813
status: complete
---

# Phase 11 Plan 09: Lifecycle and Transition Gap Closure Summary

Typed lease loss now runs the shared terminalize → reconcile → unresolved-evidence → release → unlock lifecycle, and recurring intraday safety facts use stable identities rather than transient iteration UUIDs.

## Accomplishments

- Forwarded unresolved reconciliation persistence through `stop_after_ownership_loss()` and reject active typed-loss cleanup without a real terminalizer.
- Exercised the direct offline `run_intraday_check()` path using a real SQLite-backed lease, including no-POST and release/unlock ordering assertions.
- Derived recurring risk subjects from ticker plus reason and broker-truth subjects from their stable failure code, preserving append-only counts and one notification decision across restart-like iterations.

## Verification

- `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_intraday.py tests/test_mutation_lease.py tests/test_phase11_transitions.py tests/test_portfolio_store.py -x` — 43 passed.
- `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` — 813 passed.
- All collaborators were injected offline seams; no live KIS request was made.

## Task Commits

1. **Task 1: Repair and prove typed ownership-loss durable cleanup**
   - `e4545cc` test(11-09): cover typed ownership-loss cleanup
   - `7688bc6` fix(11-09): complete typed ownership-loss cleanup
2. **Task 2: Stabilize recurring production risk and broker-truth transition subjects**
   - `e4545cc` test(11-09): cover typed ownership-loss cleanup
   - `7688bc6` fix(11-09): complete typed ownership-loss cleanup

## Decisions Made

- State-bearing lease-loss cleanup fails closed if no real terminalizer was composed by the caller; it never silently substitutes a no-op terminal record.
- The durable transition subject excludes fresh iteration UUIDs only for repeatable `RISK_EXIT` and `BROKER_TRUTH` facts. Lease loss, interruptions, order ambiguity, and broker orders retain their existing distinct identities.

## Deviations from Plan

None - plan executed within the existing offline SQLite and injected-collaborator test architecture.

## Known Stubs

None.

## Self-Check: PASSED

- All required production and regression-test files exist.
- Task commits `e4545cc` and `7688bc6` are present in local history.
- No new network, authentication, file-access, or schema trust boundary was introduced.
