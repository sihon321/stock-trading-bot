# Phase 9: KIS Mock Soak & Fault Drills - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-07-16
**Phase:** 9-KIS Mock Soak & Fault Drills
**Areas discussed:** Mock-only entry and isolation, Campaign pass/fail accounting, Broker-truth reconciliation and recovery, Fault-drill execution and evidence

---

## Mock-only entry and isolation

### Soak entry point

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated `bot soak` commands | Explicit start, run, resume, and status operations with unmistakable campaign intent. | ✓ |
| Extend `bot run --soak` | Reuse the daily command, with greater risk of confusing ordinary runs and campaign evidence. | |
| Single `bot soak` command | Infer start or resume, reducing explicit recovery intent. | |
| Agent discretion | Let planning choose the command structure. | |

**User's choice:** Dedicated `bot soak` commands.

### Mock isolation strength

| Option | Description | Selected |
|--------|-------------|----------|
| Construct a mock-only runtime | Resolve only mock credentials, domain, account, and TR IDs. | ✓ |
| Validate the normal active runtime | Build the shared runtime and validate its selected mode afterward. | |
| Separate soak environment file | Require a dedicated secrets file for soak operation. | |
| Agent discretion | Let research choose the isolation boundary. | |

**User's choice:** Construct a mock-only runtime.

### Visible identity proof

| Option | Description | Selected |
|--------|-------------|----------|
| Full non-secret identity receipt | Persist target, domain class, account suffix, TR-ID profile, campaign ID, and policy version. | ✓ |
| Simple mock banner | Show only a generic KIS mock label. | |
| Receipt plus manual confirmation | Require confirmation before every campaign run. | |
| Agent discretion | Let planning choose identity evidence. | |

**User's choice:** Full non-secret identity receipt.

### Isolation failure evidence

| Option | Description | Selected |
|--------|-------------|----------|
| Record a blocked attempt when audit is healthy | Append a sanitized non-counting block event; fail without mutation when audit is unknown. | ✓ |
| Fail before all persistence | Exit without durable campaign evidence. | |
| Count it as a failed soak day | Consume the day's campaign attempt. | |
| Agent discretion | Let planning choose the persistence boundary. | |

**User's choice:** Record a blocked attempt when audit is healthy.

---

## Campaign pass/fail accounting

### Required campaign length

| Option | Description | Selected |
|--------|-------------|----------|
| Immutable per campaign, default 20 eligible days | Record the target at creation and prevent later changes. | ✓ |
| Fixed at 20 eligible days | Use one threshold for every campaign. | |
| Immutable per campaign, no default | Require the operator to choose N explicitly. | |
| Agent discretion | Let research establish the target. | |

**User's choice:** Immutable per campaign with a default of 20 eligible KRX days.

### Eligible-day admission

| Option | Description | Selected |
|--------|-------------|----------|
| One designated terminal mock run | Count at most one complete run per confirmed trading date; HOLD and zero-order days qualify. | ✓ |
| Any terminal mock run | Allow the first complete run to earn credit implicitly. | |
| Only days with a mock order | Require at least one broker submission. | |
| Agent discretion | Let planning define admission. | |

**User's choice:** One explicitly designated terminal mock run per eligible KRX day.

### Availability failures

| Option | Description | Selected |
|--------|-------------|----------|
| Separate budget, default two days | Consume budget without day credit or safety-streak reset; fail when exceeded. | ✓ |
| Reset progress and continue | Restart consecutive progress after any availability failure. | |
| Zero failure budget | Fail the campaign on the first unavailable dependency. | |
| Agent discretion | Let planning define availability accounting. | |

**User's choice:** Separate immutable availability budget defaulting to two days.

### Immediate campaign failure

| Option | Description | Selected |
|--------|-------------|----------|
| Any safety-invariant breach | Permanently fail on real-target reachability, unsafe submission/retry, evidence loss, or reconciliation defects. | ✓ |
| Only unintended mock orders | Pause and reset for other invariant defects. | |
| Reset for all defects | Permit campaign continuation unless manually aborted. | |
| Agent discretion | Let planning define the invariant catalog. | |

**User's choice:** Any safety-invariant breach permanently fails the campaign; correctly contained drills do not.

---

## Broker-truth reconciliation and recovery

### Mandatory reconciliation points

