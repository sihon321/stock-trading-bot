---
phase: 15-unattended-scheduling-service-resilience
verified: 2026-10-05T02:55:56Z
status: gaps_found
score: 39/46 must-haves verified
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 34/46
  previous_report_commit: d7460e5
  gaps_closed:
    - "G1: fresh same-account first collection snapshot and consistent held context."
    - "G2: bounded actual production screen/context/news collection with parent fairness and durable UNKNOWN recovery."
    - "G3: observation-start/evaluation-end activation preserves advancing-clock freshness."
    - "G4: coherent same-subject OPEN/PARTIAL/NO_FILL recovery permits healthy scoped work without freeze release."
    - "Additional future-control provenance: CONTROL_UNKNOWN does not rewrite future source time or halt independent observer reminders."
  gaps_remaining:
    - "G5: actual failed intraday result is saved as successful RISK_PROTECTED and clears stalled-worker incidents."
  regressions:
    - "Truth 45 previously accepted offline health coverage is reclassified FAILED after exercising the omitted actual fail-soft result path."
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
  - truth: "Failed risk work remains unhealthy and cannot act as positive stalled-worker recovery."
    status: failed
    reason: "G5 BLOCKER remains: AccountTradingBinding.risk returns a fail-soft IntradayIterationResult with outcome FAILED; ServiceRuntime.tick discards it and records RUNNING/RISK_PROTECTED. The saved health reader trusts that success marker and AlertDetector/AlertStore positively recover the existing WORKER_STALLED incident."
    artifacts:
      - path: trading_bot/service_runtime.py
        issue: "197-213 returns the actual typed intraday outcome; 453-461 discards it and records unconditional successful risk progress."
      - path: trading_bot/intraday.py
        issue: "400-416 catches ordinary adapter errors, audits FAILED/ITERATION_FAILED and returns instead of throwing; the caller must inspect this outcome."
      - path: trading_bot/web_evidence.py
        issue: "652-653 derives last_progress_at from the falsely successful event; 677-692 cannot recover the omitted failed watch outcome."
      - path: trading_bot/alert_detector.py
        issue: "50-59 treats the falsely projected RUNNING progress as positive incident recovery."
      - path: tests/test_service_acceptance.py
        issue: "The failed-risk corrective test raises from work.run rather than returning failure from the actual intraday binding, leaving this path untested."
    missing:
      - "Inspect the actual protection result and record FAILED/BLOCKED/INTERRUPTED or other non-success outcomes with attributable source/reason rather than successful progress."
      - "Only actual successful protection or explicit completed reconciliation may establish positive progress; preserve D8 healthy-other-subject protection when a pending/frozen subject alone is suppressed."
      - "Actual production binding/runtime-reader-detector-AlertStore regression for ordinary quote failure, repeated fail-soft outcomes, real successful recovery, and renewed failure."
---

# Phase 15: Unattended Scheduling and Service Resilience Verification Report

**Phase goal:** Operators can run calendar-aware daily evaluation and intraday held-position protection unattended, with exactly-once intent, durable recovery, health visibility, and immediate manual stop authority.

**Status: gaps_found. Score: 39/46.** One reproduced BLOCKER remains, affecting five truths. G1–G4 and the additional future-control observer defect are closed by actual source wiring and independently passing behavioral checks. Two truths remain UNCERTAIN pending device checks. No overrides were requested or applied. The initial audit remains available at commit `d7460e5`.

## Evidence scope and provenance

Re-verification followed the typed verifier workflow/references/template, project instructions, STATE/PROJECT/REQUIREMENTS/ROADMAP, fourteen canonical plans and summary inventories, CONTEXT/PATTERNS/relevant RESEARCH, Phase09 acceptance checkpoints and applicable Phase11/14 guarantees. PLAN-CHECK files were treated as reports, not additional plans. Summaries supplied inventory and candidate claims; actual source and behavior determine this verdict.

The production composition, account/leader/control/provider authority, spawned market collection, scheduler/recovery, canonical input and intent flow, independent expectation/observer, saved query-only health, routes/templates and launcher were traced. All new execution used resolved temporary stores and injected offline adapters. No live KIS/LLM/Discord, production store reads or migrations, deployment, actual launchctl or approval capture occurred. Only this report was edited; no source fix or commit was made.

