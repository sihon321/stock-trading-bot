---
phase: 15-unattended-scheduling-service-resilience
plan: "03"
subsystem: execution
tags: [sqlite, flock, service, recovery, offline-tests]
requires:
  - phase: 15-01
    provides: Immutable service models, protected registration and shared offline fixtures
provides:
  - Owned phase15-service version 1 journal with immutable logical jobs and ordered checkpoints
  - Scoped independent expectation and single-dispatch operational admission writers
  - Separate exclusive service leadership and persistent three-restart/600-second admission
affects: [15-04, 15-07, 15-09, 15-10, 15-11, 15-13, 15-14]
tech-stack:
  added: []
  patterns: [rollbackable owned SQLite migration, bounded immediate transactions, process-exclusive flock, terminal consumed handoff]
key-files:
  created: [trading_bot/service_store.py, trading_bot/service_leader.py, tests/test_service_store.py, tests/test_service_authority.py]
  modified: []
key-decisions:
  - "Service leadership uses one fixed installation lock and never grants account POST, control reset or freeze-clearing authority."
  - "Independent expectations have deterministic scope/date/kind/input-provenance identities; runtime observations remain separate append-only evidence."
  - "Parent prepares only an exact consumed DISPATCHED handoff with dispatched_at and a previously committed daily universe; suppression or crash never restores dispatch authority."
  - "Restart denial persists MANUAL_ATTENTION until an explicit validated reset after 600 seconds; clock reversal across reset remains denial."
requirements-completed: []
coverage:
  - id: D1
    description: Owned protected migration, first-commit job/universe identity and ordered crash checkpoints
    requirement: AUTO-01
    verification:
      - kind: unit
        ref: tests/test_service_store.py#test_owned_migration_idempotence_rollback_and_foreign_rejection
        status: pass
      - kind: integration
        ref: tests/test_service_store.py#test_concurrent_claim_and_immutable_ordered_universe
        status: pass
    human_judgment: false
  - id: D2
    description: Separate append-only expectation provenance and non-replayable narrow provider admission
    requirement: AUTO-01
    verification:
      - kind: unit
        ref: tests/test_service_store.py#test_expectation_scoped_append_only_provenance_and_runtime_separation
        status: pass
      - kind: unit
        ref: tests/test_service_store.py#test_failed_suppression_never_calls_and_consumption_survives
        status: pass
    human_judgment: false
  - id: D3
    description: Live leader exclusion, durable killed-owner recovery and bounded restart admission
    requirement: AUTO-02
    verification:
      - kind: integration
        ref: tests/test_service_authority.py#test_spawn_live_owner_cannot_be_displaced_by_stale_heartbeat
        status: pass
      - kind: integration
        ref: tests/test_service_authority.py#test_killed_owner_enters_recovery_retaining_jobs_and_restart_reservation
        status: pass
      - kind: unit
        ref: tests/test_service_store.py#test_restart_reservations_persist_and_attention_requires_explicit_validated_reset
        status: pass
    human_judgment: false
duration: 45min
completed: 2026-10-04
status: complete
---

# Phase 15 Plan 03: Durable Service Journal and Leadership Summary

**불변 서비스 작업·독립 기대 증거·소비된 호출 저널과 별도 flock 리더를 구현해, 충돌 복구와 600초당 최대 3회 자동 재시작을 영속적으로 제한한다.**

## Performance

- Commit-evidenced execution interval: first RED 2026-10-04T03:45:43Z through final GREEN 2026-10-04T04:30:51Z, approximately 45min. Earlier context discovery is excluded; the interval includes the usage interruption and authorized continuation.
- Tasks: 2/2. Implementation/test files: 4.

## Accomplishments

