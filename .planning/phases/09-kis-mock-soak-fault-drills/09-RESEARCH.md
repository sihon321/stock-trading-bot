# Phase 9: KIS Mock Soak & Fault Drills - Research

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

### Mock-only entry and isolation
- **D-01:** Expose a dedicated `bot soak` command family with explicit start, run, resume, status, and drill operations. Do not hide soak semantics behind ordinary `bot run` flags.
- **D-02:** Construct a mock-only runtime that can resolve only `kis_mock` credentials, the mock domain, mock account, and mock TR IDs. Real configuration must not be reachable from the soak execution path, and any mismatch fails before campaign execution.
- **D-03:** Before any soak mutation, show and persist a non-secret identity receipt containing `target=mock`, sanitized domain class, account suffix, TR-ID profile, campaign ID, and mock-isolation policy version. Every identity field must pass.
- **D-04:** When audit storage is healthy, an isolation failure appends a sanitized `MOCK_ISOLATION_BLOCKED` campaign event, places no order, and does not count the day as attempted. If audit health is unknown, fail without mutation and emit only a terminal error.

### Campaign pass/fail accounting
- **D-05:** Record an immutable `target_eligible_days` when a campaign starts, defaulting to 20 eligible KRX days. The target cannot change after campaign creation.
- **D-06:** Count at most one explicitly designated terminal mock run per confirmed KRX trading date. Grant day credit only after daily-report evidence confirms complete run, ticker, order, and reconciliation evidence.
- **D-07:** HOLD and zero-order days can earn eligible-day credit. Weekends, holidays, preview screens, dry-runs, controlled drill runs, and extra reruns cannot add credit.
- **D-08:** Record a separate immutable availability-failure budget, defaulting to two days. Pre-submission failures clearly attributable to external KIS, LLM, or data availability consume the budget and earn no day credit, but do not reset the safety clean streak. Exceeding the budget fails the campaign.
- **D-09:** Any safety-invariant breach permanently fails the campaign; it cannot be repaired by resetting the clean streak inside the same campaign. Breaches include real-target reachability, unjustified submission, blind POST retry, duplicate order, lost or contradictory audit evidence, incorrectly released ambiguity, and disagreement between local evidence and broker truth.
- **D-10:** A controlled fault does not fail the campaign when the expected containment, evidence, and recovery checks all pass. Fault-drill coverage remains separate from clean-operation day accounting.

### Broker-truth reconciliation and recovery
- **D-11:** Authenticated reconciliation is mandatory at soak startup or resume, before every designated run, after every submission, and before run finalization/day credit.
- **D-12:** Each reconciliation persists a normalized snapshot and comparison verdict for campaign-touched orders, fills, open orders, holdings, and available cash. Exclude raw KIS payloads, secrets, and unrelated account activity.
- **D-13:** Accepted-then-timeout and other ambiguous submissions are never resubmitted. Perform bounded broker inquiry over a recorded time window using account, ticker, side, quantity, price, and available broker identifiers; append every observation.
- **D-14:** Keep an ambiguously submitted ticker frozen until inquiry establishes exactly one determinate match or confirmed absence. Multiple or inconclusive matches require operator review and cannot release the freeze.
- **D-15:** Complete partial-fill or no-fill evidence is determinate, but the ticker remains ineligible for new orders across restarts until the remaining order is filled, cancelled, rejected, or expired and broker truth confirms that terminal state.
- **D-16:** A day with a partial or no fill may earn credit only after all evidence is complete and local holdings, cash, and order state reconcile to broker truth. The unresolved ticker freeze persists independently of day credit.

### Fault-drill execution and evidence
- **D-17:** Track `CONTROLLED_INJECTION` and `KIS_OBSERVED` as separate evidence classes and never combine their counts or claims in reports.
- **D-18:** Every required Phase 9 fault gets a reproducible controlled-injection drill. Naturally occurring KIS mock failures add `KIS_OBSERVED` evidence and may satisfy the same drill only when the identical expected containment and reconciliation checks pass.
- **D-19:** Invoke controlled drills only through `bot soak drill <fault>`. Each invocation requires an active campaign, a passing mock identity receipt, exactly one named fault, an explicit injection boundary, and a generated drill ID. Ordinary soak runs cannot accept hidden fault-injection flags.
- **D-20:** Controlled drill runs never increment eligible-day credit or consume the availability budget. Naturally occurring faults during designated daily runs follow normal campaign accounting.
- **D-21:** Use an independent controller journal outside the primary audit DB being tested. Before injection it durably records campaign identity, drill ID, fault type, injection boundary, and expected containment.
- **D-22:** After recovery, the controller journal links observed run, ticker, and order events; broker reconciliation where applicable; interruption/restart evidence; prohibited-action checks; and a terminal pass/fail verdict. Any required evidence missing from this contract fails the drill.

