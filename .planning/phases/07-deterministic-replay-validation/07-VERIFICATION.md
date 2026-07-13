---
phase: 07-deterministic-replay-validation
verified: 2026-07-13T00:13:08Z
status: gaps_found
score: 10/11
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 7/11
  gaps_closed:
    - "F-002: all eleven required boundaries now have exactly one executed and attributed check."
    - "F-003: full-day replay now advances cash, positions, and explicit daily-loss state in production rank order."
    - "F-004: compute_result_id, ReplayResult, and CLI now share the complete deterministic identity document."
  gaps_remaining:
    - "F-001: fixture OHLCV still does not drive production screening; precomputed technical rows do."
  regressions: []
requirements:
  REPLAY-01: blocked
  REPLAY-02: satisfied
  REPLAY-03: satisfied
  REPLAY-04: satisfied
gaps:
  - truth: "Frozen historical OHLCV flows through production candidate selection before signal, parser, risk, sizing, and execution gates."
    status: failed
    reason: "Replay history contains precomputed screener fields and technicals, not OHLCV. The runner forwards the latest precomputed record to screen_candidates and never calls calculate_technicals; the new mutation test changes atr_14/historical_volatility rather than an OHLCV price or volume."
    artifacts:
      - path: "trading_bot/replay.py"
        issue: "load_replay_bundle requires market/state/trading_value/technicals/health records and run_replay_scenarios projects them directly into screen_candidates; no OHLCV-to-indicator transform exists."
      - path: "tests/fixtures/replay/full_day.json"
        issue: "market_history has one pre-derived technical row per ticker and no open/high/low/close/volume warm-up series."
      - path: "tests/test_replay.py"
        issue: "test_historical_input_materially_drives_production_screener_rank mutates technicals, so it cannot prove OHLCV materially drives screening."
    missing:
      - "Store cutoff-safe per-ticker OHLCV warm-up series in the replay fixture."
      - "Run the shipped calculate_technicals transform (or a production-equivalent existing composition seam) before screen_candidates."
      - "Add a regression that mutates close/high/low/volume and proves selection or rank changes, while a future OHLCV row fails before screening or broker mutation."
---

# Phase 07: Deterministic Replay Validation Verification Report

**Phase Goal:** Operators can reproducibly exercise shipped screening, signal, risk, sizing, and execution rules against frozen historical scenarios without contacting live services.
**Verified:** 2026-07-13T00:13:08Z
**Status:** gaps_found
**Re-verification:** Yes — after gap closure

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|---|---|---|
| 1 | Frozen OHLCV flows through production candidate selection, then fixture signal/parser/risk/sizing/execution gates | **FAILED — BLOCKER** | `market_history` records are already-derived screener rows. `run_replay_scenarios` removes `observed_at`, wraps health, and calls `screen_candidates`; it never calls `calculate_technicals`. The claimed mutation test changes `atr_14` and `historical_volatility`, not OHLCV. |
| 2 | Replay contacts no live LLM, KIS, Naver, pykrx, SQLite, network, or wall clock | **VERIFIED** | Replay remains a pure fixture composition path; the CLI test patches `build_runtime` to raise and passes. Full suite is green. |
| 3 | Identical deterministic inputs produce byte-identical ordered evidence and stable identity | **VERIFIED** | Canonical serialization, repeated CLI output-file stability, deterministic-field sensitivity, and metadata exclusion are tested. |
| 4 | Complete manifest records fixture domains, policy, revision/diff, initial state, fixed time/date, and schema | **VERIFIED** | `ReplayManifest` and `build_replay_manifest` retain every locked deterministic input domain. |
| 5 | Focused scenarios are isolated | **VERIFIED** | Each scenario constructs a new `MockBroker` and `DailyLossState`; focused fixtures have independent initial state. |
| 6 | Full-day steps advance cash, positions, and daily loss in production rank order | **VERIFIED** | `test_full_day_uses_production_rank_and_fill_state` and `test_full_day_daily_loss_progresses_and_blocks_later_buy` pass. COMPLETE mutates broker state, NONE preserves it, and the later BUY is `HOLD/RISK_BLOCK` after loss reaches 500,000. |
| 7 | Every unmarked future-data request fails loudly | **VERIFIED** | Loader and runner apply `guarded_historical_view`; the dedicated expected-rejection scenario is explicit and ordinary future rows raise `FutureDataAccessError`. |
| 8 | Every required Phase 7 boundary has exactly one executed attributed check | **VERIFIED** | Eleven outcomes produce eleven `ReplayCheck`s. The exact `Counter` equality fails on missing, duplicate, or unknown IDs, and non-empty scenario/ticker/stage/expected/actual attribution is required. |
| 9 | Funnel exposes explicit denominators for BUY stages, actions, and blocks | **VERIFIED** | `ReplayCount` denominators and monotonic stage invariants remain implemented and tested. |
| 10 | CLI shows stable ID, summaries, funnel, verification, mismatch-only detail, and writes normalized JSON | **VERIFIED** | CLI integration tests pass twice with one stable result file and bounded mismatch/error output. |
| 11 | CLI/JSON make no profitability claim or metric | **VERIFIED** | Both emit the non-profitability disclaimer; normalized evidence contains no performance metric fields. |

