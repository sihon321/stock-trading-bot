---
phase: 15-unattended-scheduling-service-resilience
plan: "05"
subsystem: database
tags: [sqlite, control, flock, service-authority, revision, offline-tests]
requires:
  - phase: 15-01
    provides: Immutable installation-global control contracts and protected registration
  - phase: 15-03
    provides: Actual process-exclusive ServiceLeader and durable generation ownership
provides:
  - Protected phase15-control v1 journal and fixed actor/installation request facade
  - Durable restrictive acceptance linearized with final admission by one global flock
  - Live-service-only application with fresh all-account owner resume validation
  - Separate requested/applied/rejected facts and durable in-flight/unknown admission evidence
affects: [15-07, 15-08, 15-09, 15-10, 15-11, 15-13, 15-14]
tech-stack:
  added: []
  patterns: [append-only control evidence, bounded lock acquisition, query-only facade, source-bound resume validation]
key-files:
  created: [trading_bot/control_store.py, trading_bot/control_runtime.py, tests/test_service_controls.py]
  modified: []
key-decisions:
  - "Control acceptance belongs to the entire protected installation, independent of account selection, trading date and service generation."
  - "Actual live ServiceLeader ownership, rather than an arbitrary boolean/callback, mints the service application capability."
  - "Fresh permissive checks run before admission.lock; bounded local current-source rereads and revision/freshness checks precede application commit."
  - "Applied RUNNING is operational state only and supplies neither Phase 9 acceptance nor account/order permission."
requirements-completed: []
coverage:
  - id: D1
    description: Durable pending restrictions, installation-global revisions and protected narrow facades
    requirement: AUTO-02
    verification:
      - kind: integration
        ref: tests/test_service_controls.py#test_request_process_global_lock_busy_no_false_acceptance
        status: pass
      - kind: integration
        ref: tests/test_service_controls.py#test_request_revision_two_writers_one_winner
        status: pass
      - kind: unit
        ref: tests/test_service_controls.py#test_request_persistence_restart_and_date_no_reset
        status: pass
    human_judgment: false
  - id: D2
    description: Live service application, fresh explicit resume and stale-revision denial
    verification:
      - kind: integration
        ref: tests/test_service_controls.py#test_service_resume_checks_outside_lock_two_process_restriction_wins
        status: pass
      - kind: unit
        ref: tests/test_service_controls.py#test_service_resume_uncertain_gates_rejected_preserves_freeze_and_kill
        status: pass
      - kind: integration
        ref: tests/test_service_controls.py#test_service_capability_only_actual_live_leader_applies
        status: pass
    human_judgment: false
duration: 13min
completed: 2026-10-04
status: complete
---

# Phase 15 Plan 05: Durable Global Controls and Service Application Summary

**등록된 전체 모의 계좌의 PAUSE/KILL을 감사 기록과 함께 커밋해 즉시 적용하고, 실제 서비스 leader만 최신 revision 및 현재 안전 증거를 확인해 재개를 적용한다.**

## Performance

- Execution started: 2026-10-04T04:52:38Z. Completed approximately 2026-10-04T05:05:30Z, 13min.
- Tasks: 2/2. Implementation/test files: 3. No dependency changes.

## Accomplishments and Actual API

