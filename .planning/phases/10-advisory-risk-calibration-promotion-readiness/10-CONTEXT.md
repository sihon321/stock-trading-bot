# Phase 10: Advisory Risk Calibration & Promotion Readiness - Context

**Gathered:** 2026-08-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Build read-only advisory calibration and promotion-readiness reporting from existing replay, audit, report, and KIS mock-soak evidence. Operators can compare one-at-a-time variants for confidence thresholds, maximum position value, stop-loss, and take-profit; see exposure and risk-trigger differences with explicit sample sufficiency; and obtain an evidence-bound `READY` or `BLOCKED` promotion assessment. This phase does not mutate runtime policy, enable real-money trading, waive Phase 9 evidence, claim profitability, add scheduling, or add a new strategy.

Phase 10 may proceed before Phase 9's 20 eligible-day acceptance is complete, but that sequencing exception applies only to advisory analysis. The incomplete and safety-failed Phase 9 campaign cannot be represented as passed and keeps real-money promotion `BLOCKED`.

</domain>

<decisions>
## Implementation Decisions

### Evidence and comparison design
- **D-01:** Use the available 10-day KIS mock sample for advisory analysis while displaying an explicit `INSUFFICIENT_EVIDENCE` warning. It is not sufficient evidence for real-money promotion.
- **D-02:** Include only normally completed cycles in policy comparisons. Reconciliation failures, ambiguous submissions, and other abnormal cycles remain visible in a separate risk-case section and cannot be silently folded into comparison denominators.
- **D-03:** Compare confidence thresholds `0.75`, `0.80`, and `0.85` without changing the active runtime threshold.
- **D-04:** Change one policy variable at a time. Do not generate combinatorial policy bundles from the small sample.
- **D-05:** Calibration is advisory and counterfactual only. No calibration, replay, report, or readiness command may write settings, environment files, promotion state, or broker-facing state.

### Risk-value candidates
- **D-06:** Compare maximum-position-value candidates of KRW `500,000`, `1,000,000`, and `1,500,000` around the current KRW `1,000,000` cap.
- **D-07:** Compare stop-loss candidates of `-3%`, `-5%`, and `-7%` around the current `-5%` threshold.
- **D-08:** Compare take-profit candidates of `+5%`, `+10%`, and `+15%` around the current `+10%` threshold.
- **D-09:** Vary BUY and SELL confidence thresholds independently so entry and exit effects remain attributable.
- **D-10:** Keep the current policy as the explicit baseline in every comparison and identify exactly one changed field for each variant.

### Result judgment
- **D-11:** Order advisory candidates by risk reduction first. Also show changes in trade opportunities, expected position exposure, and risk-trigger counts so the trade-off remains visible.
- **D-12:** With insufficient evidence, the highest-ranked result may be labeled only `PROVISIONAL_CANDIDATE`; it must not be rendered as a recommendation to apply.
- **D-13:** Show exact eligible sample counts, relevant event counts, baseline-relative change rates, and an evidence-sufficiency grade. Preserve explicit denominators and do not hide excluded or unknown evidence.
- **D-14:** When candidate differences are absent or below a clearly defined materiality rule, report `NO_MEANINGFUL_DIFFERENCE` and retain the current policy as the advisory outcome.
- **D-15:** Do not calculate or imply profitability, investment return, statistical certainty, or production readiness from this backtest-lite and short-soak evidence.

### Real-money promotion boundary
- **D-16:** Phase 10 advisory analysis can complete while Phase 9 remains incomplete, but promotion readiness must remain `BLOCKED` until the separately defined soak evidence and every other checklist gate are satisfied.
- **D-17:** An operator waiver cannot convert missing Phase 9 evidence or a safety-failed campaign into passing promotion evidence.
- **D-18:** The promotion checklist is read-only and may return only evidence-linked `READY` or `BLOCKED`. Any future `TRADING_MODE=real` change remains a separate manual action with explicit reconfirmation outside calibration and validation commands.
- **D-19:** Any currently unresolved or ambiguous order is a hard promotion blocker. Determinately resolved historical cases remain visible as warning history but do not create a permanent blocker by themselves.
- **D-20:** Bind every readiness result to complete evidence and policy snapshot identities. Any relevant policy, configuration, or evidence change invalidates the prior result and requires a fresh assessment.
- **D-21:** The checklist must cover replay verification, Phase 9 soak acceptance, daily/period reports, unresolved orders, policy freeze, rollback procedure, kill procedure, and explicit manual approval without acquiring authority to perform those actions.

### Agent Discretion
- Choose module, class, table, reason-code, and CLI subcommand names consistent with the existing Typer, frozen-dataclass, strict-schema, and deterministic rendering patterns.
- Define a deterministic materiality rule for `NO_MEANINGFUL_DIFFERENCE` and a bounded evidence-sufficiency grading scheme, provided the 10-day sample is always insufficient and exact counts remain visible.
- Choose the presentation order and Korean wording for advisory tables and checklist output, while preserving stable machine-readable English status/reason codes.
- Choose whether comparisons consume normalized audit rows directly or a dedicated immutable projection, provided inputs are read-only, provenance-preserving, and validated before comparison.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Milestone scope and requirements
- `.planning/PROJECT.md` — v1.1 goal, mock-first safety posture, advisory calibration target, and prohibition on automatic real-money promotion.
- `.planning/REQUIREMENTS.md` — CAL-01 through CAL-04 and the future-scope boundary excluding full portfolio profitability backtesting.
- `.planning/ROADMAP.md` — Phase 10 goal, dependency, success criteria, and intended execution order.
- `.planning/STATE.md` — Current milestone state, accumulated safety decisions, and the unresolved Phase 9 evidence concerns.

