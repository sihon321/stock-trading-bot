---
phase: 15-unattended-scheduling-service-resilience
plan: "14"
subsystem: testing
tags: [pytest, sqlite, spawn, capability-tripwires, recovery, kst]
requires:
  - phase: 15-09
    provides: Bounded fresh account work and stable evaluation-derived order intent
  - phase: 15-10
    provides: ServiceRuntime scheduling, consumed dispatch recovery and independent obligations
  - phase: 15-11
    provides: Saved service health and source-partition-safe observer delivery
  - phase: 15-12
    provides: Fixed read/request control capabilities
  - phase: 15-13
    provides: Protected CLI, mock composition and independent GUI supervision
provides:
  - Actual temporary service scheduling and consumed-dispatch recovery through the dry-run CLI
  - Cross-owner hard-crash, entry/control, partial-universe, single-intent and observer failure proofs
  - Seven fresh-interpreter service capability families with source hashes and constructor/FD/process negative controls
  - Korean mechanically checked pending activation checklist and final full regression evidence
affects: [phase-verification, operator-activation, phase-16]
tech-stack:
  added: []
  patterns: [temporary offline runtime composition, pre-import capability guards, request-only SQL authorizer, durable producer-linked assertions]
key-files:
  created: [tests/test_service_dry_run.py, tests/test_service_acceptance.py]
  modified: [trading_bot/service_cli.py, tests/capability_probe.py, tests/test_web_capabilities.py, docs/operator-runbook.md, tests/test_operator_runbook.py]
key-decisions:
  - "Dry-run rebuilds every runtime path below an owned temporary root, uses frozen canonical inputs and interrupts after committed dispatch before any provider construction."
  - "Offline implementation and regression completion do not complete either 09-08 approval, actual GUI/private-device acceptance or unattended activation."
  - "Existing control-reader O_RDWR descriptor pinning is allowed only on exact registered sources, with FD write/pwrite/ftruncate and source SQL mutations separately denied."
requirements-completed: []
coverage:
  - id: D1
    description: Actual offline service scheduling and successor recovery preserve source bytes and consumed work
    requirement: AUTO-01
    verification:
      - kind: integration
        ref: tests/test_service_dry_run.py#test_dry_run_runs_owned_runtime_recovery_and_preserves_registered_sources
        status: pass
    human_judgment: false
  - id: D2
    description: Hard crash, pending controls, entry-first fairness, partial universe and unique order intent proofs
    requirement: AUTO-01
    verification:
      - kind: integration
        ref: tests/test_service_acceptance.py#test_hard_process_crash_recovers_stable_primary_identity_without_replay
        status: pass
      - kind: integration
        ref: tests/test_service_acceptance.py#test_actual_spawn_entry_rechecks_pending_acceptance_before_application
        status: pass
      - kind: integration
        ref: tests/test_service_acceptance.py#test_evaluation_intent_at_most_one_post_preserves_unknown_000660_freeze
        status: pass
    human_judgment: false
  - id: D3
    description: Seven fresh-interpreter saved-read/request/disabled/offline command families preserve capability separation
    requirement: AUTO-02
    verification:
      - kind: integration
        ref: tests/test_web_capabilities.py#test_fresh_service_read_request_setup_render_dry_run_capabilities
        status: pass
    human_judgment: false
  - id: D4
    description: Pending activation checklist matches callable commands and preserves external gates
    requirement: FUT-04
    verification:
      - kind: unit
        ref: tests/test_operator_runbook.py#test_phase15_external_acceptance_checklist_is_pending_and_never_forged
        status: pass
    human_judgment: false
  - id: D5
    description: Actual owner GUI lifecycle, Korean desktop/320px controls, private phone HTTPS and both broker-facing approvals
    verification: []
    human_judgment: true
    rationale: Temporary stores, injected transports and offline process tests cannot prove owner devices, installed agents or authenticated elapsed-day broker acceptance; these remain pending and block activation.
duration: 24min
completed: 2026-10-05
status: complete
---

# Phase 15 Plan 14: Offline Acceptance and Activation Boundaries Summary

**Actual temporary service scheduling/recovery and spawned adversarial proofs preserve consumed work, request restrictions and source bytes while activation remains gated.**

## Performance

- Duration: approximately 24 minutes measured from first RED commit; initial context reading precedes this measurement.
- Started: 2026-10-04T17:01:30Z (2026-10-05T02:01:30+09:00), first RED.
- Completed: 2026-10-04T17:25:03Z (2026-10-05T02:25:03+09:00), final full-suite result.
- Tasks: 2; implementation/test/document files: 7.