### the agent's Discretion
- Choose campaign table/schema names, exact state enum names, journal serialization, CLI option spelling, and output formatting consistent with existing Typer and normalized SQLite evidence patterns.
- Define bounded KIS inquiry durations, polling cadence, and exact field matching after confirming authenticated mock endpoint behavior; these choices may not weaken the no-resubmission or ticker-freeze decisions above.
- Choose safe injection seams for each required fault and the internal controller implementation, provided ordinary soak runs cannot activate them and the evidence classes remain explicit.
- Define the exhaustive stable reason-code catalog and drill result schema while preserving the locked campaign accounting, provenance, containment, and reconciliation distinctions.

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within Phase 9. Advisory policy calibration and real-money promotion readiness remain Phase 10; scheduling, unattended retries, profitability backtesting, and new strategies remain outside the milestone.
</user_constraints>

**Researched:** 2026-07-16
**Domain:** KIS mock-account composition, broker-truth reconciliation, soak campaign accounting, and fault-injection evidence
**Confidence:** MEDIUM

## Summary

Phase 9 is not chiefly a load-testing phase. It is a safety-evidence phase that needs four independently testable mechanisms: a structurally mock-only composition root, an immutable campaign/day ledger, an authenticated broker-truth reconciler, and a controlled-fault controller whose journal survives failure of the primary audit store. The shipped code already provides append-only order events, a single-shot POST boundary, typed preflight checks, WAL-backed SQLite evidence, stable reason codes, and dependency-injection seams. [VERIFIED: codebase grep and source inspection]

The most important planning discovery is an authenticated compatibility gap. The current official KIS examples use mock cash-order TR IDs `VTTC0012U`/`VTTC0011U` and same-day order/fill inquiry `VTTC0081R`, while this repository currently derives `VTTC0802U`/`VTTC0801U` and `VTTC8001R`. The official examples also require account/date/side/fill-state/pagination fields that the current adapter does not send, and model balance as paginated `output1` holdings plus `output2` summary rather than the project's current single `output` assumption. [CITED: https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/order_cash/order_cash.py] [CITED: https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_daily_ccld/inquire_daily_ccld.py] [CITED: https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_balance/inquire_balance.py] [VERIFIED: `trading_bot/kis_order.py`]

Therefore the first implementation wave must be a fail-closed KIS mock compatibility characterization: update or version the mock TR-ID profile only after read-only authenticated queries and a deliberately operator-run mock order prove the accepted IDs, response shapes, continuation headers, and normalized matching fields. Do not build campaign success claims on the current Phase 5 adapter assumptions. [INFERENCE from cited official examples and verified code divergence]

**Primary recommendation:** Plan Phase 9 as contracts and compatibility first, then campaign persistence, reconciliation, orchestration, drills, and reporting; make authenticated mock characterization a prerequisite gate rather than a final smoke test.

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| SOAK-01 | Operator can run an explicit KIS mock-account soak path that cannot select real credentials, domains, accounts, or transaction IDs. | Separate `SoakSettings`/mock composition root, allowlisted mock domain class, V-prefixed TR profile, and persisted identity receipt before mutation. |
| SOAK-02 | Operator can run and review an N-eligible-KRX-day mock soak campaign with clean-streak accounting, a declared availability-failure budget, and zero-tolerance safety invariants. | Immutable campaign row plus one designated-day record per confirmed KRX date, derived credit verdict, permanent safety-failure latch, and separate drill coverage. |
| SOAK-03 | Operator can verify broker-truth reconciliation for mock-account orders, fills, open orders, account state, duplicate reruns, ambiguous submissions, and restart recovery. | Paginated normalized KIS snapshots, campaign-touched filtering, comparison verdicts, ambiguity matcher, and persisted per-ticker freeze state reconstructed on resume. |
| SOAK-04 | Operator can run and record fault drills for stale data, malformed or timed-out LLM responses, KIS API failure, accepted-then-timeout orders, throttling, partial or no fill, interruption, notification failure, and audit failure. | Dedicated drill registry, injection-only composition root, independent controller SQLite journal, expected-containment assertions, and provenance-separated reporting. |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Mock-only identity and runtime construction | CLI / composition root | Pydantic configuration | Real credentials must be structurally absent before adapters are constructed. [VERIFIED: current `Settings.active_kis` and CLI runtime are the selection seam] |
| Campaign and day accounting | Domain/service layer | SQLite storage | Eligibility, credit, budgets, and permanent failure are business invariants; storage enforces immutability and uniqueness. [INFERENCE from locked D-05 through D-10] |
| Broker-truth collection | KIS adapter | Reconciliation service | The adapter owns authenticated pagination/normalization; the service compares only campaign-touched state. [CITED: official KIS inquiry examples] |
| Ambiguity and restart recovery | Reconciliation service | Campaign storage / CLI resume | Inquiry state is durable and must reconstruct ticker freezes without another POST. [VERIFIED: current append-only order-event/recovery pattern] |
| Fault injection | Drill controller | Injected ports/adapters | Only the drill composition root may construct faulting collaborators. [INFERENCE from locked D-19] |
| Independent drill evidence | Controller SQLite file | Primary audit DB references | The controller must survive primary-audit interruption and link back by stable IDs. [INFERENCE from locked D-21/D-22] |
| Campaign/drill reports | Read-only reporting projection | Typer CLI | Existing reports already separate lifecycle, target, reconciliation, and notification dimensions. [VERIFIED: `trading_bot/reporting.py`, `report_cli.py`] |