### Upstream evidence contracts
- `.planning/phases/06-audit-evidence-cycle-boundaries/06-CONTEXT.md` — normalized run, ticker, order, timing, freshness, and policy-snapshot evidence that calibration must preserve.
- `.planning/phases/07-deterministic-replay-validation/07-CONTEXT.md` — frozen deterministic replay identities, explicit denominators, and the non-profitability boundary.
- `.planning/phases/08-decision-reports-operator-runbook/08-CONTEXT.md` — read-only daily, period, and replay reporting plus manual operational and failure-triage contracts.
- `.planning/phases/09-kis-mock-soak-fault-drills/09-CONTEXT.md` — campaign accounting, irreversible safety failure, broker-truth reconciliation, ambiguity, and provenance separation.
- `.planning/phases/09-kis-mock-soak-fault-drills/09-07-SUMMARY.md` — shipped triple-store read-only reporting and the rule that Phase 10 cannot treat drill, synthetic, or ambiguous evidence as eligible soak credit.
- `.planning/phases/09-kis-mock-soak-fault-drills/09-08-PLAN.md` — unfulfilled human acceptance requiring 20 eligible days and zero safety breaches; this gate may not be reported as passed or waived.
- `docs/operator-runbook.md` — existing operator commands, evidence review order, freeze recovery, and real-money/policy-mutation prohibitions.

### Current failure investigation
- `.planning/debug/resolved/post-submission-reconcile.md` — cause and code correction for premature post-submission reconciliation; historical campaign evidence remains unchanged.
- `.planning/debug/kis-soak-query-unknown.md` — KIS soak query uncertainty relevant to evidence quality and warning presentation.
- `.planning/debug/kis-mock-balance-incomplete.md` — incomplete mock balance evidence relevant to readiness blockers.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `trading_bot/reporting.py`: read-only deterministic daily, period, and replay projections with exact-schema validation, explicit denominators, and stable text rendering.
- `trading_bot/replay.py`: immutable policy snapshots, canonical evidence hashing, normalized replay outcomes, action funnels, and a mandatory non-profitability disclaimer.
- `trading_bot/soak_reporting.py`: independently stable read-only views over primary audit, soak, and controller evidence; contradictory or missing cross-store evidence becomes `UNKNOWN`.
- `trading_bot/execution.py`: current BUY/SELL confidence and position-sizing policy path, including the configurable maximum-position-value cap.
- `trading_bot/risk.py`: deterministic stop-loss and take-profit decisions suitable for one-variable counterfactual evaluation.
- `trading_bot/config.py`: current baselines of BUY/SELL `0.80`, maximum position KRW `1,000,000`, stop-loss `5%`, and take-profit `10%`.

### Established Patterns
- Read-only inspection must not construct KIS, LLM, market-data, or order collaborators and must never create a missing evidence database.
- Inputs and outputs use exact schemas, stable identities, canonical hashes, frozen dataclasses, and deterministic ordering.
- Missing, contradictory, or unsupported evidence fails closed as `UNKNOWN` or `BLOCKED`; it is never omitted or upgraded to success.
- Synthetic, controlled-injection, KIS-observed, replay, eligible-day, and availability evidence retain separate provenance and denominators.
- Replay and reports explicitly state that policy-path validation is not a profitability estimate.

### Integration Points
- Extend the Typer CLI near existing `report`, `replay`, and `soak status` read-only commands without adding a settings-write or broker-capable path.
- Consume normalized audit/replay/soak projections and complete policy snapshots rather than raw KIS responses or mutable runtime objects.
- Reuse execution sizing and risk-decision semantics for counterfactual calculation, but isolate them from live order submission.
- Persist or render readiness snapshot identity so policy/evidence changes can deterministically invalidate a prior assessment.

</code_context>

<specifics>
## Specific Ideas

- Every comparison row should identify the baseline value, candidate value, exactly one changed policy field, eligible denominator, excluded/unknown count, trigger/action difference, and exposure difference.
- The short-sample banner and machine-readable status should remain visible even when a provisional candidate ranks first.
- Promotion readiness should clearly distinguish `ADVISORY_ANALYSIS_COMPLETE` from `REAL_MONEY_PROMOTION_BLOCKED` so completing Phase 10 cannot be mistaken for live-trading approval.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within Phase 10. Full portfolio profitability backtesting, automatic policy application, scheduling, and new trading strategies remain future or prohibited scope.

</deferred>

---

*Phase: 10-advisory-risk-calibration-promotion-readiness*
*Context gathered: 2026-08-10*
