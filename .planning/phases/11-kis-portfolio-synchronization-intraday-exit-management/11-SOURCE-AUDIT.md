# Phase 11 Multi-Source Coverage Audit

| SOURCE | ID | Feature / requirement | Plan | Status |
|---|---|---|---|---|
| GOAL | — | Synchronize KIS portfolio truth into every cycle and safely exit held positions with restart-safe reconciliation | 01-06 | COVERED |
| REQ | PORT-01 | Complete KIS cash, holdings, orderable quantity, average price, open orders, and recent fills before decisions | 01, 02, 03, 04, 05, 06 | COVERED |
| REQ | PORT-02 | Held-first union with incomplete held evidence retained and failed closed | 01, 03, 06 | COVERED |
| REQ | EXIT-01 | One daily LLM evaluation plus deterministic no-LLM intraday exits | 01, 03, 04, 05, 06 | COVERED |
| REQ | EXIT-02 | Broker-truth reconciliation across partial/cancel/ambiguity/restart/duplicate paths | 01, 02, 04, 05, 06 | COVERED |
| RESEARCH | R-01 | Whole-account pagination and cancellation normalization | 01 | COVERED |
| RESEARCH | R-02 | Append-only snapshot, daily evaluation, watch, transition, and lease persistence | 01, 02, 06 | COVERED |
| RESEARCH | R-03 | Hybrid `flock` plus durable recovery state | 02 | COVERED |
| RESEARCH | R-04 | Held-first once-daily evaluation with immutable input/reuse | 03 | COVERED |
| RESEARCH | R-05 | Shared daily/intraday SELL coordinator and single-shot POST | 04 | COVERED |
| RESEARCH | R-06 | Foreground check/watch state machine and session timeline | 05 | COVERED |
| RESEARCH | R-07 | State-transition alert projection and operator contract | 06 | COVERED |
| RESEARCH | R-08 | Strict normalization, sanitized evidence, fail-closed persistence, and no new packages | 01-06 | COVERED |
| CONTEXT | D-01 | Complete required account dimensions before mutation | 01 | COVERED |
| CONTEXT | D-02 | Cycle snapshot plus affected-ticker pre-POST refresh | 04 | COVERED |
| CONTEXT | D-03 | Changed truth recalculates and reruns gates | 04 | COVERED |
| CONTEXT | D-04 | Restart queries KIS anew | 01, 02 | COVERED |
| CONTEXT | D-05 | Current/previous trading-day window plus older unresolved lookup | 01 | COVERED |
| CONTEXT | D-06 | Bounded read retry; single-shot POST | 01, 04 | COVERED |
| CONTEXT | D-07 | KIS current truth, local append-only intent history | 01, 03 | COVERED |
| CONTEXT | D-08 | Warning divergence versus blocking order-risk divergence | 01 | COVERED |
| CONTEXT | D-09 | Held-first attributable union and broker-observed candidate capacity | 03 | COVERED |
| CONTEXT | D-10 | Overlap evaluated once with dual provenance | 03 | COVERED |
| CONTEXT | D-11 | Six held-position context fields | 03 | COVERED |
| CONTEXT | D-12 | Per-held market failure remains DATA_INCOMPLETE/HOLD; account failure global | 03 | COVERED |
| CONTEXT | D-13 | One finalized logical evaluation per date/ticker | 01, 03 | COVERED |
| CONTEXT | D-14 | Retries inside identity; exhaustion final HOLD | 01, 03 | COVERED |
| CONTEXT | D-15 | Same-day signal reuse without LLM recall | 03 | COVERED |
| CONTEXT | D-16 | Reused signal cannot override current gates | 03, 04 | COVERED |
| CONTEXT | D-17 | Manual one-shot check and foreground watch only | 05, 06 | COVERED |
| CONTEXT | D-18 | Configurable 60-second default/minimum cadence | 05 | COVERED |
| CONTEXT | D-19 | Independent audited no-LLM watch iteration | 05 | COVERED |
| CONTEXT | D-20 | Incomplete iteration blocks only itself and watch continues | 05 | COVERED |
| CONTEXT | D-21 | Pre-open read-only and confirmed continuous activation | 05, 06 | COVERED |
| CONTEXT | D-22 | 15:20 POST cutoff, 15:30 exit, no auto-cancel | 05, 06 | COVERED |
| CONTEXT | D-23 | Ctrl-C stops POST, terminalizes, reconciles, then releases | 05, 06 | COVERED |
| CONTEXT | D-24 | Recovery-only startup after crash/unresolved shutdown | 02, 05 | COVERED |
| CONTEXT | D-25 | One account lease across run/check/watch | 02, 03, 04 | COVERED |
| CONTEXT | D-26 | Active owner conflict exits immediately with bounded metadata | 02 | COVERED |
| CONTEXT | D-27 | Reclaim requires owner-gone proof, recovery, and reconciliation | 02 | COVERED |
| CONTEXT | D-28 | Lease loss stops POST and reconciles/terminalizes | 02, 04, 05 | COVERED |
| CONTEXT | D-29 | Latest full orderable quantity, excluding open SELL | 04 | COVERED |
| CONTEXT | D-30 | Fresh tick-snapped limit SELL only | 04, 06 | COVERED |
| CONTEXT | D-31 | OPEN/PARTIAL is reconcile-only | 04, 06 | COVERED |
| CONTEXT | D-32 | Terminal no-fill/cancel can retry only in later independent cycle | 04 | COVERED |
| CONTEXT | D-33 | Later HOLD/BUY does not cancel open SELL; BUY stays blocked | 04, 06 | COVERED |
| CONTEXT | D-34 | Observe cancellation; no cancel POST | 04, 06 | COVERED |
| CONTEXT | D-35 | Broker snapshot owns post-partial position | 04 | COVERED |
| CONTEXT | D-36 | Daily-loss remains BUY-only | 04 | COVERED |
| CONTEXT | D-37 | Notify only transitions and safety events | 06 | COVERED |
| CONTEXT | D-38 | Stable INFO/WARNING/CRITICAL with Korean text | 06 | COVERED |
| CONTEXT | D-39 | Durable state-identity dedup with count/duration | 06 | COVERED |
| CONTEXT | D-40 | Transport fail-soft; attempt-evidence fail-closed | 04, 06 | COVERED |

## Exclusions

- Unattended scheduling, background supervision, distributed locking, and global pause/resume remain Phase 15.
- Automatic cancellation, market-order exits, aggressive price chasing, and portfolio-wide forced liquidation are explicitly deferred and do not appear in the plans.

## Result

All goal, requirement, research, and locked-context items are covered. No source item is missing and no phase split is required.
