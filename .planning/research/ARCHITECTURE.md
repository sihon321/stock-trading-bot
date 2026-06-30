# Architecture Research

**Domain:** Personal, Korean-market, LLM-driven automated stock trading bot (Python, three pipelines: data / LLM agent / execution)
**Researched:** 2026-06-30
**Confidence:** HIGH (structure/pattern recommendations are standard and directly grounded in the PROJECT.md spec; external-API specifics — KIS token lifetime, pykrx surface — verified at MEDIUM)

## Standard Architecture

This is a **layered pipeline-and-ports** design. The PROJECT.md already names the three pipelines; the load-bearing architectural decision is to put a **stable interface (port)** in front of each swappable external dependency — LLM provider, broker, data source — so that Claude↔OpenAI and mock↔real are config switches, not code rewrites. A single **orchestrator** runs one evaluation cycle by talking only to those interfaces.

### System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                     ENTRYPOINT / CLI                             │
│        `run-cycle` (manual trigger) → loads Config               │
└───────────────────────────────┬─────────────────────────────────┘
                                 │ injects concrete impls (per config)
                                 ▼
┌─────────────────────────────────────────────────────────────────┐
│                      ORCHESTRATOR (one cycle)                    │
│   screen → collect → build context → prompt → parse →           │
│   risk-check → execute → log     (depends only on PORTS below)   │
└───┬───────────────┬───────────────────┬───────────────┬─────────┘
    │               │                   │               │
    ▼ PORT          ▼ PORT              ▼ PORT          ▼ STATE
┌─────────┐  ┌──────────────┐   ┌──────────────┐  ┌──────────────┐
│DataSource│  │ LLMProvider  │   │   Broker     │  │ StateStore   │
│(Protocol)│  │ (Protocol)   │   │ (Protocol)   │  │ + Logger     │
└────┬────┘   └──────┬───────┘   └──────┬───────┘  └──────┬───────┘
     │ adapters       │ adapters         │ adapters         │
 ┌───┴────┐      ┌────┴─────┐       ┌────┴──────┐     ┌─────┴─────┐
 │ pykrx  │      │ Claude   │       │ MockKIS   │     │ SQLite /  │
 │ KIS RT │      │ OpenAI   │       │ RealKIS   │     │ JSONL     │
 │ Naver  │      │          │       │ (KISClient│     │ files     │
 │ scrape │      │          │       │  + token) │     │           │
 └────────┘      └──────────┘       └───────────┘     └───────────┘
                                          │
                                    ┌─────┴──────┐
                                    │ KIS session │  token cache (24h,
                                    │ /token mgr  │  refresh w/ buffer)
                                    └─────────────┘