## Accomplishments

- Dry-run retains `replay-result.json` and adds `service-result.json` plus dedicated temporary owner stores under `service-proof/`. It executes actual ServiceSchedule, ServiceRuntime, BoundedAccountWork, owner migrators, canonical input/dispatch commits, successor recovery and terminal risk handling. The frozen first scenario supplies canonical inputs; a deliberate DISPATCH_COMMITTED interruption prevents provider construction. Recovered dispatch is DISPATCHED_UNKNOWN, job IDs remain stable, leases are released and the 15:30 runtime is IDLE. Sources remain byte-identical; no typed acceptance receipt, provider subprocess or broker is produced.
- Seventeen acceptance cases use actual runtime/store/admission collaborators. Five spawned worker hard exits cover INPUT_COMMITTED, DISPATCH_COMMITTED, ACCOUNT_RELEASED, CHILD_STARTED and RESPONSE_BEFORE_FINALIZATION. Recovery preserves evaluation IDs and canonical hashes and produces exact EXPIRED_NEVER_DISPATCHED or DISPATCHED_UNKNOWN outcomes, with at most one entered mock transport. Normal/holiday/UNKNOWN/delayed sessions use fixed 08:50/09:00/09:10/09:20/15:20/15:30 boundaries.
- Spawned pre-entry PAUSE/KILL/cutoff checks reject transport before application, while entry-first IN_FLIGHT releases both account ownership and admission exclusion. Risk reconciliation advances during slow response, accepted KILL persists and older RESUME is REVISION_CONFLICT. Partial first-input persistence retains 000660 in the committed universe across a sleep gap without collecting again. Two determinate/lost-response order cases preserve the original 000660 freeze and stable evaluation-derived intent with one POST/admission.
- Repeated protected service/control read failures leave the original CRITICAL incident active and permit owned outbox/reminders; failed shared-source cursors do not advance. Observer-owned store failure stops further sends. Existing independently supervised midnight/pre-first-tick and own-ownership proofs are reused through the full regression rather than duplicated as new mock-only workflows.
- Fresh-interpreter status, saved health, control-request, disabled run, setup-disabled, render and dry-run probes install guards before target imports and verify source hashes. Dry-run permits necessary reducer imports while denying trading Settings, dotenv and KIS/LLM constructors, network, process/launchctl/install, production SQL and source writes. Control requests have a SQL authorizer limited to request/audit inserts; applications/admissions remain untouched. Negative controls prove constructor, source-FD write, process, SDK and dotenv rejection.
- Korean runbook documents actual commands/reducers, deadlines, request-versus-application semantics, entry-first POST uncertainty, 3/600s restart accounting, own-store failure and same-Mac total-outage limitations. A mechanically checked table keeps all real account/device/observer approvals pending, 000660 frozen and Phase 16 real blocked.

## Task Commits

1. Task 1 RED: `70e23d8` — require offline scheduling/recovery result (one expected missing `service-result.json` failure).
2. Task 1 GREEN: `9b49867` — actual temporary service runtime and integrated capability/adversarial proofs.
3. Task 2: `6b4a24c` — final Korean activation checklist and callable-command/document contract tests.

Normal repository commit hooks were used. RED precedes GREEN; no tracked files were deleted.

## Verification

- `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_service_acceptance.py tests/test_service_dry_run.py tests/test_web_capabilities.py`: **21 passed in 33.81s**.
- `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_operator_runbook.py tests/test_service_cli.py`: **25 passed in 1.71s**.
- Required prior regression: `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_market_cycle.py tests/test_mutation_lease.py tests/test_portfolio_store.py tests/test_phase11_cli.py tests/test_intraday.py tests/test_evidence_contracts.py tests/test_alert_observer.py tests/test_web_capabilities.py`: **150 passed in 28.64s**.
- Final whole suite, run once after final source/test/document changes: `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q`: **1874 passed in 468.61s (7m48s)**.
- Full suite ran at `9b49867aa5b948da7c99bbf925d79b123194d247` with only the final runbook and runbook tests pending commit. `6b4a24c1b48432d532a300f6cf049cd82573eb14` commits those identical tested bytes, so it is the final tested implementation/document tree. No source/test/document edits followed the full-suite pass; later commits contain planning metadata only.
- `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m compileall -q trading_bot tests` and `git diff --check` passed.
- All checks used temporary stores, frozen data, injected HTTP/account/notification collaborators and offline processes. No live KIS, paid provider, Discord, production DB read/migration, package install/download, LaunchAgent bootstrap/install or approval capture occurred.

