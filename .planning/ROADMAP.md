# Roadmap: Stock Trading Bot (KR / LLM-driven)

## Milestones

- ✅ **v1.0 MVP** — Phases 1-5 (shipped 2026-07-03)
- 🚧 **v1.1 Mock Soak & Replay Validation** — Phases 6-10 (in progress)
- 📋 **v1.2 Complete Trade Lifecycle & Strategy Evidence** — Phases 11-13 (planned)
- 📋 **v1.3 Safe Automation & Controlled Production** — Phases 14-16 (planned)

## Phases

<details>
<summary>✅ v1.0 MVP (Phases 1-5) — SHIPPED 2026-07-03</summary>

- [x] **Phase 1: Foundation** — completed 2026-06-30 (3/3 plans)
- [x] **Phase 2: Mock Execution Core** — completed 2026-07-01 (3/3 plans)
- [x] **Phase 3: Data Pipeline** — completed 2026-07-01 (6/6 plans)
- [x] **Phase 4: LLM Agent** — completed 2026-07-02 (4/4 plans)
- [x] **Phase 5: Real-Money Readiness & Operations** — completed 2026-07-02 (5/5 plans)

Full phase details are archived at `.planning/milestones/v1.0-ROADMAP.md`.

</details>

### 🚧 v1.1 Mock Soak & Replay Validation (In Progress)

**Milestone Goal:** Prove through reproducible replay and repeated KIS mock-account operation that daily decisions are safe, explainable, and evidence-backed before any manual real-money promotion is considered.

- [x] **Phase 6: Audit Evidence & Cycle Boundaries** — Establish complete, correctly attributed evidence for every run, ticker, order path, and executable market window. (completed 2026-07-11)
- [x] **Phase 7: Deterministic Replay Validation** — Exercise the production decision and execution gates against frozen historical scenarios without live dependencies. (completed 2026-07-13)
- [x] **Phase 8: Decision Reports & Operator Runbook** — Make validation evidence reviewable and daily operation repeatable, including failure triage. (completed 2026-07-13)
- [ ] **Phase 9: KIS Mock Soak & Fault Drills** — Collect multi-day broker-facing mock evidence and prove recovery behavior under expected faults.
- [x] **Phase 10: Advisory Risk Calibration & Promotion Readiness** — Compare policy variants without mutation and gate any real-money consideration behind manual evidence review. (implemented 2026-08-10; re-verified 2026-10-01)

### 📋 v1.2 Complete Trade Lifecycle & Strategy Evidence (Planned)

**Milestone Goal:** Complete the broker-backed buy-hold-sell lifecycle and produce realistic, attributable strategy evidence without granting analysis tools execution authority.

- [x] **Phase 11: KIS Portfolio Synchronization & Intraday Exit Management** — Synchronize broker-held positions and safely operate daily and intraday exit paths while Phase 9 elapsed-day evidence continues collecting. (completed 2026-09-04)
- [x] **Phase 12: Full Portfolio Backtesting & Market Friction Modeling** — Evaluate the strategy chronologically across a portfolio with realistic fills, Korean fees and taxes, slippage, and no look-ahead. (completed 2026-10-01)
- [ ] **Phase 13: Historical LLM Shadow Evaluation & Model Governance** — Compare optional historical LLM signals under a cost-controlled, fully attributable, non-executable shadow workflow.

### 📋 v1.3 Safe Automation & Controlled Production (Planned)

**Milestone Goal:** Add operator visibility and resilient scheduling, then permit only an explicitly approved, capital-capped real-money pilot after every upstream safety gate passes.

- [ ] **Phase 14: Operator Web UI, Dashboard & Alerting** — Provide an authenticated responsive web application for portfolio, decision, order, validation, report, and alert workflows without adding trade authority.
- [ ] **Phase 15: Unattended Scheduling & Service Resilience** — Schedule calendar-aware daily and intraday workers with leader locking, recovery, health checks, and a global kill switch.
- [ ] **Phase 16: Controlled Real-Money Pilot & Scale Gates** — Run a manually approved, allowlisted, capital-capped pilot with evidence windows, rollback, and explicit scaling approvals.

## v1.1 Mock Soak & Replay Validation (Phase Details)

### Phase 6: Audit Evidence & Cycle Boundaries

