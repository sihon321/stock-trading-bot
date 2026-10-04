---
phase: 15-unattended-scheduling-service-resilience
plan: "10"
subsystem: service-runtime
tags: [kst, scheduling, observer, multiprocessing, recovery, single-shot]
requires:
  - phase: 15-03
    provides: Protected service journal, leader and narrow expectation/admission writers
  - phase: 15-05
    provides: Durable installation controls and serialized restrictive acceptance
  - phase: 15-06
    provides: Owned mock activation and concrete production composition
  - phase: 15-07
    provides: Saved envelopes and actual transport entry acknowledgement
  - phase: 15-09
    provides: Main-thread bounded fresh account authority
provides:
  - Exact-date pure schedule with locked daily deadlines and coalesced risk slots
  - Independent protected observer obligations with query-only historical absence reading
  - Recovery-first runtime with spawned provider-only children and persistent overnight leadership
  - Typed concrete account trading binding contracts for the installed CLI root
affects: [15-11, 15-13, 15-14, phase-16]
tech-stack:
  added: []
  patterns: [pure exact-date reducer, independent observer provenance, spawn-only provider isolation, fresh account sections, idle supervisor]
key-files:
  created: [trading_bot/service_schedule.py, trading_bot/service_runtime.py, tests/test_service_schedule.py, tests/test_service_recovery.py]
  modified: [trading_bot/service_store.py]
key-decisions:
  - "A present config/login/control sample cannot manufacture authority for a past due interval; independently persisted observer history remains separate from runtime progress."
  - "Provider children receive only provider settings, a frozen envelope and narrow operational admission inputs; spawn never inherits account or leader descriptors."
  - "15:30 terminalizes the risk session while service leadership remains IDLE; a new exact trading date requires renewed activation, controls and fresh account recovery."
  - "Installed account work must bind concrete KISBroker and registered SubmissionAuthority/OwnedActivationCheck; truth callbacks and a runtime wiring Boolean cannot grant trading authority."
requirements-completed: []
coverage:
  - id: D1
    description: Exact locked KST deadlines, delayed sessions and coalesced risk slots
    verification:
      - kind: unit
        ref: tests/test_service_schedule.py#test_locked_schedule_priority_cadence_and_no_backlog
        status: pass
      - kind: unit
        ref: tests/test_service_schedule.py#test_delayed_open_misses_daily_and_absolute_close_terminates
        status: pass
    human_judgment: false
  - id: D2
    description: Independent observer publication detects absent schedules without runtime jobs or invented historical authority
    verification:
      - kind: integration
        ref: tests/test_service_schedule.py#test_observer_only_midnight_publishes_current_date_absence
        status: pass
      - kind: integration
        ref: tests/test_service_schedule.py#test_trading_crash_before_expectation_still_detects_absent_schedule
        status: pass
      - kind: unit
        ref: tests/test_service_schedule.py#test_pause_kill_and_present_samples_never_invent_due_history
        status: pass
    human_judgment: false
  - id: D3
    description: Spawned single-shot calls enforce current transport entry restrictions and wait outside account/admission authority
    verification:
      - kind: integration
        ref: tests/test_service_recovery.py#test_spawned_entry_after_startup_rechecks_current_restrictions
        status: pass
      - kind: integration
        ref: tests/test_service_recovery.py#test_inflight_response_unlocks_control_and_healthy_risk_progress
        status: pass
      - kind: integration
        ref: tests/test_service_recovery.py#test_child_timeout_and_stop_are_consumed_unknown_and_preserve_kill
        status: pass
    human_judgment: false
  - id: D4
    description: Exclusive recovery preserves saved inputs, consumed dispatches and overnight controls before next-day work
    verification:
      - kind: integration
        ref: tests/test_service_recovery.py#test_crash_barriers_consumed_work_never_replays
        status: pass
      - kind: integration
        ref: tests/test_service_recovery.py#test_recovery_resumes_only_saved_never_dispatched_before_deadline
        status: pass
      - kind: integration
        ref: tests/test_service_recovery.py#test_terminal_risk_keeps_supervisor_for_next_day_fresh_recovery
        status: pass
    human_judgment: false
duration: 30min
completed: 2026-10-04
status: complete
---

# Phase 15 Plan 10: Scheduling and Recovery Runtime Summary

**Exact-date KST scheduling and independent observer obligations now drive a recovery-first service with spawned single-shot providers and an overnight idle supervisor.**

## Performance

- **Duration:** 30 minutes from the first recorded RED gate; initial context loading was not separately timed.
- **First recorded RED:** 2026-10-04T10:41:14Z.
- **Completed:** 2026-10-04T11:12:00Z.
- **Tasks:** 2/2.
- **Source/test files:** 5, including 4 new files.

## Accomplishments

