# Phase 7: Deterministic Replay Validation - Research

**Researched:** 2026-07-12
**Domain:** Offline deterministic scenario replay, canonical serialization, and safety-policy verification
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

### Scenario and fixture design
- **D-01:** Use a mixed fixture structure. Focused single-purpose cases are the default; add full-day, multi-ticker scenarios only where interactions between candidates or state materially matter.
- **D-02:** The initial catalog must cover the complete Phase 7 requirement set: BUY threshold boundaries, HOLD, SELL, malformed signals, stale data, stop-loss/take-profit overrides, daily-loss BUY blocking, sizing boundaries, and look-ahead rejection.
- **D-03:** Store explicit raw JSON signals for each ticker and evaluation point. Replay must pass them through the production parser rather than storing only pre-validated signal objects.
- **D-04:** OHLCV fixtures include the indicator warm-up period through the fixed evaluation date. Any attempt to access later data must fail immediately through an explicit future-access guard.

### Replay state progression
- **D-05:** Support two state modes. Focused cases start from their own explicit initial state; steps inside a full-day scenario carry cash, positions, and daily-loss state forward in order.
- **D-06:** Apply each fixture-defined deterministic fill immediately after its step so later tickers observe updated state.
- **D-07:** Phase 7 models complete fill and no fill only. Partial fills, ambiguous submissions, broker reconciliation, and restart recovery remain Phase 9 scope.
- **D-08:** Process multi-ticker scenarios in production screener-rank order, breaking equal scores by ascending ticker code.

### Manifest and stable result identity
- **D-09:** The manifest records hashes for the scenario, OHLCV, and raw-signal fixtures; the complete policy snapshot; code revision; initial cash, positions, and daily-loss state; fixed evaluation time and trading date; and fixture schema version.
- **D-10:** Compute stable result identity from both deterministic manifest inputs and ordered normalized outcomes. Identical inputs that produce different outcomes must yield different identities and expose nondeterminism.
- **D-11:** Represent code state with the Git commit plus a content hash of relevant tracked changes, allowing reproducible evidence from a dirty worktree without pretending it equals the clean commit.
- **D-12:** Include fixture-fixed evaluation time in deterministic identity. Keep actual invocation time, duration, and output path as observational metadata excluded from the stable identity.

### Operator output and policy comparison
- **D-13:** Default CLI output shows the stable result ID, scenario-level BUY/HOLD/SELL and blocked counts, and verification status. Expand ticker-level detail only for failed checks or differences from expected outcomes.
- **D-14:** Persist the complete manifest, ordered outcomes, and verification checks as normalized JSON. Human-readable daily and period reporting remains Phase 8 scope.
- **D-15:** Compare BUY-policy strictness as a gate funnel with explicit denominators: evaluated, selected, BUY-signaled, confidence-qualified, risk-qualified, validly sized, and order-eligible. Show HOLD, SELL, and blocked-reason counts with explicit denominators as well.
- **D-16:** CLI and JSON must state that replay validates policy paths rather than profitability. Do not generate P&L, return, win-rate, Sharpe, or similar performance metrics.

### the agent's Discretion
- Choose fixture file layout, schema serialization details, CLI command/flag names, normalized JSON field names, hashing algorithm, and output-directory conventions consistent with the existing Python/Typer patterns.
- Define additional focused cases when needed to prove the locked requirements, provided they remain within deterministic policy-path validation.

### Deferred Ideas (OUT OF SCOPE)
- Partial fills, ambiguous submissions, broker reconciliation, duplicate reruns, and restart recovery remain Phase 9 mock-soak scope.
- Human-readable daily and period reports remain Phase 8 scope.
- Profitability backtesting is outside v1.1; advisory policy calibration remains Phase 10 scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| REPLAY-01 | Replay OHLCV through production screening, fixture signal, parser, risk, sizing, and gate with no live providers or clock. | Use a replay-only orchestrator over `screen_candidates` and `execute_signal_cycle`; never call `build_runtime`. |
| REPLAY-02 | Inspect deterministic manifest with hashes, policy, revision, initial state, outcomes, and stable identity. | Canonical JSON bytes plus SHA-256; separate deterministic identity material from observational metadata. |
| REPLAY-03 | Compare BUY/HOLD/SELL policy behavior without claiming profitability. | Emit an explicit-denominator gate funnel and a mandatory non-profitability disclaimer; exclude all performance fields. |
| REPLAY-04 | Verify thresholds, malformed signals, stale data, overrides, HOLD/SELL, and no look-ahead. | Parameterized focused fixtures plus a guarded point-in-time OHLCV adapter and interaction scenarios. |
</phase_requirements>

