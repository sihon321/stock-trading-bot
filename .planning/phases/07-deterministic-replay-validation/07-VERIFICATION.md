---
phase: 07-deterministic-replay-validation
verified: 2026-07-12T00:00:00+09:00
status: gaps_found
score: 7/11
requirements:
  REPLAY-01: blocked
  REPLAY-02: satisfied
  REPLAY-03: satisfied
  REPLAY-04: blocked
gaps:
  - id: F-001
    severity: blocker
    must_have: "Frozen historical OHLCV traverses the production candidate-selection path."
    evidence: "market_history is only cutoff-checked; run_replay_scenarios screens precomputed step.market_row values. Replacing every historical close leaves all outcomes unchanged."
  - id: F-002
    severity: blocker
    must_have: "Every Phase 7 boundary has a checked-in fixture expectation and visible verification result."
    evidence: "The bundle declares 11 boundary labels but focused.json contains only 5 scenarios; HOLD, ordinary SELL, stale data, take profit, sizing boundary, and future-access are not replay outcomes/checks."
  - id: F-003
    severity: blocker
    must_have: "Full-day steps carry cash, positions, and daily-loss state forward."
    evidence: "The schema has no per-step daily-loss fact/update and run_replay_scenarios constructs one immutable DailyLossState for the whole scenario. The only full-day fixture exercises two BUYs, not daily-loss progression."
  - id: F-004
    severity: warning
    must_have: "compute_result_id and ReplayResult expose one stable result identity contract."
    evidence: "compute_result_id hardcodes funnel=None and verification=None, while ReplayResult hashes actual funnel/verification. The two public identity paths return different IDs for the same complete replay."
---

# Phase 07 Verification

## Verdict

**GAPS FOUND.** The implementation has a working offline CLI, production parser/risk/sizing/execution reuse, deterministic JSON evidence, and a useful explicit-denominator funnel. However, the phase goal is not achieved because historical OHLCV does not drive screening, most required boundary cases are labels rather than replayed expectations, and full-day daily-loss progression is not implemented.

## Goal-Backward Results

| # | Observable truth | Status | Evidence |
|---|---|---|---|
| 1 | Frozen OHLCV flows through production candidate selection, then fixture signal/parser/risk/sizing/execution gates | **FAILED — BLOCKER** | `run_replay_scenarios` passes `ReplayStep.market_row` directly to `screen_candidates`; `scenario.market_history` is only passed to `guarded_historical_view`. An adversarial mutation of every historical close produced identical outcomes. Parser/risk/sizing/execution do correctly reuse `execute_signal_cycle`. |
| 2 | Replay contacts no live LLM, KIS, Naver, pykrx, SQLite, network, or wall clock | **VERIFIED** | Replay imports and calls only the pure screener/execution seams plus in-memory broker. CLI directly invokes replay functions and never calls `build_runtime`; focused CLI test with `build_runtime` patched to raise passes. |
| 3 | Identical deterministic inputs produce byte-identical ordered evidence and stable identity | **VERIFIED** | Canonical serialization, manifest hashing, ordered outcomes, metadata exclusion, atomic output, and one-at-a-time manifest sensitivity are covered and pass. |
| 4 | Complete manifest records fixture domains, policy, revision/diff, initial state, fixed time/date, schema | **VERIFIED** | `ReplayManifest` and `build_replay_manifest` contain all contracted fields; relevant tracked diff changes its hash and observational metadata is outside identity. |
| 5 | Focused scenarios are isolated | **VERIFIED** | A new `MockBroker` and `DailyLossState` are constructed per scenario. |
| 6 | Full-day candidates run in production rank order and complete/no-fill state is observed immediately | **PARTIALLY VERIFIED** | Existing full-day test proves `(-score, ticker)` ordering, COMPLETE cash mutation, and NONE cash/position stability. Daily-loss state cannot progress, so the broader state truth fails (F-003). |
| 7 | Every future-data request fails loudly | **VERIFIED** | Future `market_history` and future `market_row.observed_at` values raise `FutureDataAccessError` before runner mutation. |
| 8 | Required Phase 7 boundary catalog is replayed and expectation-checked | **FAILED — BLOCKER** | `boundaries` lists 11 strings, but only five focused scenarios exist. `verify_replay_expectations` checks only outcomes that exist and only the final action. Missing cases can therefore pass invisibly. |
| 9 | Funnel exposes explicit denominators for BUY stages, actions, and blocks | **VERIFIED** | `ReplayCount` is used for each stage/action/block reason; monotonic facts are enforced and tests pass. |
| 10 | CLI shows stable ID, scenario summary, funnel, verification, mismatch-only detail, and writes JSON | **VERIFIED** | CLI integration tests pass; invalid fixtures fail with bounded diagnostics and mismatches exit nonzero. |
| 11 | CLI/JSON make no profitability claim or metric | **VERIFIED** | Mandatory disclaimer is emitted in both; normalized evidence contains no performance metric fields. |

