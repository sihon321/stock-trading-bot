---
phase: 07-deterministic-replay-validation
verified: 2026-07-13T05:11:18Z
status: passed
score: 11/11
behavior_unverified: 0
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 10/11
  gaps_closed:
    - "F-001: canonical fixtures now carry cutoff-safe raw OHLCV warm-up series, and replay derives screener technicals through the shipped calculate_technicals transform."
  gaps_remaining: []
  regressions: []
requirements:
  REPLAY-01: satisfied
  REPLAY-02: satisfied
  REPLAY-03: satisfied
  REPLAY-04: satisfied
---

# Phase 07: Deterministic Replay Validation Verification Report

**Phase Goal:** Operators can reproducibly exercise shipped screening, signal, risk, sizing, and execution rules against frozen historical scenarios without contacting live services.
**Verified:** 2026-07-13T05:11:18Z
**Status:** passed
**Re-verification:** Yes — after 07-06 gap closure

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|---|---|---|
| 1 | Frozen OHLCV flows through production candidate selection, then fixture signal/parser/risk/sizing/execution gates | **VERIFIED** | Both canonical bundles contain only raw `open/high/low/close/volume` warm-up rows. `run_replay_scenarios` cutoff-guards all history, builds the Korean-column DataFrame, calls the imported shipped `calculate_technicals(..., IndicatorConfig)`, then passes its `IndicatorResult.technicals` to production `screen_candidates`. The shipped-call, raw-mutation, and complete boundary tests pass. |
| 2 | Replay contacts no live LLM, KIS, Naver, pykrx, SQLite, network, or wall clock | **VERIFIED** | `trading_bot/replay.py` imports only pure domain/indicator/screener/execution seams plus local filesystem/Git evidence utilities. The replay CLI never calls `build_runtime`; its offline integration test passes. No invocation clock is read or persisted. |
| 3 | Identical deterministic inputs produce byte-identical ordered evidence and stable identity | **VERIFIED** | Canonical JSON, manifest-field sensitivity, outcome-order sensitivity, metadata exclusion, repeated CLI output identity, and shared helper/object result identity are implemented and green. |
| 4 | Complete manifest records fixture domains, policy, revision/diff, initial state, fixed time/date, and schema | **VERIFIED** | `ReplayManifest` and `build_replay_manifest` bind scenario/OHLCV/signal hashes, policy, HEAD plus relevant tracked-diff hash, state, evaluation time, trading date, and schema version. |
| 5 | Focused scenarios are isolated | **VERIFIED** | Each focused `ReplayScenario` declares its own initial cash, positions, and daily-loss state; each scenario invocation constructs fresh broker/risk state. |
| 6 | Full-day steps advance cash, positions, and daily loss in production rank order | **VERIFIED** | The full-day replay is ranked `000010`, `000020`, `000030`; COMPLETE and NONE fill effects persist correctly, and explicit realized loss reaches 500,000 before blocking the later BUY. |
| 7 | Every unmarked future-data request fails loudly before downstream work | **VERIFIED** | Loader and runner both apply `guarded_historical_view`. The adversarial test observes `FutureDataAccessError` with zero indicator, screener, execution, and broker-mutation calls; the explicitly marked rejection remains attributed. |
| 8 | Every required Phase 7 boundary has exactly one executed attributed check | **VERIFIED** | Eleven outcomes produce exactly one check for each member of `REQUIRED_BOUNDARIES`; exact `Counter` equality and non-empty scenario/ticker/stage/expected/actual fields fail closed. |
| 9 | Funnel exposes explicit denominators for BUY stages, actions, and blocks | **VERIFIED** | `ReplayCount` carries each numerator/denominator, stage monotonicity is enforced, and action/block denominators are tested. |
| 10 | CLI shows stable ID, summaries, funnel, verification, mismatch-only detail, and writes normalized JSON | **VERIFIED** | Offline CLI integration verifies stable output filename/ID, PASS summary, explicit funnel denominators, bounded anomaly-only detail, and complete normalized JSON evidence. |
| 11 | CLI/JSON make no profitability claim or metric | **VERIFIED** | Both surfaces include `NON_PROFITABILITY_DISCLAIMER`; normalized evidence is tested to exclude P&L, return, win-rate, Sharpe, and profitability keys. |

