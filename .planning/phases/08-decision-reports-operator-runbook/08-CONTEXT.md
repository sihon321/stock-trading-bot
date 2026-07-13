# Phase 8: Decision Reports & Operator Runbook - Context

**Gathered:** 2026-07-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Turn the normalized SQLite audit evidence and deterministic replay JSON produced by earlier phases into human-readable daily, period, and replay CLI reports. Document a fixed, manual KRX-session operating procedure for `bot status`, `bot screen`, `bot run`, and report review, including fail-closed preflight gates and safe failure triage. This phase does not add scheduling, a web dashboard, broker-facing soak campaigns, automatic policy changes, profitability backtesting, or real-money promotion.

</domain>

<decisions>
## Implementation Decisions

### Daily report shape
- **D-01:** The default daily report shows a concise run/day summary first, followed by full detail for every candidate ticker; detail is not hidden behind an extra flag.
- **D-02:** Group ticker detail by `screen` or `run` invocation and retain actual processing order within each invocation so evidence remains traceable to its source run.
- **D-03:** Display no-trade and failure reasons as the stable machine-readable reason code together with a Korean human-readable explanation.
- **D-04:** Print reports to the terminal by default. When `--output` is supplied, save the same human-readable report to a file.

### Period and replay summaries
- **D-05:** Expose distinct Typer subcommands: `bot report daily`, `bot report period`, and `bot report replay`.
- **D-06:** Period selection uses an inclusive start/end range over the recorded KST trading date (`trading_date_kst`), not UTC invocation timestamps.
- **D-07:** Show total and determinate denominators side by side. Complete, incomplete, and unknown states remain explicit and must reconcile to the detail rows rather than disappearing from statistics.
- **D-08:** Show every replay stable result ID and verification status separately before aggregation. Aggregate only results whose schema, policy, and scenario basis are compatible; separate incompatible results and explain why they were not combined.
- **D-09:** Every replay report retains the statement that replay validates decision-policy paths and does not estimate profitability or investment performance.

### Daily operating sequence
- **D-10:** The documented default KST schedule is: 08:50 `bot status` preflight, 09:05 `bot screen` preview, 09:10 `bot run`, then immediate `bot report daily` review. These are manual operator steps, not scheduled automation.
- **D-11:** If mock-target identity, audit writability/evidence health, KRX trading-day/session state, or unresolved-order state cannot be confirmed, abort `bot run`. Read-only status and historical report access remain available.
- **D-12:** The 09:05 screen is a preview. `bot run` performs a fresh screen at execution time; the report makes differences between preview candidates and run candidates visible.
- **D-13:** The daily procedure is complete only after the run is terminal, every attempted ticker has one terminal outcome, order/no-trade evidence has been reviewed, and any ambiguous order is either absent or formally transferred into its triage procedure. Notification failure requires direct report review.

### Failure triage playbooks
- **D-14:** Organize the runbook as a per-failure response table plus stepwise checklists. Every entry states symptoms/reason codes, whether trading stops, evidence or commands to inspect, prohibited actions, the safe next action, and the resolution criterion.
- **D-15:** Never automatically rerun after data, API, or LLM failure. After confirming that audit evidence is healthy and no order may have been submitted, the operator may start a new run with a new `run_id` linked to the earlier run through `parent_run_id`.
- **D-16:** For ambiguous or duplicate orders, freeze new orders for the affected ticker, establish broker truth from KIS order/open-order/fill evidence, append reconciliation evidence, and resume only after the state is determinate. A duplicate is linked to the existing order and is never resubmitted.
- **D-17:** Audit persistence or evidence-integrity failure stops new trading. Notification failure remains fail-soft, but must be visible in the CLI report and manually reviewed before the daily procedure is considered complete.

### Agent Discretion
- Choose the internal report models, query/service boundaries, SQL details, terminal table/wrapping style, output file extension, and exact CLI option names consistent with the existing synchronous Typer architecture.
- Define the Korean explanation catalog and replay-compatibility comparison mechanics, provided stable source codes/identities remain visible and all locked denominators and incompatibility reasons are explicit.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone scope and locked requirements
- `.planning/PROJECT.md` — Core value, mock-first manual operation, v1.1 reporting/runbook goal, and explicit exclusions for automation and dashboards.
- `.planning/REQUIREMENTS.md` — REP-01, REP-02, RUN-01, and RUN-02; explicit denominator, incomplete-state, target, reconciliation, and failure-triage requirements.
- `.planning/ROADMAP.md` — Phase 8 goal, success criteria, dependency on Phase 7, and boundaries with Phases 9 and 10.
- `.planning/STATE.md` — Current milestone position and accumulated evidence-first safety constraints.

