---
phase: 03-data-pipeline
plan: 05
subsystem: data-pipeline
tags: [naver-news, scraping, sanitizer, compliance-gate, fail-safe, untrusted-input, phase3-wave2]
requires:
  - "Settings.naver_news_enabled / naver_news_max_items / naver_news_max_chars (from 03-01)"
  - "Plan 03-01 Naver acceptable-use decision (recorded DISABLED in 03-MANUAL-DECISIONS.md)"
  - "trading_bot.data_models source-health types SourceHealth/SourceStatus (from 03-02)"
provides:
  - "NewsArticle / NaverNewsResult internal-structured news models"
  - "NaverNewsAdapter: compliance-gated, fail-soft, sanitized Naver Finance news adapter"
  - "sanitize_news_text: markup/script/control/prompt-injection stripper with length cap"
  - "render_news_for_context: item-count cap producing DataContext.news sanitized strings"
  - "parse_naver_news_html: isolated BeautifulSoup/lxml DOM parser (one-file layout fix)"
affects:
  - trading_bot/naver_news.py
  - tests/test_naver_news.py
tech-stack:
  added: []
  patterns: [untrusted-input-sanitizer, adapter-boundary-normalization, compliance-gate, bounded-retry-fail-soft, injected-http-client]
key-files:
  created:
    - trading_bot/naver_news.py
    - tests/test_naver_news.py
  modified: []
decisions:
  - "Naver news is DISABLED by default per Plan 03-01 decision; disabled/unapproved returns empty news and never touches the network"
  - "All DOM knowledge (BeautifulSoup/lxml, type5 table, td.title) isolated in parse_naver_news_html so a layout change is a one-file fix"
  - "Sanitizer strips <script>/<style> bodies, all tags, control chars, prompt-injection phrases, and collapses whitespace before capping length"
  - "Only capped sanitized strings reach DataContext.news; structured NewsArticle detail stays internal (D-04/D-06)"
  - "HTTP >=400, network, encoding/decode, missing table, and parse failures all normalize to UNAVAILABLE empty news via tenacity bounded retry, never raising (D-15)"
metrics:
  duration: ~8m
  completed: 2026-07-01
status: complete
---

# Phase 3 Plan 05: Naver Finance News Adapter Summary

Implemented the Naver Finance news adapter as a compliance-gated, fail-soft, sanitized data source (DATA-04). It fetches per-ticker news only when the operator approved acceptable use in Plan 03-01 (disabled by default because Naver `robots.txt` disallows general crawlers), treats all scraped HTML as untrusted input for the later LLM phase, and degrades every failure mode to empty sanitized news so a scraping problem can never crash a cycle or pollute the compact LLM context.

## What Was Built

- **Task 1 — Compliance-gated fail-soft Naver news adapter (TDD):**
  - `trading_bot/naver_news.py`:
    - `NewsArticle` / `NaverNewsResult` frozen dataclasses. Structured article detail stays internal; `NaverNewsResult.rendered` is always a tuple of capped, sanitized strings for `DataContext.news` (D-04/D-06).
    - `NaverNewsAdapter.fetch_news(ticker)` is gated on `enabled` (from `Settings.naver_news_enabled`, i.e. the Plan 03-01 decision). When disabled/unapproved it returns empty news with an UNAVAILABLE `SourceHealth` reason and never touches the network. It validates the 6-digit KRX ticker, fetches via an injectable httpx-like client with a realistic User-Agent and timeout, wraps transient failures in a `tenacity` bounded retry, and converts HTTP >=400, network exceptions, EUC-KR decode failures, a missing DOM, and parse failures into empty-news graceful degradation — never raising (D-15, threats T-03-05-D/R).
    - `parse_naver_news_html(html)` isolates all BeautifulSoup/lxml DOM knowledge (the `table.type5` container and `td.title` anchors), skips malformed rows, and raises an internal transient error when the expected container is absent so the adapter can normalize it. lxml failure falls back to the stdlib parser.
    - `sanitize_news_text(value, max_chars)` treats news as untrusted text: drops `<script>`/`<style>` bodies, strips all tags, removes prompt-injection / instruction-like phrases (e.g. "ignore all previous instructions", "system prompt", role tags), removes control characters, collapses whitespace, and caps length (threat T-03-05-T). Non-string/empty input yields `""`.
    - `render_news_for_context(articles, max_items, max_chars)` caps item count and sanitizes each string, dropping blanks — the single path from internal articles to `DataContext.news`.
  - No prompt construction, LLM call, notification, or scheduler code was added.

## Verification

`PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest tests/test_naver_news.py -q` -> **24 passed**.

Full suite `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` -> **225 passed** (was 201 before this plan; +24 new, no regressions).

Acceptance criteria confirmed:
- Tests use local HTML strings and fake HTTP clients only; no live network.
- Coverage includes disabled/unapproved mode (and that it never fetches), valid parse, broken/missing DOM, HTTP 403/429/500/503, network error, encoding-decode error, sanitizer markup/script/control/prompt-injection/length behavior, item-count caps, and empty-news continuation.
- `DataContext.news` receives only sanitized strings (asserted markup-free, prompt-injection-free); article objects and raw HTML stay internal.
- `trading_bot/ports.py` remains free of naver/httpx/adapter imports (full suite including `tests/test_ports.py` green).

## TDD Gate Compliance

- RED: `test(03-05)` `55c70cc` — 24 failing tests (module absent).
- GREEN: `feat(03-05)` `a2d6eea` — implementation, 24 passing, full suite green.
- REFACTOR: none needed.

## Deviations from Plan

None - plan executed exactly as written.

## Known Stubs

None. The adapter is fully wired. The disabled-by-default empty-news path is an intentional compliance behavior recorded in `03-MANUAL-DECISIONS.md`, not a stub: when the operator opts in via `Settings.naver_news_enabled=True`, the same code fetches and parses live news.

## Threat Flags

None. The file implements the mitigations for T-03-05-T (sanitize markup/control/prompt-injection and cap rendered strings), T-03-05-D (timeout, bounded retry, disabled-by-policy, empty-news degradation), and T-03-05-R (source-health reason on every disabled/unapproved/failure path) already in the plan's threat register. No new trust-boundary surface introduced beyond the Naver HTML -> parser boundary the plan anticipated.

## Self-Check: PASSED

- Files found: trading_bot/naver_news.py, tests/test_naver_news.py
- Commits found: 55c70cc, a2d6eea
