# Project Research Summary

**Project:** Stock Trading Bot (KR / LLM-driven) — v1.1 Mock Soak & Replay Validation
**Domain:** Operational validation of a personal Korean-market LLM trading bot
**Researched:** 2026-07-11
**Confidence:** MEDIUM-HIGH

## Executive Summary

v1.1 is not a strategy-expansion milestone; it is an evidence and operational-confidence milestone around the shipped v1.0 trading core. The product must prove two different things without conflating them: deterministic offline replay validates screener, parser, risk, sizing, and execution-gate mechanics using frozen point-in-time market data and fixture signals, while a multi-day KIS mock-account soak validates the real KIS paper environment, authentication, rate limits, order submission/readback, reconciliation, restart behavior, and operator procedures. The in-memory `MockBroker` is correct for replay and tests but is not KIS 모의투자 evidence.

The recommended implementation is an additive validation layer with no new runtime dependencies unless a measured gap justifies one. Reuse Python's standard library, SQLite, Typer, pytest, the existing deterministic domain functions, and the current KIS adapters. First make audit evidence complete: every run needs a terminal lifecycle state and every attempted ticker needs a durable outcome, including skips, failures, duplicate suppression, and ambiguous orders. Only then build reports or collect soak evidence. Extract the existing orchestration into a reusable application service, but do not fork the production execution/risk rules for replay.

The key risks are false confidence from incomplete audits, look-ahead or live-provider leakage in replay, mistaking local simulation for KIS paper operation, blind retries after ambiguous order submission, stale data reaching order preflight, and overfitting tiny samples. Mitigate them with forward-only schema migrations, immutable provenance and policy snapshots, a network/LLM-free replay boundary, explicit execution-target labeling, persisted order intents plus broker-truth reconciliation, N eligible KRX trading days plus fault drills, snapshot-consistent reports, and advisory-only calibration. Real-money promotion remains a manual evidence-linked checklist with the existing confirmation gate; no replay, report, or calibration command may alter settings or enable real trading.

## Key Findings

### Recommended Stack

Add no runtime dependency for v1.1. The existing modular Python application and standard library already cover replay, evidence storage, reporting, calibration summaries, hashing, KST date handling, and CLI operation. Use small project modules rather than introducing a backtesting framework, analytics database, scheduler, notebook workflow, dashboard, or optimizer. See [STACK.md](./STACK.md) for detailed rationale.

**Core technologies:**

- Python `>=3.10`: replay/services and KST handling — preserve the current compatibility floor; v1.1 needs no newer feature.
- `sqlite3`: canonical runs, attempts/outcomes, order evidence, replay provenance, and policy snapshots — evolve the current WAL database with additive, idempotent migrations.
- Typer `0.26.8`: explicit `replay`, `report`, and `soak` operator commands — reuse the current composition root and `CliRunner` testing pattern.
- Existing pure domain core: `screen_candidates()`, signal parsing, `evaluate_signal_action()`, risk evaluation, sizing, and `execute_signal_cycle()` — one implementation must serve live, replay, and soak paths.
- Existing `MockBroker`: stateful deterministic replay simulation — allow mutation across replay epochs, but prohibit it from counting as KIS paper evidence.
- Existing KIS REST/broker layer: KIS mock-account soak — configure it through an explicit mock-only factory; do not replace it or add `python-kis` in this milestone.
- pytest `8.4.2`: deterministic fixtures, boundary matrices, migrations, CLI contracts, and fault adapters — no test plugin is required.
- Standard-library `datetime`/`zoneinfo`, `json`, `csv`, `statistics`, `hashlib`, and `pathlib`: KST grouping, stable fixtures/exports, descriptive metrics, and provenance hashes.

**Critical compatibility requirements:**

- Keep migrations and queries compatible with SQLite versions available under the Python `>=3.10` deployment floor; do not assume the research machine's newer SQLite build.
- Preserve the existing direct-REST KIS implementation and real-money confirmation tests.
- Store fixtures at the adapter boundary as versioned JSON/CSV, not pickled pandas objects.
- Keep reporting read-only and snapshot-consistent; do not run migrations implicitly from report commands.

### Expected Features

The milestone must establish operational truth before analytical polish. See [FEATURES.md](./FEATURES.md) for the full acceptance catalog.

**Must have (table stakes):**

