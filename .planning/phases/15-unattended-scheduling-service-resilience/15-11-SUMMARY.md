---
phase: 15-unattended-scheduling-service-resilience
plan: "11"
subsystem: monitoring
tags: [sqlite, read-only, independent-observer, source-partitions, alerts]
requires:
  - phase: 15-03
    provides: Owned service journal and narrow expectation writer
  - phase: 15-05
    provides: Installation-global control evidence and read facade
  - phase: 15-10
    provides: Independently dated expectations and persistent service lifecycle
provides:
  - Pure exact service/control schema capabilities and saved read-only health DTOs
  - Independent expectation publication before each bounded alert scan
  - Source outage isolation preserving outbox, ACK and CRITICAL reminders
affects: [15-12, 15-13, 15-14]
tech-stack:
  added: []
  patterns: [mode=ro/query_only reads, positive-source recovery, retained shared cursor on incomplete batch]
key-files:
  created: [tests/test_service_health.py]
  modified: [trading_bot/evidence_contracts.py, trading_bot/web_config.py, trading_bot/web_models.py, trading_bot/web_evidence.py, trading_bot/alert_config.py, trading_bot/alert_detector.py, trading_bot/alert_observer.py, tests/test_alert_observer.py]
key-decisions:
  - "Saved obligation provenance and runtime progress are separate; polling never renews source freshness."
  - "Failed source partitions retain the shared cursor and existing incidents while independently owned delivery continues."
  - "Only new attributable source evidence recovers availability; observer storage failure or ownership loss still halts sends."
requirements-completed: []
coverage:
  - id: D1
    description: Exact owner/schema saved service/control health without writer imports
    verification:
      - kind: integration
        ref: tests/test_service_health.py#test_owner_migrated_pure_schema_and_query_only_bytes
        status: pass
    human_judgment: false
  - id: D2
    description: Independent observer detects absent runtime and exact-date rollover with only expectation writes
    verification:
      - kind: integration
        ref: tests/test_service_health.py#test_independent_observer_publishes_exact_date_before_first_runtime_tick
        status: pass
    human_judgment: false
  - id: D3
    description: Persistent source failure preserves outbox/reminders and prevents false recovery
    verification:
      - kind: integration
        ref: tests/test_alert_observer.py#test_persistent_service_control_failure_keeps_owned_delivery_reminders_and_ack
        status: pass
      - kind: integration
        ref: tests/test_alert_observer.py#test_watch_survives_repeated_reader_exception_and_due_reminder
        status: pass
    human_judgment: false
duration: 27min
completed: 2026-10-04
status: complete
---

# Phase 15 Plan 11: Independent Saved Service Health Summary

**Pure service/control health projections and independently owned alerts preserve CRITICAL delivery during persistent source outages without inventing runtime progress or recovery.**

## Accomplishments

- Added exact pure version-one service/control table/column maps, including expectation provenance, expectation health and provider admission evidence. Read paths validate owner/version/schema and protected operational source permissions; fresh-import proof rejects service/control writers, runtime and composition imports.
- Registered `service` and `control` evidence owners. `ControlResourceDescriptor` fixes an installation-global mock scope and separate owner-checked request authority; `WebSettings.control_resource` defaults to disabled. Existing resource/report defaults remain compatible.
- Added immutable `ServiceHealthDTO`, `ControlStateDTO`, compatible WorkerDTO defaults, `OverviewDTO.service_health`/`controls` and `AlertSourceBatch.service_health`. `OperatorEvidenceService.service_health` consumes independently saved exact-date obligations without trading jobs/heartbeats and preserves config/login/session/control provenance, due/deadline and original observation time.
- Added saved control state, pending requests, revisions and scope identity validation. Service health distinguishes not expected, unknown, missed schedule, stalled risk progress, recovery blocked and manual attention. Daily pause suppresses daily obligations while active-session risk observation remains expected; terminal risk is not expected overnight. Heartbeat freshness is 120 seconds; missing risk progress cannot become healthy merely from a fresh leader heartbeat.
- `ObserverSettings.expectation_service_config_path` explicitly reserves protected registration authority, requiring registered service/control resources. `AlertObserver(..., expectation_producer=...)` publishes through the injected narrow producer before each scan/date rollover. The web reader never receives this writer. Plan 15-13 owns installed OS login/protected configuration composition.
- Replaced source-failure abort-before-delivery with `ScanSourceOutcome` partitions. Failed/unknown sources cannot supply recovery or advance the existing shared cursor. Healthy observer-owned pending delivery, acknowledgements, 30-minute CRITICAL reminders and watch progress continue. Own-store failure, failed checkpoint persistence and lost observer ownership remain fail-closed before sending.
- Existing outbox claim/finalize, receipt ownership, UNKNOWN terminal delivery and deduplication remain the sole delivery mechanism. Saved source outage events preserve their first observation; recovery requires a new positive attributable source observation. Manual attention uses its append-only occurrence/reset events to avoid projection duplication.
- Saved attempted-execution freshness events provide MARKET_DATA_STALE and explicit FRESHNESS_CHECKED recovery. Saved notification failures/UNKNOWN are shown separately from successful delivery; absence overnight cannot invent stale quote or recovery. Successful read-only PREP events are INFO history only.