**Goal**: Operators can trust that every cycle and ticker path is complete, attributable, and evaluated against explicit KRX timing and freshness boundaries.
**Depends on**: Phase 5
**Requirements**: EVID-01, EVID-02, EVID-03, EVID-04
**Success Criteria** (what must be TRUE):

  1. Operator can inspect every run with one terminal lifecycle state, KST trading date, run kind, execution target, policy snapshot, and input provenance.
  2. Operator can account for every attempted ticker through exactly one terminal outcome, including holds, skips, malformed signals, stale-data blocks, provider/API failures, duplicate suppression, fills, and ambiguous submissions.
  3. Operator can trace each ticker's order intent through submission and broker reconciliation, or see the exact attributed reason that no order was placed.
  4. Operator can verify the KRX session, completed-bar cutoff, quote freshness, and permitted order window used by each executable cycle.

**Plans**: 5/5 plans complete

**Wave 1**

- [x] 06-01-PLAN.md

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 06-02-PLAN.md

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 06-03-PLAN.md

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 06-04-PLAN.md

**Wave 5** *(gap closure; blocked on Wave 4 completion)*

- [x] 06-05-PLAN.md

### Phase 7: Deterministic Replay Validation

**Goal**: Operators can reproducibly exercise shipped screening, signal, risk, sizing, and execution rules against frozen historical scenarios without contacting live services.
**Depends on**: Phase 6
**Requirements**: REPLAY-01, REPLAY-02, REPLAY-03, REPLAY-04
**Success Criteria** (what must be TRUE):

  1. Operator can replay frozen historical OHLCV through the production candidate-selection, fixture-signal, parser, risk, sizing, and execution-gate path with no live LLM, KIS, Naver, or wall-clock dependency.
  2. Repeating a replay with identical fixtures, policy, revision, and initial state produces the same ordered outcomes, manifest hashes, and stable result identity.
  3. Operator can compare BUY, HOLD, and SELL outcomes across fixture scenarios to assess policy strictness without the output claiming live profitability.
  4. Replay verification visibly covers threshold boundaries, malformed signals, stale data, risk overrides, HOLD and SELL paths, and rejects look-ahead access.

**Plans**: 6/6 plans complete

- [x] 07-04-PLAN.md
- [x] 07-05-PLAN.md
- [x] 07-06-PLAN.md

**Wave 1**

- [x] 07-01-PLAN.md

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 07-02-PLAN.md

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 07-03-PLAN.md

### Phase 8: Decision Reports & Operator Runbook

**Goal**: Operators can review complete evidence in understandable reports and run the daily validation workflow safely from documented procedures.
**Depends on**: Phase 7
**Requirements**: REP-01, REP-02, RUN-01, RUN-02
**Success Criteria** (what must be TRUE):

  1. Operator can generate a KST daily decision report from SQLite that shows candidates, decisions, confidence, order outcomes, and no-trade reasons.
  2. Operator can generate period and replay summaries whose denominators, incomplete or unknown states, execution targets, and reconciliation status are explicit and reconcile to their details.
  3. Operator can follow a fixed market-session runbook for `bot status`, `bot screen`, `bot run`, and report review, including preflight, abort, and postflight checks.
  4. Operator can diagnose and safely recover from stale data, API failure, timeout, ambiguous or duplicate orders, notification failure, and audit failure using documented triage steps.

**Plans**: 6/6 plans complete
**UI hint**: yes

Plans:

- [x] 08-06-PLAN.md

**Wave 1**

- [x] 08-01-PLAN.md — Persist sanitized append-only notification delivery evidence.

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 08-02-PLAN.md — Build read-only daily, period, and replay report projections/renderers.

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 08-03-PLAN.md — Expose offline report subcommands with atomic terminal/file delivery.

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 08-04-PLAN.md — Share and enforce typed preflight evidence across status and run.

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 08-05-PLAN.md — Publish and contract-test the Korean operator runbook.

### Phase 9: KIS Mock Soak & Fault Drills

**Goal**: Operators can prove repeated, recoverable operation against the actual KIS mock environment while preserving zero-tolerance safety invariants.
**Depends on**: Phase 8
**Requirements**: SOAK-01, SOAK-02, SOAK-03, SOAK-04
**Success Criteria** (what must be TRUE):

  1. Operator can start a visibly labeled KIS mock-account soak path that cannot resolve real credentials, domains, accounts, or transaction IDs.
  2. Operator can run and review an N-eligible-KRX-day campaign with clean-streak accounting, a declared availability-failure budget, and zero tolerance for safety-invariant breaches.
  3. Operator can reconcile mock orders, fills, open orders, and account state to broker truth after duplicate reruns, ambiguous submissions, and process restarts.
  4. Operator can execute and retain evidence for the required stale-data, LLM, KIS, accepted-then-timeout, throttling, fill, interruption, notification, and audit fault drills, with synthetic drills distinguished from KIS-observed evidence.

