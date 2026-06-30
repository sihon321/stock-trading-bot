# Stack Research

**Domain:** Korean-market, LLM-driven automated stock trading bot (personal use, Python)
**Researched:** 2026-06-30
**Confidence:** HIGH

## Executive Summary

The bot is a Python project with three pipelines (data → LLM signal → KIS execution). The 2025/2026 standard stack is settled and uncontroversial for most layers:

- **KIS access:** Use the actively maintained community library **`python-kis`** (Soju06) for both real-time prices and order execution. It supports the KIS mock (모의투자) account natively, manages AppKey/SecretKey tokens for you, and wraps the websocket. Do NOT use `mojito2` (unmaintained since 2023, no mock support documented). Calling the KIS REST API directly is a viable fallback but adds significant boilerplate (token issuance/refresh, hashkey, tr_id juggling, domain switching) for no benefit at this scale.
- **Daily data:** **`pykrx`** for OHLCV + screening fundamentals. It does NOT compute indicators, so pair it with a TA library.
- **Indicators:** **`ta`** (pure-Python, no C dependency) is the pragmatic default — `TA-Lib` carries a painful C-library install, and mainline `pandas-ta` has gone yearly-maintenance and now requires Python 3.12+.
- **LLM:** Official **`anthropic`** and **`openai`** SDKs, switchable via config. Enforce the strict JSON contract with **forced tool use + `strict: true`** (Anthropic) and **`responses.parse` / `chat.completions.parse` with a Pydantic model** (OpenAI) — both validate against a Pydantic `TradeSignal` model and guarantee schema conformance, which is exactly what the "fail-safe on unparseable output" requirement needs.
- **Config/secrets:** **`pydantic-settings`** + a `.env` file (gitignored). **Scheduling:** a plain CLI (`typer`) for v1 — no scheduler, matching the manual-trigger decision. **Persistence:** **SQLite** via stdlib `sqlite3` for the per-cycle audit log; **logging:** stdlib `logging` with `structlog` for structured JSON lines.

The only judgment call is the indicator library; everything else is a clear "use X because Y."

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.12+ | Runtime | Required by `pykrx` (>=3.10) and `python-kis` (3.10–3.13); 3.12 keeps the door open for mainline `pandas-ta` if ever needed. Use 3.12 (not 3.13) for the widest library compatibility. |
| `python-kis` | 2.1.6 (2025-10-13) | KIS real-time prices + order execution | Only actively maintained community KIS library. Native mock (모의투자) account support, automatic AppKey/SecretKey token issuance + refresh, websocket with auto-reconnect, type hints, English method names. Eliminates ~all KIS REST boilerplate. |
| `pykrx` | 1.2.8 (2026-05-04) | Daily OHLCV + screening fundamentals | De-facto standard for KRX daily data. `get_market_ohlcv`, ticker lists, PER/PBR/EPS/DIV, market cap, investor-type trading value, short-selling. Actively maintained. Scrapes KRX/Naver public data — no API key. |
| `ta` | 0.11.0 | Technical indicators (RSI, MACD, MAs, Bollinger) | Pure-Python on pandas, MIT, **no C dependency** → trivial `pip install`. `pykrx` returns raw OHLCV only, so an indicator lib is mandatory. Stable and sufficient for standard indicators. |
| `anthropic` | 0.40+ (current major) | Claude LLM provider | Official SDK. Forced tool use + `strict: true` gives a hard schema guarantee for the `{decision,confidence,reason}` contract. Default model `claude-opus-4-8`. |
| `openai` | 2.44.0 (2026-06) | OpenAI LLM provider | Official SDK. `responses.parse` / `chat.completions.parse` with a Pydantic model returns a validated object — schema-conformant JSON guaranteed. |
| `pydantic` | 2.x | Data models + LLM output validation | The `TradeSignal` model is the single source of truth: it defines the JSON schema sent to both LLMs AND validates their responses. A `ValidationError` IS the "fail-safe, no trade" signal. |
| `pydantic-settings` | 2.14.2 (2026-06-19) | Config + secrets | `BaseSettings` + `SettingsConfigDict(env_file=".env")` loads typed config and secrets (KIS appkey/secret, LLM keys, account no, provider toggle) from env/`.env` with validation. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `typer` | 0.12+ | CLI entrypoint | v1 manual trigger: `bot run`, `bot run --dry-run`, `bot screen`. Built on Click, type-hint driven, minimal. |
| `structlog` | 24.x+ | Structured logging | Emit each cycle's data context, LLM signal, and order outcome as structured JSON log lines for review (a hard requirement). Wraps stdlib `logging`. |
| `httpx` | 0.27+ | Naver Finance news scraping | Modern requests-compatible client with timeouts/retries; HTTP/2. Use for fetching Naver Finance per-ticker news pages. |
| `beautifulsoup4` | 4.12+ | HTML parsing | Parse scraped Naver Finance news HTML. Pair with `lxml` parser for speed. |
| `lxml` | 5.x | Fast HTML/XML parser backend | `BeautifulSoup(html, "lxml")` — faster and more lenient than the stdlib parser. |
| `tenacity` | 8.x+ | Retry/backoff | Wrap flaky network calls (Naver scrape, KIS REST, LLM calls) with exponential backoff. |
| `pandas` | 2.x | DataFrames | `pykrx` returns DataFrames; `ta` consumes/produces them. Transitive dependency you'll use directly. |
| `sqlite3` | stdlib | Per-cycle audit persistence | Log every cycle (timestamp, ticker, data snapshot, LLM signal JSON, order result) to a local SQLite DB. Zero-ops, queryable, ships with Python. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| `uv` | Dependency + venv management | Fast, modern installer/resolver; `uv add`, `uv run`. Replaces pip+venv+pip-tools. (pip + `venv` is the conservative fallback.) |
| `ruff` | Lint + format | One tool for both; near-instant. |
| `pytest` | Test runner | Standard. See Testing notes below. |
| `respx` or `pytest-httpx` | Mock httpx in tests | Mock Naver scrape + KIS REST responses deterministically. |
| `mypy` | Static type checking | The stack is heavily typed (pydantic, typer, python-kis) — mypy catches signal-shape mistakes early. |

