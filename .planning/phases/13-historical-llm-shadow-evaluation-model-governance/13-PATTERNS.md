# Phase 13 — Pattern Map

**Mode:** Inline inspection; 2026-10-01. New symbols below are planned, not existing code.

| New/changed file | Role | Closest existing analog | Adaptation |
|---|---|---|---|
| shadow_models.py | strict frozen manifest/response | backtest_models.py: `Frozen`, `Amount`, `content_hash` | Reuse canonical finite Decimal rules; bounded identity/unknown facts |
| shadow_inputs.py | offline snapshots/sampling | backtest_inputs.py: `decision_view`; prompts.py: `render_prompt` | Freeze raw-close price and shipped adjusted technicals separately; no news fetch |
| backtest_engine.py | value-only pre-decision observer | Existing per-ticker loop before `execute_signal_cycle` | Observer sees no mutable ledger/broker; identical canonical result with/without observer |
| backtest_ledger.py | read-only affordability projection | Existing reserve logic | Shared with project_backtest_action to prevent fee/quantity divergence |
| shadow_budget.py | deterministic accounting | backtest_ledger.py: `PortfolioLedger` | Separate LLM costs; consumed + uncertain + reserved never hidden |
| shadow_store.py | durable run journal | portfolio_store.py / sqlite_audit.py guarded transitions | New DB only; transaction reservation + dispatch intent, append-only events, exclusive owner |
| shadow_providers.py | single-shot envelope | llm_provider.py Claude/OpenAI request signatures | Do not reuse live logging/retry/execution; SDK retries 0 |
| shadow_runner.py | resumable orchestration | soak campaign guarded state transitions | One request per reserved attempt; persist before/after; interruption/unknown block |
| shadow_reporting.py | validated comparisons/report | backtest_reporting.py validated load/build/render | Same canonical state; full counts and provenance; no profitability winner |
| shadow_cli.py + CLI mounts | operator interface | backtest_cli.py + report_cli.py | Offline prepare/report; explicit run/resume; LLM-only credentials lazy |
| tests/test_shadow_*.py | behavior tests | tests/test_backtest_engine.py and test_backtest_cli.py | Fake transport, crash injection, monkeypatch capability tripwires |

## Concrete observed seams

`backtest_engine.py` calls `ledger.start_session`, applies actions/fills/settlement, builds `view = decision_view(...)`, computes shipped indicators, then iterates held-first targets. Inside this loop `execute_signal_cycle(..., dry_run=True)` precedes `ledger.reserve(...)`. Place the snapshot collector immediately before these operations, not after `ledger.snapshot(...)` at session end.

`backtest_models.py` has `model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)` and canonical `content_hash`. Reuse strict canonical evidence, but frozen top-level dicts alone are not deep immutability: snapshot values must have immutable typed substructure/canonical copies.

`prompts.py` renders sorted technical keys and delimits third-party news with `<untrusted_news>`. Preserve this exact prompt content/version in manifests; any shadow-specific metadata rendering requires its own frozen version and hash.

`backtest_reporting.py` validates saved result by rebuilding metrics/evidence and uses no-overwrite atomic publication. Use this pattern for finalized shadow JSON/text; do not call private writers without first defining their narrow public reusable contract.

`llm_provider.py` has `_call_provider_with_retry`, `_log_cycle` and `run_llm_cycle`, and existing provider protocol returns `LLMSignal` only. These are explicitly not the shadow runner/provider interface.

`cli.py` mounts `report_app` and `backtest_app` at lines 154–156. `report_cli.py` holds standalone `report_app`. Add shadow mounts without triggering `Settings`, SQLite audit creation, workers or broker construction; import-time `dotenv.load_dotenv()` is existing behavior and must never grant order capability to the new handlers.
