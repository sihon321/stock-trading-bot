---
phase: 15-unattended-scheduling-service-resilience
verified: 2026-10-04T17:48:25Z
status: gaps_found
score: 34/46 must-haves verified
behavior_unverified: 0
overrides_applied: 0
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
gaps:
  - truth: "Daily first-universe capture uses fresh same-account holdings and matching held-position context."
    status: failed
    reason: "G1 BLOCKER: _daily consumes the recovery-time self.fresh holdings; risk reads newer holdings without replacing it. Production collector mixes stale universe membership with latest_snapshot context."
    artifacts:
      - path: trading_bot/service_runtime.py
        issue: "296 and 447-468: initial held list comes from stale self.fresh."
      - path: trading_bot/service_cli.py
        issue: "543-571: held_first_targets and held context use differently dated inputs."
    missing:
      - "Bounded fresh same-account snapshot immediately before first universe capture; release authority before collection/provider."
      - "Use that captured snapshot consistently for holdings and held context; preserve already committed universe/input immutability."
      - "Regression with holdings changed between startup and daily collection."
  - truth: "Daily screen/context/news collection permits independently due held-position protection to progress."
    status: failed
    reason: "G2 BLOCKER: synchronous collect runs in the parent tick before risk; provider-spawn fairness tests bypass this collection interval."
    artifacts:
      - path: trading_bot/service_runtime.py
        issue: "426-438 and 453: synchronous collection delays the same parent risk loop."
      - path: trading_bot/service_cli.py
        issue: "549-570: whole-market screening and per-target context/news lack a parent-loop cooperative boundary."
    missing:
      - "Bounded spawned or cooperative collection for screen/context/news, with parent risk/control/health progress and lease-free collection."
      - "Crash/deadline truth and first captured input/universe identity retained."
      - "Fairness regression covering actual collection rather than only slow provider transport."
  - truth: "Eligible protected production activation succeeds with an advancing real clock while preserving source freshness."
    status: failed
    reason: "G3 BLOCKER: safety callback observes later than the supplied validation time, so observed_at <= now fails and production always returns CURRENT_SAFETY_UNKNOWN."
    artifacts:
      - path: trading_bot/service_cli.py
        issue: "417-423: callback ignores its now argument and reads clock again."
      - path: trading_bot/service_activation.py
        issue: "438-446: validation compares callback observation against earlier now."
    missing:
      - "Consistent observation-start/evaluation-end timestamp semantics with actual source age preserved."
      - "Advancing-clock production-root regression; no arbitrary timestamp backdating to bypass freshness."
  - truth: "Determinate known nonterminal orders suppress affected subjects without stopping independently healthy held protection."
    status: failed
    reason: "G4 BLOCKER: production reconcile requires terminal order proof even for complete same-subject OPEN/PARTIAL, turning ordinary pending orders into account-global recovery blockage."
    artifacts:
      - path: trading_bot/service_cli.py
        issue: "497-510: not matches[0].terminal sets determinate False; subsequent BoundedAccountWork cannot enter healthy work."
    missing:
      - "Accept complete determinate same-subject nonterminal progression for scoped recovery; retain affected-ticker suppression and unresolved terminal freeze."
      - "Keep UNKNOWN/missing/contradictory truth globally fail-closed; regress actual production work and manual CLI equivalence."
  - truth: "Failed risk work remains unhealthy and cannot act as positive stalled-worker recovery."
    status: failed
    reason: "G5 BLOCKER: recent BLOCKED RISK_UNAVAILABLE counts as progress; fresh RUNNING heartbeat projects healthy RUNNING, and AlertDetector clears the existing stall."
    artifacts:
      - path: trading_bot/service_runtime.py
        issue: "444: risk exception saves BLOCKED without changing overall RUNNING phase."
      - path: trading_bot/web_evidence.py
        issue: "667-686: risk reducer ignores blocked job/event state when heartbeat and event time are fresh."
      - path: trading_bot/alert_detector.py
        issue: "49-58: projected RUNNING plus failed progress produces positive RECOVERED facts."
    missing:
      - "Distinguish failed/blocked/unknown work from successful protection/reconciliation progress in saved health and incident recovery."
      - "Attributable blocked source/reason and readiness; no false incident clear on repeated failed ticks."
      - "Actual runtime-reader-detector negative regression for failed progress after an existing stall."
