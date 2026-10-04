---
phase: 15
slug: unattended-scheduling-service-resilience
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-10-04
---

# Phase 15 — Validation Strategy

> Execution feedback contract. This plan audit covers all 28 tasks in 14 plans/9 waves; it does not mean implementation, tests or operator acceptance have passed. nyquist_compliant records complete planned feedback coverage; wave_0_complete remains false until fixtures/tests actually exist.

## Test Infrastructure

| Property | Value |
|---|---|
| Framework | pytest 8.4.2; existing project infrastructure |
| Config | pyproject.toml |
| Existing quick regression | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_market_cycle.py tests/test_mutation_lease.py tests/test_portfolio_store.py tests/test_phase11_cli.py tests/test_intraday.py tests/test_web_capabilities.py tests/test_alert_observer.py` |
| Full suite | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` |
| Observed quick runtime | Research baseline: 103 passed in 21.90s |
| Target focused feedback | Under 30s; verify during implementation, do not assert an unmeasured future runtime |

## Sampling Rate

- After every implementation task: its focused offline tests and nearest existing regression module.
- After every wave: applicable cross-module regression; the complete suite is mandatory before phase verification. Broaden only when changes or unresolved failures justify it.
- No watch-mode test commands. No broker, paid LLM, Discord delivery, OS installation or production-store mutations from automated checks.
- Fake aware UTC/KST wall clocks, monotonic time, authoritative session fixtures, temporary SQLite stores, fake providers/brokers, deterministic crash barriers and spawn-safe process fixtures.

## Actual Plan / Task Verification Map

All 28 tasks have explicit automated checks. A producing task writes tests before its implementation and verification; no command relies on an uncreated test. Shared fixtures are produced by 15-01-T2 before every later wave. Commands below are literal plan commands; test function names/cases are defined by each task behavior and acceptance contract.