Reused the supplied final complete regression: `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` — **1894 passed in 487.94s**, implementation `c5ad0d1f16aec666b38d85e29ff58cf59bf8fd4e`. Independently confirmed HEAD `05fe6d4` differs only in STATE and 15-14-SUMMARY after that pass. The earlier `cc57bd5` run was **1891 passed, 2 failed**, and is not cited as a pass. Parent compile/diff checks passed; schema-drift block=false and schema files=[] were supplied. Code-review/security execute:post and verify:post hooks were empty; no separate audit was performed.

## Observable truths

| # / contract | Truth | Verdict | Evidence |
| --- | --- | --- | --- |
| 1 (SC1) | KRX holiday/session rules schedule one daily decision cycle and a separately bounded held-position risk worker. | VERIFIED | Fresh bounded same-account capture immediately precedes first spawned collection; actual screen/context/news fairness checks passed. |
| 2 (SC2) | Leader locking, durable job identities, checkpoints, and reconciliation prevent overlapping workers or duplicate order submission after restart. | VERIFIED | ServiceLeader, immutable dispatch/intent checkpoints, final POST admission; named crash proof passed. |
| 3 (SC3) | Health checks detect missed schedules, stalled workers, stale market data, and notification failure; recovery remains fail closed. | FAILED — BLOCKER | G5 remains: actual IntradayIterationResult FAILED is discarded and saved as RISK_PROTECTED, falsely recovering a stall. |
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
| 34 (15-10.3) | D-08, D-09, D-10, D-12: healthy risk protection continues after daily failure or normal pause, while kill/common safety faults block every new submission. | VERIFIED | Production scoped determinate pending-order recovery passed; normal pause retains eligible held-risk work. G5 separately falsifies success reporting. |
| 35 (15-11.1) | D-16: web health exposes missed schedules, stalled workers, stale market data and notification failures from attributable saved sources. | FAILED — BLOCKER | G5 remains: actual failed watch produces saved RUNNING health and positive progress. |
| 36 (15-11.2) | D-09, D-10, D-13: expected-worker health reflects positive session, date, controls and login/service state; same stopped Mac cannot notify during total sleep/outage. | VERIFIED | Independent pre-tick/midnight expectation provenance and negative/UNKNOWN tests. |
| 37 (15-11.3) | D-16: independent observer preserves occurrence/worsening/recovery dedupe, INFO history, delivery UNKNOWN and unacknowledged CRITICAL30-minute reminders. | FAILED — BLOCKER | G5 remains: actual runtime → query-only reader → detector → AlertStore clears the existing stall after failed protection. |
| 38 (15-12.1) | D-11: authenticated CLI/web/phone use fixed pause/resume/kill request authority with actor, time, scope, revision and CSRF. | UNCERTAIN — WARNING | Fixed authenticated request routes proven offline; actual private phone HTTPS/session check pending. |
| 39 (15-12.2) | D-09, D-10, D-12: interface clearly distinguishes pending accepted restriction, applied state, rejected resume and older in-flight submission. | VERIFIED | Native forms show accepted/pending/applied/rejected and in-flight source evidence; route tests. |
| 40 (15-12.3) | D-16: Korean health/control views reuse approved Phase14 responsive design and show saved blocking evidence. | FAILED — BLOCKER | G5 supplies false healthy saved state to Korean views; desktop/320px visual judgment also remains pending. |
| 41 (15-13.1) | D-11, D-12: CLI shares attributable revisioned requests and cannot silently apply resume or reset kill. | VERIFIED | Fixed attributable CLI request facade; no silent applied RESUME/reset. |
| 42 (15-13.2) | D-13, D-14: current Mac starts installed service at owner login through LaunchAgent, recovery-first; sleep/logout suspend availability. | UNCERTAIN — WARNING | LaunchAgent generation is wired and offline-tested; actual installation/login/logout/sleep/wake pending. |
| 43 (15-13.3) | D-15, D-16: durable maximum3 automatic restarts/600 seconds applies before worker construction; separate observer continues after trading restart exhaustion. | VERIFIED | Launcher reserves maximum3/600 before factory; separate observer process/budget and exhaustion tests. |
| 44 (15-14.1) | D-01–D-12: integrated offline crash/race/deadline proofs show single-shot dispatch, exactly-once intent, fresh recovery, fair account work and durable stop authority. | VERIFIED | Actual production fresh snapshot, spawned collection, advancing clock, determinate order, authority budget and dispatch-crash negative checks passed. |
| 45 (15-14.2) | D-13–D-16: login supervision/independent health contracts are proven offline, while actual Mac/private-device operation remains manual. | FAILED — BLOCKER | G5 falsifies the independent health contract despite passing offline supervision/expectation plumbing; actual devices remain manual. |
| 46 (15-14.3) | FUT-04: completed offline implementation is distinct from external Phase9 acceptance and deliberate activation; Phase16 real remains rejected. | VERIFIED | No offline acceptance fabrication; both real approvals absent; current Codex unproven and REAL closed. |

