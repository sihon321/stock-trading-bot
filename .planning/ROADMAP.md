# Roadmap: Stock Trading Bot (KR / LLM-driven)

## Overview

This roadmap builds a personal, safety-first Korean-market trading bot in dependency order:
the controls that prevent real-money loss exist before any code that can place a consequential
order. Phase 1 lays the typed-config foundation and the atomic mock/real mode guard. Phase 2
builds a fully testable mock execution core (rules risk engine + fail-safe signal parser +
dry-run executor) with zero external dependencies and zero financial risk. Phase 3 attaches
real market data (pykrx, Naver news, KIS price) to that proven core. Phase 4 plugs in the LLM
agent behind the existing provider port. Phase 5 adds idempotent real-broker execution,
per-cycle audit, notifications, and the deliberate, gated promotion to real money. Each port
(Broker, LLMProvider, DataSource) is introduced as a Protocol before its first concrete adapter,
so no phase rewrites an earlier one.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation** - Typed config/secrets, atomic mock/real TradingMode guard, domain models, and the ports skeleton (completed 2026-06-30)
- [x] **Phase 2: Mock Execution Core** - Rules risk engine, fail-safe signal parser, dry-run executor, and MockBroker — testable with zero external deps and zero financial risk (completed 2026-07-01)
- [x] **Phase 3: Data Pipeline** - pykrx OHLCV + indicators + daily screener, fail-soft Naver news, and KIS real-time price behind a shared token manager (completed 2026-07-01)
- [ ] **Phase 4: LLM Agent** - Switchable Claude/OpenAI provider behind the port, strict-JSON structured output, and context builder wired to the fail-safe parser
- [ ] **Phase 5: Real-Money Readiness & Operations** - Manual CLI trigger, per-cycle audit log, Telegram notifications, idempotent real KISBroker, and the gated real-money promotion

## Phase Details

### Phase 1: Foundation

**Goal**: A typed configuration layer that loads secrets safely, binds the trading mode atomically so a partial mock/real swap can never trade real money, and exposes the domain models and empty port Protocols everything else depends on.
**Depends on**: Nothing (first phase)
**Requirements**: CFG-01, CFG-02, CFG-03
**Success Criteria** (what must be TRUE):

  1. Operator can place all secrets (KIS appkey/secret, LLM API keys) in a gitignored `.env`, and they load through typed settings — secrets never appear in logs
  2. Selecting `mock` vs `real` in config binds KIS domain, appkey, appsecret, and TR_ID together atomically — there is no way to set them independently, and the active mode is printed in a loud startup banner
  3. Operator can select the active LLM provider (`claude` / `openai`) in config, and exactly one is resolved per run
  4. Domain models (Decision, Order, Position) and the three port Protocols (Broker, LLMProvider, DataSource) exist and import cleanly with no concrete adapters yet

**Plans**: 3/3 plans complete
Plans:
**Wave 1**

- [x] 01-01-PLAN.md — Package skeleton, env template, and SUS dependency verification checkpoint

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 01-02-PLAN.md — Typed settings, atomic KIS mode binding, LLM provider selection, and config safety tests
- [x] 01-03-PLAN.md — Domain models, synchronous semantic ports, and import/shape tests

### Phase 2: Mock Execution Core

**Goal**: A fully testable execution core — MockBroker paper account, pure-functions risk engine, and the fail-safe signal parser — that runs the parse → risk → execute → log chain end-to-end against hand-written signals with zero external calls and zero financial risk.
**Depends on**: Phase 1
**Requirements**: EXEC-01, EXEC-02, EXEC-03, EXEC-05, RISK-01, RISK-02, RISK-03
**Success Criteria** (what must be TRUE):

  1. Given a validated signal, the system issues a BUY only when `decision == "BUY"` AND `confidence >= 0.8`, and a SELL on `decision == "SELL"` (with confidence threshold) for held positions — sizing is a configurable % of capital bounded by a max-position cap
  2. A rules-based stop-loss / take-profit net evaluates held positions independent of any LLM and can SELL on its own; when it conflicts with an LLM signal on the same ticker in a cycle, the risk net wins and the LLM signal is suppressed
  3. A daily-loss kill switch halts all new BUYs for the rest of the day once the configured loss threshold is breached
  4. Any malformed or schema-invalid signal maps to HOLD (no trade), full stop — never a repaired-into-a-trade partial object
  5. Dry-run mode logs the would-be decision and order while making zero order calls and zero external state mutation

**Plans**: 3/3 plans complete
Plans:
**Wave 1**

- [x] 02-01-PLAN.md — Fail-safe signal parser and parser tests

**Wave 2** *(blocked on Wave 1 completion)*

- [x] 02-02-PLAN.md — Risk engine, execution rules, and configuration defaults

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 02-03-PLAN.md — MockBroker, dry-run audit chain, and end-to-end mock-safe tests

### Phase 3: Data Pipeline

