# Phase 9: KIS Mock Soak & Fault Drills - Context

**Gathered:** 2026-07-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Build an explicit KIS mock-account soak workflow that proves repeated safe manual operation over eligible KRX days, reconciles campaign-touched orders and account state against authenticated broker truth, survives ambiguous submissions and process restarts without blind resubmission, and records required fault drills with machine-checkable provenance. This phase does not add scheduling, real-money promotion, automatic policy changes, profitability analysis, or new trading strategies.

</domain>

<decisions>
## Implementation Decisions

### Mock-only entry and isolation
- **D-01:** Expose a dedicated `bot soak` command family with explicit start, run, resume, status, and drill operations. Do not hide soak semantics behind ordinary `bot run` flags.
- **D-02:** Construct a mock-only runtime that can resolve only `kis_mock` credentials, the mock domain, mock account, and mock TR IDs. Real configuration must not be reachable from the soak execution path, and any mismatch fails before campaign execution.
- **D-03:** Before any soak mutation, show and persist a non-secret identity receipt containing `target=mock`, sanitized domain class, account suffix, TR-ID profile, campaign ID, and mock-isolation policy version. Every identity field must pass.
- **D-04:** When audit storage is healthy, an isolation failure appends a sanitized `MOCK_ISOLATION_BLOCKED` campaign event, places no order, and does not count the day as attempted. If audit health is unknown, fail without mutation and emit only a terminal error.

### Campaign pass/fail accounting
- **D-05:** Record an immutable `target_eligible_days` when a campaign starts, defaulting to 20 eligible KRX days. The target cannot change after campaign creation.
- **D-06:** Count at most one explicitly designated terminal mock run per confirmed KRX trading date. Grant day credit only after daily-report evidence confirms complete run, ticker, order, and reconciliation evidence.
- **D-07:** HOLD and zero-order days can earn eligible-day credit. Weekends, holidays, preview screens, dry-runs, controlled drill runs, and extra reruns cannot add credit.
- **D-08:** Record a separate immutable availability-failure budget, defaulting to two days. Pre-submission failures clearly attributable to external KIS, LLM, or data availability consume the budget and earn no day credit, but do not reset the safety clean streak. Exceeding the budget fails the campaign.
- **D-09:** Any safety-invariant breach permanently fails the campaign; it cannot be repaired by resetting the clean streak inside the same campaign. Breaches include real-target reachability, unjustified submission, blind POST retry, duplicate order, lost or contradictory audit evidence, incorrectly released ambiguity, and disagreement between local evidence and broker truth.
- **D-10:** A controlled fault does not fail the campaign when the expected containment, evidence, and recovery checks all pass. Fault-drill coverage remains separate from clean-operation day accounting.

### Broker-truth reconciliation and recovery
- **D-11:** Authenticated reconciliation is mandatory at soak startup or resume, before every designated run, after every submission, and before run finalization/day credit.
- **D-12:** Each reconciliation persists a normalized snapshot and comparison verdict for campaign-touched orders, fills, open orders, holdings, and available cash. Exclude raw KIS payloads, secrets, and unrelated account activity.
- **D-13:** Accepted-then-timeout and other ambiguous submissions are never resubmitted. Perform bounded broker inquiry over a recorded time window using account, ticker, side, quantity, price, and available broker identifiers; append every observation.
- **D-14:** Keep an ambiguously submitted ticker frozen until inquiry establishes exactly one determinate match or confirmed absence. Multiple or inconclusive matches require operator review and cannot release the freeze.
- **D-15:** Complete partial-fill or no-fill evidence is determinate, but the ticker remains ineligible for new orders across restarts until the remaining order is filled, cancelled, rejected, or expired and broker truth confirms that terminal state.
- **D-16:** A day with a partial or no fill may earn credit only after all evidence is complete and local holdings, cash, and order state reconcile to broker truth. The unresolved ticker freeze persists independently of day credit.

