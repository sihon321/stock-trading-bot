---
phase: 07
slug: deterministic-replay-validation
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-12
---

# Phase 07 — Validation Strategy

> Per-phase validation contract for deterministic offline replay.

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.4.2 |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `.venv/bin/python -m pytest -q tests/test_replay.py tests/test_screener.py tests/test_execution.py` |
| **Full suite command** | `PYTHONUSERBASE="$PWD/.python-userbase" .venv/bin/python -m pytest -q` |
| **Baseline targeted runtime** | 96 existing screener/execution/parser/risk/CLI tests pass in 0.51 seconds |

## Sampling Rate

- **After every task commit:** Run the task-specific selector below and the touched production-contract tests.
- **After every plan wave:** Run replay plus screener/parser/risk/execution/CLI tests.
- **Before `$gsd-verify-work`:** Full suite green and representative bundle replayed twice with identical deterministic bytes and stable ID.
- **Max feedback latency:** 30 seconds.

## Requirement Verification Map

| Requirement | Secure behavior | Test type | Automated command | File status |
|-------------|-----------------|-----------|-------------------|-------------|
| REPLAY-01 | Fixture-only path invokes production screening and execution seams without `build_runtime`, network, providers, SQLite, or clock | integration/import-boundary | `.venv/bin/python -m pytest -q tests/test_replay.py tests/test_cli.py -k 'replay'` | ✅ 07-01-01, 07-03-02 |
| REPLAY-02 | Manifest has all locked inputs, fixture hashes, HEAD+tracked-diff hash, ordered outcomes, and input+outcome result ID | unit/integration | `.venv/bin/python -m pytest -q tests/test_replay.py -k 'manifest or identity or dirty'` | ✅ 07-02-01, 07-02-02 |
| REPLAY-03 | Funnel stages and action/block counts have explicit denominators; CLI/JSON disclaim profitability and omit performance metrics | unit/CLI | `.venv/bin/python -m pytest -q tests/test_replay.py tests/test_cli.py -k 'funnel or disclaimer or replay'` | ✅ 07-03-01, 07-03-02 |
| REPLAY-04 | Catalog covers exact threshold edges, HOLD, SELL, malformed, stale, stop/take overrides, daily-loss block, sizing and hard look-ahead failure | parameterized boundary | `.venv/bin/python -m pytest -q tests/test_replay.py -k 'boundary or catalog or lookahead'` | ✅ 07-01-01, 07-01-02 |

## Required Invariants

1. Reordering focused scenario files does not change an individual scenario outcome.
2. Full-day steps run in `(-score, ticker)` order and immediately observe prior complete fills.
3. `NONE` fill never changes cash, positions, daily loss, or order history.
4. A repeated replay from identical deterministic inputs produces identical ordered outcomes and result ID.
5. Changing any fixture, policy, relevant tracked diff, initial state, fixed evaluation time, or normalized outcome changes the corresponding evidence hash/result ID.
6. Invocation time, duration, and output path do not change result ID.
7. Any query after evaluation date raises the dedicated future-access error.
8. No normalized JSON key represents P&L, return, win rate, Sharpe, or profitability.

## Wave 0 Requirements

- [x] Create `tests/test_replay.py` with typed fixture builders and tests for all four requirements before or with the first production module.
- [x] Create `tests/fixtures/replay/` with schema-versioned focused and multi-ticker examples, raw JSON signals, fixed evaluation timestamps, explicit state/fills, and expected outcomes.
- [x] Extend `tests/test_cli.py` for `bot replay`, concise summary, mismatch detail, output JSON, disclaimer, and live-builder prohibition.
- [x] No dependency or pytest configuration change is required.

## Manual-Only Verifications

None. CLI presentation is text-based and every Phase 7 behavior is deterministically automatable.

## Multi-Source Coverage Audit

| Source | ID | Feature / constraint | Status |
|--------|----|----------------------|--------|
| REQ | REPLAY-01 | Offline production-path replay | COVERED |
| REQ | REPLAY-02 | Deterministic manifest and identity | COVERED |
| REQ | REPLAY-03 | Policy strictness comparison without profitability | COVERED |
| REQ | REPLAY-04 | Complete boundary/failure/no-look-ahead catalog | COVERED |
| CONTEXT | D-01..D-04 | Mixed fixtures, raw signals, warm-up and guard | COVERED |
| CONTEXT | D-05..D-08 | Independent/sequential state, complete/no fill, production ordering | COVERED |
| CONTEXT | D-09..D-12 | Manifest, stable identity, dirty code state, metadata split | COVERED |
| CONTEXT | D-13..D-16 | Summary/detail JSON, funnel, non-profitability contract | COVERED |
| RESEARCH | Architecture | Replay-only composition root over shipped pure seams | COVERED |
| RESEARCH | Security | Strict fixtures, no live builders, canonical hash, safe paths | COVERED |

Excluded without gaps: Phase 8 reports/runbook, Phase 9 broker soak/reconciliation, Phase 10 calibration/promotion, and future profitability backtesting.

## Validation Sign-Off

- [x] Every requirement has automated coverage planned.
- [x] Safety-critical determinism, look-ahead, live-boundary, and non-profitability invariants are explicit.
- [x] No watch mode or external service is required.
- [x] Targeted tests are expected well below the 30-second feedback limit.
- [x] `nyquist_compliant: true` set in frontmatter.

**Approval:** implemented and verified by the Phase 7 targeted and full-suite commands.
