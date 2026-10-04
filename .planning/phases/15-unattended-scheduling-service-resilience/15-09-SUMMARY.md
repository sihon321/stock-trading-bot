---
phase: 15-unattended-scheduling-service-resilience
plan: "09"
subsystem: trading-execution
tags: [account-authority, flock, bounded-io, provider-dispatch, recovery]
requires:
  - phase: 15-03
    provides: Service journal and separate leadership exclusion
  - phase: 15-06
    provides: Owned activation and authenticated mock composition
  - phase: 15-07
    provides: Immutable consumed provider dispatch and actual transport acknowledgement
  - phase: 15-08
    provides: Concrete serialized final POST entry and effective restrictions
provides:
  - Bounded same-account acquire/recover/fresh-truth/work/reconcile/release sections
  - Released account and admission locks during daily provider waits and risk cadence
  - Stable evaluation-and-side intents and conservative response recovery
affects: [15-10, 15-11, 15-14, phase-16]
tech-stack:
  added: []
  patterns: [synchronous main-thread deadline interruption, fresh authority per section, durable blocked close]
key-files:
  created: [trading_bot/account_work.py]
  modified: [trading_bot/intraday.py, trading_bot/cli.py, trading_bot/mutation_lease.py, tests/test_service_authority.py, tests/test_phase11_cli.py, tests/test_intraday.py, tests/test_mutation_lease.py]
key-decisions:
  - "Bounded account workers use synchronous main-thread interruption, a 45-second ceiling and reserved cleanup; no abandoned thread retains late mutation capability."
  - "Failed reconciliation commits RECOVERY_BLOCKED before OS unlock; heartbeat expiry never permits takeover or healthy RELEASED evidence."
  - "Daily reservation, signal finalization and execution acquire fresh authority separately; data collection, provider response waits and cadence sleeps hold neither account exclusion nor a SQLite transaction."
  - "Final owner assertions reserve the configured single POST timeout in addition to the separate cleanup reserve, including after slow request preparation."
patterns-established:
  - "Per-pass authority and final transport-entry acknowledgement allow risk progress and restrictive request acceptance during slow LLM responses."
  - "Stable UUIDs derive from evaluation identity and actual order side, allowing existing durable admission to suppress restart replay."
requirements-completed: []
coverage:
  - id: D1
    description: Actual stalled account work is interrupted and keeps recovery-only authority after unlock
    requirement: AUTO-01
    verification:
      - kind: integration
        ref: tests/test_service_authority.py#test_real_stalled_read_is_interrupted_without_live_lock_takeover
        status: pass
      - kind: integration
        ref: tests/test_mutation_lease.py#test_preserved_blocked_release_requires_fresh_recovery
        status: pass
    human_judgment: false
  - id: D2
    description: Actual intraday composition releases authority between passes and terminates at the absolute close
    requirement: AUTO-01
    verification:
      - kind: integration
        ref: tests/test_intraday.py#test_production_intraday_root_uses_a_new_released_lease_each_pass
        status: pass
      - kind: integration
        ref: tests/test_intraday.py#test_production_intraday_check_at_terminal_never_acquires_account
        status: pass
    human_judgment: false
  - id: D3
    description: A slow daily provider leaves account and global admission locks available to risk work and KILL acceptance
    requirement: AUTO-02
    verification:
      - kind: integration
        ref: tests/test_service_authority.py#test_spawned_slow_provider_allows_risk_account_work_and_kill_acceptance
        status: pass
      - kind: integration
        ref: tests/test_phase11_cli.py#test_daily_provider_wait_releases_account_and_admission_locks
        status: pass
    human_judgment: false
  - id: D4
    description: Delayed consumed handoffs suppress calls without replay and fresh signal execution keeps one admitted intent
    requirement: AUTO-01
    verification:
      - kind: integration
        ref: tests/test_phase11_cli.py#test_consumed_handoff_barriers_suppress_transport_and_never_replay
        status: pass
      - kind: integration
        ref: tests/test_service_authority.py#test_daily_evaluation_side_intent_survives_new_execution_wrapper
        status: pass
      - kind: integration
        ref: tests/test_service_authority.py#test_final_owner_assertion_reserves_configured_post_budget_after_preparation
        status: pass
    human_judgment: false
