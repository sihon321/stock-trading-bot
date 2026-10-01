# Phase 13: Historical LLM Shadow Evaluation & Model Governance — Research

**Researched:** 2026-10-01
**Requirements:** FUT-02, GOV-01
**Confidence:** HIGH for repository seams and pinned SDK contracts; conditional for operator-selected model pricing/context capabilities.
**Runtime:** Inline Codex skill-adapter fallback; no independent agent context was spawned. Research, planning and adversarial review are recorded separately but do not constitute independent-agent review.

## User Constraints

All D-01–D-16 in `13-CONTEXT.md` are locked. Default: 100 sampled units, one explicit model/prompt variant, one dispatch each, 100 attempts / 200,000 total tokens / USD 5 / concurrency 1. Freeze and budget explicit overrides. No live orders, settings writes or promotion. Current-model historical knowledge contamination must remain visible.

## Summary

Build a separate frozen-manifest shadow workflow. Prepare/sampling/report are offline; only an explicitly invoked run/resume can construct a dedicated single-shot API provider. Every SDK retry layer must be disabled. The runner owns durable dispatch reservation, terminal observations and conservative UNKNOWN accounting; providers return observation envelopes instead of live `LLMSignal` cycles. Paid calls are not required for implementation verification.

The critical seam is before each baseline ticker evaluation, after prior fills/actions/settlement and earlier ticker reservations. Existing `BacktestRun.decisions` and end-of-day `sessions` cannot reconstruct this intermediate state alone. Add a frozen value-only observer to the canonical replay, invoked before fixture execution/reservation and also for excluded/incomplete evaluation units. It captures raw decision-close tradable price, shipped adjusted indicators, held lot/available quantity, daily loss, cash and reservations, status, unknowns and applicable policy. Re-running with/without collection must have identical canonical trading evidence. Avoid a separate copied ledger simulator. Plan 13-02 extracts `project_backtest_action(snapshot, raw_signal)` and any required read-only affordability projection from the existing ledger; both the canonical engine and shadow comparisons consume that shared contract.

Validate any supplied baseline saved result and bind it to the bundle and resolved window/profile/policy. Capture a fresh replay and reconcile its semantic decision/fill/cash/holding trajectory with the supplied baseline; retain the original baseline bytes/hash and record current collector code separately. Expected code-revision identity differences do not permit changed trading behavior. A semantics mismatch blocks preparation. Initially generated baselines are persisted once before calls. Fixture signals and outcomes never become shadow-dependent.

## Architectural Responsibility Map

| Capability | Owner / tier | Boundary |
|---|---|---|
| Historical truth and ticker ordering | backtest engine / offline simulation | Emits frozen values before each decision; no provider imports |
| Cutoff snapshots / sampling / prompt freeze | shadow_inputs / offline preparation | Strict bundle and optional frozen news only; no current data fetch |
| Strict manifests / outcomes | shadow_models / pure domain | Explicit identities, finite limits, unknown facts; no secrets |
| Reservations / journal / resume | shadow_budget + shadow_store / local evidence | Durable before dispatch, exclusive ownership, no live SQLite |
| Network call and usage extraction | shadow_providers / isolated LLM adapter | One HTTP request, explicit credential and allowlisted endpoint |
| Hypothetical risk/action comparison | shadow_reporting / offline analysis | Identical canonical state per variant, no ledger mutation |
| Operator routing | shadow_cli / CLI | prepare/report offline; run/resume explicit; no live Settings |

## Standard Stack

Reuse Python stdlib `json`, `hashlib`, `decimal`, `pathlib`, `sqlite3`, `dataclasses`/Pydantic, pytest/Typer/httpx and the already pinned `openai==2.44.0`, `anthropic==0.115.1`. Do not upgrade packages or add an agent/evaluation framework. Exact installed token definitions were inspected under `.python-userbase/lib/python/site-packages/{openai,anthropic}/types/`. Both installed SDK constants set default retries to 2; configure `max_retries=0` and an explicit bounded timeout.

## Package Legitimacy Audit

No package-manager install is planned. Existing dependencies are defined in `pyproject.toml`; the official provider SDK repositories below corroborate publisher identity. No new package name or install task is introduced.

## Architecture Patterns

### Single-shot observation envelopes