## Summary

Phase 7 should be implemented as a new offline application service, not as a variant of the live CLI runtime. The production decision seams are already suitable: `screen_candidates` is a pure ranked transform with stable `(-score, ticker)` ordering, and `execute_signal_cycle` runs the shipped raw parser, risk precedence, confidence gates, sizing, and dry-run/order boundary. [VERIFIED: codebase inspection of `trading_bot/screener.py` and `trading_bot/execution.py`] The live `run_cycle` path conditionally calls `build_runtime`, which constructs KIS, pykrx, news, LLM, SQLite, notifier, calendar, and wall-clock collaborators; replay must bypass it entirely. [VERIFIED: codebase inspection of `trading_bot/cli.py`]

Use versioned JSON fixture bundles loaded into frozen typed replay models. Hash raw fixture file bytes independently for provenance, but compute the stable result ID over one canonical semantic document containing deterministic manifest inputs and ordered normalized outcomes. Python's standard `json.dumps(..., sort_keys=True, separators=(",", ":"), allow_nan=False)` and `hashlib.sha256` are sufficient; no dependency is needed. [VERIFIED: Python standard-library behavior and installed codebase patterns] Values that can vary per invocation—actual start time, duration, and output path—must live outside the identity payload.

The critical correctness risk is not parsing JSON; it is accidental access to production adapters or data after the evaluation cutoff. Make future access an explicit exception raised by a fixture OHLCV view whenever a requested date exceeds the scenario evaluation date. Add forbidden-import/call tests, run identical fixtures twice, and byte-compare deterministic JSON after removing observational metadata. [VERIFIED: existing project import-boundary test pattern in `tests/test_screener.py` and `tests/test_execution.py`]

**Primary recommendation:** Build `trading_bot/replay.py` as a synchronous, adapter-free orchestrator with typed fixtures, a cutoff-guarded OHLCV view, deterministic state/fill application, canonical JSON hashing, and a thin `bot replay` CLI wrapper.

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Fixture loading and schema validation | API / Backend | Static fixture storage | Python boundary validates versioned JSON before policy logic runs. |
| Historical screening and decision replay | API / Backend | — | Pure application/business logic owns ordering and gate evaluation. |
| Sequential cash/position/loss state | API / Backend | In-memory storage | Scenario-local state is explicit and ephemeral; no audit DB is required. |
| Manifest and stable identity | API / Backend | Filesystem output | Canonical serialization and hashing are application evidence concerns. |
| Operator output | CLI / Client | API / Backend | Typer renders only a summary from the complete normalized result. |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Python stdlib `dataclasses`, `json`, `hashlib`, `pathlib`, `subprocess` | Python 3.10+ project contract | Typed immutable replay inputs, canonical serialization, SHA-256, file IO, Git evidence | Already available; avoids introducing a replay framework. [VERIFIED: `pyproject.toml`] |
| Existing `trading_bot.screener` | repository revision | Production candidate filtering/ranking | Already pure, offline, explicit-date, and deterministically ordered. [VERIFIED: codebase] |
| Existing `trading_bot.execution` / `signal_parser` / `risk` | repository revision | Production parser, risk, confidence, sizing, and order gate | These are the shipped rules Phase 7 must exercise, not reproduce. [VERIFIED: codebase] |
| Existing `MockBroker` or a replay-local Broker implementation | repository revision | Position reads and deterministic complete fills | `MockBroker` mutates only on explicit `place_order` and uses deterministic accounting/order sequence. [VERIFIED: codebase] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Typer | 0.26.8 | `bot replay` command and concise operator output | Thin command wrapper only. [VERIFIED: `pyproject.toml`] |
| pytest | 8.4.2 | Unit, boundary, integration, CLI, and reproducibility tests | Existing suite and config; targeted Phase 7 baseline is 96 tests in 0.51s. [VERIFIED: local execution] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Versioned JSON fixtures | YAML | Adds a parser dependency and extra scalar/coercion ambiguity without phase value. |
| Stdlib SHA-256 canonical payload | UUID/random run IDs | Random IDs cannot establish stable replay equivalence. |
| Replay-local normalized JSON | SQLite audit tables | Couples Phase 7 to Phase 8/9 persistence and introduces invocation metadata into deterministic evidence. |

