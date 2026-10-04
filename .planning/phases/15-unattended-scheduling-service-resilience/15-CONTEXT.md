# Phase 15: Unattended Scheduling & Service Resilience - Context

**Gathered:** 2026-10-04
**Status:** Ready for planning
**Decision authority:** The owner selected all four areas and answered each of the 16 preference questions individually. The owner then explicitly selected context creation. D-01 through D-16 capture those answers; carried-forward safety boundaries and planning responsibilities are identified separately.

<domain>
## Phase Boundary

Deliver FUT-04, AUTO-01 and AUTO-02: calendar-aware unattended daily evaluation and separately bounded held-position risk monitoring, durable job identities/checkpoints, leader exclusion, safe restart recovery, health visibility, and explicit pause/resume/global kill authority.

Phase 9 Plan 09-08 must be approved before unattended trading mutation is enabled. This phase can design and validate scheduling, controls, dry-run and recovery without claiming that elapsed-day acceptance has passed. Preserve all unresolved-order freezes, including 000660 unless same-subject determinate terminal broker evidence establishes resolution. Real-money pilot enablement remains Phase 16 and requires its separate manual gates; a scheduler or web resume request cannot grant promotion authority.

</domain>

<decisions>
## Implementation Decisions

### Execution time and monitoring cadence
- **D-01:** Schedule one daily LLM evaluation at 09:10 Asia/Seoul on positively confirmed eligible KRX days. Keep the existing daily input/signal uniqueness contract; one daily logical job is not a license to repeat provider calls.
- **D-02:** Start LLM-free held-position risk monitoring at 09:00 KST, protecting existing holdings before the daily evaluation. Serialize money-moving work with the existing account mutation exclusion; the watch must not monopolize authority and starve the 09:10 job.
- **D-03:** Use a 60-second risk-check cadence. Carry forward the existing session boundary: no new order submission at or after 15:20; reconciliation-only through the closing interval, and orderly watch termination at 15:30. Reconciliation failure remains recorded and frozen, not implicitly resolved at shutdown.
- **D-04:** Add an 08:50 KST preparation check using existing non-order readiness semantics. Recheck all applicable safety conditions at execution and immediately before submission. PRE_OPEN cannot authorize an order. No additional 09:05 preview job was selected.

### Missed execution and restart recovery
- **D-05:** A daily job that never started may catch up only before 09:20 KST on that same eligible date, after fresh safety checks. At or after 09:20, record a missed evaluation and surface it through existing alert semantics; do not backfill prior trading dates or move the job into an afternoon evaluation.
- **D-06:** After an unexpected service interruption, perform broker-truth reconciliation and recovery checks first, then automatically resume eligible remaining work if those checks pass. Uncertain orders retain their freezes and block affected work; no timeout or stale heartbeat independently grants mutation authority. Operator-requested pause/kill is not an unexpected interruption and must never be cleared by this automatic recovery path.
- **D-07:** For a partly completed daily evaluation, resume only never-dispatched ticker evaluations before 09:20, preserving saved inputs and progress. Do not repeat completed evaluations, blindly retry an uncertain LLM call, or replace the first committed canonical input. After the resume window, record unfinished work explicitly. Research/planning must distinguish dispatch deadlines from bounded completion/reconciliation of already-dispatched work; the window does not authorize abandoning order evidence.
- **D-08:** A failed or missed daily evaluation does not itself stop held-position protection. Continue risk monitoring when its own fresh portfolio/quote/order/lease checks pass. Shared safety faults continue to block mutation; this separation cannot bypass a global kill, unhealthy audit evidence, unresolved authority or other common gates.

### Pause, resume and global kill
- **D-09:** Normal pause stops daily evaluation and new BUY activity while retaining deterministic stop-loss/take-profit monitoring and submitted-order reconciliation. Enforce the BUY block even if an earlier evaluation or another invocation already produced a BUY signal.
- **D-10:** Global kill blocks every new order submission, including risk SELL, while leaving read-only observation, submitted-order reconciliation and alerts available. Do not automatically cancel outstanding orders or liquidate positions. Global stop authority must be checked by every affected money-moving path, not merely stop future scheduler launches.
- **D-11:** Provide pause/resume/kill controls in both CLI and the authenticated web application, including the owner's phone through the separately configured private access path. The web records narrowly authorized control requests; the execution service validates and applies them. The web must not instantiate trading credentials, directly place/cancel orders, call an LLM, write trading policy or clear evidence gates. Preserve authentication, authorization, CSRF, actor/time audit and observable requested-versus-applied state.
- **D-12:** Operator pause and kill persist across process restarts, login and trading-date changes until an explicit operator resume. Resume still requires fresh safety checks and all existing gates; it cannot clear a broker freeze or safety latch. No expiry, next-day auto-unpause or automatic kill reset was selected.

