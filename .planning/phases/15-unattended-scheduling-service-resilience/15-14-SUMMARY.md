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
  created: [tests/test_service_dry_run.py, tests/test_service_acceptance.py, trading_bot/service_collection.py]
  modified: [trading_bot/service_cli.py, trading_bot/service_runtime.py, trading_bot/service_activation.py, trading_bot/service_schedule.py, trading_bot/web_evidence.py, trading_bot/alert_detector.py, tests/test_service_cli.py, tests/test_service_recovery.py, tests/test_service_health.py, tests/test_service_launchd.py, tests/capability_probe.py, tests/test_web_capabilities.py, docs/operator-runbook.md, tests/test_operator_runbook.py]
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
- Independent-verification correction implementation: 29m33s from first corrective RED (`e7d89bb`) through `cc57bd5`, followed by a quota interruption and resumed validation/observer repair. The interruption is not counted as active execution. Corrections changed 13 source/test/runbook files; no plan/phase counter or requirement completion was advanced during corrections.

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
- Initial plan whole suite: `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q`: **1874 passed in 468.61s (7m48s)**. This predates the independent audit and corrections below.
- That initial suite ran at `9b49867aa5b948da7c99bbf925d79b123194d247` with runbook/tests pending commit; `6b4a24c1b48432d532a300f6cf049cd82573eb14` preserved those identical tested bytes. The final corrected implementation tree is recorded below.
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

No dependency/schema changes or unrelated warning fixes. The parent explicitly assigned the bounded spawn collector and additional observer repair during independent-verification corrections. Necessary O_RDWR source descriptor pinning in the existing reader is narrowly represented by the probe and backed by independent FD-write rejection, query-only SQL and byte hashes.

## Independent Verification Corrections

Canonical `15-VERIFICATION.md` at `d7460e5` remains the initial independent audit; it was not modified. Parent-assigned G1–G5 were handled as correctness deviations under Rules 1/2 with RED tests and atomic normal-hook commits. Requirement completion remains empty; fresh whole-phase verification belongs to the parent.

- **G1 — same first snapshot:** `_daily` obtains an exact same-account snapshot through BoundedAccountWork immediately before first construction and releases account ownership before collection. Production collection uses that captured snapshot consistently for held membership and position context. Recovery reads saved universe/provenance/canonical envelopes unchanged. `test_first_daily_collect_captures_fresh_membership_outside_account_ownership` and actual production-root collection tests distinguish recovery holdings, first capture and later parent holdings.
- **G2 — actual collection fairness:** picklable `ProductionInputSource` replaces the production local-class binder. Screen/context/news run in a spawned child with collection-only policy, public prompt identity and bounded mock quote configuration; no account number, order adapter, leader/primary FD, submission authority, LLM credentials or production store paths cross this boundary. No callbacks or abandoned threads mutate the parent. A durable INPUT_COLLECTION_STARTED marker precedes spawning; completed immutable inputs survive recovery, while uncertain incomplete predecessor work becomes UNKNOWN with its original snapshot identity and is never silently recollected.
- Collection has a **90-second monotonic bound**, 09:20/date/stop bounds, 4,096-target and 8 MiB result bounds. Full-market collection that exceeds a bound deliberately fails closed rather than extending eligibility. Parent risk work, accepted PAUSE and heartbeats progress during actual screen, context and news waits with both ownership domains free. The real binder is pickle-tested; child negative controls install before target imports, deny Settings/dotenv/provider/broker/SQLite/network constructors in offline adapters, and inspect inherited FDs. Five additional crash/expiry cases cover cutoff, monotonic timeout, stop, child crash and pre-spawn crash; processes are joined/terminated, unique temporary output is removed, and successors never recollect.
- **G3 — observation age:** `ObservedSafetyReader` uses the supplied time as observation start and its actual clock after bounded reads as evaluation end. Validation requires `observed_at <= start <= evaluated < expires_at` with at most a ten-second TTL. Advancing microseconds no longer falsely reject fresh production-root evidence; an eleven-second source read and UNKNOWN evidence remain rejected. Source timestamps are not backdated.
- **G4 — exact determinate nonterminal truth:** matching OPEN/PARTIAL/NO_FILL observations with coherent subject, quantities and monotonic filled quantity reconcile account uncertainty sufficiently for independently healthy held protection. They retain affected ticker/order suppression and the original 000660 freeze. Actual production AccountTradingBinding risk work is exercised; missing, UNKNOWN, duplicate, quantity-contradictory and wrong-subject truth remains globally closed. Freeze release still requires exact same-subject terminal proof.
- **G5 — positive progress:** service health projects saved BLOCKED/FAILED/UNKNOWN and unsuccessful account-busy/reserved ticks as attributed unavailable readiness. Recent heartbeat or older success cannot overwrite a newer failed tick. AlertDetector retains the existing WORKER_STALLED incident family; recovery requires actual successful saved progress. Runtime → saved reader → detector → AlertStore regression verifies failure retention, attributed success recovery and renewed failed/LeaseBusy ticks retaining the incident.
- **Additional full-regression defect — future control provenance:** the first corrected full run exposed two launchd tests mixing real setup time with a frozen observer clock. `ExpectationProducer.publish` had already assigned a rejected future timestamp, then raised a model ValidationError instead of emitting UNKNOWN. It now commits candidate control and timestamp only after validation; owner timestamps/DB bytes remain untouched and CONTROL_UNKNOWN is attributed to the real source. The two fixtures use explicit setup clocks. A genuine future-owner-control regression verifies UNKNOWN publication plus live CRITICAL outbox/reminders and the unchanged original 000660 incident.

