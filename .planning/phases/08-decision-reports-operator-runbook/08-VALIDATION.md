---
phase: 08
slug: decision-reports-operator-runbook
status: draft
nyquist_compliant: false
wave_0_complete: false
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
| 08-W0-01 | TBD | 0 | REP-01 | T-08-01 | Parameterized read-only audit queries; sanitized output | unit + CLI | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_reporting.py tests/test_report_cli.py -k daily` | ❌ W0 | ⬜ pending |
| 08-W0-02 | TBD | 0 | REP-02 | T-08-02 | Replay integrity checked before aggregation; unknown states preserved | unit + CLI | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_reporting.py tests/test_report_cli.py -k 'period or replay'` | ❌ W0 | ⬜ pending |
| 08-W0-03 | TBD | 0 | RUN-01 | T-08-03 | Unknown safety evidence blocks mutation | unit + CLI + docs | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_preflight.py tests/test_operator_runbook.py` | ❌ W0 | ⬜ pending |
| 08-W0-04 | TBD | 0 | RUN-02 | T-08-04 | Audit failure blocks; notification failure remains attributable | unit + CLI + docs | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_preflight.py tests/test_operator_runbook.py -k failure` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_reporting.py` — SQLite fixtures, evidence-state classification, processing order, preview differences, period denominators, reconciliation reduction, and Korean reasons.
- [ ] `tests/test_report_cli.py` — nested commands, input validation, read-only behavior, terminal/file equality, replay compatibility, and integrity errors.
- [ ] `tests/test_preflight.py` — mock/audit/KRX/unresolved-order PASS/BLOCK/UNKNOWN plus shared status/run enforcement.
- [ ] `tests/test_operator_runbook.py` — fixed schedule, completion checklist, all RUN-02 failure rows, prohibited reruns/resubmissions, and resolution criteria.
- [ ] Extend `tests/test_sqlite_audit.py`, `tests/test_cli.py`, and `tests/test_notifier.py` for notification persistence while retaining fail-soft delivery behavior.

No framework installation or pytest configuration change is required.

---

## Manual-Only Verifications

All Phase 8 behaviors have automated unit, CLI integration, or documentation-contract verification. Human review of report readability remains advisory and does not replace automated acceptance checks.

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30 seconds
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