## Source Grounding

- [CLI dry-run composition](../../../trading_bot/service_cli.py): `dry_run` and `offline_service_proof` build fresh temporary topology and retained replay evidence.
- [Runtime](../../../trading_bot/service_runtime.py): `start`, `recover`, `tick`, `_daily`, `_poll_child` and `stop` are the executed scheduling/recovery/dispatch path.
- [Scheduling](../../../trading_bot/service_schedule.py): ServiceSchedule and independently derived obligations remain exact-date and deadline bounded.
- [Submission authority](../../../trading_bot/submission_authority.py): FinalPostEntry and durable admission guard the irreversible transport boundary and same-subject freezes.
- [Capability probe](../../../tests/capability_probe.py): pre-import guards, source SQL/FD restrictions and request-only mutation allowlist.
- [Runbook](../../../docs/operator-runbook.md): Phase 15 final checklist gives the operator the remaining real evidence requirements.

## Decisions Made

Use actual runtime reducers with deliberate capability-free dispatch interruption for the CLI proof, alongside retained frozen replay compatibility. Keep all requirement completion entries empty until independent whole-phase verification; implementation completion does not replace either Phase 9 owner approval or device acceptance.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Connect replay-only dry-run to actual temporary service reducers**
- Found during Task 1: existing dry-run saved only replay results, failing the declared runtime/recovery key link.
- Parent explicitly assigned narrow ownership of the dry-run branch in `trading_bot/service_cli.py`; no other production modules were changed.
- Fix: rebuild all runtime paths below an owned temporary authority, persist frozen canonical inputs, interrupt committed dispatch before provider construction, recover with successor and report stable identities/lease/terminal evidence.
- Verification: new RED/GREEN proof, fresh-interpreter capability negative controls and final 1874-test regression.
- Committed in: `9b49867`.

No architecture/dependency changes or unrelated warning fixes. Necessary O_RDWR source descriptor pinning in the existing reader is narrowly represented by the probe and backed by independent FD-write rejection, query-only SQL and byte hashes.

## Known Stubs

None blocking. Offline config source documents deliberately contain SYNTHETIC/OFFLINE_ONLY markers and are not valid acceptance receipts or production credentials. This is the planned capability-free fixture boundary. The historical runbook word `placeholder` describes UNKNOWN display semantics, not a newly unwired feature.

## Issues Encountered

New hard-crash successor tests initially reused helper snapshot IDs across processes; successor snapshots now use fresh IDs while evaluation/input identities remain immutable. Exact EXPIRED_NEVER_DISPATCHED/PARTIAL and bounded warning-versus-CRITICAL reminder assertions were grounded in the existing owner contracts. No production defect beyond the replay-only dry-run gap was found. Authentication gates: none.

## Remaining External Activation Gates

- Actual **09-08 task 1 and task 2** approvals and their linked owned receipt/current safety proof are absent; no offline artifact grants activation.
- **000660 stays frozen** until same-subject determinate terminal broker evidence. No resubmission or fabricated release is authorized.
- Actual **Codex CLI 0.144.6 single-shot transport is unsupported/closed**. No paid provider acceptance was attempted.
- Actual LaunchAgent installation, owner GUI login/logout/sleep/wake/SIGTERM/removal and independently supervised observer acceptance remain **PENDING**.
- Korean authenticated desktop/320px controls, actual Tailscale/private HTTPS phone mobile-data/certificate/login/session/actor checks remain **PENDING**.
- Same-Mac total outage prevents both service and local observer progress. Phase 16 real-money promotion is **BLOCKED** and separate.

## Next Phase Readiness

All 14 Phase 15 plans now have offline implementation summaries. Ready for independent whole-phase verification using the unchanged final tested tree and full regression result. FUT-04/AUTO-01/AUTO-02 remain unmarked here; real unattended mutation remains gated by the separate external acceptance evidence.

## Self-Check: PASSED

Created proof files and the modified CLI exist. Task commits `70e23d8`, `9b49867` and `6b4a24c` exist in git history. Focused, prior-regression and whole-suite evidence passed; no unexpected deletions or generated untracked artifacts were found.