**Plans**: 9/10 plans executed

Plans:
**Wave 1**

- [x] 09-01-PLAN.md — Establish mock-only contracts and deterministic KIS compatibility probing.

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 09-02-PLAN.md — Authenticate and approve the accepted mock profile using read-only calls.

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 09-03-PLAN.md — Build the immutable campaign and broker-evidence ledger.

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 09-04-PLAN.md — Implement complete broker-truth reconciliation and restart freezes.

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 09-09-PLAN.md — Implement the durable non-credit single-shot proof-order service and CLI path.

**Wave 6** *(blocked on Wave 5 completion)*

- [x] 09-10-PLAN.md — Approve one authenticated proof order through the implemented durable path.

**Wave 7** *(blocked on Wave 6 completion)*

- [x] 09-05-PLAN.md — Orchestrate explicit mock soak campaign commands and day accounting.

**Wave 8** *(blocked on Wave 7 completion)*

- [x] 09-06-PLAN.md — Add the independent fault controller and all required drills.

**Wave 9** *(blocked on Wave 8 completion)*

- [x] 09-07-PLAN.md — Publish read-only soak reports and the Korean operator procedure.

**Wave 10** *(blocked on Wave 9 completion)*

- [ ] 09-08-PLAN.md — Complete authenticated designated-day, drill, and 20-day UAT gates.

### Phase 10: Advisory Risk Calibration & Promotion Readiness

**Goal**: Operators can make an evidence-informed, explicitly manual decision about policy changes and real-money readiness without granting validation tools execution authority.
**Depends on**: Phase 9
**Requirements**: CAL-01, CAL-02, CAL-03, CAL-04
**Success Criteria** (what must be TRUE):

  1. Operator can compare confidence-threshold, position-cap, stop-loss, and take-profit variants in advisory reports without changing runtime or live settings.
  2. Operator can see sample counts, uncertainty and insufficient-evidence warnings, exposure changes, and risk-trigger differences before considering a policy change.
  3. Operator can complete an evidence-linked real-money promotion checklist covering replay, soak, reports, unresolved orders, policy freeze, rollback and kill procedures, and explicit manual approval.
  4. Operator can verify that replay, report, soak, and calibration commands cannot enable real-money trading or automatically mutate live configuration.

**Plans**: 4/4 plans complete

**Verification:** `passed` (2026-10-01), 24/24 must-haves verified after shared runtime schema and historical-warning gap closure; see `10-VERIFICATION.md`.

- [x] 10-01-PLAN.md
- [x] 10-02-PLAN.md
- [x] 10-03-PLAN.md
- [x] 10-04-PLAN.md

## Progress

**Execution Order:** Phase 6 → Phase 7 → Phase 8 → Phase 9 implementation → Phase 10 → Phase 11 → Phase 12 → Phase 13 → Phase 14 → Phase 15 → Phase 16. Phase 9 Plan 09-08 elapsed-day UAT continues in parallel but must pass before Phase 15 unattended operation or Phase 16 real-money pilot.

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Foundation | v1.0 | 3/3 | Complete | 2026-06-30 |
| 2. Mock Execution Core | v1.0 | 3/3 | Complete | 2026-07-01 |
| 3. Data Pipeline | v1.0 | 6/6 | Complete | 2026-07-01 |
| 4. LLM Agent | v1.0 | 4/4 | Complete | 2026-07-02 |
| 5. Real-Money Readiness & Operations | v1.0 | 5/5 | Complete | 2026-07-02 |
| 6. Audit Evidence & Cycle Boundaries | v1.1 | 5/5 | Complete    | 2026-07-11 |
| 7. Deterministic Replay Validation | v1.1 | 6/6 | Complete    | 2026-07-13 |
| 8. Decision Reports & Operator Runbook | v1.1 | 6/6 | Complete    | 2026-07-14 |
| 9. KIS Mock Soak & Fault Drills | v1.1 | 9/10 | In Progress|  |
| 10. Advisory Risk Calibration & Promotion Readiness | v1.1 | 4/4 | Complete | 2026-10-01 |
| 11. KIS Portfolio Synchronization & Intraday Exit Management | v1.2 | 9/9 | Complete   | 2026-09-04 |
| 12. Full Portfolio Backtesting & Market Friction Modeling | v1.2 | 6/6 | Complete    | 2026-10-01 |
| 13. Historical LLM Shadow Evaluation & Model Governance | v1.2 | 0/TBD | Not Planned |  |
| 14. Operator Web UI, Dashboard & Alerting | v1.3 | 0/TBD | Not Planned |  |
| 15. Unattended Scheduling & Service Resilience | v1.3 | 0/TBD | Not Planned |  |
| 16. Controlled Real-Money Pilot & Scale Gates | v1.3 | 0/TBD | Not Planned |  |

