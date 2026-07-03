---
phase: 05-real-money-readiness-operations
plan: 05
subsystem: execution-audit
tags: [OPS-02, audit, confidence, sqlite, fail-safe]
requires:
  - "05-03: sqlite_audit.write_decision confidence REAL column + writer"
  - "05-04: injectable CLI run_cycle orchestration"
provides:
  - "ExecutionResult.confidence carries parsed signal confidence out of the execution core"
  - "decisions.confidence persisted end-to-end for every parsed signal (OPS-02, D-10)"
affects:
  - "trading_bot/execution.py"
  - "trading_bot/cli.py"
  - "tests/test_cli.py"
tech_stack:
  added: []
  patterns:
    - "Confidence rides the execution-layer result carrier (ExecutionResult), not the frozen CycleAuditEvent (D-11 honored literally, D-10 satisfied)"
    - "NULL-on-parse-failure kept as the fail-safe: confidence stays None only when there is no parsed signal"
key_files:
  created: []
  modified:
    - "trading_bot/execution.py"
    - "trading_bot/cli.py"
    - "tests/test_cli.py"
decisions:
  - "confidence rides ExecutionResult (appended last, Optional default None) so CycleAuditEvent stays a frozen stdlib dataclass with zero changes (D-11), while write_decision receives a real value (D-10)"
  - "parse-error _finalize_cycle call-site deliberately omits confidence= so it defaults None — NULL-on-parse-failure is correct fail-safe behavior, not a gap"
metrics:
  duration: ~8 min
  completed: 2026-07-03
  tasks: 2
  files: 3
status: complete
---

# Phase 05 Plan 05: OPS-02 Confidence Persistence Summary

Threaded the parsed LLM signal confidence from `execute_signal_cycle` out through a new optional `ExecutionResult.confidence` field into the production CLI audit write, so `decisions.confidence` is non-null for every parsed signal — closing the single OPS-02 blocking gap where the CLI hardcoded `confidence=None` at the write site.

## What Was Built

- **`ExecutionResult.confidence: Optional[float] = None`** — appended as the last field so every existing positional/keyword construction (including `evaluate_signal_action` and test fixtures) stays valid without edits.
- **`_finalize_cycle(..., confidence: Optional[float] = None)`** — the single `ExecutionResult` construction point now threads a confidence keyword. The three PARSED call-sites (risk-override, daily-loss kill-switch, normal action) pass `confidence=confidence` (the `parsed.signal.confidence` computed once per cycle); the parse-error call-site leaves it at the `None` default.
- **`CycleAuditEvent` untouched** — still a frozen stdlib dataclass with the same fields (D-11 honored literally).
- **CLI read sites** — `_outcome_from_result` returns `result.confidence` (was literal `None`); `run_cycle`'s `write_decision` call passes `confidence=result.confidence` (was `confidence=None`). The per-ticker error/except outcome dict keeps `"confidence": None` (an error ticker has no parsed signal).
- **`test_confidence_persisted_end_to_end`** — drives the real `_run_llm_cycle -> execute_signal_cycle` path (with `run_cycle=None`) through the real `write_decision` sink into an in-memory SQLite DB, then reads `SELECT confidence FROM decisions` back and asserts it equals the provider's 0.95. It also asserts the fail-safe: a failing ticker records no decisions row, so confidence is non-null ONLY for the successfully parsed signal.

## Key Links (source of truth -> sink)

`parsed.signal.confidence` (execution.py) -> `ExecutionResult.confidence` -> `result.confidence` (cli.py) -> `write_decision(confidence=...)` -> `decisions.confidence` column. The parse-error branch never sets it, so `ExecutionResult.confidence` stays `None` -> `decisions.confidence` NULL on parse failure.

## Verification

- `tests/test_cli.py::test_confidence_persisted_end_to_end` passes: stored `decisions.confidence == 0.95`, non-null (inverts the verifier's failing NULL probe at 05-VERIFICATION.md line 94).
- Regression proof: temporarily reverting the CLI write site to `confidence=None` makes the new test fail with `assert None is not None`; restoring it passes. The test is not tautological.
- `tests/test_sqlite_audit.py` passes — CycleAuditEvent unchanged and still frozen; no new field.
- `tests/test_execution.py` passes — execution/risk/signal_parser behavior unchanged.
- Full suite: **305 passed** (`python3.14 -m pytest -q`, PYTHONUSERBASE pointed at the shared `.python-userbase`).

## Deviations from Plan

None — plan executed exactly as written.

Environment note (not a code deviation): the worktree does not carry the gitignored `.python-userbase`, and the plan's `python3` resolves to system Python 3.9 here. Per the recorded project test convention (PYTHONUSERBASE + Python 3.14, native extension must match the interpreter), tests were run with `/opt/homebrew/bin/python3.14` and `PYTHONUSERBASE` pointed at the shared checkout's `.python-userbase` (pydantic 2.13.4 native build matches 3.14). This only changes how the documented verify command is invoked, not what it asserts.

## Threat Mitigations Applied

| Threat ID | Mitigation |
|-----------|-----------|
| T-05-18 (Repudiation: audit drops LLM confidence) | Confidence threaded through ExecutionResult to write_decision; end-to-end test pins the DB round-trip (non-null 0.95) |
| T-05-19 (Tampering: parse-failure records spurious non-null) | Parse-error call-site leaves confidence None; NULL-on-failure asserted (no decisions row for the failing ticker) |
| T-05-20 (EoP: re-opening frozen Phase 2-4 logic/domain types) | Confidence rides ExecutionResult only; CycleAuditEvent unchanged and frozen; risk engine, confidence gate, and signal parser untouched |

## Commits

- `6bf6ab5` feat(05-05): thread parsed signal confidence into the audit write
- `f60f523` test(05-05): pin confidence persistence end-to-end (OPS-02)

## Self-Check: PASSED

- SUMMARY.md present on disk.
- Commits 6bf6ab5, f60f523 (task commits) and b37144d (docs) all present in git history.
