---
phase: quick-260720-elk
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - trading_bot/data_source.py
  - trading_bot/pykrx_adapter.py
  - tests/test_market_cycle.py
  - tests/test_pykrx_adapter.py
autonomous: true
requirements:
  - QUICK-HOLIDAY-EVIDENCE-COMMIT-01
must_haves:
  truths:
    - "The existing weekend and holiday OHLCV evidence fix passes its 38 focused regression tests before commit."
    - "The atomic code commit contains exactly the two implementation files and two regression-test files already modified for this fix."
    - "The unfinished weekend-data debug note and every Phase 09 artifact remain outside the code commit."
  artifacts:
    - trading_bot/data_source.py
    - trading_bot/pykrx_adapter.py
    - tests/test_market_cycle.py
    - tests/test_pykrx_adapter.py
  key_links:
    - "pykrx_adapter._normalize_frame holiday-frame rejection -> ObservedKRXCalendar trading-day evidence"
    - "holiday and available-empty regression tests -> the exact existing implementation diff"
    - "explicit git add pathspec -> four-file-only atomic commit"
---

<objective>
Verify and atomically commit the existing weekend and holiday OHLCV trading-day evidence fix without changing its implementation or tests.

Purpose: Preserve the already-written fail-closed holiday handling as one reviewable code commit while leaving unfinished diagnostic and Phase 09 work untouched.
Output: One verified git commit whose changed paths are exactly the four allowed code and test files.
</objective>

<execution_context>
@/Users/oceano/Project/Python/auto-trader/stock-trading-bot/.codex/gsd-core/workflows/execute-plan.md
@/Users/oceano/Project/Python/auto-trader/stock-trading-bot/.codex/gsd-core/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@AGENTS.md
@.planning/debug/weekend-data-marked-stale.md
@trading_bot/data_source.py
@trading_bot/pykrx_adapter.py
@tests/test_market_cycle.py
@tests/test_pykrx_adapter.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Verify and commit the existing holiday evidence diff with an exact path allowlist</name>
  <files>trading_bot/data_source.py, trading_bot/pykrx_adapter.py, tests/test_market_cycle.py, tests/test_pykrx_adapter.py</files>
  <action>
Treat the current working-tree content of the four listed files as immutable input: do not edit, format, or otherwise rewrite implementation or tests. First inspect `git diff --` for exactly those paths and confirm it remains the focused change already present: all-zero whole-market holiday data normalizes to unavailable, an available-but-empty frame cannot prove a trading day, and the two matching regression tests cover those cases.

Run `.venv/bin/python -m pytest tests/test_market_cycle.py tests/test_pykrx_adapter.py -q` and require the reported result to be exactly 38 passing tests. If practical, also run `.venv/bin/python -m pytest -q`; a full-suite failure blocks the commit unless it is demonstrably unrelated and is recorded with evidence in the summary. Run `git diff --check --` against exactly the four allowed paths. Run `ruff check` against exactly the four allowed paths when a repository-local or PATH-provided Ruff executable is available; do not install a package or modify files to obtain Ruff, and record tool unavailability in the summary when it is absent.

Before staging, inspect `git status --short` and preserve all unrelated work. Stage with one explicit `git add -- trading_bot/data_source.py trading_bot/pykrx_adapter.py tests/test_market_cycle.py tests/test_pykrx_adapter.py`; never use a broad pathspec. Verify `git diff --cached --name-only` is exactly that four-path set and verify `git diff --cached --check` passes. If any other path is staged, unstage only the unintended path without discarding its working-tree content, then repeat the allowlist check. In particular, `.planning/debug/weekend-data-marked-stale.md`, the `.planning/debug/` directory, this quick-plan artifact, and all `.planning/phases/09-*` content must remain absent from the staged code diff.

