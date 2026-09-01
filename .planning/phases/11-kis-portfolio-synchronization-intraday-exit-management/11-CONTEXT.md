# Phase 11: KIS Portfolio Synchronization & Intraday Exit Management - Context

**Gathered:** 2026-09-01
**Status:** Ready for planning

<domain>
## Phase Boundary

Synchronize complete KIS broker portfolio truth into every mutable cycle, evaluate the union of broker-held positions and screened candidates once per KRX trading day, and safely execute daily LLM SELL signals plus deterministic intraday stop-loss and take-profit exits. The phase includes an operator-started one-shot check and foreground watch loop, account-scoped mutation exclusion, restart recovery, partial-fill and cancellation observation, durable evidence, and state-transition alerts. It does not add unattended scheduling, background service management, automatic order cancellation, automatic real-money promotion, market orders, new strategies, or repeated intraday LLM calls.

</domain>

<decisions>
## Implementation Decisions

### Portfolio truth and synchronization boundaries
- **D-01:** A mutable cycle obtains no order authority unless cash, holdings, orderable quantity, average price, open orders, and recent fills are all completely and successfully normalized from KIS. Any incomplete required dimension blocks all orders for that cycle.
- **D-02:** Fetch a complete account snapshot at cycle start. Immediately before every POST, re-fetch the affected ticker's holding, orderable quantity, open-order, and recent-fill truth together with a fresh quote.
- **D-03:** If pre-POST broker truth differs from the cycle-start snapshot, recalculate quantity and re-run the applicable execution gates against the latest truth. Proceed only if the original decision remains actionable.
- **D-04:** A snapshot from an earlier process or cycle is audit and comparison evidence only. Restart always performs a new KIS query before acquiring mutation authority.
- **D-05:** The standard recent-order/fill window covers the current and immediately previous confirmed KRX trading day. Older locally unresolved orders remain individually queryable back to their originating date until determinate.
- **D-06:** Read-only KIS queries may use bounded retries with short backoff. Exhaustion leaves the snapshot incomplete and the cycle non-mutable; POST remains single-shot and is never blindly retried.
- **D-07:** Complete KIS truth is authoritative for current cash, holdings, fills, and open orders. Local audit data remains authoritative for intent and observation history; every divergence is recorded rather than overwritten.
- **D-08:** A simple holding or cash difference is synchronized from KIS and warned. An unresolved or ambiguous local order that cannot be uniquely attributed to a KIS order by ticker, side, quantity, and identity is an order-risk divergence that blocks mutation.

### Daily evaluation universe and held-position context
- **D-09:** The daily evaluation universe is the attributable union of broker-held positions and current screened candidates. Evaluate held positions first, then evaluate new candidates against the resulting cash and position-cap state.
- **D-10:** A ticker present in both sources is evaluated once. Preserve both `HELD` and `SCREENED` provenance on the shared ticker/evaluation record.
- **D-11:** Held-position LLM context includes average price, total quantity, orderable quantity, current price, unrealized return, and open SELL quantity, in addition to the existing market, indicator, and delimited untrusted-news context.
- **D-12:** Incomplete market evidence for one held ticker never removes the holding from review. Record an attributable `DATA_INCOMPLETE/HOLD`, block that ticker's order, and continue other tickers. This does not weaken D-01: incomplete account-level broker truth blocks every order.

### One daily LLM evaluation
- **D-13:** Allow at most one finalized logical LLM evaluation per KRX trading date and ticker. HELD/SCREENED overlap shares one stable evaluation identity.
- **D-14:** Provider timeout, provider error, or malformed output may use bounded retries only inside that logical evaluation. Exhaustion finalizes `LLM_UNAVAILABLE/HOLD` for the ticker and prevents another LLM call that trading day.
- **D-15:** A later `bot run` on the same trading day reuses the successful signal and its immutable input snapshot. It re-evaluates current broker truth, fresh quote, risk, sizing, and order gates without calling the LLM again.
- **D-16:** The daily signal expires at the KRX trading-day boundary. Before then it never overrides current broker truth, deterministic risk rules, quote freshness, mutation lease ownership, duplicate suppression, or unresolved-order freezes.

