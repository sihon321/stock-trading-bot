# Phase 3: Data Pipeline - Research

**Researched:** 2026-07-01
**Domain:** Korean-market market data adapters, KIS quote auth, indicators, source-health normalization
**Confidence:** MEDIUM

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
## Implementation Decisions

### Safety Path
- **D-01:** Daily OHLCV freshness follows a hybrid policy by ticker state. For screener/new candidates, bad, empty, stale, or unusable data skips the ticker. For portfolio/existing holdings, bad data fails closed by freezing actions and forcing HOLD while recording the problem. For holidays/weekends or natural market closures, the pipeline may gracefully fall back to the last valid KRX trading day instead of treating the closure as an error.
- **D-02:** KIS real-time price access must use one shared cached token manager with bounded retry/backoff. If token refresh, throttling, or price fetch still fails after the bounded retry policy, the price is unavailable and safety policy applies rather than retrying aggressively.
- **D-03:** Whenever Phase 3 skips or freezes a ticker due to missing/stale/unavailable source data, it should record a structured audit event and also print a visible console warning during the run. The event should include ticker, source, reason, observed date/time, expected trading date when applicable, and action taken such as `SKIP_CANDIDATE` or `FORCE_HOLD`.

### Data Shape
- **D-04:** Concrete adapters may return rich internal typed results, but the public LLM-facing `DataContext` should remain compact. Keep the boundary oriented around ticker, current price, flat technical values, and capped sanitized news strings; source metadata and health can live in adapter/orchestration results rather than bloating the prompt context.
- **D-05:** The baseline indicator set should be tailored for volatility-breakout workflows without becoming a full technical-analysis pack. Include moving averages, RSI, volatility metrics such as ATR or historical volatility, and volume ratios. Do not require MACD or Bollinger Bands in Phase 3 unless research/planning finds a narrow reason.
- **D-06:** Naver news should stay structured internally, but render into `DataContext.news` only as capped sanitized strings. Sanitization must strip markup and prompt-like instructions so scraped news remains untrusted data for Phase 4.

### Screener Policy
- **D-07:** The daily screener should optimize for volatility-breakout readiness: liquid names with sufficient ATR/historical volatility and volume expansion. This is preferred over generic momentum-only or large-cap-only ranking.
- **D-08:** Candidate universe breadth should be configurable, with a setting such as `screener_max_candidates`. Default to a small operator-reviewable shortlist, but do not hard-code that as the only possible cap.
- **D-09:** Market inclusion should be configurable, defaulting to KOSPI + KOSDAQ with liquidity floors and the ability to restrict markets later.

### Screener Detail
- **D-10:** Screener ranking should treat ATR/historical volatility and a liquidity floor as primary inputs. Volume expansion and recent momentum rank within the surviving set.
- **D-11:** Low-liquidity, suspended, halted, or bad-data tickers should be hard-excluded before ranking by default. Liquidity floors and excluded ticker states should be configurable.
- **D-12:** Lock screener policy and safety constraints now, not exact thresholds or score weights. The planner/researcher should choose concrete thresholds and formulas after checking current pykrx/KRX behavior and data quality.

### Adapter Boundaries
- **D-13:** Split Phase 3 into source adapters plus pure transforms plus a thin `DataSource` orchestrator. pykrx, KIS token/price, and Naver news should be source-specific adapters; indicator calculation, screener scoring/filtering, and news sanitization should be pure/testable transforms.
- **D-14:** The KIS token manager should be built as shared KIS infrastructure now. Phase 3 price calls consume it first, and Phase 5 broker/order calls should be able to reuse it instead of creating a second token flow.
- **D-15:** Source-specific failures should be normalized at each adapter boundary. pykrx/KIS/Naver adapters convert vendor exceptions, empty frames, bad DOM, throttles, token failures, and source-specific bad data into typed unavailable/stale/source-health results so the orchestrator applies policy consistently.

### the agent's Discretion
The planner may choose exact module names, dataclass names, enum names, retry counts, refresh-margin defaults, indicator implementation details, and screener threshold defaults consistent with the decisions above. Exact scoring formulas and thresholds are intentionally left for planning/research after validating current pykrx/KRX/KIS behavior.

### Deferred Ideas (OUT OF SCOPE)
## Deferred Ideas

None - discussion stayed within Phase 3 scope. Exact KIS retry defaults, token refresh margin, screener thresholds, and ranking formula are intentionally deferred to research/planning within this phase, not to a later capability.
</user_constraints>

## Summary

