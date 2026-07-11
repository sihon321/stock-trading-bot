# Phase 6: Audit Evidence & Cycle Boundaries - Context

**Gathered:** 2026-07-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Establish complete and correctly attributed evidence for every `bot screen` and `bot run` invocation, every attempted ticker, every order path, and every executable KRX market window. This phase defines lifecycle, outcome, order-event, timing, and freshness semantics that later replay, reporting, and soak phases consume. It does not add replay, reports, soak campaigns, calibration, scheduling, or automatic real-money promotion.

</domain>

<decisions>
## Implementation Decisions

### Run lifecycle and identity
- **D-01:** Record `bot screen` and `bot run` as runs. `bot status` is read-only and does not create a run.
- **D-02:** Use terminal run states `COMPLETED`, `COMPLETED_WITH_ERRORS`, `FAILED`, and `INTERRUPTED`; an in-progress run may use `RUNNING` but must eventually resolve to exactly one terminal state.
- **D-03:** At the start of the next `bot screen` or `bot run`, automatically close any abandoned `RUNNING` run as `INTERRUPTED`, recording recovery time and a normalized reason.
- **D-04:** Issue a new UUID `run_id` for every invocation. When an invocation is an explicit retry, link it to the prior invocation through optional `parent_run_id`; never overwrite a prior attempt.

### Ticker terminal outcomes
- **D-05:** Separate a bounded, stable `outcome_code` from the more specific `reason_code` and sanitized explanatory detail.
- **D-06:** Use run-kind-specific outcome vocabularies: screening outcomes describe selection/rejection/screening failure, while evaluation outcomes describe no-trade, suppression, submission, reconciliation, ambiguity, or execution failure.
- **D-07:** Every attempted ticker must receive exactly one terminal outcome row even when data collection, LLM invocation, parsing, risk evaluation, or order handling raises. Unknown/unavailable fields remain explicit `NULL`; failures record `failed_stage` and normalized reason.
- **D-08:** Preserve stable reason codes such as stale data, low confidence, malformed signal, provider timeout, KIS unavailability, and duplicate suppression. Store only sanitized diagnostic detail; do not store secrets, raw provider responses, tokens, or credentials.

### Order evidence chain
- **D-09:** Preserve the order path as append-only, timestamped events and retain a convenient final order-state summary on the ticker terminal outcome. Do not erase earlier evidence by updating one mutable order-history row.
- **D-10:** Assign `order_intent_id` when an order intent is created and a distinct `submission_id` for every broker submission attempt. Broker queries and reconciliation events link back to the originating intent.
- **D-11:** A submission whose acceptance cannot be determined terminates the ticker as `AMBIGUOUS_SUBMISSION`; it must not trigger a blind POST retry. Later broker inquiry appends reconciliation events to the original intent and attributes the observation to both the originating run and the later observing run.
- **D-12:** Duplicate suppression and reconciliation evidence stores normalized broker facts: observation time, KIS order ID, ticker, side, requested quantity, filled quantity, remaining quantity, and inquiry status. Duplicate suppression links the matching existing broker order. Raw KIS responses are not persisted.

### KRX cycle boundaries and freshness
- **D-13:** Permit order submission only during the conservative KRX regular-session continuous-trading window. Pre-open, after-hours, and auction windows are non-executable but their observed session state is recorded. Research/planning must confirm exact boundaries against authoritative KRX rules.
- **D-14:** During an open-market run, indicators and screening use bars only through the immediately preceding completed KRX trading day; never use the current incomplete daily bar. Record requested trading date, completed-bar cutoff, and actual last bar date.
- **D-15:** Re-fetch the KIS quote immediately before submission. At submission time the quote must be no more than 10 seconds old. Record both initial-context quote time and pre-submit quote observation time; stale quotes block the trade.
- **D-16:** If the KRX trading day or current session cannot be established, fail closed and place no order. Record KST observation time, trading date, session, executable/non-executable decision, normalized reason, and timing-policy version.