### Service operation and health
- **D-13:** Target the current development Mac as the single execution machine. Do not require a separate Mac or Linux server for this phase. Scheduled operation requires that this Mac be powered on and awake; do not claim uninterrupted service from a sleeping laptop.
- **D-14:** Start the service automatically after the owner logs into macOS, rather than before login or by daily manual start. Every launch first enters the durable recovery/safety path and retains any operator pause/kill. This decision describes the intended installed service; the discussion does not install it or start unattended orders.
- **D-15:** After an unexpected process exit, allow at most three automatic restart attempts within a ten-minute window. Stop the restart loop on repeated failure and persist a manual-attention state for health display/alerting. Preserve accounting across crashes so relaunch does not reset the limit. Each attempt retains job identity and requires recovery checks. Exact restart backoff, timeout handling and reset mechanics remain planning decisions within this limit.
- **D-16:** Show missed schedules, stalled workers, stale market data and notification failures in the web health view. Use the existing Discord problem-occurrence/worsening/recovery semantics and 30-minute reminders for unacknowledged CRITICAL episodes; do not add a routine daily 08:50 success notification. Preserve INFO web history, deduplication, acknowledgement semantics and delivery uncertainty. A total outage or sleep of this Mac cannot be detected and notified immediately by processes on the same stopped machine; the user was told this limitation.

### Carried-forward requirements and planning responsibilities

The owner answered every preference rather than delegating defaults. Choose the scheduler library, macOS service mechanism, module names, schemas, control-request transport, bounded timeouts/backoff and health thresholds during research/planning.

- KRX calendar evidence remains authoritative. Holidays are not inferred from weekdays; unknown calendar/session state fails closed. All times are KST. Preserve completed-bar cutoffs, current broker truth and pre-submit quote freshness. Research exceptional/delayed exchange sessions and apply documented session restrictions rather than overriding them with wall-clock schedules.
- Use durable logical job identity, account/target scope, first-input wins, checkpoints, process exclusion and ordered recovery together. A durable intent does not prove that an external POST occurred exactly once; ambiguous submissions remain UNKNOWN and are never blindly resubmitted. Existing manual CLI invocations must participate in exclusion and global stop enforcement.
- The separately bounded risk worker and daily evaluation need coordinated ownership without overlapping mutation. Restart begins recovery-only and cannot trust stale in-memory cash, holdings, lease heartbeat or locally projected proceeds. Persist terminal/partial/missed/blocked states honestly.
- Maintain independent non-trading health observation and alert delivery while the trading worker is paused, killed, crashed or restart-limited. Reuse Phase 14 evidence and alert ownership without requiring an open browser; do not create duplicate notifications or falsify successful delivery during an outage. Expected-worker health must account for the schedule, confirmed session, operator controls and login/service state.
- Ship an explicit dry-run/disabled setup path and enforce Phase 9 acceptance at the unattended mutation boundary. Default mock mode remains; no configuration, automatic restart or resume can enable real mode or bypass Phase 16.
- Use protected owner-local configuration, narrow capabilities and sanitized durable evidence. Web control scope is limited to the selected operational requests, not arbitrary jobs, file paths, settings changes or policy edits. Readiness and alert acknowledgement still grant no execution authority.
- Research current official macOS service and scheduler contracts. Define documented start/stop/status, logout/sleep/wake behavior, installation/removal and evidence-preserving recovery. Wake/relogin must re-evaluate deadlines and elapsed health gaps instead of replaying missed jobs. No unattended-before-login guarantee or external independent outage monitor was selected.

</decisions>

<canonical_refs>
## Canonical References

Downstream agents MUST read the relevant scope and safety contracts before planning or implementing. No external spec, ADR or new deployment provider was introduced in this discussion.

