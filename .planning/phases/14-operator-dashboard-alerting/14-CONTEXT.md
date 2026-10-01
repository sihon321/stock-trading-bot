# Phase 14: Operator Web UI, Dashboard & Alerting - Context

**Gathered:** 2026-10-01
**Status:** Ready for planning
**Decision authority:** The user selected all four areas and answered each preference individually, then selected context creation. D-01 through D-16 record those choices. The implementation boundaries below carry forward roadmap requirements and existing safety contracts.

<domain>
## Phase Boundary

Deliver FUT-03, UI-01, UI-02 and OPSV-01: an authenticated Korean desktop/mobile operator application for durable account, holdings, candidates, LLM decisions, orders, fills, run history, reports, replay, soak, calibration, readiness and worker-health evidence. Support authenticated report generation/export and alert acknowledgement. Provide severity-based, deduplicated, evidence-linked operational alerts.

The web process cannot submit/cancel orders, call a live LLM, write trading policy, display secrets, enable real mode or waive gates. Use local/private exposure by default. Dashboard refresh reads saved evidence and never triggers a broker query or trading cycle. Unattended trading scheduling, pause/resume and kill controls belong to Phase 15; real-money pilot authorization belongs to Phase 16. A readiness display confers no promotion authority.

</domain>

<decisions>
## Implementation Decisions

### First screen and navigation
- **D-01:** The landing screen prioritizes operational safety: unresolved orders, active safety blocks, worker health and source observation times, followed by account and holdings summaries. Coverage still includes every required Phase 14 view.
- **D-02:** Mobile presents the safety summary first, with holdings, orders and run details available through separate detail screens. Preserve the same evidence and supported non-trading actions rather than dropping mobile capabilities.
- **D-03:** Desktop uses a left navigation grouped as operational overview / account and holdings / decisions and orders / validation and reports. Mobile uses a collapsible navigation. Worker health, candidates, fills, run history, replay, soak, calibration and readiness must be discoverable within those groups.
- **D-04:** Follow the device/system light or dark preference automatically. The user chose this instead of the recommended light-only default. Keep tables/numbers readable and communicate severity through text and icons as well as color.

### Access and login
- **D-05:** Default access is from the execution PC through local binding. Support explicitly configured private VPN access from the owner's phone outside the home, including mobile data. Do not expose the app publicly by default. VPN access does not replace application authentication. The user asked what private networking meant and then chose outside-home phone access after the VPN explanation; no VPN vendor was selected.
- **D-06:** Use one dedicated operator account and password, provisioned during initial setup. These credentials are separate from KIS and LLM credentials. No public signup or external-account login is required.
- **D-07:** Login lasts at most 12 hours, after which authentication is required again. Treat this as an absolute session lifetime rather than an indefinitely sliding expiry.
- **D-08:** Permit concurrent PC and phone sessions, with independent session expiry. Logging in on the phone does not log the PC out.

### Refresh and evidence review
- **D-09:** Refresh saved evidence automatically every 30 seconds and provide a manual refresh button. Display the source's actual observation time separately from the browser refresh time. Refresh does not refresh KIS truth or execute an LLM.
- **D-10:** Retain the last successfully observed value when data becomes stale or a query fails; visibly label staleness, failure and observation time. Unknown totals stay UNKNOWN, never zero or inferred complete. A saved complete observation can still be old; do not present it as current account truth.
- **D-11:** Drill down from a total/status to its constituent rows, then an individual record with decision reasons, order progression and source IDs, then expandable source evidence. Every displayed aggregate must have attributable durable details. Source evidence means a sanitized, authorized projection; it does not permit exposing secrets, raw exception bodies or arbitrary stored payloads.
- **D-12:** Default run/decision/order history to today in Asia/Seoul, with operator-selectable periods. Unresolved orders and active alerts remain visible across dates. Do not hide the existing unresolved 000660 subject through today's date filter or treat disappearance as resolution.