**Score: 39/46 verified; five failed truths grouped into one blocker; two uncertain device truths; zero present-but-behavior-unverified truths.** Failed behavior is reproduced, rather than routed as uncertainty. The 46-entry denominator retains all four roadmap criteria and 42 canonical plan truths.

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
| 15-10 | `trading_bot/service_schedule.py`<br>`trading_bot/service_runtime.py`<br>`tests/test_service_recovery.py` | Exists, substantive, wired; fresh snapshot and spawned collection verified. Returned risk outcome remains mishandled (G5). |
| 15-11 | `trading_bot/web_evidence.py`<br>`trading_bot/alert_detector.py`<br>`tests/test_service_health.py` | Exists, substantive, wired; saved failure projection fixed, but runtime fabricates upstream successful risk evidence (G5). |
| 15-12 | `trading_bot/web_control.py`<br>`trading_bot/templates/operator/controls.html`<br>`tests/test_web_control_routes.py` | Substantive/wired; G5 displayed health, visual check pending. |
| 15-13 | `trading_bot/service_cli.py`<br>`trading_bot/service_launchd.py`<br>`docs/operator-runbook.md` | Exists, substantive, wired; advancing-clock production activation and future-control observer checks passed. |
| 15-14 | `tests/test_service_acceptance.py`<br>`tests/test_service_dry_run.py`<br>`docs/operator-runbook.md` | Exists, substantive, wired; corrective coverage G1–G4 passed. G5 test throws outside the actual fail-soft worker. |

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
| 15-09 | `BoundedAccountWork.run` → `MutationLease/recover_to_active/release_after_reconciliation` (same-account broker truth before mutation)<br>`daily provider child/wait` → `released account lease` (no authority across LLM or sleep) | WIRED; semantic risk-success contract fails where G5 applies |
| 15-10 | `ExpectationProducer.publish` → `ExpectationWriter.record_derived` (independent protected enabled/login registration and exact-date authoritative session/control provenance)<br>`ServiceRuntime.recover/start` → `BoundedAccountWork/control/activation` (exclusive fresh recovery before dispatch or POST) | WIRED; semantic risk-success contract fails where G5 applies |
| 15-11 | `independently derived expectations and separate runtime heartbeats` → `OperatorEvidenceService` (pure owner/version checked read-only DTO projections)<br>`AlertObserver._scan` → `AlertStore/notification_transport` (same existing outbox ownership/dedupe/reminder semantics) | WIRED; semantic risk-success contract fails where G5 applies |
| 15-12 | `POST /controls/<resource_id>/<action>` → `ControlRequestWriter.append_request` (server actor/time, registered scope and expected revision)<br>`GET /controls/<resource_id>` → `read-only control/service DTOs` (requested versus applied source-linked evidence) | WIRED |
| 15-13 | `bot-service run/launch` → `ServiceLeader/ServiceJournal.reserve_restart` (durable admission before worker recovery/construction)<br>`separate observer LaunchAgent` → `bot-alerts` (independent process/supervision from trading budget) | WIRED; semantic risk-success contract fails where G5 applies |
| 15-14 | `service_cli.dry-run` → `service_runtime through temporary topology` (same scheduling/recovery reducers, capability-free frozen inputs)<br>`capability_probe fresh interpreter` → `web/control/read-only/service-disabled surfaces` (tripwires before imports and byte-identical source evidence) | WIRED; semantic risk-success contract fails where G5 applies |