| Task ID | Wave | Requirement | Test/contract name | Automated command | Producer / dependency |
|---|---|---|---|---|---|
| 15-01-T1 | 1 | FUT-04/AUTO-01/AUTO-02 | Publish strict scope, job, dispatch, control and receipt contracts | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_service_contracts.py` | 15-01-T2 + creates/extends tests before GREEN; plans none |
| 15-01-T2 | 1 | FUT-04/AUTO-01/AUTO-02 | Create isolated fixture and process-barrier infrastructure | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_service_contracts.py` | 15-01-T1 + earlier wave dependencies; plans none |
| 15-02-T1 | 2 | AUTO-01 | Implement reviewed exact-date session authority and refresh policy | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_service_sessions.py tests/test_market_cycle.py` | 15-01-T2 + creates/extends tests before GREEN; plans 15-01 |
| 15-02-T2 | 2 | AUTO-01 | Unify intraday phase transitions with session authority | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_service_sessions.py tests/test_market_cycle.py tests/test_intraday.py` | 15-02-T1 + earlier wave dependencies; plans 15-01 |
| 15-03-T1 | 2 | AUTO-01/AUTO-02 | Implement owned service journal, immutable jobs and restart budget | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_service_store.py` | 15-01-T2 + creates/extends tests before GREEN; plans 15-01 |
| 15-03-T2 | 2 | AUTO-01/AUTO-02 | Implement separate leader exclusion and crash attribution | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_service_authority.py tests/test_mutation_lease.py` | 15-03-T1 + earlier wave dependencies; plans 15-01 |
| 15-04-T1 | 2 | AUTO-01 | Add owned dispatch states and conservative legacy migration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_portfolio_store.py` | 15-01-T2 + creates/extends tests before GREEN; plans 15-01 |
| 15-04-T2 | 2 | AUTO-01 | Coordinate pure capability declarations and saved readers | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_evidence_contracts.py tests/test_web_evidence.py tests/test_web_capabilities.py` | 15-04-T1 + earlier wave dependencies; plans 15-01 |
| 15-05-T1 | 2 | AUTO-02 | Implement narrow request journal and shared admission lock protocol | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_service_controls.py -k 'request or revision or persistence or capability'` | 15-01-T2 + creates/extends tests before GREEN; plans 15-01 |
| 15-05-T2 | 2 | AUTO-02 | Apply controls only from the final service with fresh gates | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_service_controls.py` | 15-05-T1 + earlier wave dependencies; plans 15-01 |
| 15-06-T1 | 3 | FUT-04/AUTO-01 | Validate explicit approval receipts against owned evidence | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_service_activation.py` | 15-01-T2 + creates/extends tests before GREEN; plans 15-01,15-02 |
| 15-06-T2 | 3 | FUT-04/AUTO-01 | Compose authenticated KIS mock only after activation | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_service_composition.py tests/test_service_activation.py` | 15-06-T1 + earlier wave dependencies; plans 15-01,15-02 |
| 15-07-T1 | 3 | AUTO-01 | Add stored-envelope one-shot provider boundaries | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_daily_dispatch.py tests/test_llm_provider.py` | 15-01-T2 + creates/extends tests before GREEN; plans 15-02,15-03,15-04,15-05 |
| 15-07-T2 | 3 | AUTO-01 | Wire atomic scoped dispatch and conservative daily recovery | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_daily_dispatch.py tests/test_phase11_cli.py tests/test_portfolio_store.py` | 15-07-T1 + earlier wave dependencies; plans 15-02,15-03,15-04,15-05 |
| 15-08-T1 | 4 | FUT-04/AUTO-01/AUTO-02 | Guard actual broker POST with serialized restrictive acceptance | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_service_controls.py` | 15-01-T2 + creates/extends tests before GREEN; plans 15-02,15-05,15-06,15-07 |
| 15-08-T2 | 4 | FUT-04/AUTO-01/AUTO-02 | Wire all money-moving composition roots and exits to the guard | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_service_authority.py tests/test_kis_broker.py tests/test_exit_manager.py` | 15-08-T1 + earlier wave dependencies; plans 15-02,15-05,15-06,15-07 |
| 15-09-T1 | 5 | AUTO-01/AUTO-02 | Implement one-pass bounded account work and intraday lifecycle | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_service_authority.py tests/test_intraday.py tests/test_mutation_lease.py` | 15-01-T2 + creates/extends tests before GREEN; plans 15-03,15-06,15-07,15-08 |
| 15-09-T2 | 5 | AUTO-01/AUTO-02 | Separate daily reservation/provider/execution into fresh authority sections | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_service_authority.py tests/test_phase11_cli.py tests/test_intraday.py` | 15-09-T1 + earlier wave dependencies; plans 15-03,15-06,15-07,15-08 |
| 15-10-T1 | 6 | FUT-04/AUTO-01/AUTO-02 | Implement pure KST due/deadline reducer with saved expectations | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_service_schedule.py tests/test_service_sessions.py` | 15-01-T2 + creates/extends tests before GREEN; plans 15-02,15-03,15-05,15-06,15-09 |
| 15-10-T2 | 6 | FUT-04/AUTO-01/AUTO-02 | Compose recovery-first service runtime and bounded children | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_service_recovery.py tests/test_service_schedule.py tests/test_service_authority.py` | 15-10-T1 + earlier wave dependencies; plans 15-02,15-03,15-05,15-06,15-09 |
| 15-11-T1 | 7 | AUTO-01/AUTO-02 | Add pure schema contracts and read-only service/control health projections | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_service_health.py tests/test_evidence_contracts.py tests/test_web_evidence.py` | 15-01-T2 + creates/extends tests before GREEN; plans 15-04,15-10 |
| 15-11-T2 | 7 | AUTO-01/AUTO-02 | Feed service health into independently owned alert observation | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_service_health.py tests/test_alert_observer.py tests/test_alert_store.py` | 15-11-T1 + earlier wave dependencies; plans 15-04,15-10 |
| 15-12-T1 | 8 | AUTO-02 | Expose narrow authenticated control-request endpoints | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_web_control_routes.py tests/test_web_alert_routes.py` | 15-01-T2 + creates/extends tests before GREEN; plans 15-05,15-08,15-11 |
| 15-12-T2 | 8 | AUTO-02 | Render responsive Korean controls and saved health affordances | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_web_control_routes.py tests/test_web_ui_contract.py` | 15-12-T1 + earlier wave dependencies; plans 15-05,15-08,15-11 |
| 15-13-T1 | 8 | FUT-04/AUTO-02 | Add explicit CLI requests, offline commands and receipt transport | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_service_cli.py tests/test_service_activation.py` | 15-01-T2 + creates/extends tests before GREEN; plans 15-03,15-05,15-06,15-10,15-11 |
| 15-13-T2 | 8 | FUT-04/AUTO-02 | Render safe login agents and enforce durable launcher admission | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_service_launchd.py tests/test_service_store.py tests/test_service_cli.py` | 15-13-T1 + earlier wave dependencies; plans 15-03,15-05,15-06,15-10,15-11 |
| 15-14-T1 | 9 | FUT-04/AUTO-01/AUTO-02 | Run integrated offline adversarial and capability proofs | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_service_acceptance.py tests/test_service_dry_run.py tests/test_web_capabilities.py` | 15-01-T2 + creates/extends tests before GREEN; plans 15-12,15-13 |
| 15-14-T2 | 9 | FUT-04/AUTO-01/AUTO-02 | Finalize runbook acceptance boundaries and regression proof | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_operator_runbook.py tests/test_service_cli.py` | 15-14-T1 + earlier wave dependencies; plans 15-12,15-13 |