**Goal**: Real Korean-market data attaches to the proven execution core — daily OHLCV + indicators + screener via pykrx, fail-soft sanitized Naver news, and KIS real-time price through a shared, auto-refreshed token manager — producing the typed DataContext.
**Depends on**: Phase 2
**Requirements**: DATA-01, DATA-02, DATA-03, DATA-04, DATA-05
**Success Criteria** (what must be TRUE):

  1. System fetches daily OHLCV per ticker via pykrx and fails safe to HOLD (not act on a bad frame) on holiday / empty / stale data, with the trading date asserted in Asia/Seoul
  2. System computes technical indicators (e.g. moving averages, RSI) from the daily OHLCV
  3. System runs a daily market screen (e.g. volume/momentum via pykrx) that selects the candidate-ticker universe for the cycle using point-in-time data
  4. System fetches a ticker's real-time price via the KIS API using one shared, cached, auto-refreshed access token (no per-call token re-issue) and stays under KIS rate limits
  5. System scrapes per-ticker Naver Finance news with input sanitization and graceful degradation — an empty or failed scrape means "no news" and continues the cycle, never crashes it

**Plans**: 6/6 plans complete
Plans:
**Wave 0**

- [x] 03-01-PLAN.md — Runtime compatibility, dependency legitimacy, and manual provider policy gates

**Wave 1** *(blocked on Wave 0 completion)*

- [x] 03-02-PLAN.md — Source-health models, pykrx OHLCV normalization, and indicator transforms

**Wave 2** *(blocked on required Wave 1 or Wave 0 dependencies)*

- [x] 03-03-PLAN.md — Volatility-breakout daily screener
- [x] 03-04-PLAN.md — Shared KIS token manager and current-price adapter
- [x] 03-05-PLAN.md — Compliance-gated sanitized Naver news adapter

**Wave 3** *(blocked on Wave 2 completion)*

- [x] 03-06-PLAN.md — Thin DataSource orchestrator and full Phase 3 validation

**Research hint**: KIS token TTL + exact rate limits, pykrx adjusted-price bug (#162), and unstable Naver Finance HTML are MEDIUM-confidence — run `/gsd-plan-phase --research-phase 3` to confirm against the live KIS portal and current Naver DOM during planning.

### Phase 4: LLM Agent

**Goal**: The LLM agent plugs into the already-tested parse → risk → execute chain — one switchable provider port serving Claude and OpenAI, feeding the real DataContext through provider-native strict JSON, with every signal re-validated by the fail-safe parser.
**Depends on**: Phase 3
**Requirements**: LLM-01, LLM-02, LLM-03
**Success Criteria** (what must be TRUE):

  1. System feeds the collected data context (price, indicators, delimited untrusted news) to the active provider through a single switchable provider interface — swapping Claude ↔ OpenAI is a config change, not a code change
  2. The active provider emits a strict JSON signal `{"decision","confidence","reason"}` with no markdown, enforced via provider-native structured output, with model + temperature pinned and the raw prompt/response logged for reproducibility
  3. Every signal is re-validated against the shared schema regardless of provider, and any malformed or unparseable output fails safe to HOLD — scraped news inside the prompt can never be followed as instructions

**Plans**: 1/4 plans executed
Plans:
**Wave 1**

- [x] 04-01-PLAN.md — Dependency lock gate (anthropic/openai/structlog pins + OpenAI model ID + D-07 temperature divergence) and Settings LLM pinning
- [ ] 04-02-PLAN.md — Versioned system prompt + pure DataContext render and the TradeSignal pydantic mirror with lockstep guard

**Wave 2** *(blocked on Wave 1 completion)*

- [ ] 04-03-PLAN.md — Claude (forced strict tool use, no temperature) and OpenAI (chat.completions.parse) adapters with parse_signal re-validation, bounded retry, and the structlog reproducibility line

**Wave 3** *(blocked on Wave 2 completion)*

- [ ] 04-04-PLAN.md — build_llm_provider switchable factory (lazy SDK imports) and run_llm_cycle wiring (LLMProviderError → HOLD) into the proven execution chain

### Phase 5: Real-Money Readiness & Operations

**Goal**: The operator can run the full cycle on demand, every cycle is auditable and pushed to a notification channel, and real-money trading becomes possible only through an idempotent, reconciled KISBroker behind a deliberate promotion gate.
**Depends on**: Phase 4
**Requirements**: OPS-01, OPS-02, OPS-03, EXEC-04, CFG-04
**Success Criteria** (what must be TRUE):

  1. Operator triggers a full evaluation cycle on demand via a manual CLI command (no scheduler), and the bot defaults to `mock` mode — switching to `real` requires an explicit, deliberate, confirmed config change
  2. Orders route through the KIS API against the configured account (mock first) idempotently — the system reconciles against broker truth before resubmitting and never blind-retries an order POST, modeling partial fills
  3. Every cycle's data context, LLM signal, risk decisions, and order outcome are written to a persistent, reviewable audit store
  4. Each cycle's decision and order outcome are pushed to the operator via a notification channel (e.g. Telegram)

**Plans**: TBD
**Research hint**: KIS order params (TR_ID prefixes, hashkey, tick-size bands, market-hours codes) and the reconciliation/idempotency flow need API-specific verification before any real-money path — run `/gsd-plan-phase --research-phase 5` during planning.

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 3/3 | Complete    | 2026-06-30 |
| 2. Mock Execution Core | 3/3 | Complete    | 2026-07-01 |
| 3. Data Pipeline | 6/6 | Complete    | 2026-07-01 |
| 4. LLM Agent | 1/4 | In Progress|  |
| 5. Real-Money Readiness & Operations | 0/TBD | Not started | - |