## Installation

```bash
# With uv (recommended)
uv init && uv venv --python 3.12
uv add python-kis pykrx ta anthropic openai pydantic pydantic-settings \
       typer structlog httpx beautifulsoup4 lxml tenacity pandas
uv add --dev ruff pytest pytest-httpx mypy

# Or with pip
python3.12 -m venv .venv && source .venv/bin/activate
pip install python-kis pykrx ta anthropic openai pydantic pydantic-settings \
            typer structlog httpx beautifulsoup4 lxml tenacity pandas
pip install -U ruff pytest pytest-httpx mypy
```

## Strict JSON LLM Contract — How to Enforce It

The `{"decision","confidence","reason"}` contract is the spine of the project. Define it once as a Pydantic model and reuse it for both providers:

```python
from enum import Enum
from pydantic import BaseModel, Field

class Decision(str, Enum):
    BUY = "BUY"; SELL = "SELL"; HOLD = "HOLD"

class TradeSignal(BaseModel):
    decision: Decision
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
```

**Anthropic (Claude) — forced tool use is the strongest guarantee:**
- Define one tool whose `input_schema` is the `TradeSignal` schema, set `strict: true` on the tool (schema must have `additionalProperties: false` + `required`), and force it with `tool_choice={"type": "tool", "name": "emit_signal"}`. The `tool_use.input` is then guaranteed to validate.
- Alternative: `output_config={"format": {"type": "json_schema", "schema": ...}}`, or `client.messages.parse(output_format=TradeSignal)`.
- Default model `claude-opus-4-8` (cost-sensitive: `claude-sonnet-4-6`).
- NOTE for 4.6+ models: assistant-message prefill and `budget_tokens` both return 400 — do not use the old "prefill `{` to force JSON" trick; use tool use / structured outputs instead.

**OpenAI — Pydantic-parsed structured outputs:**
- `client.responses.parse(model=..., input=..., text_format=TradeSignal)` (Responses API) or `client.chat.completions.parse(..., response_format=TradeSignal)` returns a validated `TradeSignal` instance directly.
- Equivalent raw form: `response_format={"type": "json_schema", "json_schema": {"strict": True, "schema": ...}}`.

