<!-- GSD:project-start source:PROJECT.md -->

## Project

**Stock Trading Bot (KR / LLM-driven)**

A personal, Korean-market automated trading bot that turns collected market data into
trading decisions via an LLM. It runs as three pipelines: a **data pipeline** (daily market
data + technical indicators via `pykrx`, real-time prices via the KIS API, and financial news
scraped from Naver Finance), an **LLM agent pipeline** (feeds the data as context to a
switchable LLM provider — Codex or OpenAI — which must emit a strict JSON trading signal),
and a **trading execution pipeline** (parses the signal and places orders through the KIS API).
Built for the owner's own use, safety-first: it validates against the KIS mock (모의투자)
account before ever touching real money.

**Core Value:** Given fresh market data, the bot produces a trustworthy, machine-checkable trading signal and
acts on it through KIS — without placing an order the rules don't justify.

### Constraints

- **Tech stack**: Python — required by `pykrx` and the KIS API boilerplate.
- **Data source**: Korea-only (pykrx + KIS) — the bot is KR-market specific.
- **LLM output**: Must be strict JSON `{"decision","confidence","reason"}`, no markdown — the
  execution pipeline parses it programmatically and unparseable output must fail safe (no trade).

- **Account safety**: KIS mock (모의투자) account is the first target; real-money promotion is a
  deliberate, gated step.

- **Execution gate**: A BUY requires `confidence >= 0.8`; lower-confidence or HOLD signals never trade.

<!-- GSD:project-end -->

<!-- GSD:stack-start source:research/STACK.md -->

## Technology Stack

## Executive Summary

- **KIS access:** Use the actively maintained community library **`python-kis`** (Soju06) for both real-time prices and order execution. It supports the KIS mock (모의투자) account natively, manages AppKey/SecretKey tokens for you, and wraps the websocket. Do NOT use `mojito2` (unmaintained since 2023, no mock support documented). Calling the KIS REST API directly is a viable fallback but adds significant boilerplate (token issuance/refresh, hashkey, tr_id juggling, domain switching) for no benefit at this scale.
- **Daily data:** **`pykrx`** for OHLCV + screening fundamentals. It does NOT compute indicators, so pair it with a TA library.
- **Indicators:** **`ta`** (pure-Python, no C dependency) is the pragmatic default — `TA-Lib` carries a painful C-library install, and mainline `pandas-ta` has gone yearly-maintenance and now requires Python 3.12+.
- **LLM:** Official **`anthropic`** and **`openai`** SDKs, switchable via config. Enforce the strict JSON contract with **forced tool use + `strict: true`** (Anthropic) and **`responses.parse` / `chat.completions.parse` with a Pydantic model** (OpenAI) — both validate against a Pydantic `TradeSignal` model and guarantee schema conformance, which is exactly what the "fail-safe on unparseable output" requirement needs.
- **Config/secrets:** **`pydantic-settings`** + a `.env` file (gitignored). **Scheduling:** a plain CLI (`typer`) for v1 — no scheduler, matching the manual-trigger decision. **Persistence:** **SQLite** via stdlib `sqlite3` for the per-cycle audit log; **logging:** stdlib `logging` with `structlog` for structured JSON lines.

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Python | 3.12+ | Runtime | Required by `pykrx` (>=3.10) and `python-kis` (3.10–3.13); 3.12 keeps the door open for mainline `pandas-ta` if ever needed. Use 3.12 (not 3.13) for the widest library compatibility. |
| `python-kis` | 2.1.6 (2025-10-13) | KIS real-time prices + order execution | Only actively maintained community KIS library. Native mock (모의투자) account support, automatic AppKey/SecretKey token issuance + refresh, websocket with auto-reconnect, type hints, English method names. Eliminates ~all KIS REST boilerplate. |
| `pykrx` | 1.2.8 (2026-05-04) | Daily OHLCV + screening fundamentals | De-facto standard for KRX daily data. `get_market_ohlcv`, ticker lists, PER/PBR/EPS/DIV, market cap, investor-type trading value, short-selling. Actively maintained. Scrapes KRX/Naver public data — no API key. |
| `ta` | 0.11.0 | Technical indicators (RSI, MACD, MAs, Bollinger) | Pure-Python on pandas, MIT, **no C dependency** → trivial `pip install`. `pykrx` returns raw OHLCV only, so an indicator lib is mandatory. Stable and sufficient for standard indicators. |
| `anthropic` | 0.40+ (current major) | Codex LLM provider | Official SDK. Forced tool use + `strict: true` gives a hard schema guarantee for the `{decision,confidence,reason}` contract. Default model `Codex-opus-4-8`. |
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