### Fault-drill execution and evidence
- **D-17:** Track `CONTROLLED_INJECTION` and `KIS_OBSERVED` as separate evidence classes and never combine their counts or claims in reports.
- **D-18:** Every required Phase 9 fault gets a reproducible controlled-injection drill. Naturally occurring KIS mock failures add `KIS_OBSERVED` evidence and may satisfy the same drill only when the identical expected containment and reconciliation checks pass.
- **D-19:** Invoke controlled drills only through `bot soak drill <fault>`. Each invocation requires an active campaign, a passing mock identity receipt, exactly one named fault, an explicit injection boundary, and a generated drill ID. Ordinary soak runs cannot accept hidden fault-injection flags.
- **D-20:** Controlled drill runs never increment eligible-day credit or consume the availability budget. Naturally occurring faults during designated daily runs follow normal campaign accounting.
- **D-21:** Use an independent controller journal outside the primary audit DB being tested. Before injection it durably records campaign identity, drill ID, fault type, injection boundary, and expected containment.
- **D-22:** After recovery, the controller journal links observed run, ticker, and order events; broker reconciliation where applicable; interruption/restart evidence; prohibited-action checks; and a terminal pass/fail verdict. Any required evidence missing from this contract fails the drill.

### Agent Discretion
- Choose campaign table/schema names, exact state enum names, journal serialization, CLI option spelling, and output formatting consistent with existing Typer and normalized SQLite evidence patterns.
- Define bounded KIS inquiry durations, polling cadence, and exact field matching after confirming authenticated mock endpoint behavior; these choices may not weaken the no-resubmission or ticker-freeze decisions above.
- Choose safe injection seams for each required fault and the internal controller implementation, provided ordinary soak runs cannot activate them and the evidence classes remain explicit.
- Define the exhaustive stable reason-code catalog and drill result schema while preserving the locked campaign accounting, provenance, containment, and reconciliation distinctions.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone scope and locked requirements
- `.planning/PROJECT.md` — Core value, mock-first safety posture, manual operation, v1.1 soak goal, and explicit exclusions for scheduling and automatic promotion.
- `.planning/REQUIREMENTS.md` — SOAK-01 through SOAK-04, required broker-truth states and fault catalog, and boundaries against Phase 10 calibration.
- `.planning/ROADMAP.md` — Phase 9 goal, success criteria, dependency on Phase 8, and separation from promotion readiness.
- `.planning/STATE.md` — Current milestone position and accumulated evidence-first constraints, including the rule that only explicit KIS mock operation counts as soak evidence.

### Upstream decisions and operator contracts
- `.planning/phases/06-audit-evidence-cycle-boundaries/06-CONTEXT.md` — Immutable run/ticker/order evidence, ambiguity, reconciliation attribution, KRX timing, and freshness semantics that soak evidence must preserve.
- `.planning/phases/07-deterministic-replay-validation/07-CONTEXT.md` — Explicit separation between deterministic fixtures and broker-facing soak behavior, plus stable evidence identity patterns.
- `.planning/phases/08-decision-reports-operator-runbook/08-CONTEXT.md` — Manual daily sequence, preflight gates, report semantics, per-ticker freezes, and failure-triage decisions that Phase 9 extends with broker truth.
- `docs/operator-runbook.md` — Shipped operator commands, completion criteria, prohibited retries, local unresolved-order triage, and the current boundary before Phase 9 authenticated reconciliation.

### Existing production contracts
- `trading_bot/cli.py` — Existing synchronous Typer commands, runtime construction, run identity, lifecycle finalization, preflight enforcement, audit writes, and injected-collaborator patterns.
- `trading_bot/preflight.py` — Typed mock-target, audit-health, KRX-session, and unresolved-order checks; global stop versus ticker-freeze semantics.
- `trading_bot/kis_broker.py` — Query-before-POST behavior, single-shot submission, ambiguity error, append-only order events, fill reconciliation, and later-observer attribution.
- `trading_bot/kis_order.py` — Mode-derived KIS TR IDs, authenticated order/fill/balance inquiries, bounded query retries, and intentionally non-retried order POST.
- `trading_bot/sqlite_audit.py` — Versioned normalized audit schema, immediate commits, run/ticker/order/notification persistence, and abandoned-run recovery.
- `trading_bot/audit_models.py` — Stable lifecycle, outcome, reason, order-event, freshness, and sanitized-detail contracts.
- `trading_bot/reporting.py` — Existing run/ticker/reconciliation/notification projections and explicit determinate/incomplete/unknown evidence dimensions.