Do not reuse `build_llm_provider` or `run_llm_cycle`; existing adapters log full prompts, retry and discard usage/model envelope facts. Create isolated adapters receiving frozen prompt/schema/model/settings and only dedicated LLM credentials. OpenAI uses a schema-constrained Chat Completions `create` response so raw content, refusal, finish reason, model, usage and request ID survive even invalid/truncated output; revalidate locally. Claude uses exactly one forced `emit_signal` tool with strict schema, never executes the tool and rejects multiple/wrong tool blocks. No server/client tools, web search, cache opt-in, audio, batching, thinking opt-in or configurable base URL. Unsupported model/settings combinations are preflight failures, not reason to silently change settings or retry.

Normalize OpenAI prompt + completion totals. Reasoning/cached tokens are subdivisions, not additions to those totals. Claude input + cache-read + cache-creation + inclusive output form the total; output reasoning is not added twice. Unknown/malformed usage retains the reservation. A pricing-based cost is ESTIMATED even with actual token facts; ACTUAL cost requires an explicit attributable billed fact. Detect actual usage/model mismatch or reservation breach, retain actual facts, mark budget/accounting breach and stop new calls rather than clipping evidence to the cap.

### Budget proof

Use a reviewed, frozen provider/model/endpoint capability and pricing record including source URL, retrieval/review date, currency, tier, maximum accepted input-context tokens, generation ceiling and billing dimensions. Before dispatch reserve a sound upper bound for input + all generated tokens and their cost; safest initial bound is the documented accepted context ceiling plus the enforced output ceiling (conservative double allowance is safe). A heuristic character count or token-count estimate is not a hard bound. A tighter bound is permitted only with a verified model-specific proof. Default output ceiling 1,024 tokens, subject to the supported endpoint contract. Reject unbounded/unknown profiles. Token counting endpoints, if used, are not signal-generation calls, must be rate-bounded and are estimates; they cannot alone justify releasing budget reservations.

Freeze USD pricing by default. Non-USD records require an attributable frozen FX conversion and preserve native-currency facts. Test prices are explicitly synthetic fixture facts; no invented current price is shipped as a reviewed profile. Price/model selection belongs in the operator-supplied reviewed manifest. This means the workflow can intentionally stop short of 100 samples when conservative reservations consume the budget.

### Durable state and ownership

Use a dedicated shadow journal, separate from audit/soak DBs, to atomically reserve budget and insert dispatch intent under exclusive run ownership before provider access. Transactions support crash recovery; schema migration applies only to the new journal. Metadata may mark materialized progress, but evidence rows are append-only with unique stable attempt IDs and legal transitions. Persist outcome before settling reservation. Never hold a DB transaction during HTTP. A second owner must fail before dispatch. Recover only after positive proof the owner is gone; interruption/unknown ownership fails closed. Persisted DISPATCH_STARTED without a result becomes UNKNOWN with full reservation retained. Ambiguous persistence failure after provider dispatch also leaves reserved UNKNOWN evidence and halts. No automatic retry at any layer.

### Reports and immutable identity

A run spec ID hashes normalized baseline, sample, snapshots, variants, actual prompt/schema, pricing, limits and code content. A distinct immutable observation-run ID separates two requests with the same spec; attempts remain unique, with observational timestamps outside deterministic semantic hashes. Resume validates the existing frozen manifest and code facts rather than editing it. Report regeneration validates journal/saved-result cardinality, IDs/hashes, transition order, budget and counts; hash equality detects accidental tampering but is not an external signature/authenticity claim.

Compute comparisons using the same unit's canonical snapshot and shipped gate semantics, including parse-failure-before-risk, sizing, reservation affordability, unknown-data BUY blocking, tradability, ticks and next-session availability. Pure simulation helpers or forbidden-submission adapters may be used; no broker factory, live account or mutable order object crosses the boundary. No hypothetical action changes baseline holdings or affects the next unit. Agreement is consistency, not quality. Default evidence grade is advisory/INSUFFICIENT_EVIDENCE; exact equality can be NO_MEANINGFUL_DIFFERENCE, with explicit sample counts.

## Don't Hand-Roll

Do not duplicate technical indicators, screening, ledger, trade schema, confidence/risk precedence, or money rounding. Reuse pure code and validated saved-evidence patterns; create only the provider envelope, immutable snapshots, budget/journal and reporting orchestration needed here. Do not infer intraday fills or reconstruct news from current pages.

## Common Pitfalls

