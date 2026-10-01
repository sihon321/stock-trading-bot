# Requirements: Stock Trading Bot (KR / LLM-driven)

**Defined:** 2026-07-11
**Core Value:** Given fresh market data, the bot produces a trustworthy, machine-checkable trading signal and acts on it through KIS without placing an order the rules do not justify.

## v1.1 Requirements

Requirements for the Mock Soak & Replay Validation milestone. Each requirement maps to exactly one roadmap phase.

### Evidence & Audit

- [x] **EVID-01**: Operator can see every run recorded with a terminal lifecycle state, KST trading date, run kind, execution target, policy snapshot, and input provenance.
- [x] **EVID-02**: Operator can trace every attempted ticker to one terminal outcome, including HOLD, skip, malformed signal, stale-data block, provider/API error, duplicate suppression, fill status, and ambiguous submission.
- [x] **EVID-03**: Operator can verify that order intent, submission, broker reconciliation, and no-trade reasons are attributed to the correct ticker and run.
- [x] **EVID-04**: Operator can verify the KRX session, completed-bar cutoff, quote freshness, and order window used for each executable cycle.

### Deterministic Replay

- [x] **REPLAY-01**: Operator can replay historical OHLCV through the production screener, fixture signal, parser, risk rules, sizing, and execution gate without live LLM, KIS, Naver, or wall-clock dependencies.
- [x] **REPLAY-02**: Operator can inspect a deterministic replay manifest containing fixture hashes, policy snapshot, code revision, initial state, ordered outcomes, and a stable result identity.
- [x] **REPLAY-03**: Operator can compare BUY, HOLD, and SELL outcomes across fixture scenarios to judge whether the BUY policy is too strict or too loose without presenting replay results as live profitability.
- [x] **REPLAY-04**: Replay verification covers threshold boundaries, malformed signals, stale data, risk overrides, HOLD and SELL paths, and no-look-ahead constraints.

### Reports & Runbook

- [x] **REP-01**: Operator can generate a daily decision report from SQLite showing candidates, signal decisions, confidence, order outcomes, and no-trade reasons.
- [x] **REP-02**: Operator can generate period and replay summaries with explicit denominators, incomplete or unknown states, execution target, and reconciliation status.
- [x] **RUN-01**: Operator can follow a runbook for `bot status`, `bot screen`, `bot run`, and report review at fixed market-session times.
- [x] **RUN-02**: Operator can follow documented failure triage for stale data, API failure, timeout, ambiguous order, duplicate order, notification failure, and audit failure.

### KIS Mock Soak

- [x] **SOAK-01**: Operator can run an explicit KIS mock-account soak path that cannot select real credentials, domains, accounts, or transaction IDs.
- [x] **SOAK-02**: Operator can run and review an N-eligible-KRX-day mock soak campaign with clean-streak accounting, a declared availability-failure budget, and zero-tolerance safety invariants.
- [x] **SOAK-03**: Operator can verify broker-truth reconciliation for mock-account orders, fills, open orders, account state, duplicate reruns, ambiguous submissions, and restart recovery.
- [x] **SOAK-04**: Operator can run and record fault drills for stale data, malformed or timed-out LLM responses, KIS API failure, accepted-then-timeout orders, throttling, partial or no fill, interruption, notification failure, and audit failure.

### Risk Calibration & Promotion

- [x] **CAL-01**: Operator can compare policy variants for confidence threshold, position cap, stop-loss, and take-profit through advisory reports only.
- [x] **CAL-02**: Operator can see sample counts, uncertainty warnings, exposure changes, risk triggers, and insufficient-evidence warnings before considering policy changes.
- [x] **CAL-03**: Operator can complete a real-money promotion checklist tied to replay, soak, and report evidence, unresolved-order checks, policy freeze, rollback and kill procedures, and explicit manual approval.
- [x] **CAL-04**: No replay, report, soak, or calibration command can automatically mutate live settings or enable real-money trading.

## Future Requirements

Planned beyond v1.1 in the v1.2 and v1.3 roadmap. These remain unchecked until their
own phase verification passes; planning them does not weaken the Phase 9 soak or manual
real-money promotion gates.

### Portfolio Truth & Exit Lifecycle

- [x] **PORT-01**: Every executable cycle can load complete KIS broker truth for cash, holdings, orderable quantity, average price, open orders, and recent fills before making a decision.
- [x] **PORT-02**: The daily execution universe is the union of screened candidates and broker-held positions, with stale or incomplete held-position evidence failing closed without dropping the holding from review.
- [x] **EXIT-01**: Operator can run one daily LLM BUY/HOLD/SELL evaluation while deterministic stop-loss, take-profit, and kill rules monitor held positions intraday without repeated LLM calls.
- [x] **EXIT-02**: SELL orders, partial fills, cancellations, ambiguous acknowledgements, restarts, and duplicate invocations reconcile to broker truth without overselling or blind resubmission.

### Extended Validation

