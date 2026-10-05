---
phase: 15-unattended-scheduling-service-resilience
verified: 2026-10-05T03:26:58Z
status: passed
score: 46/46 must-haves verified (44 automated, 2 owner-reported UAT)
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 39/46
  previous_report_commit: 5578359
  initial_report_commit: d7460e5
  tested_implementation_commit: 6c038d13d35e95b9148fc7b7bd5a6ab5644e779d
  gaps_closed:

    - "G5: actual fail-soft intraday outcomes no longer fabricate successful protection progress or recover stalled-worker incidents."
  gaps_remaining: []
  regressions: []
must_haves:
  truths:

    - "KRX holiday/session rules schedule one daily decision cycle and a separately bounded held-position risk worker."
    - "Leader locking, durable job identities, checkpoints, and reconciliation prevent overlapping workers or duplicate order submission after restart."
    - "Health checks detect missed schedules, stalled workers, stale market data, and notification failure; recovery remains fail closed."
    - "Manual pause, resume, dry-run, and global kill controls work without deleting audit evidence or releasing unresolved-order freezes."
    - "D-01, D-07: logical daily identity uses scope, mock target and KST date, while immutable input and dispatch identity survive a process generation."
    - "D-11, D-12: request authority and applied state are distinct, actor/revision attributable and independent of date rollover."
    - "D-13, D-14: setup is disabled by default on the owner Mac; offline proofs cannot confer broker or provider authority."
    - "D-01, D-03, D-04, D-05: schedule firing never grants execution; every consumer uses the same date-specific authoritative session evidence."
    - "D-03: delayed openings preserve absolute 15:20 POST and 15:30 watch cutoffs; an opening after 09:20 cannot shift the daily evaluation."
    - "D-04: 08:50 preparation preserves PRE_OPEN execution blocks and current UNKNOWN evidence is refreshable."
    - "D-01, D-06, D-07: one scope/target/date/kind job retains ordered checkpoints across crash generations."
    - "D-06: service leadership is exclusive but never grants account mutation or freeze-clearing authority."
    - "D-15: at most three automatic worker restarts per 600 seconds are durably admitted; exhaustion persists MANUAL_ATTENTION."
    - "D-01, D-07: first canonical input is immutable and each scope/target/date/ticker can be dispatched once."
    - "D-06, D-07: legacy PROVIDER_ATTEMPT is conservatively dispatched; unfinished recovery cannot mutate evaluation state before exclusive account authority."
    - "D-16: schema upgrades preserve saved reporting, web and observer evidence without silently rewriting existing trading facts."
    - "D-09, D-10: accepted pending PAUSE blocks every BUY/daily dispatch, and accepted pending KILL blocks every new order before application polling."
    - "D-11: CLI/web submit only fixed actor/scope/revision requests; final service applies or rejects them."
    - "D-12: pause/kill persist across crash/login/date changes; stale resume never weakens kill or clears evidence gates."
    - "FUT-04: no unattended trading collaborator or final submission is enabled without both explicit 09-08 approvals bound to exact immutable evidence."
    - "D-06: recovery preserves applicable 000660 and other unresolved freezes; local receipt/readiness cannot clear them."
    - "D-13, D-14: authenticated KIS-mock composition is distinct from offline simulation and always rejects Phase16 real-money authority."
    - "D-01, D-07: dispatch sends committed prompt/system/schema/model identity rather than reconstructing current context."
    - "D-07: every durable dispatch causes at most one provider transport/subprocess attempt, including SDK max_retries=0."
    - "D-06, D-07: uncertain provider outcome is HOLD/UNKNOWN, and only proven never-dispatched inputs may resume before 09:20 after authority recovery."
    - "D-09: every BUY including previously saved/manual signals is denied by applied or accepted pending pause."
    - "D-10, D-11: accepted global kill denies every subsequent admission, including risk SELL and proof/soak/manual paths; no cancellation or liquidation is implied."
    - "D-12: pending resume, restart/date changes and stale revisions never grant submission permission."
    - "D-02, D-03: a risk pass owns account authority for at most45 seconds and releases before every60-second wait; daily work is not starved."
    - "D-01, D-07: provider work holds no account mutation lease; reserved saved-input dispatch and execution each have fresh authority."
    - "D-06, D-08: recovery precedes mutable work and failed daily evaluation does not stop independently healthy held protection."
    - "D-01–D-05: 08:50 preparation,09:00 risk/60 seconds,09:10 daily and strict before09:20 catch-up follow positive KRX/session evidence."
    - "D-06, D-07: recovery owns account authority before reconciliation/checkpoints; only never-dispatched saved inputs resume and uncertain provider/order work never retries."
    - "D-08, D-09, D-10, D-12: healthy risk protection continues after daily failure or normal pause, while kill/common safety faults block every new submission."
    - "D-16: web health exposes missed schedules, stalled workers, stale market data and notification failures from attributable saved sources."
    - "D-09, D-10, D-13: expected-worker health reflects positive session, date, controls and login/service state; same stopped Mac cannot notify during total sleep/outage."
    - "D-16: independent observer preserves occurrence/worsening/recovery dedupe, INFO history, delivery UNKNOWN and unacknowledged CRITICAL30-minute reminders."
    - "D-11: authenticated CLI/web/phone use fixed pause/resume/kill request authority with actor, time, scope, revision and CSRF."
    - "D-09, D-10, D-12: interface clearly distinguishes pending accepted restriction, applied state, rejected resume and older in-flight submission."
    - "D-16: Korean health/control views reuse approved Phase14 responsive design and show saved blocking evidence."
    - "D-11, D-12: CLI shares attributable revisioned requests and cannot silently apply resume or reset kill."
    - "D-13, D-14: current Mac starts installed service at owner login through LaunchAgent, recovery-first; sleep/logout suspend availability."
    - "D-15, D-16: durable maximum3 automatic restarts/600 seconds applies before worker construction; separate observer continues after trading restart exhaustion."
    - "D-01–D-12: integrated offline crash/race/deadline proofs show single-shot dispatch, exactly-once intent, fresh recovery, fair account work and durable stop authority."
    - "D-13–D-16: login supervision/independent health contracts are proven offline, while actual Mac/private-device operation remains manual."
    - "FUT-04: completed offline implementation is distinct from external Phase9 acceptance and deliberate activation; Phase16 real remains rejected."
  artifacts:

    - path: "trading_bot/service_models.py"
    - path: "trading_bot/service_config.py"
    - path: "tests/service_fixtures.py"
    - path: "trading_bot/session_evidence.py"
    - path: "trading_bot/market_cycle.py"
    - path: "tests/test_service_sessions.py"
    - path: "trading_bot/service_store.py"
    - path: "trading_bot/service_leader.py"
    - path: "tests/test_service_authority.py"
    - path: "trading_bot/portfolio_store.py"
    - path: "trading_bot/evidence_contracts.py"
    - path: "tests/test_portfolio_store.py"
    - path: "trading_bot/control_store.py"
    - path: "trading_bot/control_runtime.py"
    - path: "tests/test_service_controls.py"
    - path: "trading_bot/service_activation.py"
    - path: "trading_bot/service_composition.py"
    - path: "tests/test_service_activation.py"
    - path: "trading_bot/llm_provider.py"
    - path: "trading_bot/cli.py"
    - path: "tests/test_daily_dispatch.py"
    - path: "trading_bot/submission_authority.py"
    - path: "trading_bot/kis_broker.py"
    - path: "trading_bot/account_work.py"
    - path: "trading_bot/service_schedule.py"
    - path: "trading_bot/service_runtime.py"
    - path: "tests/test_service_recovery.py"
    - path: "trading_bot/web_evidence.py"
    - path: "trading_bot/alert_detector.py"
    - path: "tests/test_service_health.py"
    - path: "trading_bot/web_control.py"
    - path: "trading_bot/templates/operator/controls.html"
    - path: "tests/test_web_control_routes.py"
    - path: "trading_bot/service_cli.py"
    - path: "trading_bot/service_launchd.py"
    - path: "docs/operator-runbook.md"
    - path: "tests/test_service_acceptance.py"
    - path: "tests/test_service_dry_run.py"
  prohibitions: []