duration: 20min
completed: 2026-10-04
status: complete
---

# Phase 15 Plan 09: Bounded Account Authority Summary

**Daily providers and risk cadence now wait outside account authority, while every owned section recovers fresh broker truth within a bounded lifecycle and preserves unresolved recovery evidence.**

## Performance

- **Duration:** 20 minutes from the first durably recorded RED gate; initial context loading was not separately timed.
- **First recorded RED gate:** 2026-10-04T10:06:36Z
- **Completed:** 2026-10-04T10:26:06Z
- **Tasks:** 2/2
- **Source/test files:** 8, including one new module.

## Accomplishments

- `BoundedAccountWork.run` acquires account exclusion, recovers non-released predecessors, commits a fresh complete same-account snapshot, runs one operation, terminalizes, saves fresh reconciliation and releases. Its work and cleanup share a maximum 45-second budget with a 10-second cleanup reserve. Main-thread `SIGALRM` interrupts synchronous blocked I/O; `AccountWorkTimeout` escapes ordinary fail-soft exception handlers. SQLite contention is capped at one second during the owned section, then the previous setting is restored. Thread workers and existing timers are denied before mutable work.
- Failed or exhausted sections durably retain `RECOVERY_BLOCKED` before closing OS exclusion. No stale heartbeat steals a live lock. Subsequent owners enter recovery and require fresh complete determinate broker truth. No timeout, release or daily failure clears a ticker freeze.
- Actual intraday composition creates a new lease per pass, uses one-pass callbacks, and releases before the 60-second sleep. It reuses existing risk, stop, quote, audit and final submission checks; no LLM is introduced. Risk budgets also end by the absolute 15:30 terminal boundary, while final session checks prohibit new POST at 15:20. Terminal `check` performs no account query or acquisition.
- Daily initialization, universe/reservation, signal persistence and current execution use separate sections. Screening, context collection, provider construction and response waits occur without account exclusion. An actual transport acknowledgement releases the shared admission flock before waiting for the response. No SQLite transaction spans the provider or broker read. Each execution refreshes held facts and available cash from broker truth, including screened-only work after held execution.
- Stable intents derive from evaluation identity and actual side. Existing primary ambiguity and durable admission enforce at most one admitted POST across a new execution wrapper. Final owner assertions check that the configured single POST timeout still fits the work budget, with cleanup reserved separately; request preparation cannot knowingly consume that allowance.
- Spawned slow-provider tests prove independent risk progress, KILL acceptance and preservation of the still-running daily lifecycle. Barriers at `ACCOUNT_RECONCILED`, `ACCOUNT_RELEASED`, `CHILD_STARTED` and `BEFORE_TRANSPORT_ENTRY` prove zero provider calls when a consumed 09:19:59 handoff reaches 09:20, PAUSE or KILL before actual entry. Suppression remains consumed and never replays. A response whose fresh account truth fails stays recoverable without execution; later recovery records UNKNOWN without another provider call.

## Task Commits

1. **Task 1 RED:** `2bca181` — `test(15-09): specify bounded account work and released watch cadence` (five expected missing-module failures).
2. **Task 1 GREEN:** `99f511d` — `feat(15-09): bound account work and preserve blocked recovery authority` (81 focused tests passed in 4.79s).
3. **Task 2 RED:** `f4f76c7` — `test(15-09): require unowned daily provider and data collection waits` (two expected held-authority failures).
4. **Task 2 GREEN:** `a57f09f` — `feat(15-09): release account authority around provider waits and risk cadence`.

All production/test commits used ordinary hooks on the authorized sequential main checkout. No tracked files were deleted, reverted or reset.

## Verification

