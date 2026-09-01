# Phase 11: KIS Portfolio Synchronization & Intraday Exit Management - Research

**Researched:** 2026-09-02
**Domain:** KIS account-truth synchronization, daily evaluation idempotency, deterministic intraday exits, single-host mutation exclusion, and restart-safe SELL reconciliation
**Confidence:** HIGH for repository architecture and locked behavior; MEDIUM for external KIS field semantics

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Portfolio truth and synchronization boundaries
- **D-01:** A mutable cycle obtains no order authority unless cash, holdings, orderable quantity, average price, open orders, and recent fills are all completely and successfully normalized from KIS. Any incomplete required dimension blocks all orders for that cycle.
- **D-02:** Fetch a complete account snapshot at cycle start. Immediately before every POST, re-fetch the affected ticker's holding, orderable quantity, open-order, and recent-fill truth together with a fresh quote.
- **D-03:** If pre-POST broker truth differs from the cycle-start snapshot, recalculate quantity and re-run the applicable execution gates against the latest truth. Proceed only if the original decision remains actionable.
- **D-04:** A snapshot from an earlier process or cycle is audit and comparison evidence only. Restart always performs a new KIS query before acquiring mutation authority.
- **D-05:** The standard recent-order/fill window covers the current and immediately previous confirmed KRX trading day. Older locally unresolved orders remain individually queryable back to their originating date until determinate.
- **D-06:** Read-only KIS queries may use bounded retries with short backoff. Exhaustion leaves the snapshot incomplete and the cycle non-mutable; POST remains single-shot and is never blindly retried.
- **D-07:** Complete KIS truth is authoritative for current cash, holdings, fills, and open orders. Local audit data remains authoritative for intent and observation history; every divergence is recorded rather than overwritten.
- **D-08:** A simple holding or cash difference is synchronized from KIS and warned. An unresolved or ambiguous local order that cannot be uniquely attributed to a KIS order by ticker, side, quantity, and identity is an order-risk divergence that blocks mutation.

#### Daily evaluation universe and held-position context
- **D-09:** The daily evaluation universe is the attributable union of broker-held positions and current screened candidates. Evaluate held positions first, then evaluate new candidates against the resulting cash and position-cap state.
- **D-10:** A ticker present in both sources is evaluated once. Preserve both `HELD` and `SCREENED` provenance on the shared ticker/evaluation record.
- **D-11:** Held-position LLM context includes average price, total quantity, orderable quantity, current price, unrealized return, and open SELL quantity, in addition to the existing market, indicator, and delimited untrusted-news context.
- **D-12:** Incomplete market evidence for one held ticker never removes the holding from review. Record an attributable `DATA_INCOMPLETE/HOLD`, block that ticker's order, and continue other tickers. This does not weaken D-01: incomplete account-level broker truth blocks every order.

#### One daily LLM evaluation
- **D-13:** Allow at most one finalized logical LLM evaluation per KRX trading date and ticker. HELD/SCREENED overlap shares one stable evaluation identity.
- **D-14:** Provider timeout, provider error, or malformed output may use bounded retries only inside that logical evaluation. Exhaustion finalizes `LLM_UNAVAILABLE/HOLD` for the ticker and prevents another LLM call that trading day.
- **D-15:** A later `bot run` on the same trading day reuses the successful signal and its immutable input snapshot. It re-evaluates current broker truth, fresh quote, risk, sizing, and order gates without calling the LLM again.
- **D-16:** The daily signal expires at the KRX trading-day boundary. Before then it never overrides current broker truth, deterministic risk rules, quote freshness, mutation lease ownership, duplicate suppression, or unresolved-order freezes.

#### Intraday operator workflow
- **D-17:** Provide both an operator-invoked one-shot intraday `check` and a foreground `watch`. Neither creates a background service, scheduler, or boot-time process.
- **D-18:** The watch cadence is configurable with a conservative default of 60 seconds and an enforced minimum interval to prevent abusive KIS request rates.
- **D-19:** Treat every watch iteration as an independent audited cycle. Each iteration obtains complete broker truth and fresh quotes for held positions, then applies deterministic stop-loss, take-profit, and existing daily-loss rules without an LLM call.
- **D-20:** An incomplete iteration blocks orders for that iteration but does not terminate watch. A later iteration may regain mutation authority only from a newly complete snapshot.
- **D-21:** Watch may start before the market and perform read-only preflight and synchronization while waiting. Mutation activates only after a positively confirmed KRX continuous session begins.
- **D-22:** Stop new POSTs at 15:20 KST, retain read-only reconciliation through 15:30, then exit automatically. Do not auto-cancel remaining open orders.
- **D-23:** On `Ctrl-C`, stop new POSTs immediately, terminalize the in-progress cycle as `INTERRUPTED`, perform bounded reconciliation for already submitted orders, then release the mutation lease. Any unresolved result remains durable.
- **D-24:** After a crash or unresolved shutdown, watch enters recovery-only mode first. It may not resume normal evaluation or POST until prior cycles are terminalized and broker truth makes earlier order state determinate.

#### Account-scoped mutation lease
- **D-25:** Enforce one mutation lease per KIS account across `bot run`, intraday `check`, and `watch`. Ticker-level or command-level concurrency is not sufficient because cash, holdings, and open orders are account-wide truth.
- **D-26:** A new mutable command that finds an active lease exits immediately as non-mutable and reports bounded owner/start metadata plus the read-only inspection path. It does not wait, steal the lease, or silently become an observer.
- **D-27:** Reclaim a stale lease only after confirming its owner is gone, recovering/terminalizing the prior cycle, and completing broker reconciliation. Heartbeat age or reboot alone never grants mutation authority.
- **D-28:** If a running process loses lease ownership or cannot renew it, stop new POSTs immediately, reconcile already submitted orders, and terminalize the cycle with an explicit failure/interruption state.

#### SELL order lifecycle
- **D-29:** Both a daily LLM SELL and an intraday deterministic exit target the latest KIS orderable quantity in full. Quantity already reserved by an open SELL is excluded and never submitted again.
- **D-30:** Submit a limit SELL based on a quote observed no more than 10 seconds before POST and snapped to the valid KRX tick. Do not introduce market orders or an automatic aggressive-price offset in this phase.
- **D-31:** While an order is `OPEN` or `PARTIAL`, track and reconcile that broker order only. Do not submit the remainder again, auto-cancel it, or chase the price.
- **D-32:** A determinate `CANCELED`, `EXPIRED`, or `NO_FILL` may lead to a new intent only in a later independent cycle after complete broker truth, a fresh quote, and a still-valid exit condition are all re-established.
- **D-33:** A later HOLD/BUY signal or cleared risk threshold does not auto-cancel an already open SELL. Block new BUY for that ticker until the SELL reaches determinate terminal broker state.
- **D-34:** This phase observes cancellations made through KIS/operator channels but adds no cancel-POST authority to the bot.
- **D-35:** After a partial fill, the next complete KIS snapshot's remaining quantity and average price define the position. Local fill arithmetic is comparison evidence, not mutation authority.
- **D-36:** The existing daily-loss kill switch continues to block new BUY only. It does not liquidate every holding or block valid stop-loss/take-profit SELLs.

