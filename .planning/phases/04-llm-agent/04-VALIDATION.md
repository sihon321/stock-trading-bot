---
phase: 4
slug: llm-agent
status: ready
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-02
updated: 2026-07-02
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.4.2 (`[tool.pytest.ini_options]` in pyproject.toml; `testpaths=["tests"]`, `pythonpath=["."]`) |
| **Config file** | pyproject.toml |
| **Quick run command** | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_llm_provider.py tests/test_prompts.py tests/test_trade_signal.py -x` |
| **Full suite command** | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` |
| **Estimated runtime** | ~30 seconds (full suite, offline — all provider tests use injected fake SDK clients) |

---

## Sampling Rate

- **After every task commit:** Run the quick run command (scoped to the plan's test files)
- **After every plan wave:** Run `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 4-01-01 | 01 | 1 | LLM-02 | T-04-SC | [SUS] pins human-approved before any install | human gate | N/A — `checkpoint:human-verify` (blocking-human) | — | ⬜ pending |
| 4-01-02 | 01 | 1 | LLM-02 | T-04-SC | Only approved exact pins installed; suite unaffected | integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -c "import anthropic, openai, structlog; print(anthropic.__version__, openai.__version__, structlog.__version__)" && PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` | ✅ self-contained | ⬜ pending |
| 4-01-03 | 01 | 1 | LLM-02 | — | Non-positive LLM retry knobs fail Settings closed | unit | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_config.py -x` | ✅ exists (extended in-task) | ⬜ pending |
| 4-02-01 | 02 | 1 | LLM-02, LLM-03 | T-04-01, T-04-05 | Hostile news item stays inside the untrusted_news block; SYSTEM_PROMPT carries the ignore-instructions rule | unit | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_prompts.py -x` | ❌ created in-task | ⬜ pending |
| 4-02-02 | 02 | 1 | LLM-02, LLM-03 | T-04-02 | TradeSignal ↔ LLMSignal lockstep; round-trip through parse_signal; extras forbidden | unit | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_trade_signal.py -x && PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_ports.py -x` | ❌ created in-task | ⬜ pending |
| 4-03-01 | 03 | 2 | LLM-01, LLM-02, LLM-03 | T-04-02, T-04-03, T-04-04 | Claude request has strict forced tool + no temperature/top_p/top_k; refusal/missing-block/malformed → LLMProviderError; bounded retry; one secret-free llm_signal_cycle line | unit | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_llm_provider.py -x && PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_ports.py -x` | ❌ created in-task | ⬜ pending |
| 4-03-02 | 03 | 2 | LLM-01, LLM-02, LLM-03 | T-04-02, T-04-04 | OpenAI parse with temperature 0.0 + response_format=TradeSignal; refusal/None-parsed → LLMProviderError | unit | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_llm_provider.py tests/test_prompts.py tests/test_trade_signal.py -x` | ❌ created in-task | ⬜ pending |
| 4-04-01 | 04 | 3 | LLM-01 | T-04-03, T-04-SC | Factory selects provider from config only; SDKs stay unloaded in a fresh interpreter; secret confined to real-client construction | unit | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_llm_provider.py -x && PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_ports.py -x` | ❌ created in-task | ⬜ pending |
| 4-04-02 | 04 | 3 | LLM-03 | T-04-04 | LLMProviderError → audited HOLD with zero broker calls; success flows through unchanged execute_signal_cycle under dry_run | unit + integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_llm_provider.py -x && PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` | ❌ created in-task | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

Test files are created inside the same task as the code they verify (test-with-implementation, matching prior phases), so no standalone Wave 0 plan is needed. The prerequisites that must exist before Wave 2 adapter tests can run are owned by Wave 1 plans:

- [ ] `anthropic`, `openai`, `structlog` installed into `.python-userbase` — plan 04-01 Task 2 (gated by the blocking-human dependency checkpoint, Task 1)
- [ ] `tests/test_prompts.py`, `tests/test_trade_signal.py` — plan 04-02 (created with their modules)
- [ ] `tests/conftest.py` (`make_data_context`, `FakeAnthropicClient`, `FakeOpenAIClient`; `make_settings` added in 04-04) — plans 04-03/04-04
- [ ] `tests/test_llm_provider.py` — plan 04-03 (extended in 04-04)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Dependency pin / OpenAI model ID / D-07 divergence approval | LLM-02 | Package-legitimacy [SUS] verdicts and dependency lock-in are never auto-approvable in this project | Plan 04-01 Task 1 checkpoint: review pypi.org pages, approve pins + model ID + temperature handling |

All other phase behaviors have automated verification (offline fake-client tests; no live API call required anywhere in Phase 4).

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies (sole exception: the blocking-human dependency checkpoint, which is human-by-design)
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (test files created in the same tasks as their code; installs gated in Wave 1)
- [x] No watch-mode flags
- [x] Feedback latency < 60s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending (approve during `/gsd-execute-phase 4`)