Phase 3 should add concrete data adapters behind the existing synchronous `DataSource` Protocol while keeping `trading_bot.ports` and the compact `DataContext` free of pykrx, KIS, Naver, and HTTP dependencies. [VERIFIED: codebase grep] The correct plan shape is source adapters plus pure transforms plus a thin orchestrator: pykrx handles daily OHLCV and whole-market screen inputs, `ta` handles indicator calculations, direct KIS REST via `httpx` handles current price through one shared token manager, and Naver news is isolated behind a fail-soft, sanitized, compliance-gated adapter. [CITED: github.com/sharebook-kr/pykrx] [CITED: technical-analysis-library-in-python.readthedocs.io] [CITED: github.com/koreainvestment/open-trading-api]

The biggest planning constraint is dependency/runtime compatibility. Current `pykrx` 1.2.8 declares Python `>=3.10` and depends on `pandas>=2.2,<3.0`, while this project currently declares `requires-python >=3.9`; plan Wave 0 must raise the lower bound to `>=3.10` or deliberately pin older packages. [VERIFIED: pypi registry] [CITED: github.com/sharebook-kr/pykrx/pyproject.toml] KIS details are MEDIUM confidence because the public portal exposes multiple token-duration contexts: standard REST token samples use daily tokens, while a partnership document describes 90-day user access tokens; the project settings model maps to the standard appkey/appsecret REST flow. [CITED: apiportal.koreainvestment.com/apiservice-apiservice] [CITED: apiportal.koreainvestment.com/provider-doc4] [CITED: github.com/koreainvestment/open-trading-api]

Naver Finance news scraping is the highest non-technical risk. `https://finance.naver.com/robots.txt` currently disallows general `User-agent: *`, and the live item-news HTML is EUC-KR, table-based, and JavaScript-rewrites news links. [VERIFIED: live curl] The planner should add a human verification checkpoint before enabling Naver scraping; implementation should degrade to empty news and continue the cycle when the checkpoint is not approved or the DOM changes. [ASSUMED]