### Alerts and report workflows
- **D-13:** Show all alert severities and history in the web app. Use the existing Discord notification channel for WARNING/CRITICAL events and recovery notifications. INFO remains available in the web view; retain existing production notifications without creating duplicate deliveries.
- **D-14:** Group repeated observations of the same underlying problem into one incident. Notify on occurrence, worsening and recovery. Remind every 30 minutes for an unacknowledged CRITICAL incident; WARNING has no periodic reminder. Durable occurrence counts, duration and delivery-attempt history remain reviewable across refreshes/restarts. A newly worsened or recurring incident must not inherit acknowledgement of an earlier state.
- **D-15:** Acknowledgement means the operator has read the alert. Record operator identity and time automatically; a response note is optional. Acknowledgement stops that incident's periodic reminders but does not resolve it, clear a freeze/latch, alter broker evidence or relax any safety gate. Active warnings remain visible until source evidence establishes recovery.
- **D-16:** Provide Korean TXT reports, structured JSON results and CSV tables suitable for spreadsheet review. Preserve source IDs, report scope, denominators and UNKNOWN/INCOMPLETE facts in exports; identify simulated/advisory results. Generate/export existing read-only reports from saved evidence. Exporting a report never starts replay/backtest/shadow evaluation or live data collection.

### Required implementation boundaries and agent discretion

All selected areas are resolved; the user did not delegate preference questions to the agent. Frameworks, module names, internal schemas, precise layouts, secure session storage, password hashing/recovery, bounded queries, pagination, accessible components and implementation mechanics remain research/planning decisions.

- Enforce authentication and authorization throughout pages, evidence endpoints, report generation/download and acknowledgement. State-changing requests must be CSRF-protected and audit logged. Password/session material and secret-bearing configuration are never displayed or exported.
- Read production evidence through capability-limited readers. Do not instantiate credential-bearing trading Settings, broker/LLM collaborators, mutation leases or live CLI orchestration inside the web runtime. Store session, acknowledgement, web-action audit and alert delivery bookkeeping separately from authoritative trading evidence; web writes cannot amend source facts or migrate production databases.
- Preserve separate mock/real/dry-run/simulated/shadow scopes, broker versus local observation provenance, report denominators and advisory readiness semantics. Validate supported schemas and source links. Missing sources or inconsistent cross-store links remain unavailable/UNKNOWN, with per-source observation facts rather than a claimed atomic cross-database snapshot.
- Worker health derives from durable lifecycle/heartbeat evidence and the applicable session/expected-worker state. Distinguish stopped/not expected from stale/failed and UNKNOWN when expectation cannot be established. No record does not prove health. Research/planning chooses documented thresholds compatible with existing watch cadence and manual operation; Phase 15 scheduling is not a prerequisite for displaying current evidence.
- Alerts cover failed/stale workers and cycles, unresolved orders, safety latches and broker divergence. Deduplication uses stable account/target/problem subjects and incident transitions, not page refreshes or iteration UUIDs. Use existing INFO/WARNING/CRITICAL semantics where supported; detection/display never acquires order authority or invents broker recovery.
- Alert observation and reminders must work independently of an open browser while their explicitly started, non-trading monitoring process is running. Define its local start/stop/health contract and durable delivery accounting. This permits bounded operational monitoring, not unattended trading scheduling. Notification transport failures remain visible and do not rewrite trading outcomes. Preserve existing mandatory transition-evidence safety behavior.
- CSV content must be safe to open in spreadsheet software; render all third-party news, LLM reasons, stored text and operator notes as untrusted content. Allow only registered evidence/report resources and bounded sanitized exports, not arbitrary local paths or executable commands.
- VPN deployment details and the concrete authentication/web stack need current primary-source research during planning. No installation, public deployment, notification sending or trade is authorized by this discussion alone.

</decisions>

<canonical_refs>
## Canonical References

Downstream agents MUST read these before planning or implementing. No user-supplied external spec, ADR, design reference or VPN provider was introduced.