---

# Phase 15: Unattended Scheduling and Service Resilience Verification Report

**Phase goal:** Operators can run calendar-aware daily evaluation and intraday held-position protection unattended, with exactly-once intent, durable recovery, health visibility, and immediate manual stop authority.

**Status: gaps_found. Score: 34/46.** Five reproduced BLOCKER root causes prevent goal achievement. Initial verification; no previous Phase15 report or accepted overrides. The four roadmap success criteria and all 42 canonical plan truths are retained below; overlapping plan details reuse evidence. Two truths require actual device validation. Every other truth has behavioral evidence or a reproduced failure, rather than presence-only acceptance.

## Evidence scope

Read the verifier workflow/references/template, AGENTS, STATE/PROJECT/REQUIREMENTS/ROADMAP, all fourteen canonical plans and summaries, CONTEXT/PATTERNS/relevant RESEARCH, Phase11/14 verification and Phase09 approval checkpoints. Summaries supplied an inventory, not the verdict.

Inspected production composition, account/leader/control/provider authority, scheduler, recovery, immutable input/intent data flow, health/observer, request routes/templates, launch supervision and offline dry-run. No source fixes, tracking edits, authenticated approval collection, production journal access, external calls, installation or deployment were performed.

Reused parent execution evidence: `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` — **1874 passed, 468.61 seconds**, implementation tree `6b4a24c1b48432d532a300f6cf049cd82573eb14`. Verified final HEAD `0c5cc9b1ecc232bb681472bbe5694a50fcd3e1f2` differs only in ROADMAP, STATE and 15-14-SUMMARY; implementation/tests/docs did not change after that pass. This regression evidence does not invalidate the targeted counterexamples below. Parent compileall/schema checks also passed. No separate code review or security audit was performed; their hooks were empty.

## Observable truths

