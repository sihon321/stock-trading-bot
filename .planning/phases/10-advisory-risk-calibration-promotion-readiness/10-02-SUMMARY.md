---
phase: 10-advisory-risk-calibration-promotion-readiness
plan: 02
subsystem: calibration-analysis
tags: [replay, counterfactual, risk-ranking, deterministic-reporting, sha256]
requires:
  - phase: 10-advisory-risk-calibration-promotion-readiness
    provides: immutable one-field candidate catalog and read-only calibration evidence envelope
provides:
  - production-replay-path evaluation for every locked policy variant
  - explicit action, block, trigger, exposure, and expected-action-delta metrics
  - transparent risk-first provisional judgment with named materiality thresholds
  - canonical calibration report identity and deterministic Korean advisory rendering
affects: [10-03-calibration-cli, 10-04-promotion-readiness]
tech-stack:
  added: []
  patterns: [production-path counterfactuals, observable lexicographic ranking, canonical report hashing, mandatory non-profitability disclaimer]
key-files:
  created: []
  modified: [trading_bot/calibration.py, trading_bot/calibration_reporting.py, tests/test_calibration.py, tests/test_calibration_reporting.py]
key-decisions:
  - "Run every candidate by replacing exactly its declared ReplayScenario policy key and invoking run_replay_scenarios()."
  - "Compute end-of-step exposure as position quantity times fixture price and never label it as profit or return."
  - "Rank lexicographically by fewer risk events, lower exposure, then fewer order-eligible opportunities without a composite score."
  - "Require a one-event, KRW 100,000 exposure, or one-opportunity delta before labeling a changed leader provisional."
patterns-established:
  - "Expected-action mismatch is an explicit calibration delta, not a counterfactual execution failure."
  - "Calibration identity hashes source identities, evidence counts, risk cases, variants, metrics, judgment, and disclaimer."
requirements-completed: [CAL-01, CAL-02, CAL-04]
coverage:
  - id: D1
    description: "Every one-field variant executes through production replay semantics with deterministic explicit metrics and exposure."
    requirement: CAL-01
    verification:
      - kind: integration
        ref: "tests/test_calibration.py -k 'counterfactual or confidence or position or stop or take or deterministic'"
        status: pass
    human_judgment: false
  - id: D2
    description: "Risk-first materiality retains baseline for ties or immaterial deltas and limits a changed leader to PROVISIONAL_CANDIDATE."
    requirement: CAL-02
    verification:
      - kind: unit
        ref: "tests/test_calibration.py#test_risk_first_judgment_precedes_exposure_and_opportunity_tiebreaks"
        status: pass
      - kind: unit
        ref: "tests/test_calibration.py#test_materiality_is_deterministic_and_retains_baseline_below_threshold"
        status: pass
    human_judgment: false
  - id: D3
    description: "The deterministic report exposes all denominators, deltas, uncertainty, and risk cases without execution authority or profitability claims."
    requirement: CAL-04
    verification:
      - kind: integration
        ref: "tests/test_calibration_reporting.py#test_calibration_report_renders_exact_deltas_uncertainty_and_no_application"
        status: pass
    human_judgment: false
duration: 6 min
completed: 2026-08-10
status: complete
---

# Phase 10 Plan 2: Counterfactual Calibration Summary

**Every locked policy candidate now runs through shipped replay semantics and produces a canonical, risk-first Korean advisory report that keeps the short sample provisional and non-executable.**

## Performance

- **Duration:** 6 min
- **Started:** 2026-08-10T14:05:47+09:00
- **Completed:** 2026-08-10T14:10:54+09:00
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments

- Cloned each replay scenario policy, changed only the declared calibration field, and invoked `run_replay_scenarios()` for all eleven baseline/candidate variants.
- Added deterministic counts for evaluated outcomes, BUY/HOLD/SELL, order eligibility, low confidence, risk blocks, stop-loss, take-profit, expected-action deltas, and end-of-step exposure.
- Added transparent lexicographic judgment with named materiality thresholds and stable `BASELINE`, `PROVISIONAL_CANDIDATE`, and `NO_MEANINGFUL_DIFFERENCE` statuses.
- Built canonical SHA-256 report identity from normalized sources, evidence, metrics, and judgment rather than rendered prose.
- Rendered exact counts, baseline-relative deltas, risk cases, missing-portfolio facts, `INSUFFICIENT_EVIDENCE`, advisory limits, and the replay non-profitability disclaimer.

## Task Commits

Each TDD task was committed as a failing contract followed by its passing implementation:

1. **Task 1: Production-path one-field variant evaluation** — `6703c01` (test), `6961b9e` (fixture-boundary correction), `38f9d81` (feat)
2. **Task 2: Risk-first judgment and uncertainty report** — `e7ec908` (test), `7a20b71` (feat)

## Files Created/Modified

- `trading_bot/calibration.py` — variant metrics/evaluations, production replay orchestration, materiality constants, and risk-first judgment.
- `tests/test_calibration.py` — one-field runner spy, confidence/position/stop/take boundaries, deterministic metrics, ranking, ties, and materiality tests.
- `trading_bot/calibration_reporting.py` — report rows, canonical identity builder, and deterministic Korean rendering.
- `tests/test_calibration_reporting.py` — identity sensitivity, exact denominator/delta rendering, insufficient evidence, disclaimer, and no-execution-language tests.

## Decisions Made

- Risk ordering uses the observable tuple `risk events ascending → exposure ascending → order eligibility ascending`; the report prints that tuple and emits no aggregate score.
- A changed leader is material at one risk event, KRW 100,000 exposure, or one order-eligible opportunity. Below those boundaries, the current baseline is retained.
- Exposure uses only replay `position_quantity_after * current_price`; unfilled order intent is not counted as held exposure.
- Fixture expected-action mismatch remains visible in `expectation_deltas` because a policy counterfactual is expected to differ from baseline fixture expectations.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Used the filled full-day fixture for position exposure boundaries**
- **Found during:** Task 1 counterfactual boundary verification
- **Issue:** Focused BUY fixtures intentionally use `fill=NONE`, so maximum-position candidates correctly produced identical end-of-step held exposure.
- **Fix:** Kept focused fixtures for confidence/trigger boundaries and used the production full-day filled BUY with a 20% cash fraction to isolate the 500k/1m/1.5m cap boundary.
- **Files modified:** `tests/test_calibration.py`
- **Verification:** All focused counterfactual tests and the complete 108-test calibration/replay/execution/risk suite pass.
- **Committed in:** `6961b9e`

---

**Total deviations:** 1 auto-fixed blocking fixture-selection issue.
**Impact on plan:** No production behavior or scope changed; the corrected fixture now actually exercises the planned exposure boundary.

## Issues Encountered

None after the fixture-boundary correction above.

## User Setup Required

None - evaluation and rendering are offline, advisory, and read-only.

## Next Phase Readiness

- Plan 10-03 can expose the report through a credential-free CLI using existing fixture and evidence paths.
- Plan 10-04 can bind promotion readiness to `calibration_id` without parsing human text.
- Phase 9 remains incomplete and promotion remains blocked; no runtime settings, environment, KIS state, or real-money mode changed.

## Self-Check: PASSED

- All five Task 1/2 commits exist and all planned files are present.
- The complete calibration unit/report suite passes: 26 tests.
- The specified calibration, replay, execution, and risk regression suite passes: 108 tests.
- Python byte compilation and `git diff --check` pass.
- Unrelated dirty source/test changes and debug notes were preserved and not staged.

---
*Phase: 10-advisory-risk-calibration-promotion-readiness*
*Completed: 2026-08-10*