#### Intraday evidence and alerts
- **D-37:** Send immediate notifications only for state transitions and safety events: risk SELL triggers, order-state changes, ambiguity/unresolved state, broker-truth failure, lease loss, interruption, and recovery. Unchanged normal iterations remain in durable audit evidence without notification noise.
- **D-38:** Use stable `INFO`, `WARNING`, and `CRITICAL` severity codes with Korean human-readable text. Starts, stops, and determinate fills are informational; sustained failures and long-open orders are warnings; ambiguity, audit failure, and lease loss are critical.
- **D-39:** Deduplicate by stable state identity: notify once when the state begins and once when it changes or recovers. Persist occurrence count and duration for every repeated watch observation.
- **D-40:** Notification transport failure remains fail-soft and visible. Failure to persist notification-attempt evidence is fail-closed for new orders, consistent with the existing evidence boundary.

### the agent's Discretion

- Choose concrete module, class, table, command, option, lock-backend, heartbeat, retry-count, minimum-cadence, and stable reason-code names consistent with existing Typer, frozen dataclass, SQLite, canonical identity, and append-only evidence patterns.
- Define bounded reconciliation timeouts, exact long-open WARNING threshold, terminal rendering, and Korean message wording, provided the locked lifecycle and fail-closed boundaries remain unchanged.
- Choose whether portfolio snapshots extend the primary audit schema or use an independently versioned projection linked by stable IDs, provided one cycle can prove the exact snapshot and pre-POST observation used.

### Deferred Ideas (OUT OF SCOPE)

- Unattended scheduling, background service supervision, distributed leader election, and global pause/resume controls remain Phase 15.
- Automatic cancellation, market-order exits, aggressive price chasing, and forced portfolio-wide liquidation are not included in Phase 11.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| PORT-01 | Every executable cycle can load complete KIS broker truth for cash, holdings, orderable quantity, average price, open orders, and recent fills before making a decision. | Factor Phase 9 pagination/normalization into an account-scoped snapshot service; add cancellation fields, exact completeness rules, account snapshot evidence, and pre-POST ticker refresh. [VERIFIED: codebase grep and phase context D-01..D-08] |
| PORT-02 | The daily execution universe is the union of screened candidates and broker-held positions, with stale or incomplete held-position evidence failing closed without dropping the holding from review. | Build an immutable held-first union with dual provenance and per-ticker `DATA_INCOMPLETE/HOLD`, while preserving the account-level global mutation block. [VERIFIED: phase context D-09..D-12] |
| EXIT-01 | Operator can run one daily LLM BUY/HOLD/SELL evaluation while deterministic stop-loss, take-profit, and kill rules monitor held positions intraday without repeated LLM calls. | Persist one daily evaluation identity and immutable input before provider invocation; make intraday `check/watch` call only the existing pure risk reducer. [VERIFIED: codebase grep and phase context D-13..D-24] |
| EXIT-02 | SELL orders, partial fills, cancellations, ambiguous acknowledgements, restarts, and duplicate invocations reconcile to broker truth without overselling or blind resubmission. | Reuse single-shot POST and intent/submission identities; add full cancellation normalization, open-SELL suppression, account lease, recovery-only startup, and broker-authoritative post-fill position refresh. [VERIFIED: codebase grep and phase context D-25..D-40] |
</phase_requirements>

## Summary

Phase 11 should be planned as an extension of the existing KIS and audit contracts, not as a replacement execution engine. The repository already has complete-page query primitives, normalized broker snapshot types, a single-shot POST boundary, intent/submission identities, duplicate suppression, ambiguity freezes, partial-fill comparison, deterministic risk rules, immediate SQLite commits, and injectable synchronous Typer orchestration. [VERIFIED: `trading_bot/kis_order.py`, `soak_reconcile.py`, `kis_broker.py`, `risk.py`, `sqlite_audit.py`, and `cli.py`]

Two foundation gaps must be closed before orchestration. First, `collect_broker_snapshot()` currently discards orders, fills, and holdings unrelated to campaign-touched references, so it cannot represent whole-account portfolio truth. Second, the KIS daily-order allowlist does not retain the official cancellation fields (`cncl_yn`, cancellation-confirmed quantity, rejection quantity), so cancellation cannot yet be normalized as a determinate terminal state. [VERIFIED: codebase grep] [CITED: https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_daily_ccld/chk_inquire_daily_ccld.py]

The central architecture should be one account-scoped portfolio snapshot service and one account-scoped mutation coordinator shared by `bot run`, intraday `check`, and foreground `watch`. Every order-capable cycle begins with newly queried complete broker truth; every POST repeats affected-ticker truth plus quote checks; all state is linked by immutable identities. Daily LLM evaluation is a separate once-per-trading-date ledger, while intraday checks never construct or call an LLM. [VERIFIED: phase context D-01..D-40]

