---
phase: 12
slug: full-portfolio-backtesting-market-friction-modeling
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-10-01
---

# Phase 12 — Validation Strategy

Execution validated on 2026-10-01: 77 focused cases pass in 4.00s; full suite 905 cases pass in 24.44s. All task checks and shared fixture dependencies are satisfied.

## Test Infrastructure

Existing pytest and .venv/bin/python; configuration pyproject.toml. Quick command: `.venv/bin/python -m pytest -q tests/test_backtest_*.py`. Full: `.venv/bin/python -m pytest -q`. Focused runtime target below 60 seconds; actual timing must be measured during execution.

## Sampling Rate

Each task implements meaningful tests in the same commit and runs its focused command. Each wave runs accumulated backtest tests; final wave and pre-verification run full suite. No three-task gap and no watch mode. If focused latency exceeds 60 seconds, split checks without omitting coverage.

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---|---|---|---|---|---|---|---|---|---|
| 12-01-01 | 01 | 1 | FUT-01 | T-12-01–04 | Cutoff/reservation/input/offline invariants as assigned | unit/integration | `.venv/bin/python -m pytest -q tests/test_backtest_inputs.py` | ✅ exists | ✅ green |
| 12-01-02 | 01 | 1 | FUT-01 | T-12-01–04 | Cutoff/reservation/input/offline invariants as assigned | unit/integration | `.venv/bin/python -m pytest -q tests/test_backtest_inputs.py` | ✅ exists | ✅ green |
| 12-02-01 | 02 | 2 | FUT-01 | T-12-01–04 | Cutoff/reservation/input/offline invariants as assigned | unit/integration | `.venv/bin/python -m pytest -q tests/test_backtest_costs.py` | ✅ exists | ✅ green |
| 12-02-02 | 02 | 2 | FUT-01 | T-12-01–04 | Cutoff/reservation/input/offline invariants as assigned | unit/integration | `.venv/bin/python -m pytest -q tests/test_backtest_fills.py` | ✅ exists | ✅ green |
| 12-03-01 | 03 | 3 | FUT-01 | T-12-01–04 | Cutoff/reservation/input/offline invariants as assigned | unit/integration | `.venv/bin/python -m pytest -q tests/test_backtest_ledger.py` | ✅ exists | ✅ green |
| 12-03-02 | 03 | 3 | FUT-01 | T-12-01–04 | Cutoff/reservation/input/offline invariants as assigned | unit/integration | `.venv/bin/python -m pytest -q tests/test_backtest_ledger.py` | ✅ exists | ✅ green |
| 12-04-01 | 04 | 4 | FUT-01 | T-12-01–04 | Cutoff/reservation/input/offline invariants as assigned | unit/integration | `.venv/bin/python -m pytest -q tests/test_backtest_engine.py` | ✅ exists | ✅ green |
| 12-04-02 | 04 | 4 | FUT-01 | T-12-01–04 | Cutoff/reservation/input/offline invariants as assigned | unit/integration | `.venv/bin/python -m pytest -q tests/test_backtest_engine.py` | ✅ exists | ✅ green |
| 12-05-01 | 05 | 5 | FUT-01 | T-12-01–04 | Cutoff/reservation/input/offline invariants as assigned | unit/integration | `.venv/bin/python -m pytest -q tests/test_backtest_reporting.py` | ✅ exists | ✅ green |
| 12-05-02 | 05 | 5 | FUT-01 | T-12-01–04 | Cutoff/reservation/input/offline invariants as assigned | unit/integration | `.venv/bin/python -m pytest -q tests/test_backtest_reporting.py` | ✅ exists | ✅ green |
| 12-06-01 | 06 | 6 | FUT-01 | T-12-01–04 | Cutoff/reservation/input/offline invariants as assigned | unit/integration | `.venv/bin/python -m pytest -q tests/test_backtest_cli.py` | ✅ exists | ✅ green |
| 12-06-02 | 06 | 6 | FUT-01 | T-12-01–04 | Cutoff/reservation/input/offline invariants as assigned | unit/integration | `.venv/bin/python -m pytest -q tests/test_backtest_e2e.py` | ✅ exists | ✅ green |

## Wave 0 Requirements

- [x] 12-01 task 1 creates strict-model fixture and tests/test_backtest_inputs.py; task 2 extends its cutoff/coverage assertions.
- [x] Each later task creates its own mapped test file before running its verification; depends_on ensures fixture and preceding contracts exist. No future absent test command is declared already passing.
- [x] No framework installation required.

## Manual-Only Verifications

All implemented behaviors have automated verification. Actual historical data and market-rule source curation must be reviewed before a real-history complete-evidence claim; fixture tests cannot substitute for that external evidence. No production account experiment required.

## Validation Sign-Off

- [x] Every task has an automated verification and creation ownership for missing tests.
- [x] Sampling continuity and fixture dependencies are explicit.
- [x] No watch mode; offline, deterministic checks.
- [x] Actual feedback latency measured: 4.00s focused; 24.44s full suite.
- [x] Wave 0 and all implementation tests executed successfully.

Approval: implementation validation passed 2026-10-01; see 12-VERIFICATION.md.
