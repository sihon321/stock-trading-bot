## ISSUES FOUND

Phase 15 — Unattended Scheduling & Service Resilience. Standard independent pre-execution review: **14 plans, 28 tasks, 9 waves; 4 BLOCKERs, 1 WARNING**.

Read all plans, CONTEXT/RESEARCH/PATTERNS/VALIDATION, roadmap/requirements/project, AGENTS.md and project skill indexes. Source grounding was limited to existing dispatch, mutation lease, final POST and alert contracts. No implementation/runtime tests, service operations, live calls, production DB queries, installation or commits were performed.

| Coverage | Result |
|---|---|
| FUT-04 | Claimed and executable receipt/composition/final-admission tasks in 01/06/08/10/13/14 |
| AUTO-01 | Claimed throughout session/job/dispatch/account-work/recovery plans; dispatch gap below prevents approval |
| AUTO-02 | Claimed throughout controls/health/web/CLI plans; observer gaps below prevent approval |
| D-01…D-16 | Every locked decision has substantive tasks; D-05/D-07/D-09/D-16 remain incomplete at the identified seams |

All 14 `verify.plan-structure` results are valid. All `must_haves` parse (42 truths, 42 artifacts, 28 links). Dependencies exist, are acyclic, and each wave equals maximum dependency wave + 1; same-wave changed-file sets are disjoint. Each plan has two tasks and 3–9 files. Architectural tiers, saved schema migration companions, immutable envelopes, all provider retry layers, final POST controls, manual-path guard propagation, per-pass leases, restart accounting, receipt provenance, real-mode rejection and external-gate separation are explicitly addressed. No deferred deployment/promotion work is included. No contradictory factual/count claims or suppressed-error verification commands were found.

Nyquist: VALIDATION exists; **28/28 tasks have nonempty automated commands**, each with its own or an earlier test producer. Per-wave sampling is 2/2, 8/8, 4/4, 2/2, 2/2, 2/2, 4/4, 2/2, 2/2. No MISSING or watch commands. Feedback latency remains an implementation measurement; no test success is claimed. No REVIEWS artifact was present.

```yaml
issues:
  - severity: BLOCKER
    dimension: cross_plan_data_contracts
    plan: "15-07,15-09,15-10"
    task: "15-07-T2;15-09-T2;15-10-T2"
    affected_field: "<action>; dispatch claim versus actual provider transport admission"
    finding: "15-07 validates deadline/controls before claim; 15-04 marks that claim DISPATCHED. 15-09 then reconciles/releases account authority before the call, and 15-10 starts a separate child. No task assigns a final deadline/control check at the actual provider boundary. A claim at 09:19:59 can therefore call after09:20, or after a PAUSE accepted during release/child startup, while being treated as already dispatched. RESEARCH's Daily recovery and deadline contract explicitly forbids the former."
    suggested_fix: "Define a final provider-dispatch admission immediately before the single transport/subprocess invocation, using current aware time, same eligible date/session and effective pending/applied controls without account authority across the call. Define durable zero-call suppression after an already consumed claim without restoring replay authority. Add barriers between claim, reconciliation/release, child startup and call: cutoff or accepted pause must produce zero calls; a truly begun call may finish boundedly after09:20."
  - severity: BLOCKER
    dimension: key_links_planned
    plan: "15-10,15-11,15-13"
    task: "15-10-T1;15-11-T1/T2;15-13-T2"
    affected_field: "service_expectations producer and independent observer inputs"
    finding: "Expectations are produced by trading ServiceSchedule/ServiceRuntime ticks; the independent observer only consumes positive saved expectations and must return UNKNOWN when none exist. If trading crashes/reaches MANUAL_ATTENTION before today's expectations (including across midnight), the awake observer has no current dated expectation and cannot detect today's absent PREP/DAILY/RISK schedules. Separate process supervision alone does not close this D-16/AUTO-02 gap."
    suggested_fix: "Specify a non-trading expectation producer or a durable advance-coverage protocol using protected enabled/login state, exact-date authoritative session evidence and current controls. Wire its read-only calendar/schedule inputs and writer ownership explicitly; unknown evidence stays UNKNOWN. Test observer-only operation across midnight and a trading crash before expectation creation on a positively evidenced eligible day, with detected absence plus holiday/paused/unknown controls avoiding false incidents."
  - severity: BLOCKER
    dimension: task_completeness
    plan: "15-11"
    task: 2
    affected_field: "<action>; AlertObserver._scan mandatory-source failure handling"
    finding: "The task adds service/control mandatory sources but does not replace the existing abort-before-delivery behavior. Current alert_observer.py _scan raises SOURCE_FAILED before detector facts, due_reminders and pending_deliveries; watch then exits. A missing/corrupt/unreadable service/control source can therefore repeatedly stop independent health delivery and unacknowledged CRITICAL reminders, although the observer's own operational store and transport remain healthy."
    suggested_fix: "Explicitly separate per-source UNKNOWN/failure observation from healthy observer outbox/reminder progress. Preserve prior incidents and avoid false recovery; use attributable source-unavailable evidence while continuing bounded existing deliveries/ACK/reminders when operational storage is healthy. Test persistent failed service/control reads with a preexisting pending CRITICAL episode and reminder, verifying observer stays active and delivery UNKNOWN ownership remains intact."
  - severity: BLOCKER
    dimension: research_resolution
    plan: null
    task: null
    affected_field: "15-RESEARCH.md:307 — ## Open Questions"
    finding: "All three listed research questions lack RESOLVED markers and the section is not marked (RESOLVED), failing mandatory Dimension11 even though plans propose session bundles, acceptance transport and restart accounting."
    suggested_fix: "Record the concrete chosen resolutions with links to15-02,15-06/13 and15-03/13 and mark the section/questions RESOLVED. Keep unavailable future-date evidence and actual09-08 approval explicitly pending activation gates; they need not block offline implementation."
  - severity: WARNING
    dimension: pattern_compliance
    plan: "15-01,15-03,15-13"
    task: "15-01-T1;15-03-T1;15-13-T1"
    affected_field: "<action> analog references"
    finding: "PATTERNS maps service_config.py to alert_config.py, service_store.py to portfolio_store.py/web_store.py, and service_cli.py to alert_cli.py. These files are loaded in read_first but their task actions do not reference the assigned analogs as required by Dimension12."
    suggested_fix: "Add concise action references to the mapped analogs and the specific protected-settings, owner/migration and explicit-CLI patterns to copy; retain intentional dispatch/control differences."
```

Return to planner for these concrete revisions. External Mac installation/login/wake, private-device access and Phase9 approvals remain unpassed operator gates and do not prevent autonomous offline implementation after plan gaps are resolved.