```

### Component Responsibilities

| Component | Responsibility | Typical Implementation |
|-----------|----------------|------------------------|
| **CLI / entrypoint** | Parse the manual trigger, load config, wire concrete adapters, invoke one cycle. | `argparse`/`typer`; a small `build_orchestrator(config)` factory (composition root). |
| **Orchestrator (strategy runner)** | Run the seven-step cycle in order; owns the control flow; depends only on the ports. | A `TradingCycle.run()` method; pure orchestration, no vendor SDK imports. |
| **DataSource port + adapters** | Provide market data: daily OHLCV + indicators (pykrx), real-time price (KIS), per-ticker news (Naver scrape), and the screening universe. | `DataSource` Protocol; `PykrxSource`, `KISPriceSource`, `NaverNewsSource`. Usually 2-3 distinct ports (daily, realtime, news) rather than one god-interface. |
| **Screener** | Select candidate tickers from the market (volume/momentum/fundamentals via pykrx). | A function/class consuming the daily DataSource; returns a ticker list. |
| **Context builder** | Assemble the typed **DataContext** (one ticker's facts) that gets serialized into the prompt. | A `DataContext` pydantic model + a builder that merges OHLCV/indicators/price/news. |
| **LLMProvider port + adapters** | Take a DataContext, return a raw **TradingSignal** dict; enforce "strict JSON, no markdown" at the provider boundary. | `LLMProvider` Protocol with `.generate_signal(context) -> dict`; `ClaudeProvider`, `OpenAIProvider`. |
| **Signal validator** | Parse + validate the LLM output against the strict schema; **fail-safe (HOLD/no-trade) on any error**. | A pydantic `TradingSignal` model + `parse_signal()` that never raises into a trade. |
| **Risk engine** | Apply the rules the LLM does **not** own: confidence gate, position sizing (% of capital, max cap), stop-loss/take-profit net, holdings checks. | Pure functions over signal + current positions + config thresholds. |
| **Broker port + adapters** | Place/cancel orders, read positions and balance. Mock vs real is one swap here. | `Broker` Protocol; `MockBroker` (in-memory/SQLite paper account), `KISBroker` (real). |
| **KIS session/token manager** | Issue/cache/refresh the KIS access token; sign order requests (hashkey). | A `KISClient` owning token cache + HTTP; shared by `KISPriceSource` and `KISBroker`. |
| **StateStore** | Persist positions (in dry-run/mock), cooldowns, last-run metadata. | SQLite (recommended) or JSON files. |
| **Logger / audit** | Append every cycle's data context, signal, and order outcome for later review. | Structured JSONL per cycle + standard `logging`. |
| **Config** | Provider selection, mock-vs-real, thresholds, secrets. | pydantic-settings; `.env` + a typed `Settings` object. |

## Recommended Project Structure

```
stock_trading_bot/
├── pyproject.toml
├── .env.example                  # appkey/secret, ANTHROPIC/OPENAI keys, account no.
├── src/stock_trading_bot/
│   ├── __init__.py
│   ├── config.py                 # pydantic-settings Settings; provider/mode/thresholds
│   ├── cli.py                    # `run-cycle`, `--dry-run`; composition root
│   ├── orchestrator.py           # TradingCycle.run() — the seven steps
│   │
│   ├── ports/                    # the swappable seams (Protocols / ABCs only)
│   │   ├── data_source.py        #   DailyData, RealtimePrice, NewsSource protocols
│   │   ├── llm_provider.py       #   LLMProvider protocol
│   │   └── broker.py             #   Broker protocol
│   │
│   ├── data/                     # DataSource adapters
│   │   ├── pykrx_source.py       #   OHLCV + indicators + screening universe
│   │   ├── kis_price.py          #   real-time price (uses kis/client.py)
│   │   ├── naver_news.py         #   Naver Finance per-ticker scrape
│   │   └── screener.py           #   candidate selection
│   │
│   ├── context/
│   │   ├── models.py             #   DataContext pydantic model (LLM input schema)
│   │   └── builder.py            #   merge sources → DataContext
│   │
│   ├── llm/                      # LLMProvider adapters + the contract
│   │   ├── claude_provider.py
│   │   ├── openai_provider.py
│   │   ├── prompt.py             #   system/user prompt templates
│   │   └── signal.py             #   TradingSignal model + parse_signal() FAIL-SAFE
│   │
│   ├── execution/
│   │   ├── risk.py               #   confidence gate, sizing, stop-loss/take-profit
│   │   └── executor.py           #   signal → order via Broker
│   │
│   ├── broker/                   # Broker adapters
│   │   ├── mock_broker.py        #   paper account (mock-first)
│   │   └── kis_broker.py         #   real KIS orders
│   │
│   ├── kis/                      # shared KIS HTTP + auth (used by price + broker)
│   │   ├── client.py             #   KISClient: base URL, headers, request
│   │   └── token.py              #   token issue/cache/refresh + hashkey
│   │
│   ├── state/
│   │   ├── store.py              #   positions, cooldowns, last-run (SQLite)
│   │   └── audit.py              #   JSONL cycle log (context+signal+outcome)
│   │
│   └── domain/                   # shared dataclasses/enums (Decision, Order, Position)
│       └── models.py
└── tests/
    ├── test_signal_parsing.py    #   the fail-safe path — highest-value tests
    ├── test_risk.py
    └── test_mock_broker.py