- `ServiceSchedule.tick` is a pure aware-KST reducer. PREP is read-only at 08:50; risk starts at the later of 09:00 and the confirmed opening, coalesces to one current minute, and retains a durable processed slot. DAILY has priority over new risk reservation at 09:10 and requires strict `<09:20` admission. Delayed 10:00 opening cannot move the daily deadline. New POST retains the absolute 15:20 limit through the existing concrete authority, and the risk session terminalizes at 15:30. Old dates never backfill.
- `derive_expectations`, `OwnerLoginProbe`, `ExpectationProducer` and `ExpectationHistoryReader` publish/read append-only `OBSERVER_DERIVED` facts from protected registration, bounded attributable GUI evidence, exact-date reviewed session and accepted/applied controls. Disabled, logout, holiday and daily PAUSE suppress appropriate obligations; KILL retains reconciliation expectations. UNKNOWN sources emit source-health evidence. Current samples after a due interval never invent its earlier authority; independently saved dated obligations survive midnight and runtime absence.
- `ServiceRuntime.start/recover/tick/stop/run` bind actual `ServiceLeader`, `ControlStore`, `ServiceComposition` and `BoundedAccountWork`. Every start and new eligible date performs fresh exclusive recovery before work. Restrictive controls apply even when recovery blocks. First inputs/universe and consumed dispatches are committed before spawning. Recovery resumes only saved NEVER_DISPATCHED inputs before the original deadline; consumed, suppressed, uncertain and previous-date work cannot replay.
- Provider children use the `spawn` start method, provider-only typed `ProviderSettings`, exact frozen envelopes and a one-row operational admission facade. They receive no account connection, broker, lease or leader. Existing `ProviderDispatchAdmission` and `TransportEntryAck` recheck date/session/controls at actual transport entry, durably consume suppression without a call, then release the shared flock before the 90-second response wait. Parent polling uses fresh account authority for completion. Timeouts and stop preserve UNKNOWN consumption; signal completion after 09:20 remains possible without admitting a new call.
- Daily failure leaves independently due risk/reconciliation work running. Shutdown reserves a bounded 30-second budget without clearing controls/freezes. At 15:30 only risk/watch terminalizes; the leader remains IDLE across the night. UNKNOWN/holiday on a new date cannot reuse yesterday's authority, while refreshed positive exact-date evidence permits fresh recovery.

## Task Commits

1. **Task 1 RED:** `991f5ce` — `test(15-10): specify exact-date schedules and independent obligations` (13 expected missing-module failures before implementation).
2. **Task 1 GREEN:** `179c204` — `feat(15-10): derive exact-date schedules and independent saved obligations` (85 focused tests passed).
3. **Task 2 RED:** `1cd9edc` — `test(15-10): require recovery-first runtime and spawned single-shot handoffs` (8 expected missing-module failures).
4. **Task 2 GREEN:** `16bf161` — `feat(15-10): orchestrate recovery-first runtime and isolated provider children` (156 relevant tests passed).
5. **Lifecycle hardening:** `3c2d2da` — `fix(15-10): retain idle leadership and recover each exact trading date` (158 relevant tests passed).
6. **Named observer acceptance:** `541298f` — `test(15-10): prove independent named midnight and absent-worker obligations` (22 schedule tests passed, including one additional midnight case).

All commits used ordinary hooks on the authorized sequential main checkout. No worktree, reset, stash, deletion or external mutation was performed.

## Verification

- Final combined relevant suite: **158 passed in 15.17s** across recovery, schedule, session, service store and service authority tests.
- Final added named observer case: **22 schedule tests passed in 0.89s**. Across these final runs, **159 distinct tests** were covered; **40 tests** live in the two new files.
- Real spawned-child tests cover startup-to-entry cutoff, midnight, PAUSE and KILL: zero actual fake HTTP entries plus durable SUPPRESSED_NO_CALL and consumed unavailable output. Entry-first evidence stays IN_FLIGHT while a held response permits risk reconciliation and durable KILL acceptance; later completion finalizes without replay. Process termination records DISPATCHED_UNKNOWN and cannot create a second call.
- Input/claim/release/child-start crash barriers preserve immutable inputs and consumption. Before-deadline recovery reuses saved bytes; after-deadline recovery expires or preserves unknown work. The existing authority suite supplies concrete final POST/control/freeze regressions; this plan does not claim an installed service placed an order.
- Source compilation and `git diff --check` passed. Stub scan found no TODO/FIXME/placeholder preventing this plan's contracts. No untracked generated files or tracked deletions remained.
- Every check used temporary journals and injected offline collaborators. No packages, download, KIS/paid LLM/Discord query, production DB access/migration, actual approval, launchctl or installation occurred.

## Runtime Contracts for Plan 15-13

