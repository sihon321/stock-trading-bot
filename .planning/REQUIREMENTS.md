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

- [ ] **REP-01**: Operator can generate a daily decision report from SQLite showing candidates, signal decisions, confidence, order outcomes, and no-trade reasons.
- [ ] **REP-02**: Operator can generate period and replay summaries with explicit denominators, incomplete or unknown states, execution target, and reconciliation status.
- [ ] **RUN-01**: Operator can follow a runbook for `bot status`, `bot screen`, `bot run`, and report review at fixed market-session times.
- [ ] **RUN-02**: Operator can follow documented failure triage for stale data, API failure, timeout, ambiguous order, duplicate order, notification failure, and audit failure.

### KIS Mock Soak

- [ ] **SOAK-01**: Operator can run an explicit KIS mock-account soak path that cannot select real credentials, domains, accounts, or transaction IDs.
- [ ] **SOAK-02**: Operator can run and review an N-eligible-KRX-day mock soak campaign with clean-streak accounting, a declared availability-failure budget, and zero-tolerance safety invariants.
- [ ] **SOAK-03**: Operator can verify broker-truth reconciliation for mock-account orders, fills, open orders, account state, duplicate reruns, ambiguous submissions, and restart recovery.
- [ ] **SOAK-04**: Operator can run and record fault drills for stale data, malformed or timed-out LLM responses, KIS API failure, accepted-then-timeout orders, throttling, partial or no fill, interruption, notification failure, and audit failure.

### Risk Calibration & Promotion

- [ ] **CAL-01**: Operator can compare policy variants for confidence threshold, position cap, stop-loss, and take-profit through advisory reports only.
- [ ] **CAL-02**: Operator can see sample counts, uncertainty warnings, exposure changes, risk triggers, and insufficient-evidence warnings before considering policy changes.
- [ ] **CAL-03**: Operator can complete a real-money promotion checklist tied to replay, soak, and report evidence, unresolved-order checks, policy freeze, rollback and kill procedures, and explicit manual approval.
- [ ] **CAL-04**: No replay, report, soak, or calibration command can automatically mutate live settings or enable real-money trading.

## Future Requirements

Deferred beyond v1.1 and not included in the current roadmap.

### Extended Validation

- **FUT-01**: Operator can run a full portfolio backtest with modeled fills, fees, taxes, and slippage.
- **FUT-02**: Operator can optionally compare fixture signals with historical live-LLM decisions under a separate cost-controlled workflow.
- **FUT-03**: Operator can review validation data in a web dashboard.
- **FUT-04**: Operator can schedule unattended cycles after manual-operation evidence is sufficient.

## Out of Scope

| Feature | Reason |
|---------|--------|
| Automatic threshold optimization or policy writes | Calibration must remain advisory and manually approved for safety. |
| Automatic real-money promotion | Real-money enablement requires explicit human approval and remains outside validation commands. |
| Live LLM calls during historical replay | Frozen fixture signals are required for deterministic, low-cost replay. |
| Full P&L backtester | v1.1 validates decision and execution gates, not strategy profitability with market microstructure. |
| Web dashboard | Human-readable CLI reports are sufficient for this milestone. |
| Always-on loop or intraday polling | Daily manual operation remains the validation model until promotion evidence is complete. |
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
| REP-01 | Phase 8 | Pending |
| REP-02 | Phase 8 | Pending |
| RUN-01 | Phase 8 | Pending |
| RUN-02 | Phase 8 | Pending |
| SOAK-01 | Phase 9 | Pending |
| SOAK-02 | Phase 9 | Pending |
| SOAK-03 | Phase 9 | Pending |
| SOAK-04 | Phase 9 | Pending |
| CAL-01 | Phase 10 | Pending |
| CAL-02 | Phase 10 | Pending |
| CAL-03 | Phase 10 | Pending |
| CAL-04 | Phase 10 | Pending |

**Coverage:**

- v1.1 requirements: 20 total
- Mapped to phases: 20
- Unmapped: 0 ✓

---
*Requirements defined: 2026-07-11*
*Last updated: 2026-07-11 after v1.1 roadmap creation*
