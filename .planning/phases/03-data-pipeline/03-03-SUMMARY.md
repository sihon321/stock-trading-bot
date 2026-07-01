---
phase: 03-data-pipeline
plan: 03
subsystem: data-pipeline
tags: [screener, volatility-breakout, fail-safe, pure-transform, phase3-wave2]
requires:
  - "OhlcvResult / SourceHealth / SourceStatus / DataSourceAuditEvent from 03-02"
  - "Settings screener_* fields from 03-01 (max_candidates, markets, min_trading_value, min_volume_ratio, excluded_states)"
provides:
  - "ScreenerConfig / ScreenerCandidate / ScreenerResult frozen dataclasses"
  - "build_screener_config(settings) — policy driven from Settings, not hard-coded"
  - "screen_candidates(trading_date, rows, config) — pure filter-then-rank transform with SKIP_CANDIDATE audits"
  - "score_volatility_breakout(technicals, trading_value, config) — volatility+liquidity-first ranking score"
affects:
  - trading_bot/screener.py
  - tests/test_screener.py
tech-stack:
  added: []
  patterns: [frozen-dataclass-string-enum, pure-transform-fail-closed, filter-before-rank, settings-driven-policy]
key-files:
  created:
    - trading_bot/screener.py
    - tests/test_screener.py
  modified: []
decisions:
  - "Hard exclusions (market, source health, excluded state, liquidity floor, missing/non-finite technicals, volume-ratio floor) run before any scoring so unsafe data never reaches ranking (D-11)"
  - "Ranking score puts historical-volatility + ATR (normalized by SMA-long) scaled by a log-liquidity factor as the dominant term; volume expansion and MA-spread momentum are smaller secondary terms (D-07/D-10)"
  - "Score ties are broken by ticker for deterministic ordering; result is capped at max_candidates after sorting"
  - "Screener is a pure transform over already-fetched inputs — no pykrx/HTTP/KIS/Naver imports; guarded by an import-boundary test (D-13)"
  - "Every excluded ticker yields a DataSourceAuditEvent with action=SKIP_CANDIDATE, expected_date=trading_date, and only non-secret fields (D-03)"
metrics:
  duration: ~3m
  completed: 2026-07-01
status: complete
---

# Phase 3 Plan 03: Volatility-Breakout Screener Summary

Implemented the Wave 2 daily screener: a pure filter-then-rank transform that hard-excludes unhealthy, illiquid, suspended/halted/excluded-state, out-of-market, and bad-technical tickers before ranking survivors for volatility-breakout readiness, capping the output and emitting `SKIP_CANDIDATE` audit evidence for every exclusion — so bad market data can never enter the candidate universe that feeds a BUY (DATA-05).

## What Was Built

- **Task 1 — Volatility-breakout screener filtering and ranking (TDD):**
  - `trading_bot/screener.py`:
    - Frozen dataclasses `ScreenerConfig`, `ScreenerCandidate`, `ScreenerResult`.
    - `build_screener_config(settings)` populates policy entirely from Phase 3 `Settings` fields (`screener_max_candidates`, `screener_markets`, `screener_min_trading_value`, `screener_min_volume_ratio`, `screener_excluded_states`) — no hard-coded policy (D-08/D-09/D-11).
    - `screen_candidates(trading_date, rows, config)` is a pure function over an explicit asserted trading date plus per-ticker input rows (`ticker`, `market`, `state`, `trading_value`, `technicals`, `health`). It applies hard exclusions via `_exclusion_reason` (out-of-market, source not `AVAILABLE`, excluded ticker state, trading value below the liquidity floor, missing/empty/non-finite required technicals, and volume ratio below the expansion floor) BEFORE scoring, then ranks survivors, breaks ties by ticker, and caps at `max_candidates`.
    - `score_volatility_breakout(technicals, trading_value, config)` makes historical volatility + normalized ATR the dominant term, scaled by a log-scaled liquidity factor above the configured floor (liquidity as a primary input), with volume expansion and short-vs-long MA momentum as smaller secondary ordering terms (D-07/D-10).
    - Every exclusion produces a `DataSourceAuditEvent` with `action="SKIP_CANDIDATE"`, `expected_date=trading_date`, and only non-secret fields (D-03), reusing the source health/audit types from Plan 03-02.

## Verification

`PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest tests/test_screener.py -q` -> **16 passed**.

Phase-3 unit slice `tests/test_indicators.py tests/test_screener.py tests/test_pykrx_adapter.py -q` -> **45 passed**.

Full suite `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` -> **158 passed** (was 142 before this plan; +16 new, no regressions).

Acceptance criteria confirmed:
- Tests cover configurable market list, configurable max candidates, liquidity floor, low volume ratio, suspended/halted/admin/delisting exclusion (parametrized), stale/unhealthy-source exclusion, missing/NaN-technical exclusion, ranking order (volatility+liquidity over momentum), score monotonicity in volatility, trading-date propagation to result + audits, and `SKIP_CANDIDATE` audit action values.
- The screener accepts explicit trading dates and exposes them in `ScreenerResult.trading_date` and every audit `expected_date`.
- No pykrx network calls occur in `tests/test_screener.py` — the screener is a pure transform over plain-mapping inputs, and an import-boundary test asserts `trading_bot.screener` loads no pykrx/httpx/requests/anthropic/openai or local adapter/kis/naver modules.

## TDD Gate Compliance

- Task 1 — RED: `test(03-03)` `c0574fe` (16 tests, `ModuleNotFoundError` on missing `trading_bot.screener`); GREEN: `feat(03-03)` `33d22ca` (16 passed).
- REFACTOR: none needed — implementation was clean on first green.

## Deviations from Plan

None — plan executed exactly as written. Rules 1-3 were not triggered; no architectural (Rule 4) decisions arose.

## Known Stubs

None. The screener is fully wired: filtering, scoring, capping, and audit emission all operate on real inputs. It intentionally does not fetch data itself (D-13) — the Wave-3 orchestrator (Plan 03-06) supplies rows from the pykrx adapter and indicator transform.

## Threat Flags

None. The file implements the plan's threat-register mitigations: T-03-03-T (hard-exclude unhealthy/low-liquidity/suspended data before ranking + `SKIP_CANDIDATE` audits), T-03-03-R (audit events carry ticker, source, reason, observed/expected dates, and action), and T-03-03-D (configurable markets + `max_candidates` cap bound the actionable set). No new trust-boundary surface introduced; audit output carries only non-secret fields.

## Self-Check: PASSED

- Files found: trading_bot/screener.py, tests/test_screener.py
- Commits found: c0574fe (test/RED), 33d22ca (feat/GREEN)