| Option | Description | Selected |
|--------|-------------|----------|
| Startup, pre-run, post-submission, and finalization | Reconcile at every mutation and day-credit boundary. | ✓ |
| Startup and end-of-run only | Reduce KIS inquiries with longer divergence windows. | |
| Only unresolved evidence | Query only after ambiguity, duplicates, or incomplete fills. | |
| Agent discretion | Let research balance inquiry coverage and rate limits. | |

**User's choice:** Startup/resume, pre-run, post-submission, and run-finalization reconciliation.

### Broker-truth snapshot

| Option | Description | Selected |
|--------|-------------|----------|
| Orders, fills, open orders, and account state | Normalize campaign-touched order, holding, and cash evidence together. | ✓ |
| Order and fill state only | Exclude holdings and cash comparison. | |
| Full account snapshot | Include unrelated holdings and broker activity. | |
| Agent discretion | Let planning choose the minimum facts. | |

**User's choice:** Orders, fills, open orders, holdings, and available cash for campaign-touched activity.

### Ambiguous-submission recovery

| Option | Description | Selected |
|--------|-------------|----------|
| Bounded strict broker matching | Never resubmit; search by recorded facts and require a determinate result. | ✓ |
| Wait until next run | Delay inquiry until campaign startup. | |
| Immediate manual review only | Avoid automated recovery inquiry. | |
| Agent discretion | Let research determine KIS matching support. | |

**User's choice:** Bounded authenticated inquiry with strict matching and operator review for multiple or inconclusive matches.

### Partial and no fills

| Option | Description | Selected |
|--------|-------------|----------|
| Determinate but ticker-frozen until terminal | Permit complete evidence while preventing overlapping intents across restarts. | ✓ |
| Allow new evaluations | Permit later orders using reconciled holdings while a remainder stays open. | |
| Fail on every non-full fill | Treat broker liquidity behavior as campaign failure. | |
| Agent discretion | Let planning choose the freeze policy. | |

**User's choice:** Preserve day eligibility when evidence is complete, but keep the ticker frozen until broker-confirmed terminal state.

---

## Fault-drill execution and evidence

### Evidence provenance

| Option | Description | Selected |
|--------|-------------|----------|
| Separate controlled and KIS-observed classes | Require reproducible drills and keep naturally observed evidence distinct. | ✓ |
| Prefer KIS-observed evidence | Inject only failures that cannot safely occur naturally. | |
| Controlled injection only | Treat real KIS failures only as ordinary soak events. | |
| Agent discretion | Let research classify fault sources. | |

**User's choice:** Separate `CONTROLLED_INJECTION` and `KIS_OBSERVED` evidence classes.

### Drill invocation

| Option | Description | Selected |
|--------|-------------|----------|
| Dedicated `bot soak drill <fault>` | Require one explicit fault, injection boundary, and drill ID. | ✓ |
| Flags on ordinary soak runs | Mix drill controls into eligible-day execution. | |
| Multi-fault fixture file | Run several faults from one scenario document. | |
| Agent discretion | Let planning choose the interface. | |

**User's choice:** Dedicated one-fault-per-invocation drill command.

### Day-credit interaction

| Option | Description | Selected |
|--------|-------------|----------|
| Separate drill-coverage dimension | Controlled drills cannot earn day credit or consume availability budget. | ✓ |
| Count contained drills | Allow a successful drill to qualify as the daily run. | |
| Operator chooses per drill | Make credit-bearing status an invocation option. | |
| Agent discretion | Let planning decide whether evidence dimensions overlap. | |

**User's choice:** Keep controlled drill coverage separate from clean-operation day accounting.

### Self-failure evidence boundary

| Option | Description | Selected |
|--------|-------------|----------|
| Independent controller journal | Persist intent before injection and link recovery evidence afterward outside the audit DB under test. | ✓ |
| Primary audit DB only | Depend on the component intentionally being disrupted. | |
| Operator checklist | Rely on manual evidence when automated capture is unavailable. | |
| Agent discretion | Let research design the evidence boundary. | |

**User's choice:** Standard machine-checkable drill contract backed by an independent controller journal.

---

## Agent Discretion

No user decisions were delegated. Downstream agents retain only the bounded technical discretion recorded in `09-CONTEXT.md`.

## Deferred Ideas

None. The discussion stayed within Phase 9.