- Canonical run lifecycle with `STARTED` and exactly one terminal state, explicit KST trading date, run kind, execution target, counts, policy snapshot, and provenance.
- One persisted terminal outcome for every attempted ticker, including HOLD, skip, malformed signal, stale-data block, provider/API error, duplicate suppression, partial fill, and ambiguous submission.
- Explicit KRX session/data-cutoff contract and fresh-data evidence rechecked immediately before order POST.
- Point-in-time replay over frozen dated inputs and versioned fixture signals, with no KIS, Naver, pykrx-current, live LLM, wall-clock, or notification access.
- Production-gate parity in replay by invoking the shipped parser, confidence threshold, risk precedence, sizing, and execution boundary.
- Deterministic replay manifest with fixture/data hashes, code revision, initial state, policy snapshot, ordered outcomes, and stable result identity.
- Explicit KIS-paper execution target that cannot select real credentials, domains, accounts, or TR IDs and is visibly distinct from local `MockBroker` simulation and dry-run.
- N-eligible-KRX-day soak campaign with clean-streak accounting, zero-tolerance safety invariants, declared availability failure budget, and broker reconciliation.
- Fault drills for stale data, malformed/timeout LLM, KIS read/POST ambiguity, duplicate rerun, partial fill, throttling, interruption, notification failure, and audit failure.
- Deterministic daily and period reports built from complete SQLite evidence, with visible denominators, incomplete/unknown states, KST dates, execution provenance, and reconciliation status.
- Operator runbook covering preflight, `status → screen → run/soak → report`, expected output, abort conditions, diagnosis, safe recovery, backup, and postflight reconciliation.
- Policy comparison as an advisory worksheet with sample counts and uncertainty, plus an evidence-linked real-money promotion checklist that preserves manual confirmation.

**Should have (high-value differentiators):**

- Candidate-funnel reporting to explain where potential trades were removed.
- Replay/soak decision-path diff that explains differences without mixing evidence classes.
- Tamper-evident provenance and a redacted one-command evidence bundle.
- Shadow-policy comparison and metamorphic safety tests.
- Forward outcome labeling and confidence-band analysis only after the outcome horizon and sufficient sample requirements are defined.

**Defer (v2+):**

- Full portfolio/P&L backtester with realistic fills, fees, slippage, corporate actions, and intraday ordering.
- Live LLM calls during historical replay.
- Automatic threshold optimization, policy writes, or mock-to-real promotion.
- Scheduler/always-on loop, intraday polling, web dashboard, and strategy expansion during a soak campaign.
- Claims that LLM `confidence=0.8` means an 80% success probability or that paper fills predict live execution quality.

### Architecture Approach

Build a small modular monolith using a functional core and imperative shell. Extract the per-ticker workflow from `cli.run_cycle` into a reusable `CycleService`; inject data, signal, broker, clock, policy, audit, and notifier collaborators. Live and KIS-soak paths use live adapters, while replay uses a point-in-time data adapter, fixture-signal provider, injected clock/IDs, and one shared `MockBroker`. Reports and calibration read immutable audit snapshots and have no write path to runtime settings. See [ARCHITECTURE.md](./ARCHITECTURE.md) for component details.

**Major components:**

1. `CycleService` plus immutable `RunSpec`/`RunResult` — execute one explicit run and finalize lifecycle/outcomes without owning CLI parsing or concrete adapters.
2. `AuditRepository` and migrations — persist run lifecycle, ticker attempts, decisions, reconciliation, policy/provenance, and query models.
3. `ReplayService`, `ReplayDataSource`, and `FixtureSignalProvider` — advance chronological point-in-time epochs with frozen inputs and zero network/LLM access.
4. `SoakService` and `KISMockBrokerFactory` — enforce mock-only KIS composition, campaign metadata, bounded manual cycles, and broker-truth reconciliation.
5. Reporting service/renderers — read one SQLite snapshot and produce stable text/Markdown plus machine-readable JSON/CSV where useful.
6. Calibration service — run transparent, bounded policy comparisons and emit recommendations only.
7. Operator runbook and real-money promotion checklist — document evidence-based decisions, abort conditions, recovery, and deliberate promotion outside the automated paths.

**Key patterns:**

