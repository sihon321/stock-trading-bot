# Phase 11: KIS Portfolio Synchronization & Intraday Exit Management - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-09-01
**Phase:** 11-kis-portfolio-synchronization-intraday-exit-management
**Areas discussed:** Portfolio synchronization boundary, daily evaluation universe, intraday operation, SELL lifecycle, daily LLM identity, mutation lease, watch lifecycle, intraday alerts

---

## Portfolio Synchronization Boundary

| Decision point | Selected | Alternatives considered |
|----------------|----------|-------------------------|
| Incomplete required broker truth | Block every order in the cycle | Block BUY only; isolate affected ticker |
| Refresh boundary | Full snapshot at cycle start plus affected truth immediately before POST | Start-only snapshot; full snapshot per ticker |
| Changed pre-POST truth | Recalculate quantity and all applicable gates | Abort order; apply reductions only |
| Snapshot after restart | Evidence only; always query KIS again | Reuse within TTL; reuse for trading date |
| Recent-fill window | Current and previous KRX day, plus older unresolved intents individually | Current day only; three-day fixed window |
| Query failure | Bounded read retry, then non-mutable cycle | Fail first attempt; retry indefinitely |
| Current-state authority | Complete KIS truth, with local divergence recorded | Block on every divergence; local state first |
| Divergence blocker | Unattributable unresolved/ambiguous order risk | Every cash/holding difference; never block |

**User's choice:** Selected the recommended option for every decision point.
**Notes:** Complete KIS broker truth is the mutation authority; local evidence remains immutable intent and observation history.

---

## Daily Evaluation Universe

| Decision point | Selected | Alternatives considered |
|----------------|----------|-------------------------|
| Processing order | Holdings first, then screened candidates | Screener rank; ticker sort |
| HELD/SCREENED overlap | One LLM evaluation with both provenance labels | Two evaluations; held-only provenance |
| Held-position LLM context | Full decision-relevant portfolio state | Average price/quantity only; market data only |
| Per-ticker data failure | Keep holding, record `DATA_INCOMPLETE/HOLD`, block ticker only | Block whole daily run; call LLM with incomplete data |

**User's choice:** Selected the recommended option for every decision point.
**Notes:** Account-level broker-truth incompleteness still blocks all orders; only ticker-local market-data failure is isolated.

---

## Intraday Operation

| Decision point | Selected | Alternatives considered |
|----------------|----------|-------------------------|
| Operator interface | Both one-shot check and foreground watch | Check only; watch only |
| Cadence | Configurable, default 60 seconds, enforced minimum | Fixed 60 seconds; five minutes; websocket |
| Per-iteration inputs | Complete broker truth plus fresh held-position quotes | Quote every iteration, broker periodically; subset truth |
| Failed iteration | Block that iteration and continue watch | Exit immediately; latch until manual release |

**User's choice:** Selected the recommended option for every decision point.
**Notes:** Intraday cycles never call the LLM.

---

## SELL Order Lifecycle

| Decision point | Selected | Alternatives considered |
|----------------|----------|-------------------------|
| Quantity | Entire latest KIS orderable quantity | Gross holding; half; different LLM/risk sizing |
| Price | Fresh-current-price KRX-tick limit | Market; aggressive limit; risk-only market |
| Partial/open remainder | Reconcile existing order; no additional POST | Reorder each cycle; timed cancel/reorder |
| Canceled/expired/no-fill | Re-evaluate as a new intent in a later cycle | Manual approval; wait a day; same-cycle repost |
| Later HOLD/BUY conflict | Keep open SELL and block BUY | Cancel SELL; cancel only LLM-origin SELL |
| Cancellation authority | Observe external/operator KIS cancellation only | CLI cancel; automatic end-of-watch cancel |
| Post-partial position | Use next complete KIS holding and average price | Original position; local arithmetic |
| Daily-loss kill | Block BUY only; continue valid exits | Liquidate all; block all orders |

**User's choice:** Selected the recommended option for every decision point.
**Notes:** Ambiguous acknowledgement never becomes terminal by inference and freezes the ticker until determinate.

---

## Daily LLM Evaluation Identity

| Decision point | Selected | Alternatives considered |
|----------------|----------|-------------------------|
| Daily limit | One finalized evaluation per KRX date and ticker | One portfolio call; one call per invocation |
| Provider failure | Bounded retry inside one logical evaluation, then daily HOLD | Immediate HOLD; later rerun; operator override |
| Same-day rerun | Reuse signal/input snapshot; refresh execution truth | Inspection only; recall when market data changes |
| Signal expiry | KRX trading-day end, subordinate to current gates | First order attempt; portfolio change; fixed TTL |

**User's choice:** Selected the recommended option for every decision point.
**Notes:** Stable evaluation identity prevents repeated intraday or rerun LLM costs and contradictory signals.

---

## Account Mutation Lease

| Decision point | Selected | Alternatives considered |
|----------------|----------|-------------------------|
| Lock scope | One mutation lease per KIS account | Ticker lock; command-specific lock |
| Contending command | Exit immediately as non-mutable | Observer fallback; wait; steal lease |
| Stale lease | Owner-death proof plus cycle recovery and reconciliation | Timeout reclaim; manual deletion; reboot reset |
| Lease loss | Stop POST, reconcile submitted orders, fail/interrupt cycle | Finish ticker; grace period |

**User's choice:** Selected the recommended option for every decision point.
**Notes:** Phase 11 uses local/manual-process exclusion; unattended or distributed leadership remains Phase 15.

---

## Watch Lifecycle

| Decision point | Selected | Alternatives considered |
|----------------|----------|-------------------------|
| Pre-open start | Read-only preflight/wait, mutate after confirmed open | Reject start; evaluate early |
| Close boundary | Stop POST 15:20, reconcile to 15:30, auto-exit | Exit 15:20; POST to 15:30; remain observing |
| Ctrl-C | Stop POST, mark interrupted, bounded reconcile, release | Finish cycle; immediate exit; confirmation prompt |
| Restart with unresolved work | Recovery-only before normal watch | Parallel recovery; separate manual recovery command |

**User's choice:** Selected the recommended option for every decision point.
**Notes:** Remaining open orders are never automatically canceled at shutdown.

---

## Intraday Alerts and Evidence

| Decision point | Selected | Alternatives considered |
|----------------|----------|-------------------------|
| Immediate alert scope | State transitions and safety events | Every iteration; order only; critical only |
| Severity | INFO/WARNING/CRITICAL | Two levels; unclassified |
| Deduplication | State identity start once plus change/recovery once | Fixed cooldown; severity cooldown; every iteration |
| Notification failure | Transport fail-soft; evidence-write fail-closed | Every failure blocks; every failure fail-soft |

**User's choice:** Selected the recommended option for every decision point.
**Notes:** Repeated occurrence count and duration remain queryable even when notifications are deduplicated.

---

## Agent's Discretion

- Internal names, schemas, command spelling, lock backend, heartbeat and bounded timeout values.
- Exact Korean rendering and the threshold for a long-open WARNING.
- Storage projection boundaries, provided snapshot and pre-POST evidence remain attributable.

## Deferred Ideas

- Phase 15: unattended scheduling, service supervision, distributed leadership, global pause/resume.
- Outside Phase 11: cancel POST authority, automatic price chasing, market orders, and forced portfolio liquidation.
