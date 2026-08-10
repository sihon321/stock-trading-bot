# Phase 10: Advisory Risk Calibration & Promotion Readiness - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-08-10
**Phase:** 10-advisory-risk-calibration-promotion-readiness
**Areas discussed:** Evidence and comparison design, Risk-value candidates, Result judgment, Real-money promotion boundary

---

## Evidence and comparison design

### Available 10-day sample

| Option | Description | Selected |
|--------|-------------|----------|
| Analyze with warning | Use the sample while retaining an insufficient-evidence warning and excluding it from promotion proof. | ✓ |
| Treat as sufficient | Treat 10 days as enough evidence. | |
| Combine replay history | Expand the sample with historical replay data. | |
| Other | Use another evidence rule. | |

**User's choice:** Analyze with warning.
**Notes:** The user wants Phase 10 to proceed now rather than wait for 20 elapsed eligible days.

### Failed-campaign data

| Option | Description | Selected |
|--------|-------------|----------|
| Separate abnormal cases | Compare only normally completed cycles and analyze reconciliation failures and ambiguous orders separately. | ✓ |
| Include all rows | Include all data regardless of failure state. | |
| Exclude campaign | Exclude the entire failed campaign and use replay only. | |
| Other | Use another denominator rule. | |

**User's choice:** Separate abnormal cases.
**Notes:** Failed and ambiguous evidence must remain visible without contaminating normal-cycle comparisons.

### Confidence candidates

| Option | Description | Selected |
|--------|-------------|----------|
| 0.75 / 0.80 / 0.85 | Compare the current value and symmetric neighboring candidates. | ✓ |
| 0.80 / 0.85 / 0.90 | Compare only conservative candidates. | |
| 0.80 only | Keep the current threshold and vary other policy fields. | |
| Other | Use another range. | |

**User's choice:** `0.75 / 0.80 / 0.85`.
**Notes:** All candidates are advisory; runtime remains unchanged.

### Variant isolation

| Option | Description | Selected |
|--------|-------------|----------|
| One variable at a time | Preserve attribution despite the small sample. | ✓ |
| Multi-variable combinations | Compare a combinatorial policy matrix. | |
| Policy bundles | Compare conservative, current, and aggressive bundles. | |
| Other | Use another comparison structure. | |

**User's choice:** One variable at a time.
**Notes:** Avoid confounding and sample fragmentation.

---

## Risk-value candidates

### Maximum position value

| Option | Description | Selected |
|--------|-------------|----------|
| KRW 500k / 1m / 1.5m | Compare symmetric candidates around the current KRW 1m cap. | ✓ |
| KRW 500k / 750k / 1m | Compare only conservative candidates. | |
| Account percentage | Generate candidates as percentages of account value. | |
| Other | Use another range. | |

**User's choice:** KRW `500,000 / 1,000,000 / 1,500,000`.
**Notes:** Report expected quantity and exposure differences without changing settings.

### Stop-loss

| Option | Description | Selected |
|--------|-------------|----------|
| -3% / -5% / -7% | Compare symmetric candidates around the current -5%. | ✓ |
| -2% / -3% / -5% | Compare more loss-limiting candidates. | |
| -5% only | Keep the current value. | |
| Other | Use another range. | |

**User's choice:** `-3% / -5% / -7%`.
**Notes:** None.

### Take-profit

| Option | Description | Selected |
|--------|-------------|----------|
| +5% / +10% / +15% | Compare early, current, and longer-hold exits. | ✓ |
| +7% / +10% / +12% | Compare tightly around the current value. | |
| +10% only | Keep the current value. | |
| Other | Use another range. | |

**User's choice:** `+5% / +10% / +15%`.
**Notes:** None.

### BUY and SELL thresholds

| Option | Description | Selected |
|--------|-------------|----------|
| Vary independently | Attribute entry and exit changes separately. | ✓ |
| Vary together | Apply the same candidate to BUY and SELL together. | |
| BUY only | Keep SELL at 0.80. | |
| Other | Use another application rule. | |

**User's choice:** Vary BUY and SELL independently.
**Notes:** This remains consistent with the one-variable-at-a-time rule.

---