human_verification:

  - test: "Korean desktop and320px phone controls"
    expected: "Authenticated native controls clearly distinguish accepted/pending/applied/rejected state, active blocks, timestamps and older in-flight submission, with accessible44px targets and retained mobile details."
    why_human: "Rendered HTML and unchanged responsive tokens do not establish actual appearance or operator usability."

  - test: "Actual owner Mac lifecycle and independent observer"
    expected: "After separately authorized disabled/offline installation, GUI login/logout/sleep/wake, SIGTERM/unexpected exit, restart exhaustion and removal preserve recovery-first startup, stops/freeze/audit, honest suspension and maximum3/600; the separate observer survives trading exhaustion."
    why_human: "Generated plist and offline supervision tests cannot prove installed-device lifecycle."

  - test: "Actual private Tailscale HTTPS phone access/session"
    expected: "After separately authorized private configuration, owner phone over mobile data has valid certificate, authentication, CSRF/session expiry and independent sessions; controls preserve fixed actor/scope/revision and truthful saved state."
    why_human: "Private network, certificate and real phone/session behavior require owner devices; no deployment occurred."

  - test: "External activation acceptance"
    expected: "Both actual09-08 approvals, immutable eligible mock evidence/profile/source identities, linked protected receipt, supported single-shot provider and current broker safety must pass before activation; absent/mismatched proof remains closed and000660 remains frozen until same-subject terminal proof."
    why_human: "Actual authenticated broker/provider evidence and explicit approvals cannot be inferred from synthetic fixtures; current CodexCLI0.144.6 single-shot support remains closed."
uat_accepted_at: "2026-10-05T05:37:31Z"
---

# Phase 15: Unattended Scheduling and Service Resilience Verification Report

**Phase Goal:** Operators can run calendar-aware daily evaluation and intraday held-position protection unattended, with exactly-once intent, durable recovery, health visibility, and immediate manual stop authority.
**Verified:** 2026-10-05T03:26:58Z
**Status:** passed — independent implementation checks plus owner-reported UAT
**Re-verification:** Yes — after actual G5 returned-outcome correction; previous independent report `5578359`, initial report `d7460e5`.

**46/46 must-haves accepted: 44 independently verified, 2 confirmed by owner-reported UAT. No implementation gaps remain.** The five truths affected by G5 are VERIFIED. The owner separately answered `pass` for all four UAT categories, including private-phone access and installed Mac lifecycle, on 2026-10-05. This acceptance is user-reported, not a new agent-performed device or broker test. No overrides or newly deferred scope were applied. Phase acceptance grants no unattended mutation or Phase16 authority; the separate immutable activation approvals and safety gates remain mandatory.

## Evidence scope and provenance

Applied the typed verifier goal-backward references/template and the existing execute-phase verification workflow. Read project instructions, STATE/PROJECT/REQUIREMENTS/ROADMAP, canonical CONTEXT, all14 plan frontmatters/truths/artifact/link requirements and summary inventories. PLAN-CHECK documents remain reference reports. Prior independent source/behavior evidence in `5578359` is retained for unchanged passed items, including G1–G4 and future-control provenance; summaries alone are not evidence.

Independently compared `c5ad0d1 → 6c038d1`: only `trading_bot/service_runtime.py`, `tests/test_service_acceptance.py` and `tests/test_service_cli.py` changed outside planning metadata. Inspected the complete changed source and relevant actual binding, intraday, account-work, audit writer, query-only health, detector, controls, scoped suppression and templates. `6c038d1 → HEAD ea5ccae` changes only STATE and15-14-SUMMARY. All38 declared unique artifact paths exist; fresh machine queries passed42/42 declared entries, and all28 declared links remain semantically accounted for.

Reused the orchestrator-supplied final actual regression result: `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` — **1904 passed in488.69s**, session97058, tested implementation **`6c038d13d35e95b9148fc7b7bd5a6ab5644e779d`**. The supplied focused gate is205 passed in61.16s across11 relevant modules. No full-suite duplicate was run. The prior1894-pass gate at`c5ad0d1` is historical, not the current gate; the earlier1891-pass/two-failure result at`cc57bd5` remains distinguished in15-14-SUMMARY. Compile/diff checks were supplied as passed; fresh `git diff --check` also passed. Execute:post/verify:post hooks are empty; no separate code-review/security audit is claimed.

Fresh selected checks passed 17 unique named test cases and 5 additional source/result negative diagnostic cases. Every invocation finished under 10 seconds. All used resolved temporary stores, injected offline adapters and NoExternalCapabilities; no live KIS, paid LLM, Discord, production database read/migration, approval capture, install/download, actual LaunchAgent or deployment occurred. Only this report was edited, with no source/test/tracking change or commit.

## Observable truths