| # / contract | Truth | Verdict | Evidence |
| --- | --- | --- | --- |
| 1 (SC1) | KRX holiday/session rules schedule one daily decision cycle and a separately bounded held-position risk worker. | FAILED — BLOCKER | G1/G2: initial holdings stale and synchronous collection blocks risk. |
| 2 (SC2) | Leader locking, durable job identities, checkpoints, and reconciliation prevent overlapping workers or duplicate order submission after restart. | VERIFIED | ServiceLeader, immutable dispatch/intent checkpoints, final POST admission; named crash proof passed. |
| 3 (SC3) | Health checks detect missed schedules, stalled workers, stale market data, and notification failure; recovery remains fail closed. | FAILED — BLOCKER | G5: BLOCKED risk is shown RUNNING and clears stalled incident. |
| 4 (SC4) | Manual pause, resume, dry-run, and global kill controls work without deleting audit evidence or releasing unresolved-order freezes. | FAILED — BLOCKER | G3: actual advancing clock prevents eligible startup/resume; restrictive controls and dry-run are implemented. |
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
| 31 (15-09.3) | D-06, D-08: recovery precedes mutable work and failed daily evaluation does not stop independently healthy held protection. | FAILED — BLOCKER | G4: determinate OPEN/PARTIAL subjects become account-global RECOVERY_BLOCKED. |
| 32 (15-10.1) | D-01–D-05: 08:50 preparation,09:00 risk/60 seconds,09:10 daily and strict before09:20 catch-up follow positive KRX/session evidence. | FAILED — BLOCKER | G2: actual screen/context/news collection starves due risk passes. |
| 33 (15-10.2) | D-06, D-07: recovery owns account authority before reconciliation/checkpoints; only never-dispatched saved inputs resume and uncertain provider/order work never retries. | VERIFIED | Exclusive recovery before checkpoint mutation; consumed provider/intent never replayed. |
| 34 (15-10.3) | D-08, D-09, D-10, D-12: healthy risk protection continues after daily failure or normal pause, while kill/common safety faults block every new submission. | FAILED — BLOCKER | G4: known nonterminal subject prevents healthy-other-held protection; G2 collection also delays it. |
| 35 (15-11.1) | D-16: web health exposes missed schedules, stalled workers, stale market data and notification failures from attributable saved sources. | FAILED — BLOCKER | G5: saved BLOCKED risk hidden by fresh heartbeat/progress. |
| 36 (15-11.2) | D-09, D-10, D-13: expected-worker health reflects positive session, date, controls and login/service state; same stopped Mac cannot notify during total sleep/outage. | VERIFIED | Independent pre-tick/midnight expectation provenance and negative/UNKNOWN tests. |
| 37 (15-11.3) | D-16: independent observer preserves occurrence/worsening/recovery dedupe, INFO history, delivery UNKNOWN and unacknowledged CRITICAL30-minute reminders. | FAILED — BLOCKER | G5 false positive recovery; partition/outbox/reminder behavior itself passed named test. |
| 38 (15-12.1) | D-11: authenticated CLI/web/phone use fixed pause/resume/kill request authority with actor, time, scope, revision and CSRF. | UNCERTAIN — WARNING | Fixed authenticated request routes proven offline; actual private phone HTTPS/session check pending. |
| 39 (15-12.2) | D-09, D-10, D-12: interface clearly distinguishes pending accepted restriction, applied state, rejected resume and older in-flight submission. | VERIFIED | Native forms show accepted/pending/applied/rejected and in-flight source evidence; route tests. |
| 40 (15-12.3) | D-16: Korean health/control views reuse approved Phase14 responsive design and show saved blocking evidence. | FAILED — BLOCKER | G5 gives false RUNNING saved health; new Korean desktop/320px controls still need visual review. |
| 41 (15-13.1) | D-11, D-12: CLI shares attributable revisioned requests and cannot silently apply resume or reset kill. | VERIFIED | Fixed attributable CLI request facade; no silent applied RESUME/reset. |
| 42 (15-13.2) | D-13, D-14: current Mac starts installed service at owner login through LaunchAgent, recovery-first; sleep/logout suspend availability. | UNCERTAIN — WARNING | LaunchAgent generation is wired and offline-tested; actual installation/login/logout/sleep/wake pending. |
| 43 (15-13.3) | D-15, D-16: durable maximum3 automatic restarts/600 seconds applies before worker construction; separate observer continues after trading restart exhaustion. | VERIFIED | Launcher reserves maximum3/600 before factory; separate observer process/budget and exhaustion tests. |
| 44 (15-14.1) | D-01–D-12: integrated offline crash/race/deadline proofs show single-shot dispatch, exactly-once intent, fresh recovery, fair account work and durable stop authority. | FAILED — BLOCKER | G1–G5 contradict integrated fresh/fair/healthy runtime claims; fixtures missed these production cases. |
| 45 (15-14.2) | D-13–D-16: login supervision/independent health contracts are proven offline, while actual Mac/private-device operation remains manual. | VERIFIED | Offline login/supervision/expectation/capability contracts tested; device operation explicitly manual. |
| 46 (15-14.3) | FUT-04: completed offline implementation is distinct from external Phase9 acceptance and deliberate activation; Phase16 real remains rejected. | VERIFIED | No offline acceptance fabrication; both real approvals absent; current Codex unproven and REAL closed. |