### Named Adversarial Acceptance Cases

| Name to implement | Producing task | Consuming proof | Required assertion |
|---|---|---|---|
| test_crash_after_dispatch_never_replays_provider | 15-07-T1/T2; fixture barriers 15-01-T2 | 15-10-T2, 15-14-T1 | One transport call even after response-before-commit crash; UNKNOWN retained. |
| test_request_acceptance_linearizes_before_later_post | 15-08-T1 | 15-14-T1 | Two-process restrictive-first ordering yields zero POST; already-admitted ordering records one in-flight attempt. |
| test_slow_provider_releases_account_and_risk_progresses | 15-09-T2 | 15-10-T2, 15-14-T1 | No account lease or admission flock across provider response/sleep; due daily/risk progress and accepted kill without overlap. |
| test_final_provider_entry_rechecks_deadline_after_claim_release_startup | 15-07-T1/T2; barriers15-01-T2 | 15-09-T2,15-10-T2,15-14-T1 | At each claim/reconcile/release/child-start/admission-persistence/pre-entry barrier,09:19:59 claim crossing09:20 yields zero transport calls, durable SUPPRESSED_NO_CALL/consumed unavailable and no replay. |
| test_provider_entry_rechecks_date_session_and_accepted_controls | 15-07-T1/T2 | 15-09-T2,15-10-T2,15-14-T1 | Changed date, UNKNOWN/closed session or accepted PAUSE/KILL before entry yields zero calls; pending RESUME grants nothing. |
| test_transport_entry_orders_control_acceptance_and_releases_admission_lock | 15-07-T1/T2 | 15-09-T2,15-10-T2,15-14-T1 | Entry-first is honest IN_FLIGHT; synchronous TransportEntryAck releases bounded lock before slow response, later accepted controls/risk POST proceed, completion after09:20 remains bounded. Unsupported/missing entry ack fails closed. |
| test_provider_admission_suppression_and_crash_never_restore_claim | 15-03-T1,15-07-T1/T2 | 15-10-T2,15-14-T1 | Narrow writer changes only prepared matching operational row; consumed/suppressed/uncertain dispatch stays unavailable after crash/duplicate child, zero or one calls only. |
| test_narrow_expectation_writer_cannot_amend_runtime_or_trading_state | 15-03-T1 | 15-11-T2,15-13-T2,15-14-T1 | Allowed expectation/health appends only; jobs/generations/restarts/heartbeats/control applications/trading evidence unchanged. |
| test_observer_only_midnight_publishes_current_date_absence | 15-10-T1,15-11-T1/T2 | 15-13-T2,15-14-T1 | Enabled protected registration, confirmed continuous GUI login, exact-date reviewed session and control provenance create current-date obligation with zero runtime ticks; missing due job raises one incident. |
| test_trading_crash_before_expectation_still_detects_absent_schedule | 15-10-T1,15-11-T1/T2 | 15-13-T2,15-14-T1 | Trading never creates today rows or is restart-limited; independent producer/observer still detects confirmed due absence with OBSERVER_DERIVED provenance. |
| test_independent_expectations_holiday_pause_disabled_login_unknown | 15-10-T1,15-11-T1/T2 | 15-13-T2,15-14-T1 | Holiday/disabled/logout have no mutation expectation; PAUSE excludes daily and retains eligible risk; unknown date/session/control/login yields source/expectation health without invented miss/recovery. |
| test_source_failure_keeps_pending_critical_delivery_and_reminders_alive | 15-11-T2 | 15-14-T1 | Repeated failed service/control reads do not exit watch; healthy own-store pending CRITICAL delivery and30-minute reminder advance with existing claims/ACK/UNKNOWN semantics and no false recovery. |
| test_source_failure_preserves_checkpoint_and_recovers_only_on_positive_evidence | 15-11-T2 | 15-14-T1 | Failed partition cursor/receipt does not advance; dedupe suppresses repeats, positive source recovery produces exactly one recovery, polling cannot renew source age. |
| test_observer_own_store_or_ownership_failure_stops_delivery | 15-11-T2 | 15-14-T1 | Own-store corruption/write failure or lost ownership yields zero sends; transport failure remains UNKNOWN and never blind replay. |
| test_observer_launch_binds_registration_and_injected_gui_probe | 15-13-T2 | 15-14-T1 | Plist/CLI fixed protected registration path, explicit owner-GUI probe, no broker/provider/live queries; disabled render performs no OS calls. |
| test_service_disabled_registration_has_no_active_callbacks | 15-06-T2 | 15-13-T1,15-14-T1 | service_enabled=false remains disabled even if mock mode/receipt exists; observation never grants activation. |
| test_fourth_restart_is_rejected_before_worker_construction | 15-03-T1, 15-13-T2 | 15-14-T1 | Three committed automatic restarts/600s; fourth denial, manual-attention persists. |
| test_stale_resume_cannot_weaken_kill | 15-05-T2 | 15-08-T1, 15-12-T1, 15-14-T1 | Newer accepted kill dominates queued resume across restart/date. |
| test_saved_health_expectations_distinguish_pause_unknown_and_missed | 15-11-T1/T2 | 15-14-T1 | No false missed/stalled or positive recovery for unknown session/control evidence. |
| test_offline_service_has_zero_external_capabilities | 15-14-T1 | Phase verification | Fresh-interpreter imports/CLI exercise temp topology and leave production sources unchanged. |

