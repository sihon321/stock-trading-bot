# Phase 2: Mock Execution Core - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md - this log preserves the alternatives considered.

**Date:** 2026-07-01
**Phase:** 2-Mock Execution Core
**Areas discussed:** Signal parser behavior, Execution and risk rules

---

## Area Selection

| Option | Description | Selected |
|--------|-------------|----------|
| All four areas | Parser failure behavior, execution/risk precedence, mock broker account model, and dry-run/audit shape. | |
| Signal parser behavior | How malformed JSON, unknown decisions, confidence bounds, and missing fields become HOLD/no-trade. | Yes |
| Execution and risk rules | BUY/SELL thresholds, sizing, stop-loss/take-profit, risk precedence, and daily-loss kill switch. | Yes |
| Mock broker account model | How cash, positions, order IDs, fills, and broker state should behave in tests. | |
| Dry-run and audit output | What gets logged when orders are suppressed, simulated, or risk-overridden. | |

**User's choice:** `2, 3`
**Notes:** User selected parser behavior plus execution/risk rules only.

---

## Signal Parser Behavior

| Question | Selected Option | Notes |
|----------|-----------------|-------|
| For malformed or incomplete LLM signal input, what should the parser preserve? | Reject with exception internally | Parser raises a domain error; execution chain catches it and converts to HOLD/no-trade. |
| What should count as invalid? | Strict required fields, tolerate extras | Malformed JSON, missing required fields, unknown decision, out-of-range confidence, and empty reason are invalid; extra fields are ignored. |
| How should confidence thresholds apply? | Execution thresholds only | Parser validates only the `0.0..1.0` range. |
| What should parser output look like on success? | Parsed wrapper | Preserve canonical signal plus raw input and non-sensitive diagnostics. |

**User's choice:** See selected options above.
**Notes:** User moved to the next selected area after these parser questions.

---

## Execution and Risk Rules

| Question | Selected Option | Notes |
|----------|-----------------|-------|
| For BUY/SELL confidence thresholds, what should Phase 2 lock? | Separate thresholds | BUY and SELL use separately configurable thresholds, defaulting to `0.8` and `0.8`. |
| How should position sizing work for BUY? | Cash percent capped by max position | Spend a configurable percentage of available cash, capped by max position value per ticker. |
| When the risk net and LLM signal disagree on a ticker, what should happen? | Risk always wins | Stop-loss, take-profit, or kill-switch decisions suppress conflicting LLM actions and are logged as overrides. |
| How should the daily-loss kill switch behave? | Block new BUYs only | After breach, block new BUYs for the day while still allowing SELLs and risk exits. |
| How should stop-loss and take-profit evaluate positions? | Percent thresholds from average price | Compare current price to position average price using configurable percentages. |

**User's choice:** See selected options above.
**Notes:** User chose to write context after these questions.

---

## the agent's Discretion

- Exact class/function names.
- Exact diagnostic wrapper fields, as long as raw input and non-sensitive diagnostics are preserved.
- Test fixture organization.

## Deferred Ideas

None.