## Requirements Coverage

| Requirement | Status | Evidence |
|---|---|---|
| REPLAY-01 | **BLOCKED** | Production parser/risk/sizing/execution are reused and execution is offline, but frozen OHLCV never influences candidate selection. |
| REPLAY-02 | **SATISFIED** | Deterministic manifest, normalized ordered evidence, code-state evidence, and stable `ReplayResult` identity are implemented and tested. |
| REPLAY-03 | **SATISFIED** | BUY/HOLD/SELL counts and stage funnel have explicit denominators; disclaimer and absence of profitability metrics are verified. |
| REPLAY-04 | **BLOCKED** | Threshold-at/below, malformed, stop-loss, and daily-loss cases exist; ordinary HOLD/SELL, stale, take-profit, sizing, and look-ahead are not visible replay expectation outcomes. |

No Phase 7 requirements are orphaned from plan frontmatter.

## Artifact and Wiring Audit

- `trading_bot/replay.py`: substantive and wired to `screen_candidates` and `execute_signal_cycle`, but the OHLCV-to-screener link is hollow.
- `trading_bot/cli.py`: replay command is wired directly to loader, runner, funnel, manifest, result writer.
- `tests/fixtures/replay/focused.json`: substantive JSON, but does not implement the declared catalog.
- `tests/fixtures/replay/full_day.json`: substantive ordering/fill fixture, but only two BUY steps and no daily-loss transition.
- `tests/test_replay.py`, `tests/test_cli.py`: runnable and green, but catalog assertions are too weak (`>=` five IDs and boundary-label count) and do not prove the missing scenarios.
- No unreferenced `TBD`, `FIXME`, or `XXX` debt markers were found in Phase 7 implementation/test files.

## Behavioral Evidence

| Check | Result |
|---|---|
| `.venv/bin/python -m pytest -q tests/test_replay.py tests/test_cli.py -k replay --maxfail=1` | **PASS:** 31 passed, 12 deselected |
| `.venv/bin/python -m pytest -q` | **PASS:** 391 passed |
| Enumerate scenario IDs vs outcomes | **FAIL contract:** only 5 focused scenarios for 11 declared boundaries |
| Replace all `market_history[].close` values and compare outcomes | **FAIL contract:** outcomes unchanged |
| Compare `compute_result_id(manifest, outcomes)` with a complete `ReplayResult.result_id` | **WARNING:** IDs differ when funnel/verification are present |

## Required Gap Closure

1. Make cutoff-guarded historical OHLCV/derived data the actual input that produces the production screener rows, or revise the fixture contract so the historical input and derived row are cryptographically and behaviorally linked; add a mutation test proving OHLCV changes can affect candidate outcomes.
2. Add executable focused scenarios and attributed checks for every required boundary: explicit HOLD, ordinary SELL, stale data, take-profit override, sizing boundary, and future-access rejection. Verification must fail when any declared boundary has no executed check.
3. Add explicit per-step daily-loss state facts/updates for full-day scenarios and test that a later BUY sees the updated state. Preserve the non-profitability boundary by using explicit fixture facts rather than inferred P&L.
4. Unify `compute_result_id` and `ReplayResult.result_id` around the same complete deterministic document, or remove the misleading second identity path.

