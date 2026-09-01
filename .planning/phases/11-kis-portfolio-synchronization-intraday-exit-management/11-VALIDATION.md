---
phase: 11
slug: kis-portfolio-synchronization-intraday-exit-management
status: planned
nyquist_compliant: true
wave_0_complete: false
created: 2026-09-02
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.4.2 |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_portfolio.py tests/test_mutation_lease.py tests/test_exit_manager.py tests/test_intraday.py tests/test_phase11_cli.py -x` |
| **Full suite command** | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` |
| **Estimated runtime** | ~2 seconds focused; full-suite runtime measured during execution |

---

## Sampling Rate

- **After every task commit:** Run the new module's focused test plus directly affected upstream tests; target under 30 seconds.
- **After every plan wave:** Run the Phase 11 focused suite plus `tests/test_kis_order.py`, `tests/test_kis_broker.py`, `tests/test_soak_reconcile.py`, `tests/test_cli.py`, and `tests/test_sqlite_audit.py`.
- **Before `$gsd-verify-work`:** Run the full suite; it must remain green.
- **Max feedback latency:** 30 seconds for task-level automated feedback.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 11-01-01 | 01 | 1 | PORT-01, PORT-02, EXIT-02 | T-11-02 / T-11-03 | Whole-account pagination, cancellation normalization, and divergence classification fail closed | unit + adapter regression | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_portfolio.py tests/test_kis_order.py tests/test_soak_reconcile.py -x` | 🆕 task | ⬜ pending |
| 11-01-02 | 01 | 1 | PORT-01, EXIT-01 | T-11-05 / T-11-08 | Immutable snapshot/evaluation evidence and one daily identity survive crash and races | SQLite integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_portfolio_store.py tests/test_sqlite_audit.py -x` | 🆕 task | ⬜ pending |
| 11-02-01 | 02 | 2 | PORT-01, EXIT-02 | T-11-01 / T-11-03 | Only the exact active account-scoped owner token may mutate | multiprocessing + integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_mutation_lease.py -k 'exclusive or active or owner or renew or permissions' -x` | 🆕 task | ⬜ pending |
| 11-02-02 | 02 | 2 | PORT-01, EXIT-02 | T-11-01 / T-11-06 | Restart recovery terminalizes prior work and reconciles before ACTIVE | multiprocessing + recovery | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_mutation_lease.py tests/test_portfolio_store.py -x` | 🆕 task | ⬜ pending |
| 11-03-01 | 03 | 3 | PORT-02, EXIT-01 | T-11-02 / T-11-09 | Held-first dual-provenance universe and fixed safe held context | unit + prompt | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_portfolio.py tests/test_prompts.py -x` | 🆕 task | ⬜ pending |
| 11-03-02 | 03 | 3 | PORT-01, PORT-02, EXIT-01 | T-11-05 / T-11-08 | Daily identity reuse never repeats LLM or bypasses current broker/risk/lease gates | orchestration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_phase11_cli.py tests/test_cli.py tests/test_execution.py -x` | 🆕 task | ⬜ pending |
| 11-04-01 | 04 | 4 | EXIT-01, EXIT-02 | T-11-01 / T-11-04 | Shared SELL lifecycle suppresses open/partial duplicates, oversell, cancel, and chase | unit + integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_exit_manager.py tests/test_risk.py tests/test_execution.py -x` | 🆕 task | ⬜ pending |
| 11-04-02 | 04 | 4 | PORT-01, EXIT-01, EXIT-02 | T-11-01 / T-11-02 / T-11-04 | Shared BUY/SELL boundary refreshes truth/quote, reruns gates, then reasserts lease before one evidence-backed POST | integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_exit_manager.py tests/test_kis_broker.py tests/test_execution.py -x` | 🆕 task | ⬜ pending |
| 11-05-01 | 05 | 5 | PORT-01, EXIT-01, EXIT-02 | T-11-01 / T-11-07 | Independent no-LLM iterations obey cadence and exact KRX session phases | timeline + config | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_intraday.py tests/test_config.py -x` | 🆕 task | ⬜ pending |
| 11-05-02 | 05 | 5 | EXIT-01, EXIT-02 | T-11-04 / T-11-06 | Commands, SIGINT, lease loss, and restart reconcile before release | CLI + timeline | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_intraday.py tests/test_phase11_cli.py tests/test_cli.py -x` | 🆕 task | ⬜ pending |
| 11-06-01 | 06 | 6 | EXIT-01, EXIT-02 | T-11-03 / T-11-05 / T-11-07 | Durable transition evidence dedups alerts; transport is fail-soft and evidence fail-closed | integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_phase11_cli.py tests/test_sqlite_audit.py tests/test_cli.py -x` | 🆕 task | ⬜ pending |
| 11-06-02 | 06 | 6 | PORT-01, PORT-02, EXIT-01, EXIT-02 | T-11-10 | Runbook and full injected regression prohibit unsafe operator recovery | docs + regression | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_operator_runbook.py tests/test_phase11_cli.py tests/test_intraday.py tests/test_exit_manager.py tests/test_mutation_lease.py tests/test_portfolio.py tests/test_portfolio_store.py -x` | 🆕 task | ⬜ pending |