- Construct `ServiceRuntime` with exact registered settings/journal/control owners, concrete `BoundedAccountWork`, `ServiceComposition`, `MarketCyclePolicy`, a typed `DailyInputSource.collect(day, held_tickers)` and `ProviderChildFactory(ProviderSettings(...))`. The provider settings must contain only provider credentials/options. Use top-level pickleable session/clock/transport objects for spawn; local closures cannot be child inputs.
- Bind `AccountTradingBinding` with actual account broker construction, current timestamped quote reading, typed `ExecutionConfig` (BUY threshold at least 0.8), `RiskConfig`, `DailyLossState`, and durable cycle audit. Its daily/risk paths call the shipped execution/risk functions and demand concrete `KISBroker`, committed order audit and same-registration `SubmissionAuthority`. Production additionally requires `OwnedActivationCheck`; an arbitrary Boolean or wrapper cannot authorize transport.
- Pass the runtime's **current** exact `OwnedActivationCheck` as `activation_check`. Startup and next-date recovery re-read owned evidence and retain initial conservative freeze denial. The account lease must belong to the registered primary audit path; the concrete final authority independently checks that binding. Account work stays on the main thread and retains the shipped 45-second ceiling/cleanup and configured POST allowance.
- Bind installed observer `OwnerLoginProbe` separately to the bounded explicit macOS GUI registration query. `ExpectationProducer` requires `settings`, explicit protected `config_path`, injected login probe, `ControlReader`, narrow `ExpectationWriter` and aware clock. Call `publish` before health consumption on every scan/rollover; it creates no trading jobs or authority. `ExpectationHistoryReader` is query-only and raises on unavailable/corrupt/unbounded history.
- The explicit temporary `OfflineActivationAuthority` harness may omit trading bindings and exercise reconciliation-only behavior. These tests prove risk **reconciliation** progress, not a simulated SELL disguised as production protection. The installed root must provide the concrete trading binding; its end-to-end SELL/BUY wiring is subsequent Plan 15-13/15-14 verification.
- Keep the service supervisor alive while IDLE. `stop`/SIGTERM closes leadership; a successful 15:30 process exit must not substitute for next-day scheduling under `KeepAlive SuccessfulExit=false`.

## Decisions Made

Persist provenance rather than reconstructing yesterday's state from a current sample. Treat timer events as hints, consumed provider rows as irreversible, and account leases as fresh short-lived capabilities. Keep the persistent supervisor separate from a terminal daily risk session.

## Deviations from Plan

**1. [Rule 2 - Missing Critical] Allow independent UNKNOWN evidence when a trading source is missing.**

- **Found during:** Task 1.
- **Issue:** `ServiceJournal.connection` revalidated enabled source existence, preventing the independent observer from recording a missing session as UNKNOWN.
- **Fix:** Parent approved narrow additional ownership of `trading_bot/service_store.py`. `ExpectationWriter` internally uses a disabled evidence-only registration with the same protected paths/scopes/schema. It exposes no initialize, migration, job, leader or trading methods. Runtime/leader enabled-source validation remains strict. The history reader applies the same evidence-only topology distinction.
- **Verification:** Missing calendar and malformed control sources, no false missed obligations, and the existing service store suite passed.
- **Commit:** `179c204`.

**2. [Rule 1 - Bug] Keep the service supervisor alive after the risk session ends.**

- **Found during:** Task 2 closeout.
- **Issue:** Closing the leader at 15:30 would stop next-day operation under the planned launchd successful-exit rule.
- **Fix:** Parent approved the in-scope lifecycle correction: durable risk terminalization, IDLE leadership, and current exact-date activation/session/control/account recovery before new work. Explicit stop retains bounded closure.
- **Verification:** Overnight progression and UNKNOWN/holiday-to-positive refresh tests passed; prior job identities remain terminal.
- **Commit:** `3c2d2da`.

## Issues Encountered

Initial spawn fixtures used a local session class and were not pickleable; moving the credential-free session fixture to module scope exercised actual spawn. A forced test child termination poisoned its isolated multiprocessing.Event waiter, so test cleanup stopped reusing that event. Both issues were confined to offline fixtures, with no runtime guard relaxation.

## TDD Gate Compliance

Both tasks have an expected failing RED commit followed by a verified GREEN commit. Additional lifecycle and named-observer tests were committed after relevant verification.

## User Setup Required

No external setup was performed. Both actual 09-08 approvals remain absent; the existing 000660 uncertainty freeze remains intact. Actual Codex 0.144.6 single-shot behavior remains unverified and fails closed. No real-money promotion or installed macOS behavior is claimed.

## Next Phase Readiness

Ready for Plan 15-11 saved health/independent alerts, followed by Plan 15-13 actual CLI/observer binding and Plan 15-14 integrated proof. FUT-04/AUTO-01/AUTO-02 remain pending until the whole-phase verifier. Full wave regression is owned by the parent.

## Self-Check: PASSED

All five source/test files exist. Commits `991f5ce`, `179c204`, `1cd9edc`, `16bf161`, `3c2d2da` and `541298f` exist in preserved Git history. Relevant verification passed; no unexpected tracked deletion or generated untracked file remained.