## v1.2 Complete Trade Lifecycle & Strategy Evidence (Phase Details)

### Phase 11: KIS Portfolio Synchronization & Intraday Exit Management

**Goal:** Operators can synchronize KIS broker portfolio truth into every execution cycle and safely exit held positions through daily LLM signals and intraday deterministic risk rules, with restart-safe order reconciliation.
**Requirements**: PORT-01, PORT-02, EXIT-01, EXIT-02
**Depends on:** Phase 10
**Success Criteria** (what must be TRUE):

  1. Every cycle starts from complete KIS cash, holding, orderable-quantity, average-price, open-order, and recent-fill truth; incomplete truth blocks mutation.
  2. Screened candidates and existing holdings form one attributable evaluation universe, and held positions are never dropped merely because they fail screening.
  3. The daily LLM cycle can SELL a held position while intraday deterministic risk checks can exit without repeated LLM calls.
  4. Partial fills, cancellation, ambiguity, restart, and duplicate invocation cannot oversell or create a second unjustified POST.

**Plans:** 9/9 plans complete

Plans:

- [x] 11-09-PLAN.md

- [x] 11-08-PLAN.md

- [x] 11-07-PLAN.md

**Wave 1**

- [x] 11-01-PLAN.md — Normalize and persist complete whole-account KIS portfolio truth and daily evaluation identity.

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 11-02-PLAN.md — Enforce account-scoped mutation exclusion and restart recovery before authorization.

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 11-03-PLAN.md — Build held-first daily evaluation with once-per-day LLM signals and current-gate reuse.

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 11-04-PLAN.md — Coordinate daily and intraday SELLs through one pre-POST re-gated lifecycle.

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 11-05-PLAN.md — Deliver foreground intraday check/watch with exact session and interruption behavior.

**Wave 6** *(blocked on Wave 5 completion)*

- [x] 11-06-PLAN.md — Add transition alerts, fail-closed evidence, runbook integration, and final regression coverage.

### Phase 12: Full Portfolio Backtesting & Market Friction Modeling

**Goal:** Operators can measure portfolio-level behavior under chronological capital constraints and realistic Korean-market transaction friction without contacting live providers.
**Requirements**: FUT-01
**Depends on:** Phase 11
**Success Criteria** (what must be TRUE):

  1. Multi-ticker scenarios share one chronological cash and holdings ledger, preventing impossible overlapping use of capital.
  2. Fill, fee, tax, slippage, liquidity, and partial-fill assumptions are versioned and visible in every result.
  3. Repeating identical inputs produces identical trades, equity curves, drawdowns, exposures, and result identity with no look-ahead.
  4. Reports separate gross and net results and carry an explicit modeling/forecast limitation rather than a profitability guarantee.

**Plans:** 6/6 plans complete

Plans:
**Wave 1**

- [x] 12-01-PLAN.md

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 12-02-PLAN.md

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 12-03-PLAN.md

**Wave 4** *(blocked on Wave 3 completion)*

- [x] 12-04-PLAN.md

**Wave 5** *(blocked on Wave 4 completion)*

- [x] 12-05-PLAN.md

**Wave 6** *(blocked on Wave 5 completion)*

- [x] 12-06-PLAN.md

**Cross-cutting constraints:**

- D-01: Frozen three-year requested window is explicit and incomplete history is visible.
- D-02: Point-in-time frozen data runs without online capabilities.
- D-03: Corporate actions and missing valuation preserve accountable holdings.
- D-04: Shipped signal gates and malformed HOLD behavior remain attributable.
- D-15: Identical normalized inputs and code reproduce evidence identity.
- D-08: Shared volume cap, partial fills and expiry are deterministic.
- D-11: Reviewed effective rules cover market/date and costs are explicit.
- D-12: Baseline/stress assumptions and Decimal rounding are recorded.
- D-06: One reserved ledger prevents capital reuse and oversell.
- D-09: T+2 exchange-session proceeds are distinct from settled cash.
- D-13: Gross attribution follows identical net executions.
- D-14: Korean reports expose coverage, metrics and modeled limitations.
- D-16: Validated offline commands have no live mutation or promotion authority.