### Intraday operator workflow
- **D-17:** Provide both an operator-invoked one-shot intraday `check` and a foreground `watch`. Neither creates a background service, scheduler, or boot-time process.
- **D-18:** The watch cadence is configurable with a conservative default of 60 seconds and an enforced minimum interval to prevent abusive KIS request rates.
- **D-19:** Treat every watch iteration as an independent audited cycle. Each iteration obtains complete broker truth and fresh quotes for held positions, then applies deterministic stop-loss, take-profit, and existing daily-loss rules without an LLM call.
- **D-20:** An incomplete iteration blocks orders for that iteration but does not terminate watch. A later iteration may regain mutation authority only from a newly complete snapshot.
- **D-21:** Watch may start before the market and perform read-only preflight and synchronization while waiting. Mutation activates only after a positively confirmed KRX continuous session begins.
- **D-22:** Stop new POSTs at 15:20 KST, retain read-only reconciliation through 15:30, then exit automatically. Do not auto-cancel remaining open orders.
- **D-23:** On `Ctrl-C`, stop new POSTs immediately, terminalize the in-progress cycle as `INTERRUPTED`, perform bounded reconciliation for already submitted orders, then release the mutation lease. Any unresolved result remains durable.
- **D-24:** After a crash or unresolved shutdown, watch enters recovery-only mode first. It may not resume normal evaluation or POST until prior cycles are terminalized and broker truth makes earlier order state determinate.

### Account-scoped mutation lease
- **D-25:** Enforce one mutation lease per KIS account across `bot run`, intraday `check`, and `watch`. Ticker-level or command-level concurrency is not sufficient because cash, holdings, and open orders are account-wide truth.
- **D-26:** A new mutable command that finds an active lease exits immediately as non-mutable and reports bounded owner/start metadata plus the read-only inspection path. It does not wait, steal the lease, or silently become an observer.
- **D-27:** Reclaim a stale lease only after confirming its owner is gone, recovering/terminalizing the prior cycle, and completing broker reconciliation. Heartbeat age or reboot alone never grants mutation authority.
- **D-28:** If a running process loses lease ownership or cannot renew it, stop new POSTs immediately, reconcile already submitted orders, and terminalize the cycle with an explicit failure/interruption state.

### SELL order lifecycle
- **D-29:** Both a daily LLM SELL and an intraday deterministic exit target the latest KIS orderable quantity in full. Quantity already reserved by an open SELL is excluded and never submitted again.
- **D-30:** Submit a limit SELL based on a quote observed no more than 10 seconds before POST and snapped to the valid KRX tick. Do not introduce market orders or an automatic aggressive-price offset in this phase.
- **D-31:** While an order is `OPEN` or `PARTIAL`, track and reconcile that broker order only. Do not submit the remainder again, auto-cancel it, or chase the price.
- **D-32:** A determinate `CANCELED`, `EXPIRED`, or `NO_FILL` may lead to a new intent only in a later independent cycle after complete broker truth, a fresh quote, and a still-valid exit condition are all re-established.
- **D-33:** A later HOLD/BUY signal or cleared risk threshold does not auto-cancel an already open SELL. Block new BUY for that ticker until the SELL reaches determinate terminal broker state.
- **D-34:** This phase observes cancellations made through KIS/operator channels but adds no cancel-POST authority to the bot.
- **D-35:** After a partial fill, the next complete KIS snapshot's remaining quantity and average price define the position. Local fill arithmetic is comparison evidence, not mutation authority.
- **D-36:** The existing daily-loss kill switch continues to block new BUY only. It does not liquidate every holding or block valid stop-loss/take-profit SELLs.