**Installation:** None. Phase 7 should add no external package.

## Package Legitimacy Audit

Not applicable: no package installation is recommended.

## Architecture Patterns

### System Architecture Diagram

```text
versioned fixture bundle
  |-- scenario + expected outcomes
  |-- OHLCV rows through fixed cutoff
  |-- raw JSON signal per ticker/step
  |-- initial cash/positions/daily loss + fill instruction
  v
fixture loader/validator --> fixture byte hashes
  v
cutoff-guarded OHLCV view --> production screen_candidates
                                      |
                                      v stable rank (-score, ticker)
                           ordered replay steps
                                      |
                                      v
raw signal --> production parse/risk/confidence/sizing/execution gate
                                      |
                     +----------------+----------------+
                     |                                 |
               no fill / HOLD                  fixture complete fill
                     |                                 |
                     +----------> next explicit state-+
                                      |
                                      v
ordered normalized outcomes + explicit-denominator funnel
                                      |
                   deterministic identity payload --SHA-256--> result_id
                                      |
                        normalized JSON + concise CLI summary

External boundary: no LLM, KIS, Naver, pykrx, SQLite, network, or wall clock.
```

### Recommended Project Structure

```text
trading_bot/
├── replay.py                 # Models, fixture loader, orchestrator, normalization/hash
└── cli.py                    # Thin `replay` command
tests/
├── fixtures/replay/          # Versioned focused and full-day JSON bundles/OHLCV
└── test_replay.py            # Requirement and determinism coverage
```

### Pattern 1: Two documents—identity and observation

Build an identity document from deterministic inputs and outcomes, hash canonical bytes, then wrap it with observational metadata. Do not hash the wrapper.

```python
canonical = json.dumps(
    identity_document,
    sort_keys=True,
    separators=(",", ":"),
    ensure_ascii=False,
    allow_nan=False,
).encode("utf-8")
result_id = hashlib.sha256(canonical).hexdigest()
```

[VERIFIED: Python stdlib API; `allow_nan=False` rejects non-JSON NaN/Infinity rather than emitting unstable/non-standard numeric tokens.]

### Pattern 2: Explicit future-access guard

The fixture store should validate both supplied rows and every query. This makes a look-ahead attempt observable even if future rows are absent.

```python
def rows_through(self, requested_date: date) -> tuple[OhlcvRow, ...]:
    if requested_date > self.evaluation_date:
        raise FutureDataAccessError(requested_date, self.evaluation_date)
    return tuple(row for row in self.rows if row.trading_date <= requested_date)
```

[VERIFIED: project requirement D-04 and existing fail-closed pure-policy style.]

### Pattern 3: State machine owned by the scenario

Focused fixtures create fresh state for one case. A full-day bundle owns one mutable-in-orchestrator state object, iterates already-ranked candidates, applies `COMPLETE` or `NONE` immediately, and snapshots state after every step. Daily-loss updates must come from explicit fixture facts; Phase 7 must not infer market P&L.

### Pattern 4: Reuse production stages, record replay stages

Do not duplicate BUY/HOLD/SELL rules. Wrap production calls and translate their results into a replay outcome containing selection status, parsed decision, confidence qualification, risk qualification/override, sizing validity, order eligibility, fill instruction/result, terminal action, reason code, and before/after state. This supplies the gate funnel without modifying production logic.

### Anti-Patterns to Avoid

