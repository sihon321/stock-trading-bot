---
phase: 03-data-pipeline
verified: 2026-07-01T00:00:00Z
status: passed
score: 5/5 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Phase 3: Data Pipeline Verification Report

**Phase Goal:** Data Pipeline — pykrx OHLCV + indicators + daily screener, fail-soft Naver news, and KIS real-time price behind a shared token manager. The compact typed `DataContext` must be produced behind the existing synchronous `DataSource` port, with source-health and fail-safe behavior explicit enough that bad/stale/unavailable data cannot create a trade.
**Verified:** 2026-07-01
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

The five ROADMAP Success Criteria (which subsume the plan `must_haves` truths) are the contract.

| #   | Truth (ROADMAP SC) | Status | Evidence |
| --- | ------------------ | ------ | -------- |
| 1 | Fetches daily OHLCV per ticker via pykrx and fails safe to HOLD on holiday/empty/stale data, trading date asserted in Asia/Seoul | ✓ VERIFIED | `trading_bot/pykrx_adapter.py` isolates pykrx, validates required columns, monotonic date index, min rows, finite positive prices, freshness vs `expected_date`/`accepted_latest_date`; normalizes empty/stale/exception into `OhlcvResult(frame=None, health=UNAVAILABLE/STALE)`. `data_source.py` `_guard` + `resolve_data_action` turn STALE/UNAVAILABLE into FORCE_HOLD (holding) / SKIP_CANDIDATE (candidate). Behavioral tests pass: `test_stale_ohlcv_holding_forces_hold`, `test_unavailable_ohlcv_candidate_is_skipped`, `test_build_context_raises_on_no_context_for_holding` (via `NoContextError`, no zero-price context). |
| 2 | Computes technical indicators (MAs, RSI, …) from the daily OHLCV | ✓ VERIFIED | `trading_bot/indicators.py` `calculate_technicals` returns `sma_short`, `sma_long`, `rsi_14`, `atr_14`, `historical_volatility`, `volume_ratio` via `ta`; fails closed to UNAVAILABLE on NaN warm-up/missing columns/insufficient history. Pure transform, no vendor/network/settings reads. `tests/test_indicators.py` green (part of 240). |
| 3 | Runs a daily market screen selecting the candidate universe using point-in-time data | ✓ VERIFIED | `trading_bot/screener.py` `screen_candidates` takes an explicit asserted `trading_date`, hard-excludes unhealthy/low-liquidity/suspended/out-of-market/bad-technical tickers before ranking, ranks volatility-breakout, caps to `screener_max_candidates`, emits SKIP_CANDIDATE audits. Composed by `MarketDataSource.screen_daily_candidates`. `test_screen_daily_candidates_composes_screener` green. |
| 4 | Fetches real-time price via KIS using one shared, cached, auto-refreshed access token, under rate limits | ✓ VERIFIED | `trading_bot/kis_auth.py` `KisTokenManager` caches token, refreshes only inside `refresh_margin` of runtime-discovered expiry, bounded retry/backoff, secret redaction, `min_interval` throttle. `trading_bot/kis_quote.py` `KisQuoteAdapter` consumes the shared manager (never re-issues), validates price>0/finite, normalizes throttle/HTTP/JSON/rt_cd/parse to UNAVAILABLE (no `Money(0)`). `tests/test_kis_auth.py`, `tests/test_kis_quote.py` green. |
| 5 | Scrapes per-ticker Naver news with sanitization + graceful degradation; empty/failed scrape = "no news", never crashes | ✓ VERIFIED | `trading_bot/naver_news.py` gated by `Settings.naver_news_enabled` (default False); `sanitize_news_text` strips tags/scripts/controls + prompt-injection phrases and caps length; `fetch_news` normalizes disabled/403/429/network/decode/DOM/parse to empty rendered news + health, never raises. `data_source.py` treats news as optional fail-soft (`test_news_failure_continues_with_empty_news`). `tests/test_naver_news.py` green. |

**Score:** 5/5 truths verified (0 present, behavior-unverified)

