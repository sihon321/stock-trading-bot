# Project Research Summary

**Project:** Stock Trading Bot (KR / LLM-driven)
**Domain:** Personal, Korean-market, LLM-driven automated stock trading bot (Python; three pipelines: data -> LLM signal -> KIS execution)
**Researched:** 2026-06-30
**Confidence:** MEDIUM-HIGH

## Executive Summary

This is a personal, safety-first automated trading bot for Korean equities that feeds collected market data (pykrx daily bars + indicators, KIS real-time prices, scraped Naver Finance news) into a switchable LLM (Claude or OpenAI), which must emit a strict JSON signal `{decision, confidence, reason}`, and then executes that signal through the KIS Open API — starting on the mock (모의투자) account and only later promoting to real money. Experts build systems like this as a **layered pipeline-and-ports (hexagonal) architecture**: a single orchestrator runs one evaluation cycle (screen -> collect -> build context -> prompt -> parse -> risk-check -> execute -> log) talking only to abstract ports, with concrete adapters (pykrx/KIS/Naver, Claude/OpenAI, Mock/Real broker) wired once in a composition root. This makes Claude<->OpenAI and mock<->real config switches, not rewrites.

The recommended stack is largely settled and uncontroversial: **`python-kis`** (Soju06) for KIS access (native mock support, token management, websocket — avoid the unmaintained `mojito2`), **`pykrx`** for daily KRX data, **`ta`** (pure-Python, no C dependency) for indicators, the official **`anthropic`**/**`openai`** SDKs behind one `LLMProvider` interface using forced tool use / `parse()` for guaranteed schema conformance, **`pydantic`** as the single source of truth for both the `DataContext` (LLM input) and `TradeSignal` (LLM output) contracts, **`pydantic-settings`** + gitignored `.env` for secrets, **SQLite + JSONL** for the per-cycle audit log, and a **`typer`** CLI for the manual v1 trigger (no scheduler). The only genuine judgment call is the indicator library; everything else is a clear "use X because Y."

The dominant risk theme is that **untrusted/non-deterministic inputs sit directly upstream of real money**. The non-negotiable mitigations: a deterministic rules layer (confidence gate, % sizing + max cap, LLM-independent stop-loss/take-profit, daily-loss kill switch) that the LLM can never bypass; a strict fail-safe parser where any malformed/invalid output maps to HOLD; an atomic `TradingMode` enum that binds domain+appkey+appsecret+TR_ID together so mock can never silently become real; idempotent order execution with reconciliation (never blind-retry an order POST); broker-as-source-of-truth position reconciliation every cycle; and treating scraped Naver news as untrusted input (delimited, quarantined, with a rules backstop) to defend against indirect prompt injection that could manufacture a high-confidence BUY. These safety controls are table stakes for *not losing money to a bug*, not polish.

## Key Findings

### Recommended Stack

The stack is a typed Python project with one shared pydantic v2 across the whole codebase. KIS access goes through the actively maintained `python-kis` (which natively supports the mock account and manages tokens), KRX daily data through `pykrx`, indicators through pure-Python `ta` (avoiding TA-Lib's C-install pain), and both LLM providers through their official SDKs behind a single switchable interface that uses provider-native structured output for hard schema guarantees. See STACK.md for full version pins and rationale.

**Core technologies:**
- `python-kis` 2.1.6 (Python 3.12): KIS real-time prices + order execution — only maintained KIS library with native mock support, token issuance/refresh, websocket
- `pykrx` 1.2.8: daily OHLCV + screening fundamentals — de-facto KRX standard, no API key
- `ta` 0.11.0: technical indicators — pure-Python, no C dependency (pykrx returns raw OHLCV only)
- `anthropic` / `openai` (behind one `LLMProvider`): the decision — forced tool use (`strict:true`) / `parse()` guarantee schema-conformant JSON
- `pydantic` 2.x + `pydantic-settings`: single source of truth for the `TradeSignal`/`DataContext` contracts and typed secrets from `.env`
- `typer` CLI + `structlog` + `sqlite3`/JSONL: manual v1 trigger, structured logs, per-cycle audit trail

### Expected Features

FEATURES.md is explicit that a set of rows are **[SAFETY-CRITICAL]** — the controls between the bot and an unrecoverable real-money loss — and must be P1, never bypassable by an LLM path.

**Must have (table stakes, v1 / mock-only):**
- KIS auth + token caching; pykrx OHLCV + local indicators; daily universe screening; KIS real-time price; Naver news scrape (fail-soft)
- Switchable LLM provider with strict JSON + pydantic validation; **fail-safe parse -> HOLD**; **confidence gating (BUY >= 0.8)**
- **% -of-capital sizing + max-position cap**; **rules stop-loss/take-profit independent of LLM**; position reconciliation from KIS
- **Dry-run mode**; **mock-account-first order placement**; **per-cycle audit log (JSONL)**; manual-trigger CLI

**Should have (competitive / gates real money):**
- Daily-loss limit / kill switch (strongly consider in v1) — caps a bad day, not just a bad trade
- Idempotent order execution (dedup/client-order-id + reconciliation); Telegram notifications; reproducibility metadata (model id, prompt version, raw I/O)

**Defer (v2+):**
- Backtest / paper-trading harness (high effort); LLM-as-sanity-check architecture; ensemble LLMs; cost/token dashboard; scheduled/intraday loop (explicitly out of scope)

### Architecture Approach

A layered pipeline-and-ports (hexagonal) design: one orchestrator runs the seven-step cycle depending only on three port seams (DataSource, LLMProvider, Broker), with a composition root selecting concrete adapters from config. The KIS token/hashkey machinery lives in its own shared `KISClient` (used by both price reads and order placement), and the security-critical fail-safe validator lives outside the LLM adapters so it runs on every signal. The suggested build order reaches a fully-testable mock execution core (Broker + risk engine + fail-safe parser) with zero external dependencies and zero financial risk *before* any LLM or real broker is attached.

**Major components:**
1. Orchestrator (`TradingCycle.run()`) — owns the screen->collect->context->prompt->parse->risk->execute->log control flow; imports only ports
2. DataSource adapters (pykrx / KIS price / Naver) + Screener + Context builder — produce the typed `DataContext`
3. LLMProvider adapters (Claude/OpenAI) + provider-agnostic `parse_signal()` fail-safe validator
4. Risk engine (pure functions: confidence gate, sizing, stop-loss/take-profit) + Executor + dry-run gate
5. Broker adapters (MockBroker / KISBroker) + shared KISClient/token manager; StateStore (SQLite) + JSONL audit

### Critical Pitfalls

PITFALLS.md catalogues 19 pitfalls ordered by blast radius. The top money-losing ones:

1. **Accidentally trading real money instead of mock** — bind an atomic `TradingMode` enum that selects domain + appkey + appsecret + TR_ID together; loud startup banner + typed confirmation for REAL; mode-tag the cached token; default to MOCK.
2. **Double-ordering / non-idempotent retries** — never blind-retry an order POST; persist intent->submitted->confirmed; on ambiguous failure, query executions and reconcile by client order id before resubmitting.
3. **Prompt injection from scraped Naver news** — treat news as untrusted data, never instructions; quarantine/delimit it (ideally a bounded sentiment label, not raw prose, to the decision-maker); rely on the independent rules backstop (universe membership, sizing caps, daily loss) that injection cannot control.
4. **Malformed LLM output executed anyway** — strict pydantic validation; any unparseable/invalid output -> HOLD, full stop; validate the ticker against the screened universe; never "repair" JSON into a trade.
5. **Position/cash desync + no daily loss limit** — broker is the source of truth (re-fetch positions/cash every cycle, model partial fills); add a daily realized-loss kill switch now so a future scheduler is safe. Also: secrets-in-logs (redact in the logging layer), stop-loss/LLM race (risk net wins, suppress LLM on that ticker), and lookahead/survivorship bias in screening (point-in-time data; beware pykrx adjusted-price bug #162).

## Implications for Roadmap

Based on combined research (especially ARCHITECTURE.md's dependency-driven build order and the FEATURES.md safety gates), the suggested phase structure front-loads the highest-risk seams and reaches a safe end-to-end mock cycle before any LLM or real-money risk.

### Phase 1: Foundation — domain models, config, ports, KIS mode safety
**Rationale:** Everything depends on domain models, typed config, and the port skeleton; and the single most dangerous pitfall (real-vs-mock) is foundational config, so the atomic `TradingMode` guard must exist before any order code.
**Delivers:** `domain/models.py`, `pydantic-settings` config, empty `ports/*` Protocols, secret loading from gitignored `.env`, atomic `TradingMode` enum + startup banner.
**Addresses:** mock-account-first foundation, switchable-provider scaffolding.
**Avoids:** Pitfall 1 (real-vs-mock accident), Pitfall 8 (secrets in logs/config).

### Phase 2: Mock execution core — Broker port, MockBroker, risk engine, fail-safe parser
**Rationale:** A working paper account + pure rules layer + fail-safe parser is a fully testable execution core with zero external dependencies and zero financial risk. Highest-value tests live here.
**Delivers:** Broker port + MockBroker + StateStore; `execution/risk.py` (confidence gate, % sizing + max cap, stop-loss/take-profit); `llm/signal.py` (`TradeSignal` model + `parse_signal()` -> HOLD on any error); executor + dry-run gate + JSONL audit log.
**Implements:** risk engine, signal validator, executor, audit (ARCHITECTURE.md components 3-5).
**Avoids:** Pitfall 5 (malformed output), Pitfall 19 (dry-run not isolated), the "LLM decides trade mechanics" anti-pattern.

### Phase 3: Data pipeline — pykrx OHLCV + indicators + screener, Naver news, KIS price + token manager
**Rationale:** Real data attaches to the proven execution core. The shared `KISClient`/token manager lands here (used by price, reused by the real broker later).
**Delivers:** pykrx daily data + `ta` indicators + screener; Naver news adapter (fail-soft, sanitized); KIS real-time price; `KISClient` with token cache/refresh + rate-limit throttle; `DataContext` builder.
**Uses:** `pykrx`, `ta`, `httpx`+`bs4`+`lxml`, `python-kis`/KISClient (STACK.md).
**Avoids:** Pitfalls 9 (lookahead/survivorship), 10 (token lifecycle), 11 (rate limits), 13 (holiday/stale data), 14 (Naver fragility), 17 (KST timezone).

### Phase 4: LLM agent — provider adapters + prompt + injection hardening
**Rationale:** With a tested parse->risk->execute chain and real DataContext, plug in the LLM. Build one provider first (Claude), then OpenAI as a second adapter behind the existing seam.
**Delivers:** `ClaudeProvider` + `OpenAIProvider` with provider-native structured output; prompt templates with untrusted-news delimiters; pinned model + temperature 0 + per-cycle reproducibility logging.
**Implements:** LLMProvider port + adapters (ARCHITECTURE.md component 3).
**Avoids:** Pitfall 4 (prompt injection), Pitfall 15 (non-determinism/cost).

### Phase 5: Real-money readiness — idempotency, reconciliation, daily-loss kill switch, KISBroker
**Rationale:** The real broker is the last, most-gated piece, validated against mock parity. Idempotency, reconciliation, and the daily-loss breaker are the controls that gate the real-money switch.
**Delivers:** idempotent execution (client order id + reconciliation), broker-truth position/cash reconciliation each cycle, daily realized-loss kill switch, market-hours/tick-size/price-band order validation, `KISBroker`, gated real-money config switch (+ optional Telegram notifications).
**Avoids:** Pitfalls 2 (double-ordering), 3 (stop-loss/LLM race), 6 (position desync), 7 (no daily loss limit), 12 (order-param rejections), 16 (slippage).

### Phase Ordering Rationale

- **Dependency-driven (per ARCHITECTURE.md):** ports + domain models unblock everything; mock execution core is testable with zero external calls; data and LLM adapters attach to the proven core; real broker is last and most gated. Each port is introduced before its first concrete adapter, so no step rewrites an earlier one.
- **Risk-front-loaded:** the atomic mode guard (Phase 1) and the fail-safe/rules core (Phase 2) — the controls that prevent real-money loss — exist before any code that can place an order with real consequences.
- **Real money is a deliberate final gate:** mock-first is preserved throughout; KISBroker + idempotency + daily-loss breaker all land before the real-money switch is even possible.

### Research Flags

Phases likely needing deeper research during planning (`/gsd-plan-phase --research-phase <N>`):
- **Phase 3 (Data pipeline):** KIS token TTL, exact rate limits, and pykrx adjusted-price behavior (#162) are MEDIUM-confidence and must be confirmed against the live KIS portal during planning; Naver HTML structure is unstable.
- **Phase 5 (Real-money readiness):** KIS order params (TR_ID prefixes, hashkey, tick-size bands, market-hours codes) and the reconciliation/idempotency flow need API-specific verification before any real-money path.

Phases with standard patterns (can skip research-phase):
- **Phase 1 (Foundation):** pydantic-settings, ports/composition-root are well-documented established patterns.
- **Phase 2 (Mock execution core):** pure rules + fail-safe pydantic validation are standard; the design is fully specified in ARCHITECTURE.md.
- **Phase 4 (LLM agent):** provider structured-output is well-documented in the claude-api skill + OpenAI docs (HIGH).

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Versions/choices verified against PyPI, official SDK docs, and the claude-api skill; only the indicator-lib choice is a judgment call. |
| Features | MEDIUM | Cross-checked against official KIS/pykrx repos and Anthropic docs, but no single authoritative source for "the standard LLM trading bot"; safety features grounded in established risk-management practice. |
| Architecture | HIGH | Port/adapter + composition-root + fail-safe-validation are standard patterns directly grounded in the PROJECT.md spec; external-API specifics MEDIUM. |
| Pitfalls | MEDIUM | KIS/pykrx specifics cross-verified across official portal + multiple community sources; trading-logic/operational pitfalls are well-established domain knowledge. |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **Exact KIS token TTL, rate limits, and order parameters (TR_ID/hashkey/tick-size/price-band):** MEDIUM confidence from community sources — confirm against the KIS developer portal during Phase 3/5 planning.
- **pykrx `adjusted=True` bug (#162):** documented to sometimes return unadjusted values — verify which series you get before using it for sizing/decisions; use unadjusted for transactable price, adjusted only for indicator continuity.
- **Naver Finance HTML stability:** no official news API; treat the scraper as brittle, isolate parsing behind one adapter, and fail-soft (empty = "no news," never a parse success).
- **LLM confidence calibration:** self-reported confidence is not a calibrated probability — the 0.8 gate is a coarse filter that must be backed by independent rules, not trusted as ground truth.
- **Prompt-injection robustness:** strict-JSON output does not stop the model from *choosing* an injected BUY — validate the dual-LLM/quarantine + rules-backstop approach during Phase 4 planning.

## Sources

### Primary (HIGH confidence)
- PyPI + official repos: `python-kis` 2.1.6, `pykrx` 1.2.8, `ta` 0.11.0, `openai` 2.44.0, `pydantic-settings` 2.14.2 — versions, capabilities, compatibility
- claude-api skill (Anthropic SDK reference) — forced tool use + strict JSON, model IDs, 4.6+ prefill/budget_tokens 400
- `.planning/PROJECT.md` — three-pipeline spec, strict-JSON contract, mock-first/dry-run/stop-loss safety posture

### Secondary (MEDIUM confidence)
- KIS Developers portal + koreainvestment/open-trading-api + Soju06/python-kis — token lifecycle, mock-vs-real domains/TR_ID, mock rate limits
- pykrx GitHub issues (#162 adjusted-price bug, #89, #158) — adjusted/unadjusted, delisted/survivorship
- Community KIS throttling write-ups (hky035, tgparkk) — 20 req/s, mock stricter, websocket caps
- TradingAgents / LLM-TradeBot repos — risk-audit veto, JSONL signal log pattern
- Anthropic Structured Outputs / OpenAI Structured Outputs docs — provider-native strict JSON
- Algo-trading risk guides (Nurp, 3commas, Bookmap) — fixed-fractional sizing, daily drawdown, fire-and-forget failure mode

### Tertiary (LOW confidence)
- LLM-as-sanity-check forum discussion — LLMs best as evaluator not generator (directional, not authoritative)
- LiteLLM tutorial — adapter/gateway pattern (informational; thin hand-rolled adapter preferred for 2 providers)

---
*Research completed: 2026-06-30*
*Ready for roadmap: yes*