| # / contract | Truth | Verdict | Evidence |
| --- | --- | --- | --- |
| 1 (SC1) | KRX holiday/session rules schedule one daily decision cycle and a separately bounded held-position risk worker. | VERIFIED | Fresh bounded same-account capture immediately precedes first spawned collection; actual screen/context/news fairness checks passed. |
| 2 (SC2) | Leader locking, durable job identities, checkpoints, and reconciliation prevent overlapping workers or duplicate order submission after restart. | VERIFIED | ServiceLeader, immutable dispatch/intent checkpoints, final POST admission; named crash proof passed. |
| 3 (SC3) | Health checks detect missed schedules, stalled workers, stale market data, and notification failure; recovery remains fail closed. | VERIFIED | Actual production quote failure remains audited FAILED and service BLOCKED/ITERATION_FAILED; query-only health denies readiness; repeated failure retains the actual stall, success recovers and renewed failure reopens it. |
| 4 (SC4) | Manual pause, resume, dry-run, and global kill controls work without deleting audit evidence or releasing unresolved-order freezes. | VERIFIED | Advancing-clock production activation check passed; current source TTL and restrictive controls remain enforced. |
| 5 (15-01.1) | D-01, D-07: logical daily identity uses scope, mock target and KST date, while immutable input and dispatch identity survive a process generation. | VERIFIED | Strict models/config and stable LogicalJobKey; model/config tests in regression. |
| 6 (15-01.2) | D-11, D-12: request authority and applied state are distinct, actor/revision attributable and independent of date rollover. | VERIFIED | Request/application models and append-only attribution; control persistence tests. |
| 7 (15-01.3) | D-13, D-14: setup is disabled by default on the owner Mac; offline proofs cannot confer broker or provider authority. | VERIFIED | Disabled defaults and temporary OfflineActivationAuthority; capability probe passed. |
| 8 (15-02.1) | D-01, D-03, D-04, D-05: schedule firing never grants execution; every consumer uses the same date-specific authoritative session evidence. | VERIFIED | Exact-date protected SessionEvidenceProvider feeds schedule/policy/intraday; session tests. |
| 9 (15-02.2) | D-03: delayed openings preserve absolute 15:20 POST and 15:30 watch cutoffs; an opening after 09:20 cannot shift the daily evaluation. | VERIFIED | Absolute 15:20/15:30 and strict 09:20; delayed-opening boundary tests. |
| 10 (15-02.3) | D-04: 08:50 preparation preserves PRE_OPEN execution blocks and current UNKNOWN evidence is refreshable. | VERIFIED | PRE_OPEN restrictions and UNKNOWN refresh; service session tests. |
| 11 (15-03.1) | D-01, D-06, D-07: one scope/target/date/kind job retains ordered checkpoints across crash generations. | VERIFIED | ServiceJournal unique job/checkpoints/universe; process crash identity test passed. |
| 12 (15-03.2) | D-06: service leadership is exclusive but never grants account mutation or freeze-clearing authority. | VERIFIED | Separate leader/account/global locks; live-owner and stale-heartbeat tests. |
| 13 (15-03.3) | D-15: at most three automatic worker restarts per 600 seconds are durably admitted; exhaustion persists MANUAL_ATTENTION. | VERIFIED | Durable reserve_restart and manual-attention latch; restart exhaustion tests. |
| 14 (15-04.1) | D-01, D-07: first canonical input is immutable and each scope/target/date/ticker can be dispatched once. | VERIFIED | Primary first input/envelope immutable, atomic scoped dispatch claim. |
| 15 (15-04.2) | D-06, D-07: legacy PROVIDER_ATTEMPT is conservatively dispatched; unfinished recovery cannot mutate evaluation state before exclusive account authority. | VERIFIED | Legacy attempt migration and lease-owned recovery; daily dispatch tests. |
| 16 (15-04.3) | D-16: schema upgrades preserve saved reporting, web and observer evidence without silently rewriting existing trading facts. | VERIFIED | Schema v4 plus v3 read compatibility; read-only byte/schema tests. |
| 17 (15-05.1) | D-09, D-10: accepted pending PAUSE blocks every BUY/daily dispatch, and accepted pending KILL blocks every new order before application polling. | VERIFIED | Control acceptance serialized against transport entry; pending restrictions tests. |
| 18 (15-05.2) | D-11: CLI/web submit only fixed actor/scope/revision requests; final service applies or rejects them. | VERIFIED | Service-only ControlApplier and fixed CLI/web request facades. |
| 19 (15-05.3) | D-12: pause/kill persist across crash/login/date changes; stale resume never weakens kill or clears evidence gates. | VERIFIED | Persisted revisions; stale RESUME cannot weaken KILL or clear frozen subjects. |
| 20 (15-06.1) | FUT-04: no unattended trading collaborator or final submission is enabled without both explicit 09-08 approvals bound to exact immutable evidence. | VERIFIED | Both exact 09-08 approvals/receipt identities required before collaborator construction. |
| 21 (15-06.2) | D-06: recovery preserves applicable 000660 and other unresolved freezes; local receipt/readiness cannot clear them. | VERIFIED | Current/receipt freeze validation; historical 000660 preservation test. |
| 22 (15-06.3) | D-13, D-14: authenticated KIS-mock composition is distinct from offline simulation and always rejects Phase16 real-money authority. | VERIFIED | Concrete mock KIS composition with guarded authority; REAL rejected and offline distinguished. |
| 23 (15-07.1) | D-01, D-07: dispatch sends committed prompt/system/schema/model identity rather than reconstructing current context. | VERIFIED | Committed prompt/system/schema/model sent through envelope API; dispatch tests. |
| 24 (15-07.2) | D-07: every durable dispatch causes at most one provider transport/subprocess attempt, including SDK max_retries=0. | VERIFIED | SDK/transport retries disabled, child single-shot admission; named crash test passed. |
| 25 (15-07.3) | D-06, D-07: uncertain provider outcome is HOLD/UNKNOWN, and only proven never-dispatched inputs may resume before 09:20 after authority recovery. | VERIFIED | DISPATCHED_UNKNOWN consumes attempt; deadline/current-session entry gate. |
| 26 (15-08.1) | D-09: every BUY including previously saved/manual signals is denied by applied or accepted pending pause. | VERIFIED | BUY guarded across saved/manual/proof/soak/intraday roots; matrix tests. |
| 27 (15-08.2) | D-10, D-11: accepted global kill denies every subsequent admission, including risk SELL and proof/soak/manual paths; no cancellation or liquidation is implied. | VERIFIED | Actual KisOrderAdapter HTTP entry guarded after preparation; root/order race tests. |
| 28 (15-08.3) | D-12: pending resume, restart/date changes and stale revisions never grant submission permission. | VERIFIED | Effective state uses accepted pending restrictions; pending RESUME grants no permission. |
| 29 (15-09.1) | D-02, D-03: a risk pass owns account authority for at most45 seconds and releases before every60-second wait; daily work is not starved. | VERIFIED | 45s interrupt plus 10s cleanup/POST budget and released lease before waits; budget test passed. |
| 30 (15-09.2) | D-01, D-07: provider work holds no account mutation lease; reserved saved-input dispatch and execution each have fresh authority. | VERIFIED | Provider spawned with provider-only settings after lease release; spawn lock probes. |
| 31 (15-09.3) | D-06, D-08: recovery precedes mutable work and failed daily evaluation does not stop independently healthy held protection. | VERIFIED | Actual production OPEN/PARTIAL/NO_FILL reconciliation checks permit bounded healthy work with scoped suppression and unchanged freeze. |
| 32 (15-10.1) | D-01–D-05: 08:50 preparation,09:00 risk/60 seconds,09:10 daily and strict before09:20 catch-up follow positive KRX/session evidence. | VERIFIED | Actual production screen/context/news spawned collection checks passed; cutoff/crash never recollect first inputs. |
| 33 (15-10.2) | D-06, D-07: recovery owns account authority before reconciliation/checkpoints; only never-dispatched saved inputs resume and uncertain provider/order work never retries. | VERIFIED | Exclusive recovery before checkpoint mutation; consumed provider/intent never replayed. |
| 34 (15-10.3) | D-08, D-09, D-10, D-12: healthy risk protection continues after daily failure or normal pause, while kill/common safety faults block every new submission. | VERIFIED | Production scoped determinate pending-order recovery passed; normal pause retains eligible held-risk work. Actual typed completed protection and unchanged scoped-freeze checks passed. |
| 35 (15-11.1) | D-16: web health exposes missed schedules, stalled workers, stale market data and notification failures from attributable saved sources. | VERIFIED | Actual runtime result is matched to committed watch outcome/phase/reason/snapshot; failure produces attributed BLOCKED health and no positive progress. Source reader is unchanged. |
| 36 (15-11.2) | D-09, D-10, D-13: expected-worker health reflects positive session, date, controls and login/service state; same stopped Mac cannot notify during total sleep/outage. | VERIFIED | Independent pre-tick/midnight expectation provenance and negative/UNKNOWN tests. |
| 37 (15-11.3) | D-16: independent observer preserves occurrence/worsening/recovery dedupe, INFO history, delivery UNKNOWN and unacknowledged CRITICAL30-minute reminders. | VERIFIED | Independently executed production runtime → reader → detector → AlertStore proof preserves repeated failures, recovers only on actual completed protection and reopens renewed failure. Prior outbox/reminder evidence is retained. |
| 38 (15-12.1) | D-11: authenticated CLI/web/phone use fixed pause/resume/kill request authority with actor, time, scope, revision and CSRF. | VERIFIED — OWNER UAT | Fixed authenticated request routes proven offline; owner reported `pass` for private-phone HTTPS/session access in UAT test 3. |
| 39 (15-12.2) | D-09, D-10, D-12: interface clearly distinguishes pending accepted restriction, applied state, rejected resume and older in-flight submission. | VERIFIED | Native forms show accepted/pending/applied/rejected and in-flight source evidence; route tests. |
| 40 (15-12.3) | D-16: Korean health/control views reuse approved Phase14 responsive design and show saved blocking evidence. | VERIFIED | Unchanged native Phase14 templates/styles render actual saved blocking health; corrected runtime supplies BLOCKED/ITERATION_FAILED. Owner reported `pass` for desktop/320px usability in UAT test 1. |
| 41 (15-13.1) | D-11, D-12: CLI shares attributable revisioned requests and cannot silently apply resume or reset kill. | VERIFIED | Fixed attributable CLI request facade; no silent applied RESUME/reset. |
| 42 (15-13.2) | D-13, D-14: current Mac starts installed service at owner login through LaunchAgent, recovery-first; sleep/logout suspend availability. | VERIFIED — OWNER UAT | LaunchAgent generation is wired and offline-tested; owner reported `pass` for actual Mac lifecycle and independent observer in UAT test 2. |
| 43 (15-13.3) | D-15, D-16: durable maximum3 automatic restarts/600 seconds applies before worker construction; separate observer continues after trading restart exhaustion. | VERIFIED | Launcher reserves maximum3/600 before factory; separate observer process/budget and exhaustion tests. |
| 44 (15-14.1) | D-01–D-12: integrated offline crash/race/deadline proofs show single-shot dispatch, exactly-once intent, fresh recovery, fair account work and durable stop authority. | VERIFIED | Actual production fresh snapshot, spawned collection, advancing clock, determinate order, authority budget and dispatch-crash negative checks passed. |
| 45 (15-14.2) | D-13–D-16: login supervision/independent health contracts are proven offline, while actual Mac/private-device operation remains manual. | VERIFIED | Actual fail-soft result and incident lifecycle now pass independently; unchanged launcher/independent expectations retain prior behavioral evidence. Installed Mac/private-device behavior remains manual. |
| 46 (15-14.3) | FUT-04: completed offline implementation is distinct from external Phase9 acceptance and deliberate activation; Phase16 real remains rejected. | VERIFIED | No offline acceptance fabrication; both real approvals absent; current Codex unproven and REAL closed. |

