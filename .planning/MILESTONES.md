# Milestones

## v1.0 MVP (Shipped: 2026-07-03)

**Delivered:** A personal, safety-first Korean-market LLM trading bot that turns fresh
market data into a machine-checkable trading signal and acts on it through KIS — validated
end-to-end on the mock (모의투자) account behind a deliberate real-money promotion gate.

**Phases completed:** 5 phases, 21 plans, 40 tasks
**Stats:** 150 commits · ~11,272 LOC Python · 48 tracked modules · 22 test files
**Timeline:** 2026-06-30 → 2026-07-03 (~4 days)
**Requirements:** 23/23 v1 requirements shipped and verified
**Closeout:** verified_closeout (all phases verification-passed; artifact audit clear)

**Key accomplishments:**

- **Phase 1 — Foundation:** Typed Pydantic settings with secret redaction, an **atomic mock/real
  KIS mode binding** (domain + appkey + secret + TR_ID swap together, so a partial swap can never
  trade real money), one-active-provider LLM selection, and the domain models + three port
  Protocols (Broker, LLMProvider, DataSource) everything else builds on.
- **Phase 2 — Mock Execution Core:** A fully testable parse → risk → execute → log chain with zero
  external deps — a fail-safe `parse_signal` (unparseable output ⇒ HOLD), an LLM-independent risk
  net (stop-loss / take-profit + daily-loss kill switch) that overrides conflicting LLM signals,
  %-of-capital sizing with a max-position cap, a deterministic `MockBroker`, and a dry-run gate
  proving zero broker mutation.
- **Phase 3 — Data Pipeline:** Real KR market data behind the proven core — pykrx OHLCV +
  indicators + a volatility-breakout daily screener, a shared auto-refreshed KIS token manager with
  a fail-safe current-price adapter, and sanitized fail-soft Naver Finance news, all assembled into
  a typed `DataContext` under a hybrid freshness policy (SKIP_CANDIDATE / FORCE_HOLD on bad data).
- **Phase 4 — LLM Agent:** A single switchable Claude/OpenAI provider port with provider-native
  strict JSON structured output, versioned prompt rendering, bounded retry, reproducibility logging,
  and re-validation through the Phase 2 fail-safe parser (malformed output ⇒ HOLD).
- **Phase 5 — Real-Money Readiness & Operations:** An **idempotent, reconciled `KISBroker`**
  (query-before-POST, never blind-retries an order POST, partial-fill readback), a two-table SQLite
  audit log, fail-soft Discord notifications, and a manual Typer CLI (`bot run/screen/status`) with
  a dry-run default and a layered, confirmed real-money promotion gate.

---
