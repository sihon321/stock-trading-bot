---
phase: 13-historical-llm-shadow-evaluation-model-governance
verified: 2026-10-01T12:11:21.854136+00:00
status: passed
score: 20/20 must-haves verified
behavior_unverified: 0
requirements: [FUT-02, GOV-01]
method: inline
---

# Phase 13 Verification Report

**Status: passed for implementation and controlled-fixture behavior.** Seven plans / fourteen tasks completed. No paid LLM or KIS request, actual invoice experiment, model-quality claim or real-money approval was performed. Inline execution/verification follows the Codex skill adapter; independent-agent review was not run.

Goal: compare frozen fixture signals with optional historical LLM observations under bounded, attributable shadow execution while keeping canonical replay immutable and denying trade/policy authority.

## Observable Truths

| ID | Truth | Result | Evidence |
|---|---|---|---|
| G-1 | Explicit budgets, concurrency, resumable checkpoints and no mutation authority | VERIFIED | shadow budget/store/runner tests; CLI capability tripwires; all paid profiles validated before credential construction |
| G-2 | Each result binds all input/provider/model/prompt/schema/cost/code/validation facts | VERIFIED | Frozen manifest embeds bundle, baseline and news; observation/journal hashes; validated replay and result metrics |
| G-3 | Reports compare raw agreement and hypothetical shipped gates without replacing baseline | VERIFIED | compare_shadow_action calls project_backtest_action; strict valid-pair matrix, confidence/action/quantity/risk and failure denominators |
| G-4 | Model/prompt adoption remains a separate manual decision | VERIFIED | No policy mutator/broker/worker; Korean advisory labels, null alternative-portfolio PnL and promotion_authority=false |
| D-01 | Bounded representative sample; frozen seed/algorithm and missing strata | VERIFIED | test_sampling_is_order_independent_and_paired; test_sampling_spreads_periods_and_tickers_before_reusing_groups; _coverage records missing decision/position/risk/period strata |
| D-02 | Time-visible required facts and optional historical news, without current queries | VERIFIED | test_future_news_is_omitted_and_historical_news_is_untrusted; test_future_action_does_not_change_earlier_inputs; test_missing_held_price_is_explicit; Phase12 raw/adjusted cutoff regression |
| D-03 | Same canonical pre-decision state and immutable fixture baseline | VERIFIED | test_observer_preserves_exact_replay_and_reservations; test_baseline_reconciles_and_is_immutable; test_rehashed_snapshot_fabrication_is_rejected_before_paid_call |
| D-04 | Frozen sources and visible coverage/news/hindsight limits | VERIFIED | Embedded bundle_document_json/news_document_json/baseline_document_json; source hashes; _coverage and Korean CURRENT_MODEL_HINDSIGHT_CONTAMINATION labels |
| D-05 | Explicit paired models; default one observation, no optimization | VERIFIED | test_paired_inputs_and_bounded_concurrency; explicit variant file; default limits/repetitions; documented shipped prompt extraction |
| D-06 | Frozen actual prompts/schema/settings and separate unknown/returned model facts | VERIFIED | test_one_sdk_request_preserves_usage; test_claude_forced_tool_and_inclusive_usage; positive reviewed API capability fields; strict shipped schema |
| D-07 | Failures remain distinct from successful HOLD | VERIFIED | model failed-outcome tests; provider success/malformed/truncation/refusal/timeout/500 tests; report invalid-fixture and zero-pair assertions |
| D-08 | LLM-only credentials, no broker/live write/lease/subprocess authority | VERIFIED | test_only_dedicated_credentials_and_no_live_settings; test_unsupported_cli_and_synthetic_profile_before_credentials; test_prepare_and_standalone_report_have_no_live_capabilities; test_foreign_journal_and_live_write_tripwires |
| D-09 | Shared default and override caps across variants/repetitions/retries | VERIFIED | test_exact_cap_and_next_call_blocked; test_group_budget_stops_calls; test_paired_group_all_or_none_and_unknown_retained; concurrency=2 evidence |
| D-10 | Sound reservations; unknowns retained; native/estimated/billed costs distinct | VERIFIED | test_subdivisions_and_unclipped_breach; test_unknown_returned_model_and_native_currency_are_explicit; test_breach_preserves_actual_tokens_and_halts |
| D-11 | One generation, no hidden retries or automatic uncertain replay | VERIFIED | test_no_hidden_retry_on_failure; test_crash_after_intent_does_not_automatically_repeat; explicit linked retry retains original observation/reservation |
| D-12 | Durable owned journal, same frozen resume, safe interruption | VERIFIED | test_owner_conflict_recovery_and_no_repeated_logical_dispatch; test_crash_after_observation_retains_finalized_output; test_interrupt_stops_new_units_and_code_mismatch_is_local; relative journal resume |
| D-13 | Validated JSON/Korean counts, matrix, confidence/actions/risk/cost facts | VERIFIED | reporting exact-denominator and unknown-cost tests; standalone and installed report smoke; outcome partitions and rare risk counts |
| D-14 | Shared read-only policy gates; malformed precedes risk; no alternate portfolio | VERIFIED | test_confidence_gate_and_risk_share_canonical_projection; test_raw_agreement_exact_denominators_and_no_mutation; Phase12 reservation/partial/corporate-action/T+2 regression |
| D-15 | Consistency only; insufficient default, exact equality rule, no automatic winner | VERIFIED | _metrics judgment rule and Korean report; no accuracy/profitability/calibration/readiness claim; promotion_authority=false |
| D-16 | Immutable evidence, code/attempt links, reproducible report and manual boundary | VERIFIED | test_saved_result_recomputed_and_outputs_are_idempotent; test_final_observation_reused_and_cache_tamper_rejected; test_linked_changed_spec_retains_parent_identity; code mismatch and output conflict tests |