**Primary recommendation:** Plan a direct, typed adapter pipeline with a Wave 0 dependency/runtime update, explicit source-health result types, KIS shared token manager, compliance-gated Naver adapter, and tests that prove bad/stale data cannot create a BUY. [VERIFIED: codebase grep]

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|--------------|----------------|-----------|
| Daily OHLCV fetch and freshness assertion | API / Backend | External KRX/Naver public data via pykrx | The backend owns data validation and source-health decisions before LLM/execution sees inputs. [CITED: github.com/sharebook-kr/pykrx] |
| Technical indicators | API / Backend | Pure transform layer | Indicators are deterministic transforms over OHLCV and should be unit-tested without network calls. [CITED: technical-analysis-library-in-python.readthedocs.io] |
| Daily screener | API / Backend | External pykrx/KRX data | Screening ranks a point-in-time candidate universe and must hard-exclude bad data before ranking. [CITED: github.com/sharebook-kr/pykrx] |
| KIS access token cache | API / Backend | Local filesystem or in-memory cache | Shared token ownership belongs in backend infrastructure so Phase 3 quotes and Phase 5 orders reuse the same flow. [CITED: github.com/koreainvestment/open-trading-api] |
| KIS current price | API / Backend | KIS Open API | Quote fetching requires authenticated REST headers, TR ID, rate-limit handling, and typed unavailable results. [CITED: github.com/koreainvestment/open-trading-api] |
| Naver news fetch/sanitize | API / Backend | External Naver Finance HTML | Scraped text is untrusted external input; fetch, parse, sanitize, and degrade before building `DataContext.news`. [VERIFIED: live curl] |

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DATA-01 | System fetches daily OHLCV per ticker via `pykrx`, failing safe to HOLD on holiday/empty/stale data rather than acting on a bad frame | pykrx supports per-ticker OHLCV, but adjusted/empty edge cases require freshness validation and hybrid skip/freeze policy. [CITED: github.com/sharebook-kr/pykrx] [CITED: github.com/sharebook-kr/pykrx/issues/162] |
| DATA-02 | System computes technical indicators from daily OHLCV | `ta` documents RSI, SMA/EMA, and ATR indicators over pandas OHLCV series. [CITED: technical-analysis-library-in-python.readthedocs.io] |
| DATA-03 | System fetches real-time price via KIS API using shared, auto-refreshed access token | KIS sample uses `/oauth2/tokenP` token cache and `/uapi/domestic-stock/v1/quotations/inquire-price` with TR ID `FHKST01010100`. [CITED: github.com/koreainvestment/open-trading-api] |
| DATA-04 | System scrapes Naver Finance news with sanitization and graceful degradation | Live page uses EUC-KR table DOM, while robots disallow general crawling; plan a checkpoint and fail-soft empty-news behavior. [VERIFIED: live curl] |
| DATA-05 | System runs daily market screen via pykrx to select candidates | pykrx supports whole-market OHLCV by date/market and ticker lists for KOSPI/KOSDAQ/ALL. [CITED: github.com/sharebook-kr/pykrx] |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- Python is required because `pykrx` and KIS API boilerplate drive the stack. [CITED: .claude/CLAUDE.md]
- Data source scope is Korea-only through pykrx + KIS. [CITED: .claude/CLAUDE.md]
- LLM-facing context must support strict downstream JSON signal parsing, but Phase 3 does not implement LLM calls. [CITED: .claude/CLAUDE.md]
- KIS mock account is first target; real-money promotion is deliberately gated. [CITED: .claude/CLAUDE.md]
- Existing core ports must remain synchronous semantic Protocols and adapter-free. [VERIFIED: codebase grep]
- Project stack notes previously recommended `python-kis`, but Phase 3 locked a shared project-owned KIS token manager; use direct REST via `httpx` for this phase so token behavior is explicit and reusable by Phase 5. [CITED: .planning/phases/03-data-pipeline/03-CONTEXT.md]

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `pykrx` [WARNING: flagged as suspicious by package-legitimacy seam; verify before install.] | 1.2.8, published 2026-05-04 | KRX/Naver daily OHLCV, ticker lists, whole-market OHLCV for screener | Official project documents ticker lists, per-ticker OHLCV, whole-market OHLCV, market selection, and adjusted-price option. [CITED: github.com/sharebook-kr/pykrx] [VERIFIED: pypi registry] |
| `ta` [WARNING: flagged as suspicious by package-legitimacy seam; verify before install.] | 0.11.0, published 2023-11-02 | RSI, moving averages, ATR, volatility metrics | Official docs list RSIIndicator, SMA/EMA indicators, and AverageTrueRange over pandas data. [CITED: technical-analysis-library-in-python.readthedocs.io] [VERIFIED: pypi registry] |
| `httpx` [WARNING: flagged as suspicious by package-legitimacy seam; verify before install.] | 0.28.1, published 2024-12-06 | KIS REST calls and optional Naver HTTP fetches | Official docs provide explicit timeout controls and default timeout behavior; it supports a clean injectable client seam. [CITED: python-httpx.org/advanced/timeouts] [VERIFIED: pypi registry] |
| `pandas` [WARNING: flagged as suspicious by package-legitimacy seam; verify before using directly.] | use pykrx-compatible `<3.0`; pykrx requires `>=2.2,<3.0` | DataFrame shape for OHLCV and indicator transforms | pykrx returns pandas DataFrames and declares pandas dependency bounds. [CITED: github.com/sharebook-kr/pykrx/pyproject.toml] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `beautifulsoup4` [WARNING: flagged as suspicious by package-legitimacy seam; verify before install.] | 4.15.0, published 2026-06-07 | Parse Naver Finance HTML | Use only if Naver scraping checkpoint is approved; parse one isolated adapter. [CITED: crummy.com/software/BeautifulSoup/bs4/doc] |
| `lxml` [WARNING: flagged as suspicious by package-legitimacy seam; verify before install.] | 6.1.1, published 2026-05-18 | Parser backend for broken HTML | Use with BeautifulSoup for explicit parser behavior on real-world HTML. [CITED: lxml.de/elementsoup.html] |
| `tenacity` [WARNING: flagged as suspicious by package-legitimacy seam; verify before install.] | 9.1.4, published 2026-02-07 | Bounded retry/backoff | Use for transient KIS/Naver network failures only; do not retry stale/invalid data. [CITED: tenacity.readthedocs.io] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Direct KIS REST via `httpx` | `python-kis` | `python-kis` may reduce boilerplate, but it hides the shared token manager locked for Phase 3 and Phase 5 reuse. [CITED: .planning/phases/03-data-pipeline/03-CONTEXT.md] |
| `ta` | Hand-written indicators | Hand-written RSI/ATR creates avoidable edge-case risk around warm-up windows and NaNs. [CITED: technical-analysis-library-in-python.readthedocs.io] |
| BeautifulSoup/lxml | `pandas.read_html` | `read_html` is brittle for DOM changes and does not naturally centralize sanitization. [ASSUMED] |

**Installation:**
```bash
python3 -m pip install "pykrx==1.2.8" "ta==0.11.0" "httpx==0.28.1" "beautifulsoup4==4.15.0" "lxml==6.1.1" "tenacity==9.1.4"
```

