# Requirements: Stock Trading Bot (KR / LLM-driven)

**Defined:** 2026-06-30
**Core Value:** Given fresh market data, the bot produces a trustworthy, machine-checkable trading signal and acts on it through KIS — without placing an order the rules don't justify.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Configuration & Safety Foundation

- [x] **CFG-01**: Operator can configure all secrets (KIS appkey/secret, LLM API keys) via a gitignored `.env`, loaded through typed settings; secrets never appear in logs
- [x] **CFG-02**: Operator selects trading mode (`mock` / `real`) in config; the mock/real switch binds KIS domain, appkey, appsecret, and TR_ID atomically so a partial swap can never trade real money by accident
- [x] **CFG-03**: Operator selects the active LLM provider (`claude` / `openai`) in config; exactly one is active per run
- [ ] **CFG-04**: System defaults to `mock` mode; switching to `real` requires an explicit, deliberate config change

### Data Pipeline

- [ ] **DATA-01**: System fetches daily OHLCV per ticker via `pykrx`, failing safe to HOLD on holiday/empty/stale data rather than acting on a bad frame
- [ ] **DATA-02**: System computes technical indicators (e.g. moving averages, RSI) from the daily OHLCV
- [ ] **DATA-03**: System fetches real-time price for a ticker via the KIS API using a shared, auto-refreshed access token
- [ ] **DATA-04**: System scrapes per-ticker financial news from Naver Finance, with basic input sanitization and graceful degradation (continue without news on scrape failure)
- [ ] **DATA-05**: System runs a daily screen over the market (e.g. volume/momentum via `pykrx`) to select candidate tickers for the evaluation cycle

### LLM Agent

- [ ] **LLM-01**: System feeds the collected data context (price, indicators, news) to the active provider through a single switchable provider interface
- [ ] **LLM-02**: The LLM must emit a strict JSON signal `{"decision","confidence","reason"}` with no markdown, enforced via provider-native structured output
- [ ] **LLM-03**: Every signal is re-validated against a shared schema; any malformed/unparseable output fails safe to no-trade (HOLD), independent of provider

### Trade Execution

- [x] **EXEC-01**: System parses the validated signal and issues a BUY only when `decision == "BUY"` AND `confidence >= 0.8`
- [x] **EXEC-02**: BUY position sizing is a configurable % of available capital, bounded by a max-position cap
- [x] **EXEC-03**: System issues a SELL on `decision == "SELL"` (with confidence threshold) for tickers currently held
- [ ] **EXEC-04**: All orders route through the KIS API against the configured account (mock first); order placement is idempotent — the system reconciles against broker truth before resubmitting and never blind-retries an order POST
- [ ] **EXEC-05**: Dry-run mode logs the would-be decision and order without placing it

### Risk Net (LLM-independent)

- [x] **RISK-01**: A rules-based stop-loss / take-profit net evaluates held positions independent of the LLM and can SELL on its own
- [x] **RISK-02**: When the risk net and an LLM signal conflict on the same ticker in a cycle, the risk net takes precedence (LLM signal is suppressed)
- [x] **RISK-03**: A daily-loss kill switch halts all new trading for the rest of the day once a configured daily loss threshold is breached

### Operations & Observability

- [ ] **OPS-01**: Operator triggers a full evaluation cycle on demand (manual CLI trigger; no scheduler in v1)
- [ ] **OPS-02**: System logs every cycle's data context, LLM signal, risk decisions, and order outcome to a persistent, reviewable audit store
- [ ] **OPS-03**: System pushes each cycle's decision and order outcome to the operator via a notification channel (e.g. Telegram)

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Validation Tooling

- **BACKTEST-01**: Historical backtest / replay harness to validate strategy against past data
- **BACKTEST-02**: Paper-trading mode separate from the KIS mock account

### Advanced Safety

- **HARDEN-01**: Dedicated prompt-injection hardening for scraped news (quarantined sentiment model / dual-LLM privilege separation that cannot act)
- **HARDEN-02**: LLM decision reproducibility controls (temperature pinning + decision audit replay)

### Automation & Strategy

- **AUTO-01**: Scheduled / always-on intraday evaluation loop
- **ENSEMBLE-01**: Ensemble / consensus across both LLM providers
- **PORT-01**: Multi-strategy portfolio allocation across signals

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Non-Korean markets | KIS + pykrx are KR-specific by design |
| Always-on intraday loop | v1 is manual-trigger only; keeps the operator in the loop while logic is unproven (deferred to AUTO-01) |
| LLM ensemble/consensus | Switchable single provider is simpler for v1 (deferred to ENSEMBLE-01) |
| Portfolio optimization / multi-strategy allocation | Single-signal execution for v1 (deferred to PORT-01) |
| LLM owning position size or stop levels | Safety anti-feature — the deterministic rules layer must own all trade math; the LLM only proposes a signal |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| CFG-01 | Phase 1 | Complete |
| CFG-02 | Phase 1 | Complete |
| CFG-03 | Phase 1 | Complete |
| CFG-04 | Phase 5 | Pending |
| DATA-01 | Phase 3 | Pending |
| DATA-02 | Phase 3 | Pending |
| DATA-03 | Phase 3 | Pending |
| DATA-04 | Phase 3 | Pending |
| DATA-05 | Phase 3 | Pending |
| LLM-01 | Phase 4 | Pending |
| LLM-02 | Phase 4 | Pending |
| LLM-03 | Phase 4 | Pending |
| EXEC-01 | Phase 2 | Complete |
| EXEC-02 | Phase 2 | Complete |
| EXEC-03 | Phase 2 | Complete |
| EXEC-04 | Phase 5 | Pending |
| EXEC-05 | Phase 2 | Pending |
| RISK-01 | Phase 2 | Complete |
| RISK-02 | Phase 2 | Complete |
| RISK-03 | Phase 2 | Complete |
| OPS-01 | Phase 5 | Pending |
| OPS-02 | Phase 5 | Pending |
| OPS-03 | Phase 5 | Pending |

**Coverage:**

- v1 requirements: 23 total
- Mapped to phases: 23
- Unmapped: 0 ✓

---
*Requirements defined: 2026-06-30*
*Last updated: 2026-06-30 after initial definition*