Concrete production binding requires actual `ServiceRuntime`, `AccountTradingBinding`, `BoundedAccountWork`, `OwnedActivationCheck`, `KISBroker` and committed audit. A placeholder callback alone cannot grant authority. Broker preparation precedes the final serialized entry; the actual adapter checks a typed, single-use final entry after preparation. Pending accepted PAUSE/KILL is re-read at provider/POST entry. Admission and stop acceptance share the global lock through bounded POST; no SQL transaction spans external I/O.


An additional semantic link is **FAILED**: `AccountTradingBinding.risk → IntradayIterationResult → ServiceRuntime.tick → attributable successful ServiceJournal progress`. Invocation is wired, but the returned outcome is discarded. All subsequent observer wiring therefore consumes a false success fact. Symbolic PLAN metadata cannot certify this behavioral contract.

## Data-flow trace

| Dynamic artifact | Actual upstream source / behavior | Verdict |
| --- | --- | --- |
| First daily universe and held context | Fresh BoundedAccountWork operation snapshot captured immediately before collection; released lease; same frozen snapshot sent to child and held context | VERIFIED G1 |
| Production market inputs | Actual MarketDataSource screen/context/news in spawned ProductionInputSource; bounded atomic result; parent validates captured identity, prompt identity, canonical envelopes and duplicate/universe limits | VERIFIED G2 |
| Completed/recovered daily inputs | Durable INPUT_COLLECTION_STARTED before spawn; cutoff/crash/incomplete successor UNKNOWN; saved first universe/envelopes are immutable and never silently recollected | VERIFIED G2 |
| Activation safety | Owned immutable approval/receipt proof plus typed ObservedSafetyReader with supplied observation start and trusted evaluation end, source age and at-most10s TTL | VERIFIED G3 |
| Same-account recovery | Current normalized snapshot plus exact coherent order ID/ticker/side/quantity; determinate OPEN/PARTIAL/NO_FILL retains scoped pending suppression and freeze | VERIFIED G4 |
| Independent expectations | Protected registration + exact-date session + validated controls; future source emits CONTROL_UNKNOWN without committing invalid control timestamp | VERIFIED |
| Saved risk health | Actual watch FAILED/ITERATION_FAILED → unconditional RUNNING/RISK_PROTECTED → last_progress_at → health RUNNING | FAILED G5 |
| Observer incidents | False RUNNING progress → positive recovery facts → actual AlertStore clears existing stall | FAILED G5 |
| Request/control views | Query-only owner/schema checked service/control rows → DTO → Korean native templates, with attributable pending/applied/rejected state | Real data wired; false upstream risk evidence G5 |
| Dry-run | Frozen temporary topology through actual reducers; external capability tripwires installed before imports | VERIFIED offline only |

## Correction re-verification

**G1 closed.** `ServiceRuntime._daily` performs the fresh same-account read through bounded account work before the first collection and releases authority before spawning. The same captured operation snapshot drives held-first membership and held context; cleanup reads cannot substitute a later snapshot. Production collection tests verify captured quantity7 remains in committed prompt despite later quantity11. Existing committed universe/prompt/hash survive recovery unchanged.

**G2 closed.** Actual production composition constructs `ProductionInputSource` and spawn-safe `collection_child` in `service_collection.py`; screen/context/news are inside that child. The child receives allowlisted collection settings, quote-only mock settings, public prompt identity and frozen snapshot, with no account ID/database/owner paths, mutation lease, leader or provider authority. Source and tests check forbidden constructor/network/SQLite tripwires, no inherited account FD, strict bounded JSON, O_EXCL0600 atomic output, and canonical/provenance validation. The parent polls risk/control/heartbeat during each real collection stage. Durable start precedes process launch;90s/09:20/session cutoff/stop/crash/incomplete recovery become UNKNOWN rather than recollection. The independently executed screen/context/news and crash/cutoff cases passed.

**G3 closed.** `ObservedSafetyReader` uses the supplied observation-start timestamp and the trusted current evaluation-end clock. Validation preserves actual age, rejects future/stale/unknown or over10s observation windows, and keeps owned source/proof requirements. The advancing-clock actual production test passed, including negative slow/untrusted-source cases in its coverage; no timestamp backdating is used.