**Version verification:**
```bash
python3 -m pip index versions pykrx
python3 -m pip index versions ta
python3 -m pip index versions httpx
python3 -m pip index versions beautifulsoup4
python3 -m pip index versions lxml
python3 -m pip index versions tenacity
```

## Package Legitimacy Audit

| Package | Registry | Age | Downloads | Source Repo | Verdict | Disposition |
|---------|----------|-----|-----------|-------------|---------|-------------|
| pykrx | PyPI | Published 2026-05-04 | unknown | github.com/sharebook-kr/pykrx | SUS: unknown downloads | Flagged - planner must add checkpoint |
| ta | PyPI | Published 2023-11-02 | unknown | github.com/bukosabino/ta | SUS: unknown downloads | Flagged - planner must add checkpoint |
| httpx | PyPI | Published 2024-12-06 | unknown | github.com/encode/httpx | SUS: unknown downloads | Flagged - planner must add checkpoint |
| beautifulsoup4 | PyPI | Published 2026-06-07 | unknown | crummy.com/software/BeautifulSoup/bs4 | SUS: too new, unknown downloads | Flagged - planner must add checkpoint |
| lxml | PyPI | Published 2026-05-18 | unknown | github.com/lxml/lxml | SUS: unknown downloads | Flagged - planner must add checkpoint |
| tenacity | PyPI | Published 2026-02-07 | unknown | github.com/jd/tenacity | SUS: unknown downloads | Flagged - planner must add checkpoint |
| pandas | PyPI | Latest 3.0.3 published 2026-05-11; use pykrx-bound `<3.0` | unknown | none from seam | SUS: unknown downloads, no repository | Transitive via pykrx; do not install latest 3.x |