## Artifact Wiring

- shadow_models: strict frozen manifests, full source/baseline/news documents, generation/pricing/capability envelopes, distinct observations and result IDs.
- backtest_engine/backtest_ledger: immutable pre-decision observer and shared project_backtest_action/project_reservation. Existing replay evidence is unchanged with observer on/off.
- shadow_inputs: historical rendering, simulated held context, escaped untrusted news, period/category/ticker rotation, sampled IDs, source/code identities and semantic baseline reconciliation. Validation replays the embedded frozen source to reject rehashed fabricated snapshots.
- shadow_budget/shadow_store: documented input-context plus enforced output bound, shared whole-group cap check, native FX facts, retained uncertainties/breaches; dedicated marker DB, append sequence/hash validation, exclusive flock and immutable finalized attempts. HTTP runs outside SQLite transactions.
- shadow_providers: pinned official SDK create calls, no parse/repair that discards usage, retry=0, timeout=60, official HTTPS origins, no environment proxy/redirect/compressed payload, bounded serialized request/body/raw response. Codex CLI and documented incompatible Claude forced-tool families fail before credentials/process/network.
- shadow_runner: deterministic paired schedule, concurrency 1–4, intent before dispatch, finalized outcome settlement, interruption/recovery and explicit retry; same content hash required on resume. Evidence capacity is checked before credentials/calls.
- shadow_reporting: validated append transitions/cardinality/charges and derived metrics; strict valid pair versus attempted denominators; deterministic Korean report, honest UNKNOWN/ESTIMATED/bill facts and exact-equality-only advisory grade. No alternate portfolio return path or automatic model selection.
- shadow_cli/cli/report_cli: prepare/run/resume/retry and standalone offline report commands. Live dotenv loading moved to the live-command callback; shadow, report and backtest do not load credentials from .env. Destination checks and atomic no-overwrite evidence publishing.
- docs/shadow-evaluation-runbook.md + README.md: all five operator workflows, reviewed capabilities/price/context/FX requirements, conservative caps and uncertainties, dedicated credentials, linked new runs and unchanged manual promotion gates.

## Automated Evidence

Final command: `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q`

**986 passed in 36.22s**: all prior 905 cases, one added backtest observer case, and 80 shadow cases. No regression, failure or skip in the final full run. Initial full run before the last API-capability guard had 983 passing cases; new guards were revalidated in the final full run.