**Score: 34/46 verified; 10 failed truths grouped into five blockers; 2 uncertain device truths; 0 present-but-behavior-unverified truths.** The retained 46-entry denominator deliberately exposes every plan addition instead of allowing fewer plan truths to reduce roadmap scope.

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
| 15-09 | `trading_bot/account_work.py`<br>`trading_bot/cli.py`<br>`tests/test_service_authority.py` | Substantive/wired; G4 production reconciliation prevents healthy progress. |
| 15-10 | `trading_bot/service_schedule.py`<br>`trading_bot/service_runtime.py`<br>`tests/test_service_recovery.py` | Substantive/wired; G1/G2 production daily path breaks goal. |
| 15-11 | `trading_bot/web_evidence.py`<br>`trading_bot/alert_detector.py`<br>`tests/test_service_health.py` | Substantive/wired; G5 health/recovery projection wrong. |
| 15-12 | `trading_bot/web_control.py`<br>`trading_bot/templates/operator/controls.html`<br>`tests/test_web_control_routes.py` | Substantive/wired; G5 displayed health, visual check pending. |
| 15-13 | `trading_bot/service_cli.py`<br>`trading_bot/service_launchd.py`<br>`docs/operator-runbook.md` | Substantive/wired; G3 production eligible path fails. |
| 15-14 | `tests/test_service_acceptance.py`<br>`tests/test_service_dry_run.py`<br>`docs/operator-runbook.md` | Substantive/wired; integrated fixtures omit G1–G5. |

Additional critical production artifacts inspected: `control_runtime.py`, `submission_authority.py`, actual `kis_order_adapter.py` HTTP entry, `portfolio.py` pending-subject suppression, `alert_observer.py` partition handling and `tests/capability_probe.py`.

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
| 15-09 | `BoundedAccountWork.run` → `MutationLease/recover_to_active/release_after_reconciliation` (same-account broker truth before mutation)<br>`daily provider child/wait` → `released account lease` (no authority across LLM or sleep) | WIRED; runtime contract partial (G1–G5 where noted) |
| 15-10 | `ExpectationProducer.publish` → `ExpectationWriter.record_derived` (independent protected enabled/login registration and exact-date authoritative session/control provenance)<br>`ServiceRuntime.recover/start` → `BoundedAccountWork/control/activation` (exclusive fresh recovery before dispatch or POST) | WIRED; runtime contract partial (G1–G5 where noted) |
| 15-11 | `independently derived expectations and separate runtime heartbeats` → `OperatorEvidenceService` (pure owner/version checked read-only DTO projections)<br>`AlertObserver._scan` → `AlertStore/notification_transport` (same existing outbox ownership/dedupe/reminder semantics) | WIRED; runtime contract partial (G1–G5 where noted) |
| 15-12 | `POST /controls/<resource_id>/<action>` → `ControlRequestWriter.append_request` (server actor/time, registered scope and expected revision)<br>`GET /controls/<resource_id>` → `read-only control/service DTOs` (requested versus applied source-linked evidence) | WIRED |
| 15-13 | `bot-service run/launch` → `ServiceLeader/ServiceJournal.reserve_restart` (durable admission before worker recovery/construction)<br>`separate observer LaunchAgent` → `bot-alerts` (independent process/supervision from trading budget) | WIRED; runtime contract partial (G1–G5 where noted) |
| 15-14 | `service_cli.dry-run` → `service_runtime through temporary topology` (same scheduling/recovery reducers, capability-free frozen inputs)<br>`capability_probe fresh interpreter` → `web/control/read-only/service-disabled surfaces` (tripwires before imports and byte-identical source evidence) | WIRED; runtime contract partial (G1–G5 where noted) |

Concrete production binding requires actual `ServiceRuntime`, `AccountTradingBinding`, `BoundedAccountWork`, `OwnedActivationCheck`, `KISBroker` and committed audit. A placeholder callback alone cannot grant authority. Broker preparation precedes the final serialized entry; the actual adapter checks a typed, single-use final entry after preparation. Pending accepted PAUSE/KILL is re-read at provider/POST entry. Admission and stop acceptance share the global lock through bounded POST; no SQL transaction spans external I/O.

## Data-flow trace