**Score:** 10/11 truths verified (0 present-but-behavior-unverified)

## Re-verification of Previous Findings

| Finding | Status | Evidence |
|---|---|---|
| F-001 — OHLCV materially drives `screen_candidates` | **REMAINS OPEN** | The fixture and loader accept precomputed technical rows only. The mutation test modifies those technical fields, bypassing `calculate_technicals(ohlcv, ...)`. |
| F-002 — exact canonical check for all 11 boundaries | **CLOSED** | `REQUIRED_BOUNDARIES` ↔ executed checks is an exact one-count `Counter` bijection; missing/duplicate/unknown cases fail. |
| F-003 — full-day cash/position/daily-loss progression | **CLOSED** | Ranked three-step fixture observes COMPLETE/NONE broker behavior and an explicit loss transition that blocks later BUY. |
| F-004 — one stable complete result identity | **CLOSED** | `ReplayResult.__post_init__` delegates to `compute_result_id` using manifest, ordered outcomes, funnel, verification, and disclaimer; CLI persists that same `result_id`. |

## Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `trading_bot/replay.py` | Offline replay, state progression, exact coverage, stable identity | **PARTIAL** | Substantive and wired; OHLCV-to-indicator-to-screener link is missing. |
| `tests/fixtures/replay/focused.json` | Executable catalog for all boundaries | **VERIFIED** | Eleven focused scenarios, including explicit expected future rejection. |
| `tests/fixtures/replay/full_day.json` | Ranked state progression | **VERIFIED** | Three candidates, complete/no-fill evidence, explicit loss progression, later BUY block. |
| `tests/test_replay.py` | Adversarial replay regressions | **PARTIAL** | F-002/F-003/F-004 coverage is substantive; F-001 test mutates precomputed outputs instead of OHLCV inputs. |
| `tests/test_cli.py` | Offline CLI and stable evidence | **VERIFIED** | Offline-builder prohibition, repeatability, output, disclaimer, and mismatch behavior are tested. |

## Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| Frozen OHLCV | `screen_candidates` | `calculate_technicals` / production indicator seam | **NOT WIRED** | No OHLCV series exists in the fixture contract and `calculate_technicals` is never invoked by replay. |
| Frozen precomputed row | `screen_candidates` | latest cutoff-safe ticker record | **WIRED** | This is deterministic but does not satisfy the OHLCV contract. |
| Step loss transition | `execute_signal_cycle` | updated `DailyLossState` for next ranked candidate | **WIRED** | Transition is applied after the current step; subsequent candidates consume it. |
| `REQUIRED_BOUNDARIES` | `ReplayVerification.checks` | exact `Counter` equality and attribution | **WIRED** | Missing, duplicate, unknown, and unattributed evidence fails verification. |
| `compute_result_id` | `ReplayResult.result_id` and CLI JSON | shared deterministic result document | **WIRED** | Object delegates to helper; CLI writes the object's ID. |

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| Four gap selectors | `.venv/bin/python -m pytest -q tests/test_replay.py -k 'historical_input_materially or required_boundaries or boundary_bijection or daily_loss_progresses or complete_result_helper or complete_result_identity' --maxfail=1` | 10 passed | **PASS, with F-001 semantic defect noted** |
| Full repository regression | `PYTHONUSERBASE="$PWD/.python-userbase" .venv/bin/python -m pytest -q` | 401 passed in 14.15s | **PASS** |
| OHLCV schema/data-flow audit | Inspect loader fields, fixture rows, and replay imports/calls | No OHLCV columns or `calculate_technicals` call; mutation changes technicals | **FAIL** |

## Requirements Coverage

| Requirement | Status | Evidence |
|---|---|---|
| REPLAY-01 | **BLOCKED** | Offline production parser/risk/sizing/execution and screener calls exist, but historical OHLCV is replaced by precomputed technical rows. |
| REPLAY-02 | **SATISFIED** | Manifest, canonical evidence, dirty-code state, ordered outcomes, and unified stable identity are implemented. |
| REPLAY-03 | **SATISFIED** | Explicit-denominator funnel and non-profitability output contract remain green. |
| REPLAY-04 | **SATISFIED** | All eleven locked boundaries execute exactly once with attribution; look-ahead rejection is explicit and fail-loud otherwise. |

No Phase 7 requirements are orphaned.

## Anti-Patterns Found

No unreferenced `TBD`, `FIXME`, or `XXX` markers were found in the Phase 7 implementation, fixtures, or tests. No deferred human checks or declared probes exist for this phase.

## Human Verification Required

None. The remaining failure is programmatically observable.

## Gaps Summary

F-002, F-003, and F-004 are closed without regression. F-001 remains a blocker: the implementation proves that frozen **precomputed screener rows** affect production ranking, but the phase contract requires frozen historical **OHLCV** to traverse the production candidate-selection path. The checked-in fixture lacks OHLCV warm-up data, replay does not call the shipped indicator calculation, and the mutation test alters derived technical values. Phase 7 therefore remains incomplete despite 401 passing tests.

---

_Verified: 2026-07-13T00:13:08Z_
_Verifier: gsd-verifier (generic-agent workaround)_