### Scope, gates and prior decisions
- `.planning/ROADMAP.md` — Phase 15 goal, four success criteria, Phase 9 activation gate and Phase 16 boundary.
- `.planning/REQUIREMENTS.md` — FUT-04, AUTO-01 and AUTO-02; web and promotion authority boundaries.
- `.planning/PROJECT.md` — mock-first owner-operated bot and selected future Tailscale access.
- `.planning/STATE.md` — current position, durable recovery decisions, unresolved 000660 and external acceptance constraints.
- `.planning/phases/09-kis-mock-soak-fault-drills/09-08-PLAN.md` — required elapsed-day operator acceptance; existence of the plan is not proof of approval.
- `.planning/phases/11-kis-portfolio-synchronization-intraday-exit-management/11-CONTEXT.md` — daily uniqueness, broker-truth exits, mutation exclusion and restart/session contracts.
- `.planning/phases/12-full-portfolio-backtesting-market-friction-modeling/12-CONTEXT.md` — offline simulation is outside live scheduling authority.
- `.planning/phases/13-historical-llm-shadow-evaluation-model-governance/13-CONTEXT.md` — shadow attempts/budgets and isolation; do not schedule paid shadow work as trading recovery.
- `.planning/phases/14-operator-dashboard-alerting/14-CONTEXT.md` — authenticated saved-evidence web, narrow operational authority, independent incident observer and notifications.
- `docs/operator-runbook.md` — existing KST timing, manual recovery, unresolved freezes, service boundaries and future Tailscale device acceptance.

### Existing runtime and evidence owners
- `trading_bot/market_cycle.py` — dependency-free calendar/session/completed-bar/quote-freshness policy.
- `trading_bot/cli.py` — manual daily and intraday orchestration, dry-run default and mutation lease integration.
- `trading_bot/intraday.py` — bounded LLM-free risk worker, session transitions, stopping and mandatory transition evidence.
- `trading_bot/mutation_lease.py` — account-scoped exclusion, durable authority and recovery-only predecessor states.
- `trading_bot/portfolio_store.py` — durable snapshots, daily inputs/evaluations, watch and transition evidence.
- `trading_bot/web_app.py` — authenticated, CSRF-protected saved-evidence HTTP surface to extend with narrow control requests.
- `trading_bot/alert_cli.py` — explicit independent alert observer entry point.
- `trading_bot/alert_observer.py` — independent incident observation, ownership and delivery evidence.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `MarketCyclePolicy` already separates TRADING_DAY/CLOSED_DAY/UNKNOWN, sessions, completed-data cutoff and quote freshness. Reuse it as the execution gate rather than treating a scheduler firing as permission.
- The shipped intraday worker has PREFLIGHT_READ_ONLY, RECOVERY_ONLY, ACTIVE, RECONCILE_ONLY, STOPPING and TERMINAL phases. Its 60-second CLI default and safe stopping/reconciliation sequence match the selected schedule.
- Mutation leases combine process exclusion with durable recovery state; every non-released predecessor requires recovery. Existing daily inputs/evaluations preserve the first canonical input.
- Phase 14 has authenticated worker-health views and a separate non-trading alert observer with durable deduplication and delivery history.

### Established Patterns
Append-only attributable evidence, strict schema/version ownership, deterministic logical identities, fresh broker truth before mutation, no blind POST retries and explicit UNKNOWN. Saved web evidence has no trading collaborators. Operational bookkeeping does not amend authoritative order facts.

### Integration Points
Add supervised scheduling around the existing daily/risk capability boundaries while preserving foreground/manual commands. Introduce narrow durable operational controls and applied-state evidence; extend web/CLI health and control surfaces without giving the web direct trading authority. Coordinate daily and risk work through account authority and durable jobs; retain independent alert supervision. The lightweight scout found no existing scheduler/service implementation or codebase maps to adopt.

</code_context>

<specifics>
## Specific Ideas

The owner wants the existing Mac to start the service after login and perform the same 09:10 daily evaluation used by the manual runbook. Held positions are protected from 09:00 with 60-second checks. Late daily dispatch has a strict before-09:20 window. Phone and CLI controls share persistent pause/kill state. All preference answers selected the first presented option, individually; this was not blanket authorization to choose unspecified recommendations.

</specifics>

<deferred>
## Deferred Ideas

None introduced by the owner; discussion stayed within Phase 15. Existing roadmap boundaries retain the Phase 16 real-money pilot and explicit promotion approval. Actual Tailscale deployment and phone/Mac external device acceptance remain the previously recorded follow-up; selecting web controls does not claim that private access is configured. No separate execution server, before-login daemon or independent external outage monitor was selected.

</deferred>

---

*Phase: 15-unattended-scheduling-service-resilience*
*Context gathered: 2026-10-04 (discussion began 2026-10-03 KST)*
