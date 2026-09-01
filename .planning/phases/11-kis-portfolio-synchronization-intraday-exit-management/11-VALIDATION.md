---
phase: 11
slug: kis-portfolio-synchronization-intraday-exit-management
status: draft
nyquist_compliant: false
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
| 11-01-01 | 01 | 1 | PORT-01 | T-11-02 / T-11-03 | Reject incomplete or malformed account truth and re-gate immediately before POST | unit + integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_portfolio.py tests/test_kis_order.py -x` | ❌ W0 | ⬜ pending |
| 11-02-01 | 02 | 1 | EXIT-02 | T-11-01 / T-11-06 | Only the active account-scoped lease owner may mutate; restart recovery precedes authorization | multiprocessing + integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_mutation_lease.py tests/test_kis_broker.py -x` | ❌ W0 | ⬜ pending |
| 11-03-01 | 03 | 2 | PORT-02, EXIT-01 | T-11-08 | Held-first union is attributable and one daily signal identity cannot be replayed without fresh gates | unit + orchestration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_portfolio.py tests/test_phase11_cli.py -x` | ❌ W0 | ⬜ pending |
| 11-04-01 | 04 | 3 | EXIT-01, EXIT-02 | T-11-01 / T-11-04 | Latest orderable quantity and open-order truth prevent duplicate SELL, oversell, and blind retry | unit + integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_exit_manager.py tests/test_kis_broker.py -x` | ❌ W0 | ⬜ pending |
| 11-05-01 | 05 | 4 | EXIT-01, EXIT-02 | T-11-01 / T-11-04 | Intraday rules run without LLM construction and stop mutation at cutoff or ownership loss | timeline + CLI integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_intraday.py tests/test_phase11_cli.py -x` | ❌ W0 | ⬜ pending |
| 11-06-01 | 06 | 5 | PORT-01, PORT-02, EXIT-01, EXIT-02 | T-11-05 / T-11-07 | Sanitized durable evidence is fail-closed for POST while notification transport is fail-soft | integration + regression | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_phase11_cli.py tests/test_sqlite_audit.py tests/test_cli.py -x` | ❌ W0 | ⬜ pending |

Task IDs and wave assignments are provisional until the planner writes the executable plans; the planner must reconcile this map with final task IDs without weakening requirement or threat coverage.

---

## Wave 0 Requirements

- [ ] `tests/test_portfolio.py` — account scope, completeness, held-first union, divergence, and cancellation normalization fixtures (PORT-01, PORT-02).
- [ ] `tests/test_portfolio_store.py` — schema migration, immutable snapshots, daily evaluation identity, and recovery (PORT-01, EXIT-01).
- [ ] `tests/test_mutation_lease.py` — cross-process exclusion, heartbeat/ownership loss, and restart recovery ordering (EXIT-02).
- [ ] `tests/test_exit_manager.py` — shared daily/intraday SELL lifecycle, partial/cancel/ambiguous states, and no-oversell matrix (EXIT-01, EXIT-02).
- [ ] `tests/test_intraday.py` — injected clock/sleeper/signal timelines, cutoff, and reconciliation-only behavior (EXIT-01, EXIT-02).
- [ ] `tests/test_phase11_cli.py` — command construction, no-LLM intraday proof, exit codes, and terminal evidence (all requirements).
- [ ] Extend `tests/test_kis_order.py` with official cancellation fields and pagination-boundary fixtures (PORT-01, EXIT-02).
- [ ] Extend `tests/test_kis_broker.py` with pre-POST portfolio refresh ordering and no-second-POST cases (EXIT-02).

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

- [ ] All tasks have `<automated>` verification or Wave 0 dependencies.
- [ ] Sampling continuity: no 3 consecutive tasks without automated verification.
- [ ] Wave 0 covers all missing test references.
- [ ] No automated test depends on real-time watch-mode flags; clocks and sleepers are injected.
- [ ] Feedback latency is under 30 seconds for task-level checks.
- [ ] Full repository suite remains green (baseline: 732 passed on 2026-09-02).
- [ ] `nyquist_compliant: true` is set after final plan/task reconciliation.

**Approval:** pending