**Score: 46/46 accepted; 44 independent implementation checks and 2 owner-reported device truths; zero failed or unresolved truths.** All four roadmap criteria and 42 canonical plan truths remain in the denominator. Automated evidence is unchanged; all four manual categories are resolved by the owner's individual `pass` reports in 15-UAT.md.

## Required artifacts

Artifact query: **42/42 declared entries, 38 unique paths, existence/substance passed**. Manual inspection additionally checked usage/data flow. Query success is not a runtime guarantee.

| Plan | Declared artifacts (all entries covered) | Three-level verification |
| --- | --- | --- |
| 15-01 | `trading_bot/service_models.py`<br>`trading_bot/service_config.py`<br>`tests/service_fixtures.py` | Exists, substantive, wired; behavioral tests present in unchanged full-pass tree. |
| 15-02 | `trading_bot/session_evidence.py`<br>`trading_bot/market_cycle.py`<br>`tests/test_service_sessions.py` | Exists, substantive, wired; behavioral tests present in unchanged full-pass tree. |
| 15-03 | `trading_bot/service_store.py`<br>`trading_bot/service_leader.py`<br>`tests/test_service_authority.py` | Exists, substantive, wired; behavioral tests present in unchanged full-pass tree. |
| 15-04 | `trading_bot/portfolio_store.py`<br>`trading_bot/evidence_contracts.py`<br>`tests/test_portfolio_store.py` | Exists, substantive, wired; behavioral tests present in unchanged full-pass tree. |
| 15-05 | `trading_bot/control_store.py`<br>`trading_bot/control_runtime.py`<br>`tests/test_service_controls.py` | Exists, substantive, wired; behavioral tests present in unchanged full-pass tree. |
| 15-06 | `trading_bot/service_activation.py`<br>`trading_bot/service_composition.py`<br>`tests/test_service_activation.py` | Exists, substantive, wired; behavioral tests present in unchanged full-pass tree. |
| 15-07 | `trading_bot/llm_provider.py`<br>`trading_bot/cli.py`<br>`tests/test_daily_dispatch.py` | Exists, substantive, wired; behavioral tests present in unchanged full-pass tree. |
| 15-08 | `trading_bot/submission_authority.py`<br>`trading_bot/kis_broker.py`<br>`tests/test_service_controls.py` | Exists, substantive, wired; behavioral tests present in unchanged full-pass tree. |
| 15-09 | `trading_bot/account_work.py`<br>`trading_bot/cli.py`<br>`tests/test_service_authority.py` | Exists, substantive, wired; determinate same-subject production reconciliation checks passed. |
| 15-10 | `trading_bot/service_schedule.py`<br>`trading_bot/service_runtime.py`<br>`tests/test_service_recovery.py` | Exists, substantive, wired; fresh snapshot and spawned collection verified. Returned risk outcome is typed, audit-correlated and behaviorally verified. |
| 15-11 | `trading_bot/web_evidence.py`<br>`trading_bot/alert_detector.py`<br>`tests/test_service_health.py` | Exists, substantive, wired; saved failure projection and actual runtime result flow verified end to end. |
| 15-12 | `trading_bot/web_control.py`<br>`trading_bot/templates/operator/controls.html`<br>`tests/test_web_control_routes.py` | Substantive/wired; truthful saved blocking health; visual check pending. |
| 15-13 | `trading_bot/service_cli.py`<br>`trading_bot/service_launchd.py`<br>`docs/operator-runbook.md` | Exists, substantive, wired; advancing-clock production activation and future-control observer checks passed. |
| 15-14 | `tests/test_service_acceptance.py`<br>`tests/test_service_dry_run.py`<br>`docs/operator-runbook.md` | Exists, substantive, wired; corrective coverage G1–G5 passed, including actual fail-soft production binding and real incident recovery. |

