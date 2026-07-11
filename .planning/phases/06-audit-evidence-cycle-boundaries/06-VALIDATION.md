---
phase: 06
slug: audit-evidence-cycle-boundaries
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-11
---

# Phase 06 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.4.2 |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `.venv/bin/python -m pytest -q tests/test_sqlite_audit.py tests/test_market_cycle.py tests/test_kis_broker.py tests/test_cli.py` |
| **Full suite command** | `PYTHONUSERBASE="$PWD/.python-userbase" .venv/bin/python -m pytest -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run the task's targeted pytest command from the map below.
- **After every plan wave:** Run `PYTHONUSERBASE="$PWD/.python-userbase" .venv/bin/python -m pytest -q`.
- **Before `$gsd-verify-work`:** Full suite must be green, including a v1-schema-to-current migration test.
- **Max feedback latency:** 30 seconds for targeted checks.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 06-W0-01 | TBD | 0 | EVID-04 | T-06-TIME | Fail closed outside confirmed KRX continuous trading and on stale quotes | boundary | `.venv/bin/python -m pytest -q tests/test_market_cycle.py` | ❌ W0 | ⬜ pending |
| 06-AUDIT | TBD | TBD | EVID-01 | T-06-AUDIT | Runs terminalize once, recover abandoned work, and snapshot policy/provenance | integration | `.venv/bin/python -m pytest -q tests/test_sqlite_audit.py tests/test_cli.py` | ✅ extend | ⬜ pending |
| 06-OUTCOME | TBD | TBD | EVID-02 | T-06-OMIT | Every attempted ticker has exactly one normalized terminal outcome | parameterized integration | `.venv/bin/python -m pytest -q tests/test_cli.py tests/test_sqlite_audit.py` | ✅ extend | ⬜ pending |
| 06-ORDER | TBD | TBD | EVID-03 | T-06-RETRY | Ambiguous submissions never blind-retry and order evidence remains append-only | unit/integration | `.venv/bin/python -m pytest -q tests/test_kis_broker.py tests/test_sqlite_audit.py` | ✅ extend | ⬜ pending |
| 06-TIME | TBD | TBD | EVID-04 | T-06-TIME | Completed-bar cutoff and <=10-second pre-submit quote gate are deterministic | boundary | `.venv/bin/python -m pytest -q tests/test_market_cycle.py tests/test_kis_quote.py tests/test_kis_broker.py` | ❌ W0 / ✅ extend | ⬜ pending |

*The planner must replace `TBD` plan/wave values and align task IDs with final PLAN.md files.*

---

## Wave 0 Requirements

- [ ] `tests/test_market_cycle.py` — KRX trading-day/session boundaries, half-open executable window, completed-bar cutoff, and quote-age fixtures.
- [ ] `tests/test_sqlite_audit.py` — v1-to-current schema migration, interrupted-run recovery, uniqueness constraints, and append-only order-event fixtures.
- [ ] `tests/test_cli.py`, `tests/test_kis_broker.py`, or `tests/conftest.py` — injected clock/calendar, quote observation, ambiguous submission, and event-sink fakes.

---

## Manual-Only Verifications

All Phase 6 behaviors have automated verification. Exact KRX boundaries must be source-grounded during implementation, but their runtime behavior is exercised with deterministic fixtures.

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verification or Wave 0 dependencies.
- [ ] Sampling continuity: no 3 consecutive tasks without automated verification.
- [ ] Wave 0 covers all missing test files and fixtures.
- [ ] No watch-mode flags.
- [ ] Targeted feedback latency remains below 30 seconds.
- [x] `nyquist_compliant: true` set in frontmatter.

**Approval:** pending
