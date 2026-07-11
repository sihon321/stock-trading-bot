# Phase 7: Deterministic Replay Validation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-11
**Phase:** 7-Deterministic Replay Validation
**Areas discussed:** Scenario and fixture design, Replay state progression, Manifest and result identity, Operator output and comparisons

---

## Scenario and Fixture Design

| Decision | Options considered | Selected |
|----------|--------------------|----------|
| Scenario unit | Mixed focused/full-day; focused only; full-day only | Mixed focused/full-day ✓ |
| Initial coverage | Full Phase 7 requirements; minimal core; extended safety | Full Phase 7 requirements ✓ |
| Signal representation | Explicit raw JSON; shared rule table; validated objects | Explicit raw JSON ✓ |
| OHLCV bounds | Warm-up through evaluation plus access guard; evaluation-only; broad dataset | Warm-up through evaluation plus access guard ✓ |

**Notes:** Focused cases are the default. Multi-ticker days cover important interactions. Raw signals use the production parser, and future access fails immediately.

---

## Replay State Progression

| Decision | Options considered | Selected |
|----------|--------------------|----------|
| State mode | Isolated focused + sequential day; always isolated; always sequential | Dual mode ✓ |
| Fill application | After each step; day-end batch; intent only | After each step ✓ |
| Fill scope | Complete/no fill; partial fills; all broker states | Complete/no fill ✓ |
| Ticker order | Screener rank + ticker tie-break; fixture order; ticker order | Screener rank + ticker tie-break ✓ |

**Notes:** Partial fills and broker uncertainty stay in Phase 9.

---

## Manifest and Result Identity

| Decision | Options considered | Selected |
|----------|--------------------|----------|
| Manifest breadth | Complete deterministic input; core only; bundle hash | Complete deterministic input ✓ |
| Stable identity | Inputs + ordered outcomes; inputs only; outcomes only | Inputs + ordered outcomes ✓ |
| Dirty worktree | Commit + relevant change hash; clean only; commit + warning | Commit + relevant change hash ✓ |
| Time fields | Separate deterministic/observational; actual time in ID; exclude all time | Separate deterministic/observational ✓ |

**Notes:** Different outcomes from identical deterministic inputs must produce a different stable result ID and expose nondeterminism.

---

## Operator Output and Comparisons

| Decision | Options considered | Selected |
|----------|--------------------|----------|
| Default CLI detail | Summary + failures/differences; all tickers; pass/fail only | Summary + failures/differences ✓ |
| Complete artifact | Normalized JSON; JSON + Markdown; SQLite | Normalized JSON ✓ |
| Strictness comparison | Explicit-denominator gate funnel; final distribution; scenario pass rate | Gate funnel ✓ |
| Profitability guard | Explicit non-profitability contract; warning + price movement; omission only | Explicit contract ✓ |

**Notes:** Replay emits no P&L, return, win-rate, Sharpe, or similar performance metrics. Phase 8 owns human-readable reports.

## Agent Discretion

- Fixture layout and schema details, CLI naming, normalized JSON field names, hashing algorithm, and output-directory conventions.

## Deferred Ideas

- Phase 8: human-readable daily and period reports.
- Phase 9: partial fills and broker-facing ambiguity/reconciliation behavior.
- Phase 10: advisory policy calibration. Full profitability backtesting remains outside v1.1.