Additional `trading_bot/service_collection.py` exists, is substantive, is spawned by the actual production runtime, and carries frozen data/quote-only authority. Its parent result is bounded and canonically validated. Additional critical production artifacts inspected: `control_runtime.py`, `submission_authority.py`, actual `kis_order_adapter.py` HTTP entry, `portfolio.py` pending-subject suppression, `alert_observer.py` partition handling and `tests/capability_probe.py`.

## Key links

Machine query reported **1/28 verified**, because most PLAN `from`/`to` values are function/component/endpoint names rather than relative files. For example 15-10 emits “Source file not found (from: must be a relative file path; describe components/endpoints in via:)”. These are metadata-query limitations, not evidence that the actual symbols are absent. All 28 links were checked semantically in source:

| Plan | Both declared links | Wiring result |
| --- | --- | --- |
| 15-01 | `service_config.ServiceSettings` → `service_models.ServiceScope` (fixed account/target and path ownership)<br>`tests/service_fixtures.py` → `Phase15 test modules` (shared no-network fixture factory) | WIRED |
| 15-02 | `session_evidence.load_session_evidence` → `MarketCyclePolicy.classify` (same exact-date evidence)<br>`MarketCyclePolicy.classify` → `intraday.session_phase_at` (shared classification with absolute cutoffs) | WIRED |
| 15-03 | `ServiceLeader` → `ServiceJournal` (generation owner and durable restart admission)<br>`ServiceJournal.claim_job` → `LogicalJobKey` (scope/target/date/kind uniqueness) | WIRED |
| 15-04 | `portfolio_store.claim_daily_dispatch` → `daily_evaluation_dispatches` (atomic exclusive claim before provider)<br>`evidence_contracts.PORTFOLIO_REPORT_SCHEMA` → `web_evidence._transaction` (supported schema and exact-column compatibility) | WIRED |
| 15-05 | `ControlRequestWriter.append_request` → `global control/submission lock` (durable acceptance serialization)<br>`ControlApplier.apply_pending` → `AppliedControl` (fresh scoped safety checks, service-only applied authority) | WIRED |
| 15-06 | `validate_unattended_activation` → `AcceptanceReceipt/checkpoint evidence` (both 09-08 approvals and immutable campaign/profile/source identities)<br>`build_service_composition` → `KISBroker/KisOrderAdapter` (authenticated mock domain/TR IDs/account receipt, guarded final POST) | WIRED |
| 15-07 | `cli._load_or_generate_daily_signal` → `portfolio_store.claim_daily_dispatch` (active scoped authority and commit-before-call)<br>`provider.generate_signal_from_envelope` → `ProviderDispatchAdmission.admit_at_transport_entry/TransportEntryAck` (frozen bytes with final current deadline/session/accepted-control check and bounded entry ordering) | WIRED |
| 15-08 | `KISBroker.place_order` → `SubmissionAuthority.admit` (same global lock held through one bounded POST attempt)<br>`manual/proof/soak/intraday builders` → `ControlReader.effective_state` (no service-start-only exemption) | WIRED |
| 15-09 | `BoundedAccountWork.run` → `MutationLease/recover_to_active/release_after_reconciliation` (same-account broker truth before mutation)<br>`daily provider child/wait` → `released account lease` (no authority across LLM or sleep) | WIRED |
| 15-10 | `ExpectationProducer.publish` → `ExpectationWriter.record_derived` (independent protected enabled/login registration and exact-date authoritative session/control provenance)<br>`ServiceRuntime.recover/start` → `BoundedAccountWork/control/activation` (exclusive fresh recovery before dispatch or POST) | WIRED |
| 15-11 | `independently derived expectations and separate runtime heartbeats` → `OperatorEvidenceService` (pure owner/version checked read-only DTO projections)<br>`AlertObserver._scan` → `AlertStore/notification_transport` (same existing outbox ownership/dedupe/reminder semantics) | WIRED |
| 15-12 | `POST /controls/<resource_id>/<action>` → `ControlRequestWriter.append_request` (server actor/time, registered scope and expected revision)<br>`GET /controls/<resource_id>` → `read-only control/service DTOs` (requested versus applied source-linked evidence) | WIRED |
| 15-13 | `bot-service run/launch` → `ServiceLeader/ServiceJournal.reserve_restart` (durable admission before worker recovery/construction)<br>`separate observer LaunchAgent` → `bot-alerts` (independent process/supervision from trading budget) | WIRED |
| 15-14 | `service_cli.dry-run` → `service_runtime through temporary topology` (same scheduling/recovery reducers, capability-free frozen inputs)<br>`capability_probe fresh interpreter` → `web/control/read-only/service-disabled surfaces` (tripwires before imports and byte-identical source evidence) | WIRED |

