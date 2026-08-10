# Phase 10: Advisory Risk Calibration & Promotion Readiness - Research

**Researched:** 2026-08-10
**Domain:** Read-only counterfactual policy comparison, short-sample evidence grading, and evidence-bound promotion readiness
**Confidence:** HIGH for repository architecture; MEDIUM for conclusions drawn from the current 10-day mock sample

<user_constraints>
## User Constraints (from CONTEXT.md)

- Use the available 10-day KIS mock sample for analysis, but always label it insufficient and never treat it as real-money promotion evidence.
- Compare only normally completed cycles; show reconciliation failures and ambiguous orders separately as risk cases.
- Compare one field at a time: BUY/SELL confidence `0.75/0.80/0.85`, maximum position KRW `500,000/1,000,000/1,500,000`, stop-loss `3%/5%/7%`, and take-profit `5%/10%/15%`.
- Rank by risk reduction, show opportunity/exposure differences, use `PROVISIONAL_CANDIDATE` only, and retain current policy on no meaningful difference.
- Phase 10 may complete advisory analysis before Phase 9, but real-money promotion remains `BLOCKED`; no operator waiver converts missing or failed soak evidence into passing evidence.
- Calibration and readiness commands are read-only and cannot mutate settings, environment files, broker state, or promotion state.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Planning implication |
|----|----------------------|
| CAL-01 | A deterministic advisory engine and report must compare all locked candidates while changing exactly one field from the baseline. |
| CAL-02 | Every result needs exact eligible/excluded/unknown counts, evidence grade, exposure/action/trigger deltas, and an insufficient-evidence warning. |
| CAL-03 | A separate evidence-bound readiness checklist must cover replay, soak, reports, unresolved orders, policy freeze, rollback, kill procedure, and explicit manual approval. |
| CAL-04 | CLI composition and tests must prove that calibration/readiness construct no KIS, LLM, market-data, order, full `Settings`, or mutable storage collaborator and expose no automatic configuration or real-mode mutation. |
</phase_requirements>

## Summary

Phase 10 should extend the existing read-only reporting architecture, not the trading runtime. The safest design has two separate projections:

1. A calibration projection reruns frozen replay scenarios under one-field policy variants and combines those deterministic results with mock-soak evidence-quality counts and abnormal risk cases.
2. A promotion-readiness projection consumes verified replay/report/soak/calibration facts and produces an ephemeral, snapshot-hashed `READY` or `BLOCKED` checklist without changing any setting.

The audit database alone cannot truthfully recompute every requested policy. It records decision confidence, current price, requested/filled quantity, and a flat policy snapshot, but it does not retain a complete per-cycle initial portfolio, available cash, or held-position average price. Maximum-position, stop-loss, and take-profit counterfactuals therefore require the frozen replay fixtures, which do contain initial cash, positions with average prices, current prices, policy, and raw signals. The 10-day mock evidence remains useful for eligible normal-cycle counts, observed confidence/action/risk-trigger frequencies, reconciliation failures, ambiguous orders, and readiness blocking, but it must not be used to invent missing counterfactual state.

**Primary recommendation:** create a new credential-free `calibration.py` domain, a deterministic `calibration_reporting.py` projection, and a `promotion_readiness.py` checklist service. Register `bot report calibration` and `bot report readiness` in the existing nested report app. Reuse strict file/SQLite validation, canonical hashing, exact denominators, deterministic rendering, and conflict-safe output from replay/reporting/soak reporting.

## Verified Existing Assets

| Asset | Reuse in Phase 10 |
|-------|-------------------|
| `trading_bot/replay.py` | `load_replay_bundle`, `run_replay_scenarios`, frozen scenarios, complete initial state, canonical JSON, and non-profitability disclaimer. |
| `trading_bot/execution.py` | Production confidence thresholds and maximum-position sizing semantics. |
| `trading_bot/risk.py` | Production stop-loss/take-profit semantics against average price. |
| `trading_bot/reporting.py` | URI `mode=ro`, `query_only`, exact schema checks, explicit denominators, replay identity verification, and deterministic text reports. |
| `trading_bot/soak_reporting.py` | Independent stable reads across primary/soak/controller stores, eligible-day accounting, permanent safety latch, active freezes, and `UNKNOWN` downgrade. |
| `trading_bot/report_cli.py` | Credential-free nested Typer app, bounded diagnostics, terminal/file byte identity, atomic conflict-safe output. |
| `trading_bot/config.py` | Current baseline values and the narrow `ReportSettings` pattern; calibration must not construct full credential-bearing `Settings`. |

## Evidence Architecture

### Calibration source separation

| Source | May support | Must not support |
|--------|-------------|------------------|
| Frozen replay fixtures | One-field counterfactual actions, order eligibility, quantity/exposure, stop/take triggers | Profitability claims or live broker behavior |
| Normal completed mock cycles | Eligible sample count, observed signal/confidence/action/trigger frequencies | Missing cash/average-price counterfactuals |
| Abnormal/failed mock cycles | Risk-case inventory and readiness blockers | Normal comparison denominator or policy ranking |
| Soak/controller evidence | Campaign progress, safety latch, reconciliation, freezes, drill provenance | Synthetic-to-eligible credit substitution |

Each report must state denominators independently. A variant can have a replay-evaluable count, an observed normal-cycle count, excluded abnormal count, and unknown count; these values cannot be merged into a single unlabeled sample size.

### Candidate catalog

Use one immutable catalog with the current baseline:

- `buy_confidence_threshold`: `0.75`, `0.80` baseline, `0.85`
- `sell_confidence_threshold`: `0.75`, `0.80` baseline, `0.85`
- `max_position_value`: `500000`, `1000000` baseline, `1500000`
- `stop_loss_pct`: `0.03`, `0.05` baseline, `0.07`
- `take_profit_pct`: `0.05`, `0.10` baseline, `0.15`

