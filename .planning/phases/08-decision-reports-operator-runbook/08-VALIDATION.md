---
phase: 08
slug: decision-reports-operator-runbook
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-07-13
---

# Phase 08 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.4.2 with Typer `CliRunner` |
| **Config file** | `pyproject.toml` (`testpaths = ["tests"]`, `pythonpath = ["."]`) |
| **Quick run command** | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_reporting.py tests/test_report_cli.py tests/test_preflight.py tests/test_operator_runbook.py` |
| **Full suite command** | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run the new test file for that task plus the directly affected baseline test (`test_sqlite_audit.py`, `test_cli.py`, `test_replay.py`, or `test_notifier.py`).
- **After every plan wave:** Run all Phase 8 tests plus `tests/test_sqlite_audit.py tests/test_cli.py tests/test_replay.py tests/test_notifier.py`.
- **Before `$gsd-verify-work`:** Full suite must be green.
- **Max feedback latency:** 30 seconds.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 08-01-01 | 08-01 | 1 | REP-01, REP-02, RUN-02 | T-08-01, T-08-02 | Additive notification schema preserves legacy evidence and rejects sensitive/non-scalar details | migration + unit | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_sqlite_audit.py -k 'migration or notification'` | inline TDD extends `tests/test_sqlite_audit.py` | ✅ green |
| 08-01-02 | 08-01 | 1 | REP-01, REP-02, RUN-02 | T-08-01, T-08-03 | Append-only notification attempts remain ordered, attributable, validated, and immutable | unit | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_sqlite_audit.py` | inline TDD extends `tests/test_sqlite_audit.py` | ✅ green |
| 08-02-01 | 08-02 | 2 | REP-01, REP-02 | T-08-04, T-08-07, T-08-08 | Read-only daily/period projections preserve order, denominators, COMPLETED/FAILED/INTERRUPTED/RUNNING and zero-candidate lifecycle evidence, ticker-scoped notifications, and run-scoped FINAL_SUMMARY DELIVERED/FAILED/DISABLED/missing evidence | unit | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_reporting.py -k 'daily or period or readonly or reconciliation or run_lifecycle or zero_candidates or final_summary_notification'` | inline TDD creates `tests/test_reporting.py` | ✅ green |
| 08-02-02 | 08-02 | 2 | REP-01, REP-02 | T-08-05, T-08-06, T-08-07, T-08-08 | Replay IDs are verified before compatible-only aggregation and renderers expose bounded deterministic evidence | unit | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_reporting.py` | inline TDD extends `tests/test_reporting.py` | ✅ green |
| 08-03-01 | 08-03 | 3 | REP-01, REP-02 | T-08-09, T-08-11, T-08-12 | Credential-free report settings and strict inputs keep all report commands offline | CLI integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_report_cli.py -k 'daily or period or replay or offline'` | inline TDD creates `tests/test_report_cli.py` | ✅ green |
| 08-03-02 | 08-03 | 3 | REP-01, REP-02 | T-08-10, T-08-11, T-08-12 | Registered reports print and atomically save identical UTF-8 bytes without output-path ambiguity | CLI integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_report_cli.py tests/test_cli.py` | inline TDD extends `tests/test_report_cli.py`, `tests/test_cli.py` | ✅ green |
| 08-04-01 | 08-04 | 4 | RUN-01, RUN-02, REP-02 | T-08-13, T-08-15, T-08-16, T-08-17 | Global proof failures abort while determinately attributed ambiguity yields exact affected-ticker freezes | unit | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_preflight.py -k 'pass or block or unknown or unresolved or audit'` | inline TDD creates `tests/test_preflight.py` | ✅ green |
| 08-04-02 | 08-04 | 4 | RUN-01, RUN-02, REP-02 | T-08-14, T-08-15, T-08-16, T-08-17 | Shared gate prevents global mutation and freezes only affected candidates; each immediate error persists exactly once with its candidate ticker, each FINAL_SUMMARY persists exactly once with NULL ticker, and report projections keep those scopes disjoint while deriving DELIVERED/FAILED/DISABLED/UNKNOWN | CLI + projection integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_preflight.py tests/test_cli.py tests/test_notifier.py tests/test_reporting.py` | inline TDD extends `tests/test_preflight.py`, `tests/test_cli.py`, `tests/test_notifier.py`, `tests/test_reporting.py` | ✅ green |
| 08-05-01 | 08-05 | 5 | RUN-01, RUN-02, REP-01, REP-02 | T-08-18, T-08-19, T-08-20, T-08-21 | Documentation contract fixes schedule, completion, seven triage rows, prohibitions, and safe resolution semantics | docs contract | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_operator_runbook.py` | inline TDD creates `tests/test_operator_runbook.py` | ✅ green |
| 08-05-02 | 08-05 | 5 | RUN-01, RUN-02, REP-01, REP-02 | T-08-18, T-08-19, T-08-20, T-08-21 | Korean runbook matches shipped commands/codes and all targeted evidence remains green | docs + integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_operator_runbook.py tests/test_preflight.py tests/test_reporting.py tests/test_report_cli.py tests/test_sqlite_audit.py tests/test_cli.py tests/test_replay.py tests/test_notifier.py` | Task creates runbook; prior inline TDD creates tests | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

No separate Wave 0 scaffold is required. Every production-changing task is `tdd="true"`, and the map above names the exact test file created or extended before implementation. Existing pytest/Typer infrastructure is sufficient, and all execution statuses are green.

---

## Manual-Only Verifications

All Phase 8 behaviors have automated unit, CLI integration, or documentation-contract verification. Human review of report readability remains advisory and does not replace automated acceptance checks.

---

## Validation Sign-Off

- [x] All tasks have exact `<automated>` verification commands
- [x] Sampling continuity: every task has automated verification
- [x] No Wave 0/MISSING references; inline TDD creation contracts are mapped above
- [x] No watch-mode flags
- [x] Expected feedback latency < 30 seconds
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved — targeted Phase 8 suite 135 passed; full suite 471 passed on 2026-07-14.