| Dynamic artifact | Actual upstream source / behavior | Verdict |
| --- | --- | --- |
| Initial daily universe | Recovery snapshot → `self.fresh.holdings` → collector; risk snapshots do not update it | FAILED G1 |
| Production held context | `held_first_targets(held_tickers, screened)` uses stale held list while context uses latest_snapshot | FAILED G1 |
| Daily inputs | Actual screen → OHLCV/indicators/quote/news → rendered immutable prompt/envelope | Real data wired; synchronous parent collection FAILED G2 |
| Activation | Protected owned receipt/approval/source hashes → current safety → typed activation check | Real gate wired; advancing clock FAILED G3 |
| Account recovery | Current normalized snapshot + primary unresolved submissions → same-subject reconcile | Real facts wired; nonterminal truth FAILED G4 |
| Saved health/control views | Owner/version-checked query-only service/control rows → DTOs → Korean native templates | Real saved data, no hardcoded empty success; risk projection FAILED G5 |
| Observer | Independent expectation source + saved DTO facts → incident/outbox/delivery/reminders | Partition continuity verified; failed-risk positive recovery FAILED G5 |
| Dry-run | Frozen replay fixture → actual runtime/schedule/account-work over temporary owned stores | Verified offline; no activation or device acceptance |

## Reproduced blockers

Each reproduction used only resolved temporary fixture roots and offline collaborators. These are diagnostic commands executed with `PYTHONUSERBASE="$PWD/.python-userbase" python3 -c ...`, not committed tests. Fixtures described as fake owned reads never establish authentic broker/operator acceptance.

### G1 — Initial held-first universe uses startup holdings

**Locations:** `service_runtime.py:296`, `:434-438`, `:447-468`; `service_cli.py:543-571`.

**Minimum reproduction:** construct `tests.test_service_recovery.runtime_fixture` at 09:00; start runtime with holding 005930. Replace its snapshot reader with a fresh complete same-account snapshot holding 000660. Tick risk at 09:00, then tick at 09:10 with a collector spy recording its held_tickers and returning no inputs.

Observed:
```text
startup_holdings=('005930',)
broker_current_holdings=('000660',)
collect_received=[('005930',)]
job_universe='[]'
```

The spy proves the stale caller argument; the production union uses that argument at line554, so a newly held 000660 that does not pass screening is omitted. Its held context also uses a different latest snapshot at560–562. Existing `test_partial_first_input_keeps_000660_in_committed_universe_after_sleep_gap` checks a previously saved universe, not a holdings change before first capture.

**Required closure:** bounded fresh same-account observation immediately before the first capture, with released authority before collector/provider work; capture holdings and held context from the same snapshot. Keep previously committed universe/input immutable. Regression must change holdings after startup and before first daily collection.

### G2 — Screen/context/news collection starves the parent risk loop

**Locations:** `service_runtime.py:426-438,453`; `service_cli.py:549-570`.

**Minimum reproduction:** `runtime_fixture` at09:09; a replacement collector advances the fixture clock 180 seconds before returning. Tick09:09 and then09:10. The collector runs synchronously before risk.

Observed:
```text
risk before collection observed_at=1791158940
next risk observed_at=1791159180, clock=09:13
risk-slot=09:10; no 09:11/09:12 passes
```

This models elapsed collection without sleeping or network. Production performs full screening and up to20 screened targets plus holdings, with per-target context/news work on the same thread. Individual adapter timeouts do not bound the aggregate collection interval or let the parent protect holdings during it.

`test_spawned_slow_provider_allows_risk_account_work_and_kill_acceptance` and provider-child fairness tests use cheap fixture collection; they prove fairness during provider response wait only. They do not exercise the full collection interval.

**Required closure:** bounded spawned/cooperative screen/context/news collection that allows risk, controls and heartbeat progress in the parent, preserves first captured inputs and deadline/crash truth, and holds no account authority while collecting. Test slow collection rather than bypassing it.

### G3 — Real advancing clock denies every otherwise eligible production activation

**Locations:** `service_cli.py:417-423`; `service_activation.py:438-446`.

**Minimum reproduction:** use `tests.test_service_cli.production_fixture` with the same typed fake owned reader/composition/calendar patches as `test_real_composition_root_binds_concrete_account_and_audit`, plus `NoExternalCapabilities`. Replace that test's constant clock with a clock returning base+1 microsecond per call. Build the actual production runtime; invoke its actual activation check and startup.

Observed:
```text
allowed=False
reason_codes=('CURRENT_SAFETY_UNKNOWN',)
clock_calls=3
external_calls=()
start -> RuntimeBlocked CURRENT_ACTIVATION_BLOCKED
```