# With uv (recommended)

# Or with pip

## Strict JSON LLM Contract — How to Enforce It

- Define one tool whose `input_schema` is the `TradeSignal` schema, set `strict: true` on the tool (schema must have `additionalProperties: false` + `required`), and force it with `tool_choice={"type": "tool", "name": "emit_signal"}`. The `tool_use.input` is then guaranteed to validate.
- Alternative: `output_config={"format": {"type": "json_schema", "schema": ...}}`, or `client.messages.parse(output_format=TradeSignal)`.
- Default model `Codex-opus-4-8` (cost-sensitive: `Codex-sonnet-4-6`).
- NOTE for 4.6+ models: assistant-message prefill and `budget_tokens` both return 400 — do not use the old "prefill `{` to force JSON" trick; use tool use / structured outputs instead.
- `client.responses.parse(model=..., input=..., text_format=TradeSignal)` (Responses API) or `client.chat.completions.parse(..., response_format=TradeSignal)` returns a validated `TradeSignal` instance directly.
- Equivalent raw form: `response_format={"type": "json_schema", "json_schema": {"strict": True, "schema": ...}}`.

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
| Assistant-prefill JSON forcing | Returns HTTP 400 on Codex 4.6+ models; the old "prefill `{`" pattern is dead. | Forced tool use + `strict: true` (Anthropic); `parse()` (OpenAI) |
| `requests` (sync, no retries by default) | Fine but dated; `httpx` gives timeouts/HTTP-2/async path for free. | `httpx` |
| Hardcoded keys / `os.getenv` sprawl | Untyped, easy to leak, no validation. | `pydantic-settings` + gitignored `.env` |
| `tiktoken` for Anthropic token counts | OpenAI's tokenizer; undercounts Codex tokens. | Anthropic `count_tokens` endpoint (only if you need counts) |

## Naver Finance Scraping — Notes

- Fetch with `httpx` (set a realistic `User-Agent`, sane timeouts), parse with `beautifulsoup4` + `lxml`, and wrap in `tenacity` retry with backoff.
- **Rate-limit yourself:** add a small delay between per-ticker requests and cap concurrency — this is a personal tool hitting a public site; be a polite client. Check `robots.txt` and avoid hammering. There is no official Naver Finance news API, so scraping is the documented source per PROJECT.md, but treat the HTML structure as unstable and isolate parsing behind one adapter module so a layout change is a one-file fix.
- Treat scraped text as **untrusted input** before it reaches the LLM prompt (it is third-party web content) — keep it clearly delimited in the prompt and never let it carry instructions.

## Stack Patterns by Variant

- Add `APScheduler` (in-process) or system `cron` calling the existing `typer` CLI.
- Because v1 already centralizes a cycle behind one CLI command, this is additive — no rearchitecture.
- The `LLMProvider` protocol already abstracts providers; an ensemble is a third implementation that fans out to both and reconciles, not a stack change.
- Move to DuckDB (analytical queries on cycle history) or Postgres (concurrency) — keep the same write-once-per-cycle schema.

## Version Compatibility

| Package A | Compatible With | Notes |
|-----------|-----------------|-------|
| `python-kis@2.1.6` | Python 3.10–3.13 | Use 3.12 to also satisfy any future mainline `pandas-ta`. |
| `pykrx@1.2.8` | Python >=3.10, pandas 2.x | Returns pandas DataFrames consumed by `ta`. |
| `ta@0.11.0` | pandas 2.x, numpy 1.x/2.x | Pure-Python; no native build step. |
| `pydantic@2.x` | `pydantic-settings@2.14.2`, `anthropic`, `openai` (both pydantic-v2 based) | One shared pydantic v2 across the whole project — avoid mixing v1. |
| `anthropic@0.40+` | Codex 4.6+ models | Adaptive thinking only; no `budget_tokens`, no assistant prefill (both 400). |
| `openai@2.44.0` | Responses API + `parse()` helpers | Pydantic-v2 models for `text_format` / `response_format`. |