Behavior-dependent truths (freshness→FORCE_HOLD state transition, exhausted-retry→UNAVAILABLE, empty-news degradation, fail-closed no-context) each have a passing named behavioral test in `tests/test_data_source.py` — VERIFIED on behavior, not presence alone.

### Required Artifacts

| Artifact | Expected | Status | Details |
| -------- | -------- | ------ | ------- |
| `trading_bot/ports.py` | Adapter-free synchronous DataSource port | ✓ VERIFIED | No vendor/config imports; `DataSource.build_context` synchronous & runtime-checkable. |
| `trading_bot/domain.py` | Compact `DataContext` | ✓ VERIFIED | `DataContext(ticker, current_price, technicals: Mapping[str,float], news: Sequence[str])` — no source metadata. |
| `trading_bot/data_models.py` | Source-health/audit models + policy fns | ✓ VERIFIED | `SourceStatus`, `DataAction`, `TickerRole`, `SourceHealth`, `OhlcvResult`, `DataSourceAuditEvent`, `IndicatorConfig`, `resolve_data_action`, `emit_data_warning`. No vendor imports. |
| `trading_bot/pykrx_adapter.py` | pykrx OHLCV adapter | ✓ VERIFIED | Only pykrx importer; substantive validation + normalization. |
| `trading_bot/indicators.py` | Pure indicator transform | ✓ VERIFIED | Only `ta` importer; fail-closed. |
| `trading_bot/screener.py` | Volatility-breakout screener | ✓ VERIFIED | Pure; config-driven; audit evidence. |
| `trading_bot/kis_auth.py` | Shared token manager | ✓ VERIFIED | Cached/margin-refresh/bounded-retry/redacted; `active_kis` sole source. |
| `trading_bot/kis_quote.py` | Current-price adapter | ✓ VERIFIED | Consumes shared manager; fail-safe price validation. |
| `trading_bot/naver_news.py` | Compliance-gated news adapter | ✓ VERIFIED | Only bs4/lxml importer; gated + sanitized + fail-soft. |
| `trading_bot/data_source.py` | Thin `MarketDataSource` orchestrator | ✓ VERIFIED | Composes adapters/transforms; reimplements none; emits compact `DataContext` or typed no-context. |
| `trading_bot/config.py` | Phase 3 policy settings | ✓ VERIFIED | All operator defaults present + `active_kis`. |
| `tests/test_ports.py` | Import-boundary contract | ✓ VERIFIED | In-process + fresh-subprocess isolation checks green. |

### Key Link Verification

| From | To | Via | Status | Details |
| ---- | -- | --- | ------ | ------- |
| `ports.py` | (none) | No adapter/vendor import | ✓ WIRED | `test_ports_stay_adapter_free_in_fresh_interpreter` passes; grep confirms no pykrx/httpx/bs4/lxml/ta/config in ports/domain/data_models. |
| `data_source.py` | pykrx_adapter, indicators, screener, kis_quote, naver_news | Constructor injection + `build_data_source` factory | ✓ WIRED | Imports and composes all five; no reimplementation. |
| `kis_quote.py` | `kis_auth.KisTokenManager` | `token_manager.get_token()` | ✓ WIRED | Single shared token flow; adapter never issues tokens. |
| `kis_auth.build_kis_auth_config` | `Settings.active_kis` | Sole credential read (D-14) | ✓ WIRED | No `kis_mock`/`kis_real` direct reads in adapters. |
| `MarketDataSource.build_context` | `DataSource` Protocol | Structural conformance | ✓ WIRED | `test_market_data_source_structurally_satisfies_data_source` passes; `build_context` synchronous. |