**G4 closed.** Actual production reconciliation accepts exact coherent same-subject OPEN/PARTIAL/NO_FILL proof while retaining the unresolved subject and affected-ticker suppression. Missing, UNKNOWN, contradictory, duplicate or wrong-subject truth remains closed. Terminal freeze release is never inferred from nonterminal proof. Actual production named OPEN/PARTIAL/NO_FILL tests and a contradictory quantity negative test passed; historical000660 remains frozen. This closure does not require healthy other subjects to fail merely because one subject is scoped out.

**Additional future-control observer defect closed.** `ExpectationProducer.publish` validates candidate control time before assigning committed control timestamp/state. Actual future source becomes CONTROL_UNKNOWN without rewriting/backdating source bytes; observer/outbox CRITICAL reminders continue. The deterministic launchd future-control test passed.

**G5 only partially closed.** Latest saved BLOCKED/FAILED/UNKNOWN/reserved/account-busy events now dominate heartbeat or older success in the reader. That repair works when an exception escapes account work. The actual intraday worker catches ordinary errors and returns a typed FAILED result; this result is still recorded as success by the runtime. Its returned outcome, rather than absence of a thrown exception, must decide health progress.

## Remaining reproduced BLOCKER: actual fail-soft protection is reported as success

**Locations:** `service_runtime.py:197–213,453–461`; `intraday.py:400–416`; `web_evidence.py:652–653,677–692`; `alert_detector.py:50–59`.

The actual binding returns `run_intraday_check(...)`. A normal quote adapter error is caught inside that function and produces an audited `IntradayIterationResult(outcome=FAILED, phase=STOPPING, reason=ITERATION_FAILED)`. `ServiceRuntime.tick` ignores the returned value from `work.run(risk)`, updates the slot and writes RUNNING/RISK_PROTECTED. The query-only reader treats that marker as successful progress. The detector emits RECOVERED and the actual AlertStore clears the stall.

**Independently executed reproduction:** resolved TemporaryDirectory; actual production root from `tests.test_service_cli.production_root` with owned offline reads/transport under NoExternalCapabilities; deterministic fixture-only ControlStore initialization clock NOW−1hour (the fixed fixture NOW must not consume actual wall-clock future controls); actual service scope and positive independent expectation fixtures; actual query-only OperatorEvidenceService, AlertDetector and temporary AlertStore. Start runtime; observe/store WORKER_STALLED at09:05; replace only the production binding's quote_reader with an ordinary RuntimeError; tick actual runtime; inspect saved watch, service event, DTO, detected facts and saved episode.

```text
watch_terminal_status FAILED
service_event RISK_PROTECTED
risk_health RUNNING
progress 2026-10-05 00:05:00+00:00
mutation_ready None
positive_recovery ['WORKER_STALLED', 'MISSED_SCHEDULE', 'EXPECTATION_UNKNOWN']
original_stall_active False
```

No provider call or order submission is required. The failure arises through the actual intraday/bounded-account path, with an ordinary data read error and valid account recovery. It is not a reader-only synthetic failure.

The expected negative assertions are contradicted:

```python
assert risk_health.state != "RUNNING"
assert not any(f.positive_recovery for f in risk_facts)
assert store.get(stall_episode.episode_id).active
```

`test_failed_actual_risk_ticks_preserve_stall_until_successful_attributed_progress` passed independently, but raises from `runtime.work.run`. It bypasses the actual fail-soft `AccountTradingBinding.risk → run_intraday_check` return and therefore does not prove this invariant. Existing collection fairness RISK_PROTECTED markers also do not establish watch success.

**Required closure:** interpret the returned typed protection outcome and save non-success with attributable watch/result source/reason. Only actual successful protection or explicit successful reconciliation may create positive progress. Check the available COMPLETED/BLOCKED/FAILED/INTERRUPTED outcomes and their phase/subject meaning; retain healthy-other-subject protection under D8 scoped suppression. Add actual runtime → reader → detector → AlertStore regression for repeated ordinary quote failure, successful protection recovery, and renewed failure.

## Behavioral spot-checks and probe execution

Common prefix: `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q`. Each independently executed named case used temporary offline evidence and completed in under10 seconds. No full-suite duplicate was run.