### Verification patterns
- `tests/test_kis_broker.py` — Existing ambiguity, duplicate suppression, later reconciliation, and partial-fill expectations.
- `tests/test_kis_order.py` — Mock/real TR-ID separation and normalized fill/account-query behavior.
- `tests/test_preflight.py` — Exact mock-target and unresolved-order gate semantics.
- `tests/test_cli.py` — Terminal outcomes, mock identity output, notification evidence, and orchestration injection patterns.
- `tests/test_sqlite_audit.py` — Persistence, lifecycle, attribution, and append-only evidence invariants.

No external specification was identified; project planning artifacts, the shipped runbook, and production contracts above are canonical.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `build_preflight_result` and typed checks in `trading_bot/preflight.py`: provide the starting mock-target, audit, market-session, and unresolved-order gates for the stronger soak identity receipt.
- `KISBroker.place_order` and `KISBroker.reconcile_order`: already enforce query-before-POST, create distinct intent/submission identities, preserve ambiguous acknowledgement, and append later broker observations without rewriting origin evidence.
- `KisOrderAdapter` inquiry methods: already separate mode-specific TR IDs and expose daily fills and balance data through the shared authenticated token flow.
- Run, ticker outcome, order event, and notification tables in `trading_bot/sqlite_audit.py`: provide normalized evidence primitives that campaign and drill records can reference instead of duplicating raw provider data.
- Daily/period reporting in `trading_bot/reporting.py`: provides existing determinate, incomplete, unknown, target, reconciliation, and notification dimensions for campaign views.

### Established Patterns
- Operator actions are synchronous, manually invoked Typer commands with explicit flags and injectable collaborators for deterministic tests.
- Mutable operations fail closed on unknown identity, timing, freshness, audit, or order state; notification transport alone remains fail-soft.
- Order POST is single-shot. Query operations may use bounded retry, and all later broker truth is appended rather than overwriting the originating event.
- Durable evidence uses stable enums/codes, sanitized bounded detail, immediate SQLite commits, and no raw provider payloads or secrets.
- Real and mock settings currently share configuration models, so Phase 9 must introduce a structurally mock-only construction path rather than merely trusting the active trading-mode flag.

### Integration Points
- Add a `soak` Typer sub-application beside `run`, `screen`, `status`, `report`, and `replay`, while reusing the existing run lifecycle and preflight vocabulary.
- Extend normalized audit persistence with campaign/day/drill/controller references that link, rather than replace, existing run, ticker, order, reconciliation, and notification evidence.
- Extend authenticated KIS inquiry projection to compare campaign-touched orders, open quantities, holdings, and available cash without persisting unrelated account data.
- Feed campaign and drill results into the existing reporting layer and operator runbook while keeping controlled-injection and KIS-observed evidence visibly separate.
- Reuse dependency injection seams in CLI and adapters for controlled faults; prohibit those seams from ordinary soak execution paths.

</code_context>

<specifics>
## Specific Ideas

- Default campaign target: 20 eligible KRX days.
- Default availability-failure budget: two days.
- The operator must see a full non-secret mock identity receipt, not only a generic mock banner.
- Clean-operation progress and fault-drill coverage are two separate campaign dimensions.
- An independent controller journal is mandatory because interruption and audit-failure drills cannot rely solely on the component being disrupted.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within Phase 9. Advisory policy calibration and real-money promotion readiness remain Phase 10; scheduling, unattended retries, profitability backtesting, and new strategies remain outside the milestone.

</deferred>

---

*Phase: 9-KIS Mock Soak & Fault Drills*
*Context gathered: 2026-07-16*
