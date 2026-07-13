# Phase 8: Decision Reports & Operator Runbook - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-13
**Phase:** 8-Decision Reports & Operator Runbook
**Areas discussed:** Daily report shape, Period and replay summaries, Daily operating sequence, Failure triage playbooks

---

## Daily Report Shape

### Default detail

| Option | Description | Selected |
|--------|-------------|----------|
| Summary followed by all ticker details | Show a key summary first, then every candidate's decision, confidence, order result, and no-trade reason. | ✓ |
| Summary only by default | Require an additional details flag for ticker rows. | |
| Problem tickers only | Expand only errors, incomplete states, or ambiguous orders. | |
| Agent discretion | Follow the existing CLI convention. | |

**User's choice:** Summary followed by all ticker details.

### Grouping and order

| Option | Description | Selected |
|--------|-------------|----------|
| Run then processing order | Group by `screen`/`run` and retain actual ticker processing order. | ✓ |
| Consolidate by ticker | Merge the day's evidence for each ticker. | |
| Outcome severity | Put ambiguous orders and failures first. | |
| Agent discretion | Choose the most natural audit-schema projection. | |

**User's choice:** Run then processing order.

### Reason presentation

| Option | Description | Selected |
|--------|-------------|----------|
| Code plus Korean explanation | Preserve stable source code and add readable Korean text. | ✓ |
| Korean explanation only | Optimize readability but weaken direct source comparison. | |
| Code only | Preserve exact evidence vocabulary without translation. | |
| Agent discretion | Match current error output. | |

**User's choice:** Code plus Korean explanation.

### Output retention

| Option | Description | Selected |
|--------|-------------|----------|
| Terminal plus optional file | Print by default; save when `--output` is supplied. | ✓ |
| Always create a dated file | Persist every generated report automatically. | |
| Terminal only | Treat SQLite as the only durable record. | |
| Agent discretion | Follow existing CLI/replay patterns. | |

**User's choice:** Terminal plus optional file.

---

## Period and Replay Summaries

### Command organization

| Option | Description | Selected |
|--------|-------------|----------|
| Separate report subcommands | Use `bot report daily`, `period`, and `replay`. | ✓ |
| One command with options | Select report type through flag combinations. | |
| Extend existing commands | Put operational reports under status and replay reports under replay. | |
| Agent discretion | Follow the most natural Typer structure. | |

**User's choice:** Separate report subcommands.

### Period selection

| Option | Description | Selected |
|--------|-------------|----------|
| Inclusive KST trading dates | Include both endpoints and query `trading_date_kst`. | ✓ |
| Invocation timestamps | Select by actual UTC/KST execution timestamp. | |
| Most recent N runs | Select a count rather than dates. | |
| Agent discretion | Use the most consistent stored field. | |

**User's choice:** Inclusive KST trading-date range.

### Incomplete evidence

| Option | Description | Selected |
|--------|-------------|----------|
| Total and determinate denominators | Show both bases plus complete, incomplete, and unknown counts. | ✓ |
| One denominator | Treat every state as a result category in one base. | |
| Completed evidence only | Exclude incomplete/unknown evidence from primary rates. | |
| Agent discretion | Preserve explicit-denominator requirements. | |

**User's choice:** Total and determinate denominators side by side.

### Multiple replay results

| Option | Description | Selected |
|--------|-------------|----------|
| Per-result then compatible aggregate | Identify each result and aggregate only compatible evidence. | ✓ |
| Combine all results | Ignore schema, policy, and scenario differences. | |
| One result only | Disallow cross-result summaries. | |
| Agent discretion | Derive a safe combination rule from replay evidence. | |

**User's choice:** Per-result summaries followed by compatible aggregation only.
**Notes:** Every form retains the replay non-profitability disclaimer.

---

## Daily Operating Sequence

### Fixed schedule

| Option | Description | Selected |
|--------|-------------|----------|
| Early-session cycle | 08:50 status, 09:05 screen, 09:10 run, immediate report review. | ✓ |
| Operator-selected intraday time | Pre-open status, then choose a time within the continuous session. | |
| Morning and afternoon checks | Add a second daily checkpoint and possible execution rules. | |
| Agent discretion | Set times consistent with KRX safety boundaries. | |

**User's choice:** Early-session cycle.

### Preflight failure

| Option | Description | Selected |
|--------|-------------|----------|
| Abort run on critical failure | Stop mutation but retain status and historical reporting. | ✓ |
| Abort the entire workflow | Stop screen, run, and reporting together. | |
| Warn and ask operator | Permit an override after a warning. | |
| Agent discretion | Follow existing fail-closed policy. | |

**User's choice:** Abort `bot run` on any trading-critical preflight failure.

### Preview versus run screen

| Option | Description | Selected |
|--------|-------------|----------|
| Preview then fresh run screen | Re-evaluate candidates at run time and report differences. | ✓ |
| Reuse preview candidates | Freeze the 09:05 candidate set for the run. | |
| Confirm on differences | Re-screen, then ask before proceeding if candidates changed. | |
| Agent discretion | Retain the existing internal screen behavior. | |

**User's choice:** Preview then fresh run screen.

### Daily completion

| Option | Description | Selected |
|--------|-------------|----------|
| Complete after evidence review | Require terminal completeness and triage transfer for ambiguity. | ✓ |
| Complete when run exits | Permit report review later. | |
| Complete when report is generated | Do not require human review. | |
| Agent discretion | Derive completion from audit completeness. | |

**User's choice:** Complete only after evidence review.

---

## Failure Triage Playbooks

### Runbook structure

| Option | Description | Selected |
|--------|-------------|----------|
| Per-failure table and procedure | Include symptoms, stop/continue, checks, prohibitions, safe action, and resolution. | ✓ |
| Shared decision tree | Route all failures through common questions. | |
| Group by command | Put troubleshooting below status, screen, run, and report. | |
| Agent discretion | Choose the most readable structure. | |

**User's choice:** Per-failure table plus stepwise procedure.

### Rerun policy

| Option | Description | Selected |
|--------|-------------|----------|
| Explicit manual rerun after checks | Confirm audit health and no possible submission, then link a new run. | ✓ |
| Immediate pre-order rerun | Retry data/LLM failures without further checks. | |
| Auto-retry read-only work | Automatically retry status, reports, or screening only. | |
| Agent discretion | Follow existing failure-stage retry policy. | |

**User's choice:** Explicit manual rerun after checks; no automatic rerun.

### Ambiguous and duplicate orders

| Option | Description | Selected |
|--------|-------------|----------|
| Freeze affected ticker and reconcile | Establish broker truth before any new order for that ticker. | ✓ |
| Stop the whole day | Block all new runs after one affected ticker. | |
| Continue other tickers | Skip the affected ticker within the same run. | |
| Agent discretion | Choose the safe stop scope. | |

**User's choice:** Freeze the affected ticker and reconcile first.

### Audit versus notification failure

| Option | Description | Selected |
|--------|-------------|----------|
| Stop for audit, manually compensate notification | Fail closed on evidence; require direct review after alert failure. | ✓ |
| Stop for both | Treat notification delivery as trade-critical. | |
| Warn for both | Continue trading despite missing audit evidence. | |
| Agent discretion | Preserve existing fail-closed/fail-soft policies. | |

**User's choice:** Audit failure stops new trading; notification failure requires manual report review.

---

## Agent Discretion

- Internal report model and SQL/service organization.
- Terminal table layout, wrapping, output file extension, and exact option spelling.
- Korean reason-description catalog implementation and replay compatibility comparison mechanics.

## Deferred Ideas

None. The discussion remained within Phase 8 boundaries.