### Intraday evidence and alerts
- **D-37:** Send immediate notifications only for state transitions and safety events: risk SELL triggers, order-state changes, ambiguity/unresolved state, broker-truth failure, lease loss, interruption, and recovery. Unchanged normal iterations remain in durable audit evidence without notification noise.
- **D-38:** Use stable `INFO`, `WARNING`, and `CRITICAL` severity codes with Korean human-readable text. Starts, stops, and determinate fills are informational; sustained failures and long-open orders are warnings; ambiguity, audit failure, and lease loss are critical.
- **D-39:** Deduplicate by stable state identity: notify once when the state begins and once when it changes or recovers. Persist occurrence count and duration for every repeated watch observation.
- **D-40:** Notification transport failure remains fail-soft and visible. Failure to persist notification-attempt evidence is fail-closed for new orders, consistent with the existing evidence boundary.

### Agent Discretion
- Choose concrete module, class, table, command, option, lock-backend, heartbeat, retry-count, minimum-cadence, and stable reason-code names consistent with existing Typer, frozen dataclass, SQLite, canonical identity, and append-only evidence patterns.
- Define bounded reconciliation timeouts, exact long-open WARNING threshold, terminal rendering, and Korean message wording, provided the locked lifecycle and fail-closed boundaries remain unchanged.
- Choose whether portfolio snapshots extend the primary audit schema or use an independently versioned projection linked by stable IDs, provided one cycle can prove the exact snapshot and pre-POST observation used.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project scope and requirements
- `.planning/PROJECT.md` — Core value, mock-first safety posture, manual-operation boundary, and existing execution/risk decisions.
- `.planning/REQUIREMENTS.md` — PORT-01, PORT-02, EXIT-01, and EXIT-02 plus later-phase boundaries for scheduling, UI, and controlled production.
- `.planning/ROADMAP.md` — Phase 11 goal, dependencies, success criteria, and separation from Phases 12–16.
- `.planning/STATE.md` — Accumulated lifecycle, quote-freshness, ambiguity, reconciliation, soak, and promotion constraints.

### Upstream decision contracts
- `.planning/phases/06-audit-evidence-cycle-boundaries/06-CONTEXT.md` — Run/ticker lifecycle, KRX continuous-session window, 10-second quote freshness, append-only order events, and restart recovery semantics.
- `.planning/phases/08-decision-reports-operator-runbook/08-CONTEXT.md` — Manual operating sequence, failure triage, read-only reporting, ticker freezes, and notification evidence boundary.
- `.planning/phases/09-kis-mock-soak-fault-drills/09-CONTEXT.md` — Complete broker snapshot, pagination, partial-fill, cancellation, ambiguity, controller-journal, and mock-only evidence decisions.
- `.planning/phases/10-advisory-risk-calibration-promotion-readiness/10-CONTEXT.md` — Current risk-policy baselines, advisory-only policy boundary, and unresolved-order promotion blockers.
- `docs/operator-runbook.md` — Current operator commands, fixed KRX timing, evidence review, ambiguity recovery, and prohibited actions.

### Existing production contracts
- `trading_bot/kis_order.py` — KIS balance/daily-fill queries, normalized fill status, account/TR-ID separation, tick snapping, bounded query retry, and single-shot order POST.
- `trading_bot/kis_broker.py` — Query-before-POST, position tracking, duplicate suppression, ambiguity, append-only reconciliation, and pre-submit freshness enforcement.
- `trading_bot/soak_reconcile.py` — Normalized complete broker snapshots for orders, fills, holdings, and account cash plus comparison and ambiguity policies.
- `trading_bot/execution.py` — Existing BUY/SELL confidence gates, sizing, held-position handling, and daily-loss blocking semantics.
- `trading_bot/risk.py` — Deterministic stop-loss, take-profit, and daily-loss rules whose behavior is preserved and reused.
- `trading_bot/cli.py` — Synchronous Typer orchestration, run lifecycle, dependency injection, reporting, replay, and soak integration points.
- `trading_bot/sqlite_audit.py` — Durable run, ticker, decision, order, reconciliation, and notification evidence boundaries.
- `trading_bot/audit_models.py` — Stable lifecycle, outcome, reason, failure-stage, freshness, and order-event vocabularies.