- `ServiceJournal(settings, clock=...)` uses only the explicitly registered operational path. `initialize`/`migrate_service` own version 1, `phase15-service`, and reject foreign ownership/version, incomplete schemas, symlinks, hardlinks, nonregular files and unsafe permissions. New directories/files are 0700/0600. Migration DDL is one rollbackable transaction; all request transactions have a one-second SQLite timeout and finish before external work.
- All required service metadata, generations, jobs, job events, restart attempts, attention events, expectations, expectation health, provider admissions and heartbeat tables exist. Rejected launcher events are stored separately in `service_launcher_events`; they never count as admitted worker restarts. Append-only history has UPDATE/DELETE rejection triggers. Logical jobs and committed universe bytes cannot be replaced; event sequences and revision comparisons serialize concurrent writers.
- `ExpectationWriter.record_derived` accepts only configured `OBSERVER_DERIVED` inputs and derives identity from the complete input provenance, scope/date/kind and producer. `record_source_health` appends bounded availability facts. Runtime expectations use `RUNTIME_OBSERVED`; neither producer overwrites the other's obligation provenance. The facade has no initialization, job, restart, heartbeat, control, receipt or trading writer methods.
- `prepare_provider_admission(admission, consumed_dispatch=...)` is a parent-only handoff. The supplied committed read-back must match dispatch/evaluation/scope/target/date/envelope, `dispatch_state=DISPATCHED`, and `dispatched_at`; a daily job's universe must already be committed. Trading-owner read-back and operational prepare are deliberately separate committed transactions. Operational dispatch/evaluation uniqueness prevents duplicate handoff. `ProviderAdmissionWriter.transition_prepared` is bound to one exact dispatch/scope/envelope, validates transport-start evidence and permits only PREPARED→IN_FLIGHT/SUPPRESSED_NO_CALL/UNKNOWN and IN_FLIGHT→FINISHED/UNKNOWN. Terminal states cannot replay. Failed suppression yields no call; parent recovery records UNKNOWN while retaining consumed facts.
- `reserve_restart` commits admission before worker creation. Three admissions in a rolling 600 seconds are allowed; the fourth latches MANUAL_ATTENTION. Expiring the window, a stale heartbeat, or clock reversal never clears the latch. Explicit reset requires 600 seconds plus current positive safety and recovery validation and appends RESET history. A clock reversal behind that reset timestamp latches denial again. An admitted but never-started worker still consumes its reservation.
- `ServiceLeader(settings, journal=..., scope=None, automatic_restart=False)` holds the fixed `service-leader.lock`, distinct from account and submission locks. The first clean login and later clean login do not consume automatic-restart budget; an explicit automatic launcher restart does. Missing clean predecessor termination reserves the restart and returns RECOVERY_ONLY with unchanged jobs. Denial closes the kernel descriptor before worker authority is returned. A live predecessor cannot be displaced by stale heartbeat or replacement lock inode. Assertions check process, inode and durable generation. Descriptors are noninheritable for exec; a fork child closes its copy without unlocking the parent's open-file description. Leadership exposes no account mutation capability.

## Task Commits

| Task | Stage | Commit | Verification |
|---|---|---|---|
| 1 | RED | be29f36 | 11 expected failures from absent service_store module |
| 1 | GREEN | 5aa181d | 11 journal tests passed |
| 2 | RED | 3466e82 | 7 expected leader failures; 12 existing mutation-lease tests passed |
| 2 | GREEN | f2d24a0 | 35 combined tests passed, including journal boundary follow-ups |

## Verification

- Task 1: `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_service_store.py` → **11 passed in 0.26s** before the subsequent safety boundary additions.
- Task 2 initial GREEN: `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_service_authority.py tests/test_mutation_lease.py` → **19 passed in 1.79s**.
- Final designated verification: `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_service_store.py tests/test_service_authority.py tests/test_mutation_lease.py` → **35 passed in 2.11s**, no warnings. This includes 16 store tests, 7 service leadership tests and 12 unchanged account mutation-lease tests.
- Acceptance criteria pass: migration rollback/idempotence, ownership/link/version/mode rejection, concurrent one-winner claim, ordered immutable universe and checkpoint history, stale revision rejection, durable restart/latch/reset, clock reversal, duplicate and uncertain provider handoffs, no-call suppression failure, independent provenance, stale heartbeat exclusion, killed predecessor recovery, no account authority and automatic launcher accounting.
- `git diff --check` passed. Normal commit hooks ran. No tracked deletion or generated untracked artifact was introduced.
- All journals/configuration/evidence were temporary injected offline fixtures. Spawned children are local test processes and are stopped/joined. No package install/download, network call, production database access/migration, broker/Discord/paid-provider call, bootstrap, launchctl or service installation occurred.