- `migrate_control(conn, fail_after_step=None)` owns exactly five tables under `phase15-control` v1: metadata, requests, applications, request audit and submission admissions. DDL rolls back together; foreign/unsupported/incomplete schema and absent immutable triggers fail closed. It does not change trading metadata or primary `user_version`.
- Trusted composition uses `ControlStore(settings, clock=...)`, explicit `initialize(actor=...)`, `reader()` and `request_writer(actor=...)`. Initial application is revision 0 PAUSED and installation scope is the canonical `InstallationScope` from protected registrations. Immutable setup evidence binds the full registration digest and the global lock inode. Registration narrowing, link replacement, hardlinks, unsafe modes, wrong owner/version and missing storage deny access. Existing initialization cannot reset controls.
- `ControlRequestWriter.append_request(ControlRequest)` exposes only fixed actor/full-installation writes. Its result has `status` REQUESTED/CONFLICT/UNAVAILABLE, `request_id`, optional `acceptance_revision`, `reason_code` and `idempotent`. Same ID and canonical payload returns the original accepted revision even after later requests; changed replay or stale expected revision conflicts. Acceptance revision is installation-global and strictly consecutive. Request plus attributable actor/scope/action/time audit commit in one BEGIN IMMEDIATE before success. Storage/audit failure rolls back acceptance. Conflict observations are audited without claiming an unaccepted request identity exists.
- Requests take `admission.lock`, wait at most one second for flock, and give SQLite only the remaining acceptance wait budget. `ControlStore.admission_lock()` returns an `AdmissionLock` context whose `assert_owned(store)` checks process/descriptor/inode. Descriptors are noninheritable and fork children close inherited lock copies without unlocking the parent. This is the same final-admission serialization point required by 15-08; no SQLite transaction spans POST.
- `ControlReader.effective_state(scope=None)` returns `EffectiveControl(applied, mode, acceptance_revision, pending_request_ids)`. Global mode includes applied mode and every newer accepted restrictive request immediately; pending RESUME grants nothing. `allows_buy`/`allows_daily` require RUNNING, `allows_risk_sell` excludes KILLED, and `allows_reconciliation` remains true. These express control eligibility only; all current trading gates remain independent. Rejected/conflicted resumes remain in immutable application history and are omitted from the pending-ID projection. `list_requests/list_applications/list_admissions(limit=50)` cap reads at 100 and use mode=ro/query_only. Reader and request facades expose no paths, connections, initialization, leader, application, job, trading or admission writer authority.
- `ControlStore.service_capability(actual_live_ServiceLeader)` requires exact registered settings and actual current process/durable generation ownership. `ControlApplier(capability, validate_resume=..., current_safety=..., clock=...)` uses `apply_pending(limit=100)` to append one attributable application per request. PAUSE/KILL skip permissive checks; KILL dominates PAUSE and stale queued RESUME. Only the actor recorded by explicit owner setup may weaken a restriction.
- `ResumeSafetyEvidence` contains registered scope, aware observed/expiry instants, strict broker/evidence/calendar/authority flags, safety latch, frozen subjects and at least four unique `SourceHash` identities. Expiry is bounded to ten seconds. `validate_resume(scope, now)` runs fresh potentially slow checks for every configured account outside the global lock. `current_safety(scope, now)` performs only a bounded local reread of the same evidence inside the lock. Missing/error/uncertain/stale/wrong-scope/changed-source evidence rejects resume. The highest accepted revision is reread under lock and again in the final transaction; freshness is checked after SQLite acquisition before commit. A restriction accepted while validation runs wins and records CONFLICT without any RUNNING application.
- The trusted owner-only `_record_admission(lock, scope, intent_id, submission_id, control_revision, admitted_at)` commits unique IN_FLIGHT evidence; `_finish_admission(lock, admission_id, state, finished_at)` permits only one FINISHED/UNKNOWN terminal transition. Accepted controls never remove or recall existing admission facts. Actual order guard policy/POST composition remains 15-08 responsibility; the private persistence method alone is not a submission grant.
- No control API cancels orders, liquidates holdings, clears frozen subjects, resets safety latches, grants a receipt or enables real-money operation.

## Task Commits

| Task | Stage | Commit | Verification |
|---|---|---|---|
| 1 | RED | d955675 | 15 expected failures from absent control_store module |
| 1 | GREEN | c3b9bb8 | 16 designated request/revision/persistence/capability tests passed |
| 2 | RED | d8f2d04 | 16 expected runtime failures, 17 existing checks passed |
| 2 | GREEN | 72b013a | 35 designated control tests passed |
| 2 boundary correction | FIX | 67c25df | 35 designated control tests passed; rejected resume no longer projected as pending |

## Verification