The check captures now, then safety ignores the supplied now and captures a later observed_at. Validation requires observed_at<=the earlier now. Normal clock progress therefore closes the success path even for otherwise accepted evidence. The existing production-root test patches a constant clock and misses this defect.

**Required closure:** define consistent observation-start/evaluation-end semantics and retain actual source age. Do not backdate source evidence merely to pass the comparison. An advancing-clock production-root regression is mandatory.

### G4 — Known OPEN/PARTIAL order becomes account-global recovery failure

**Locations:** `service_cli.py:497-510`. Manual compatibility: `cli.py:458,2618` accepts determinate non-UNKNOWN current orders; `portfolio.py:318` suppresses only the affected ticker for OPEN/PARTIAL/NO_FILL.

**Minimum reproduction:** actual `production_fixture`/production runtime with constant clock to isolate G3; fake normalized complete same-account snapshot contains `PortfolioOrder('known-open', None, '005930', 'SELL', 1, 0, 1, 0, 0, 70000., 'OPEN', '20261005', '091000')`. Start succeeds. In a real temporary `runtime.work.run` operation append a primary `OrderEvent SUBMISSION_ACCEPTED` bound to the lease cycle, known-open ID and 005930 SELL with one remaining share. No POST occurs. Run a subsequent work operation spy for healthy held protection.

Observed:
```text
release -> LeaseRecoveryBlocked: account reconciliation unresolved
next_work -> LeaseRecoveryBlocked: prior broker subjects remain unresolved
operation_calls=[]
```

The complete same-subject nonterminal result fails `not matches[0].terminal`; it blocks unrelated healthy holdings through global lease recovery. A normally accepted order can stay OPEN/PARTIAL across reads, so this is routine operation, not fabricated external ambiguity.

**Required closure:** distinguish complete determinate nonterminal progression from UNKNOWN/missing/contradictory truth. Keep affected ticker suppressed and same-subject terminal-release requirements intact, but permit independently healthy other holdings to be protected. Test actual production binder cleanup and next-work entry, with manual CLI equivalence. The actual historical000660 ambiguity/freeze must remain untouched.

### G5 — Failed risk tick falsely appears healthy and clears a stall

**Locations:** `service_runtime.py:444`; `web_evidence.py:667-686`; `alert_detector.py:49-58`.

**Minimum reproduction:** `tests.test_service_health.health_fixture`, actual temporary ServiceLeader/ServiceJournal/AlertStore and query-only reader. Advance clock4200 seconds; detect/store the existing WORKER_STALLED incident. Claim dated RISK; append BLOCKED/RISK_UNAVAILABLE and a fresh leader heartbeat with phase RUNNING. Read health, detect and store alert facts.

Observed (independently executed):
```text
saved_job_state='BLOCKED'
health_state='RUNNING'
mutation_ready=None
positive_recovery_families=['WORKER_STALLED','MISSED_SCHEDULE','EXPECTATION_UNKNOWN']
stall_still_active=False
```

This is the actual exception projection in runtime: a failed tick appends recent progress but leaves the generation RUNNING. The reducer ignores blocked risk state; the detector then interprets that failed progress as positive recovery. Repeated failures can keep the worker looking healthy while no successful protection occurs.

A useful negative assertion after this setup is:
```python
assert risk_health.state != 'RUNNING'
assert not any(f.positive_recovery for f in risk_facts)
assert store.get(stall_episode.episode_id).active
```
All three expected contracts are contradicted by the current result. Existing `test_stall_recovery_requires_actual_new_progress_and_same_subject` exercises RUNNING→COMPLETED successful progress; it omits blocked progress.

**Required closure:** preserve failure/blocked/unknown status and source reason in health, separate successful protection/reconciliation evidence from arbitrary recent events, and prohibit failed ticks from clearing incidents. Add repeated-failure runtime/reader/detector regression. Independently proven observer partition/outbox behavior does not fix this upstream false-health input.

## Behavioral spot-checks and probes

All newly run named tests completed in under10 seconds and used offline temporary fixtures. No duplicate whole-suite run.