| Behavior / node | Result |
| --- | --- |
| `tests/test_service_cli.py::test_production_safety_uses_observation_start_and_evaluation_end` | 1 passed,0.96s |
| Actual production collection stage fairness: named parametrized screen, context and news cases in `tests/test_service_cli.py` | Each passed;2.27s,2.74s,2.74s |
| `tests/test_service_cli.py::test_production_collection_expiry_and_recovery_never_recollect_first_inputs[before_spawn]` | 1 passed,1.62s |
| Same collection recovery case `[cutoff]` | 1 passed,2.70s |
| Actual production determinate order reconciliation named OPEN−0, PARTIAL−1, NO_FILL−0 cases | Each passed;1.09s,1.19s,1.21s |
| `tests/test_service_cli.py::test_production_unknown_or_contradictory_order_truth_blocks_account[quantity]` | 1 passed,1.35s |
| `tests/test_service_acceptance.py::test_failed_actual_risk_ticks_preserve_stall_until_successful_attributed_progress` | 1 passed,0.53s; outer thrown failure only, insufficient for actual returned failure |
| Deterministic launchd future-control provenance/observer continuity named case | 1 passed,0.86s |
| `tests/test_service_authority.py::test_final_owner_assertion_reserves_configured_post_budget_after_preparation` | 1 passed,0.65s |
| `tests/test_service_acceptance.py::test_hard_process_crash_recovers_stable_primary_identity_without_replay[DISPATCH_COMMITTED]` | 1 passed,1.07s |
| `tests/test_web_capabilities.py::test_fresh_service_read_request_setup_render_dry_run_capabilities` | 1 passed,4.70s |
| Actual production fail-soft quote error → saved watch → health → alert episode diagnostic | Reproduced FAILED watch falsely reported RUNNING and cleared stall: FAIL |

The capability check independently launches seven fresh interpreters with guards installed before imports and checks registered source bytes. No phase-declared/conventional shell probe is missing. Existing full regression is useful coverage but does not invalidate the production-path counterexample.

## Requirements coverage

| Requirement | Contract | Canonical claimed plans | Verdict |
| --- | --- | --- | --- |
| FUT-04 | Operator can schedule unattended cycles only after manual-operation evidence is sufficient. | 01,06,08,13,14 | Automated gate VERIFIED: both exact09-08 approvals and immutable owned proof required; current absence fails closed. Actual acceptance remains manual, not granted by fixtures. |
| AUTO-01 | Scheduled daily and intraday workers use KRX calendar/session rules, leader locking, durable checkpoints, and idempotent invocation identities so one logical job cannot submit twice. | 01,02,03,04,06,07,08,09,10,14 | VERIFIED automated contract after G1–G4 closure: current collection, calendar/deadlines, recovery and no-replay proofs. Device deployment remains pending. |
| AUTO-02 | Operator can pause, resume, inspect health, recover after restart, and activate a global kill switch without losing audit or reconciliation evidence. | 01,03,05,08,09,10,11,12,13,14 | BLOCKED G5: failed actual protection reports healthy and clears incident. Fixed stop/audit/recovery authority remains implemented; actual private-device checks pending. |

No mapped phase15 requirement is orphaned. No requirement or phase completion tracking was changed.

## Locked decisions and prior-phase compatibility

| Decision | Verification |
| --- | --- |
| D01 09:10 daily | Stable dated job, fresh first held snapshot and immutable dispatch verified. |
| D02 09:00 held risk | Bounded independently polled actual production collection verified; failed protection health G5 remains. |
| D03 60sec /15:20 POST /15:30 watch | Absolute cutoffs, bounded account ownership and parent fairness verified. |
| D04 08:50 preparation | Read-only PRE_OPEN block and unknown refresh verified. |
| D05 strictly before09:20 catch-up | No old backlog/replay; incomplete collection UNKNOWN at deadline verified. |
| D06 recovery first /affected freezes | Exact coherent same-subject nonterminal progression accepted; unknown globally closed;000660 retained. |
| D07 immutable /never-dispatched only | Commit-before-call, consumed unknown attempts and immutable saved inputs verified. |
| D08 daily failure /independently healthy risk | Scoped suppression and collection independence verified; G5 still fabricates health after actual risk failure. |
| D09 pause daily/BUY; eligible SELL/reconcile | Pending/applied restrictions and healthy scoped risk authority verified. |
| D10 global kill; no cancel/liquidate | Final provider/HTTP admission lock plus bounded entry, immediate accepted restriction verified. |
| D11 fixed CLI/web/phone requests | Attributable server scope/actor/revision/time/CSRF wired; actual phone pending. |
| D12 durable stop /explicit fresh resume | Persistence and advancing-clock successful safety semantics verified. |
| D13 awake owner Mac /honest sleep | Offline lifecycle contract only; actual machine check pending. |
| D14 owner GUI-login LaunchAgent | Generated launcher and recovery-first wiring verified; actual installation pending. |
| D15 maximum3 restarts/600sec | Durable admission before construction and manual-attention latch verified. |
| D16 saved health /independent observer /30min CRITICAL | Future-source unknown and observer/reminders verified; actual failed-risk positive recovery remains BLOCKER G5. |