**Score:** 11/11 truths verified (0 present-but-behavior-unverified)

## Re-verification of Previous Findings

| Finding | Status | Evidence |
|---|---|---|
| F-001 — OHLCV materially drives `screen_candidates` | **CLOSED** | Canonical fixture history has exact raw fields only and four cutoff-safe warm-up rows per ticker under explicit 2/3-period `IndicatorConfig` windows. `run_replay_scenarios` directly calls the shipped indicator transform before screening. Mutating only raw market observations moves `000020` from second to first production rank. |
| F-002 — exact canonical check for all 11 boundaries | **CLOSED — regression check passed** | Required/executed boundary sets remain an exact one-count bijection with full attribution. |
| F-003 — full-day cash/position/daily-loss progression | **CLOSED — regression check passed** | Ranked state progression and later daily-loss BUY block remain green. |
| F-004 — one stable complete result identity | **CLOSED — regression check passed** | `ReplayResult.__post_init__` still delegates to `compute_result_id` over manifest, ordered outcomes, funnel, verification, and disclaimer. |

## Required Artifacts

| Artifact | Expected | Status | Details |
|---|---|---|---|
| `trading_bot/replay.py` | Strict offline replay, raw OHLCV projection, state progression, coverage, and stable identity | **VERIFIED** | Exists, substantive, and wired to shipped indicators, screener, parser/risk/sizing/execution, funnel, verification, CLI, and safe evidence output. |
| `tests/fixtures/replay/focused.json` | Eleven isolated raw-OHLCV boundary scenarios | **VERIFIED** | Eleven scenarios; each history record contains only ticker metadata, health, and raw OHLCV. No precomputed technical or `market_row` field exists. |
| `tests/fixtures/replay/full_day.json` | Raw-OHLCV multi-ticker ranked state progression | **VERIFIED** | Three out-of-order input histories produce the asserted production rank and state transitions after indicator calculation. |
| `tests/test_replay.py` | Adversarial deterministic replay regressions | **VERIFIED** | Covers strict schema, shipped transform arguments, raw-input sensitivity, cutoff ordering, exact boundaries, state progression, funnel, identity, and disclaimer. |
| `trading_bot/cli.py` / `tests/test_cli.py` | Offline operator replay and normalized evidence | **VERIFIED** | CLI directly composes replay functions and the integration test proves no live runtime construction. |
| `07-VALIDATION.md` | Executable requirement and gap-closure evidence map | **VERIFIED** | F-001 now cites raw schema, shipped transform, raw mutation, and zero-downstream-call tests. |

## Key Link Verification

| From | To | Via | Status | Details |
|---|---|---|---|---|
| Raw `market_history[*].ohlcv` | `trading_bot.indicators.calculate_technicals` | `_ohlcv_frame` plus explicit `_indicator_config` | **WIRED** | Direct imported production call at replay execution; spy verifies exact columns, monotonic unique index, and config equality. |
| `IndicatorResult` | `screen_candidates` | calculated technicals plus non-derived metadata and composed health | **WIRED** | Fixture health overrides only when explicitly non-AVAILABLE; otherwise production indicator health controls fail-closed screening. |
| Future-data guard | indicators/screener/execution/broker | cutoff validation before configuration/state construction and downstream calls | **WIRED** | Adversarial call counters remain zero at rejection. |
| Raw fixture signal | parser/risk/sizing/execution | `execute_signal_cycle(..., dry_run=True)` | **WIRED** | Production execution seam consumes the raw JSON string for every selected candidate. |
| Step loss transition | next ranked execution | new explicit `DailyLossState` after each step | **WIRED** | Later BUY consumes the advanced loss state and becomes `HOLD/RISK_BLOCK`. |
| `REQUIRED_BOUNDARIES` | `ReplayVerification.checks` | exact `Counter` equality and attribution | **WIRED** | Missing, duplicate, unknown, or unattributed evidence fails verification. |
| `compute_result_id` | `ReplayResult.result_id` and CLI JSON | shared canonical deterministic document | **WIRED** | Helper/object equivalence and deterministic component sensitivity tests pass. |

## Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|---|---|---|---|---|
| `trading_bot/replay.py` | per-ticker technicals | checked-in raw OHLCV → shipped `calculate_technicals` | Yes; raw mutation changes production rank | **FLOWING** |
| `trading_bot/replay.py` | ordered outcomes | production candidates + raw signals + explicit broker/risk state | Yes; boundary and full-day tests exercise terminal outcomes | **FLOWING** |
| `trading_bot/cli.py` | persisted replay evidence | manifest + outcomes + funnel + verification | Yes; CLI integration reads and validates normalized JSON | **FLOWING** |

## Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|---|---|---|---|
| F-001 plus representative deterministic/offline regressions | Exact ten named pytest nodes covering raw schema, shipped transform, raw rank mutation, future call ordering, boundary bijection, state progression, identity, disclaimer, and CLI | 10 passed in 0.62s | **PASS** |
| Full Phase 7 production-contract suite | `pytest tests/test_replay.py tests/test_indicators.py tests/test_screener.py tests/test_signal_parser.py tests/test_risk.py tests/test_execution.py tests/test_cli.py` | 148 passed in 1.22s | **PASS** |
| Full repository regression | Orchestrator full-suite run | 406 passed | **PASS** |

## Probe Execution

No probes are declared by Phase 7 plans or summaries, and no migration/tooling probe is required.

## Requirements Coverage

| Requirement | Source Plans | Description | Status | Evidence |
|---|---|---|---|---|
| REPLAY-01 | 07-01, 07-02, 07-03, 07-04, 07-06 | Historical OHLCV traverses production screener and execution gates entirely offline | **SATISFIED** | Raw fixture → shipped indicator → production screener link is now substantive, wired, and behaviorally tested; parser/risk/sizing/execution and CLI offline tests remain green. |
| REPLAY-02 | 07-01, 07-02, 07-03, 07-05 | Deterministic manifest, ordered evidence, and stable identity | **SATISFIED** | Complete manifest and unified identity sensitivity/equivalence tests pass. |
| REPLAY-03 | 07-01, 07-02, 07-03 | BUY/HOLD/SELL comparison without profitability claims | **SATISFIED** | Explicit-denominator funnel, action/block summaries, and disclaimer/forbidden-key tests pass. |
| REPLAY-04 | 07-01, 07-02, 07-03, 07-04, 07-05, 07-06 | Complete boundary/failure/no-look-ahead verification | **SATISFIED** | All eleven boundaries execute exactly once with attribution and future OHLCV is rejected before downstream work. |

All requirement IDs declared by 07-01 through 07-06 exist in `REQUIREMENTS.md`; all four Phase 7 requirements are claimed by plans and none are orphaned.

## Anti-Patterns Found

No unreferenced `TBD`, `FIXME`, or `XXX` markers, placeholder implementations, deferred `<human-check>` blocks, or declared probes were found in the Phase 7 implementation and evidence surface. Automated key-link queries reported false negatives for symbolic `from` labels that were not file paths; each such link was manually traced and behaviorally verified above.

## Disconfirmation Pass

- **Potential partial requirement checked:** the earlier OHLCV claim was partial because fixture-derived technicals bypassed production indicators. The alternate path is now removed from canonical history and step schemas, and direct shipped-transform evidence closes it.
- **Potential misleading test checked:** the CLI offline test alone only prevents `build_runtime`. Import inspection and the replay composition show no pykrx/KIS/Naver/LLM/SQLite/network imports or calls, while the indicator import-boundary suite also passes.
- **Potential uncovered error path checked:** future nested OHLCV can arrive after strict loading through an in-memory scenario. The runner independently guards again, and the call-order test proves rejection before indicator, screener, execution, or broker mutation.

## Human Verification Required

None. All Phase 7 truths are deterministic, text/data based, and exercised by automated tests.

## Gaps Summary

No remaining gaps. F-001 is closed without regression in F-002 through F-004. The actual codebase now proves the complete frozen raw-OHLCV → shipped indicator → production screener → raw signal/parser/risk/sizing/execution path, deterministic identity/funnel evidence, exact boundary coverage, no-look-ahead behavior, and non-profitability contract.

---

_Verified: 2026-07-13T05:11:18Z_
_Verifier: gsd-verifier (generic-agent workaround)_