**Fail-safe wiring:** wrap the provider call so that any `pydantic.ValidationError`, refusal, or empty/parse failure maps to "no trade." A switchable `LLMProvider` protocol with two implementations keeps the one-active-provider constraint clean.

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| `python-kis` | Direct KIS REST/websocket (`httpx`) | If you need a KIS endpoint the wrapper doesn't cover, or want zero third-party trust in the order path. Costs you token/hashkey/tr_id/domain boilerplate. |
| `python-kis` | `mojito2` | Effectively never — unmaintained since 2023, no documented mock support. |
| `python-kis` | `pjueon/pykis` | Another KIS wrapper; viable, but `python-kis` (Soju06) has broader websocket + mock coverage and more recent activity. Re-evaluate only if `python-kis` stalls. |
| `ta` | `pandas-ta-classic` | If you need many more indicators / candlestick patterns (253) than `ta` offers, and still want no C dependency. |
| `ta` | `TA-Lib` | If you need battle-tested C-speed indicators at scale and can absorb the native-library install. Overkill for one personal bot. |
| SQLite | CSV files | If you only ever append and never query; SQLite is barely more effort and far more useful for review. |
| `typer` CLI | APScheduler / cron | Deferred — v1 is manual-trigger by decision. Add when promoting to an always-on loop. |
| `structlog` | stdlib `logging` only | Fine if you don't need machine-parseable lines; structured logs make the required per-cycle audit far easier to query later. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| `mojito2` | Last release v0.1.6 (2023-02-23), unmaintained, no mock-account support documented. The order path must be on maintained code. | `python-kis` |
| `TA-Lib` (as default) | Requires installing a separate C library (`brew install ta-lib` / manual build); a recurring source of CI/install failures. | `ta` (pure-Python) |
| Mainline `pandas-ta` | v0.4.71b0 now requires Python 3.12+, classified "inactive"/yearly-maintenance (Snyk); riskier base for a long-lived project. | `ta`, or `pandas-ta-classic` fork if you need breadth |
| Assistant-prefill JSON forcing | Returns HTTP 400 on Claude 4.6+ models; the old "prefill `{`" pattern is dead. | Forced tool use + `strict: true` (Anthropic); `parse()` (OpenAI) |
| `requests` (sync, no retries by default) | Fine but dated; `httpx` gives timeouts/HTTP-2/async path for free. | `httpx` |
| Hardcoded keys / `os.getenv` sprawl | Untyped, easy to leak, no validation. | `pydantic-settings` + gitignored `.env` |
| `tiktoken` for Anthropic token counts | OpenAI's tokenizer; undercounts Claude tokens. | Anthropic `count_tokens` endpoint (only if you need counts) |

## Naver Finance Scraping — Notes

- Fetch with `httpx` (set a realistic `User-Agent`, sane timeouts), parse with `beautifulsoup4` + `lxml`, and wrap in `tenacity` retry with backoff.
- **Rate-limit yourself:** add a small delay between per-ticker requests and cap concurrency — this is a personal tool hitting a public site; be a polite client. Check `robots.txt` and avoid hammering. There is no official Naver Finance news API, so scraping is the documented source per PROJECT.md, but treat the HTML structure as unstable and isolate parsing behind one adapter module so a layout change is a one-file fix.
- Treat scraped text as **untrusted input** before it reaches the LLM prompt (it is third-party web content) — keep it clearly delimited in the prompt and never let it carry instructions.

## Stack Patterns by Variant

**If promoting to an always-on / intraday loop (post-v1):**
- Add `APScheduler` (in-process) or system `cron` calling the existing `typer` CLI.
- Because v1 already centralizes a cycle behind one CLI command, this is additive — no rearchitecture.

**If adding the LLM-ensemble option later (currently out of scope):**
- The `LLMProvider` protocol already abstracts providers; an ensemble is a third implementation that fans out to both and reconciles, not a stack change.

**If you outgrow SQLite for the audit log:**
- Move to DuckDB (analytical queries on cycle history) or Postgres (concurrency) — keep the same write-once-per-cycle schema.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `python-kis@2.1.6` | Python 3.10–3.13 | Use 3.12 to also satisfy any future mainline `pandas-ta`. |
| `pykrx@1.2.8` | Python >=3.10, pandas 2.x | Returns pandas DataFrames consumed by `ta`. |
| `ta@0.11.0` | pandas 2.x, numpy 1.x/2.x | Pure-Python; no native build step. |
| `pydantic@2.x` | `pydantic-settings@2.14.2`, `anthropic`, `openai` (both pydantic-v2 based) | One shared pydantic v2 across the whole project — avoid mixing v1. |
| `anthropic@0.40+` | Claude 4.6+ models | Adaptive thinking only; no `budget_tokens`, no assistant prefill (both 400). |
| `openai@2.44.0` | Responses API + `parse()` helpers | Pydantic-v2 models for `text_format` / `response_format`. |

## Sources

- pypi.org/project/python-kis (v2.1.6, 2025-10-13) — version, mock support, websocket, auth — HIGH
- pypi.org/project/mojito2 (v0.1.6, 2023-02-23) — confirmed unmaintained, no mock — MEDIUM
- pypi.org/project/pykrx + github.com/sharebook-kr/pykrx (v1.2.8, 2026-05-04) — functions, no indicators — HIGH
- pypi.org/project/pandas-ta, pypi.org/project/ta, Snyk advisor — indicator-lib maintenance/deps — HIGH
- claude-api skill (Anthropic SDK reference, cached 2026) — forced tool use + strict JSON, model IDs (`claude-opus-4-8`, `claude-sonnet-4-6`, `claude-haiku-4-5`), 4.6+ prefill/budget_tokens 400 — HIGH
- pypi.org/project/openai (v2.44.0, 2026-06) — `responses.parse` / `chat.completions.parse` structured outputs — HIGH
- pypi.org/project/pydantic-settings (v2.14.2, 2026-06-19) — BaseSettings/.env loading, secret-manager extras — HIGH

---
*Stack research for: Korean-market LLM trading bot (Python)*
*Researched: 2026-06-30*