- End-of-day holdings used for a decision earlier in the day: collector must observe the exact pre-decision state.
- Copying live provider wrappers: hidden SDK + tenacity retries violate attempt/cost limits.
- Estimated cost labeled actual; missing usage priced at zero; reasoning double-counted.
- A timeout auto-repeated on resume: original charge is uncertain, so retain full reservation.
- Two processes independently checking a budget: exclusive ownership plus atomic reservation prevents duplicate calls.
- `codex exec` inherits home config, MCP/tools, secrets or workspace capability. Existing CLI is installed (0.144.6) but its pinned isolation/cost proof was not established. D-08 therefore explicitly blocks Codex CLI for shadow with `UNSUPPORTED_SHADOW_CAPABILITY`; subprocess never starts. This is the locked fail-closed path, not provider substitution.
- Live `Settings`, dotenv writes, broker construction or promotion imports added to convenience CLI paths.
- Sampled shadow signals treated as full alternative strategy return or a deployable winner.

## Assumptions Log

- Complete real historical bundles/news and reviewed current model pricing are operator inputs; neither is supplied or fabricated during this phase.
- Provider availability and output are nondeterministic; immutable observed evidence is replayable, network responses are not.
- A local journal is trusted owner-managed evidence, not a remote attestation service.

## Open Questions

No user preference remains unresolved. Runtime model/endpoint compatibility and pricing must be explicitly reviewed; absence blocks paid dispatch while offline preparation/reporting and fake-provider verification work. Independent-agent review is unavailable under the skill adapter's no-automatic-spawn rule; perform inline adversarial checks and label the limitation.

## Environment Availability

| Dependency | Available | Fallback |
|---|---|---|
| Python / pytest / pinned SDKs | Existing project userbase | `PYTHONUSERBASE="$PWD/.python-userbase" python3` |
| Codex CLI | Installed 0.144.6 | Block shadow subprocess until safety/cost proof exists |
| LLM credentials / reviewed profiles | Not inspected | Fake injected client; explicit runtime preflight |
| Historical bundle / optional news | Synthetic fixture available | Label coverage incomplete; never fabricate real history |

## Validation Architecture

Use pytest 8.4.2 and `pyproject.toml`; no new test framework. All tests inject provider clients/transports and remain offline.

| Requirement | Behavioral evidence | Planned tests |
|---|---|---|
| FUT-02 | cutoff-safe snapshots, deterministic sample and paired gates | test_shadow_inputs.py, test_shadow_reporting.py |
| FUT-02 | caps, interrupts, resume and single-shot calls | test_shadow_budget.py, test_shadow_store.py, test_shadow_runner.py |
| GOV-01 | immutable full provenance and unknown cost facts | test_shadow_models.py, test_shadow_providers.py, test_shadow_reporting.py |
| GOV-01 | forbidden capabilities and no policy promotion | test_shadow_cli.py and provider tripwires |

Each task creates its owned tests before its implementation checks; fixture infrastructure belongs to 13-01. Quick command: `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_shadow_*.py`; per-wave include backtest regression; final gate runs full suite. Runtime estimates (~30s full, <60s focused) are planning targets, not measured Phase 13 evidence.

## Security Domain

Strict bounded JSON (duplicates/NaN/unknown keys denied), frozen Decimal rates and budgets, no secrets in evidence/repr/logs, explicit provider-origin allowlist without redirects/proxies inherited from env, bounded response/input sizes, no arbitrary subprocess/model tools, no live DB schema mutations. Threats T-13-01 future input leakage, T-13-02 hidden retries/budget breach, T-13-03 journal corruption/duplicate dispatch, T-13-04 accidental order or policy authority, T-13-05 secrets/prompt injection and T-13-06 malformed usage/false governance claims are covered in executable tasks.

## Sources

Primary sources checked 2026-10-01; repository/pinned installed SDK contracts take precedence over newer README examples. No floating model IDs/prices copied.

- [OpenAI Python SDK](https://github.com/openai/openai-python) — retry disabling and explicit timeout; cross-checked pinned `_constants.py`.
- [Claude token counting](https://platform.claude.com/docs/en/build-with-claude/token-counting) — counts include request structure and remain estimates.
- [Claude context windows](https://platform.claude.com/docs/en/build-with-claude/context-windows) — input/cache and generated usage dimensions.
- [OpenAI Chat Completions API](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create) — schema/output request contract; must validate selected model compatibility.
- [Claude pricing](https://platform.claude.com/docs/en/about-claude/pricing) — pricing dimension review source, no live numeric tariff asserted.
- [Official Anthropic SDK](https://github.com/anthropics/anthropic-sdk-python) — publisher; pinned local usage/constants supply actual contract.
- Local: `trading_bot/backtest_engine.py`, `backtest_reporting.py`, `llm_provider.py`, `prompts.py`, `execution.py`, `ports.py`, `pyproject.toml`.

## Metadata

Repository seams and installed token/retry contracts: HIGH. Live model tariff/context-isolation capability: CONDITIONAL, runtime preflight mandatory. No paid requests made.