### Phase 13: Historical LLM Shadow Evaluation & Model Governance

**Goal:** Operators can compare frozen fixture signals with optional historical LLM outputs while preserving deterministic replay as the canonical baseline and preventing shadow results from trading.
**Requirements**: FUT-02, GOV-01
**Depends on:** Phase 12
**Success Criteria** (what must be TRUE):

  1. Shadow runs have explicit budgets, bounded concurrency, resumable checkpoints, and no broker or configuration-write capability.
  2. Each output records provider, model, prompt, schema, input snapshot, token/cost facts, code revision, and validation outcome.
  3. Reports compare agreement, action changes, malformed/refusal rates, cost, and risk-gate effects without replacing the deterministic baseline.
  4. Promotion of a model or prompt remains a separate manual policy decision backed by immutable evidence.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 13 to break down)

## v1.3 Safe Automation & Controlled Production (Phase Details)

### Phase 14: Operator Web UI, Dashboard & Alerting

**Goal:** Operators can use an authenticated responsive web application to inspect portfolio, decision, order, validation, report, and worker-health evidence and handle non-trading operational workflows without granting the web process trade authority.
**Requirements**: FUT-03, UI-01, UI-02, OPSV-01
**Depends on:** Phase 13
**Success Criteria** (what must be TRUE):

  1. Korean desktop and mobile views cover account summary, holdings, screened candidates, LLM decisions, orders, fills, run history, reports, replay, soak, calibration, readiness, and worker health.
  2. Every displayed total drills down to durable source details and preserves UNKNOWN/INCOMPLETE states rather than smoothing them away.
  3. Operators can generate and export existing read-only reports and acknowledge alerts, while every action is authenticated, authorized, CSRF-protected, and audit logged.
  4. Alerts are severity-based, deduplicated, evidence-linked, and cover failed/stale workers, unresolved orders, safety latches, and broker divergence.
  5. The web process has no KIS order, live LLM execution, policy-write, secret-display, real-mode activation, or safety-gate waiver capability; local/private exposure is the secure default.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 14 to break down)

### Phase 15: Unattended Scheduling & Service Resilience

**Goal:** Operators can run calendar-aware daily evaluation and intraday held-position protection unattended, with exactly-once intent, durable recovery, health visibility, and immediate manual stop authority.
**Requirements**: FUT-04, AUTO-01, AUTO-02
**Depends on:** Phase 14
**Additional gate:** Phase 9 Plan 09-08 must be approved before unattended mutation is enabled.
**Success Criteria** (what must be TRUE):

  1. KRX holiday/session rules schedule one daily decision cycle and a separately bounded held-position risk worker.
  2. Leader locking, durable job identities, checkpoints, and reconciliation prevent overlapping workers or duplicate order submission after restart.
  3. Health checks detect missed schedules, stalled workers, stale market data, and notification failure; recovery remains fail closed.
  4. Manual pause, resume, dry-run, and global kill controls work without deleting audit evidence or releasing unresolved-order freezes.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 15 to break down)

### Phase 16: Controlled Real-Money Pilot & Scale Gates

**Goal:** Operators can conduct a deliberately manual, allowlisted, capital-capped real-money pilot and increase exposure only through new evidence-backed approvals.
**Requirements**: PROD-01, PROD-02
**Depends on:** Phase 15
**Additional gates:** Phase 9 acceptance, Phase 11 mock buy-hold-sell proof, Phase 12 evidence, Phase 15 resilience verification, no unresolved orders, and Phase 10 readiness PASS.
**Success Criteria** (what must be TRUE):

  1. Real mode cannot start unless every upstream evidence identity is current, all safety gates PASS, and the operator supplies a separate explicit approval.
  2. Pilot scope is restricted by an immutable symbol allowlist, capital/notional cap, order cap, and immediate kill/rollback procedure.
  3. Every pilot order uses the same freshness, idempotency, reconciliation, freeze, audit, and notification invariants proven in mock operation.
  4. Scaling requires a completed dwell/evidence window and a new approval; no tool can automatically promote, widen scope, or clear a safety breach.

**Plans:** 0 plans

Plans:

- [ ] TBD (run /gsd-plan-phase 16 to break down)
