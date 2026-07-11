# Roadmap: Stock Trading Bot (KR / LLM-driven)

## Milestones

- ✅ **v1.0 MVP** — Phases 1-5 (shipped 2026-07-03)
- 🚧 **v1.1 Mock Soak & Replay Validation** — Phases 6-10 (in progress)

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
- [ ] **Phase 7: Deterministic Replay Validation** — Exercise the production decision and execution gates against frozen historical scenarios without live dependencies.
- [ ] **Phase 8: Decision Reports & Operator Runbook** — Make validation evidence reviewable and daily operation repeatable, including failure triage.
- [ ] **Phase 9: KIS Mock Soak & Fault Drills** — Collect multi-day broker-facing mock evidence and prove recovery behavior under expected faults.
- [ ] **Phase 10: Advisory Risk Calibration & Promotion Readiness** — Compare policy variants without mutation and gate any real-money consideration behind manual evidence review.

## Phase Details

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

**Plans**: TBD

### Phase 8: Decision Reports & Operator Runbook

**Goal**: Operators can review complete evidence in understandable reports and run the daily validation workflow safely from documented procedures.
**Depends on**: Phase 7
**Requirements**: REP-01, REP-02, RUN-01, RUN-02
**Success Criteria** (what must be TRUE):

  1. Operator can generate a KST daily decision report from SQLite that shows candidates, decisions, confidence, order outcomes, and no-trade reasons.
  2. Operator can generate period and replay summaries whose denominators, incomplete or unknown states, execution targets, and reconciliation status are explicit and reconcile to their details.
  3. Operator can follow a fixed market-session runbook for `bot status`, `bot screen`, `bot run`, and report review, including preflight, abort, and postflight checks.
  4. Operator can diagnose and safely recover from stale data, API failure, timeout, ambiguous or duplicate orders, notification failure, and audit failure using documented triage steps.

**Plans**: TBD
**UI hint**: yes

### Phase 9: KIS Mock Soak & Fault Drills

**Goal**: Operators can prove repeated, recoverable operation against the actual KIS mock environment while preserving zero-tolerance safety invariants.
**Depends on**: Phase 8
**Requirements**: SOAK-01, SOAK-02, SOAK-03, SOAK-04
**Success Criteria** (what must be TRUE):

  1. Operator can start a visibly labeled KIS mock-account soak path that cannot resolve real credentials, domains, accounts, or transaction IDs.
  2. Operator can run and review an N-eligible-KRX-day campaign with clean-streak accounting, a declared availability-failure budget, and zero tolerance for safety-invariant breaches.
  3. Operator can reconcile mock orders, fills, open orders, and account state to broker truth after duplicate reruns, ambiguous submissions, and process restarts.
  4. Operator can execute and retain evidence for the required stale-data, LLM, KIS, accepted-then-timeout, throttling, fill, interruption, notification, and audit fault drills, with synthetic drills distinguished from KIS-observed evidence.

**Plans**: TBD

### Phase 10: Advisory Risk Calibration & Promotion Readiness

**Goal**: Operators can make an evidence-informed, explicitly manual decision about policy changes and real-money readiness without granting validation tools execution authority.
**Depends on**: Phase 9
**Requirements**: CAL-01, CAL-02, CAL-03, CAL-04
**Success Criteria** (what must be TRUE):

  1. Operator can compare confidence-threshold, position-cap, stop-loss, and take-profit variants in advisory reports without changing runtime or live settings.
  2. Operator can see sample counts, uncertainty and insufficient-evidence warnings, exposure changes, and risk-trigger differences before considering a policy change.
  3. Operator can complete an evidence-linked real-money promotion checklist covering replay, soak, reports, unresolved orders, policy freeze, rollback and kill procedures, and explicit manual approval.
  4. Operator can verify that replay, report, soak, and calibration commands cannot enable real-money trading or automatically mutate live configuration.

**Plans**: TBD

## Progress

**Execution Order:** Phase 6 → Phase 7 → Phase 8 → Phase 9 → Phase 10

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Foundation | v1.0 | 3/3 | Complete | 2026-06-30 |
| 2. Mock Execution Core | v1.0 | 3/3 | Complete | 2026-07-01 |
| 3. Data Pipeline | v1.0 | 6/6 | Complete | 2026-07-01 |
| 4. LLM Agent | v1.0 | 4/4 | Complete | 2026-07-02 |
| 5. Real-Money Readiness & Operations | v1.0 | 5/5 | Complete | 2026-07-02 |
| 6. Audit Evidence & Cycle Boundaries | v1.1 | 5/5 | Complete    | 2026-07-11 |
| 7. Deterministic Replay Validation | v1.1 | 0/TBD | Not started | - |
| 8. Decision Reports & Operator Runbook | v1.1 | 0/TBD | Not started | - |
| 9. KIS Mock Soak & Fault Drills | v1.1 | 0/TBD | Not started | - |
| 10. Advisory Risk Calibration & Promotion Readiness | v1.1 | 0/TBD | Not started | - |