- Append complete structured evidence before rendering or evaluating readiness.
- Separate `DRY_RUN`, `SIMULATED`/`MockBroker`, `KIS_MOCK`, and `KIS_REAL` as explicit axes/targets.
- Preserve one production execution/risk implementation; vary adapters, not rules.
- Enforce point-in-time availability by construction and calculate future labels only after decisions are persisted.
- Persist local order intent before POST; treat ambiguous POST outcomes as `UNKNOWN`, reconcile broker truth, and never blind-resubmit.
- Keep calibration and promotion one-way and human-controlled.

### Critical Pitfalls

1. **Incomplete or misattributed audit evidence** — migrate the schema before reports or soak collection; persist every attempt and terminal run state, make reconciliation ticker/order-specific, and enforce count invariants.
2. **Local simulation mislabeled as KIS mock soak** — display and store broker backend, KIS environment, account suffix, and execute/dry-run state; only real KIS paper API interactions count toward soak acceptance.
3. **Non-point-in-time or fixture-overfit replay** — define decision/fill epochs, freeze and hash inputs, prohibit external calls, preserve portfolio state, and use a scenario matrix spanning thresholds, HOLD/SELL, malformed signals, risk overrides, stale data, and failures.
4. **Duplicate or ambiguous orders** — persist intent before a single POST, mark uncertain submissions `UNKNOWN`, exhaust inquiry pagination, reconcile after restart, and block rerun/promotion until resolved.
5. **Freshness and portfolio risk based on fictitious state** — bind as-of evidence to broker preflight, hydrate broker cash/positions/open orders/P&L once per run, carry cumulative KST daily-loss state, and update state after fills.
6. **Misleading reports and calibration** — use one SQLite read snapshot, explicit KST trading dates and denominators, partition evidence by source/policy/backend, call LLM confidence a score, use disjoint time windows, show counts/uncertainty, and never auto-apply recommendations.
7. **Quiet-day soak and command-only runbook** — require both N eligible sessions and an adversarial fault matrix; the runbook must state decisions, abort criteria, ambiguous-order recovery, and broker verification, then be drilled from a clean shell.

## Implications for Roadmap

Based on the combined research, use five phases. This order deliberately makes the evidence trustworthy before producing reports or starting the clock on a soak campaign.

### Phase 1: Evidence Contract & Operational Safety Baseline

**Rationale:** Replay, reports, soak scoring, calibration, and promotion are invalid if failed attempts are absent, runs remain open, or account/freshness state is synthetic. This is the hard dependency for every later phase.

**Delivers:** characterization tests for v1.0 behavior; forward-only audit migrations; explicit run kind/execution target; run lifecycle and per-ticker attempt/outcome records; immutable order-intent/reconciliation attribution; policy snapshots; KST session/data-cutoff model; broker-derived cumulative account/loss state; `CycleService` extraction; preflight/postflight checks; runbook skeleton.

**Addresses:** canonical lifecycle, audit completeness, mode binding, freshness, policy provenance, operator baseline.

**Avoids:** collecting corrupted evidence; stale reconciliation leaking across tickers; stale data reaching POST; fictitious cash/position/daily-loss state; local mock being presented as KIS paper.

### Phase 2: Deterministic Point-in-Time Replay

**Rationale:** Replay validates the safety and policy plumbing cheaply and reproducibly before live LLM usage or KIS paper orders. It must reuse Phase 1 evidence and the shipped production gates.

**Delivers:** versioned fixture manifest/signals; point-in-time historical adapter; explicit decision/fill epoch; stable chronological ordering; shared stateful `MockBroker`; separate replay DB/experiment provenance; no-network/no-LLM guard; deterministic hashes and summaries; threshold/risk/error scenario matrix; no-look-ahead and future-mutation tests.

**Addresses:** backtest-lite replay, production-gate parity, replay manifest, branch/invariant coverage.

**Avoids:** live-provider nondeterminism, same-bar leakage, survivorship claims beyond available data, a second execution implementation, happy-BUY fixture overfitting, and profitability overclaiming.

### Phase 3: Review Reports & Operator Runbook

**Rationale:** Operators need to prove that evidence is complete and understandable before beginning an N-day campaign; discovering denominator, timezone, or recovery gaps after the soak would invalidate collected days.

**Delivers:** query-only read models; one-snapshot daily/replay/period reports; stable text/Markdown and JSON output; explicit incomplete/unknown warnings; mechanical totals-to-details reconciliation; KST grouping; safe SQLite backup/export; finalized preflight/postflight flow; normal, abort, stale-data, and ambiguous-order runbook drills.