## Task Commits

1. Task 1 RED — `f80de93`: specify pure saved service and control health.
2. Task 1 GREEN — `52612db`: project independently saved service and global control health.
3. Task 2 RED — `158d0d4`: require resilient independent alert source partitions.
4. Task 2 GREEN — `25131d0`: keep independent alert delivery progressing through source outages.

## Verification

- Task 1 focused suite: **46 passed in 9.34s** (`test_service_health`, `test_evidence_contracts`, `test_web_evidence`); final small source-status ordering adjustment: **14 passed in 0.78s**.
- Final combined focused suite: **107 passed in 11.34s** (`tests/test_service_health.py`, `tests/test_alert_observer.py`, `tests/test_alert_store.py`, `tests/test_alert_detector.py`, `tests/test_evidence_contracts.py`, `tests/test_web_evidence.py`).
- Actual owner-migrated temporary schemas match exact pure declarations. Query-only source bytes remain unchanged. Independent producer writes change only `service_expectations` and `service_expectation_health`; every other service table and all control source bytes remain unchanged.
- Offline tests cover pre-first-tick absent work, exact-date midnight rollover, holiday/paused/disabled/logged-out negatives, missing registration/session/login/control UNKNOWN, manual attention, stale heartbeat/risk progress, same-subject positive progress recovery, real watch continuation during repeated reader exceptions, persistent service/control failures with queued CRITICAL delivery and exact 1800-second reminders, ACK, one positive availability recovery, delivery UNKNOWN/no resend and own-store/lease failure.
- `git diff --check` passed. No dependencies, network calls, real Discord webhook, broker/provider activity, production DB reads/migrations or OS installation were used. No unexpected tracked deletion or generated untracked file remained. Full-wave regression is owned by the parent orchestrator.

## Decisions Made

Keep query time distinct from source observation. Earlier positive obligation history may prove the due interval; later UNKNOWN source evidence cannot fabricate current health or recovery. Retain the shared source cursor on incomplete batches and rely on existing durable deduplication. Never let trading/source availability decide the lifetime of a healthy independent observer.

## Deviations from Plan

None requiring additional file ownership or architecture. Task 2 also updated its declared upstream `web_evidence.py` reader to preserve projection failure status in source batches and register attempted-execution freshness/candidate facts; this is necessary for trustworthy partitioning and the planned four health classes. Existing observer tests expecting source outages to stop all sends were updated to the specified resilient behavior. Fixture API/time mistakes were corrected without relaxing production checks.

## TDD Gate Compliance

Each task has an expected failing `test(15-11)` RED commit followed by a verified `feat(15-11)` GREEN commit. Task 1 produced 11 expected missing-owner/projection failures; Task 2 produced five expected source partition/injection failures.

## User Setup Required

No manual acceptance is claimed. Both actual 09-08 approvals remain absent; ticker 000660 remains frozen. Actual Codex single-shot capability is unverified and remains closed. No real-money promotion, LaunchAgent activation or launchctl action occurred. Total Mac sleep/power loss can only appear as elapsed source gaps after resumption; an observer on that same stopped Mac cannot notify during the outage.

## Next Phase Readiness

Plan 15-12 may use `WebSettings.control_resource` and the immutable fixed `ControlResourceDescriptor` for request authority, independently of arbitrary evidence selection. Plan 15-13 must inject the registered `ExpectationProducer` and bounded owner-GUI login probe into the independent observer; construction does not implicitly migrate service/control stores or instantiate trading execution. Plan 15-14 must verify full installed composition and process behavior. AUTO-01/AUTO-02 remain pending whole-phase verification.

## Self-Check: PASSED

All nine declared source/test files exist. Commits `f80de93`, `52612db`, `158d0d4` and `25131d0` exist. Both tasks passed relevant offline verification. No unfinished stub prevents the plan goal; external activation remains deliberately gated.