| Behavior | Independently executed command (pytest node after common prefix) | Result |
| --- | --- | --- |
| Owner check reserves configured POST budget after preparation | `tests/test_service_authority.py::test_final_owner_assertion_reserves_configured_post_budget_after_preparation` | 1 passed,0.43s |
| Hard crash after dispatch commit preserves identity/no replay | `tests/test_service_acceptance.py::test_hard_process_crash_recovers_stable_primary_identity_without_replay[DISPATCH_COMMITTED]` | 1 passed,0.71s |
| Failed source partitions retain owned outbox/CRITICAL reminders without false clear | `tests/test_service_acceptance.py::test_observer_persistent_source_failures_keep_critical_outbox_reminders_and_no_false_clear` | 1 passed,0.22s |
| Actual production root uses concrete account/audit/authority | `tests/test_service_cli.py::test_real_composition_root_binds_concrete_account_and_audit` | 1 passed,0.87s; constant-clock limitation G3 |
| Seven fresh-interpreter read/request/disabled/render/dry-run capability families | `tests/test_web_capabilities.py::test_fresh_service_read_request_setup_render_dry_run_capabilities` | 1 passed,3.80s |

Common command prefix: `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q`.

The capability probe is actual independent probe execution: guards install before imports in seven fresh processes; registered source bytes remain identical. No PLAN-declared or conventional `scripts/*/tests/probe-*.sh` exists for this phase; no missing declared shell probe. The five diagnostic counterexamples above produce the displayed failures despite the full suite passing.

## Requirements coverage

| Requirement | Actual REQUIREMENTS text / contract | Claimed plans | Verdict |
| --- | --- | --- | --- |
| FUT-04 | Operator can schedule unattended cycles only after manual-operation evidence is sufficient. | 01,06,08,13,14 | BLOCKED G3: actual eligible activation success path fails. Both-approval evidence gate itself is implemented and correctly closed while external acceptance is absent. |
| AUTO-01 | Scheduled daily and intraday workers use KRX calendar/session rules, leader locking, durable checkpoints, and idempotent invocation identities so one logical job cannot submit twice. | 01,02,03,04,06,07,08,09,10,14 | BLOCKED G1/G2/G4: fresh first inputs and independently healthy intraday protection fail. Identity/duplicate prevention/session cutoffs are implemented and behaviorally exercised. |
| AUTO-02 | Operator can pause, resume, inspect health, recover after restart, and activate a global kill switch without losing audit or reconciliation evidence. | 01,03,05,08,09,10,11,12,13,14 | BLOCKED G3/G4/G5; actual private-device/lifecycle validation pending. Restrictive controls/audit preservation are implemented. |

No orphaned phase15 requirement: all three mapped IDs are claimed by canonical plans. None may be marked complete merely because14 summaries exist. The table uses the actual REQUIREMENTS text.

## Locked decisions and prior-phase compatibility

| Decision | Verification |
| --- | --- |
| D01 09:10 daily | Stable single dated job/dispatch and frozen envelopes verified; first current holdings G1. |
| D02 09:00 held risk | Scheduler verified; production protection delayed G2 and globally blocked G4. |
| D03 60sec /15:20 POST cutoff /15:30 termination | Absolute cutoffs and terminal→IDLE supervisor continuation verified; actual collection fairness G2. |
| D04 08:50 read-only preparation | PRE_OPEN restriction and source refresh verified. |
| D05 strictly before09:20 never-started catch-up | Exact deadline/no old backlog/no replay verified. |
| D06 recovery first /affected freezes | Fresh scoped recovery and freeze retention exist; determinate nonterminal globally blocks G4. |
| D07 never-dispatched only /immutable inputs | Durable commit-before-call, legacy consumed attempt, uncertain HOLD/UNKNOWN and no retry verified. |
| D08 daily failure retains independently healthy risk | Cheap-input fixture passes; real collection G2 and ordinary pending order G4 violate independence. |
| D09 pause daily/BUY; eligible SELL/reconcile continue | Pending/applied enforcement verified; G4 can prevent otherwise healthy risk. |
| D10 kill every new POST; no cancel/liquidate | Shared final HTTP/provider entry ordering and read-only reconcile retained; verified. |
| D11 fixed CLI/web/phone requests | Server actor/time/scope/revision/CSRF and request-only facades verified; actual phone access pending. |
| D12 durable stop, explicit fresh resume | Persistence verified; successful actual eligible resume blocked by G3. |
| D13 current awake Mac, honest sleep limits | Offline contract verified; actual machine lifecycle pending. |
| D14 owner GUI login LaunchAgent, recovery first | Generated LaunchAgents and offline launcher wiring verified; device check pending/G3 prevents eligible active start. |
| D15 maximum3 automatic restarts/600sec | Durable admission before worker construction and attention latch verified. |
| D16 saved health /independent alerts /dedupe /30min CRITICAL | Expectation absent-run/midnight and partition delivery/reminders verified; failed-risk health/positive recovery G5. |

