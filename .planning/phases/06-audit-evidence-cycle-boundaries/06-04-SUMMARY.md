---
phase: 06-audit-evidence-cycle-boundaries
plan: 04
subsystem: market-cycle-safety
tags: [krx, pykrx, kis, audit, quote-freshness]
requires: [06-02, 06-03]
provides: [authoritative-krx-session, completed-bar-cutoff, pre-submit-quote-gate]
affects: [cli, data-source, kis-quote, kis-broker]
tech-stack:
  added: []
  patterns: [invocation-local-calendar-cache, fail-closed-time-policy, immediate-pre-submit-refetch]
key-files:
  modified:
    - trading_bot/data_source.py
    - trading_bot/cli.py
    - trading_bot/kis_quote.py
    - trading_bot/kis_broker.py
    - trading_bot/audit_models.py
    - tests/test_market_cycle.py
    - tests/test_kis_quote.py
    - tests/test_kis_broker.py
decisions:
  - "KRX execution requires positively observed trading-day data and the half-open [09:00, 15:20) KST continuous session."
  - "Daily context uses the immediately preceding confirmed KRX trading day, with unknown provider state failing closed."
  - "KIS orders re-fetch an aware timestamped quote immediately before POST and accept an inclusive maximum age of 10 seconds."
metrics:
  duration: 12m
  completed: 2026-07-11
status: complete
---

# Phase 6 Plan 4: KRX Cycle and Quote Freshness Summary

Authoritative KRX session/cutoff evidence and a timestamped immediate pre-submit quote gate now prevent unconfirmed, incomplete-bar, and stale-price orders.

## Accomplishments

- Added an invocation-local KRX-observed calendar that distinguishes confirmed closures from provider uncertainty and never falls back to weekday guesses.
- Enforced the KST continuous session as the half-open interval `09:00 <= time < 15:20` and resolved the prior confirmed trading day for OHLCV/indicator input.
- Added aware `observed_at` timestamps to successful KIS quotes and preserved `None` on unavailable quotes.
- Re-fetched quotes after session and duplicate gates, immediately before the single order POST; invalid, future, unavailable, or older-than-10-second observations block with normalized append-only evidence.
- Persisted timing policy/session/cutoff provenance on runs and initial quote/completed-bar evidence on ticker outcomes; pre-submit observations remain linked through order events.

## Task Commits

- `d678d77` — TDD RED: authoritative calendar tests.
- `0d49e27` — KRX session and prior completed-day cutoff wiring.
- `a9cd491` — TDD RED: quote observation and freshness boundary tests.
- `326f830` — Timestamped quotes and immediate pre-submit freshness gate.

## Verification

- Targeted market-cycle, CLI, data-source, quote, and broker tests: 74 passed.
- Full regression suite: 356 passed in 13.48s.
- Exact 10-second quote age is allowed; 10.001 seconds is blocked with zero POSTs.

## Decisions Made

- Empty observed KRX market data is a confirmed closure; transport/provider errors are unknown and non-executable.
- The previous trading day search stops and fails closed on the first unknown calendar state.
- Quote timestamps are assigned only after a positive price is successfully parsed.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing critical functionality] Persisted timing evidence through existing audit surfaces**

- **Found during:** Tasks 06-04-01 and 06-04-02
- **Issue:** Pure policies existed from Wave 1 but production orchestration did not retain the session, cutoff, or quote timestamps required to prove the gates.
- **Fix:** Added normalized run provenance, ticker data evidence, and order freshness events without storing raw provider responses.
- **Files modified:** `trading_bot/cli.py`, `trading_bot/data_source.py`, `trading_bot/kis_broker.py`, `trading_bot/audit_models.py`
- **Commit:** `326f830`

## Deferred Issues

- Pre-existing `[Phase ?]` decision duplicates in `STATE.md` were intentionally not cleaned because no registered GSD removal handler exists.
- The user's existing uncommitted `REQUIREMENTS.md` change was preserved and excluded from this plan's edits and commits.

## Self-Check: PASSED

- All modified production/test files exist.
- All four task commits exist in git history.
- Full suite passes with no known stubs or unplanned threat surface.