**Addresses:** daily/period reports, operator procedures, evidence review, backup and triage.

**Avoids:** reports that silently omit failures, mixed evidence classes, inconsistent multi-query totals, WAL-only backup loss, secret leakage, and unsafe generic “retry” guidance.

### Phase 4: KIS Mock Soak & Fault Evidence

**Rationale:** Only after audit and reporting are proven should the project collect broker-facing evidence. This phase validates the actual KIS mock environment, not the in-memory simulator.

**Delivers:** explicit mock-only KIS broker factory and soak command; campaign manifest; chosen N eligible KRX days; clean-streak and failure-budget rules; mock account/order/fill reconciliation; normal daily operation; duplicate, accepted-then-timeout, restart, pagination, throttling, stale-data, API failure, partial/no-fill, interruption, notification, and persistence drills; labels separating synthetic drills from KIS-observed evidence.

**Addresses:** explicit KIS-paper path, N-day campaign, soak invariants, fault matrix, broker-truth proof.

**Avoids:** counting weekends/retries/local simulation as soak days, blind POST retries, unresolved ambiguous orders, quiet-days-only validation, and treating paper fills as live execution evidence.

### Phase 5: Advisory Risk Calibration & Promotion Readiness

**Rationale:** Calibration is meaningful only after immutable, reconciled replay and soak evidence exists. It must strengthen the human promotion decision, not gain execution authority.

**Delivers:** bounded predeclared policy-grid comparison; counts, coverage, exposure, risk triggers, errors, and sensitivity; time-ordered development/holdout handling where forward outcomes exist; minimum-sample/uncertainty warnings; immutable shadow recommendation artifact; evidence-linked real-money checklist; policy freeze, rollback/kill procedure, secret/config review, unresolved-order check, and separately approved tiny-size live pilot plan.

**Addresses:** risk worksheet, shadow comparison, confidence-score review, promotion checklist.

**Avoids:** treating confidence as probability, tuning and validating on the same window, automatic settings mutation, auto-promotion, and treating KIS paper economics as live-market proof.

### Phase Ordering Rationale

- Phase 1 establishes trustworthy facts and shared orchestration; all later outputs depend on it.
- Phase 2 validates deterministic policy paths offline before any campaign cost or broker risk.
- Phase 3 proves those facts can be reconciled and operated safely before the soak clock starts.
- Phase 4 gathers real KIS paper-account and fault-path evidence over independent trading sessions.
- Phase 5 consumes frozen evidence only after provenance, completeness, and broker reconciliation are credible.
- Material strategy, prompt, model, policy, or schema changes create a new versioned cohort and may restart the clean soak streak; incompatible runs must not be blended.

### Research Flags

Phases likely needing deeper research during planning (`$gsd-plan-phase --research-phase <N>`):

- **Phase 2:** define the exact decision epoch/fill convention and verify pykrx historical availability, adjusted prices, delisted symbols, and point-in-time universe limitations.
- **Phase 4:** verify authenticated KIS mock-account restrictions, exact rate limits/error behavior, mock TR IDs, pagination, order inquiry, partial-fill, and restart reconciliation behavior.
- **Phase 5:** define forward outcome labels/horizons, minimum sample sizes, uncertainty presentation, time-ordered holdout rules, and promotion thresholds before making calibration claims.

Phases with standard patterns (skip research-phase unless implementation uncovers a gap):

- **Phase 1:** additive SQLite migrations, run lifecycle/outcome modeling, dependency injection, and characterization tests are well-established and strongly grounded in current code.
- **Phase 3:** read-only SQLite snapshots, deterministic renderers, KST grouping, backups, and operational runbooks are documented patterns; validate behavior through tests and drills.

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Local dependency and code inspection strongly supports no new runtime dependency; standard-library and pinned-tool capabilities are sufficient. |
| Features | MEDIUM | Operational requirements are well grounded in current gaps and cross-checked official guidance, but N, failure budgets, and promotion thresholds remain product decisions. |
| Architecture | HIGH | Component boundaries follow existing ports/adapters and pure-domain seams; exact point-in-time data semantics remain MEDIUM. |
| Pitfalls | MEDIUM-HIGH | Audit, freshness, broker-state, and reconciliation risks come directly from code; external KIS mock behavior and statistical calibration limits need phase validation. |