Task IDs and wave assignments match the final six executable plans. Every missing test file is created in the same task whose RED/GREEN contract uses it, so no separate unverified production-only Wave 0 task exists.

---

## Wave 0 Requirements

- [x] Plan 11-01 Task 1 creates `tests/test_portfolio.py` and extends `tests/test_kis_order.py` for account scope, pagination, cancellation, union, and divergence.
- [x] Plan 11-01 Task 2 creates `tests/test_portfolio_store.py` for migration, immutable snapshots, unique evaluation, and recovery.
- [x] Plan 11-02 creates `tests/test_mutation_lease.py` before lease/recovery implementation.
- [x] Plan 11-04 creates `tests/test_exit_manager.py` and extends `tests/test_kis_broker.py` plus `tests/test_execution.py` before shared SELL lifecycle and mandatory BUY/SELL pre-POST boundary implementation.
- [x] Plan 11-05 creates `tests/test_intraday.py` and extends `tests/test_phase11_cli.py` before orchestration.
- [x] Plan 11-06 completes `tests/test_phase11_cli.py` and runbook regression coverage.

No test framework installation is needed.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Authenticated mock-account pagination and portfolio field mapping | PORT-01 | Requires KIS mock credentials and live provider responses | Run the documented mock portfolio probe; confirm every page, cash/holding/orderable/average-price field, continuation token, and sanitized evidence record. Do not promote to real credentials. |
| Partial-cancellation field combinations and terminal-state precedence | EXIT-02 | Official examples expose fields but cannot prove the authenticated mock combinations | Place a bounded mock SELL, partially fill/cancel where possible, reconcile it, and confirm no second POST or local oversell is possible. Record sanitized observations in the UAT artifact. |
| Session cutoff and SIGINT operator experience | EXIT-01 | Wall-clock/session and terminal signal behavior needs an operator observation in addition to injected-clock tests | Run watch mode against mock/read-only conditions across the configured cutoff or send Ctrl-C at each documented lifecycle point; confirm reconciliation-only shutdown and bounded Korean status output. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verification and create/extend their tests before production behavior.
- [x] Sampling continuity: every task has focused automated verification.
- [x] All missing test references are owned by explicit TDD tasks.
- [x] No automated test depends on real-time watch-mode flags; clocks and sleepers are injected.
- [x] Focused commands are scoped to the researched under-30-second feedback target.
- [ ] Full repository suite remains green (baseline: 732 passed on 2026-09-02).
- [x] `nyquist_compliant: true` is set after final plan/task reconciliation.

**Approval:** planned; execution evidence pending