Import isolation (grep verified): pykrx → pykrx_adapter only; httpx → kis_auth/kis_quote/naver_news only; bs4/lxml → naver_news only; ta → indicators only.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
| -------- | ------- | ------ | ------ |
| Port import boundary holds in a clean interpreter | `pytest tests/test_ports.py::test_ports_stay_adapter_free_in_fresh_interpreter` | 1 passed | ✓ PASS |
| Stale OHLCV for holding → FORCE_HOLD | `pytest tests/test_data_source.py` (`test_stale_ohlcv_holding_forces_hold`) | 13 passed | ✓ PASS |
| Bad data for candidate → SKIP_CANDIDATE; no-context fail-closed | same suite (`test_unavailable_*`, `test_build_context_raises_on_no_context_for_holding`) | 13 passed | ✓ PASS |
| News failure → empty news, cycle continues | same suite (`test_news_failure_continues_with_empty_news`) | 13 passed | ✓ PASS |
| Full workspace suite (run once) | `PYTHONUSERBASE=... pytest -q` | 240 passed in ~13s | ✓ PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
| ----------- | ----------- | ----------- | ------ | -------- |
| DATA-01 | 03-01/02/06 | Daily OHLCV via pykrx, fail-safe HOLD on holiday/empty/stale | ✓ SATISFIED | pykrx_adapter normalization + data_source FORCE_HOLD/SKIP tests |
| DATA-02 | 03-01/02/06 | Technical indicators from OHLCV | ✓ SATISFIED | indicators.calculate_technicals + tests |
| DATA-03 | 03-01/04/06 | Real-time KIS price via shared auto-refreshed token | ✓ SATISFIED | kis_auth.KisTokenManager + kis_quote + tests |
| DATA-04 | 03-01/05/06 | Naver news scrape, sanitization, graceful degradation | ✓ SATISFIED | naver_news adapter (disabled default, fail-soft, sanitizer) + tests |
| DATA-05 | 03-01/03/06 | Daily market screen selecting candidate universe (point-in-time) | ✓ SATISFIED | screener.screen_candidates + screen_daily_candidates + tests |

No orphaned requirements: all 5 IDs mapped to Phase 3 in REQUIREMENTS.md appear in plan frontmatter and are implemented.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
| ---- | ---- | ------- | -------- | ------ |
| — | — | No TBD/FIXME/XXX/TODO/HACK/PLACEHOLDER in `trading_bot/` | ℹ️ Info | Clean; completion auditable |

### Operator Policy (03-MANUAL-DECISIONS.md) Honored in Code

| Decision | Expected | In `config.py` | Status |
| -------- | -------- | -------------- | ------ |
| pykrx adjusted | `ohlcv_adjusted=True` | line 75 | ✓ |
| Naver default | `naver_news_enabled=False` | line 91 | ✓ |
| KIS refresh margin | 600s | line 85 | ✓ |
| KIS min interval | 0.5s | line 86 | ✓ |
| KIS max retries | 3 | line 87 | ✓ |
| KIS backoff | 1.0s | line 88 | ✓ |
| Single KIS source (D-14) | `Settings.active_kis` | property line 127; sole read in `build_kis_auth_config` | ✓ |

### Human Verification Required

None. All truths are behaviorally proven by offline tests; no visual/real-service behavior is in scope for this phase (live pykrx/KIS/Naver calls are deliberately mocked and gated off).

### Gaps Summary

No gaps. The phase goal is achieved: real Korean-market data (pykrx OHLCV + `ta` indicators + volatility-breakout screener + shared-token KIS price + compliance-gated fail-soft Naver news) is composed behind a thin `MarketDataSource` that structurally satisfies the unchanged synchronous `DataSource` port. The core boundary (`ports.py`/`domain.py`/`data_models.py`) is free of pykrx/KIS/Naver/httpx/ta imports, proven by an in-process and a fresh-subprocess boundary test. Bad/stale/exhausted-retry/disabled inputs normalize to typed UNAVAILABLE/STALE/empty and resolve to FORCE_HOLD or SKIP_CANDIDATE (or a fail-closed `NoContextError`), so no path fabricates a tradeable zero/default-price context. Operator source policy from 03-MANUAL-DECISIONS.md is faithfully encoded in `Settings`. Full suite: 240 passed.

---

_Verified: 2026-07-01_
_Verifier: Claude (gsd-verifier)_
