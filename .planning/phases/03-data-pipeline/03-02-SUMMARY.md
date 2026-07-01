---
phase: 03-data-pipeline
plan: 02
subsystem: data-pipeline
tags: [data-models, pykrx, indicators, source-health, fail-safe, phase3-wave1]
requires:
  - "Settings.ohlcv_adjusted (from 03-01)"
  - "trading_bot.domain compact DataContext / Money / Ticker"
provides:
  - "Source-health model layer: SourceStatus/DataAction/TickerRole, SourceHealth, OhlcvResult, DataSourceAuditEvent, IndicatorConfig"
  - "resolve_data_action hybrid policy (SKIP_CANDIDATE vs FORCE_HOLD) and emit_data_warning audit"
  - "PykrxOhlcvAdapter: isolated pykrx daily + whole-market OHLCV with typed normalization"
  - "calculate_technicals pure transform producing compact volatility-breakout technicals"
affects:
  - trading_bot/data_models.py
  - trading_bot/pykrx_adapter.py
  - trading_bot/indicators.py
  - tests/test_pykrx_adapter.py
  - tests/test_indicators.py
tech-stack:
  added: []
  patterns: [frozen-dataclass-string-enum, adapter-boundary-normalization, pure-transform-fail-closed, injected-vendor-module]
key-files:
  created:
    - trading_bot/data_models.py
    - trading_bot/pykrx_adapter.py
    - trading_bot/indicators.py
    - tests/test_pykrx_adapter.py
    - tests/test_indicators.py
  modified: []
decisions:
  - "OHLCV validation asserts schema, monotonic date index, min rows, finite positive prices, nonnegative volume, and freshness before AVAILABLE"
  - "Natural-closure fallback is honored via accepted_latest_date so a legit holiday/weekend closure is AVAILABLE, not STALE"
  - "Indicators fail closed to UNAVAILABLE with empty technicals on NaN warm-up rather than emitting zero-valued signals"
  - "pykrx stock module is injectable so all tests run fully offline"
  - "historical_volatility computed as rolling std of log returns; volume_ratio as latest volume / trailing mean"
metrics:
  duration: ~10m
  completed: 2026-07-01
status: complete
---

# Phase 3 Plan 02: Source-Health Model, pykrx Adapter, and Indicators Summary

Built the Wave 1 daily-data foundation: a shared typed source-health model layer, a pykrx OHLCV adapter that isolates the vendor and normalizes empty/stale/bad/exception frames into typed outcomes, and a pure `ta`-backed indicator transform that fails closed on warm-up NaNs — so bad market data can never become tradeable context (DATA-01, DATA-02).

## What Was Built

- **Task 1 — Source-health models + pykrx adapter (TDD):**
  - `trading_bot/data_models.py`: string enums `SourceStatus` (AVAILABLE/STALE/UNAVAILABLE), `DataAction` (BUILD_CONTEXT/SKIP_CANDIDATE/FORCE_HOLD), `TickerRole` (CANDIDATE/HOLDING); frozen dataclasses `SourceHealth`, `OhlcvResult`, `DataSourceAuditEvent`, `IndicatorConfig`; `resolve_data_action` implementing the D-01 hybrid policy (bad data skips a candidate, freezes a holding) and `emit_data_warning` implementing the D-03 console warning + structured non-secret audit event.
  - `trading_bot/pykrx_adapter.py`: `PykrxOhlcvAdapter` is the only module importing `pykrx`. `fetch_daily_ohlcv` and `fetch_market_ohlcv` pass explicit trading dates, use the injected `adjusted` policy (from `Settings.ohlcv_adjusted`), validate required Korean OHLCV columns, monotonic date index, minimum rows, finite positive prices, nonnegative volume, and freshness (with natural-closure fallback), and convert pykrx exceptions / empty / stale / schema-invalid / bad-numeric inputs into typed `OhlcvResult` values without raising vendor exceptions (D-15, threats T-03-02-T/D).
- **Task 2 — Volatility-breakout indicators (TDD):**
  - `trading_bot/indicators.py`: `calculate_technicals(ohlcv, IndicatorConfig)` is a pure transform (no settings/logging/network/adapter imports). Uses `ta` for `sma_short`, `sma_long`, `rsi_14`, `atr_14`, plus rolling-log-return `historical_volatility` and a `volume_ratio`. Returns a flat `Mapping[str, float]` suitable for `DataContext.technicals`, or an `IndicatorResult` with UNAVAILABLE `SourceHealth` and empty technicals on missing columns, insufficient history, or any NaN warm-up tail (D-05, threat T-03-02-T).

## Verification

`PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest tests/test_pykrx_adapter.py tests/test_indicators.py -q` -> **29 passed**.

Full suite `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` -> **142 passed** (was 113 before this plan; +29 new, no regressions).

Acceptance criteria confirmed:
- Tests use fake pykrx modules/frames only; no live provider calls.
- Coverage includes empty frame, stale date, missing columns, non-positive price, negative volume, insufficient rows, non-monotonic index, vendor exception, natural-closure fallback, adjusted-flag propagation, and SKIP_CANDIDATE/FORCE_HOLD actions (Task 1); valid keys, insufficient history, NaN/warm-up, missing columns, and volume ratio (Task 2).
- `trading_bot/ports.py` remains free of pykrx/adapter imports (unchanged; full suite including `tests/test_ports.py` green).
- `indicators.py` imports no pykrx/httpx/KIS/Naver code (guarded by an import-boundary test).

## TDD Gate Compliance

- Task 1 — RED: `test(03-02)` `a7d6bab`; GREEN: `feat(03-02)` `b29869f`.
- Task 2 — RED: `test(03-02)` `98aaa00`; GREEN: `feat(03-02)` `c8f7ff4`.
- REFACTOR: none needed beyond the deprecation fix noted below.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] pandas 2.3.3 generic-unit Timedelta DeprecationWarning**
- **Found during:** Task 1 GREEN.
- **Issue:** `pd.Timedelta(days=lookback_days)` emitted a `DeprecationWarning` ("generic unit ... will raise an error in the future") under pandas 2.3.3, which would break on a future pandas upgrade.
- **Fix:** Changed to `pd.Timedelta(int(lookback_days), unit="D")` (explicit unit), verified clean under `-W error::DeprecationWarning`.
- **Files modified:** `trading_bot/pykrx_adapter.py`.
- **Commit:** `b29869f`.

## Known Stubs

None. Both modules are fully wired; no placeholder/empty-value data paths.

## Threat Flags

None. The files implement the mitigations for T-03-02-T (schema/date/price/health validation before downstream use) and T-03-02-D (vendor-failure normalization) already in the plan's threat register; audit output (`DataSourceAuditEvent` / `emit_data_warning`) carries only non-secret fields (T-03-02-I). No new trust-boundary surface introduced.

## Self-Check: PASSED

- Files found: trading_bot/data_models.py, trading_bot/pykrx_adapter.py, trading_bot/indicators.py, tests/test_pykrx_adapter.py, tests/test_indicators.py
- Commits found: a7d6bab, b29869f, 98aaa00, c8f7ff4
