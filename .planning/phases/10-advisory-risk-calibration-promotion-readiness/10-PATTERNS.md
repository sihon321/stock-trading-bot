# Phase 10: Advisory Risk Calibration & Promotion Readiness - Pattern Map

**Mapped:** 2026-08-10
**Scope:** New read-only calibration and readiness services plus existing report CLI integration

## File Classification

| Planned file | Role | Closest analog | Required pattern |
|--------------|------|----------------|------------------|
| `trading_bot/calibration.py` | immutable domain + counterfactual service | `trading_bot/replay.py`, `trading_bot/execution.py`, `trading_bot/risk.py` | Frozen dataclasses/StrEnum, pure deterministic functions, canonical policy identity |
| `trading_bot/calibration_reporting.py` | read-only evidence projection + renderer | `trading_bot/reporting.py`, `trading_bot/soak_reporting.py` | Existing regular files only, URI `mode=ro`, `query_only`, explicit stable transactions, exact denominators |
| `trading_bot/promotion_readiness.py` | pure checklist reducer | `trading_bot/preflight.py`, `trading_bot/soak_reporting.py` | PASS/BLOCK/UNKNOWN, fail closed, normalized scalar facts, stable reason codes |
| `trading_bot/report_cli.py` | credential-free Typer controller | existing `daily`, `period`, `replay` commands | Narrow arguments/settings, bounded diagnostics, `_deliver()` byte identity |
| `docs/operator-runbook.md` | manual readiness procedure | Phase 8/9 runbook tables | Exact commands, evidence gates, prohibited actions, resolution criteria |
| `tests/test_calibration.py` | unit/counterfactual tests | `tests/test_replay.py`, `tests/test_execution.py`, `tests/test_risk.py` | Frozen fixture inputs, boundary cases, deterministic equality |
| `tests/test_calibration_reporting.py` | projection/render tests | `tests/test_reporting.py`, `tests/test_soak_reporting.py` | Before/after DB bytes, schema drift, UNKNOWN visibility, denominator reconciliation |
| `tests/test_promotion_readiness.py` | checklist tests | `tests/test_preflight.py`, `tests/test_soak_reporting.py` | One-gate-at-a-time BLOCK/UNKNOWN, snapshot hash changes, no mutation |
| `tests/test_report_cli.py` | CLI integration | existing report CLI tests | Cleared credentials, constructor traps, output conflict/symlink checks |
| `tests/test_operator_runbook.py` | documentation contract | existing Phase 8/9 semantic tests | Registry/CLI discovery, command order, prohibition assertions |

## Pattern Assignments

### Immutable policy and outcome models

Follow `ReplayManifest`, `ReplayScenario`, `ReplayOutcome`, `ExecutionConfig`, and `RiskConfig`: use frozen dataclasses and explicit typed fields. Use `StrEnum` for persisted/rendered statuses. Reject NaN/infinity and unsupported keys. Store mappings as canonical immutable values where they cross a trust boundary.

### Production-path counterfactuals

Do not reimplement confidence, sizing, stop-loss, or take-profit formulas. Clone a validated `ReplayScenario` policy one field at a time and call `run_replay_scenarios()` so production `execute_signal_cycle()`, `build_order_intent()`, and `evaluate_position_risk()` remain the semantic source of truth. Expected-action mismatch is an observed delta in calibration, not a replay verification failure.

### Read-only evidence owners

Copy `ReadOnlyAuditRepository` and `ReadOnlySoakRepository` safety properties:

- Resolve paths with `strict=True`; reject non-regular files and duplicate inodes.
- Open SQLite through URI `mode=ro` with `isolation_level=None`.
- Set `PRAGMA query_only=ON`.
- Validate `user_version`, exact/required table columns, and stable IDs before using facts.
- Use one explicit transaction per owner; never `ATTACH` independent stores or claim cross-store atomicity.
- Missing/contradictory references become `UNKNOWN` or a hard failure, never omission.

### Explicit denominators

Copy `DenominatorCount`, `ReplayCount`, and soak provenance separation. Every calibration group exposes eligible, evaluable, excluded, and unknown counts. Render numerator/denominator pairs and assert the categories reconcile. Do not use a single percentage without its denominator.

### Deterministic output

Copy plain newline-normalized renderers and `report_cli._deliver()`/`write_report_text()`. Terminal and saved bytes must match. Existing conflicting output remains untouched. No renderer reads clocks, environment, credentials, or network.

### Fail-closed readiness

Copy `PreflightCheck` semantics and soak report downgrades. Checklist states are `PASS`, `BLOCK`, `UNKNOWN`; both `BLOCK` and `UNKNOWN` produce final `BLOCKED`. Resolved historical ambiguity is a warning fact, but any active freeze/unresolved order is `BLOCK`.

### Canonical snapshot identity

Copy `canonical_json_bytes()` and SHA-256 patterns from replay. Hash the normalized policy, source stable IDs, checklist facts, and explicit acknowledgements. The identity is output evidence, not a stored authorization token. A changed input must produce a changed identity.

### Capability restriction

Copy `ReportSettings`, not full `Settings`. Calibration/readiness code must have no field or constructor for KIS keys, LLM keys, trading mode, confirmation flags, broker, order adapter, or writable SQLite connection. Tests should replace live constructors with raising sentinels and still complete reports.

## Anti-Patterns

- Deriving average price or available cash from audit fields that do not contain them.
- Comparing multi-field bundles despite the locked one-field rule.
- Treating raw scenario count, decision-row count, or drill count as eligible mock days.
- Persisting a mutable `READY` flag or letting readiness invoke configuration writers.
- Ranking on an opaque composite score that hides exposure or trade-opportunity changes.
- Calling a top candidate `recommended` while evidence is insufficient.
- Reusing report/calibration output as proof of profitability.
- Adding schema migrations or dependencies without a demonstrated need; this phase needs neither.