## Wave 0 Test / Fixture Producers

Wave 0 denotes test-first needs, not an unlisted executor wave. The canonical files do not yet exist: wave_0_complete remains false. Every consuming implementation depends on its producing task or preceding plan.

| New file / fixture | Producer | Available before |
|---|---|---|
| tests/service_fixtures.py; FakeServiceClock, TempServiceTopology, NoExternalCapabilities, SYNTHETIC approval bundles; claim/reconcile/release/child-start/admission/pre-entry/entry barriers; synchronous fake TransportEntryAck and separate slow-response counter; protected registration/login variants, observer-only midnight, failing-source and healthy CRITICAL outbox/reminder fixtures | 15-01-T2 (wave1) | All wave2–9 tests |
| tests/test_service_contracts.py | 15-01-T1/T2 | Own implementation/verification |
| tests/test_service_sessions.py | 15-02-T1 | 15-02-T2, 15-10-T1 |
| tests/test_service_store.py, tests/test_service_authority.py; narrow ExpectationWriter/ProviderAdmissionWriter allowlist and consumed admission states | 15-03-T1/T2 | 15-08/09/10/13/14 |
| Existing tests/test_portfolio_store.py/test_evidence_contracts.py v3/v4 cases | 15-04-T1/T2 | 15-07/11/14 |
| tests/test_service_controls.py | 15-05-T1/T2 | 15-08/12/14 |
| tests/test_service_activation.py, tests/test_service_composition.py | 15-06-T1/T2 | 15-08/09/10/13/14 |
| tests/test_daily_dispatch.py, existing phase11/provider regression updates | 15-07-T1/T2 | 15-09/10/14 |
| tests/test_service_schedule.py, tests/test_service_recovery.py; derive_expectations/ExpectationProducer/OwnerLoginProbe input provenance and actual-entry recovery cases | 15-10-T1/T2 | 15-11/13/14 |
| tests/test_service_health.py; observer-only expectation/scope/date/source failure matrix; existing tests/test_alert_observer.py CRITICAL/reminder/own-store failure cases | 15-11-T1/T2 | 15-12/14 |
| tests/test_web_control_routes.py | 15-12-T1/T2 | 15-14 |
| tests/test_service_cli.py, tests/test_service_launchd.py | 15-13-T1/T2 | 15-14 |
| tests/test_service_dry_run.py, tests/test_service_acceptance.py; fresh interpreter probe additions | 15-14-T1 | Final phase verification |

