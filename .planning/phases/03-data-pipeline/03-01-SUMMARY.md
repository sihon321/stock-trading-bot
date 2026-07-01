---
phase: 03-data-pipeline
plan: 01
subsystem: config
tags: [config, dependencies, settings, phase3-gate]
requires: []
provides:
  - "Settings Phase 3 source-policy fields (ohlcv_adjusted, screener_*, kis_*, naver_news_*)"
  - "Pinned Phase 3 runtime deps (pykrx, ta, httpx, beautifulsoup4, lxml, tenacity)"
  - "Recorded operator decisions in 03-MANUAL-DECISIONS.md"
affects:
  - pyproject.toml
  - trading_bot/config.py
  - tests/test_config.py
tech-stack:
  added: [pykrx==1.2.8, ta==0.11.0, httpx==0.28.1, beautifulsoup4==4.15.0, lxml==6.1.1, tenacity==9.1.4]
  patterns: [pydantic-settings BaseSettings, model_validator fail-closed, tuple env parsing]
key-files:
  created:
    - .planning/phases/03-data-pipeline/03-MANUAL-DECISIONS.md
  modified:
    - pyproject.toml
    - trading_bot/config.py
    - tests/test_config.py
decisions:
  - "pykrx OHLCV uses adjusted prices (수정주가); ohlcv_adjusted defaults True"
  - "Naver Finance scraping disabled by default (robots.txt); naver_news_enabled defaults False"
  - "KIS mock rate policy: 0.5s min interval, 3 retries, 1.0s backoff, 600s token refresh margin"
  - "requires-python raised to >=3.10 for pykrx compatibility"
metrics:
  duration: ~6m
  completed: 2026-07-01
status: complete
---

# Phase 3 Plan 01: Phase 3 Runtime & Source-Policy Gate Summary

Established the Phase 3 dependency, runtime, and operator-decision gate: recorded approved package/provider decisions, raised the Python floor, pinned six data-pipeline deps, and added source-policy `Settings` fields (pykrx adjusted, screener, KIS rate/token, Naver) with fail-closed validation — all covered by config tests.

## What Was Built

- **Task 1 — Manual decisions gate (checkpoint:human-verify, resolved by orchestrator):** `03-MANUAL-DECISIONS.md` records all six SUS package approvals (none rejected), the KIS token TTL / rate-limit policy (DATA-03), the Naver scraping disabled-by-default decision (DATA-04), and the pykrx adjusted-price policy (DATA-01/02/05).
- **Task 2 — Settings + dependency pins (TDD):**
  - `pyproject.toml`: `requires-python` raised `>=3.9` → `>=3.10`; added pins `pykrx==1.2.8`, `ta==0.11.0`, `httpx==0.28.1`, `beautifulsoup4==4.15.0`, `lxml==6.1.1`, `tenacity==9.1.4`.
  - `trading_bot/config.py`: added 13 Phase 3 fields — `ohlcv_adjusted`, `screener_max_candidates`, `screener_markets`, `screener_min_trading_value`, `screener_min_volume_ratio`, `screener_excluded_states`, `kis_token_refresh_margin_seconds`, `kis_min_interval_seconds`, `kis_max_retries`, `kis_retry_backoff_seconds`, `naver_news_enabled`, `naver_news_max_items`, `naver_news_max_chars`. Defaults match the recorded manual decisions. Added `_require_positive_source_policy()` to the `validate_safety_gates` model validator so non-positive controls fail closed. `active_kis` atomic selection and `startup_banner` secret redaction are unchanged.
  - `tests/test_config.py`: extended `ENV_KEYS`; added deterministic-defaults, env-override, non-positive-fail-closed (parametrized), and no-secret-leak tests.

## Verification

`PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest tests/test_config.py -q` → **23 passed**.

Confirmed no ORM/schema/migration files created. Approved deps installed into the gitignored `.python-userbase` (not committed); transitive `pandas 2.3.3` and `numpy 2.5.0` pulled by pykrx/ta. pydantic import verified intact after install.

## TDD Gate Compliance

- RED: `test(03-01)` commit `eca89bc` — 11 new tests failing before implementation.
- GREEN: `feat(03-01)` commit `44683b4` — all 23 tests passing.
- REFACTOR: none needed.

## Deviations from Plan

None — plan executed exactly as written. Task 1's checkpoint was pre-resolved by the orchestrator with operator decisions recorded verbatim.

## Self-Check: PASSED

- Commits found: e00c6ca, eca89bc, 44683b4
- Files found: 03-MANUAL-DECISIONS.md, pyproject.toml, trading_bot/config.py, tests/test_config.py