- **Calling `build_runtime` or `run_cycle`:** may create live adapters and wall-clock/calendar behavior; replay owns an offline composition root.
- **Reimplementing thresholds or risk rules:** results can drift from production and cease to validate shipped behavior.
- **Hashing Python `repr`, unsorted mappings, file paths, timestamps, or duration:** makes identity process/platform/invocation dependent.
- **Using `MockBroker.place_order` for `NONE` fills:** it always completes accepted orders; no-fill must skip mutation explicitly.
- **Inferring realized loss from fixture price movement:** crosses into P&L/backtesting and invents policy state; carry explicit daily-loss state/facts.
- **Only omitting future rows:** does not prove code avoided requesting them; require the guard exception and a negative test.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Screening order | New replay ranking | `screen_candidates` | Production already hard-filters then sorts `(-score, ticker)`. |
| Signal validation | Fixture-to-object shortcut | `parse_signal` via `execute_signal_cycle` | Malformed raw JSON must exercise the shipped fail-safe parser. |
| Risk/sizing/action rules | Replay-specific policy evaluator | `execute_signal_cycle`, `evaluate_position_risk`, `build_order_intent` | One source of trading truth prevents drift. |
| Complete-fill accounting | Portfolio simulator | Existing `MockBroker` or equivalent minimal replay broker | Phase only needs complete/no fill, not market microstructure. |
| Canonical hash | Custom hashing format | Stdlib JSON + SHA-256 | Stable, inspectable, ubiquitous primitives. |

**Key insight:** The replay engine should orchestrate and observe production rules; it should not become a second trading engine.

## Common Pitfalls

### Pitfall 1: Live dependency leakage
**What goes wrong:** Tests pass locally but replay loads `.env`, clock, SQLite, provider, or network adapters.
**Why it happens:** Reusing the convenient production runtime builder.
**How to avoid:** Separate offline composition root; import/call guards; CLI test monkeypatches every live builder to raise.
**Warning signs:** `Settings()` required to load a fixture, network package imports, or output varies by date.

### Pitfall 2: Semantically unstable result IDs
**What goes wrong:** Same scenario produces different IDs, or changed outcomes retain an old ID.
**Why it happens:** Hashing raw output wrapper, unordered structures, floats with NaN, or only inputs.
**How to avoid:** Typed normalized document, fixed list ordering, sorted keys, `allow_nan=False`, explicit schema version, input+outcome hash.
**Warning signs:** Invocation timestamp appears in hashed data or a repeated-run test fails.

### Pitfall 3: Funnel double-counting
**What goes wrong:** Percentages look plausible but stages use different implicit populations.
**Why it happens:** Aggregating only terminal actions.
**How to avoid:** Store boolean/stage facts per evaluated ticker, declare the denominator beside every numerator, and test algebraic invariants.
**Warning signs:** `order_eligible > validly_sized`, or BUY-qualified counts include SELL/HOLD signals.

### Pitfall 4: State contamination
**What goes wrong:** Focused cases depend on prior cases or a no-fill changes cash/positions.
**Why it happens:** Sharing a broker/state object across bundles or always placing order intents.
**How to avoid:** Fresh state per focused scenario, scoped state per full-day scenario, explicit fill dispatch and before/after snapshots.
**Warning signs:** Scenario order changes results.

### Pitfall 5: Dirty-worktree evidence is incomplete
**What goes wrong:** The manifest records HEAD plus a generic `dirty=true`, so the tested code cannot be identified.
**Why it happens:** Git diff content is omitted or untracked/relevant-file policy is undefined.
**How to avoid:** Hash HEAD plus normalized tracked diff for a documented relevant path set; record that untracked files are excluded or include relevant untracked fixture bytes separately through fixture hashes.
**Warning signs:** Two different tracked edits produce the same code-state evidence.

## Code Examples

### Deterministic order inherited from production

```python
# Existing production contract in trading_bot/screener.py
survivors.sort(key=lambda candidate: (-candidate.score, candidate.ticker))
```

### Explicit fill application