Corrective commits:

| Commit | Verified unit |
|---|---|
| `e7d89bb` | RED fresh snapshot, advancing clock, nonterminal account truth and failed readiness |
| `fe5cc88` | GREEN production safety, determinate truth and attributed health, plus five negative broker cases |
| `20fae7f` | RED actual screen/context/news spawn binder fairness |
| `663be1f` | GREEN first-snapshot collection and bounded authority-free spawn integration |
| `cc57bd5` | Collection expiry/crash/recovery, child FD/capability checks, unsuccessful-progress regression and runbook |
| `45c0204` | RED future-control observer failure and deterministic launchd setup clocks |
| `c5ad0d1` | GREEN validated control provenance and UNKNOWN/outbox liveness |

Corrective verification:

- Final pre-resume focused service/activation/health/observer/acceptance/dry-run/capability/runbook matrix: **174 passed in 57.52s**. Actual collector child checks passed for screen/context/news (**3 in 4.61s**); expiry/crash matrix passed (**5 in 5.73s**).
- First corrected full run at `cc57bd55608489cab571f30f2987e1de9a0bff26`, session 11439: **1891 passed, 2 failed in 484.90s (8m04s)**. Failures were `test_narrow_observer_factory_never_constructs_general_service_or_trading` and `test_observer_factory_survives_missing_active_trading_sources`, both the future-control model-construction defect described above. This result is not represented as a pass.
- Future-control RED: **1 expected failure** at the actual `publish()` model boundary. After repair, `tests/test_service_launchd.py tests/test_service_schedule.py tests/test_service_health.py tests/test_alert_observer.py tests/test_service_acceptance.py tests/test_web_capabilities.py`: **99 passed in 38.45s**.
- **Final whole suite:** `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q`, session 17537: **1894 passed in 487.94s (0:08:07)** at tested implementation SHA **`c5ad0d1f16aec666b38d85e29ff58cf59bf8fd4e`**. The failure repair justified this rerun; no redundant successful full run was performed. No source/test/runbook edits followed the pass; only this planning summary changed.
- `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m compileall -q trading_bot tests` and `git diff --check` passed. All account/source/transport/observer fixtures stayed injected, temporary and offline; all seven capability families remain covered.

Additional source grounding: `service_runtime.py:_daily/_load_saved_inputs/_poll_collection`, `service_collection.py:ProductionInputSource/collection_child`, `service_cli.py:_build_production_runtime/observe_safety/reconcile`, `service_activation.py:ObservedSafetyReader/_validate_acceptance`, `web_evidence.py` successful event selection, `alert_detector.py` service recovery, and `service_schedule.py:ExpectationProducer.publish` are the executed correction paths.

## Threat Flags

| Flag | File | Description |
|---|---|---|
| threat_flag: process/file boundary | `trading_bot/service_collection.py` | New bounded spawn IPC carries snapshot/public prompt/collection policy and mock quote credentials only. Fixed mock quote origin, in-memory token, no order/LLM/account/leader authority, bounded atomic JSON and unique temporary output constrain the boundary; actual pickle, constructor and inherited-FD negative tests exercise it. No schema or externally callable endpoint was added. |

## Known Stubs

None blocking. Offline config source documents deliberately contain SYNTHETIC/OFFLINE_ONLY markers and are not valid acceptance receipts or production credentials. This is the planned capability-free fixture boundary. The historical runbook word `placeholder` describes UNKNOWN display semantics, not a newly unwired feature.

## Issues Encountered

New hard-crash successor tests initially reused helper snapshot IDs across processes; successor snapshots now use fresh IDs while evaluation/input identities remain immutable. Exact EXPIRED_NEVER_DISPATCHED/PARTIAL and bounded warning-versus-CRITICAL reminder assertions were grounded in the existing owner contracts. The later independent audit identified G1–G5, and the corrected full regression exposed future-control provenance handling; their repairs and failed/passed evidence are recorded above. A quota interruption preserved all saved commits; validation resumed without reverting or restarting implementation. Authentication gates: none.

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

Created proof files, the collection worker and corrected owner modules exist. Initial task commits and all seven corrective commits listed above exist in git history. Final focused and 1894-test whole-suite evidence passed at `c5ad0d1`; the earlier 1891-pass/two-failure run remains explicitly recorded. No unexpected deletions or generated untracked artifacts were found; phase tracking and the canonical verification report were left to the parent.