### Scope and existing safety decisions
- `.planning/ROADMAP.md` — Phase 14 goal, five success criteria and Phase 15/16 authority boundaries.
- `.planning/REQUIREMENTS.md` — FUT-03, UI-01, UI-02 and OPSV-01.
- `.planning/PROJECT.md` — Korean personal operator tool, strict signals and mock-first safety.
- `.planning/STATE.md` — Current phase and unresolved-order/soak acceptance constraints.
- `.planning/phases/11-kis-portfolio-synchronization-intraday-exit-management/11-CONTEXT.md` — Broker truth, once-daily signals, foreground watch, mutation exclusion and state-transition notification contracts.
- `.planning/phases/12-full-portfolio-backtesting-market-friction-modeling/12-CONTEXT.md` — Offline modeled portfolio evidence, reproducibility and advisory reporting.
- `.planning/phases/13-historical-llm-shadow-evaluation-model-governance/13-CONTEXT.md` — Attributable model/prompt/cost evidence and shadow isolation.
- `docs/operator-runbook.md` — Read-only review, ambiguity handling, notification severity, unresolved 000660 freeze and manual promotion boundaries.

### Evidence and notification contracts
- `trading_bot/reporting.py` — ReadOnlyAuditRepository, durable report rows, denominators and explicit evidence states.
- `trading_bot/report_cli.py` — Credential-free report orchestration and safe output handling.
- `trading_bot/soak_reporting.py` — Independent read-only evidence owners and cross-store link validation.
- `trading_bot/calibration_reporting.py` — Advisory calibration evidence projection.
- `trading_bot/promotion_readiness.py` — Pure READY/BLOCKED reduction; no authorization grant.
- `trading_bot/backtest_reporting.py` — Validated saved backtest results and modeled metrics.
- `trading_bot/shadow_reporting.py` — Validated saved shadow comparisons, usage and cost reporting.
- `trading_bot/audit_models.py` — Evidence vocabularies, operational severities, stable transition subject identities and sanitization.
- `trading_bot/portfolio_store.py` — Portfolio snapshots, daily evaluations, watch observations and durable transition state.
- `trading_bot/mutation_lease.py` — Readable lease/heartbeat/recovery facts; never grant this capability to the web runtime.
- `trading_bot/intraday.py` — Foreground worker lifecycle and transition observation/evidence semantics.
- `trading_bot/notifier.py` — Existing bounded fail-soft Discord transport; isolate its credentials from report/view configuration.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ReadOnlyAuditRepository` already opens SQLite with `mode=ro` and `query_only=ON`, validates schema capabilities and loads stable run/ticker/report evidence in a read transaction.
- Existing soak/calibration readers and pure report builders provide a route to rendering evidence without live collaborators. Cross-store reports cannot claim one atomic snapshot.
- Saved replay, backtest and shadow loaders validate immutable evidence; readiness reduction exposes UNKNOWN/BLOCK rather than inferring PASS.
- `OperationalSeverity`, `canonical_transition_identity`, transition occurrence/duration state and notification-attempt records already support durable subject-based alerts.
- Portfolio/watch/lease evidence supplies observed worker and broker-state facts. `DiscordNotifier` has bounded retries and redacted representation, but importing full trading configuration would violate the desired web boundary.

### Established Patterns
Credential-free read-only report controllers, strict source validation, stable IDs/hashes, bounded sanitized diagnostics and append-only evidence. Broker truth governs account/order recovery, local history records intent, and simulated/advisory results have no execution authority. No existing frontend map or reusable UI component library was identified in the lightweight scout.

### Integration Points
Introduce a separate web entry point consuming existing read-only repositories and pure report builders, with narrowly scoped operational persistence and an independent non-trading alert observation/delivery boundary. Extend report serialization for web/JSON/CSV without invoking CLI execution commands. Avoid the live `trading_bot/cli.py` runtime factory. Add a UI design contract during planning consistent with the chosen navigation, mobile detail views and system theme.

</code_context>

<specifics>
## Specific Ideas

The owner wants outside-home phone access through a private VPN, with dedicated application login. Both PC and phone remain logged in concurrently for at most 12 hours. The owner explicitly chose system-following light/dark mode. Safety overview and all-date unresolved incidents take priority over today's routine history. Dashboard refresh shows the latest stored observation, not a promise of a current live quote.

</specifics>

<deferred>
## Deferred Ideas

None introduced by the user; the discussion stayed within Phase 14. Existing roadmap boundaries retain unattended trading scheduling and pause/resume/kill control in Phase 15, controlled real-money pilot authorization in Phase 16, and all manual evidence/promotion gates. No PDF export or external-account login was selected.

</deferred>

---

*Phase: 14-operator-dashboard-alerting*
*Context gathered: 2026-10-01*