```python
result = execute_signal_cycle(..., dry_run=True)
if step.fill == "COMPLETE" and result.order is not None:
    replay_broker.place_order(result.order)
elif step.fill != "NONE":
    raise FixtureValidationError("unsupported Phase 7 fill state")
```

The decision pass remains dry-run so provider order evidence and UUID generation do not enter identity; the deterministic replay fill is a separate scenario instruction. [VERIFIED: `execute_signal_cycle` dry-run semantics and `MockBroker` accounting]

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|------------------|--------|
| Live-provider historical reruns | Frozen raw signals and point-in-time data | Removes model/provider drift and cost. |
| Backtest returns as validation | Policy-path replay with explicit funnels | Tests safety gates without false profitability claims. |
| Random run identity | Content-addressed deterministic result identity | Makes replay equivalence and nondeterminism inspectable. |

**Deprecated/outdated:** No project API is deprecated for this phase. Avoid extending the legacy free-text `CycleAuditEvent` as the only replay schema; Phase 6 already established bounded terminal vocabulary and normalized evidence.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| — | None. Recommendations are grounded in locked context, repository inspection, local execution, and Python standard-library contracts. | — | — |

## Open Questions (RESOLVED)

1. **Relevant tracked code path set for D-11**
   - What we know: HEAD plus relevant tracked diff content must identify dirty code state.
   - **Decision / Resolution:** Adopt the Phase 07-02 and shipped `build_replay_manifest` contract: record Git HEAD separately and hash the normalized tracked diff only for explicit replay-relevant source/config inputs (`trading_bot`, `pyproject.toml`, and `uv.lock` by default, with the path set remaining an explicit argument). Do not describe this as an all-tracked-files `tracked_worktree` hash. Untracked scenario inputs remain attributable through the independent fixture hashes.
   - Rationale: This matches the implemented manifest boundary, keeps the code-state scope explicit and reproducible, and preserves D-11's distinction between the clean commit and relevant dirty execution content.

2. **Fixture schema implementation type**
   - What we know: the project uses frozen dataclasses for domain transforms and Pydantic at configuration/provider boundaries.
   - **Decision / Resolution:** Adopt frozen dataclasses plus explicit validating loader functions in `trading_bot/replay.py`. The Phase 07-06 nested raw-OHLCV and explicit indicator-policy schema extends this same loader/dataclass pattern; it does not instantiate `Settings`, introduce Pydantic at the replay boundary, or add a dependency.
   - Rationale: This is the shipped replay pattern, keeps fixture validation offline and secret-free, and makes the strict cutoff/schema rules visible at the replay composition boundary.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.4.2 |
| Config file | `pyproject.toml` |
| Quick run command | `.venv/bin/python -m pytest -q tests/test_replay.py tests/test_screener.py tests/test_execution.py` |
| Full suite command | `PYTHONUSERBASE="$PWD/.python-userbase" .venv/bin/python -m pytest -q` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| REPLAY-01 | Offline fixture traverses production screen/parser/risk/sizing/gate and live builders are unreachable | integration/import boundary | `.venv/bin/python -m pytest -q tests/test_replay.py -k 'offline or production_path'` | ❌ Wave 0 |
| REPLAY-02 | Manifest fields, fixture/code hashes, canonical output, dirty diff, repeated stable ID | unit/integration | `.venv/bin/python -m pytest -q tests/test_replay.py -k 'manifest or identity or dirty'` | ❌ Wave 0 |
| REPLAY-03 | Explicit-denominator funnel, actions/block reasons, disclaimer, no profitability keys | unit/CLI | `.venv/bin/python -m pytest -q tests/test_replay.py tests/test_cli.py -k 'funnel or disclaimer or replay'` | ❌ Wave 0 / ✅ extend |
| REPLAY-04 | Threshold edges, malformed, stale, risk exits, HOLD/SELL, sizing and look-ahead guard | parameterized boundary | `.venv/bin/python -m pytest -q tests/test_replay.py -k 'boundary or lookahead or catalog'` | ❌ Wave 0 |

### Sampling Rate