| Shadow module | Cases passed in final full run |
|---|---:|
| tests/test_shadow_models.py | 25 |
| tests/test_shadow_inputs.py | 9 |
| tests/test_shadow_budget.py | 5 |
| tests/test_shadow_store.py | 4 |
| tests/test_shadow_providers.py | 15 |
| tests/test_shadow_runner.py | 9 |
| tests/test_shadow_reporting.py | 7 |
| tests/test_shadow_cli.py | 6 |

All eight existing backtest modules remain green: 78 cases (77 prior + one observer test). Last standalone combined wave check before the final six additional model/provider guards: 152 passed in 15.98s; the final full run covers all 158 current shadow/backtest cases.

Task verifications and their original measured counts are recorded in seven committed SUMMARY files and 13-VALIDATION.md. Final focused model/provider/CLI guard check: 46 passed in 6.17s. Final exact CLI task command: 6 passed in 3.78s.

Installed console-script smoke: `.python-userbase/bin/bot shadow prepare ...` and `bot report shadow ...` executed from an outside temporary directory with credential variables removed. Both exit 0; rendered stdout matches report bytes. Dedicated setuptools build runtime and editable console script installed locally under the existing userbase; pinned application dependencies unchanged.

Schema-drift gate: block=false, no ORM/schema drift. Codebase-drift advisory: skipped because no STRUCTURE.md. execute:post/verify:post hooks are inactive; source and adversarial checks performed inline. `git diff --check` passes.

## Requirement Traceability

- **FUT-02 VERIFIED:** Optional historical provider comparison is exposed separately from canonical replay. Explicit reviewed profiles and dedicated credentials are required for future paid use; fake APIs prove bounded scheduling, recovery and comparisons without paid testing.
- **GOV-01 VERIFIED:** Every dispatched observation joins a frozen spec/run/unit/variant/snapshot/attempt and provider/model/prompt/schema/pricing/code content; journal and report readers revalidate attribution. No shadow path instantiates mutation/trading capabilities; adoption remains manual.

## Findings Resolved During Integration

1. Handle fake pre-buffered HTTP responses within the same byte limit; reject real compressed responses before decompression and cap serialized request size before dispatch.
2. Preserve full input bundle/news to replay and validate snapshot/cash/prompt/sample facts rather than trust only a rehashed manifest; include missing observations/strata and fair period/ticker allocation.
3. Retain bounds for unknown returned models; disclose native FX estimates and real bill facts, recording overages without clipping.
4. Resolve relative journal and repository-independent Git provenance; keep original baseline code facts while rejecting actual semantic/window mismatches.
5. Guard evidence capacity before calls so a bounded result can be saved; add parent spec/run links for changed conditions.
6. Validate shipped strict schema and positively reviewed API capabilities; current Claude forced-tool limitations are rejected before credentials, never silently substituted.
7. Remove global dotenv loading from offline command import; retain legacy live-command loading through the root callback.

## Practical Limits / Optional Operator Work

- No actual model/rate is selected or asserted. A future paid invocation needs operator-reviewed dated official model/endpoint/context/pricing/capability records and dedicated keys. Official SDK contracts were inspected locally and the current Claude tool-choice limits checked in [official docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/define-tools#forcing-tool-use). OpenAI contract reference: [Chat Completions create](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create).
- Whole model-context reservations and evidence byte limits may stop a run much earlier than 100 samples. USD5 limits modeled spend, not a proven invoice. Timeout/owner-ended intents retain full upper bounds; a stored intent is not proof that the server executed or charged a request.
- Outputs remain observed randomness; only report regeneration is deterministic. Present-day model hindsight, synthetic historical rules and incomplete coverage stay visible. Agreement is not accuracy, profitability or readiness.
- Phase9 elapsed-day acceptance remains outstanding and independent. Phase11 authenticated UAT retains its recorded pass (11-UAT.md, 2026-09-07); its operational gates and Phase10 promotion requirements remain in effect. Phase13 completion does not resolve Phase9 or relax these gates. No human/paid acceptance is required for this phase's implementation scope.

## Self-Check

Seven plan structures and committed summaries exist; twenty goal/decision truths and both requirement IDs traced; substantive source links exercised; actual final suite passed. No unresolved implementation findings.