Concrete production binding requires actual `ServiceRuntime`, `AccountTradingBinding`, `BoundedAccountWork`, `OwnedActivationCheck`, `KISBroker` and committed audit. A placeholder callback alone cannot grant authority. Broker preparation precedes the final serialized entry; the actual adapter checks a typed, single-use final entry after preparation. Pending accepted PAUSE/KILL is re-read at provider/POST entry. Admission and stop acceptance share the global lock through bounded POST; no SQL transaction spans external I/O.

An additional semantic link is **VERIFIED**: `AccountTradingBinding.risk → IntradayIterationResult → ServiceRuntime.tick/_record_risk_result → attributable ServiceJournal progress → query-only health → AlertDetector → AlertStore`. Returned outcome and committed watch evidence agree before successful progress is emitted; actual repeated failure/success/re-failure proves the incident transition.

## Data-flow trace

| Dynamic artifact | Actual upstream source / behavior | Verdict |
| --- | --- | --- |
| First daily universe and held context | Fresh BoundedAccountWork operation snapshot captured immediately before collection; released lease; same frozen snapshot sent to child and held context | VERIFIED G1 |
| Production market inputs | Actual MarketDataSource screen/context/news in spawned ProductionInputSource; bounded atomic result; parent validates captured identity, prompt identity, canonical envelopes and duplicate/universe limits | VERIFIED G2 |
| Completed/recovered daily inputs | Durable INPUT_COLLECTION_STARTED before spawn; cutoff/crash/incomplete successor UNKNOWN; saved first universe/envelopes are immutable and never silently recollected | VERIFIED G2 |
| Activation safety | Owned immutable approval/receipt proof plus typed ObservedSafetyReader with supplied observation start and trusted evaluation end, source age and at-most10s TTL | VERIFIED G3 |
| Same-account recovery | Current normalized snapshot plus exact coherent order ID/ticker/side/quantity; determinate OPEN/PARTIAL/NO_FILL retains scoped pending suppression and freeze | VERIFIED G4 |
| Independent expectations | Protected registration + exact-date session + validated controls; future source emits CONTROL_UNKNOWN without committing invalid control timestamp | VERIFIED |
| Saved risk health | Actual watch FAILED/ITERATION_FAILED → audit-correlated BLOCKED with watch/account source IDs → health BLOCKED, mutation_ready=false and no fresh successful progress | VERIFIED G5 |
| Observer incidents | Actual failure retains WORKER_STALLED; completed ACTIVE same-snapshot protection creates positive recovery; subsequent failure reopens incident | VERIFIED G5 |
| Request/control views | Query-only owner/schema checked service/control rows → DTO → Korean native templates, with attributable pending/applied/rejected state | VERIFIED saved data; actual visual/device check pending |
| Dry-run | Frozen temporary topology through actual reducers; external capability tripwires installed before imports | VERIFIED offline only |

## Correction re-verification

**G1 closed.** `ServiceRuntime._daily` performs the fresh same-account read through bounded account work before the first collection and releases authority before spawning. The same captured operation snapshot drives held-first membership and held context; cleanup reads cannot substitute a later snapshot. Production collection tests verify captured quantity7 remains in committed prompt despite later quantity11. Existing committed universe/prompt/hash survive recovery unchanged.

**G2 closed.** Actual production composition constructs `ProductionInputSource` and spawn-safe `collection_child` in `service_collection.py`; screen/context/news are inside that child. The child receives allowlisted collection settings, quote-only mock settings, public prompt identity and frozen snapshot, with no account ID/database/owner paths, mutation lease, leader or provider authority. Source and tests check forbidden constructor/network/SQLite tripwires, no inherited account FD, strict bounded JSON, O_EXCL0600 atomic output, and canonical/provenance validation. The parent polls risk/control/heartbeat during each real collection stage. Durable start precedes process launch;90s/09:20/session cutoff/stop/crash/incomplete recovery become UNKNOWN rather than recollection. The independently executed screen/context/news and crash/cutoff cases passed.

**G3 closed.** `ObservedSafetyReader` uses the supplied observation-start timestamp and the trusted current evaluation-end clock. Validation preserves actual age, rejects future/stale/unknown or over10s observation windows, and keeps owned source/proof requirements. The advancing-clock actual production test passed, including negative slow/untrusted-source cases in its coverage; no timestamp backdating is used.

**G4 closed.** Actual production reconciliation accepts exact coherent same-subject OPEN/PARTIAL/NO_FILL proof while retaining the unresolved subject and affected-ticker suppression. Missing, UNKNOWN, contradictory, duplicate or wrong-subject truth remains closed. Terminal freeze release is never inferred from nonterminal proof. Actual production named OPEN/PARTIAL/NO_FILL tests and a contradictory quantity negative test passed; historical000660 remains frozen. This closure does not require healthy other subjects to fail merely because one subject is scoped out.

**Additional future-control observer defect closed.** `ExpectationProducer.publish` validates candidate control time before assigning committed control timestamp/state. Actual future source becomes CONTROL_UNKNOWN without rewriting/backdating source bytes; observer/outbox CRITICAL reminders continue. The deterministic launchd future-control test passed.

**G5 closed by actual return and committed audit evidence.** `ServiceRuntime.tick` retains the result from `BoundedAccountWork.run` at461 and forwards it with the captured operation snapshot to `_record_risk_result` at469–506. Account cleanup/reconciliation must complete successfully before that return. The captured snapshot must be exact typed, same-account, same-date and mutation-capable. Protection requires an exact typed result/outcome/phase, then committed `watch_iterations/watch_observations` outcome, phase, reason and snapshot correlation. ACTIVE/COMPLETED/COMPLETED and exact captured snapshot are required for RISK_PROTECTED. Missing/unaudited/untyped/unknown/contradictory/stale proof produces UNKNOWN; audited FAILED/BLOCKED produces BLOCKED with the actual reason, and INTERRUPTED produces UNKNOWN. Non-active completion cannot assert protection.

Explicit reconciliation remains distinct: the no-protection operation must return the exact captured same-account snapshot after bounded cleanup, or an audited COMPLETED/RECONCILE_ONLY result. These produce RISK_RECONCILED/RECONCILIATION_ONLY and never RISK_PROTECTED. Existing final admission/control rechecks are unchanged. Actual OPEN/PARTIAL/NO_FILL runtime ticks continue healthy eligible protection while preserving the original000660 freeze and subject-scoped suppression.

The existing reader honors the latest non-successful event over heartbeat/older success. The existing detector requires positive expected-running, current healthy state, non-false readiness and actual successful progress for recovery. No reader or detector source changed in this correction.

## Actual production failure, recovery and renewed failure

Independently ran `tests/test_service_acceptance.py::test_actual_production_soft_risk_failure_never_clears_stall_and_real_success_recovers` against the actual production composition root, concrete AccountTradingBinding, BoundedAccountWork, real intraday reducer and committed watch store, then query-only OperatorEvidenceService, AlertDetector and actual temporary AlertStore. Only quote reading is injected; no synthetic success flag substitutes for the worker outcome.

