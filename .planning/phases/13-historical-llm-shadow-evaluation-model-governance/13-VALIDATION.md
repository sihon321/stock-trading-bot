---
phase: 13
slug: historical-llm-shadow-evaluation-model-governance
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-10-01
---

# Phase 13 — Validation Strategy

Execution validated: 7 plans / 14 tasks. Final full regression: **986 passed in 36.22s**; no paid LLM/KIS calls.

## Test Infrastructure

| Property | Value |
|---|---|
| Framework | pytest 8.4.2, existing project userbase |
| Config | pyproject.toml |
| Quick command | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_shadow_*.py` |
| Regression command | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_backtest_*.py` |
| Full command | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` |
| Feedback target | Focused under 60s; full ~30s estimate, measure during execution |

## Sampling Rate

After each task use its exact owned-file command below. Create meaningful owned test cases before implementation checks; missing files or zero collected tests are failures, not passes. After each completed wave run all created shadow tests and backtest regression. Before phase verification run full suite. No watch flags, external API calls or paid requests.

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---|---|---|---|---|---|---|---|---|---|
| 13-01-01 | 01 | 1 | FUT-02, GOV-01 | T-13-01–06 | Frozen inputs, bounded attempts, no trading/promotion authority | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_shadow_models.py` | Created and verified | passed |
| 13-01-02 | 01 | 1 | FUT-02, GOV-01 | T-13-01–06 | Frozen inputs, bounded attempts, no trading/promotion authority | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_shadow_models.py` | Created and verified | passed |
| 13-02-01 | 02 | 2 | FUT-02, GOV-01 | T-13-01–06 | Frozen inputs, bounded attempts, no trading/promotion authority | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_shadow_inputs.py tests/test_backtest_engine.py` | Created and verified | passed |
| 13-02-02 | 02 | 2 | FUT-02, GOV-01 | T-13-01–06 | Frozen inputs, bounded attempts, no trading/promotion authority | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_shadow_inputs.py tests/test_backtest_engine.py` | Created and verified | passed |
| 13-03-01 | 03 | 2 | FUT-02, GOV-01 | T-13-01–06 | Frozen inputs, bounded attempts, no trading/promotion authority | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_shadow_budget.py` | Created and verified | passed |
| 13-03-02 | 03 | 2 | FUT-02, GOV-01 | T-13-01–06 | Frozen inputs, bounded attempts, no trading/promotion authority | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_shadow_budget.py tests/test_shadow_store.py` | Created and verified | passed |
| 13-04-01 | 04 | 2 | FUT-02, GOV-01 | T-13-01–06 | Frozen inputs, bounded attempts, no trading/promotion authority | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_shadow_providers.py` | Created and verified | passed |
| 13-04-02 | 04 | 2 | FUT-02, GOV-01 | T-13-01–06 | Frozen inputs, bounded attempts, no trading/promotion authority | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_shadow_providers.py` | Created and verified | passed |
| 13-05-01 | 05 | 3 | FUT-02, GOV-01 | T-13-01–06 | Frozen inputs, bounded attempts, no trading/promotion authority | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_shadow_runner.py` | Created and verified | passed |
| 13-05-02 | 05 | 3 | FUT-02, GOV-01 | T-13-01–06 | Frozen inputs, bounded attempts, no trading/promotion authority | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_shadow_runner.py` | Created and verified | passed |
| 13-06-01 | 06 | 4 | FUT-02, GOV-01 | T-13-01–06 | Frozen inputs, bounded attempts, no trading/promotion authority | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_shadow_reporting.py` | Created and verified | passed |
| 13-06-02 | 06 | 4 | FUT-02, GOV-01 | T-13-01–06 | Frozen inputs, bounded attempts, no trading/promotion authority | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_shadow_reporting.py` | Created and verified | passed |
| 13-07-01 | 07 | 5 | FUT-02, GOV-01 | T-13-01–06 | Frozen inputs, bounded attempts, no trading/promotion authority | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_shadow_cli.py` | Created and verified | passed |
| 13-07-02 | 07 | 5 | FUT-02, GOV-01 | T-13-01–06 | Frozen inputs, bounded attempts, no trading/promotion authority | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_shadow_cli.py` | Created and verified | passed |

## Wave 0 Requirements

Existing pytest/userbase infrastructure is available. Phase 13 files below are missing at planning time and MUST be created by the owning task before its automated verify; they are part of each task's action and files_modified, not presumed existing stubs.

- 13-01 task 1: tests/test_shadow_models.py and tests/fixtures/shadow/minimal_manifest.json (strict contract and synthetic fixture).
- 13-02 task 1: tests/test_shadow_inputs.py (baseline observer and cutoff truth); existing test_backtest_engine.py is extended.
- 13-03 task 1/2: tests/test_shadow_budget.py and tests/test_shadow_store.py. Task 1's verify is narrowed to budget until store task 2 creates its file.
- 13-04 task 1: tests/test_shadow_providers.py (injected fake SDK/transport; zero actual HTTP).
- 13-05 task 1: tests/test_shadow_runner.py (crash/resume and deterministic schedule).
- 13-06 task 1: tests/test_shadow_reporting.py (paired gates then saved evidence).
- 13-07 task 1: tests/test_shadow_cli.py (Typer and capability tripwires).

Do not mark wave_0_complete until these meaningful tests exist and collect. Tests that merely mirror dataclass assignments do not prove the safety behaviors.

## Held-Out / Adversarial Cases

Future-input perturbation, multiple tickers sharing cash/reservations, split-adjusted indicator versus raw tradable prices, stopped/unknown input, malformed output versus valid HOLD risk precedence, reasoning/cache usage dimensions, cap boundary + outstanding reservation, timeout/in-flight process death, concurrent runner, after-result-before-checkpoint crash, foreign live DB path, tampered evidence, missing strata, zero valid pairs, unknown charge and attempted CLI subprocess. Use fake clients and injected durable-boundary faults. Independent-agent review was not run; inline adversarial planning checks are recorded separately.

## Manual-Only Verifications

No paid call is required to complete implementation or automated acceptance. Before an operator optionally requests a real shadow run, review the chosen model/endpoint capability and dated pricing/context bound, credential origin, native-currency FX if used and historical-source attribution. A paid run remains outside this plan's test commands. Codex CLI stays blocked absent isolation/cost proof; this is an automated fail-closed check.

## Validation Sign-Off

- [x] All 14 tasks have bounded automated checks and explicit test-creation ownership.
- [x] No three consecutive tasks lack automated verification.
- [x] Missing test references have owned creation tasks before use.
- [x] No watch-mode or paid-test requirement.
- [x] Planning Nyquist contract is structurally compliant.
- [x] Actual implementation tests exist, collect and pass.
- [x] Focused feedback below 60s; final full regression measured at 36.22s.
- [x] Final full regression passes.

**Sign-off:** Execution verified inline 2026-10-01. 80 shadow + 78 backtest cases passed inside the 986-case final full suite; independent-agent review and paid smoke were not run.


## Actual Execution Measurements

| Plan | Task 1 original check | Task 2 original check |
|---|---|---|
| 13-01 | 12 passed / 0.05s | 22 passed / 0.07s |
| 13-02 | 16 passed / 2.34s | 20 passed / 3.06s |
| 13-03 | 4 passed / 0.05s | 7 passed / 1.12s |
| 13-04 | 7 passed / 2.30s | 11 passed / 2.57s |
| 13-05 | 4 passed / 1.03s | 8 passed / 1.66s |
| 13-06 | 3 passed / 0.83s | 5 passed / 1.22s |
| 13-07 | 3 passed / 1.32s | 6 passed / 3.78s |

Final guard check: 46 passed / 6.17s. Final full suite: 986 passed / 36.22s. Original wave checks progressed through 124, 132, 140 and 152 passing combined shadow/backtest cases; final full suite includes six later guards. Transient failures were corrected: pre-buffered mock response reading; fixture JSON model serialization; malformed-fixture agreement assumptions; relative Git provenance; one missing test import. No failure remains. See 13-VERIFICATION.md for final per-file inventory and practical limits.