## Standard Stack

No new external package is needed or recommended. Reuse the installed project stack. [VERIFIED: `pyproject.toml` and codebase]

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python | runtime 3.14.3; project `>=3.10` | Typed domain/services and CLI | Existing runtime; stdlib has `sqlite3`, enums, dataclasses, and timezone support. [VERIFIED: environment probe and `pyproject.toml`] |
| `sqlite3` | SQLite 3.51.3 in current runtime | Campaign, reconciliation, and independent controller journals | Existing audit store uses additive migrations, WAL, explicit commits, and integrity checks. [VERIFIED: environment probe and `sqlite_audit.py`] |
| Typer | 0.26.8 | `bot soak` command family | Existing synchronous operator CLI and test patterns. [VERIFIED: `pyproject.toml`, `cli.py`] |
| Pydantic / pydantic-settings | 2.13.4 / 2.11.0 | Mock-only settings and validated evidence contracts | Existing typed settings and validation approach. [VERIFIED: `pyproject.toml`, `config.py`] |
| HTTPX + Tenacity | 0.28.1 / 9.1.4 | KIS queries with bounded retry; POST without retry | Existing adapter explicitly retries query legs and keeps order POST single-shot. [VERIFIED: `pyproject.toml`, `kis_order.py`] |
| pytest | 8.4.2 | Unit, integration, restart, and CLI tests | Existing suite has 472 passing tests in 16.01 seconds. [VERIFIED: test run on 2026-07-16] |

### Supporting

| Component | Purpose | When to Use |
|-----------|---------|-------------|
| Existing `ObservedKRXCalendar` / `MarketCyclePolicy` | Confirm eligible KRX date and continuous session | Campaign designated-run admission and day-credit derivation. [VERIFIED: `market_cycle.py`, `cli.py`] |
| Existing `KisTokenManager` | Shared mock bearer-token lifecycle | All authenticated mock inquiries and order/hashkey calls. [VERIFIED: `kis_auth.py`] |
| Existing order/ticker/notification evidence models | Stable links into Phase 6–8 evidence | Campaign/day/reconciliation/drill rows should reference, not duplicate, run and order evidence. [VERIFIED: `audit_models.py`, `sqlite_audit.py`] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Separate controller SQLite file | JSONL with `fsync` | JSONL is simpler but makes schema validation, uniqueness, restart queries, and terminal verdict constraints bespoke. Use SQLite to match project patterns. [INFERENCE] |
| New soak service modules | Add more branches to `run_cycle` | Branching the production cycle would entangle campaign accounting and hidden injection flags with ordinary runs, contrary to D-01/D-19. [VERIFIED: current `run_cycle` is already a dense orchestration seam] |
| Broker raw-payload archive | Normalized allowlisted snapshots | Raw payloads risk secrets/unrelated activity and violate D-12; normalized fields are sufficient for comparison. [VERIFIED: existing `sanitize_detail` rejects provider payload shapes] |

## Package Legitimacy Audit

Not applicable: Phase 9 should install no new package. The plan must reuse dependencies already pinned in `pyproject.toml`. [VERIFIED: stack analysis]

## KIS Compatibility Findings

### Identity separation