### Upstream evidence contracts
- `.planning/phases/06-audit-evidence-cycle-boundaries/06-CONTEXT.md` — Locked run lifecycle, ticker outcome, order event, KRX timing, freshness, retry, and reconciliation semantics that reports must preserve.
- `.planning/phases/07-deterministic-replay-validation/07-CONTEXT.md` — Locked replay manifest/result identity, explicit-denominator funnel, normalized JSON, and non-profitability semantics.

### Existing production contracts
- `trading_bot/audit_models.py` — Stable run statuses, ticker outcomes, reason codes, failed stages, order events, and sanitized evidence contracts.
- `trading_bot/sqlite_audit.py` — Current versioned SQLite schema and persistence boundaries for runs, decisions, ticker outcomes, and append-only order events.
- `trading_bot/cli.py` — Existing Typer commands, run/screen lifecycle orchestration, terminal outcomes, replay output, and minimal status command.
- `trading_bot/replay.py` — Stable replay results, manifests, funnel denominators, compatibility inputs, verification checks, and non-profitability disclaimer.
- `tests/test_sqlite_audit.py` — Persistence, lifecycle, attribution, and schema expectations reporting queries must not weaken.
- `tests/test_cli.py` — Existing CLI output and injected-collaborator testing patterns.
- `tests/test_replay.py` — Replay identity, funnel, verification, and normalized-output expectations.

No external specifications were identified; the project planning files and production contracts above are canonical.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `runs`, `decisions`, `ticker_outcomes`, and `order_events` in `trading_bot/sqlite_audit.py`: normalized evidence already contains the run, ticker, decision, confidence, reason, order, target, and reconciliation facts needed by daily and period reports.
- `RunStatus`, `TickerOutcomeCode`, `ReasonCode`, `FailedStage`, and `OrderEventType` in `trading_bot/audit_models.py`: stable vocabularies can drive grouping, Korean explanations, incomplete/unknown classification, and triage lookup.
- `ReplayResult`, `ReplayManifest`, `ReplayFunnel`, and `ReplayVerification` in `trading_bot/replay.py`: existing normalized replay JSON already exposes stable identity, compatibility inputs, explicit denominators, mismatches, and the required disclaimer.
- Existing `run`, `screen`, `replay`, and `status` Typer commands in `trading_bot/cli.py`: establish the command style and operator-facing integration point for a `report` sub-application.

### Established Patterns
- Operator actions are synchronous and manually triggered through Typer; external collaborators are injected for deterministic tests.
- Trading fails closed when decision-critical evidence is missing, while notifications are deliberately fail-soft.
- SQLite evidence is normalized, immediately committed, provider-neutral, sanitized, and attributable by immutable run/ticker/order identities.
- KIS POST requests are never blindly retried; broker truth and append-only reconciliation evidence govern recovery.
- Replay output is deterministic JSON keyed by stable result identity and never claims profitability.

### Integration Points
- Add a Typer `report` command group beside the existing top-level commands without changing the shipped decision or execution gates.
- Build read-only reporting queries/services over the existing SQLite connection and normalized replay files; report commands must not create trading runs or mutate policy/settings.
- Compare the separate preview screen run with the later execution run through recorded KST date, run kind, timestamps, and candidate outcomes while retaining both immutable runs.
- Keep the runbook as operator documentation tied to actual commands, reason codes, lifecycle states, and reconciliation evidence rather than prose-only generic advice.

</code_context>

<specifics>
## Specific Ideas

- Default daily timing is explicitly 08:50, 09:05, and 09:10 KST.
- Human-facing reason text is Korean, but stable source codes remain visible beside it.
- Reports are summary-first but never hide complete ticker detail by default.
- Candidate differences between preview screening and the fresh run screening are part of the daily review evidence.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within Phase 8. KIS mock soak/fault execution remains Phase 9; calibration and promotion readiness remain Phase 10; scheduling and a web dashboard remain future scope.

</deferred>

---

*Phase: 8-Decision Reports & Operator Runbook*
*Context gathered: 2026-07-13*