```

### Structure Rationale

- **`ports/`:** isolates the three interface seams in one place so the swap points are obvious and reviewable. The orchestrator imports from `ports/`, never from `llm/`, `broker/`, or `data/` directly.
- **`kis/` separate from `broker/` and `data/`:** the KIS token/hashkey machinery is shared by both real-time price reads and order placement. Putting `KISClient` in its own module avoids duplicating auth in two adapters and keeps the token cache single-owner.
- **`llm/signal.py` separate from `llm/*_provider.py`:** validation/fail-safe is provider-agnostic and security-critical — it must run on *every* signal regardless of which LLM produced it, so it lives outside the adapters.
- **`execution/risk.py` as pure functions:** the rules-based safety net (confidence gate, sizing, stop-loss/take-profit) must be independent of the LLM and trivially unit-testable; keeping it side-effect-free makes that easy.
- **`context/models.py` and `llm/signal.py` as the two schema files:** the DataContext (LLM input) and TradingSignal (LLM output) are the two contracts at the LLM boundary; co-locating each with its pipeline stage makes the boundary explicit.

## Architectural Patterns

### Pattern 1: Port/Adapter (Hexagonal) for every external dependency

**What:** Define an abstract interface (Python `Protocol` or ABC) for each external system; concrete adapters implement it; the orchestrator depends only on the interface.
**When to use:** Any dependency that has a "swap" axis — here: LLM (Claude/OpenAI) and broker/data (mock/real).
**Trade-offs:** A little upfront indirection; in exchange, switching providers is a config + factory change, and every adapter is independently mockable in tests. For a 2×2 swap matrix (2 LLMs × mock/real broker) this pays for itself immediately.

**Example:**
```python
# ports/llm_provider.py
from typing import Protocol
from ..context.models import DataContext

class LLMProvider(Protocol):
    def generate_signal(self, context: DataContext) -> dict:
        """Return a raw signal dict. MUST be strict JSON; no markdown.
        Validation happens downstream in llm/signal.py — adapters do not trade."""
        ...
```

### Pattern 2: Composition root / factory selects implementations from config

**What:** A single `build_orchestrator(config)` reads `config.llm_provider` and `config.mode` and constructs the right adapters once, at startup. No `if provider == "claude"` scattered through the code.
**When to use:** Always, once you have ports. It's the only place that knows concrete classes.
**Trade-offs:** None meaningful for this size; it centralizes wiring.

**Example:**
```python
# cli.py (composition root)
def build_orchestrator(cfg: Settings) -> TradingCycle:
    llm = {"claude": ClaudeProvider, "openai": OpenAIProvider}[cfg.llm_provider](cfg)
    broker = MockBroker(cfg) if cfg.mode == "mock" or cfg.dry_run else KISBroker(kis_client)
    return TradingCycle(data=..., llm=llm, broker=broker, risk=RiskEngine(cfg), audit=...)
```

### Pattern 3: Parse-don't-trust at the LLM boundary (fail-safe validation)

**What:** Treat LLM output as untrusted. Validate against a strict pydantic model; on **any** parse/validation failure return a HOLD/no-trade signal rather than raising into the execution path.
**When to use:** Always, for the signal. This is the single most important safety boundary in the system.
**Trade-offs:** None — a malformed signal must never reach the broker.

**Example:**
```python
# llm/signal.py
from pydantic import BaseModel, ValidationError, field_validator

class TradingSignal(BaseModel):
    decision: Literal["BUY", "SELL", "HOLD"]
    confidence: float
    reason: str

def parse_signal(raw: str | dict) -> TradingSignal:
    try:
        data = raw if isinstance(raw, dict) else json.loads(raw)
        return TradingSignal.model_validate(data)
    except (json.JSONDecodeError, ValidationError):
        return TradingSignal(decision="HOLD", confidence=0.0, reason="parse_failed")
```
Provider-native structured output (Anthropic `output_config.format`/`messages.parse()`, OpenAI `response_format` json_schema) makes the LLM *emit* valid JSON, but the pydantic re-validation must still run — the fail-safe is the guarantee, the provider feature is an optimization.

### Pattern 4: Single owner for KIS token/session (cache + refresh)

**What:** One `KISClient` issues the access token, caches it with its expiry, refreshes within a buffer, and signs orders (hashkey). Both the price DataSource and the Broker adapter borrow this one client.
**When to use:** Whenever an external API has a rate-limited, time-boxed token (KIS tokens are ~24h-lived and token issuance is rate-limited — re-issuing per request will get throttled).
**Trade-offs:** Slight statefulness in an otherwise stateless cycle; necessary and standard.

## Data Flow

### One Evaluation Cycle (the request flow)

```
[manual trigger: run-cycle]
        ↓
1. SCREEN     screener (pykrx) → candidate ticker list
        ↓
2. COLLECT    for each ticker: pykrx OHLCV+indicators, KIS realtime price, Naver news
        ↓
3. CONTEXT    builder → DataContext (typed, per ticker)
        ↓
4. PROMPT     LLMProvider.generate_signal(context) → raw JSON   [Claude OR OpenAI]
        ↓
5. PARSE      parse_signal(raw) → TradingSignal   [FAIL-SAFE: bad output ⇒ HOLD]
        ↓
6. RISK-CHECK risk engine: confidence gate (BUY needs ≥0.8), sizing (% cap + max),
              holdings/cooldown check, stop-loss/take-profit net (LLM-independent)
        ↓                              │ rejected → log "no-trade" reason, next ticker
        ↓ approved
7. EXECUTE    executor → Broker.place_order()   [MockBroker OR KISBroker; dry-run logs only]
        ↓
8. LOG        audit.write(context, signal, decision, order_outcome)  → JSONL + StateStore
        ↓
   next ticker → repeat 2–8
```

### State Management

```
StateStore (SQLite)              Audit log (JSONL, append-only)
  positions   ─── read by ───▶ risk engine / executor
  cooldowns   ─── read/write ─▶ risk engine (skip recently-traded tickers)
  last_run    ─── written by ─▶ orchestrator
                                 every cycle appends: {ts, ticker, context,
                                 signal, risk_decision, order_result}
```
State that must persist between manual runs: **open positions** (especially in mock/dry-run, where there's no real broker to ask), **cooldowns**, and **last-run metadata**. In real mode, positions/balance are authoritative from `Broker.get_positions()`/`get_balance()`; the StateStore still holds cooldowns and the audit trail.

### Key Data Flows

1. **DataContext (input contract):** sources → builder → one typed object per ticker → serialized into the prompt. Keeping it a pydantic model means the prompt is built from validated data, and the exact context is logged verbatim.
2. **TradingSignal (output contract):** LLM → `parse_signal` → validated signal → risk engine. The signal never reaches the broker without passing both validation and the rules-based gate.
3. **Token flow:** `KISClient` ← (cache hit / refresh) → KIS auth endpoint; both `KISPriceSource` and `KISBroker` call through the same client so the token is issued once per validity window.

## Scaling Considerations

This is a **single-user, manual-trigger** tool; "scale" means cycle breadth and future automation, not concurrent users.

| Scale | Architecture Adjustments |
|-------|--------------------------|
| v1: a handful of candidate tickers, manual run | Synchronous loop is fine. SQLite + JSONL files. No queue, no scheduler. |
| Wider universe (50–200 tickers/cycle) | Parallelize the COLLECT step (async or thread pool) and **batch/limit LLM calls** (cost + KIS rate limits). The port boundaries already let you do this without touching orchestration logic. Respect KIS mock-account rate limits — they are lower than live. |
| Automation / intraday (explicitly out of scope for v1) | Add a scheduler in front of the existing `run-cycle` entrypoint; the orchestrator does not change. This is why the trigger is kept separate from the cycle. |

### Scaling Priorities

1. **First bottleneck:** LLM latency/cost and KIS rate limits as the ticker count grows → batch contexts, cap candidates in the screener, and parallelize data collection (not the LLM calls).
2. **Second bottleneck:** Naver scraping fragility/throttling → cache news per ticker per day; treat news as best-effort (a missing news section should degrade the context, not crash the cycle).

## Anti-Patterns

### Anti-Pattern 1: Letting the LLM decide trade mechanics

**What people do:** Trust the LLM's `decision` directly to size and place orders.
**Why it's wrong:** A hallucinated/over-confident signal can place a trade the rules don't justify; the LLM has no view of capital limits or stop-loss state.
**Do this instead:** The LLM only *proposes* (`decision`, `confidence`, `reason`). The **risk engine** owns the confidence gate, sizing, max-position cap, and the LLM-independent stop-loss/take-profit. Keep `execution/risk.py` separate and pure.

### Anti-Pattern 2: Parsing LLM output by string-matching / regex (or trusting it)

**What people do:** `if "BUY" in response:` or `json.loads(response)` straight into execution.
**Why it's wrong:** Markdown fences, extra prose, or a malformed object silently produce wrong trades or crashes mid-cycle.
**Do this instead:** Single `parse_signal()` with a strict pydantic schema that returns HOLD on any failure. Validation is a boundary, not scattered checks.

### Anti-Pattern 3: Duplicating KIS auth in each adapter / re-issuing tokens per call

**What people do:** Each of price-fetch and order-place issues its own token inline.
**Why it's wrong:** Token issuance is rate-limited (you'll get throttled), and two token caches drift.
**Do this instead:** One `KISClient` owns issue/cache/refresh; price and broker adapters share it.

### Anti-Pattern 4: Branching on provider/mode throughout the codebase

**What people do:** `if config.provider == "claude"` / `if config.mode == "real"` sprinkled across modules.
**Why it's wrong:** Every new branch is a place the swap can break; testing combinatorially explodes.
**Do this instead:** Resolve concrete implementations once in the composition root; everything downstream sees only the port.

### Anti-Pattern 5: No dry-run path distinct from mock

**What people do:** Conflate "mock account" with "dry run."
**Why it's wrong:** They're different safety levels — mock places real orders against the KIS paper account; dry-run places nothing and just logs the would-be order.
**Do this instead:** `dry_run` short-circuits inside the executor (log the intended order, skip `Broker.place_order`), independent of which Broker adapter is wired.

## Integration Points

### External Services

| Service | Integration Pattern | Notes |
|---------|---------------------|-------|
| **KIS Open API (한국투자증권)** | REST via shared `KISClient`; token cached ~24h with refresh buffer; orders need a hashkey. Real-time price + order placement both go through it. | Mock (모의투자) and live are different base URLs/credentials → select in config. Mock rate limits are lower than live. (MEDIUM confidence on exact token TTL — confirm against the KIS developer portal during Phase 1.) |
| **pykrx** | Library call; daily OHLCV (`get_market_ohlcv`), fundamentals (`get_market_fundamental`), market cap/volume (`get_market_cap`), ticker lists — used for screening + daily data. | KRX scraping under the hood; treat as daily, cache per run. |
| **Naver Finance (네이버 금융)** | HTML scraping per ticker; best-effort. | Fragile by nature — must degrade gracefully (missing news ⇒ context note, not a crash) and be cached per ticker/day. |
| **Anthropic (Claude) / OpenAI** | Behind `LLMProvider`; both support native strict-JSON / structured-output modes. | One active at a time via config. Re-validate output with pydantic regardless of native mode. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Orchestrator ↔ DataSource/LLM/Broker | Direct method calls through `ports/` Protocols | The three swap seams; orchestrator never imports an adapter. |
| LLM adapter ↔ Signal validator | Adapter returns raw dict; `parse_signal` validates | Fail-safe lives here, outside the adapter. |
| Risk engine ↔ StateStore/Broker | Reads positions/cooldowns; pure decision out | No side effects in risk; executor performs the action. |
| Price source & Broker ↔ KISClient | Shared client instance | Single token/session owner. |

## Suggested Build Order (dependency-driven)

This ordering lets you reach a safe, end-to-end mock cycle before any LLM or real-money risk, and front-loads the highest-risk seams.

1. **Domain models + Config + ports skeleton** — `domain/models.py`, `config.py`, empty `ports/*` Protocols. Everything depends on these.
2. **Broker port + MockBroker + StateStore** — a working paper account *first*. This is the precondition for testing execution without risk (the downstream consumer's "broker + mock account before LLM execution" note).
3. **Risk engine** (`execution/risk.py`) + **signal model & fail-safe parser** (`llm/signal.py`) — pure, unit-testable, no external calls. Build and test these against hand-written signals before any real LLM. Highest-value tests live here.
4. **Executor** wiring (signal → risk → MockBroker) + **dry-run path** + **audit log** — now you can run a full execution pipeline with fake signals end-to-end.
5. **DataSource adapters** — pykrx (daily + screener) first, then Naver news (best-effort), then KIS real-time price. **KISClient/token manager** lands here (shared by price; reused by the real broker later).
6. **Context builder + DataContext model** — assemble real data into the typed context.
7. **LLMProvider: one adapter first (e.g. Claude), then OpenAI** — plug into the already-tested parse→risk→execute chain. Because the seam exists, adding the second provider is an adapter + a config value.
8. **KISBroker (real)** — implemented last, behind the same Broker port, validated against mock parity before being selected in config. Real-money promotion is the final, gated config switch.

**Why this order:** ports and domain models unblock everything; the mock broker + risk engine + fail-safe parser form a fully testable execution core with zero external dependencies and zero financial risk; data and LLM adapters attach to that proven core; the real broker is the last and most gated piece. Each interface seam (Broker, LLMProvider, DataSource) is introduced as a Protocol *before* its first concrete adapter, so no step requires rewriting an earlier one.

## Sources

- `.planning/PROJECT.md` — the three-pipeline spec, strict-JSON contract, mock-first/dry-run/stop-loss safety posture (HIGH; project's own decisions).
- KIS Developers portal & community references — token issuance/lifetime, hashkey for orders, mock rate limits (MEDIUM; confirm exact TTL during Phase 1). https://apiportal.koreainvestment.com/apiservice , https://github.com/koreainvestment/open-trading-api
- pykrx (sharebook-kr) README/PyPI — OHLCV / fundamental / market-cap functions and market coverage for screening (MEDIUM). https://github.com/sharebook-kr/pykrx , https://pypi.org/project/pykrx/
- Anthropic Claude API skill (structured outputs / `messages.parse()` / strict tool use) and OpenAI Structured Outputs — provider-native strict-JSON modes behind the LLMProvider port (MEDIUM-HIGH for the provider-agnostic validation pattern).
- Port/Adapter + composition-root + Strategy pattern (standard ccxt-style broker abstraction and provider abstraction in trading bots) (MEDIUM; well-established pattern).

---
*Architecture research for: Korean-market LLM-driven trading bot (three-pipeline, mock-first, Python)*
*Researched: 2026-06-30*
