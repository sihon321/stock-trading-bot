---
phase: 12-full-portfolio-backtesting-market-friction-modeling
verified: 2026-10-01T07:02:20.050867+00:00
status: passed
score: 20/20 must-haves verified
behavior_unverified: 0
requirements: [FUT-01]
method: inline
---

# Phase 12 Verification Report

Phase goal: measure chronological portfolio behavior and KR market friction offline, with repeatable evidence and honest modeling limits.

Status: **passed**. Six plans/twelve tasks completed. Verification is implementation/controlled-fixture evidence; no complete real three-year historical performance claim or real-account approval was made.

## Observable Truths

| # | Truth | Status | Evidence |
|---|---|---|---|
| G-1 | Multi-ticker shared capital/holdings prevent impossible overlap | VERIFIED | Ledger reservation/oversell/partial/T+2 tests and engine account continuity |
| G-2 | Fill, fee, tax, slippage, liquidity and partial assumptions are versioned | VERIFIED | Strict dated rules, profile manifest, component tests and report labels |
| G-3 | Same inputs reproduce trades/curves/exposure/ID without look-ahead | VERIFIED | Shuffled-input/path comparison, cutoff/future-action perturbations and saved ledger replay |
| G-4 | Gross/net are separated and modeled limitations are explicit | VERIFIED | Same-path cost attribution, Korean report and incomplete-evidence assertions |
| D-01 | Frozen three-year requested coverage, leap day, explicit intervals and warm-up | VERIFIED | tests/test_backtest_inputs.py#test_default_three_years_is_not_silently_shortened; test_leap_day_default; test_complete_short_window_needs_reviewed_rules_and_warmup |
| D-02 | Frozen point-in-time ordinary KR equities and credential-free capabilities | VERIFIED | tests/test_backtest_inputs.py#test_held_union_late_signal_and_unknown_price; tests/test_backtest_cli.py#test_offline_run_and_saved_report_without_credentials; decision_view source cutoff |
| D-03 | Raw execution prices, known adjustment events and missing/corporate-action evidence | VERIFIED | tests/test_backtest_inputs.py#test_point_in_time_future_mutation_and_raw_adjustment_separation; tests/test_backtest_ledger.py#test_split_conserves_cost_basis_and_dividend_payable_timing; test_unresolved_delist_preserves_inventory_and_unknown_valuation |
| D-04 | Frozen strict signals and shipped policy gates | VERIFIED | tests/test_backtest_engine.py#test_missing_malformed_and_confidence_safe_hold; test_low_confidence_signals_cannot_buy |
| D-05 | Decision-close intents cannot fill on the same session | VERIFIED | tests/test_backtest_fills.py#test_no_same_session_fill_and_no_range_touch_fiction; tests/test_backtest_e2e.py#test_risk_exit_is_next_session_and_no_same_day_sale_funding |
| D-06 | One shared reserved account, held-first review and no cash/inventory reuse | VERIFIED | tests/test_backtest_ledger.py#test_cash_reservation_prevents_two_tickers_sharing_capital; test_no_oversell_or_duplicate_reservation; engine held-first order |
| D-07 | Side-aware date-effective opening limits, no range-touch or lock fiction | VERIFIED | tests/test_backtest_costs.py#test_tick_cross_band_side_aware_rounding; tests/test_backtest_fills.py#test_no_same_session_fill_and_no_range_touch_fiction; test_no_unproven_volume_or_limit_lock |
| D-08 | Aggregate ticker/session participation, partial fill and expiry | VERIFIED | tests/test_backtest_fills.py#test_aggregate_partial_capacity_and_stable_allocation; tests/test_backtest_ledger.py#test_partial_fill_then_expiry_releases_remainder_once |
| D-09 | Separated settled/reserved/pending cash and conservative T+2 sessions | VERIFIED | tests/test_backtest_ledger.py#test_sale_proceeds_T_plus_two_holiday_not_calendar_days; tests/test_backtest_e2e.py#test_risk_exit_is_next_session_and_no_same_day_sale_funding |
| D-10 | Daily-close held risk and exact shipped parser/risk precedence | VERIFIED | tests/test_backtest_engine.py#test_existing_daily_risk_override_valid_signal; test_malformed_held_signal_does_not_bypass_shipped_parse_failure_order; execute_signal_cycle dry-run wiring |
| D-11 | Reviewed source metadata, date-effective tax/tick rules and historical gaps rejected | VERIFIED | tests/test_backtest_costs.py#test_effective_boundary_and_future_fact; test_later_curation_review_does_not_rewrite_historical_fact_availability; test_cost_components_and_assumptions |
| D-12 | Labeled baseline/stress assumptions and deterministic Decimal rounding | VERIFIED | tests/test_backtest_costs.py#test_cost_components_and_assumptions; tests/test_backtest_engine.py#test_canonical_decimal_spelling_is_normalized |
| D-13 | Same net quantity/timing gross attribution; linked independent stress run | VERIFIED | tests/test_backtest_engine.py#test_gross_attribution_reconciles_same_fill_path; test_equivalent_ordered_inputs_and_independent_profiles |
| D-14 | Korean coverage/curves/drawdown/exposure/turnover/cost reporting and optional index | VERIFIED | tests/test_backtest_reporting.py#test_korean_report_has_metrics_unknown_benchmark_and_limitations; test_hand_calculated_metrics_and_same_path_cost_drag; test_frozen_same_period_benchmark_and_future_benchmark_rejection |
| D-15 | Normalized input/code/policy identities exclude time/path and guard future information | VERIFIED | tests/test_backtest_e2e.py#test_end_to_end_baseline_stress_and_output_location_independence; tests/test_backtest_engine.py#test_future_retroactive_action_does_not_leak_into_prior_decisions |
| D-16 | Credential-free offline CLI, saved-evidence revalidation and conflict-safe publication | VERIFIED | tests/test_backtest_cli.py#test_offline_run_and_saved_report_without_credentials; test_output_conflict_preserves_existing_file; tests/test_backtest_reporting.py#test_tampered_or_forged_evidence_rejected; test_report_output_uses_atomic_conflict_safe_publish |

