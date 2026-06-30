# Feature Research

**Domain:** Personal LLM-driven automated stock trading bot (Korean equities, KIS + pykrx)
**Researched:** 2026-06-30
**Confidence:** MEDIUM (web sources cross-checked against official KIS/pykrx repos and Anthropic structured-output docs; no single authoritative source for "the standard LLM trading bot")

> **Safety note for the roadmap consumer:** rows tagged **[SAFETY-CRITICAL]** are the controls that stand between this bot and an unrecoverable real-money loss. For a personal bot that will eventually touch a live KIS account, these are not "table stakes for polish" — they are table stakes for *not losing money to a bug*. Treat them as P1 and do not let an LLM decision path bypass them.

## Feature Landscape

### Table Stakes (Without These the Bot Is Unsafe or Useless)

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Daily universe screening** (pykrx volume/momentum/market-cap filter) | A fixed ticker list goes stale; the bot must surface candidates dynamically | MEDIUM | `pykrx` `get_market_ohlcv` / `get_market_fundamental_by_ticker` / market-cap. Respect KRX ~1s/request delay — it blocks bursts. |
| **Daily OHLCV + technical indicators** | LLM needs price history context; indicators (MA, RSI, etc.) are standard inputs | MEDIUM | pykrx for daily bars; compute indicators locally (don't ask the LLM to compute math). |
| **Real-time / latest price via KIS** | Sizing and stop checks need the current price, not yesterday's close | MEDIUM | KIS REST quote. Auth `svr=vps` (mock) vs `prod` (real). |
| **Per-ticker news (Naver Finance)** | Sentiment/catalyst context is a core differentiator of an LLM approach | MEDIUM | Scraping is brittle (HTML changes); isolate behind an interface and fail soft if it breaks. |
| **Strict JSON LLM signal** `{decision, confidence, reason}` | Execution parses programmatically; markdown/prose breaks the pipeline | MEDIUM | Use provider structured-output (Anthropic `output_format: json_schema`; OpenAI `response_format json_schema`) + Pydantic validation. |
| **Fail-safe on unparseable LLM output** **[SAFETY-CRITICAL]** | An unparseable signal must NEVER fall through to a trade | LOW | Parse error → log → HOLD/no-op. Default-deny. |
| **Confidence gating** (BUY requires `confidence >= 0.8`) **[SAFETY-CRITICAL]** | Bounds action to high-conviction signals; rejects low-confidence/HOLD | LOW | Pure rule check after parse. Cheap, high-value. |
| **% -of-capital position sizing with max-position cap** **[SAFETY-CRITICAL]** | Bounds single-trade risk; scales with account; prevents all-in | MEDIUM | Fixed-fractional is the professional default (industry caps risk at ~1–2%/trade; your % is a config knob). |
| **Rules-based stop-loss / take-profit, independent of LLM** **[SAFETY-CRITICAL]** | The LLM may never say SELL in time; a deterministic net must exit | MEDIUM | Must run every cycle on held positions regardless of LLM output. |
| **Dry-run mode** | Validate full logic, log the would-be order, place nothing | LOW | Single boolean gate at the execution boundary. |
| **Mock-account-first (모의투자)** **[SAFETY-CRITICAL]** | Validate end-to-end with zero capital risk before real money | LOW | Config flag `svr=vps`; real-money promotion is a deliberate gated step. Note: mock has *lower* REST rate limits. |
| **Order placement via KIS** | The whole point — turn a signal into a fill | MEDIUM | Needs access token (~24h TTL, 1 issue/min) + hashkey per order. |
| **Per-cycle audit log** (data context + LLM signal + order outcome) **[SAFETY-CRITICAL]** | Without it you can't tell why the bot did what it did; debugging blind | LOW | Append-only JSONL per cycle (`signal_log.jsonl` pattern). This IS the decision audit trail. |
| **Manual trigger** (run one full cycle on demand) | Keeps the operator in the loop while logic is unproven | LOW | A CLI entrypoint; no scheduler for v1. |

### Differentiators (Competitive Advantage / High-Value Add)

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **LLM reasoning as a sanity-check layer over rule signals** | Research consensus: LLMs work best *evaluating/vetoing* signals, not as the sole generator. A rules pre-filter + LLM veto is more robust than LLM-only. | MEDIUM | Optional evolution: have rules nominate candidates, LLM confirm/reject. |
| **Daily-loss / drawdown limit + kill switch** **[SAFETY-CRITICAL differentiator]** | Hard stop on the *day* (e.g. halt all trading after −X% realized). Caps a bad day, not just a bad trade. | MEDIUM | Industry standard (~10% daily drawdown). Strongly recommended even for v1 — small lift, big protection. |
| **Idempotent order execution** (dedup key / client order id) **[SAFETY-CRITICAL differentiator]** | Prevents a retry or double-run from placing the same order twice | MEDIUM | Track placed orders for the cycle; reconcile against KIS before re-placing. |
| **Position reconciliation** (sync held positions from KIS each cycle) | Source of truth is the broker, not local state; survives crashes/restarts | MEDIUM | Query KIS balances at cycle start; drives stop/take-profit checks. |
| **Telegram (or similar) notifications** | Personal bot you don't babysit — push decisions/orders/errors to your phone | LOW | Counters the #1 retail failure: "fire and forget." Cheap, high quality-of-life. |
| **Reproducibility of LLM decisions** | Log model id, prompt version, temperature, raw input + raw output so a decision can be re-examined | LOW–MEDIUM | Pin model + prompt version; `temperature=0` reduces (not eliminates) drift. Store the exact prompt with the log. |
| **Switchable LLM provider behind one interface** (Claude/OpenAI) | Avoid vendor lock-in; swap via config | MEDIUM | Adapter pattern; one `LLMProvider` interface, two impls. (LiteLLM exists but a thin hand-rolled adapter is fine for 2 providers.) |
| **Paper-trading / backtest harness** | Validate a strategy on history before trusting it live | HIGH | The official KIS repo ships a `backtester`; pykrx gives history. High value but high effort — defer past v1. |
| **Cost / token tracking per cycle** | LLM calls cost money; visibility prevents surprise bills | LOW | Log token usage per call. |

### Anti-Features (Deliberately NOT Building for Personal v1)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Always-on intraday polling loop** | "Real-time" feels powerful | Multiplies LLM cost, hits KIS rate limits (20 req/s, lower on mock), and removes the human from the loop while logic is unproven | Manual-trigger one cycle; add a scheduled daily run only after validation |
| **Ensemble / multi-LLM consensus** | More models = more confidence | 2× cost/latency, ambiguous tie-breaking, hard to debug which model was "right" | Single switchable provider; revisit ensemble only if single-provider proves unreliable |
| **Multi-market (US/global)** | Broader opportunity | KIS + pykrx are KR-specific; doubles data/auth/calendar complexity | KR-only by design |
| **Portfolio optimization / multi-strategy allocation** | "Optimal" capital allocation | Mean-variance/optimizers need data and assumptions you don't have yet; over-engineering for one signal | Single-signal execution with a max-position cap |
| **LLM as the sole signal source with no rule floor** | Simplest mental model | Research says LLMs are weak as pure generators and non-deterministic; one hallucinated high-confidence BUY = real loss | Rules own the hard safety floor (sizing, stops, gating); LLM only *proposes* within those bounds |
| **Letting the LLM set position size or stop levels** | "Let the smart model decide everything" | Hands the safety-critical math to a non-deterministic component | Sizing & stops are deterministic rules; LLM output is confined to decision + confidence + reason |
| **Auto-promotion mock → real money** | Convenience | Removes the deliberate human gate before risking capital | Real-money is a manual, explicit config change after mock validation |

## Feature Dependencies

```
[KIS auth: token + hashkey]
    └──requires──> [Real-time price]
    └──requires──> [Order placement]
                       └──requires──> [Idempotency / dedup]
                       └──requires──> [Position reconciliation]
                                          └──requires──> [Rules stop-loss/take-profit]

[pykrx OHLCV + indicators] ──feeds──> [Daily universe screening]
                            └──feeds──> [LLM context]
[Naver news scrape] ──────────────────> [LLM context]
[Real-time price] ────────────────────> [LLM context] & [Position sizing] & [Stop/TP checks]

[LLM context]
    └──> [Strict JSON signal]
            └──requires──> [Fail-safe parse]
                              └──> [Confidence gating]
                                     └──> [Position sizing + max cap]
                                            └──> [Dry-run gate] ──> [Order placement]

[Per-cycle audit log] ──enhances──> EVERYTHING (must wrap the whole cycle)
[Daily-loss limit / kill switch] ──gates──> [Order placement]  (veto power)
[Telegram notify] ──enhances──> [Audit log]  (push, don't pull)

[LLM-as-sanity-check] ──conflicts──> [LLM-as-sole-generator]  (pick one philosophy)
```

### Dependency Notes

- **Order placement requires KIS auth (token + hashkey):** every order needs a valid access token (24h TTL, 1 issuance/min — cache and refresh it) and a per-order hashkey. Token management is foundational infra, not a feature afterthought.
- **Stop-loss/take-profit requires position reconciliation:** you can only protect positions you know you hold; reconcile from KIS at cycle start so stops survive restarts.
- **Idempotency requires order placement + reconciliation:** dedup is "did I already place this?" — answerable only by tracking placed orders and/or querying KIS fills.
- **Confidence gating + sizing + dry-run form the execution gauntlet:** every order passes parse → confidence → sizing/cap → dry-run gate → daily-loss veto, in that order. None may be skippable by an LLM path.
- **Audit log wraps everything:** it's a cross-cutting concern, not a leaf feature — instrument from cycle start.
- **LLM-as-sanity-check conflicts with LLM-as-sole-generator:** these are two architectures; v1 is LLM-as-generator-within-rule-bounds, with the sanity-check pattern as a documented evolution path.

## MVP Definition

### Launch With (v1) — mock account only

- [ ] **KIS auth + token caching** — nothing works without it
- [ ] **pykrx OHLCV + local indicators** — LLM input
- [ ] **Daily universe screening** — produces candidates
- [ ] **KIS real-time price** — sizing & stop inputs
- [ ] **Naver news scrape (fail-soft)** — the LLM-edge input
- [ ] **Switchable LLM provider with strict JSON + Pydantic validation** — the decision
- [ ] **Fail-safe on parse error → HOLD** **[SAFETY]**
- [ ] **Confidence gating (BUY ≥ 0.8)** **[SAFETY]**
- [ ] **% -of-capital sizing + max-position cap** **[SAFETY]**
- [ ] **Rules stop-loss/take-profit independent of LLM** **[SAFETY]**
- [ ] **Position reconciliation from KIS** — feeds stops/sizing
- [ ] **Dry-run mode** **[SAFETY]**
- [ ] **Order placement on mock (모의투자)** **[SAFETY-gated]**
- [ ] **Per-cycle audit log (JSONL)** **[SAFETY]**
- [ ] **Manual trigger CLI**

### Add After Validation (v1.x) — gates real-money

- [ ] **Idempotent order execution** — trigger: before any real-money run
- [ ] **Daily-loss limit / kill switch** — trigger: before real-money run (strongly consider in v1)
- [ ] **Telegram notifications** — trigger: once you stop watching the terminal
- [ ] **Reproducibility metadata in logs** (model id, prompt version, raw I/O) — trigger: first "why did it do that?" investigation
- [ ] **Scheduled daily run** — trigger: after manual cycles prove stable

### Future Consideration (v2+)

- [ ] **Backtest / paper-trading harness** — defer: high effort; validate concept on mock first
- [ ] **LLM-as-sanity-check architecture** (rules nominate, LLM vetoes) — defer: requires a working rule signal to layer on
- [ ] **Cost/token tracking dashboard** — defer: nice-to-have once volume grows
- [ ] **Ensemble LLMs** — defer: only if single provider proves unreliable

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| KIS auth + token caching | HIGH | MEDIUM | P1 |
| Strict JSON signal + Pydantic validation | HIGH | MEDIUM | P1 |
| Fail-safe parse → HOLD | HIGH | LOW | P1 |
| Confidence gating | HIGH | LOW | P1 |
| % sizing + max-position cap | HIGH | MEDIUM | P1 |
| Rules stop-loss/take-profit | HIGH | MEDIUM | P1 |
| Dry-run mode | HIGH | LOW | P1 |
| Mock-account-first | HIGH | LOW | P1 |
| Per-cycle audit log | HIGH | LOW | P1 |
| pykrx OHLCV + screening | HIGH | MEDIUM | P1 |
| Real-time price | HIGH | MEDIUM | P1 |
| Naver news scrape | MEDIUM | MEDIUM | P1 |
| Switchable LLM provider | MEDIUM | MEDIUM | P1 |
| Manual trigger | HIGH | LOW | P1 |
| Position reconciliation | HIGH | MEDIUM | P1/P2 |
| Daily-loss limit / kill switch | HIGH | MEDIUM | P2 |
| Idempotent execution | HIGH | MEDIUM | P2 |
| Telegram notifications | MEDIUM | LOW | P2 |
| Reproducibility metadata | MEDIUM | LOW–MEDIUM | P2 |
| Backtest harness | MEDIUM | HIGH | P3 |
| LLM-as-sanity-check layer | MEDIUM | MEDIUM | P3 |
| Ensemble LLMs | LOW | HIGH | P3 |

**Priority key:** P1 = must have for v1 launch · P2 = add before real money / once unattended · P3 = future

## Competitor / Reference Feature Analysis

| Feature | Official KIS `open-trading-api` | Multi-agent LLM bots (TradingAgents / LLM-TradeBot) | Our Approach |
|---------|-------------------------------|------------------------------------------------------|--------------|
| Signal source | rule/strategy builder | multi-agent LLM debate (bull/bear) | single LLM, strict JSON, within rule bounds |
| Structured output | n/a | Pydantic models, `signal_log.jsonl` | Pydantic + JSONL audit log (adopt this pattern) |
| Risk layer | helper functions | "Risk Audit with veto power" | deterministic rules own sizing/stops/gating |
| Backtesting | ships a backtester | backtested approaches common | defer to v2; reuse KIS backtester later |
| Mock environment | `svr=vps` 모의투자 | n/a | mock-first, gated promotion |
| Provider lock-in | KIS-only (fine) | usually single-vendor | switchable Claude/OpenAI adapter |

## Sources

- [Top Trading Algo Bots / Bookmap](https://bookmap.com/blog/top-trading-algo-bots-automating-your-trading-strategy) — modular bot feature breakdown (MEDIUM)
- [7 Risk Management Strategies for Algorithmic Trading / Nurp](https://nurp.com/algorithmic-trading-blog/7-risk-management-strategies-for-algorithmic-trading/) — fixed-fractional sizing, stops, limits (MEDIUM)
- [AI Trading Bot Risk Management Guide / 3commas](https://3commas.io/blog/ai-trading-bot-risk-management-guide) — daily drawdown, circuit breakers, fire-and-forget failure mode (MEDIUM)
- [TradingAgents — Multi-Agent LLM Financial Framework / GitHub](https://github.com/tauricresearch/tradingagents) — risk-audit veto, structured agents (MEDIUM)
- [LLM-TradeBot / GitHub](https://github.com/EthanAlgoX/LLM-TradeBot) — JSONL signal log, reason field audit trail (MEDIUM)
- [Using LLMs as a sanity check in trading pipelines / BlackHatWorld](https://www.blackhatworld.com/seo/using-llms-as-a-sanity-check-in-crypto-trading-pipelines-what-actually-helps.1815069/) — LLM best as evaluator not generator (LOW)
- [koreainvestment/open-trading-api / GitHub](https://github.com/koreainvestment/open-trading-api) — official KIS sample code, examples_llm, backtester, mock vs prod (MEDIUM)
- [python-kis / Soju06 / GitHub](https://github.com/Soju06/python-kis) — community KIS library (MEDIUM)
- [KIS API throttling / hky035](https://hky035.github.io/web/kis-api-throttling/) — 20 req/s rate limit, websocket 41 tickers/session (MEDIUM)
- [TG's Programming Blog — KIS rate-limit solutions](https://tgparkk.github.io/robotrader/2025/10/09/robotrader-1-70stocks-problem.html) — token TTL ~24h, mock lower limits (MEDIUM)
- [pykrx / sharebook-kr / GitHub](https://github.com/sharebook-kr/pykrx) — OHLCV, fundamental (PER/PBR), market cap, ticker list; 1s delay advised (MEDIUM)
- [Anthropic Structured Outputs / Claude Platform Docs](https://platform.claude.com/docs/en/build-with-claude/structured-outputs) — `output_format json_schema`, grammar-constrained generation, Pydantic (MEDIUM, official)
- [LiteLLM Tutorial](https://tutorials.technology/tutorials/litellm-tutorial-python-2026.html) — adapter/gateway pattern for swappable providers (LOW)

---
*Feature research for: personal LLM-driven KR-market stock trading bot*
*Researched: 2026-06-30*