**Overall confidence:** MEDIUM-HIGH

### Gaps to Address

- **Soak duration and pass policy:** choose N consecutive eligible KRX trading days, the availability-failure budget, and streak reset/invalidation rules during requirements. Safety-invariant breaches should have zero tolerance.
- **KRX timing contract:** choose the exact operator decision time, latest legal completed daily bar, order window, quote-age cutoff, holiday handling, and replay fill convention.
- **KIS mock specifics:** confirm mock credential/account binding, endpoint/TR-ID map, throttling, supported order types, inquiry pagination, partial-fill visibility, and ambiguous-submission reconciliation against authenticated documentation and actual probes.
- **Point-in-time market data:** determine what pykrx can prove about historical universe membership, delisted/suspended names, adjusted prices, and availability timestamps; label replay limitations instead of implying a full bias-free backtest.
- **Fixture policy:** decide how fixture signals are authored/versioned and require a scenario matrix independent of desired trade counts.
- **Audit taxonomy/migration:** finalize run/attempt/order-intent states, count invariants, schema version mechanism, old-row compatibility, and sanitized diagnostic fields before collecting evidence.
- **Outcome and calibration semantics:** define forward horizon, prices/cost assumptions, no-fill/cancel treatment, minimum observations, disjoint evaluation window, and uncertainty before reviewing confidence quality.
- **Promotion thresholds:** define evidence-linked pass/fail/insufficient criteria; promotion must remain blocked for any `UNKNOWN` order, unreconciled position, stale-data POST, incomplete report, failed critical drill, or unreviewed policy change.

## Sources

### Primary (HIGH confidence)

- Current project code and tests: `trading_bot/cli.py`, `execution.py`, `risk.py`, `screener.py`, `data_source.py`, `domain.py`, `mock_broker.py`, `kis_broker.py`, `kis_order.py`, `sqlite_audit.py`, and associated tests — shipped seams and current evidence gaps.
- Local planning artifacts: `.planning/PROJECT.md`, `.planning/MILESTONES.md`, `.planning/STATE.md`, and the four v1.1 research files — milestone scope and existing decisions.
- [Python `sqlite3` documentation](https://docs.python.org/3/library/sqlite3.html) — transactions, row factories, and online backup support.
- [SQLite WAL documentation](https://www.sqlite.org/wal.html), [isolation documentation](https://www.sqlite.org/isolation.html), and [Online Backup API](https://www.sqlite.org/backup.html) — snapshot behavior and safe backups.
- [pytest documentation](https://docs.pytest.org/en/stable/) and [Typer testing documentation](https://typer.tiangolo.com/tutorial/testing/) — deterministic fixtures, fault injection, and CLI contracts.

### Secondary (MEDIUM confidence)

- [Korea Investment & Securities Open Trading API repository](https://github.com/koreainvestment/open-trading-api) — mock/real separation, examples, and mock API behavior; authenticated operational details still require validation.
- [FINRA Regulatory Notice 15-09](https://www.finra.org/rules-guidance/notices/15-09) and [FCA algorithmic-trading controls review](https://www.fca.org.uk/publications/multi-firm-reviews/algorithmic-trading-controls-high-level-observations) — testing, pilot operation, monitoring, reconciliation, and controls.
- [CFA Institute, Investment Model Validation](https://rpc.cfainstitute.org/sites/default/files/-/media/documents/article/rf-brief/investment-model-validation.pdf) — point-in-time data, look-ahead, survivorship, and time-ordered validation.
- [scikit-learn probability calibration guide](https://scikit-learn.org/stable/modules/calibration.html) — reliability interpretation and independent calibration evidence.
- [Interactive Brokers paper-account limitations](https://www.interactivebrokers.com/campus/glossary-terms/paper-trading-account/) and [Alpaca paper-trading documentation](https://docs.alpaca.markets/us/v1.4.2/docs/paper-trading) — cross-broker evidence that paper fills do not establish live execution quality.
- [Google SRE incident-management guide](https://sre.google/resources/practices-and-processes/incident-management-guide/) — actionable runbooks, drills, response, and learning.

### Tertiary / Validation Required

- Recent research on temporal non-interference and community backtesting patterns — useful support for point-in-time construction, but exact pykrx/KIS behavior must be established in phase-specific research and tests.

---
*Research completed: 2026-07-11*
*Ready for roadmap: yes*