**Packages removed due to [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** pykrx, ta, httpx, beautifulsoup4, lxml, tenacity, pandas

*Packages discovered via WebSearch or training data that have not been verified against an authoritative source are tagged `[ASSUMED]` and the planner must gate each install behind a `checkpoint:human-verify` task.*

## Architecture Patterns

### System Architecture Diagram

```text
Manual cycle / screener run
        |
        v
DataSource orchestrator
        |
        +--> pykrx adapter --> OHLCV frame validator --> source-health result
        |                         |
        |                         v
        |                    indicator transform (ta)
        |
        +--> KIS quote adapter --> shared token manager --> KIS /oauth2/tokenP + inquire-price
        |                         |
        |                         v
        |                    rate-limit + retry policy
        |
        +--> Naver news adapter --> HTML parser --> sanitizer --> capped news strings
        |
        v
Policy resolver: SKIP_CANDIDATE / FORCE_HOLD / BUILD_CONTEXT
        |
        v
Compact DataContext(ticker, current_price, technicals, news)
```

### Recommended Project Structure

```text
trading_bot/
├── data_source.py          # Thin DataSource orchestrator
├── data_models.py          # SourceHealth, adapter result dataclasses, audit events
├── indicators.py           # Pure OHLCV -> flat technical dict
├── screener.py             # Pure ranking/filtering over validated market data
├── pykrx_adapter.py        # pykrx calls and frame normalization
├── kis_auth.py             # Shared cached token manager
├── kis_quote.py            # KIS current-price REST adapter
└── naver_news.py           # Fetch/parse/sanitize/fail-soft news adapter
tests/
├── test_pykrx_adapter.py
├── test_indicators.py
├── test_screener.py
├── test_kis_auth.py
├── test_kis_quote.py
├── test_naver_news.py
└── test_data_source.py
```

### Pattern 1: Adapter Result Normalization
**What:** Each adapter returns typed `AVAILABLE`, `UNAVAILABLE`, or `STALE` results with source, observed timestamp/date, reason, and raw-vendor details kept out of `DataContext`. [VERIFIED: codebase grep]
**When to use:** Every pykrx/KIS/Naver boundary.
**Example:**
```python
# Source: local project pattern + Phase 3 D-15
@dataclass(frozen=True)
class SourceHealth:
    source: str
    status: str
    reason: str
    observed_at: datetime
```

### Pattern 2: Point-In-Time Screener
**What:** Build candidate universes from an asserted KRX trading date, whole-market OHLCV, and validated per-ticker lookback data. [CITED: github.com/sharebook-kr/pykrx]
**When to use:** Daily screen before LLM evaluation cycle.
**Example:**
```python
# Source: pykrx README whole-market get_market_ohlcv(date, market)
market_frame = stock.get_market_ohlcv(trading_date, market="KOSPI")
```

### Pattern 3: KIS Token Manager
**What:** Centralize token cache, expiry margin, refresh lock, bounded retry, and auth failure normalization. [CITED: github.com/koreainvestment/open-trading-api]
**When to use:** All KIS adapters, including future Phase 5 orders.
**Example:**
```python
# Source: KIS official sample uses /oauth2/tokenP and access_token_token_expired
payload = {"grant_type": "client_credentials", "appkey": app_key, "appsecret": app_secret}
```

### Anti-Patterns to Avoid
- **Per-call token issuance:** KIS samples cache tokens and note daily validity; per-call token issue risks throttling and avoidable auth failures. [CITED: github.com/koreainvestment/open-trading-api]
- **Letting empty OHLCV pass as neutral data:** Empty/stale frames must be unavailable/stale, not zero-valued indicators. [CITED: github.com/sharebook-kr/pykrx/issues/270]
- **Expanding DataContext with raw source metadata:** Phase 3 locks compact LLM-facing context; keep metadata in adapter/orchestrator results. [CITED: .planning/phases/03-data-pipeline/03-CONTEXT.md]
- **Treating scraped news as trusted instructions:** News is untrusted third-party text and must be sanitized before Phase 4 prompts. [CITED: .codex/gsd-core/references/untrusted-input-boundary.md]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Korean OHLCV scraping | Custom KRX/Naver scraping | `pykrx` | pykrx already wraps ticker lists and market OHLCV but still needs validation. [CITED: github.com/sharebook-kr/pykrx] |
| RSI/ATR/moving averages | Custom indicator math | `ta` | Indicator warm-up, NaN handling, and formula consistency are easy to get wrong. [CITED: technical-analysis-library-in-python.readthedocs.io] |
| HTTP timeouts | Raw sockets or unbounded requests | `httpx.Timeout` | HTTPX documents default timeout behavior and explicit configuration. [CITED: python-httpx.org/advanced/timeouts] |
| Retry loops | `while True` retry | `tenacity` bounded stop/wait policies | Tenacity gives explicit stop and wait controls. [CITED: tenacity.readthedocs.io] |
| HTML parsing | Regex over raw HTML | BeautifulSoup + lxml | Parser-backed extraction is less brittle than ad hoc regex. [CITED: crummy.com/software/BeautifulSoup/bs4/doc] |

**Key insight:** Custom code should own source-health policy and orchestration, not vendor scraping, indicator formulas, token refresh retries, or HTML parsing. [ASSUMED]

## Common Pitfalls

### Pitfall 1: pykrx Adjusted-Price and Empty-Frame Surprises
**What goes wrong:** `adjusted=True` or `adjusted=False` can return unexpected or empty historical data in reported pykrx issues. [CITED: github.com/sharebook-kr/pykrx/issues/162] [CITED: github.com/sharebook-kr/pykrx/issues/270]
**Why it happens:** pykrx scrapes external services and its README warns data may differ from official data. [CITED: github.com/sharebook-kr/pykrx]
**How to avoid:** Require minimum rows, monotonic date index, expected latest trading date, nonzero price sanity, and explicit adjusted policy tests.
**Warning signs:** Empty DataFrame, latest index before expected trading date, zero OHLC prices, missing columns.

### Pitfall 2: KIS Token Duration Confusion
**What goes wrong:** Planner assumes one TTL for all KIS accounts. [CITED: apiportal.koreainvestment.com/apiservice-apiservice] [CITED: apiportal.koreainvestment.com/provider-doc4]
**Why it happens:** Public docs show standard REST daily token flow and separate partnership 90-day user-token flow.
**How to avoid:** Implement token manager from response `access_token_token_expired`, not hard-coded TTL, and add manual portal verification for the active account type.
**Warning signs:** Token refresh every call, token expiry ignored, no refresh margin, no lock around refresh.

### Pitfall 3: Naver Scraping Compliance and DOM Fragility
**What goes wrong:** Scraper breaks or violates robots policy. [VERIFIED: live curl]
**Why it happens:** Current robots disallows general crawlers and item-news page is EUC-KR table HTML with JavaScript link rewriting.
**How to avoid:** Add human checkpoint before enabling, isolate parser, set low request rate, and degrade to `news=()`.
**Warning signs:** Encoding garbage, no `table.type5`, link rewrite script changes, HTTP 403/429.

### Pitfall 4: Screener Lookahead Bias
**What goes wrong:** Candidate selection uses latest available data after the asserted trading date. [ASSUMED]
**Why it happens:** Convenience calls without explicit dates may use recent business day internally.
**How to avoid:** Pass explicit Asia/Seoul trading date into all pykrx calls and include date in audit output.
**Warning signs:** Tests freeze time but screener result changes based on current date.

## Code Examples

Verified patterns from official sources:

### pykrx Per-Ticker OHLCV
```python
# Source: https://github.com/sharebook-kr/pykrx README
from pykrx import stock

df = stock.get_market_ohlcv("20220720", "20220810", "005930")
```

### pykrx Whole-Market OHLCV
```python
# Source: https://github.com/sharebook-kr/pykrx README
from pykrx import stock

df = stock.get_market_ohlcv("20200831", market="KOSDAQ")
```

### KIS Current Price Endpoint
```python
# Source: https://github.com/koreainvestment/open-trading-api examples_llm/domestic_stock/inquire_price
API_URL = "/uapi/domestic-stock/v1/quotations/inquire-price"
tr_id = "FHKST01010100"
params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": "005930"}
```

### Indicator Transform
```python
# Source: https://technical-analysis-library-in-python.readthedocs.io/
from ta.momentum import RSIIndicator
from ta.trend import SMAIndicator
from ta.volatility import AverageTrueRange

technicals = {
    "rsi_14": float(RSIIndicator(close=df["종가"], window=14).rsi().iloc[-1]),
    "sma_20": float(SMAIndicator(close=df["종가"], window=20).sma_indicator().iloc[-1]),
    "atr_14": float(AverageTrueRange(high=df["고가"], low=df["저가"], close=df["종가"], window=14).average_true_range().iloc[-1]),
}
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Project `requires-python >=3.9` | Raise to at least `>=3.10` for current pykrx | pykrx 1.2.8 current metadata | Planner needs Wave 0 dependency/runtime task. [CITED: github.com/sharebook-kr/pykrx/pyproject.toml] |
| Blind KIS token issue per call | Cache token until response expiry with refresh margin | KIS official sample caches token by expiry | Avoids throttling and aligns with D-02/D-14. [CITED: github.com/koreainvestment/open-trading-api] |
| Naver scrape as ordinary data source | Human-gated, fail-soft optional adapter | Current robots.txt checked 2026-07-01 | Prevents Phase 3 from depending on non-compliant scraping. [VERIFIED: live curl] |

**Deprecated/outdated:**
- Hard-coding KIS token TTL: use the token response expiry and manual portal verification. [CITED: github.com/koreainvestment/open-trading-api]
- Regex HTML parser for Naver news: use parser-backed extraction and sanitizer. [CITED: crummy.com/software/BeautifulSoup/bs4/doc]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | BeautifulSoup/lxml is better than `pandas.read_html` for centralizing sanitizer behavior. | Alternatives Considered | Parser implementation may be more work than needed. |
| A2 | Custom code should own source-health policy rather than vendor scraping or indicator formulas. | Don't Hand-Roll | Planner may over-depend on third-party libraries. |
| A3 | Screener lookahead bias is a likely risk if explicit dates are not passed everywhere. | Common Pitfalls | False positives in strategy validation. |
| A4 | Naver scraping should degrade to no news if human/legal checkpoint is not approved. | Summary | DATA-04 may need requirement clarification. |

## Open Questions — RESOLVED by Plan 03-01 Manual Decision Contract

The following questions are no longer unresolved research blockers. They are intentionally routed to the blocking manual checkpoint in `.planning/phases/03-data-pipeline/03-01-PLAN.md` and recorded in `.planning/phases/03-data-pipeline/03-MANUAL-DECISIONS.md` before provider behavior is enabled.

1. **RESOLVED: Can Naver Finance scraping be enabled under the operator's acceptable-use policy?**
   - What we know: robots.txt currently disallows general crawlers; live page can be parsed. [VERIFIED: live curl]
   - Resolution: Plan 03-01 has a blocking manual verification task requiring the operator to approve or disable Naver Finance scraping and record the decision in `03-MANUAL-DECISIONS.md`.
   - Implementation contract: Until that recorded decision approves enablement, the Naver adapter remains disabled/unapproved and returns empty news safely.

2. **RESOLVED: What are the exact active KIS portal rate limits for this account?**
   - What we know: KIS has 2026 portal notices about per-second call limits and official samples sleep 0.05s in prod and 0.5s in mock. [CITED: apiportal.koreainvestment.com] [CITED: github.com/koreainvestment/open-trading-api]
   - Resolution: Plan 03-01 has a blocking manual verification task requiring the operator to verify active-account token TTL and rate-limit values in the KIS portal and record the exact values in `03-MANUAL-DECISIONS.md`.
   - Implementation contract: KIS token/quote code consumes the recorded values for `kis_min_interval_seconds`, refresh margin, and bounded retry defaults; missing or unrecorded values keep live provider behavior disabled.

3. **RESOLVED: Should pykrx use adjusted or unadjusted OHLCV for Phase 3 indicators?**
   - What we know: README says adjusted is default and issues report adjusted-data edge cases. [CITED: github.com/sharebook-kr/pykrx] [CITED: github.com/sharebook-kr/pykrx/issues/162]
   - Resolution: Plan 03-01 has a blocking manual verification task requiring the operator to choose and record the Phase 3 `ohlcv_adjusted` default in `03-MANUAL-DECISIONS.md`.
   - Implementation contract: The pykrx adapter exposes `ohlcv_adjusted` as configuration and asserts frame quality for either selected mode.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python | Runtime | yes | 3.14.3 | Use project-local Python 3.10+ if library incompatibility appears. |
| pip | Dependency install | yes | 26.0 | — |
| pytest | Validation | yes via `PYTHONUSERBASE=$PWD/.python-userbase python3 -m pytest` | 8.4.2 | Install project dependencies into local userbase. |
| curl | Live provider checks | yes | 8.7.1 | Python `urllib`/`httpx` after install. |
| pykrx | DATA-01/DATA-05 | no | — | Install after package checkpoint. |
| ta | DATA-02 | no | — | Install after package checkpoint. |
| httpx | DATA-03/DATA-04 | no | — | stdlib `urllib` only for tests; not recommended for implementation. |
| beautifulsoup4/lxml | DATA-04 | no | — | Disable Naver adapter and return empty news. |
| tenacity | KIS/Naver bounded retries | no | — | Small local retry helper, but library preferred after checkpoint. |

**Missing dependencies with no fallback:**
- `pykrx` for real DATA-01/DATA-05 behavior.
- `ta` for DATA-02 if planner avoids hand-rolled indicators.
- `httpx` for production KIS REST adapter.

**Missing dependencies with fallback:**
- `beautifulsoup4`/`lxml`: fallback is no-news adapter until checkpoint/install.
- `tenacity`: fallback is limited local retry, but add checkpoint before install.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.4.2 [VERIFIED: local command] |
| Config file | `pyproject.toml` |
| Quick run command | `PYTHONUSERBASE=$PWD/.python-userbase python3 -m pytest tests/test_indicators.py tests/test_screener.py tests/test_data_source.py -q` |
| Full suite command | `PYTHONUSERBASE=$PWD/.python-userbase python3 -m pytest` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| DATA-01 | Empty/stale/holiday pykrx frame maps to SKIP_CANDIDATE or FORCE_HOLD | unit | `PYTHONUSERBASE=$PWD/.python-userbase python3 -m pytest tests/test_pykrx_adapter.py -q` | no - Wave 0 |
| DATA-02 | RSI/SMA/ATR/volume ratio computed from valid OHLCV and excludes NaN warm-up rows | unit | `PYTHONUSERBASE=$PWD/.python-userbase python3 -m pytest tests/test_indicators.py -q` | no - Wave 0 |
| DATA-03 | KIS token cache is shared, refreshes before expiry, and quote failures normalize to unavailable | unit | `PYTHONUSERBASE=$PWD/.python-userbase python3 -m pytest tests/test_kis_auth.py tests/test_kis_quote.py -q` | no - Wave 0 |
| DATA-04 | Naver parser sanitizes text and returns empty news on failure/disallowed mode | unit | `PYTHONUSERBASE=$PWD/.python-userbase python3 -m pytest tests/test_naver_news.py -q` | no - Wave 0 |
| DATA-05 | Screener filters low-liquidity/bad-data names and ranks by volatility-breakout inputs using asserted date | unit | `PYTHONUSERBASE=$PWD/.python-userbase python3 -m pytest tests/test_screener.py -q` | no - Wave 0 |

### Sampling Rate
- **Per task commit:** `PYTHONUSERBASE=$PWD/.python-userbase python3 -m pytest tests/test_<changed_module>.py -q`
- **Per wave merge:** `PYTHONUSERBASE=$PWD/.python-userbase python3 -m pytest`
- **Phase gate:** Full suite green plus manual KIS/Naver checkpoints recorded before `$gsd-verify-work`.

### Wave 0 Gaps
- [ ] `tests/test_pykrx_adapter.py` - covers DATA-01 and pykrx source-health normalization.
- [ ] `tests/test_indicators.py` - covers DATA-02.
- [ ] `tests/test_kis_auth.py` and `tests/test_kis_quote.py` - cover DATA-03.
- [ ] `tests/test_naver_news.py` - covers DATA-04 and sanitizer.
- [ ] `tests/test_screener.py` - covers DATA-05.
- [ ] `tests/test_data_source.py` - covers orchestrator policy and compact `DataContext`.
- [ ] Dependency metadata update - raise project Python lower bound to `>=3.10` or pin older compatible versions.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | yes | KIS secrets stay in `Settings.active_kis`; access token cached without logging token values. [VERIFIED: codebase grep] |
| V3 Session Management | no | No browser/user sessions in Phase 3. [VERIFIED: codebase grep] |
| V4 Access Control | no | Single-user local tool; real-trading gate remains config-level. [CITED: .claude/CLAUDE.md] |
| V5 Input Validation | yes | Validate ticker format, KIS response numeric fields, OHLCV schema, and sanitize news. [VERIFIED: codebase grep] |
| V6 Cryptography | yes | Use TLS via HTTPS clients; do not implement custom crypto for tokens. [CITED: python-httpx.org] |

### Known Threat Patterns for Python Data Pipeline

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Prompt injection through scraped news | Tampering | Strip markup/control text, cap strings, keep news clearly untrusted for Phase 4. [CITED: .codex/gsd-core/references/untrusted-input-boundary.md] |
| Secret/token leakage in logs | Information Disclosure | Redact KIS appsecret/access token; audit source-health reasons without raw headers. [VERIFIED: codebase grep] |
| API throttling/denial by retry storm | Denial of Service | Shared token cache, minimum request interval, bounded retry/backoff. [CITED: github.com/koreainvestment/open-trading-api] |
| Bad market data causing unsafe BUY | Tampering | Source-health normalization, stale assertions, skip/freeze policy before LLM/execution. [CITED: .planning/phases/03-data-pipeline/03-CONTEXT.md] |

## Sources

### Primary (HIGH confidence)
- Local codebase: `trading_bot/domain.py`, `trading_bot/ports.py`, `trading_bot/config.py`, `trading_bot/execution.py`, `tests/test_ports.py` - existing ports, compact `DataContext`, settings, audit style, adapter-free import boundary. [VERIFIED: codebase grep]
- Local phase context: `.planning/phases/03-data-pipeline/03-CONTEXT.md` - locked user decisions D-01 through D-15. [VERIFIED: file read]

### Secondary (MEDIUM confidence)
- https://github.com/sharebook-kr/pykrx - pykrx README, OHLCV/ticker/market behavior, warnings, Python requirement. [CITED: github.com/sharebook-kr/pykrx]
- https://github.com/sharebook-kr/pykrx/issues/162 and issue #270 search result - adjusted-price/empty-data edge cases. [CITED: github.com/sharebook-kr/pykrx/issues/162]
- https://github.com/koreainvestment/open-trading-api - official KIS samples for token cache, quote endpoint, TR ID, headers, sleeps. [CITED: github.com/koreainvestment/open-trading-api]
- https://apiportal.koreainvestment.com/apiservice-apiservice - standard REST token portal page. [CITED: apiportal.koreainvestment.com/apiservice-apiservice]
- https://apiportal.koreainvestment.com/provider-doc4 - partnership token-duration page. [CITED: apiportal.koreainvestment.com/provider-doc4]
- https://technical-analysis-library-in-python.readthedocs.io - `ta` indicator docs. [CITED: technical-analysis-library-in-python.readthedocs.io]
- https://www.python-httpx.org/advanced/timeouts/ - HTTPX timeout docs. [CITED: python-httpx.org/advanced/timeouts]
- https://www.crummy.com/software/BeautifulSoup/bs4/doc/ - BeautifulSoup parser docs. [CITED: crummy.com/software/BeautifulSoup/bs4/doc]
- https://lxml.de/elementsoup.html - lxml/BeautifulSoup parser integration. [CITED: lxml.de/elementsoup.html]
- https://tenacity.readthedocs.io - Tenacity retry docs. [CITED: tenacity.readthedocs.io]
- Live `curl` to `https://finance.naver.com/robots.txt` and item news page on 2026-07-01 - robots and DOM check. [VERIFIED: live curl]

### Tertiary (LOW confidence)
- None used as authority; assumptions are listed in the Assumptions Log.

## Metadata

**Confidence breakdown:**
- Standard stack: MEDIUM - versions verified from PyPI and official docs, but legitimacy seam flagged all new packages as SUS due unknown download metadata.
- Architecture: HIGH - driven by locked context and current codebase boundaries.
- Pitfalls: MEDIUM - pykrx/KIS/Naver risks were live-checked, but exact KIS account limits require manual portal verification.

**Research date:** 2026-07-01
**Valid until:** 2026-07-08 for KIS/Naver details; 2026-07-31 for pykrx/indicator stack.