- **Per task commit:** targeted `tests/test_replay.py` selector plus the touched production contract tests.
- **Per wave merge:** `.venv/bin/python -m pytest -q tests/test_replay.py tests/test_screener.py tests/test_signal_parser.py tests/test_risk.py tests/test_execution.py tests/test_cli.py`
- **Phase gate:** full suite green; run a representative replay twice and compare deterministic payload bytes/result ID.

### Wave 0 Gaps

- [ ] `tests/test_replay.py` — shared builders plus REPLAY-01..04 requirement tests.
- [ ] `tests/fixtures/replay/` — versioned focused/full-day fixture catalog, raw signals, cutoff data, and expected outcomes.
- [ ] Extend `tests/test_cli.py` — `bot replay` summary/failure detail/output/disclaimer and no-live-builder tests.
- [ ] No framework installation or config change required.

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|------------------|
| V2 Authentication | no | Offline local fixture command has no identity boundary. |
| V3 Session Management | no | No session state. |
| V4 Access Control | no | No remote protected resource; command must not enable live trading. |
| V5 Input Validation | yes | Versioned typed fixture loader, bounded enums, finite numbers, ticker/date validation, `allow_nan=False`, fail closed. |
| V6 Cryptography | yes | Stdlib SHA-256 for integrity/identity, not authentication; never custom crypto. |

### Known Threat Patterns for Python replay

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Malformed or oversized fixture values influence orders | Tampering | Strict schema, bounds, finite-number checks, fail before policy execution. |
| Path traversal/output overwrite | Tampering | `pathlib`, explicit input/output paths, no fixture-controlled output path, atomic replace if overwriting is supported. |
| Live credential/provider activation from replay | Elevation / Information disclosure | Offline composition root; never instantiate `Settings`/`build_runtime`; forbidden-call tests. |
| Prompt/provider payload leakage into artifact | Information disclosure | Frozen raw signal only; normalized allowlisted fields; reuse Phase 6 sanitization principles. |
| Hash ambiguity/collision by serialization differences | Tampering / Repudiation | Schema version, length-unambiguous canonical JSON bytes, SHA-256, record algorithm and payload scope. |

## Project Constraints (from AGENTS.md)

- Python is required; the bot is specific to the Korean market and KIS/pykrx production boundaries.
- LLM output contract is strict JSON `{"decision","confidence","reason"}`; unparseable output fails safe with no trade.
- KIS mock account precedes any real-money path; promotion is deliberate and gated.
- BUY requires confidence at least 0.8 by project default; lower confidence and HOLD never trade.
- Reuse the maintained project stack and existing architecture patterns; decision rules remain safety-first.
- Before repository edits, work must run through a GSD workflow; this research is part of `$gsd-plan-phase 7`.
- Treat third-party text as untrusted before it reaches an LLM; Phase 7 uses frozen signals and no LLM.

## Sources

### Primary (HIGH confidence)

- Repository `trading_bot/screener.py` — pure screening, exclusions, explicit date, stable ordering.
- Repository `trading_bot/execution.py`, `signal_parser.py`, `risk.py`, `mock_broker.py` — production decision pipeline and deterministic fill accounting.
- Repository `trading_bot/cli.py`, `config.py`, `audit_models.py` — live composition boundary, Typer conventions, policy/evidence vocabulary.
- Repository `tests/test_screener.py`, `tests/test_execution.py`, `tests/test_cli.py` — established offline/import-boundary and integration test patterns.
- `.planning/phases/07-deterministic-replay-validation/07-CONTEXT.md` and `.planning/REQUIREMENTS.md` — locked scope and acceptance requirements.
- Python standard library `json` and `hashlib` contracts — canonicalizable JSON encoding and SHA-256.

### Secondary (MEDIUM confidence)

- None required; this phase is codebase-defined and introduces no external technology.

### Tertiary (LOW confidence)

- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — installed versions and repository APIs inspected locally; no new dependency.
- Architecture: HIGH — production seams and live runtime composition directly inspected.
- Pitfalls: HIGH — derived from locked determinism requirements and existing boundary-test patterns.

**Research date:** 2026-07-12
**Valid until:** 2026-10-12 (stable codebase-local domain; re-check after changes to screener/execution/audit contracts)