Phase09 both approvals remain absent, actual current Codex single-shot support remains unverified/fail closed, and historical000660 freeze remains unchanged. Phase11 held-first/current snapshot and scoped pending suppression are now preserved. Phase14 approved styling is reused; its prior visual/private-access evidence does not substitute for new Phase15 control/device acceptance. REAL remains rejected.

## Anti-patterns and test limitations

No unreferenced TBD/FIXME/XXX debt marker or TODO/HACK/PLACEHOLDER stub was found in the69 canonical plan artifact/file paths plus new collection source scanned. Empty/None values examined represent unknown/disabled/read-only capabilities, not hardcoded success. All42 declared artifact entries (38 unique paths) passed query existence/substance; all28 symbolic links were traced semantically. No skip/disabled test marker was found in that inventory. The blocker is substantive result handling, not a placeholder.

The failed-risk test boundary must include the actual returned worker outcome. A passed test that injects a thrown outer exception cannot prove a fail-soft inner transition. No separate code-review/security report is implied by these scans.

## Human verification required


These items were harvested from15-12/13/14 plans and deduplicated with verification findings. They remain pending even after code blockers close.

1. **Korean desktop and320px phone controls.** Trigger authenticated native PAUSE/RESUME/KILL on temporary saved evidence. Expected: understandable accepted-versus-applied, rejected resume, active blocks, timestamps and older in-flight submission; accessible44px targets and retained mobile details. Actual visual/usability judgment is required; rendered HTML assertions do not complete it.
2. **Actual owner Mac lifecycle and independent observer.** After separately authorized installation in disabled/offline mode, check GUI login/logout, sleep/wake, SIGTERM/unexpected exit, restart exhaustion, observer survival and removal. Expected: recovery first, persisted stops/freeze/audit, honest suspension/absence, maximum3/600 and observer independence. Generated plist/offline proofs do not establish installed-device behavior.
3. **Actual private Tailscale HTTPS phone access/session.** After explicit private-network configuration, test owner phone over mobile data, certificate, authentication, CSRF/session expiry and independent sessions. Expected: private authenticated fixed controls with truthful saved state. No network/device deployment was performed in this verification.
4. **External activation acceptance.** Review actual both09-08 approval records, immutable eligible mock evidence/profile/source identities, linked protected receipt and current broker safety before activation. Expected: absent/mismatched evidence remains closed; no frozen subject is cleared by readiness. Actual authenticated broker/provider acceptance cannot be inferred from fake owned fixtures. Installed Codex0.144.6 single-shot support remains unproven and fails closed; an authorized supported provider and actual current account evidence are required.

Missing external acceptance is intentionally closed authority, not a sixth implementation blocker. Human or offline fixtures cannot fabricate it. No Phase16 real-money authority is granted.


## Deferral and verdict

No remaining gap is deferred. Actual ROADMAP Phase16 is a gated manual real-money pilot dependent on Phase15 resilience; it does not own correction of false protection health. The roadmap query parser omits later sections, so the comparison uses the actual markdown.

Close G5 with actual returned-outcome regression and re-verify before proceeding. Four pending human/device/acceptance categories remain even after code closure. **Phase15 goal is not achieved and Phase16 must not proceed based on this report.**

---
_Verified: 2026-10-05T02:55:56Z_
_Verifier: independent gsd-verifier agent; no commit_