**Primary recommendation:** implement in dependency order: account snapshot normalization and persistence → lease/recovery primitives → once-daily held-first evaluation → shared SELL lifecycle coordinator → one-shot intraday check → foreground watch/state-transition alerts → CLI/runbook integration and full safety matrix.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| KIS account snapshot and per-ticker pre-POST refresh | API / Backend | External KIS service | Broker queries and normalization belong at the authenticated adapter/service boundary; raw provider payloads must not enter domain/audit layers. [VERIFIED: existing adapter boundaries] |
| Portfolio/evaluation/order/lease evidence | Database / Storage | API / Backend | SQLite owns restart-persistent identities and append-only observations; services own validation and transitions. [VERIFIED: existing audit pattern] |
| Held-first universe and execution gates | API / Backend | Database / Storage | This is deterministic orchestration over broker, screen, risk, and prior daily-evaluation facts. [VERIFIED: phase context D-09..D-16] |
| Intraday risk checks and watch loop | API / Backend | CLI / Client | Pure rules run in backend services; Typer only starts/stops and renders the foreground workflow. [VERIFIED: `risk.py` and `cli.py`] |
| Mutation exclusion and recovery | API / Backend | OS / Storage | A process-lifetime OS lock prevents concurrent local mutation; SQLite records durable ownership/recovery evidence. [CITED: https://docs.python.org/3.12/library/fcntl.html] [CITED: https://www.sqlite.org/lang_transaction.html] |
| Operator alerts and terminal output | CLI / Client | Database / Storage | Rendering/transport is operator-facing; attempt evidence and dedup state remain durable. [VERIFIED: existing notification boundary] |

## Project Constraints (from AGENTS.md)

- Use Python; the bot is Korea-market specific and uses KIS/pykrx. [VERIFIED: `AGENTS.md`]
- LLM output remains strict JSON `{"decision","confidence","reason"}`; malformed output fails safe with no trade. [VERIFIED: `AGENTS.md`]
- KIS mock remains the first target; real-money promotion is a separate deliberate gate. [VERIFIED: `AGENTS.md`]
- BUY requires confidence at least `0.8`; HOLD and lower-confidence BUY do not trade. [VERIFIED: `AGENTS.md`]
- Reuse the existing direct KIS adapter/runtime contracts found in the codebase; do not introduce a second order client during this phase. [VERIFIED: codebase and existing architecture instruction]
- Use existing Typer, frozen dataclass, stdlib SQLite, pydantic settings, structured logging, and pytest conventions. [VERIFIED: `AGENTS.md`, `pyproject.toml`, and codebase grep]
- Treat Naver/news text as untrusted, delimited LLM context; portfolio numeric facts must not weaken that prompt-injection boundary. [VERIFIED: `AGENTS.md` and `prompts.py`]
- Preserve manual operation: no scheduler, service, boot-time process, automatic cancel, automatic policy write, or automatic real-money promotion. [VERIFIED: `AGENTS.md` and phase context]
- Before repository edits, work must be entered through GSD; this research was started through `init.phase-op 11`. [VERIFIED: `AGENTS.md` and command evidence]
- No additional project skill rule applies: project skills are routing commands invoked only when explicitly requested; they do not define Phase 11 implementation conventions. [VERIFIED: `.agents/skills/*/SKILL.md`]

## Standard Stack

### Core

| Library / Runtime | Version | Purpose | Why Standard |
|-------------------|---------|---------|--------------|
| Python | project `>=3.10`; host `3.14.3` | Runtime, synchronous loop, signal handling, `fcntl`, SQLite | Already required and installed; Phase 11 needs no new runtime. [VERIFIED: `pyproject.toml` and environment probe] |
| stdlib `sqlite3` | SQLite `3.51.3` on host | Lease metadata, daily evaluation identity, portfolio snapshot and watch evidence | Existing audit store is WAL-backed with immediate commits; explicit short transactions support atomic acquisition/state transitions. [VERIFIED: environment probe and `sqlite_audit.py`] [CITED: https://docs.python.org/3.12/library/sqlite3.html#transaction-control] |
| stdlib `fcntl` | Python stdlib | Non-blocking, process-lifetime, single-host account mutation lock | `flock` exposes exclusive and non-blocking lock operations and releases kernel-held ownership with the process/file descriptor lifecycle. Use only for the current POSIX host boundary; distributed coordination is deferred. [CITED: https://docs.python.org/3.12/library/fcntl.html] |
| `tenacity` | `9.1.4` pinned | Bounded retry/backoff for KIS GET and in-logical-evaluation LLM calls | Already used for query/provider retries; never apply it to order POST. [VERIFIED: `pyproject.toml`, `kis_order.py`, `llm_provider.py`] |
| `typer` | `0.26.8` pinned | `run`, `intraday check`, and foreground `intraday watch` commands | Existing synchronous operator CLI and injection pattern. [VERIFIED: `pyproject.toml` and `cli.py`] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pydantic` / `pydantic-settings` | `2.13.4` / `2.11.0` | Positive cadence/retry/threshold configuration and strict provider models | Validate watch cadence, reconciliation bounds, and existing secret-bearing settings. [VERIFIED: `pyproject.toml` and `config.py`] |
| `pytest` | `8.4.2` | Unit, SQLite integration, command, restart, and interruption tests | Existing suite; no new test framework. [VERIFIED: environment probe] |
| Existing KIS adapter | repository code | Complete paginated balance/daily-order queries, quote fetch, tick snap, single-shot order POST | Extend this adapter; do not add a second KIS package/client. [VERIFIED: `kis_order.py`, `kis_quote.py`, `kis_broker.py`] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `fcntl` + durable SQLite metadata | SQLite row alone | A row alone survives a crashed owner and cannot prove process death; a kernel lock supplies local liveness while SQLite preserves evidence. A short SQLite transaction is still required to serialize metadata. [CITED: Python fcntl and SQLite transaction docs] |
| foreground synchronous watch | asyncio/background daemon | Adds lifecycle/concurrency complexity and crosses the locked manual foreground boundary. [VERIFIED: phase context D-17] |
| factored Phase 9 normalizers | a second portfolio parser | A second parser risks incompatible order-state and completeness semantics. [VERIFIED: codebase architecture] |

**Installation:** none. Phase 11 should add no external package. [VERIFIED: all required primitives are already pinned or stdlib]

## Package Legitimacy Audit

Not applicable: no external package installation is recommended for this phase. [VERIFIED: Standard Stack]

## Architecture Patterns

### System Architecture Diagram

```text
Operator
  ├─ bot run ────────────────┐
  ├─ bot intraday check ─────┼─> acquire account OS lock + durable lease
  └─ bot intraday watch ─────┘             │
                                           v
                               recovery-only gate on startup
                                │ clear             │ unresolved
                                v                   └─> reconcile/terminalize -> stop
                  complete paginated KIS account snapshot
                    balance + orders/fills + local unresolved lookback
                                │
                    incomplete? ├─ yes -> audit BLOCK, no POST
                                v no
                  persist immutable snapshot + divergence facts
                                │
         ┌──────────────────────┴────────────────────────┐
         │ daily run                                     │ intraday iteration
         v                                               v
 held-first union with screened candidates       held positions + fresh quotes
         │                                               │
 daily evaluation exists?                         pure stop/take risk reducer
   ├─ yes -> reuse immutable signal                      │
   └─ no  -> persist STARTED -> bounded LLM -> FINAL     │
         └──────────────────────┬────────────────────────┘
                                v
                       shared exit/order coordinator
          current session + lease + audit + freeze + open-SELL gates
                                │
                  affected-ticker KIS refresh + fresh quote
                                │
                truth changed? recalculate and re-gate decision
                                │
          no existing OPEN/PARTIAL SELL -> single limit SELL POST
                                │
                 accepted / ambiguous / partial / terminal
                                v
          append order + reconciliation + transition-notification evidence
```

The diagram is a direct decomposition of D-01 through D-40. [VERIFIED: phase context]

### Recommended Project Structure

```text
trading_bot/
├── portfolio.py          # account snapshot models, completeness, divergence, held-first union
├── portfolio_store.py    # snapshot/evaluation/watch evidence migrations and writers
├── mutation_lease.py     # account file lock + durable lease/heartbeat/recovery metadata
├── exit_manager.py       # shared daily/intraday SELL gates and broker reconciliation
├── intraday.py           # one-shot iteration and foreground watch state machine
├── kis_order.py          # factored page queries + cancellation-field allowlist
├── kis_broker.py         # single-shot POST and intent/submission event boundary
├── cli.py                # thin Typer wiring only
└── audit_models.py       # stable new run/reason/order/alert vocabularies
tests/
├── test_portfolio.py
├── test_portfolio_store.py
├── test_mutation_lease.py
├── test_exit_manager.py
├── test_intraday.py
└── test_phase11_cli.py
```

Keep the pure domain/reducer modules separate from KIS and SQLite adapters so most state matrices run without credentials or wall-clock sleeps. [VERIFIED: existing `risk.py`, replay, and injected CLI patterns]

### Pattern 1: Complete Account Snapshot as a Capability Token

**What:** a frozen `PortfolioSnapshot` is executable only when every page and required normalized field is complete. It contains the observation identity/time/window, holdings, account cash, all recent orders/fill aggregates, and any older individually queried unresolved orders. [VERIFIED: phase context D-01..D-08]

**Implementation:** factor page-to-domain normalization out of `collect_broker_snapshot()`. Provide two projections over the same normalized pages: `ACCOUNT` retains the complete account rows required for Phase 11; `TOUCHED` preserves Phase 9 campaign minimization. Never make Phase 9 broader by accident. [VERIFIED: current `collect_broker_snapshot()` touched filtering]

**Required completeness checks:** page cap not exhausted; continuation tokens not repeated; response success; every row shape valid; required holding fields valid; required cash fields valid; order/fill status normalizable; local unresolved intent coverage determinate. Zero holdings or zero orders is valid only when a complete page sequence explicitly returns zero rows. [VERIFIED: existing `BrokerPageEnvelope`, `PageCompleteness`, and locked D-01]

### Pattern 2: Held-First Attributable Union

**What:** build immutable `EvaluationTarget` records keyed by ticker. Sort broker holdings by ticker for deterministic held-first processing; append screened-only candidates in screener rank order. An overlap has `provenance=(HELD, SCREENED)` and one evaluation ID. [VERIFIED: phase context D-09..D-10; deterministic ordering is a recommended implementation choice]

**Critical boundary:** incomplete per-ticker market context becomes a persisted `DATA_INCOMPLETE/HOLD`; it does not delete the holding or stop sibling tickers. Incomplete account truth is different and blocks mutation globally. [VERIFIED: phase context D-12]

### Pattern 3: Durable Once-Daily Evaluation Ledger

**What:** enforce a unique `(KRX trading date, ticker)` evaluation header and append evaluation events. Persist the immutable canonical input snapshot and hash before the first provider attempt. Persist `FINAL_SIGNAL` or `FINAL_LLM_UNAVAILABLE_HOLD` once. Later invocations only load the final record. [VERIFIED: phase context D-13..D-16]

**Crash rule:** if recovery finds `STARTED` without a final event, append `FINAL_LLM_UNAVAILABLE_HOLD` and do not call the provider again that date. This can conservatively forfeit an evaluation when a crash occurred before the remote call, but it is the only local design that proves no repeated post-crash LLM call without provider idempotency. [VERIFIED: fail-closed derivation from D-13..D-15]

**Signal reuse rule:** reuse only the parsed strict signal and its immutable input evidence. Always recompute risk, broker quantity, cash/position caps, quote freshness, freezes, lease ownership, and duplicate/open-order gates. [VERIFIED: phase context D-15..D-16]

### Pattern 4: Hybrid Local Lease with Recovery Gate

**What:** acquire a non-blocking exclusive `flock` on an account-scoped lock file and then atomically insert/transition a durable SQLite lease row inside a short write transaction. Keep the file descriptor open for the mutable command lifetime; record a random owner token, bounded PID/command/start/heartbeat metadata, and current cycle ID. [CITED: https://docs.python.org/3.12/library/fcntl.html] [CITED: https://www.sqlite.org/lang_transaction.html]

**Why two layers:** the kernel lock rejects a live concurrent local process and naturally ceases ownership when its descriptor/process ends; SQLite preserves the abandoned owner and recovery trail across restart. Heartbeat age is observational only. Reclaim requires obtaining the OS lock, terminalizing abandoned cycles, completing broker reconciliation, and writing a recovery transition before enabling POST. [VERIFIED: phase context D-25..D-28]

**Transaction rule:** use `BEGIN IMMEDIATE`, conditional write, `COMMIT`, and a zero/short busy timeout for fail-fast acquisition. Do not keep a SQLite transaction open during network calls or the watch lifetime. SQLite permits only one simultaneous writer and `BEGIN IMMEDIATE` can fail busy when another writer exists. [CITED: https://www.sqlite.org/lang_transaction.html]

### Pattern 5: One Shared SELL Lifecycle Coordinator

**What:** daily LLM SELL and intraday risk SELL produce an `ExitTrigger`, then pass through the same gates and intent/submission/reconciliation machinery. [VERIFIED: phase context D-29..D-36]

**Order rule:** if any same-ticker SELL is `OPEN` or `PARTIAL`, observe/reconcile it and submit nothing. Otherwise the candidate quantity is the newest KIS `orderable_quantity`; re-fetch affected-ticker truth and a fresh quote, compare against the cycle snapshot, recompute and re-gate, snap to tick, then call the existing single-shot POST exactly once. [VERIFIED: phase context D-02..D-03 and D-29..D-35]

**Partial/cancel rule:** never update holdings by local arithmetic for authority. A later complete KIS snapshot owns remaining quantity and average price. Retain `cncl_yn`, `cnc_cfrm_qty`, `rjct_qty`, remaining quantity, original order number, order date/time, and broker order identity so operator cancellation becomes determinate. Preserve the repository's existing `CANCELLED` stable spelling or migrate with an explicit compatibility alias for context `CANCELED`; do not silently split the state. [VERIFIED: existing `_TERMINAL_STATES`; official KIS field mapping cited below]

### Pattern 6: Audited Foreground Watch State Machine

**What:** `watch` is a loop of independent iteration services, not one long database transaction. The loop states are `PREFLIGHT_READ_ONLY`, `RECOVERY_ONLY`, `ACTIVE`, `RECONCILE_ONLY`, `STOPPING`, and `TERMINAL`. Each iteration gets its own run/cycle identity and terminal outcome. [VERIFIED: phase context D-17..D-24]

**Timing:** default and minimum cadence should both be 60 seconds for Phase 11; allow a larger operator value. This directly preserves the locked conservative default and avoids inventing a faster unvalidated rate. [VERIFIED: phase context D-18]

**Shutdown:** install a main-thread SIGINT handler that only flips a stop-request flag. At safe checkpoints, stop new POSTs, persist `INTERRUPTED`, reconcile submitted orders for a bounded 60-second window using the existing 5-second/12-observation ambiguity policy, persist unresolved state, release durable lease state, then close the file lock. Python documents that `KeyboardInterrupt` can occur at unpredictable points and recommends explicit signal handling for high-reliability graceful shutdown. [CITED: https://docs.python.org/3.12/library/signal.html#note-on-signal-handlers-and-exceptions] [VERIFIED: existing 60/5/12 policy in `cli.py`]

### Pattern 7: State-Transition Alert Projection

**What:** derive `state_identity = canonical_hash(account_scope, ticker, event_family, normalized_state, subject_order_id)` and persist first-seen, last-seen, occurrence count, active/recovered status, severity, and last notification result. Notify only on begin/change/recovery. [VERIFIED: phase context D-37..D-40; canonical hashing is an existing project pattern]

**Recommended threshold:** emit `LONG_OPEN_ORDER` WARNING after 15 minutes and then remain quiet until state changes; the exact duration is an operator-policy heuristic and must be visible in the policy snapshot. [ASSUMED]

### Anti-Patterns to Avoid

- **Calling `collect_broker_snapshot()` unchanged:** it filters to touched references and can omit held positions, violating PORT-01/02. [VERIFIED: codebase grep]
- **Treating an empty local row set as no broker order:** only a complete KIS page sequence can establish absence. [VERIFIED: Phase 9 ambiguity policy]
- **Subtracting open SELL twice:** do not infer that `orderable_quantity` excludes or includes reservations and then also submit a remainder; D-31 says any OPEN/PARTIAL SELL means no new POST. [VERIFIED: phase context D-29..D-31]
- **Using old snapshot state after restart:** snapshots are audit evidence only after process/cycle end. [VERIFIED: D-04]
- **Catching `Exception` and expecting Ctrl-C cleanup:** `KeyboardInterrupt` inherits `BaseException`, and asynchronous delivery can interrupt unsafe points. Use a shutdown flag and controlled checkpoints. [CITED: https://docs.python.org/3.12/library/exceptions.html#KeyboardInterrupt]
- **Holding a SQLite write transaction across KIS/LLM calls:** it blocks other audit writers and entangles network latency with lease correctness. [CITED: https://www.sqlite.org/lang_transaction.html]
- **Updating one order row in place:** append observations and transitions so original intent, submission ambiguity, partial progress, operator cancellation, and later observer attribution remain intact. [VERIFIED: existing order evidence contract]
- **Calling the LLM from `check/watch`:** intraday exits are deterministic and repeated LLM calls are prohibited. [VERIFIED: D-19]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| KIS pagination | New one-page HTTP loops per command | Factor `KisOrderAdapter._query_pages`, `BrokerPageEnvelope`, and `PageCompleteness` | Existing code already detects page caps, repeated tokens, provider/parse failure, and bounded retry. [VERIFIED: codebase] |
| Order submission retry/idempotency | Generic retry decorator or client-generated resend | Existing single-shot POST plus intent/submission identity and broker reconciliation | A timeout may mean accepted; blind retry can duplicate a real order. [VERIFIED: codebase and D-06] |
| Position arithmetic | Local fill-ledger authority | New complete KIS holding snapshot | Partial fill, operator cancel, and outside activity make local arithmetic comparison-only. [VERIFIED: D-07 and D-35] |
| Risk strategy | New watch-specific stop/take formulas | `evaluate_position_risk()` and `blocks_new_buy()` | Existing pure rules already encode stop-loss, take-profit, and BUY-only daily-loss semantics. [VERIFIED: `risk.py`] |
| KRW tick logic | New SELL price rounding | Existing `snap_to_tick()` | The order path already centralizes tick snapping and quote freshness. [VERIFIED: `kis_order.py` and `kis_broker.py`] |
| Process lock algorithm | PID file/heartbeat alone | stdlib `flock` plus SQLite evidence | PID/heartbeat age alone does not prove owner death and is forbidden as reclaim authority. [VERIFIED: D-27] [CITED: Python fcntl docs] |
| Watch scheduling | Scheduler/daemon framework | Foreground synchronous loop with injected clock/sleeper | Unattended/background operation is explicitly deferred. [VERIFIED: phase boundary] |
| Alert dedup | In-memory `set` | Durable state-identity projection | Restart must not renotify unchanged states or lose occurrence/duration evidence. [VERIFIED: D-39] |

**Key insight:** broker truth, local intent history, and process ownership are three different authorities. Planning must link them by stable IDs without allowing any one to impersonate the others. [VERIFIED: D-04, D-07, D-25..D-28]

## Common Pitfalls

### Pitfall 1: Whole-account completeness is accidentally ticker-scoped
**What goes wrong:** a touched-ticker snapshot is marked complete although an unobserved held position or open order exists elsewhere in the account. [VERIFIED: current filter behavior]
**How to avoid:** completion applies to the unfiltered page sequence; filtering is only a later projection. Persist account snapshot page counts and completeness before deriving ticker slices. [VERIFIED: Phase 9 page model]
**Warning signs:** snapshot holding count changes with `touched_refs`; a held ticker disappears when not screened. [VERIFIED: code-derived test oracle]

### Pitfall 2: Cancellation is inferred from quantity arithmetic
**What goes wrong:** a cancelled/no-fill or partial-cancel order becomes `UNKNOWN`, `NO_FILL`, or even `FILLED` because `cncl_yn` and cancellation-confirmed quantity were discarded. [VERIFIED: current allowlist gap]
**How to avoid:** retain official cancellation/rejection fields, normalize with explicit precedence, and fixture-test partial-cancel combinations. [CITED: official KIS daily-order example]
**Warning signs:** remaining quantity zero while filled quantity is below ordered quantity; cancellation flag present in raw fixture but absent from normalized evidence. [VERIFIED: normalization logic]

### Pitfall 3: Daily evaluation uniqueness is enforced only in memory
**What goes wrong:** duplicate CLI invocation or restart calls the LLM twice for the same date/ticker. [VERIFIED: current `run_cycle` has no daily evaluation ledger]
**How to avoid:** database unique key, pre-call durable STARTED event, immutable input hash, and recovery finalization without another call. [VERIFIED: D-13..D-15]
**Warning signs:** two provider call records share date/ticker; overlap HELD/SCREENED creates two identities. [VERIFIED: required invariant]

### Pitfall 4: SELL proceeds are credited before broker truth
**What goes wrong:** candidate BUY sizing assumes an accepted/open SELL released cash or position capacity. [VERIFIED: broker-authority boundary]
**How to avoid:** do not project proceeds from submitted orders. Refresh complete account truth at the held-to-candidate boundary and use KIS-observed cash/holdings only. [VERIFIED: D-07 and D-09]
**Warning signs:** available cash increases from local order price × quantity without a KIS snapshot. [VERIFIED: forbidden derivation]

### Pitfall 5: Lease acquisition is separated from evidence
**What goes wrong:** one process holds the OS lock while SQLite says another owner, or a process begins mutation before recovery evidence commits. [VERIFIED: D-25..D-28]
**How to avoid:** lock first, atomically inspect/transition durable metadata, run recovery, then transition to ACTIVE; check owner token before every POST. Release durable state before closing the descriptor on normal shutdown. [VERIFIED: recommended state machine]
**Warning signs:** heartbeat renew affects zero rows; lock is acquired with an ACTIVE prior owner and no recovery event; POST follows a failed renew. [VERIFIED: D-28]

### Pitfall 6: Watch interruption lands between intent and POST evidence
**What goes wrong:** Ctrl-C produces an untracked possible submission or releases the lease before reconciliation. [CITED: Python signal docs]
**How to avoid:** explicit shutdown flag, persist `SUBMISSION_ATTEMPTED` immediately before the single POST, treat every exception after that boundary as ambiguous, and keep the lease through bounded reconciliation. [VERIFIED: existing broker event ordering and D-23]
**Warning signs:** POST count without submission event; lease release timestamp precedes reconciliation terminalization. [VERIFIED: required ordering]

### Pitfall 7: Repeated watch failures spam alerts or hide duration
**What goes wrong:** every minute sends the same warning, or dedup suppresses evidence entirely. [VERIFIED: D-37..D-39]
**How to avoid:** append every observation, update occurrence/duration projection, notify only begin/change/recovery. [VERIFIED: D-39]
**Warning signs:** notification count equals iteration count; no first/last seen timestamps. [VERIFIED: required invariant]

## Code Examples

Verified patterns and implementation sketches:

### Atomic lease transition without a long transaction

```python
# Sources: Python 3.12 fcntl docs; SQLite transaction docs; Phase 11 D-25..D-28.
lock_file = open(account_lock_path, "a+")
fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

conn.execute("BEGIN IMMEDIATE")
try:
    prior = load_lease(conn, account_scope)
    lease = record_acquiring(conn, prior=prior, owner_token=owner_token)
    conn.commit()
except BaseException:
    conn.rollback()
    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
    lock_file.close()
    raise

# Recovery and fresh KIS reconciliation happen with no SQLite write transaction open.
# Only after they pass does a second short transaction mark the lease ACTIVE.
```

### Held-first attributable union

```python
# Source: Phase 11 D-09/D-10; deterministic ordering follows project patterns.
targets: dict[str, EvaluationTarget] = {}
for holding in sorted(snapshot.holdings, key=lambda item: item.ticker):
    targets[holding.ticker] = EvaluationTarget(
        ticker=holding.ticker,
        provenance=("HELD",),
        holding=holding,
    )
for candidate in screened_in_rank_order:
    previous = targets.get(candidate.ticker)
    if previous is None:
        targets[candidate.ticker] = EvaluationTarget(
            ticker=candidate.ticker,
            provenance=("SCREENED",),
            candidate=candidate,
        )
    else:
        targets[candidate.ticker] = replace(
            previous, provenance=("HELD", "SCREENED"), candidate=candidate
        )
```

### Once-daily provider boundary

```python
# Source: Phase 11 D-13..D-16.
evaluation = store.reserve_evaluation(
    trading_date=trading_date,
    ticker=ticker,
    immutable_input=input_snapshot,
)
if evaluation.final_event is not None:
    return evaluation.final_signal  # no provider call
if evaluation.recovered_started_event:
    return store.finalize_unavailable_hold(evaluation.id, "ABANDONED_EVALUATION")

try:
    signal = provider.generate_signal(context)  # provider owns bounded retries
except LLMProviderError:
    return store.finalize_unavailable_hold(evaluation.id, "LLM_UNAVAILABLE")
return store.finalize_signal(evaluation.id, signal)
```

### SELL suppression and latest-quantity rule

```python
# Source: Phase 11 D-29..D-35.
if ticker_truth.open_sell is not None:
    return reconcile_only(ticker_truth.open_sell)
if exit_trigger.action != "SELL" or ticker_truth.orderable_quantity <= 0:
    return hold("NO_ORDERABLE_QUANTITY")

refreshed = portfolio.refresh_ticker_with_quote(ticker)
if not refreshed.complete or not refreshed.quote_fresh:
    return block("PRE_POST_TRUTH_INCOMPLETE")
if not exit_trigger.still_valid(refreshed):
    return hold("EXIT_NO_LONGER_ACTIONABLE")
return broker.place_order(limit_sell(refreshed.orderable_quantity, refreshed.quote))
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Single-page account/order inquiry | Continue through KIS `CTX_AREA_FK100`/`CTX_AREA_NK100` while `tr_cont` indicates more pages, with an explicit page cap | Current official KIS examples created 2025-06-01 | Whole-account truth cannot be claimed from only the first page; mock daily-order inquiry may return only 15 rows per call. [CITED: official KIS examples] |
| Legacy recent-order TR IDs | `TTTC0081R` real / `VTTC0081R` demo for within-three-month daily order/fill inquiry | Current official KIS examples | Preserve the accepted Phase 9 profile and do not regress to repository legacy candidates. [CITED: official KIS daily-order example] [VERIFIED: codebase profile] |
| Python pre-3.12 transaction defaults as implicit knowledge | Explicitly choose transaction behavior; Python 3.12 introduced `autocommit` control and recommends explicit transaction management | Python 3.12 | Lease transitions should not rely on interpreter-default transaction behavior. [CITED: Python 3.12 sqlite3 docs] |
| Catch `KeyboardInterrupt` around an arbitrary long loop | Explicit main-thread SIGINT handler requests controlled shutdown | Current Python reliability guidance | Prevent new POSTs at a checkpoint, then reconcile and release in known order. [CITED: Python 3.12 signal docs] |

**Deprecated/outdated:**
- The unchanged touched-only Phase 9 projection is not a portfolio snapshot. Keep it for campaign reconciliation, but factor shared normalization. [VERIFIED: codebase]
- `TTTC8001R`/legacy daily-query assumptions should not be introduced into new Phase 11 code; use the already accepted `0081R` profile family. [CITED: official KIS example] [VERIFIED: `MOCK_TR_PROFILE_CANDIDATES`]
- In-memory tracked positions in `KISBroker` are not broker authority after partial fill/restart. Hydrate/replace them from each complete portfolio snapshot. [VERIFIED: D-04, D-07, D-35]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | A long-open-order WARNING threshold of 15 minutes is operationally useful. | Architecture Pattern 7 | Warning may be too noisy or too slow; expose it in policy evidence and let the planner/user adjust before implementation. |

All other design choices are locked decisions, verified repository patterns, or cited primary documentation. [VERIFIED: sources listed below]

## Open Questions

1. **Does authenticated KIS mock cancellation evidence populate `cncl_yn` and `cnc_cfrm_qty` consistently for partial cancel?**
   - What we know: the official field catalog includes them, but current authenticated fixtures focus on empty/partial/no-fill paths. [CITED: official KIS example] [VERIFIED: tests/fixtures]
   - Recommendation: add deterministic fixtures immediately and an operator-gated mock observation test; normalization must remain UNKNOWN rather than guessing if required cancellation fields conflict.

2. **Should portfolio snapshots live in the primary audit DB or an independent projection DB?**
   - What we know: both are permitted; primary audit already owns execution cycles and immediate evidence, while Phase 9 uses independently versioned broker snapshot evidence. [VERIFIED: phase context and codebase]
   - Recommendation: use the primary audit DB for lease, daily evaluation, iteration, and exact snapshot links, but give portfolio snapshot tables their own schema version and append-only rows. This avoids cross-database mutation gating while preserving an independently evolvable projection.

3. **How should the persistent historical `000660` Phase 9 ambiguity affect the account-wide Phase 11 lease?**
   - What we know: it remains a same-ticker freeze and promotion blocker; D-08 says unattributable unresolved order risk blocks mutation. [VERIFIED: STATE.md and phase context]
   - Recommendation: the Phase 11 startup comparison must classify it. If complete current KIS truth cannot uniquely attribute/terminalize it, block account mutation rather than merely hiding the ticker, because D-08 is stricter than Phase 8's local-only ticker freeze.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python | All Phase 11 code | ✓ | 3.14.3 host; project supports >=3.10 | Use project-supported Python 3.12+ environment for deployment parity. [VERIFIED: probe and pyproject] |
| SQLite | Audit/lease/evaluation evidence | ✓ | 3.51.3 | None needed. [VERIFIED: probe] |
| `fcntl` | Current-host process lock | ✓ | Python stdlib on current POSIX host | SQLite fail-closed lease only if porting to non-POSIX; cross-platform/distributed lock design is outside Phase 11. [VERIFIED: import availability implied by POSIX host; cited docs] |
| pytest | Validation | ✓ with project `PYTHONUSERBASE` | 8.4.2 | Use configured full-suite command. [VERIFIED: probe] |
| KIS mock credentials/service | Authenticated integration/UAT | Not probed during research | external | Unit fixtures and injected adapters cover automation; authenticated cancellation/portfolio proof remains a human gate. [VERIFIED: safety boundary] |

**Missing dependencies with no fallback:** authenticated KIS mock access is required only for the final external proof, not for implementation/unit planning. [VERIFIED: Phase 9 precedent]

**Missing dependencies with fallback:** global Python site-packages do not contain project dependencies, but the configured `.python-userbase` does; use `PYTHONUSERBASE="$PWD/.python-userbase"`. [VERIFIED: environment probe]

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.4.2 [VERIFIED: environment probe] |
| Config file | `pyproject.toml` [VERIFIED: codebase] |
| Quick run command | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_portfolio.py tests/test_mutation_lease.py tests/test_exit_manager.py tests/test_intraday.py tests/test_phase11_cli.py -x` |
| Full suite command | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` [VERIFIED: `.planning/config.json`] |

The current baseline is green: 97 focused tests pass across risk, KIS order/broker, soak reconciliation, and CLI suites, and the full repository suite passes 732 tests. [VERIFIED: test runs on 2026-09-02]

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| PORT-01 | Complete all balance/order pages; normalize cash/holdings/orderable/average/open/fills/cancel; any missing dimension blocks mutation; pre-POST refresh re-gates | unit + integration | `python3 -m pytest -q tests/test_portfolio.py tests/test_kis_order.py -x` | ❌ Wave 0 (`test_portfolio.py`) |
| PORT-02 | Held-first stable union; overlap evaluated once with dual provenance; held market failure becomes attributable HOLD; account failure blocks all orders | unit + orchestration | `python3 -m pytest -q tests/test_portfolio.py tests/test_phase11_cli.py -x` | ❌ Wave 0 |
| EXIT-01 | Unique daily evaluation, same-day signal reuse, crash-finalized HOLD, intraday no-LLM, stop/take exits, session/cadence/cutoff behavior | unit + integration | `python3 -m pytest -q tests/test_intraday.py tests/test_exit_manager.py tests/test_risk.py -x` | ❌ Wave 0 |
| EXIT-02 | Account lease race/loss/reclaim, open-SELL suppression, partial/cancel/ambiguous/restart reconciliation, no blind retry/oversell | unit + integration + CLI | `python3 -m pytest -q tests/test_mutation_lease.py tests/test_exit_manager.py tests/test_phase11_cli.py tests/test_kis_broker.py -x` | ❌ Wave 0 |

Prefix focused commands with `PYTHONUSERBASE="$PWD/.python-userbase"` in this environment. [VERIFIED: environment probe]

### Required Test Matrices

1. **Portfolio completeness:** zero/one/multiple pages; mock 15-row continuation; repeated token; page cap; missing output1/output2; malformed numeric; zero holdings; missing cash; local unresolved older than window; divergence severity. [VERIFIED: KIS and Phase 9 contracts]
2. **Order state:** OPEN, NO_FILL, PARTIAL, FILLED, CANCELED/CANCELLED, partial-cancel, REJECTED, EXPIRED, conflicting fields, monotonic cumulative fills, missing broker order. [VERIFIED: EXIT-02 scope]
3. **Daily identity:** held-only, screened-only, overlap; two invocations; provider retry within one identity; final timeout; crash after STARTED; signal reuse with changed broker truth; date rollover. [VERIFIED: D-13..D-16]
4. **Lease:** simultaneous processes (multiprocessing, not threads only); active rejection; owner metadata bounds; heartbeat renewal; token mismatch/loss; crash releasing OS lock but leaving durable row; recovery success; unresolved recovery block; no wait/steal. [VERIFIED: D-25..D-28]
5. **Watch timeline:** pre-open read-only; continuous activation; incomplete iteration then recovery; 15:20 mutation cutoff; 15:20-15:30 reconcile-only; 15:30 exit; Ctrl-C before intent, after intent, during POST ambiguity, during reconciliation; lease loss. [VERIFIED: D-17..D-24]
6. **No oversell:** open SELL blocks every new SELL/BUY; partial fill remains reconcile-only; operator cancellation permits only a later independent cycle; latest orderable quantity controls; no local fill arithmetic authority. [VERIFIED: D-29..D-35]
7. **Alerts/evidence:** begin/change/recovery only; repeated occurrence/duration; transport failure fail-soft; evidence persistence failure blocks POST; bounded Korean text and severity. [VERIFIED: D-37..D-40]

### Sampling Rate

- **Per task commit:** focused new module test plus directly affected upstream suite, target under 30 seconds. [VERIFIED: current focused suite is 1.36s]
- **Per wave merge:** Phase 11 focused suite plus `test_kis_order.py`, `test_kis_broker.py`, `test_soak_reconcile.py`, `test_cli.py`, and `test_sqlite_audit.py`.
- **Phase gate:** full suite green, then authenticated mock portfolio/cancellation/partial-fill operator UAT before `$gsd-verify-work`. [VERIFIED: project safety posture]

### Wave 0 Gaps

- [ ] `tests/test_portfolio.py` — account scope, completeness, union, divergence, cancellation normalization (PORT-01/02)
- [ ] `tests/test_portfolio_store.py` — schema migration, immutable snapshots, unique daily evaluation, recovery (PORT-01, EXIT-01)
- [ ] `tests/test_mutation_lease.py` — real cross-process exclusion and recovery ordering (EXIT-02)
- [ ] `tests/test_exit_manager.py` — shared daily/intraday SELL lifecycle and no-oversell matrix (EXIT-01/02)
- [ ] `tests/test_intraday.py` — injected clock/sleeper/signal watch timelines (EXIT-01/02)
- [ ] `tests/test_phase11_cli.py` — command construction, no-LLM intraday proof, exit codes, terminal evidence (all requirements)
- [ ] Extend `tests/test_kis_order.py` with official cancellation fields and page-boundary fixtures (PORT-01, EXIT-02)
- [ ] Extend `tests/test_kis_broker.py` to prove pre-POST portfolio refresh ordering and no second POST for open/partial SELL (EXIT-02)
- [ ] Add operator-runbook command contract tests and authenticated mock UAT checklist (EXIT-01/02)

No test framework installation is needed. [VERIFIED: pytest availability]

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Reuse `KisTokenManager`, selected credential group, mock/real separation, and no credential persistence in Phase 11 tables. [VERIFIED: existing code] |
| V3 Session Management | no for user sessions | There is no web/user session; KIS token lifecycle remains the existing adapter's responsibility. [VERIFIED: architecture] |
| V4 Access Control | yes | Mutation authority requires mock/real preflight, account lease ownership, recovery clear, complete truth, session open, and existing execution confirmation. [VERIFIED: phase context and preflight] |
| V5 Input Validation | yes | Allowlisted KIS fields, strict numeric/ticker/status normalization, Pydantic settings, canonical enums, bounded sanitized evidence. [VERIFIED: codebase pattern] |
| V6 Cryptography | yes | Use existing TLS provider clients/token handling and standard SHA-256 only for non-secret identity hashes; never invent encryption or log credentials. [VERIFIED: codebase pattern] |
| V7 Error/Logging | yes | Stable codes, sanitized scalar details, no raw KIS/LLM payloads or secrets, immediate evidence writes. [VERIFIED: `sanitize_detail` and D-37..D-40] |
| V12 Files/Resources | yes | Account lock file must be created in an application-owned data directory with restrictive permissions and no raw account number in its name. [CITED: Python fcntl docs; security recommendation] |

### Known Threat Patterns for This Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Concurrent `run/check/watch` overspends or oversells | Tampering | Account-scoped non-blocking OS lock, durable owner token, pre-POST ownership check, complete broker refresh. [VERIFIED: D-25..D-28] |
| TOCTOU between snapshot and POST | Tampering | Fresh affected-ticker truth and quote immediately before POST; recalculate and re-run gates. [VERIFIED: D-02..D-03] |
| Timeout interpreted as rejection and retried | Spoofing/Tampering | Single POST, ambiguous terminal event, freeze, broker inquiry, no blind resubmission. [VERIFIED: existing broker and D-06] |
| Malformed/hostile KIS payload becomes authority | Tampering | Allowlist and strict completeness; UNKNOWN/BLOCK on missing/conflicting fields; never persist raw response. [VERIFIED: existing normalizer] |
| News prompt injection influences control flow | Elevation of privilege | Continue explicit `<untrusted_news>` delimiting; portfolio facts are rendered as fixed numeric fields outside news and cannot carry instructions. [VERIFIED: `prompts.py`] |
| Lease metadata leaks account/credentials | Information disclosure | Persist only account scope hash/suffix and bounded owner metadata; never raw CANO, token, app key, request/response. [VERIFIED: sanitize boundary] |
| Audit/notification evidence failure hidden | Repudiation | Immediate commits; evidence-write failure blocks new POST; transport failure remains visible and fail-soft. [VERIFIED: D-40] |
| Stale/replayed daily signal overrides current safety | Replay/Tampering | Date-scoped identity plus mandatory current broker/risk/quote/lease/freeze gates on every reuse. [VERIFIED: D-15..D-16] |

## Planning Recommendation

Use six plans with explicit dependency ordering:

1. **Portfolio foundation:** factor paginated normalization, add cancellation fields/status precedence, whole-account snapshot models, completeness/divergence, persistence, and fixtures. Covers PORT-01 foundation.
2. **Mutation lease and recovery:** hybrid OS/SQLite account lease, owner-loss semantics, abandoned cycle terminalization, broker recovery gate, and multiprocessing tests. Covers EXIT-02 foundation.
3. **Daily universe/evaluation:** held-first union, richer held context, immutable once-daily evaluation ledger, signal reuse, per-ticker data-incomplete HOLD, and held-to-candidate cash refresh. Covers PORT-02/EXIT-01.
4. **Shared exit coordinator:** daily/intraday trigger model, latest orderable SELL quantity, open-SELL suppression, pre-POST recheck, single POST, partial/cancel/ambiguous lifecycle. Covers EXIT-01/EXIT-02.
5. **Intraday commands/watch:** one-shot check, foreground loop, session phases, injected clock/sleeper, SIGINT shutdown, reconciliation-only cutoff, iteration evidence. Covers EXIT-01.
6. **Alerts/operator integration:** state transition projection, severity/Korean rendering, fail-soft transport/fail-closed evidence, runbook/status/report updates, full regression and authenticated mock checklist. Completes all four requirements.

Do not combine Plan 1 with watch CLI work: downstream orchestration is unsafe until account-scope completeness and cancellation normalization are proven. Do not combine lease acquisition with recovery: acquiring a kernel lock is only the start of recovery, not mutation authorization. [VERIFIED: codebase gaps and D-24..D-28]

## Sources

### Primary (HIGH confidence repository evidence)
- `11-CONTEXT.md` — locked portfolio, evaluation, intraday, lease, SELL, and alert decisions. [VERIFIED: local file]
- `AGENTS.md`, `REQUIREMENTS.md`, `ROADMAP.md`, `STATE.md` — project constraints, PORT/EXIT scope, sequencing, unresolved ambiguity. [VERIFIED: local files]
- `trading_bot/kis_order.py`, `kis_broker.py`, `soak_reconcile.py`, `execution.py`, `risk.py`, `cli.py`, `sqlite_audit.py`, `audit_models.py` — current implementation contracts and gaps. [VERIFIED: codebase grep/read]
- Relevant tests and `docs/operator-runbook.md` — existing behavioral and operator contracts. [VERIFIED: codebase]

### Secondary (MEDIUM confidence official documentation via verified web search)
- https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_balance/inquire_balance.py — balance endpoint, current TR IDs, continuation and page accumulation. [CITED]
- https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_balance/chk_inquire_balance.py — holdings/cash field meanings. [CITED]
- https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_daily_ccld/inquire_daily_ccld.py — daily order/fill endpoint, query window, current TR IDs, continuation, mock/real page sizes. [CITED]
- https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_daily_ccld/chk_inquire_daily_ccld.py — order, cumulative fill, cancellation, rejection, and remaining fields. [CITED]
- https://docs.python.org/3.12/library/sqlite3.html#transaction-control — explicit transaction control. [CITED]
- https://www.sqlite.org/lang_transaction.html — one-writer behavior and `BEGIN IMMEDIATE`. [CITED]
- https://docs.python.org/3.12/library/fcntl.html — exclusive/non-blocking file locks. [CITED]
- https://docs.python.org/3.12/library/signal.html#note-on-signal-handlers-and-exceptions — controlled signal shutdown guidance. [CITED]
- https://docs.python.org/3.12/library/exceptions.html#KeyboardInterrupt — interrupt semantics and `BaseException` inheritance. [CITED]

### Tertiary (LOW confidence)
- None. The single `[ASSUMED]` item is an explicitly identified operator threshold, not a library/API claim.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — no new package; versions and availability verified locally.
- Architecture: HIGH — derives from locked decisions and shipped repository seams.
- KIS field behavior: MEDIUM — official examples confirm field catalog/pagination, but authenticated mock cancellation combinations remain to be observed.
- Pitfalls: HIGH for code-derived gaps; MEDIUM for provider cancellation edge combinations.

**Research date:** 2026-09-02
**Valid until:** 2026-10-02 for repository architecture; recheck official KIS examples before authenticated UAT.