No new package installation or ORM schema-push gate is applicable. Explicit owned SQLite migrations run only in temporary fixture stores during offline implementation checks; runtime production migration/installation requires the documented separate operator path.

## Dependency and Ownership Audit

| Wave | Plans | Producer handoff |
|---|---|---|
| 1 | 15-01 | Shared strict contracts and tested fixture factory |
| 2 | 15-02,15-03,15-04,15-05 | Session authority; journal/leader; dispatch schema+reader compatibility; controls |
| 3 | 15-06,15-07 | Authentic composition after session producer; single-shot frozen dispatch after schema/controls |
| 4 | 15-08 | All final POST paths after control, provider, session and approval contracts |
| 5 | 15-09 | Shared cli/intraday bounded authority after guard |
| 6 | 15-10 | Active scheduler/recovery after all execution safety producers |
| 7 | 15-11 | Saved health and resilient independent observer after expectation producer |
| 8 | 15-12,15-13 | Authenticated web requests and CLI/login supervision after observer schema/constructor handoff |
| 9 | 15-14 | Integrated crash/capability/full-regression acceptance |

Same-wave files_modified sets are disjoint. Shared cli.py edits are ordered15-07→15-08→15-09; intraday.py15-02→15-09; evidence_contracts.py/web_evidence.py15-04→15-11; web_app.py15-12 only; runbook15-13→15-14. Provider admission03→07→09→10 and independent expectation03→10→11→13 handoffs are explicit; alert_cli.py composition is owned13 after11 observer config/constructor changes. No producer-before-consumer cycle or blanket summary chaining.


## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Instructions |
|---|---|---|---|
| Phase 9 elapsed-day acceptance | FUT-04 | Tests cannot supply real operator approval or broker-observed eligible-day proof | Complete and approve 09-08 using exact campaign/source identities. Preserve unresolved freezes. Missing acceptance blocks activation, not planning/offline execution. |
| Mac login/logout, sleep/wake and service lifecycle | AUTO-02 | Real user GUI domain and machine lifecycle | Use explicitly installed disabled/offline configuration; check login start, logout stop, missed window on wake, kill persistence and uninstall preservation. Installation is a separate operator action. |
| Korean web control usability | AUTO-02 | Owner review of PC/phone affordances | Inspect pause/kill/resume effect, requested/applied distinction and active blocks; offline temp evidence, authenticated sessions. |
| External private phone access | AUTO-02 | Existing future deployment/device acceptance | Actual Tailscale/HTTPS/device configuration remains a separate follow-up. Do not assert external reachability from local browser tests. |

## Multi-Source Coverage Audit