Phase09 approvals and historical000660 freeze are preserved. Phase11 held-first fresh account truth and per-subject pending-order suppression are not fully preserved by the production scheduler (G1/G4). Phase14 read-only owner/schema/capability isolation remains implemented; new saved health is incorrectly interpreted (G5), and added Korean controls require their own visual acceptance.

## Anti-pattern scan

No unreferenced TBD/FIXME/XXX debt markers or TODO/HACK/PLACEHOLDER stubs found in the67 phase inventory paths scanned. Empty/None values inspected represent unknown/disabled/read-only capability states rather than hardcoded success. The five blockers are substantive wiring/ordering/projection defects, not grep-detected placeholders. Symbolic PLAN link metadata should be corrected for future machine-query precision; it is not a substitute runtime fix.

## Human verification required

These items were harvested from15-12/13/14 plans and deduplicated with verification findings. They remain pending even after code blockers close.

1. **Korean desktop and320px phone controls.** Trigger authenticated native PAUSE/RESUME/KILL on temporary saved evidence. Expected: understandable accepted-versus-applied, rejected resume, active blocks, timestamps and older in-flight submission; accessible44px targets and retained mobile details. Actual visual/usability judgment is required; rendered HTML assertions do not complete it.
2. **Actual owner Mac lifecycle and independent observer.** After separately authorized installation in disabled/offline mode, check GUI login/logout, sleep/wake, SIGTERM/unexpected exit, restart exhaustion, observer survival and removal. Expected: recovery first, persisted stops/freeze/audit, honest suspension/absence, maximum3/600 and observer independence. Generated plist/offline proofs do not establish installed-device behavior.
3. **Actual private Tailscale HTTPS phone access/session.** After explicit private-network configuration, test owner phone over mobile data, certificate, authentication, CSRF/session expiry and independent sessions. Expected: private authenticated fixed controls with truthful saved state. No network/device deployment was performed in this verification.
4. **External activation acceptance.** Review actual both09-08 approval records, immutable eligible mock evidence/profile/source identities, linked protected receipt and current broker safety before activation. Expected: absent/mismatched evidence remains closed; no frozen subject is cleared by readiness. Actual authenticated broker/provider acceptance cannot be inferred from fake owned fixtures. Installed Codex0.144.6 single-shot support remains unproven and fails closed; an authorized supported provider and actual current account evidence are required.

Missing external acceptance is intentionally closed authority, not a sixth implementation blocker. Human or offline fixtures cannot fabricate it. No Phase16 real-money authority is granted.

## Deferral and verdict

None of G1–G5 is deferred: Phase16 explicitly concerns a gated real-money manual pilot and requires Phase15 resilience verification upstream. The roadmap query parser omitted later phase sections, so this comparison used the actual ROADMAP Phase16 text rather than claiming query coverage.

The implementation contains substantial safety, identity, audit and capability controls, but task completion does not establish unattended goal achievement. Close all five source defects with regressions covering the actual production paths, then perform fresh verification. Device/acceptance items remain separately pending. **Do not proceed to Phase16 based on this report.**

---
_Verified: 2026-10-04T17:48:25Z_  
_Verifier: independent gsd-verifier agent; no commit_