## Files Created/Modified

- `trading_bot/service_store.py`: owned journal, migrations, immutable jobs/checkpoints, narrow operational writers and durable restart latch.
- `trading_bot/service_leader.py`: separate OS leader lifecycle, generation evidence and crash admission.
- `tests/test_service_store.py`: protected journal/provenance/consumption/restart behavioral checks.
- `tests/test_service_authority.py`: spawn-safe live/killed owner exclusion and recovery; uses the actual shared fixture APIs without modifying their owner.

## Decisions Made

- Global service process exclusion is separate from account mutation and control/submission authority. RECOVERY_ONLY remains operational state, not broker permission.
- The consumed parent handoff uses `dispatched_at` to match the planned trading-owner v4 schema. Later composition must obtain its read-back from the committed trading owner; this journal does not independently open that owner or claim cross-journal atomicity.
- Narrow writers operate only on their service operational rows. Persisting an observer expectation or a suppressed/uncertain admission cannot change a control, receipt, freeze or trading claim.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Reject post-reset clock reversal and close descriptors after failed SQLite connect**
- Found during Task 2's final review of Task 1 boundaries.
- A wall clock reversal after a valid RESET could otherwise admit a restart before the recorded reset instant; SQLite connection construction failure could leave a protected descriptor open.
- Compare admission time against the latest attention/reset observation and close descriptors even when no SQLite connection was constructed. Two focused regression cases exercise both failures.
- Files: service_store.py, test_service_store.py. Commit: f2d24a0. Final required suite: 35 passed.

Task 2 also completed planned handoff integration checks: committed universe before provider prepare, canonical `dispatched_at`, and UNKNOWN recovery for abandoned PREPARED/IN_FLIGHT admissions. These are the plan's required contracts, not a scope reduction.

## Issues Encountered

- Execution paused due to a usage error, then continued in the same typed executor after the parent's authorization. Committed Task 1 and Task 2 RED were retained; no restart, rollback, repeated broad regression or external action was performed.
- Installed GSD state handlers use named flags; metrics/decisions/session updates use the registered handlers. Phase-level requirement completion stays deferred and `requirements-completed` is empty.

## Known Stubs

None preventing this plan's goal. Null stopped/invocation/universe values represent explicit absent or unconsumed operational facts; they confer no authority. Synthetic fixtures provide shape/behavior proofs only.

## External Activation Blockers

- Both Phase 09-08 task 1/task 2 human approvals remain absent. No unattended trading activation is authorized.
- 000660 retains its unresolved freeze until same-subject determinate terminal broker evidence; leadership/reset cannot clear it.
- Real-money service remains refused; Phase 16 promotion is a separate deliberate gate.
- Actual protected installation, owner-GUI/login/wake lifecycle, reviewed current-date sessions, private device access and authenticated elapsed-day acceptance remain external work. Offline process tests do not claim these checks passed.
- AUTO-01/AUTO-02/FUT-04 remain pending for later composition and final phase verification.

## Next Plan Readiness

15-04 can produce the committed v4 DISPATCHED read-back. 15-07 can consume its exact handoff and operational writer, 15-10 can use durable jobs/leadership, and 15-11 can append independent expectations/source-health through the narrow facade. Full wave regression remains the parent's later verification responsibility.

## Self-Check: PASSED

- All four implementation/test paths exist.
- be29f36, 5aa181d, 3466e82 and f2d24a0 are actual commit objects observed in Git.
- Final designated suite and file/deletion/stub checks passed. No external acceptance or requirement completion is inferred.