### Agent Discretion
- Choose schema/table names, enum implementation, migration mechanics, indexes, and internal service boundaries consistent with the existing SQLite and synchronous CLI patterns.
- Define the exhaustive initial code lists and event names, provided they preserve the semantic distinctions above and remain stable for downstream reports.
- Select an authoritative KRX calendar/session source and exact continuous-trading boundaries during research, with fail-closed behavior when unavailable.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone scope and requirements
- `.planning/PROJECT.md` — Core value, safety posture, shipped v1.0 state, and v1.1 milestone constraints.
- `.planning/REQUIREMENTS.md` — EVID-01 through EVID-04 and boundaries excluding replay, reports, soak, and calibration from Phase 6.
- `.planning/ROADMAP.md` — Phase 6 goal, success criteria, dependency on Phase 5, and downstream phase sequence.
- `.planning/STATE.md` — Current milestone position and accumulated constraints for evidence-first validation.

### Existing implementation contracts
- `trading_bot/sqlite_audit.py` — Current two-table audit schema and immediate-commit writer to evolve.
- `trading_bot/cli.py` — Current run orchestration, UUID/correlation construction, ticker error isolation, audit writes, and notification flow.
- `trading_bot/kis_broker.py` — Current preflight, duplicate query-before-POST, mutable last reconciliation, fill readback, and local reference behavior.
- `trading_bot/data_source.py` — Existing point-in-time OHLCV policy, source-health actions, and typed no-context outcomes.
- `tests/test_sqlite_audit.py` — Existing persistence and correlation expectations.
- `tests/test_cli.py` — Existing per-ticker isolation behavior and the known missing audit row on ticker failure.
- `tests/test_kis_broker.py` — Existing duplicate, submission, and partial-fill reconciliation behavior.
- `tests/test_data_source.py` — Existing stale-data and source-health fail-safe behavior.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `sqlite_audit.connect/start_run/write_decision`: existing WAL-backed SQLite entry points can anchor migrations and new lifecycle/outcome/event writers.
- `cli.run_cycle`: already owns run identity, ticker iteration, correlation IDs, error isolation, summary notification, and the natural run-finalization boundary.
- `CycleAuditEvent` and `DataSourceAuditEvent`: existing structured decision and source-health evidence can feed normalized terminal outcomes instead of free-text-only errors.
- `KISBroker` reconciliation helpers: query-before-POST, fill readback, duplicate detection, and normalized fill data are the starting points for append-only order events.
- `DataSourceConfig.expected_date` and `accepted_latest_date`: existing explicit date policy can be expanded to capture completed-bar cutoff evidence.

### Established Patterns
- Synchronous, manually triggered Typer commands with injected collaborators for deterministic tests.
- Fail-closed trading behavior with per-ticker error isolation and fail-soft notifications.
- SQLite writes commit immediately; structured audit data is kept separate from raw LLM/provider payloads.
- KIS order POST is never blindly retried; broker truth is queried before submission and after ambiguous outcomes.

### Integration Points
- Extend run creation/finalization around `cli.run_cycle` and the screening command path; add abandoned-run recovery before new mutable commands begin.
- Replace the exception path that currently only appends an in-memory `ERROR` outcome with a persisted terminal ticker outcome.
- Capture data-source audit details before `build_context` raises, so stale/skip outcomes retain typed attribution.
- Replace reliance on `broker.last_reconciliation` as the sole evidence channel with intent/submission/event records correlated to run and ticker.
- Insert explicit calendar/session, completed-bar, and pre-submit quote-freshness gates before broker submission.

</code_context>

<specifics>
## Specific Ideas

- Quote freshness is explicitly capped at 10 seconds at submission time.
- Run retries remain separate immutable runs and may be linked with `parent_run_id`.
- Later reconciliation of an ambiguous submission must preserve both original-run attribution and the identity of the observing run.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope. Replay belongs to Phase 7, reports/runbook to Phase 8, mock soak/fault drills to Phase 9, and calibration/promotion readiness to Phase 10.

</deferred>

---

*Phase: 6-Audit Evidence & Cycle Boundaries*
*Context gathered: 2026-07-11*