## Result judgment

### Candidate ordering

| Option | Description | Selected |
|--------|-------------|----------|
| Risk reduction first | Prioritize reduced risk while displaying opportunity and exposure changes. | ✓ |
| Trade opportunity first | Prioritize more trade opportunities with risk constraints. | |
| Aggregate score | Produce an automatic composite ranking. | |
| No ranking | Show values side by side only. | |

**User's choice:** Risk reduction first.
**Notes:** Trade opportunity remains visible but is not the primary objective.

### Short-sample label

| Option | Description | Selected |
|--------|-------------|----------|
| Provisional candidate | Identify a leader without recommending application. | ✓ |
| No candidate | Provide comparisons only. | |
| Recommended candidate | Recommend despite the insufficient-evidence warning. | |
| Other | Use another status. | |

**User's choice:** `PROVISIONAL_CANDIDATE` with no application recommendation.
**Notes:** A ranked result must not imply authorization to change policy.

### Uncertainty display

| Option | Description | Selected |
|--------|-------------|----------|
| Counts plus grade | Show exact sample/event counts, change rates, and an evidence grade. | ✓ |
| Bootstrap intervals | Calculate bootstrap confidence intervals. | |
| Warning only | Show warning text without numeric support. | |
| Other | Use another method. | |

**User's choice:** Counts plus evidence grade.
**Notes:** Exact denominators are required.

### Negligible differences

| Option | Description | Selected |
|--------|-------------|----------|
| No meaningful difference | Retain current policy when differences are absent or immaterial. | ✓ |
| Conservative tie-break | Select the more conservative candidate. | |
| Opportunity tie-break | Select the candidate with more trade opportunities. | |
| Other | Use another tie-break. | |

**User's choice:** `NO_MEANINGFUL_DIFFERENCE`; retain current policy.
**Notes:** The implementation may define a deterministic materiality rule.

---

## Real-money promotion boundary

### Incomplete Phase 9

| Option | Description | Selected |
|--------|-------------|----------|
| Promotion blocked | Allow advisory completion but keep real-money promotion blocked. | ✓ |
| Operator waiver | Permit a signature to waive Phase 9 evidence. | |
| Small real-money pilot | Permit limited live operation. | |
| Other | Use another boundary. | |

**User's choice:** Promotion remains `BLOCKED`.
**Notes:** Phase 9 remains truthfully incomplete and the safety-failed campaign cannot be converted into passing evidence.

### Approval authority

| Option | Description | Selected |
|--------|-------------|----------|
| Read-only readiness | Report READY/BLOCKED; keep real-setting changes in a separate manual, reconfirmed action. | ✓ |
| Mutating approval | Let the checklist command change real-money settings. | |
| Document only | Provide checkboxes without a readiness judgment. | |
| Other | Use another approval flow. | |

**User's choice:** Read-only readiness with separate manual promotion.
**Notes:** Validation commands receive no execution authority.

### Order blockers

| Option | Description | Selected |
|--------|-------------|----------|
| Active unresolved blocks | Current ambiguity blocks; resolved history remains a warning. | ✓ |
| Permanent historical block | Any historical ambiguity blocks forever. | |
| Timeout override | Let an operator ignore unresolved orders after time passes. | |
| Other | Use another rule. | |

**User's choice:** Current unresolved or ambiguous orders block promotion.
**Notes:** Determinately resolved historical cases remain reviewable without becoming permanent blockers.

### Readiness validity

| Option | Description | Selected |
|--------|-------------|----------|
| Snapshot-bound | Invalidate readiness when relevant evidence or policy changes. | ✓ |
| Persistent READY | Keep READY until manually revoked. | |
| 24-hour validity | Expire after a fixed day. | |
| Other | Use another validity rule. | |

**User's choice:** Snapshot-bound and invalidated on change.
**Notes:** A fresh assessment is required after any relevant change.

---

## Agent Discretion

- Exact CLI and module naming, deterministic materiality threshold, evidence-grade labels, and output formatting remain implementation choices within the locked boundaries.

## Deferred Ideas

- None. Full profitability backtesting, automatic policy writes, scheduling, and new strategies remain outside this phase.