## Artifacts and Wiring

- backtest_models/backtest_inputs: substantive strict file schema, bounded loader, explicit requested/actual/warm-up interval and availability views.
- backtest_costs/backtest_fills: substantive reviewed-rule lookup, band-aware tick grid, modeled charges and aggregate opening capacity.
- backtest_ledger/backtest_engine: persistent Decimal accounting, cash/inventory reservations, exchange-session settlement, corporate actions, production indicators/screener/execute_signal_cycle dry-run integration and deterministic intent IDs.
- backtest_reporting: reconstructs ledger transitions, validates hash/rule/cost/quantity/initial-equity/benchmark/metrics, calculates gross/net and writes safe JSON/text.
- backtest_cli + cli/report_cli registration: installed `bot backtest run` and `bot report backtest` surfaces exercised without runtime/network/store capabilities.
- docs/operator-runbook.md: executable commands, strict bundle requirements, assumptions, formulas and complete/incomplete semantics.
- Eight substantive test modules and synthetic chronological fixture; all six PLAN artifacts have committed SUMMARY files.

Key links are exercised end-to-end from bundle → production pure decisions → reserved ledger → next-session fills → saved evidence → Korean report. Existing replay/live behavior remains covered by all prior 828 tests.

## Automated Checks

| Test file | Cases passed |
|---|---:|
| tests/test_backtest_inputs.py | 21 |
| tests/test_backtest_costs.py | 8 |
| tests/test_backtest_fills.py | 5 |
| tests/test_backtest_ledger.py | 9 |
| tests/test_backtest_engine.py | 13 |
| tests/test_backtest_reporting.py | 14 |
| tests/test_backtest_cli.py | 3 |
| tests/test_backtest_e2e.py | 4 |

- `.venv/bin/python -m pytest -q tests/test_backtest_*.py`: **77 passed in 4.00s**.
- `.venv/bin/python -m pytest -q`: **905 passed in 24.44s**, including prior 828 tests; zero regressions.
- Installed-entrypoint smoke: `bot backtest run ... --start 2023-01-09 --end 2023-01-20` saved ten simulated sessions/three fills; `bot report backtest` reloaded it. Report stdout and file match byte-for-byte (`cmp`). Synthetic fixture verdict was correctly INCOMPLETE. Temporary smoke artifacts used /private/tmp because macOS /tmp is a symlink and unsafe output paths are rejected.
- Decision-plan coverage gate: 16/16. All task/wave checks passed before proceeding.
- Schema-drift gate: no drift, no ORM migrations. Codebase-drift advisory skipped because no STRUCTURE.md. execute:post/verify:post contain no active review/gate hooks; final code examination was performed inline.
- `git diff --check`: pass.

## Findings Resolved During Integration

1. Require positive liquidity floor, matching production screener division; widen bounded Decimal precision for computed averages and normalize equivalent decimal spellings.
2. Persist original intents, calendar, corporate actions and rules so saved evidence can replay cash/share transitions rather than trusting only its hash.
3. Separate retrospective curation reviewed_at from historical rule known_at. Only fact availability constrains historical lookup.
4. Prevent not-yet-known retroactive actions from contaminating earlier decisions; make historical price gaps visible.
5. Settle explicitly payable delisting cash after the same-session corporate event; do not apply pre-initial-state splits twice or guess prior dividend entitlements.
6. Require initial position knowledge before the first opening opportunity; independently reconcile initial equity/marks.
7. Revalidate benchmark availability and report zero terminal equity as total modeled loss, rather than missing data.
8. Publish both JSON and backtest text with atomic no-overwrite semantics, including concurrent conflict checks.

All fixes have targeted passing assertions. No TODO/stub blocks remain in phase deliverables; the offline broker's submission prohibition is intentional enforcement and production decisions use dry_run.

## Requirement Traceability

FUT-01 is delivered by all six plans and the input→ledger→report offline flow. D-01–D-16 retain accepted recommendations. Deferred historical live LLM, dashboard, scheduling and real-money work was not introduced.

## Threat Mitigation

T-12-01: cutoff-safe observations, future-action/volume perturbation and benchmark availability tests.
T-12-02: Decimal cash/share reservations, duplicate-fill/oversell rejection and replay reconciliation.
T-12-03: strict/bounded/sanitized inputs, forged metric/cash/quantity rejection and conflict-safe outputs.
T-12-04: CLI settings/network/SQLite tripwires, forbidden policy broker submission and modeled-only report labels.

## Human Verification and Limits

No human step is required to validate this offline implementation. Real-history data/source/dated tax/tick curation remains an operator evidence prerequisite, not a claim fulfilled by synthetic fixtures. Daily OHLCV cannot prove queue priority or intraday risk execution; participation and settlement are declared model assumptions. Phase 9 elapsed-day external KIS acceptance and Phase 11 authenticated portfolio UAT remain separate work.