### Verification patterns
- `tests/test_kis_broker.py` — Single-shot POST, quote freshness, duplicate suppression, ambiguity, partial-fill, and reconciliation expectations.
- `tests/test_kis_order.py` — Account query normalization, TR-ID separation, retry boundaries, tick snapping, and fill parsing.
- `tests/test_soak_reconcile.py` — Complete broker snapshot and ambiguity comparison behavior.
- `tests/test_cli.py` — CLI orchestration, terminal outcome, audit, notification, and injected-collaborator patterns.
- `tests/test_risk.py` — Stop-loss, take-profit, and daily-loss semantics.

No external specification was identified; project planning artifacts, the operator runbook, and production contracts above are canonical.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `KisOrderAdapter` in `trading_bot/kis_order.py`: already queries KIS daily executions and balances with bounded read retries, mode-derived TR IDs, normalized health, and no POST retry.
- `KISBroker` in `trading_bot/kis_broker.py`: already implements query-before-POST duplicate suppression, immutable intent/submission IDs, fresh-quote enforcement, partial-fill projection, and later reconciliation.
- `BrokerSnapshot`, `BrokerOrder`, `BrokerFill`, `BrokerHolding`, and `BrokerAccountSummary` in `trading_bot/soak_reconcile.py`: provide a strong starting schema for complete account truth rather than inventing a second normalization contract.
- `evaluate_risk` and `blocks_new_buy` in `trading_bot/risk.py`: support LLM-free intraday exits while preserving the current non-liquidating daily-loss rule.
- Run, ticker, order, notification, and reconciliation evidence in `trading_bot/sqlite_audit.py` and `trading_bot/audit_models.py`: support stable cycle identities, terminal outcomes, deduplication, and recovery.

### Established Patterns
- Mutable work is synchronous and manually invoked through Typer; external collaborators and clocks are injectable for deterministic tests.
- Incomplete decision-critical evidence fails closed, while notification transport alone remains fail-soft.
- KIS POST is single-shot. Read queries may retry within bounds, and ambiguity freezes a ticker until broker truth becomes determinate.
- Durable evidence is append-only, immediately committed, stable-code based, sanitized, and attributable across origin and observer runs.
- KRX mutation uses the confirmed continuous-session window and a quote no older than an inclusive 10 seconds at POST.

### Integration Points
- Extend the authenticated KIS inquiry layer to expose one complete production portfolio snapshot using the normalization and pagination proofs already exercised by soak reconciliation.
- Build the daily union before existing per-ticker LLM/execution orchestration, with durable evaluation identity lookup to enforce one signal per trading date and ticker.
- Add one-shot and foreground intraday commands beside existing `run`, `status`, `report`, `replay`, and `soak` commands without introducing a scheduler.
- Add account-scoped mutation lease and recovery gates ahead of every order-capable command, and bind the exact lease/snapshot/pre-POST observation to each cycle and order intent.
- Reuse the existing audit and notification boundary, extending it with watch iteration, persistent state identity, occurrence count, duration, interruption, and recovery evidence.

</code_context>

<specifics>
## Specific Ideas

- Foreground watch defaults to a 60-second cadence, permits read-only pre-open waiting, stops new POSTs at 15:20 KST, reconciles through 15:30, and exits.
- Current-price limit SELLs use the existing inclusive 10-second quote-freshness policy.
- Portfolio holdings are evaluated before screened BUY candidates, and the operator can see both HELD and SCREENED provenance on overlaps.
- Repeated intraday states are quiet operationally but retain exact occurrence counts and duration in audit evidence.

</specifics>

<deferred>
## Deferred Ideas

- Unattended scheduling, background service supervision, distributed leader election, and global pause/resume controls remain Phase 15.
- Automatic cancellation, market-order exits, aggressive price chasing, and forced portfolio-wide liquidation are not included in Phase 11.

</deferred>

---

*Phase: 11-KIS Portfolio Synchronization & Intraday Exit Management*
*Context gathered: 2026-09-01*