Every `PolicyVariant` must contain exactly one changed field or represent the baseline. Validate finite positive values, supported field names, and baseline equality before running scenarios.

### Metrics and judgment

Per variant, compute deterministic counts from normalized outcomes: BUY/HOLD/SELL, order-eligible, low-confidence block, risk block, stop-loss trigger, take-profit trigger, and estimated end-of-step exposure. Exposure is a policy-path comparison only and must be derived from replay position quantity and fixture current price; it is not P&L.

Rank risk-first using observable quantities rather than a hidden composite score. A suitable deterministic order is: fewer risk-triggered/blocked unsafe opportunities, lower exposure, then no increase in order eligibility; always display all dimensions. Define a documented materiality rule and return `NO_MEANINGFUL_DIFFERENCE` when the leader does not cross it. Since the observed mock sample has fewer than 20 eligible days, the highest-ranked changed variant can be only `PROVISIONAL_CANDIDATE`, never `RECOMMENDED`.

### Evidence sufficiency

Use stable grades, for example `INSUFFICIENT`, `LIMITED`, and `SUFFICIENT`, but lock the current 10-day campaign to `INSUFFICIENT`. Grade from eligible normal days and evidence integrity, not raw row count. Any permanent safety latch, active freeze, incomplete reconciliation, or contradictory cross-store reference prevents `SUFFICIENT` even if the numerical day count is large.

## Promotion Readiness Architecture

`promotion_readiness.py` should be a pure reducer over immutable normalized inputs. It returns checklist items with stable codes, evidence references, `PASS/BLOCK/UNKNOWN`, and a final `READY/BLOCKED`. Any `BLOCK` or `UNKNOWN` makes the result `BLOCKED`.

Required gates:

1. Replay results identity-valid and verification-passed.
2. Phase 9 target reached with zero permanent safety breach; current incomplete/failed campaign therefore blocks.
3. Daily/period evidence complete and unknown-free for the reviewed interval.
4. No active unresolved/ambiguous order or ticker freeze.
5. Calibration report exists, is snapshot-valid, and does not claim sufficient evidence from 10 days.
6. Policy-freeze snapshot is explicit and matches the calibration baseline.
7. Rollback and kill procedures are present and operator-acknowledged.
8. Explicit manual approval is present only after all objective gates pass.

The reducer computes a canonical SHA-256 identity over all normalized checklist facts, source identities, policy snapshot, and acknowledgements. It does not persist READY. Any new evidence or policy produces a different identity and requires a fresh invocation.

## CLI Boundary

Recommended commands:

- `bot report calibration REPLAY_FIXTURE... --audit-db PATH --soak-db PATH --campaign-id ID [--output PATH]`
- `bot report readiness REPLAY_RESULT... --audit-db PATH --soak-db PATH --controller-db PATH --campaign-id ID --policy-snapshot PATH --rollback-ack --kill-ack --manual-approval [--output PATH]`

Exact spelling remains implementation discretion, but the commands must use narrow credential-free settings/arguments, read only existing regular files, and never import or call `build_runtime`, `Settings`, KIS adapters, LLM providers, brokers, order ports, or writable database connectors. Output uses the existing `_deliver()` path.

## Failure Modes and Mitigations

| Failure mode | Required mitigation |
|--------------|---------------------|
| Audit rows lack average price/cash | Mark counterfactual dimension unevaluable; use replay fixtures rather than inference. |
| Variant changes multiple fields | Reject the variant before execution. |
| Replay input identity/schema differs | Separate or reject incompatible groups; do not aggregate. |
| Abnormal mock cycle enters normal denominator | Exact state filter plus explicit excluded-risk-case count and tests. |
| Phase 9 missing/failed but checklist says READY | Hard-coded evidence gate and regression fixture for the current campaign shape. |
| Old READY reused after evidence/config change | Canonical snapshot identity changes; no persistent mutable READY state exists. |
| CLI accidentally constructs live runtime | Monkeypatch constructors to fail and assert calibration/readiness still run; static import/command-contract tests. |
| Report implies returns | Mandatory non-profitability/advisory disclaimer in every renderer and saved file. |

## Validation Architecture

Use existing `pytest` and `CliRunner`; no new dependency is required.

- Unit-test candidate catalog, one-field invariant, counterfactual determinism, exact denominators, exposure/trigger deltas, materiality, and evidence grades.
- Integration-test read-only SQLite/fixture inputs with before/after bytes and missing/unsupported schema failures.
- CLI-test credential-free construction, bounded diagnostics, deterministic terminal/file bytes, and absence of broker/settings mutation.
- Readiness-test every checklist gate independently, all `UNKNOWN` fail-closed behavior, current Phase 9 incomplete/failed evidence, resolved historical ambiguity warnings, active ambiguity blockers, and snapshot invalidation.
- Contract-test operator runbook commands, explicit manual separation, rollback/kill acknowledgements, and prohibitions on policy writes/real enablement.
- Run the focused Phase 10 suite after every task and the repository suite after each plan wave. The pre-existing `tests/test_soak_campaign.py` collection defect must be reported separately if still present; Phase 10 must not hide it by weakening test selection.

## Planning Recommendation

Plan in four sequential waves:

1. Strict calibration evidence models, catalog, and read-only source projection.
2. Deterministic one-field counterfactual engine, result judgment, and renderer.
3. Credential-free calibration CLI and output safety.
4. Snapshot-bound promotion checklist, readiness CLI, runbook contract, and full CAL-01..04 verification.

No schema push, new package, web UI, scheduler, broker call, automatic settings write, or real-money action belongs in this phase.