- The official KIS sample configuration has distinct production and paper app keys, distinct real and paper account numbers, production REST domain `openapi.koreainvestment.com:9443`, and mock REST domain `openapivts.koreainvestment.com:29443`. [CITED: https://github.com/koreainvestment/open-trading-api/blob/main/kis_devlp.yaml]
- The official README instructs operators to authenticate with `svr="vps"` for mock and states that real and mock app keys should be prepared separately. [CITED: https://github.com/koreainvestment/open-trading-api]
- Current `build_runtime()` always constructs the shared `Settings`, token manager, and quote adapter, but routes `TradingMode.MOCK` to the local `MockBroker`; therefore no existing CLI path performs a genuine KIS mock order. [VERIFIED: `trading_bot/cli.py`]
- `Settings` requires both `kis_mock` and `kis_real`, and `active_kis` can select either. A soak runtime built from `Settings` would still make real configuration reachable and would not satisfy D-02. [VERIFIED: `trading_bot/config.py`]

### TR IDs and response contracts

- Current official order-cash examples select `VTTC0012U` for mock buy and `VTTC0011U` for mock sell. The repository currently selects `VTTC0802U` and `VTTC0801U`. [CITED: official `order_cash.py`] [VERIFIED: `kis_order.py`]
- Current official same-day order/fill inquiry selects `VTTC0081R` for mock within three months; the repository currently selects `VTTC8001R`. [CITED: official `inquire_daily_ccld.py`] [VERIFIED: `kis_order.py`]
- The official balance example still selects mock `VTTC8434R`, matching the repository. [CITED: official `inquire_balance.py`] [VERIFIED: `kis_order.py`]
- Official same-day inquiry supports filters for date range, side, fill state, ticker, branch/order number, exchange, and `CTX_AREA_*` continuation keys. Mock pages contain at most 15 order rows. [CITED: official `inquire_daily_ccld.py`]
- Official balance inquiry has at most 20 mock holdings per page, returns holdings and a summary separately, and requires continuation keys. [CITED: official `inquire_balance.py`]
- The current adapter sends only market/ticker/order ID for daily inquiry, does not send the account tuple or date/fill filters, does not consume continuation headers, and parses only `body["output"]`. [VERIFIED: `kis_order.py`]
- The current `inquire_psbl_rvsecncl` official example hard-codes real `TTTC0084R` and exposes no mock TR ID. Do not assume that endpoint is a valid mock open-order source; derive open orders from the supported mock daily inquiry until an authenticated mock call proves another endpoint. [CITED: official `inquire_psbl_rvsecncl.py`] [INFERENCE]

### Throttling and ambiguity

- KIS's official README says mock REST limits are lower and identifies `EGW00201` as a per-second transaction-volume error; official pagination examples delay between continuation calls. [CITED: https://github.com/koreainvestment/open-trading-api]
- No authoritative KIS material found in this research establishes a client idempotency key or declares an order POST retry safe after a transport timeout. Preserve the existing zero-retry POST rule. [ASSUMED: negative claim; authenticated/official confirmation still required]
- Because a timeout may occur after broker acceptance, a bounded inquiry window must append every observation and classify zero, exactly one, or multiple matches; it must not convert a transient absence into permission to submit again. [INFERENCE from D-13/D-14 and absence of a verified idempotency contract]

## Architecture Patterns

### System Architecture Diagram

```text
Operator
  -> bot soak start/run/resume/status
       -> Mock-only composition root
            -> identity receipt gate (mock key/domain/account/TR profile only)
            -> authenticated reconciliation gate
                 -> paginated KIS mock queries
                 -> normalized campaign-touched snapshot
                 -> comparison verdict / ticker freezes
            -> production run-cycle collaborators
            -> campaign/day ledger -> read-only reports

Operator
  -> bot soak drill <fault>
       -> Drill-only composition root
            -> controller journal COMMIT (separate SQLite file)
            -> exactly one injected boundary
            -> primary audit/run/order evidence
            -> recovery + reconciliation + prohibited-action assertions
            -> controller terminal verdict
```

### Recommended Project Structure

```text
trading_bot/
├── soak_models.py          # Campaign/day/identity/reconciliation/drill enums and records
├── soak_config.py          # Mock-only settings and identity receipt construction
├── soak_store.py           # Additive campaign/day/snapshot persistence
├── soak_reconcile.py       # Pagination, normalization, matching, comparison, freezes
├── soak_campaign.py        # Start/run/resume/finalize accounting state machine
├── soak_drills.py          # Named fault registry and drill-only injected collaborators
├── soak_controller.py      # Independent SQLite controller journal
├── soak_reporting.py       # Read-only campaign and drill projections
└── cli.py                  # Registers `soak_app`; delegates to the modules above
tests/
├── test_soak_config.py
├── test_soak_store.py
├── test_soak_reconcile.py
├── test_soak_campaign.py
├── test_soak_drills.py
└── test_soak_cli.py
```

### Pattern 1: Structurally mock-only composition root

Define `SoakSettings` independently from `Settings`; it reads only `kis_mock`, mock account values, audit/controller paths, and campaign policy defaults. It must not contain `kis_real`, `trading_mode`, or `confirm_real_trading`. Build KIS adapters from this type and validate an exact sanitized domain class and V-prefixed allowlisted TR profile before opening a mutation-capable campaign. [INFERENCE from D-02 and verified current settings reachability]

### Pattern 2: Immutable facts plus derived verdicts

Persist campaign policy once, append designated-day attempts and reconciliation observations, then derive credit/budget/failure from evidence. Enforce one designated run per campaign/date with a database uniqueness constraint. Never update a failed campaign back to active and never rewrite observations. [INFERENCE from D-05 through D-10; aligned with verified append-only storage patterns]

### Pattern 3: Snapshot envelope, not raw KIS payload

Normalize each page into allowlisted `BrokerOrder`, `BrokerFill`, `BrokerHolding`, and `BrokerAccountSummary` records. Persist snapshot ID, campaign ID, run ID, stage, requested time window, page count, completeness, normalized records, and comparison verdict. Hashing canonical normalized content is optional but useful for contradiction detection. [INFERENCE from D-11/D-12]

### Pattern 4: Three-way ambiguity matcher

Match on the strongest available broker identifiers first, then bounded composite fields `(account_suffix, ticker, side, quantity, snapped_price, observed_time_window)`. Return exactly one of `NO_MATCH_CONFIRMED`, `ONE_MATCH_DETERMINATE`, `MULTIPLE_OR_INCONCLUSIVE`; only the first two are determinate, and neither automatically authorizes another POST. Operator review controls any later new intent. [INFERENCE from D-13/D-14]

### Pattern 5: Pre-commit drill intent

Open a separate controller database, insert the drill contract, commit it, verify it can be read back, and only then activate one named fault at one injection boundary. After recovery, append stable references and a terminal verdict. Use `PRAGMA journal_mode=WAL`, verify the returned mode, and use `PRAGMA synchronous=FULL` for the controller because D-21 requires durable pre-injection evidence. [CITED: https://www.sqlite.org/wal.html] [CITED: https://www.sqlite.org/pragma.html] [INFERENCE for project policy]

### Anti-Patterns to Avoid

- **Reusing `Settings` with `trading_mode=mock`:** real fields remain reachable. Create a smaller settings type. [VERIFIED: `config.py`]
- **Crediting a day at run completion alone:** day credit requires report completeness and final broker reconciliation. [INFERENCE from D-06]
- **Using a single successful first page:** mock queries are explicitly paginated and have small page caps. [CITED: official KIS inquiry examples]
- **Treating `NO_MATCH` at one instant as absence:** inquiry lag/throttling can make early observations incomplete. Preserve a bounded observation sequence. [ASSUMED: exact KIS visibility lag is not documented]
- **Injecting faults through ordinary command flags/environment variables:** hidden activation violates D-19. Construct fault ports only in the drill command path. [INFERENCE]
- **Keeping the controller journal in the primary audit DB or using `ATTACH`:** SQLite does not make separate WAL databases atomic as a set, and the primary DB is itself a fault target. [CITED: https://www.sqlite.org/wal.html]
- **Copying only the `.db` file while WAL connections are active:** committed state can reside in the `-wal` file; use SQLite backup/checkpoint procedures. [CITED: https://www.sqlite.org/wal.html]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| KRX eligible-day inference | Weekday/holiday arithmetic | Existing observed KRX calendar and market-cycle evidence | Existing policy already fails closed on unknown days. [VERIFIED: `market_cycle.py`] |
| Retry/backoff | Custom sleep loops scattered across adapters | Existing Tenacity query pattern plus one centralized KIS rate limiter | Keeps bounded query retry distinct from forbidden POST retry. [VERIFIED: `kis_order.py`] |
| Secret filtering | Ad hoc string redaction | Existing allowlisted scalar `sanitize_detail`, extended for soak models | Raw payload/credential keys are already rejected. [VERIFIED: `audit_models.py`] |
| Fault-specific orchestration copies | Nine separate run implementations | Registry of named fault specs over injected protocol boundaries | One containment contract prevents scenario drift. [INFERENCE] |
| Controller durability format | Bespoke JSON append/recovery parser | Separate stdlib SQLite database with explicit transactions | Existing project operational skill and integrity checks transfer directly. [VERIFIED: `sqlite_audit.py`; cited Python sqlite3 docs] |
| Broker idempotency | Local client key presented as broker guarantee | Single-shot POST plus broker inquiry and freeze | Current local ref is explicitly not a KIS idempotency key. [VERIFIED: `kis_broker.py`] |

## Common Pitfalls

### Pitfall 1: Planning against stale TR IDs
**What goes wrong:** The soak cannot place/query mock orders or, worse, proves only local fakes. **Why:** Phase 5 constants differ from current official examples. **Avoid:** authenticated compatibility plan first; version the accepted profile and persist it in the identity receipt. **Warning:** `rt_cd != 0`, missing output, or zero rows despite known mock activity. [CITED and VERIFIED as above]

### Pitfall 2: Incomplete pagination masquerades as broker truth
**What goes wrong:** A duplicate/open order on a later page is missed. **Why:** mock page caps are 15 orders and 20 holdings. **Avoid:** follow continuation header/body keys until terminal, cap pages, and mark cap/parse failure `INCOMPLETE`. **Warning:** continuation header indicates another page or keys repeat. [CITED: official inquiry examples]

### Pitfall 3: Campaign/day state conflation
**What goes wrong:** A drill or rerun increments credit, availability resets the clean streak, or a safety breach gets repaired. **Avoid:** separate immutable campaign policy, designated-day ledger, safety latch, availability counter, and drill coverage tables. [INFERENCE from D-05 through D-10]

### Pitfall 4: Ambiguous submission released too early
**What goes wrong:** accepted-then-timeout becomes a duplicate order. **Avoid:** persist `SUBMISSION_ATTEMPTED` before POST, freeze immediately, query a recorded window, and require an explicit determinate release event. [VERIFIED existing event ordering; INFERENCE for Phase 9]

### Pitfall 5: Controller dies with the system under test
**What goes wrong:** audit-failure/interruption drills have no trustworthy pre-injection contract. **Avoid:** separate path/file/connection and commit/read-back before injection. **Warning:** controller and audit paths resolve to the same inode/directory target or drill starts before commit. [INFERENCE]

### Pitfall 6: Synthetic and observed evidence blended
**What goes wrong:** a deterministic injection is reported as proof of KIS behavior. **Avoid:** evidence class in every drill observation and denominators grouped by class. [INFERENCE from D-17/D-18]

### Pitfall 7: Testing permanent process interruption only in-process
**What goes wrong:** exception-based tests pass but restart reconstruction fails. **Avoid:** subprocess tests that terminate after controller commit and after primary-audit writes, then invoke resume in a new process. [INFERENCE]

## Code Examples

### Mock-only settings shape

```python
# Source: project Pydantic pattern; exact names are implementation discretion.
class SoakSettings(BaseSettings):
    kis_mock: KisCredentialGroup
    kis_mock_account_cano: SecretStr
    kis_mock_account_product_code: str = "01"
    audit_db_path: Path = Path("./data/audit.db")
    soak_controller_db_path: Path = Path("./data/soak-controller.db")

    # Deliberately no kis_real, trading_mode, or confirm_real_trading fields.
```

### Durable controller boundary

```python
# Sources: Python sqlite3 transaction docs and SQLite WAL/pragma docs.
conn = sqlite3.connect(controller_path)
mode = conn.execute("PRAGMA journal_mode=WAL").fetchone()[0]
if str(mode).lower() != "wal":
    raise RuntimeError("controller journal WAL unavailable")
conn.execute("PRAGMA synchronous=FULL")
conn.execute("BEGIN IMMEDIATE")
conn.execute("INSERT INTO drill_invocations (...) VALUES (...) ", values)
conn.commit()  # injection is forbidden before this succeeds
```

### Reconciliation cardinality

```python
# Source: locked D-13/D-14, expressed as a domain pattern.
matches = tuple(match_candidate(candidate, intent) for candidate in snapshot.orders)
matches = tuple(item for item in matches if item is not None)
if len(matches) == 1:
    verdict = "ONE_MATCH_DETERMINATE"
elif snapshot.complete and len(matches) == 0 and inquiry_window_complete:
    verdict = "NO_MATCH_CONFIRMED"
else:
    verdict = "MULTIPLE_OR_INCONCLUSIVE"
# No branch submits an order. Submission is a later, separate operator action.
```

## Recommended Plan Decomposition

1. **Compatibility and contracts:** add mock-only settings/identity models; characterize current KIS mock TR IDs, required params, payload shapes, and pagination with sanitized fixtures; fix the adapter before campaign work. [INFERENCE from compatibility gap]
2. **Campaign persistence:** additive schema/migrations for campaigns, immutable policy, designated days, campaign events, reconciliation snapshots, freezes, and permanent failure latch. [INFERENCE from D-05–D-16]
3. **Reconciliation service:** paginated order/fill/balance normalization, touched-state projection, comparison verdicts, ambiguity cardinality, partial/no-fill terminality, and restart reconstruction. [INFERENCE]
4. **Soak orchestration and CLI:** `start/run/resume/status` with identity and reconciliation gates at every required boundary; designated run delegates to existing run-cycle collaborators but uses genuine KIS mock broker. [VERIFIED integration seams in `cli.py`/`kis_broker.py`]
5. **Controller and fault registry:** independent database plus all nine named controlled injections, prohibited-action assertions, restart drills, and evidence-class separation. [INFERENCE]
6. **Reports and runbook:** campaign status/day denominators, reconciliation completeness, freezes, drill matrix split by provenance, authenticated compatibility procedure, and manual UAT. [VERIFIED existing report/runbook patterns]

The planner should keep these as multiple small PLAN.md files with the adapter compatibility work in the first wave; otherwise later campaign tests will encode an unverified KIS contract. [INFERENCE]

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.4.2 [VERIFIED: runtime] |
| Config file | `pyproject.toml` [VERIFIED] |
| Quick run command | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_soak_config.py tests/test_soak_campaign.py tests/test_soak_reconcile.py -x` |
| Full suite command | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` (472 passed in 16.01s before Phase 9) [VERIFIED] |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SOAK-01 | Real config is unrepresentable/rejected; receipt gates all mutation | unit + CLI integration | `python3 -m pytest -q tests/test_soak_config.py tests/test_soak_cli.py -x` | ❌ Wave 0 |
| SOAK-02 | Eligible-day credit, budgets, immutable target, permanent failure | unit + SQLite integration | `python3 -m pytest -q tests/test_soak_campaign.py tests/test_soak_store.py -x` | ❌ Wave 0 |
| SOAK-03 | Pagination, normalized comparison, ambiguity, partial fill, restart freeze | unit + integration + subprocess restart | `python3 -m pytest -q tests/test_soak_reconcile.py -x` | ❌ Wave 0 |
| SOAK-04 | Exactly one named injection, containment/evidence/recovery, provenance split | unit + CLI + subprocess | `python3 -m pytest -q tests/test_soak_drills.py tests/test_soak_cli.py -x` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** focused new soak test file plus affected existing KIS/audit/CLI tests.
- **Per wave merge:** full 472+ test suite.
- **Phase gate:** full suite green, then authenticated KIS mock UAT over at least one designated run and every controlled drill; the 20-day campaign itself cannot be compressed into automated execution. [INFERENCE from D-05]

### Wave 0 Gaps

- [ ] `tests/test_soak_config.py` — mock-only construction and receipt gate.
- [ ] `tests/test_soak_store.py` — migrations, immutability, uniqueness, permanent failure.
- [ ] `tests/test_soak_reconcile.py` — multi-page fixtures, cardinality, account comparison, restart freeze.
- [ ] `tests/test_soak_campaign.py` — eligibility/budget/credit state machine.
- [ ] `tests/test_soak_drills.py` — fault registry and controller durability/recovery.
- [ ] `tests/test_soak_cli.py` — command isolation and end-to-end injected collaborators.
- [ ] Sanitized authenticated KIS mock fixtures for accepted current TR profile and page/response shapes; no secrets/raw unrelated account data. [OPEN: requires operator environment]

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|-------------|-----------|---------|----------|
| Python | all implementation/tests | ✓ | 3.14.3 | Project supports >=3.10. [VERIFIED] |
| SQLite | audit/controller journals | ✓ | 3.51.3 | None needed. [VERIFIED] |
| pytest | verification | ✓ | 8.4.2 | None needed. [VERIFIED] |
| `uv` CLI | optional project workflow | ✗ | — | Use configured `python3 -m pytest` commands. [VERIFIED] |
| `.env` | local credential/config source | ✓ file present | contents intentionally not inspected | Operator validates via mock identity receipt. [VERIFIED: file existence only] |
| Authenticated KIS mock service/account | compatibility and UAT | not probed | — | No substitute counts as SOAK evidence; planner must add operator-run authenticated checkpoint. [VERIFIED: project requirement] |

**Missing dependencies with no fallback:** authenticated KIS mock compatibility evidence is not available to this research agent and is required before SOAK-03 claims.

**Missing dependencies with fallback:** `uv` is absent; the repository's Python/pytest command works.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Existing KIS token manager with mock-only credentials and redacted representations. [VERIFIED: `kis_auth.py`] |
| V3 Session Management | yes | Runtime-derived token expiry, refresh margin, lock, and bounded token issuance. [VERIFIED: `kis_auth.py`] |
| V4 Access Control | yes | Capability restriction by construction: soak composition contains no real credentials/domain/TR IDs. [INFERENCE from D-02] |
| V5 Input Validation | yes | Pydantic/settings validation, enums, stable codes, normalized scalar evidence, database constraints. [VERIFIED: project patterns] |
| V6 Cryptography | yes | Use KIS HTTPS/TLS and SDK/HTTP client defaults; do not implement custom cryptography. [CITED: official KIS HTTPS domains] |

### Known Threat Patterns for This Phase

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Confused-deputy access to real KIS target | Elevation of privilege | Smaller mock-only settings/composition root plus exact receipt gate. [INFERENCE] |
| Credential or unrelated account leakage | Information disclosure | Persist only suffix/domain class/profile and campaign-touched normalized records. [VERIFIED existing sanitization pattern] |
| Hidden fault activation in ordinary runs | Tampering | Drill-only constructor and enum registry; no environment/ordinary-run injection flags. [INFERENCE] |
| Blind POST replay after timeout/restart | Spoofing/repudiation | Pre-POST durable event, no retry, inquiry sequence, persistent ticker freeze. [VERIFIED existing no-retry; INFERENCE for resume] |
| Audit/controller evidence contradiction | Tampering/repudiation | Independent controller, stable cross-IDs, append-only observations, explicit contradiction as safety breach. [INFERENCE] |
| SQLite durability assumptions | Tampering/data loss | Verify WAL mode, controller `synchronous=FULL`, explicit commits, `integrity_check`, safe backup including WAL state. [CITED: SQLite official docs] |

## Project Constraints (from AGENTS.md)

- Use Python and Korea-only market sources; KIS mock is the first target. [VERIFIED: AGENTS.md]
- LLM output remains strict JSON and unparseable output fails safe; BUY requires confidence >= 0.8. [VERIFIED: AGENTS.md]
- Real-money promotion is a deliberate gated future step; Phase 9 cannot schedule, auto-promote, or mutate policy. [VERIFIED: AGENTS.md and phase context]
- Preserve the existing `python-kis`/pykrx/TA/LLM/config/SQLite/Typer/structured-logging stack decisions unless the codebase's implemented direct KIS adapter contract requires compatible extension. [VERIFIED: AGENTS.md and codebase]
- Treat scraped/provider text as untrusted and never persist raw secrets/provider payloads. [VERIFIED: AGENTS.md]
- Before implementation edits, execute through the appropriate GSD workflow; Phase 9 implementation should use `$gsd-execute-phase`. [VERIFIED: AGENTS.md]
- Follow existing code patterns because conventions/architecture documents are not yet populated. [VERIFIED: AGENTS.md]

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | KIS exposes no safe client idempotency key/order-POST retry contract. | Throttling and ambiguity | If an official key exists, matching could be stronger; no-retry remains safe. |
| A2 | Broker visibility can lag long enough that one immediate `NO_MATCH` is insufficient. | Anti-patterns | Inquiry window/cadence may be over-conservative; authenticated characterization must set it. |

## Open Questions

1. **Which TR-ID profile does the operator's KIS mock account currently accept?**
   - What we know: current official examples and repository constants diverge. [CITED/VERIFIED]
   - What's unclear: KIS portal/account rollout compatibility and whether legacy IDs remain accepted.
   - Recommendation: first plan adds a read-only profile probe, then one explicitly operator-run mock order with sanitized evidence before locking `mock-tr-profile-vN`.

2. **What exact normalized fields are present for mock open/no-fill/partial-fill and available cash?**
   - What we know: official examples define inquiry filters, page caps, and separate balance outputs. [CITED]
   - What's unclear: live mock payload field presence/semantics for all terminal states.
   - Recommendation: capture allowlisted field-name/value-shape fixtures from authenticated calls; never retain raw payloads.

3. **What bounded ambiguity inquiry window and cadence are justified?**
   - What we know: mock limits are lower and queries support date/order/ticker filters. [CITED]
   - What's unclear: visibility latency and throttling behavior after accepted-then-timeout.
   - Recommendation: make duration/cadence policy-versioned and configurable only at campaign creation; start conservatively, record every observation, never auto-resubmit.

4. **Can a mock-only cancel/open-order endpoint be proven?**
   - What we know: the current official `inquire_psbl_rvsecncl` example is real-only. [CITED]
   - What's unclear: portal-only or alternative mock support.
   - Recommendation: do not depend on it for the first plan; derive open quantity from supported same-day inquiry, then extend only after authenticated proof.

## Sources

### Primary project evidence (HIGH confidence)
- `trading_bot/config.py`, `cli.py`, `kis_auth.py`, `kis_order.py`, `kis_broker.py`, `preflight.py`, `sqlite_audit.py`, `audit_models.py`, `reporting.py` — current composition, KIS, evidence, and report contracts.
- `tests/test_kis_order.py`, `test_kis_broker.py`, `test_preflight.py`, `test_sqlite_audit.py`, `test_cli.py` — verified behavior and extension seams.
- Phase 6–9 planning artifacts and `docs/operator-runbook.md` — locked safety/accounting boundaries.

### Official external sources (MEDIUM confidence per research seam)
- https://github.com/koreainvestment/open-trading-api — KIS official examples, mock identity separation, lower mock request limits, `EGW00201`.
- https://github.com/koreainvestment/open-trading-api/blob/main/kis_devlp.yaml — real/mock credentials, accounts, and domains.
- https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/order_cash/order_cash.py — current order-cash TR IDs and request contract.
- https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_daily_ccld/inquire_daily_ccld.py — current mock daily order/fill inquiry, filters, pagination, page cap.
- https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_balance/inquire_balance.py — current balance TR IDs, outputs, pagination, page cap.
- https://github.com/koreainvestment/open-trading-api/blob/main/examples_llm/domestic_stock/inquire_psbl_rvsecncl/inquire_psbl_rvsecncl.py — current real-only correct/cancel-capable inquiry example.
- https://docs.python.org/3/library/sqlite3.html — explicit Python transaction control and commit/rollback behavior.
- https://www.sqlite.org/wal.html — WAL commit, checkpoint, file-set, and multi-database limitations.
- https://www.sqlite.org/pragma.html — `journal_mode`, `synchronous`, and `integrity_check` behavior.

### Tertiary (LOW confidence)
- No tertiary web source was used. Two assumptions are listed explicitly above.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — existing pinned and runtime-probed project stack; no new dependencies.
- Architecture: HIGH for project seams, MEDIUM for exact KIS adapter changes pending authenticated mock proof.
- Pitfalls: HIGH for campaign/evidence invariants, MEDIUM for KIS timing/visibility behavior.

**Research date:** 2026-07-16
**Valid until:** 2026-07-23 for KIS endpoint/TR-ID details; 2026-08-15 for stable project/SQLite architecture.