- Task 1: `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_service_controls.py -k 'request or revision or persistence or capability'` → **16 passed in 2.96s**.
- Final designated suite after the pending projection correction: `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_service_controls.py` → **35 passed in 4.89s**, no warnings.
- Covers two writers/one revision winner, duplicate/changed replay, fixed actor/full scope, restrictive acceptance before application, RUNNING→pending PAUSE BUY/daily denial with risk SELL eligibility, missing/unsafe/link/replaced-lock/version/registration refusal, rollback and append-only history, storage busy/failed audit, process-held flock returning unavailable, restart/date persistence, actual live/closed leader authority, KILL dominance, owner-only fresh all-account resume, every uncertainty/freeze/latch gate, callback failure, source changes and expiry, spawn-process KILL during unlocked validation, failed application persistence and honest immutable IN_FLIGHT/UNKNOWN admissions.
- `git diff --check` passed. Normal Git hooks ran. No tracked deletion, shared fixture edit or generated untracked artifact was introduced. No broad regression was run; the parent owns the later wave regression.
- All configuration/journals/collaborators were temporary synthetic offline fixtures. Spawned processes were joined/stopped. No package install/download, network/provider/broker/Discord call, production database access/migration, bootstrap, service installation or launchctl occurred.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical authority] Make the service capability depend on actual Phase 15-03 leadership.**
- Found during Task 2. The plan declared only 15-01 but its service-only authority needs the real shipped `ServiceLeader` and durable generation, rather than a manufactured permissive boolean.
- 15-03 was already completed before this sequential execution. The implementation verifies exact leader type/registration/current ownership and the SUMMARY records the actual 15-03 dependency. No runtime dependency or architectural replacement was introduced.
- Files: control_store.py, control_runtime.py, test_service_controls.py. Commits c3b9bb8/72b013a. Live/closed leader tests pass.

**2. [Rule 1 - Bug] Separate rejected resume from pending request display.**
- Found during final Task 2 boundary review. The initial newer-than-applied projection correctly retained restrictive mode but also showed an already REJECTED resume as pending.
- Exclude IDs with durable application outcomes from pending-ID display while retaining every accepted newer restrictive request in effective mode. Rejected facts remain append-only; applied revision stays unchanged.
- Files: control_store.py, test_service_controls.py. Commit 67c25df. Final 35-test suite includes rejected-resume pending-ID assertions.

## Known Stubs

None preventing this plan's owned goal. Initial request_id NULL means explicit owner setup, not an unattributed permission. Unaccepted conflict audit request_id NULL preserves FK truth. Unfinished admission finished_at NULL means an existing in-flight attempt, not safe retry permission. External callback composition and actual final order boundary are explicitly subsequent plans.

## External Activation Blockers

- Both Phase 09-08 task 1/task 2 approvals remain absent; applied RUNNING cannot activate unattended mutation.
- 000660 remains frozen pending same-subject determinate terminal broker evidence. No freeze facts were changed.
- Real-money service remains refused; Phase 16 promotion is separately gated.
- Actual protected installation, owner-GUI/login/wake lifecycle, reviewed current-date sessions, private device access and authenticated elapsed-day acceptance remain unperformed. Synthetic fixtures do not grant approval.
- AUTO-01/AUTO-02/FUT-04 completion remains pending complete phase proof; `requirements-completed` is empty.

## Deferred Integration Issue

- The previously reported CLI `recover_started_evaluations(conn)` call without ACTIVE account authority remains outside this scope. It stays fail closed; the parent assigned 15-07 to repair composition. No CLI, authority guard or fixture owner was weakened or modified here.

## Next Plan Readiness

15-07 can query effective daily eligibility, 15-08 can hold the same checked AdmissionLock across durable final admission and one bounded POST, and 15-09/13 can receive only fixed-actor request/read facades. 15-10 can mint service application capability from its actual acquired ServiceLeader and supply fresh validation plus bounded local source rereads. Missing control state denies submission, independently of operational restart/date changes.

## Self-Check: PASSED

- All three declared source/test paths exist and the canonical SUMMARY was written to the plan directory.
- d955675, c3b9bb8, d8f2d04, 72b013a and 67c25df are actual Git commit objects.
- Final designated tests, diff/deletion/stub checks passed. No unmodeled endpoint or trading authority surface was introduced.
- External acceptance and later final-POST composition remain explicitly separate from completed owned proofs.