| Trigger | Committed watch/runtime evidence | Health/detector/actual incident |
| --- | --- | --- |
|09:05 initial missing progress | No prior successful protection | WORKER_STALLED episode active |
|09:05 ordinary quote RuntimeError | FAILED/ITERATION_FAILED; runtime BLOCKED with watch/account source IDs | BLOCKED; mutation_ready=false; last_progress_at=None; no positive recovery; original stall active |
|09:06 repeated ordinary error | Same attributed unsuccessful outcome with new iteration | Original stall remains active; no positive recovery |
|09:07 non-triggering current quote | Actual COMPLETED/ACTIVE/COMPLETED, same captured snapshot; RISK_PROTECTED | RUNNING with09:07 progress; positive recovery; original episode inactive |
|09:08 renewed ordinary error | Audited FAILED; new BLOCKED/ITERATION_FAILED | Older09:07 progress retained but readiness=false; no positive recovery; a WORKER_STALLED episode active |

The independently run nine-case matrix also covers actual incomplete portfolio, stop and preflight reducer outcomes; absent/untyped/mismatched-snapshot/missing-snapshot/missing-reason/unknown-outcome results never publish protection.

A separate verifier diagnostic ran actual successful risk code and then removed or contradicted only temporary committed evidence before the caller consumed it. Missing watch observation, contradictory saved outcome, contradictory saved phase and contradictory saved reason each produced **UNKNOWN/RISK_RESULT_UNKNOWN**. Returning the prior audited successful result on the next tick also produced UNKNOWN because the newly captured snapshot differed. Thus a previously valid positive result cannot be recycled to establish new protection. Initial diagnostic setup used an unresolved macOS temp-path alias and correctly failed the fixture path guard before runtime; resolving the path allowed all5 diagnostics to pass.

## Behavioral spot-checks

Common prefix: `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q`. Fresh targeted commands used temporary/offline state only; no new test files were written.

| Named behavior / command nodes | Result | Verdict |
| --- | --- | --- |
| `tests/test_service_acceptance.py::test_actual_production_soft_risk_failure_never_clears_stall_and_real_success_recovers` |1 passed in1.20s |PASS — actual inner fail-soft and incident lifecycle |
| `tests/test_service_acceptance.py::test_actual_risk_worker_non_success_and_invalid_results_never_publish_progress` |9 parametrized cases passed in1.97s |PASS |
| `tests/test_service_cli.py::test_production_account_work_accepts_exact_nonterminal_truth_without_clearing` plus `tests/test_service_recovery.py::test_daily_failure_keeps_risk_alive_and_controls_persist` |3 OPEN/PARTIAL/NO_FILL cases plus daily-failure/KILL case:4 passed in1.43s |PASS |
| `tests/test_service_controls.py::test_service_pause_kill_skip_permissive_checks_and_preserve_risk_observation`, `tests/test_service_acceptance.py::test_first_transport_entry_keeps_locks_free_and_stale_resume_cannot_clear_kill`, `tests/test_service_recovery.py::test_terminal_risk_keeps_supervisor_for_next_day_fresh_recovery` |3 passed in1.66s |PASS |
| `python3 -c` verifier diagnostic under resolved TemporaryDirectory/production_root, no file creation |5 missing/conflicting/stale-audit cases passed,1.56s command |PASS |

Prior named passing evidence retained from the unchanged independently audited implementation at`5578359`: advancing-clock production safety (0.96s); actual screen/context/news spawn fairness (each2.27/2.74/2.74s); collection before_spawn/cutoff recovery (1.62/2.70s); contradictory quantity rejection (1.35s); future-control observer continuity (0.86s); final account/POST budget (0.65s); DISPATCH_COMMITTED crash identity (1.07s); seven fresh-interpreter capability families (4.70s). These checks are not presented as rerun in this verification. The prior outer-exception-only failed-risk test remains useful coverage but is not used to certify the actual inner returned-outcome invariant.

## Probe execution

No shell probes are declared by the14 canonical plans and no conventional `scripts/*/tests/probe-*.sh` directory exists. No documented probe is missing. Phase15's declared Python capability probes were independently run in the preceding report and remain in the supplied final current passing regression; their source did not change. There is no replacement of a failed probe with SUMMARY narration.

## Requirements coverage

| Requirement | Contract | Claimed canonical plans | Verdict |
| --- | --- | --- | --- |
|FUT-04 |Unattended cycles only after sufficient manual-operation evidence |01,06,08,10,13,14 |Implementation gate VERIFIED; owner accepted the activation gating conditions in UAT test 4. Both actual09-08 approvals and immutable owned proof remain required before collaborator construction/admission; UAT does not create these records or enable activation. |
|AUTO-01 |Calendar-aware daily/risk workers, leader exclusion, durable checkpoints and exactly-once logical intent |01,02,03,04,06,07,08,09,10,11,14 |Implementation VERIFIED with unchanged recovery/identity/session proofs and actual protection-result checks. Owner reported installed awake-Mac availability/lifecycle PASS in UAT test 2. |
|AUTO-02 |Pause/resume/health/restart/global kill retain audit and reconciliation |01,03,05,08,09,10,11,12,13,14 |Implementation VERIFIED; G5 closed. Owner reported control usability, installed lifecycle and private phone access PASS in UAT tests 1–3. |

All3 roadmap-mapped requirements appear in canonical plan frontmatter; no orphaned requirement. The independent verifier did not change tracking. After the owner's UAT acceptance, the registered completion transition may update Phase15 and its mapped requirements; runtime activation gates remain separate.

## Locked decisions and prior-phase compatibility

| Decision | Verification |
| --- | --- |
| D01 09:10 daily | Stable dated job, fresh first held snapshot and immutable dispatch verified. |
| D02 09:00 held risk | Bounded independently polled actual production collection verified; actual failed protection now remains unhealthy. |
| D03 60sec /15:20 POST /15:30 watch | Absolute cutoffs, bounded account ownership and parent fairness verified. |
| D04 08:50 preparation | Read-only PRE_OPEN block and unknown refresh verified. |
| D05 strictly before09:20 catch-up | No old backlog/replay; incomplete collection UNKNOWN at deadline verified. |
| D06 recovery first /affected freezes | Exact coherent same-subject nonterminal progression accepted; unknown globally closed;000660 retained. |
| D07 immutable /never-dispatched only | Commit-before-call, consumed unknown attempts and immutable saved inputs verified. |
| D08 daily failure /independently healthy risk | Scoped suppression and collection independence verified; actual success remains distinct from failed risk work. |
| D09 pause daily/BUY; eligible SELL/reconcile | Pending/applied restrictions and healthy scoped risk authority verified. |
| D10 global kill; no cancel/liquidate | Final provider/HTTP admission lock plus bounded entry, immediate accepted restriction verified. |
| D11 fixed CLI/web/phone requests | Attributable server scope/actor/revision/time/CSRF wired; owner reported phone UAT PASS. |
| D12 durable stop /explicit fresh resume | Persistence and advancing-clock successful safety semantics verified. |
| D13 awake owner Mac /honest sleep | Offline lifecycle contract verified; owner reported actual machine lifecycle UAT PASS. |
| D14 owner GUI-login LaunchAgent | Generated launcher and recovery-first wiring verified; owner reported lifecycle UAT PASS. |
| D15 maximum3 restarts/600sec | Durable admission before construction and manual-attention latch verified. |
| D16 saved health /independent observer /30min CRITICAL | Future-source unknown and observer/reminders verified; actual fail-soft negative recovery and success/re-failure incident lifecycle verified. |