## Sources

- pypi.org/project/python-kis (v2.1.6, 2025-10-13) — version, mock support, websocket, auth — HIGH
- pypi.org/project/mojito2 (v0.1.6, 2023-02-23) — confirmed unmaintained, no mock — MEDIUM
- pypi.org/project/pykrx + github.com/sharebook-kr/pykrx (v1.2.8, 2026-05-04) — functions, no indicators — HIGH
- pypi.org/project/pandas-ta, pypi.org/project/ta, Snyk advisor — indicator-lib maintenance/deps — HIGH
- Codex-api skill (Anthropic SDK reference, cached 2026) — forced tool use + strict JSON, model IDs (`Codex-opus-4-8`, `Codex-sonnet-4-6`, `Codex-haiku-4-5`), 4.6+ prefill/budget_tokens 400 — HIGH
- pypi.org/project/openai (v2.44.0, 2026-06) — `responses.parse` / `chat.completions.parse` structured outputs — HIGH
- pypi.org/project/pydantic-settings (v2.14.2, 2026-06-19) — BaseSettings/.env loading, secret-manager extras — HIGH

<!-- GSD:stack-end -->

<!-- GSD:conventions-start source:CONVENTIONS.md -->

## Conventions

Conventions not yet established. Will populate as patterns emerge during development.
<!-- GSD:conventions-end -->

<!-- GSD:architecture-start source:ARCHITECTURE.md -->

## Architecture

Architecture not yet mapped. Follow existing patterns found in the codebase.
<!-- GSD:architecture-end -->

<!-- GSD:skills-start source:skills/ -->

## Project Skills

| Skill | Description | Path |
|-------|-------------|------|
| "source-command-gsd-mempalace-recall" | "Recall decisions, patterns, and surprises from MemPalace before planning" | `.agents/skills/source-command-gsd-mempalace-recall/SKILL.md` |
| "source-command-gsd-ns-context" | "codebase intel \| map graphify docs learnings mempalace" | `.agents/skills/source-command-gsd-ns-context/SKILL.md` |
| "source-command-gsd-ns-ideate" | "exploration capture \| explore sketch spike spec capture" | `.agents/skills/source-command-gsd-ns-ideate/SKILL.md` |
| "source-command-gsd-ns-manage" | "config workspace \| workstreams thread update ship inbox" | `.agents/skills/source-command-gsd-ns-manage/SKILL.md` |
| "source-command-gsd-ns-project" | "project lifecycle \| milestones audits summary" | `.agents/skills/source-command-gsd-ns-project/SKILL.md` |
| "source-command-gsd-ns-review" | "quality gates \| code review debug audit security eval ui" | `.agents/skills/source-command-gsd-ns-review/SKILL.md` |
| "source-command-gsd-ns-workflow" | "workflow \| discuss plan execute verify phase progress" | `.agents/skills/source-command-gsd-ns-workflow/SKILL.md` |
| "source-command-gsd-review-backlog" | "Review and promote backlog items to active milestone" | `.agents/skills/source-command-gsd-review-backlog/SKILL.md` |
| "source-command-gsd-workstreams" | "Manage parallel workstreams — list, create, switch, status, progress, complete, and resume" | `.agents/skills/source-command-gsd-workstreams/SKILL.md` |
<!-- GSD:skills-end -->

<!-- GSD:workflow-start source:GSD defaults -->

## GSD Workflow Enforcement

Before using Edit, Write, or other file-changing tools, start work through a GSD command so planning artifacts and execution context stay in sync.

Use these entry points:

- `/gsd-quick` for small fixes, doc updates, and ad-hoc tasks
- `/gsd-debug` for investigation and bug fixing
- `/gsd-execute-phase` for planned phase work

Do not make direct repo edits outside a GSD workflow unless the user explicitly asks to bypass it.
<!-- GSD:workflow-end -->

<!-- GSD:profile-start -->

## Developer Profile

> Profile not yet configured. Run `/gsd-profile-user` to generate your developer profile.
> This section is managed by `generate-Codex-profile` -- do not edit manually.
<!-- GSD:profile-end -->
