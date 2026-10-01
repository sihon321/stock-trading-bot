---
phase: 12
slug: full-portfolio-backtesting-market-friction-modeling
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-10-01
---

# Phase 12 — Validation Strategy

Planning contract only; implementation tests are pending. Nyquist compliance denotes every task has an automated check, not executed success.

## Test Infrastructure

Existing pytest and .venv/bin/python; configuration pyproject.toml. Quick command: `.venv/bin/python -m pytest -q tests/test_backtest_*.py`. Full: `.venv/bin/python -m pytest -q`. Focused runtime target below 60 seconds; actual timing must be measured during execution.

## Sampling Rate

Each task implements meaningful tests in the same commit and runs its focused command. Each wave runs accumulated backtest tests; final wave and pre-verification run full suite. No three-task gap and no watch mode. If focused latency exceeds 60 seconds, split checks without omitting coverage.

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---|---|---|---|---|---|---|---|---|---|
| 12-01-01 | 01 | 1 | FUT-01 | T-12-01–04 | Cutoff/reservation/input/offline invariants as assigned | unit/integration | `.venv/bin/python -m pytest -q tests/test_backtest_inputs.py` | ❌ created in task | pending |
| 12-01-02 | 01 | 1 | FUT-01 | T-12-01–04 | Cutoff/reservation/input/offline invariants as assigned | unit/integration | `.venv/bin/python -m pytest -q tests/test_backtest_inputs.py` | ❌ created in task | pending |
| 12-02-01 | 02 | 2 | FUT-01 | T-12-01–04 | Cutoff/reservation/input/offline invariants as assigned | unit/integration | `.venv/bin/python -m pytest -q tests/test_backtest_costs.py` | ❌ created in task | pending |
| 12-02-02 | 02 | 2 | FUT-01 | T-12-01–04 | Cutoff/reservation/input/offline invariants as assigned | unit/integration | `.venv/bin/python -m pytest -q tests/test_backtest_fills.py` | ❌ created in task | pending |
| 12-03-01 | 03 | 3 | FUT-01 | T-12-01–04 | Cutoff/reservation/input/offline invariants as assigned | unit/integration | `.venv/bin/python -m pytest -q tests/test_backtest_ledger.py` | ❌ created in task | pending |
| 12-03-02 | 03 | 3 | FUT-01 | T-12-01–04 | Cutoff/reservation/input/offline invariants as assigned | unit/integration | `.venv/bin/python -m pytest -q tests/test_backtest_ledger.py` | ❌ created in task | pending |
| 12-04-01 | 04 | 4 | FUT-01 | T-12-01–04 | Cutoff/reservation/input/offline invariants as assigned | unit/integration | `.venv/bin/python -m pytest -q tests/test_backtest_engine.py` | ❌ created in task | pending |
| 12-04-02 | 04 | 4 | FUT-01 | T-12-01–04 | Cutoff/reservation/input/offline invariants as assigned | unit/integration | `.venv/bin/python -m pytest -q tests/test_backtest_engine.py` | ❌ created in task | pending |
| 12-05-01 | 05 | 5 | FUT-01 | T-12-01–04 | Cutoff/reservation/input/offline invariants as assigned | unit/integration | `.venv/bin/python -m pytest -q tests/test_backtest_reporting.py` | ❌ created in task | pending |
| 12-05-02 | 05 | 5 | FUT-01 | T-12-01–04 | Cutoff/reservation/input/offline invariants as assigned | unit/integration | `.venv/bin/python -m pytest -q tests/test_backtest_reporting.py` | ❌ created in task | pending |
| 12-06-01 | 06 | 6 | FUT-01 | T-12-01–04 | Cutoff/reservation/input/offline invariants as assigned | unit/integration | `.venv/bin/python -m pytest -q tests/test_backtest_cli.py` | ❌ created in task | pending |
| 12-06-02 | 06 | 6 | FUT-01 | T-12-01–04 | Cutoff/reservation/input/offline invariants as assigned | unit/integration | `.venv/bin/python -m pytest -q tests/test_backtest_e2e.py` | ❌ created in task | pending |

## Wave 0 Requirements

- [ ] 12-01 task 1 creates strict-model fixture and tests/test_backtest_inputs.py; task 2 extends its cutoff/coverage assertions.
- [ ] Each later task creates its own mapped test file before running its verification; depends_on ensures fixture and preceding contracts exist. No future absent test command is declared already passing.
- [ ] No framework installation required.

## Manual-Only Verifications

All implemented behaviors have automated verification. Actual historical data and market-rule source curation must be reviewed before a real-history complete-evidence claim; fixture tests cannot substitute for that external evidence. No production account experiment required.

## Validation Sign-Off

- [x] Every task has an automated verification and creation ownership for missing tests.
- [x] Sampling continuity and fixture dependencies are explicit.
- [x] No watch mode; offline, deterministic checks.
- [ ] Actual feedback latency measured during execution.
- [ ] Wave 0 and all implementation tests executed successfully.

Approval: planning contract reviewed 2026-10-01; implementation validation pending.