| Source | ID | Required feature / constraint | Plan(s) | Status |
|---|---|---|---|---|
| GOAL | Phase15 | Calendar-aware unattended daily + held protection, exactly-once intent/recovery, health and immediate manual stop | 15-01–14 | COVERED |
| REQ | FUT-04 | Sufficient manually approved evidence before scheduling mutation | 15-01/06/08/10/13/14 | COVERED |
| REQ | AUTO-01 | Calendar/session, leader, durable checkpoint and idempotent intent | 15-01/02/03/04/06/07/08/09/10/11/14 | COVERED |
| REQ | AUTO-02 | Pause/resume/health/restart/kill preserving evidence | 15-01/03/05/08/09/10/11/12/13/14 | COVERED |
| CONTEXT | D-01 | Daily09:10 immutable single-shot identity | 15-01/04/07/10 | COVERED |
| CONTEXT | D-02 | 09:00 protection/fair account exclusion | 15-09/10 | COVERED |
| CONTEXT | D-03 | 60s risk,15:20/15:30 absolute cutoffs | 15-02/09/10 | COVERED |
| CONTEXT | D-04 | 08:50 read-only prep/final gates | 15-02/08/10 | COVERED |
| CONTEXT | D-05 | Same-date never-started before09:20 only | 15-07/10 | COVERED |
| CONTEXT | D-06 | Exclusive broker recovery then eligible work | 15-03/04/06/09/10 | COVERED |
| CONTEXT | D-07 | Resume only never-dispatched stored input | 15-04/07/10 | COVERED |
| CONTEXT | D-08 | Daily failure independent from healthy risk | 15-09/10 | COVERED |
| CONTEXT | D-09 | Normal pause every BUY/daily, retain risk | 15-05/08/10/12 | COVERED |
| CONTEXT | D-10 | Global kill every new POST, retain reconciliation | 15-05/08/10/12 | COVERED |
| CONTEXT | D-11 | CLI/web/phone narrow audited requests | 15-05/12/13/14 | COVERED |
| CONTEXT | D-12 | Persistent explicit resume, no safety clearing | 15-05/08/10/13 | COVERED |
| CONTEXT | D-13 | Current Mac, awake requirement | 15-01/13/14 | COVERED |
| CONTEXT | D-14 | Login LaunchAgent/recovery first | 15-03/10/13 | COVERED |
| CONTEXT | D-15 | At most3 automatic restarts/600s, persistent latch | 15-03/13/14 | COVERED |
| CONTEXT | D-16 | Saved health, independent alerts/dedupe/reminders | 15-11/13/14 | COVERED |
| RESEARCH | SessionEvidence | Authoritative exact date/delayed opening, UNKNOWN refresh, absolute cutoffs | 15-02/10 | COVERED |
| RESEARCH | ServiceJournal / leader | Owned explicit migrations, scope/date IDs, immutable universe, separate flock | 15-01/03/10 | COVERED |
| RESEARCH | FairAccountWork | No lease during provider/sleep, bounded one-pass account work/manual compatibility | 15-08/09/10 | COVERED |
| RESEARCH | DailyDispatch | Frozen input, SDK retry0, final actual-entry deadline/control/session admission, bounded handshake/no lease or shared lock over response, durable consumed suppression and no uncertain replay | 15-04/07/10 | COVERED |
| RESEARCH | Schema companions | Pure v3/v4 saved report/web/observer compatibility | 15-04/11/14 | COVERED |
| RESEARCH | FinalSubmissionAuthority | Pending restriction, serialized accepted-request/admission, in-flight semantics | 15-05/08/14 | COVERED |
| RESEARCH | OperationalRequests | Global stop domain, actor/revision/audit, service-only apply, stale resume | 15-05/12/13 | COVERED |
| RESEARCH | Service health / observer | Independent exact-date obligation writer with protected enabled/login/session/control inputs, saved absent expectations, UNKNOWN source health and resilient own-store delivery/reminders | 15-03/10/11/13/14 | COVERED |
| RESEARCH | LaunchAgent / restart | Owner GUI/login,3 admitted restarts/600s, collision checks, lifecycle | 15-03/13/14 | COVERED |
| RESEARCH | Activation receipt | Both09-08 approvals, exact campaign/profile/source proof, freezes, real denial | 15-01/06/08/13/14 | COVERED |
| RESEARCH | Authentic mock / offline | Shipped KIS adapter composition, no in-memory acceptance; zero external capability dry-run | 15-06/13/14 | COVERED |
| RESEARCH | Security / paths / dependency | Strict owner-local paths/capabilities, sanitized evidence, ASVS5.0 web guards, no new packages | 15-01/03/05/06/08/11/12/13/14 | COVERED |

Deferred/out-of-scope: actual Tailscale deployment/device configuration, independent external outage monitoring, before-login daemon/separate server and Phase16 real promotion. Manual checks remain recorded below; offline code completion never claims external activation.


## Validation Sign-Off

- [x] Every task has automated verify and producing tests/fixtures mapped.
- [x] No three consecutive implementation tasks lack automated feedback.
- [x] All missing test references have producing tasks before use.
- [x] No watch-mode flags or live collaborators are planned.
- [ ] Measured focused feedback meets the target.
- [x] nyquist_compliant: true records validated plan coverage, not executed tests.
- [ ] wave_0_complete: true only after required fixtures/tests actually exist.

**Revision1 static audit:** all14 frontmatter and plan-structure checks passed with zero errors/warnings;28 tasks retain automated feedback. Wave13 moves from7 to8 after11 observer config/constructor, retaining9 waves and disjoint file ownership. Four blocker contracts and the analog-reference warning have targeted changes; independent recheck remains pending. No implementation tests or external operations were performed.

**Approval:** plan coverage audited; independent plan checker, implementation test results and human/operator acceptance remain pending. Full regression command runs in15-14 verification; no execution tests were run during planning.