- [x] **FUT-01**: Operator can run a full chronological portfolio backtest with modeled fills, fees, Korean-market taxes, and slippage.
- [x] **FUT-02**: Operator can optionally compare fixture signals with historical live-LLM decisions under a separate cost-controlled, non-executable workflow.
- [x] **GOV-01**: Every shadow LLM result is attributable to provider, model, prompt, schema, input snapshot, cost, and code revision and cannot mutate trading policy.
- [ ] **FUT-03**: Operator can review validation, portfolio, order, soak, calibration, readiness, and worker-health evidence in an authenticated responsive web application.
- [ ] **UI-01**: Korean desktop and mobile views cover account summary, holdings, candidates, LLM decisions, orders, fills, run history, reports, replay, soak, calibration, readiness, and worker health with drill-down to durable evidence.
- [ ] **UI-02**: Web actions are limited to authenticated non-trading workflows such as report generation/export and alert acknowledgement; the web process cannot order, invoke a live LLM, write policy, reveal secrets, enable real mode, or waive a safety gate.
- [ ] **OPSV-01**: Operator receives deduplicated, severity-based alerts for stale workers, failed cycles, unresolved orders, safety latches, and broker-state divergence.
- [ ] **FUT-04**: Operator can schedule unattended cycles only after manual-operation evidence is sufficient.
- [ ] **AUTO-01**: Scheduled daily and intraday workers use KRX calendar/session rules, leader locking, durable checkpoints, and idempotent invocation identities so one logical job cannot submit twice.
- [ ] **AUTO-02**: Operator can pause, resume, inspect health, recover after restart, and activate a global kill switch without losing audit or reconciliation evidence.

### Controlled Production

- [ ] **PROD-01**: Operator can start a manually approved, allowlisted, capital-capped real-money pilot only when all replay, soak, exit-lifecycle, automation, unresolved-order, and readiness gates are PASS.
- [ ] **PROD-02**: Any increase in symbols or capital requires a new evidence window, explicit approval, rollback proof, and zero unresolved safety breaches; automatic promotion remains impossible.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Automatic threshold optimization or policy writes | Calibration must remain advisory and manually approved for safety. |
| Automatic real-money promotion | Real-money enablement requires explicit human approval and remains outside validation commands. |
| Live LLM calls inside deterministic replay | Phase 13 keeps optional LLM shadow evaluation separate so the canonical replay remains frozen and reproducible. |
| Automatic strategy optimization | Backtest and calibration outputs remain advisory; they cannot select or write a production policy. |
| Strategy expansion or ensemble models | The milestone calibrates and validates the shipped strategy rather than adding new strategies. |

## Traceability

Updated during roadmap creation. Every v1.1 requirement must map to exactly one phase.

| Requirement | Phase | Status |
|-------------|-------|--------|
| EVID-01 | Phase 6 | Complete |
| EVID-02 | Phase 6 | Complete |
| EVID-03 | Phase 6 | Complete |
| EVID-04 | Phase 6 | Complete |
| REPLAY-01 | Phase 7 | Complete |
| REPLAY-02 | Phase 7 | Complete |
| REPLAY-03 | Phase 7 | Complete |
| REPLAY-04 | Phase 7 | Complete |
| REP-01 | Phase 8 | Complete |
| REP-02 | Phase 8 | Complete |
| RUN-01 | Phase 8 | Complete |
| RUN-02 | Phase 8 | Complete |
| SOAK-01 | Phase 9 | Complete |
| SOAK-02 | Phase 9 | Complete |
| SOAK-03 | Phase 9 | Complete |
| SOAK-04 | Phase 9 | Complete |
| CAL-01 | Phase 10 | Complete |
| CAL-02 | Phase 10 | Complete |
| CAL-03 | Phase 10 | Complete |
| CAL-04 | Phase 10 | Complete |

**Coverage:**

- v1.1 requirements: 20 total
- Mapped to phases: 20
- Unmapped: 0 ✓

### Future Roadmap Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| PORT-01 | Phase 11 | Planned |
| PORT-02 | Phase 11 | Planned |
| EXIT-01 | Phase 11 | Planned |
| EXIT-02 | Phase 11 | Planned |
| FUT-01 | Phase 12 | Planned |
| FUT-02 | Phase 13 | Complete |
| GOV-01 | Phase 13 | Complete |
| FUT-03 | Phase 14 | Planned |
| UI-01 | Phase 14 | Planned |
| UI-02 | Phase 14 | Planned |
| OPSV-01 | Phase 14 | Planned |
| FUT-04 | Phase 15 | Planned |
| AUTO-01 | Phase 15 | Planned |
| AUTO-02 | Phase 15 | Planned |
| PROD-01 | Phase 16 | Planned |
| PROD-02 | Phase 16 | Planned |

**Future coverage:** 16 requirements mapped, 0 unmapped.

---
*Requirements defined: 2026-07-11*
*Last updated: 2026-08-25 after adding the v1.2-v1.3 future roadmap*
