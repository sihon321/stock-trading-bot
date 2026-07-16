---
phase: 09
slug: kis-mock-soak-fault-drills
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-16
---

# Phase 09 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.4.2 |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_soak_config.py tests/test_soak_campaign.py tests/test_soak_reconcile.py -x` |
| **Full suite command** | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` |
| **Estimated runtime** | ~20 seconds before Phase 9 growth |

---

## Sampling Rate

- **After every task commit:** Run the focused new soak test file plus affected existing KIS, audit, and CLI tests.
- **After every plan wave:** Run `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q`.
- **Before `$gsd-verify-work`:** The full suite must be green, followed by authenticated KIS mock UAT.
- **Max feedback latency:** 30 seconds for automated task-level checks.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 09-TBD-01 | TBD | TBD | SOAK-01 | T-09-01 | Real-target configuration is unrepresentable or rejected before mutation. | unit + CLI integration | `python3 -m pytest -q tests/test_soak_config.py tests/test_soak_cli.py -x` | ❌ W0 | ⬜ pending |
| 09-TBD-02 | TBD | TBD | SOAK-02 | Campaign targets and failure budgets are immutable; invariant breaches permanently fail. | unit + SQLite integration | `python3 -m pytest -q tests/test_soak_campaign.py tests/test_soak_store.py -x` | ❌ W0 | ⬜ pending |
| 09-TBD-03 | TBD | TBD | SOAK-03 | Ambiguous submissions are not retried and ticker freezes survive restart until broker truth is determinate. | unit + integration + subprocess | `python3 -m pytest -q tests/test_soak_reconcile.py -x` | ❌ W0 | ⬜ pending |
| 09-TBD-04 | TBD | TBD | SOAK-04 | Exactly one named fault is injected and containment, provenance, recovery, and prohibited-action checks are durable. | unit + CLI + subprocess | `python3 -m pytest -q tests/test_soak_drills.py tests/test_soak_cli.py -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_soak_config.py` — mock-only construction and identity-receipt gate for SOAK-01.
- [ ] `tests/test_soak_store.py` — migrations, immutability, uniqueness, and permanent campaign failure for SOAK-02.
- [ ] `tests/test_soak_reconcile.py` — multi-page broker fixtures, ambiguity cardinality, account comparison, and restart freeze for SOAK-03.
- [ ] `tests/test_soak_campaign.py` — eligible-day, budget, and clean-streak state machine for SOAK-02.
- [ ] `tests/test_soak_drills.py` — fault registry and controller-journal durability/recovery for SOAK-04.
- [ ] `tests/test_soak_cli.py` — command isolation and end-to-end injected collaborators for SOAK-01 and SOAK-04.
- [ ] Sanitized authenticated KIS mock fixtures for the accepted TR-ID profile and paginated response shapes; no secrets, raw payloads, or unrelated account data.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Current TR-ID profile and normalized fields work against the operator's authenticated KIS mock account. | SOAK-01, SOAK-03 | The external mock service and credentials are unavailable to deterministic tests. | Run the compatibility command with mock-only credentials, retain the sanitized identity receipt and normalized fixtures, and verify no real domain/account/TR-ID can be resolved. |
| A designated eligible-KRX-day run reconciles orders, fills, open orders, holdings, and cash before day credit. | SOAK-02, SOAK-03 | Broker timing and account truth require the live KIS mock environment. | Execute one designated mock run, inspect the daily report and reconciliation snapshot, and confirm credit is granted only after complete evidence. |
| The full 20-eligible-day campaign meets the immutable target and availability budget without safety breaches. | SOAK-02 | Calendar duration cannot be compressed into automated execution. | Run the operator campaign over 20 confirmed eligible KRX dates and verify the final campaign report denominators, budget, clean streak, and permanent-failure latch. |

---

## Validation Sign-Off

- [ ] Planner replaces `09-TBD-*` entries with final task IDs, plans, and waves.
- [ ] All tasks have `<automated>` verification or explicit Wave 0 dependencies.
- [ ] Sampling continuity: no three consecutive implementation tasks without automated verification.
- [ ] Wave 0 covers every missing test and sanitized fixture reference.
- [ ] No watch-mode flags.
- [ ] Automated feedback latency remains below 30 seconds.
- [ ] Authenticated KIS mock checkpoints remain manual and cannot be substituted with synthetic evidence.
- [ ] `nyquist_compliant: true` and `wave_0_complete: true` are set only after the final task map and fixtures exist.

**Approval:** pending
