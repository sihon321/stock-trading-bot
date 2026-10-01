---
phase: 10
slug: advisory-risk-calibration-promotion-readiness
status: gaps_found
nyquist_compliant: true
wave_0_complete: true
created: 2026-08-10
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.4.2 + Typer `CliRunner` |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_calibration.py tests/test_calibration_reporting.py tests/test_promotion_readiness.py tests/test_report_cli.py` |
| **Full suite command** | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` |
| **Estimated runtime** | focused < 15 seconds; full suite < 40 seconds |

## Sampling Rate

- **After every task commit:** Run the task's focused test file(s).
- **After every plan wave:** Run the Phase 10 focused suite plus directly affected replay/report/soak regressions.
- **Before `$gsd-verify-work`:** Full suite must be green, with any pre-existing collection defect identified explicitly rather than excluded silently.
- **Max feedback latency:** 40 seconds.

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Secure behavior | Test type | Automated command | Status |
|---------|------|------|-------------|-----------------|-----------|-------------------|--------|
| 10-01-01 | 01 | 1 | CAL-01, CAL-02, CAL-04 | Candidate catalog accepts only baseline or one-field variants | unit | `python3 -m pytest -q tests/test_calibration.py -k 'catalog or variant or baseline'` | ✓ test suite passed (2026-10-01) |
| 10-01-02 | 01 | 1 | CAL-02, CAL-04 | Existing audit/soak files are read without mutation and abnormal cycles remain separate | integration | `python3 -m pytest -q tests/test_calibration_reporting.py -k 'readonly or evidence or abnormal or denominator'` | ✓ test suite passed (2026-10-01) |
| 10-02-01 | 02 | 2 | CAL-01, CAL-02 | Production replay path evaluates every one-field candidate deterministically | unit | `python3 -m pytest -q tests/test_calibration.py -k 'counterfactual or confidence or position or stop or take'` | ✓ test suite passed (2026-10-01) |
| 10-02-02 | 02 | 2 | CAL-01, CAL-02 | Ranking is risk-first, short-sample candidates remain provisional, and ties retain baseline | unit/render | `python3 -m pytest -q tests/test_calibration.py tests/test_calibration_reporting.py` | ✓ test suite passed (2026-10-01) |
| 10-03-01 | 03 | 3 | CAL-01, CAL-02, CAL-04 | Calibration CLI constructs no live/settings/mutable collaborator | CLI integration | `python3 -m pytest -q tests/test_report_cli.py -k 'calibration'` | ✓ test suite passed (2026-10-01) |
| 10-03-02 | 03 | 3 | CAL-04 | Terminal/file output is byte-identical, conflict-safe, and always advisory | CLI integration | `python3 -m pytest -q tests/test_report_cli.py tests/test_cli.py` | ✓ test suite passed (2026-10-01) |
| 10-04-01 | 04 | 4 | CAL-03, CAL-04 | Any BLOCK/UNKNOWN, incomplete/failed soak, or active unresolved order produces BLOCKED | unit | `python3 -m pytest -q tests/test_promotion_readiness.py` | ✓ test suite passed (2026-10-01) |
| 10-04-02 | 04 | 4 | CAL-03, CAL-04 | Readiness CLI and runbook separate assessment from manual real-mode change | CLI/docs | `python3 -m pytest -q tests/test_report_cli.py tests/test_operator_runbook.py tests/test_cli.py` | ✓ test suite passed (2026-10-01) |

## Wave 0 Requirements

Existing pytest, replay fixtures, SQLite fixture builders, and Typer CLI helpers cover all requirements. Each production task creates or extends its named test before implementation; no new framework or shared fixture scaffold is required.

## Manual-Only Verifications

All safety and evidence semantics have automated coverage. Human review of Korean wording and table readability is advisory and cannot substitute for automated checklist/status assertions.

## Validation Sign-Off

- [x] All tasks have an automated verification command.
- [x] Sampling continuity has no untested task gap.
- [x] Existing infrastructure covers Wave 0.
- [x] No watch-mode flags.
- [x] Expected feedback latency is under 40 seconds.
- [x] `nyquist_compliant: true` is set for the planned coverage.

**Approval:** verification gaps found on 2026-10-01; see `10-VERIFICATION.md`.

## Final Verification Results — 2026-10-01

- Phase 10 focused suite plus CLI/runbook contracts: 86 passed in 2.26s using `.venv/bin/python -m pytest`.
- Entire workspace suite: 815 passed in 21.00s, with no collection exclusions. The historical soak-campaign collection defect no longer reproduces.
- All eight planned task test groups are covered by the executed focused suite above. Per-task markers record test execution only; final integration acceptance remains blocked by the gaps below.
- Current runtime calibration and readiness evidence reads fail with `unsupported primary audit schema tables` because Phase 11 adds independently owned portfolio tables.
- Readiness CLI does not propagate resolved historical ambiguity; it hardcodes the count to zero. Reducer-only coverage does not verify this operator behavior.
- Final phase acceptance remains `gaps_found` until both integration gaps are closed. No live request, order, configuration write, or campaign mutation was performed.