- Relevant regression: **237 passed in 20.28s** across service authority, Phase 11 daily orchestration, intraday, mutation leases, ordinary CLI, daily dispatch, portfolio storage, service controls and exit management.
- Final terminal composition regression: **2 passed in 0.47s**, including the new 15:30 `check` case; **238 distinct tests** covered across these runs.
- The focused four-module suite passed **100 tests in 7.89s** before the last configured-POST-budget and terminal-root additions.
- A real five-second stalled callback was interrupted using a shortened 0.15-second test budget, completed under one second, retained blocked evidence and denied a live competitor. This tests the production interrupt path, not only fake clock arithmetic.
- Compilation of all four changed source modules and `git diff --check` passed. A stub scan found no TODO/FIXME/placeholder preventing the goal. No generated untracked files or tracked deletions remained.
- All checks used injected collaborators and temporary journals. No installs, live KIS, paid LLM, Discord, production DB access/migration, actual approval, service install or launchctl action occurred.

## Files Created/Modified

- `trading_bot/account_work.py` — aware/monotonic budget, synchronous interruption, fresh lifecycle and final-owner POST capacity guard.
- `trading_bot/mutation_lease.py` — public durable blocked state/close and opt-in preservation on failed shutdown.
- `trading_bot/intraday.py` — one-pass watch composition and remaining-budget checks.
- `trading_bot/cli.py` — separated daily sections, stable intents and actual per-pass intraday composition with injected offline seams.
- `tests/test_service_authority.py`, `tests/test_phase11_cli.py`, `tests/test_intraday.py`, `tests/test_mutation_lease.py` — process progress, lock probes, real stall interruption, barriers, configured POST budget and replay/terminal regressions.

## Decisions Made

Use a synchronous main-thread worker deadline rather than spawning an abandoned background callback with continuing mutation capability. Separate primary daily run lifetime from account lease lifetime, so risk work cannot terminalize a healthy daily parent merely because its provider is waiting. Keep final restrictions and unattended receipt enforcement in the existing concrete authority; manual paths retain their original gates.

## Deviations from Plan

**1. [Rule 2 - Missing Critical] Preserve blocked predecessor state when returning OS ownership**

- **Found during:** Task 1.
- **Issue:** Existing `release_after_reconciliation` always recorded `RELEASED`, including failed reconciliation, and offered no public blocked-close API.
- **Fix:** Parent assigned narrow additional ownership of `trading_bot/mutation_lease.py` and `tests/test_mutation_lease.py`. Added guarded `mark_recovery_blocked`, `close_blocked` and opt-in `preserve_blocked=True`; legacy default remains compatible while bounded production sections require preservation.
- **Verification:** Failed reconciliation, actual stalled callback, live lock contention and successor recovery tests passed.
- **Commit:** `99f511d`; subsequent whole-cleanup timer hardening is in `a57f09f`.

**Total deviations:** One critical correctness addition; no new schema, dependency or architecture.

## Issues Encountered

Existing fixtures assumed one long-lived injected lease and exactly two fixed snapshots. They now create fresh unique snapshots for every section, refresh timestamps with the injected clock and reacquire released owners on repeat invocations. No production gate was weakened to preserve the old fixture assumptions.

## User Setup Required

No new setup action was performed. Actual Phase 09-08 approvals remain absent, so unattended activation remains closed. The installed actual Codex CLI single-shot capability remains unproven and closed. Existing `000660` ambiguity freeze and target-scoped authority remain preserved.

## Next Phase Readiness

Ready for Plan 15-10 scheduling and service runtime composition. Account sections run on a main-thread worker process and require committed evidence, aware clocks and fresh complete same-account snapshots. The scheduler can favor due daily reservation over new risk ticks; it must not preempt a live bounded account owner. AUTO-01/AUTO-02 stay pending until integrated phase verification, as instructed by the orchestrator. Full wave regression is owned by the parent.

## Self-Check: PASSED

- New `trading_bot/account_work.py` exists.
- All eight changed source/test files exist.
- Commits `2bca181`, `99f511d`, `f4f76c7` and `a57f09f` exist in Git history.
- Both task verification suites, final boundary tests, compilation and diff checks passed.