Create one atomic commit with message `fix(data): handle holiday OHLCV evidence`. After committing, verify `git show --format= --name-only HEAD` lists exactly the four allowed paths and `git status --short` still shows the unfinished debug note as uncommitted/untracked if it was present before execution. Do not amend, absorb, or otherwise include Phase 09 artifacts.
  </action>
  <verify>
    <automated>.venv/bin/python -m pytest tests/test_market_cycle.py tests/test_pykrx_adapter.py -q &amp;&amp; git diff --cached --check &amp;&amp; test "$(git show --format= --name-only HEAD | sed '/^$/d' | sort)" = "$(printf '%s\n' tests/test_market_cycle.py tests/test_pykrx_adapter.py trading_bot/data_source.py trading_bot/pykrx_adapter.py | sort)"</automated>
  </verify>
  <done>The focused run reports 38 passed; the full suite is green when practical; diff hygiene passes; optional Ruff is green when available or its absence is recorded; one commit exists with exactly the four allowed paths; no debug note, quick artifact, or Phase 09 artifact appears in that code commit; and none of the four files was edited during execution.</done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| working tree -> git index | Unrelated debug and Phase 09 work shares the repository but must not cross into this code commit. |
| existing diff -> verification tools | The executor may inspect and test the diff but has no authority to rewrite the four files. |

## STRIDE Threat Register

| Threat ID | Category | Component | Severity | Disposition | Mitigation Plan |
|-----------|----------|-----------|----------|-------------|-----------------|
| T-quick-260720-01 | Tampering | git staging boundary | high | mitigate | Stage only the four explicit paths, compare the cached path set to the allowlist before commit, and verify the committed path set afterward. |
| T-quick-260720-02 | Repudiation | regression verification | medium | mitigate | Require the named 38-test focused run and preserve full-suite, diff-check, and Ruff outcomes in the quick summary. |
| T-quick-260720-03 | Information Disclosure | unfinished debug note | medium | mitigate | Keep `.planning/debug/` outside the index and committed path set; never quote or copy the unfinished note into the code commit. |
| T-quick-260720-SC | Tampering | package installation | low | accept | No dependencies or tools are installed; Ruff is used only if already available. |
</threat_model>

<source_audit>

| Source | ID | Feature/Requirement | Plan | Status | Notes |
|--------|----|---------------------|------|--------|-------|
| GOAL | QUICK-HOLIDAY-EVIDENCE-COMMIT-01 | Verify and atomically commit the existing weekend/holiday evidence fix | 01 | COVERED | Single task owns verification, exact staging, commit, and post-commit proof. |
| REQ | QUICK-HOLIDAY-EVIDENCE-COMMIT-01 | Commit exactly the four allowed modified files | 01 | COVERED | Explicit path allowlist before and after commit. |
| RESEARCH | — | No research artifact applies | 01 | COVERED | Existing diff only; no implementation or dependency choice. |
| CONTEXT | — | Exclude debug note and Phase 09 artifacts | 01 | COVERED | Staging and post-commit gates explicitly exclude both scopes. |

</source_audit>

<verification>
- The targeted command reports exactly 38 passing tests.
- The full test suite passes when practical, with any unrelated blocking failure evidenced in the summary.
- `git diff --check` and cached diff checks pass for the four-file change.
- Ruff passes for the four files when already available; no tool installation is performed.
- The committed path set equals the four-file allowlist and excludes `.planning/debug/`, this quick plan, and `.planning/phases/09-*`.
</verification>

<success_criteria>
- The existing holiday/weekend evidence fix is preserved unchanged and committed once.
- The commit contains exactly `trading_bot/data_source.py`, `trading_bot/pykrx_adapter.py`, `tests/test_market_cycle.py`, and `tests/test_pykrx_adapter.py`.
- The focused 38-test regression set is green, with broader verification recorded.
- The unfinished debug note and all Phase 09 work remain outside the code commit.
</success_criteria>

<output>
Create `.planning/quick/260720-elk-commit-the-existing-weekend-and-holiday-/260720-elk-SUMMARY.md` when done.
</output>