Phase09 both approvals remain absent, actual current Codex single-shot support remains unverified/fail closed, and historical000660 freeze remains unchanged. Phase11 held-first/current snapshot and scoped pending suppression are now preserved. Phase14 approved styling is reused; its prior visual/private-access evidence does not substitute for new Phase15 control/device acceptance. REAL remains rejected.

## Anti-patterns and disconfirmation

No TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER or skip/xfail marker was found in the three changed source/test files. Prior independent inventory scan covered69 canonical plan artifact/file paths plus collection source, with no unaudited debt marker or output stub; unchanged source retains that result. Empty/None values represent explicit unknown/disabled/read-only contracts. Fresh machine artifact query passed42/42 declared entries (38 paths). Symbolic PLAN link query still returns1/28 due to component/endpoint strings in from/to; all28 links retain the manual semantic evidence above, rather than treating metadata regexes as runtime proof.

Disconfirmation checks targeted three specific failure modes: outer successful cleanup could hide inner FAILED; arbitrary/stale positive return could fabricate protection; strict result validation could halt otherwise healthy positions merely because000660 is pending. Actual fail-soft incident proof,5 independent audit contradictions/stale-return cases and3 actual scoped nonterminal risk ticks falsified those hypotheses. The old outer-exception test could pass without proving the inner return contract; it is explicitly insufficient on its own. The remaining partial acceptance is actual installed/device/external operation, reported as WARNING/human verification.

No prohibition block is declared across these plans, no override exists, and no judgment or test-tier prohibition has been silently passed. No new source bug was observed. This goal verification is not a separate security/code review.

## Owner-reported human UAT

Four categories harvested from15-12/13/14 plans were presented individually through gsd-verify-work. The owner answered `pass` for each on 2026-10-05; 15-UAT.md records 4 passed, 0 issues, 0 pending. These are owner-reported acceptance results, not checks performed by the verifier. Test4 confirms the stated gating/fail-closed behavior and does not issue the two separate09-08 approvals, create a protected receipt, certify the current Codex transport, activate trading or clear000660.

### 1. Korean desktop and320px phone controls

**Test:** On actual desktop/320px phone, trigger authenticated native PAUSE/RESUME/KILL against temporary saved evidence.
**Expected:** Authenticated native controls clearly distinguish accepted/pending/applied/rejected state, active blocks, timestamps and older in-flight submission, with accessible44px targets and retained mobile details.
**Why human:** Rendered HTML and unchanged responsive tokens do not establish actual appearance or operator usability.

### 2. Actual owner Mac lifecycle and independent observer

**Test:** After separately authorized disabled/offline installation, exercise GUI login/logout/sleep/wake, SIGTERM/unexpected exit, restart exhaustion, observer survival and removal.
**Expected:** After separately authorized disabled/offline installation, GUI login/logout/sleep/wake, SIGTERM/unexpected exit, restart exhaustion and removal preserve recovery-first startup, stops/freeze/audit, honest suspension and maximum3/600; the separate observer survives trading exhaustion.
**Why human:** Generated plist and offline supervision tests cannot prove installed-device lifecycle.

### 3. Actual private Tailscale HTTPS phone access/session

**Test:** After separately authorized private configuration, test owner phone over mobile data, certificate, authentication, session expiry/CSRF and independent sessions.
**Expected:** After separately authorized private configuration, owner phone over mobile data has valid certificate, authentication, CSRF/session expiry and independent sessions; controls preserve fixed actor/scope/revision and truthful saved state.
**Why human:** Private network, certificate and real phone/session behavior require owner devices; no deployment occurred.

### 4. External activation acceptance

**Test:** Review actual both09-08 approvals and linked immutable evidence, protected receipt, supported single-shot provider and current broker safety before any activation.
**Expected:** Both actual09-08 approvals, immutable eligible mock evidence/profile/source identities, linked protected receipt, supported single-shot provider and current broker safety must pass before activation; absent/mismatched proof remains closed and000660 remains frozen until same-subject terminal proof.
**Why human:** Actual authenticated broker/provider evidence and explicit approvals cannot be inferred from synthetic fixtures; current CodexCLI0.144.6 single-shot support remains closed.

The verifier did not obtain actual09-08 approval records, validate the current CodexCLI0.144.6 single-shot transport, perform paid provider acceptance, install/configure owner devices or enable unattended mutation. These facts are not inferred from UAT. 000660 remains frozen pending same-subject determinate terminal broker evidence. Device/lifecycle acceptance is reported by the owner. The same powered-off/sleeping Mac cannot run either local service or observer.

## Deferral and verdict

No implementation gap remains or is deferred. After all four owner-reported UAT passes, gsd-verify-work canonicalizes the previous human_needed report to **passed**. The two device truths are explicitly attributed to owner UAT rather than automated proof. Actual ROADMAP Phase16 remains a separately gated manual real-money pilot; Phase15 acceptance cannot replace Phase09 approvals or any runtime evidence/authority gate.

**Phase15 implementation and conversational UAT acceptance are complete.** The registered shared completion predicate and transition determine final phase/requirement tracking. Fail-closed activation,000660 freeze and all separate Phase16 real-money approvals remain in force.

Independent report validation originally passed with 44 VERIFIED/2 UNCERTAIN and human_needed. The UAT completion update resolves both remaining device truths as owner-reported VERIFIED, retaining46 total truths and four accepted UAT categories. Implementation gaps/regressions remain empty; the completion update is validated by the shared GSD predicate and diff/YAML checks.

---
_Verified: 2026-10-05T03:26:58Z_
_Verifier: independent gsd-verifier agent; no commit_
_Owner UAT accepted: 2026-10-05T05:37:31Z; each of four responses was `pass`. Canonical acceptance update by verify-work; no new runtime authority granted._
