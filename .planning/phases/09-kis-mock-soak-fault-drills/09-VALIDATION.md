---
phase: 09
slug: kis-mock-soak-fault-drills
status: ready
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-16
updated: 2026-07-16
---

# Phase 09 — Validation Strategy

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.4.2 |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_soak_config.py tests/test_soak_store.py tests/test_soak_reconcile.py -x` |
| **Full suite command** | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` |
| **Estimated runtime** | focused checks <60 seconds; full suite after every wave |

## Sampling Rate

- After every task commit: focused command from the task row.
- After every wave: full deterministic suite.
- Before `$gsd-verify-work`: full suite, authenticated profile/proof-order checkpoints, one designated day/all drills, then elapsed 20-day checkpoint.
- No three consecutive implementation tasks lack automated verification; no watch-mode command is used.

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Automated / Manual Verification | Wave-0 Artifact |
|---------|------|------|-------------|------------|-----------------|-------------------------------|-----------------|
| 09-01-01 | 09-01 | 1 | SOAK-01, SOAK-03 | T-09-01,02 | Mock capability and all DB paths are structurally safe and secret-free. | `pytest -q tests/test_soak_config.py -x` | `tests/test_soak_config.py` |
| 09-01-02 | 09-01 | 1 | SOAK-03 | T-09-03,04 | Profile probing paginates completely while order POST stays single-shot. | `pytest -q tests/test_soak_reconcile.py tests/test_kis_order.py -x` | `tests/test_soak_reconcile.py` |
| 09-01-03 | 09-01 | 1 | SOAK-01 | T-09-01,02 | Probe-only CLI cannot construct general runtime or mutate stores. | `pytest -q tests/test_soak_cli.py tests/test_cli.py -x` | `tests/test_soak_cli.py` |
| 09-02-01 | 09-02 | 2 | SOAK-01, SOAK-03 | T-09-05,06,07 | Accepted authenticated profile is complete, sanitized, and POST-free. | Focused 09-02 command + blocking manual approval | `accepted-profile.json` |
| 09-03-01 | 09-03 | 3 | SOAK-02, SOAK-03 | T-09-08,10,11 | Soak schema migrates atomically and stores immutable policy/cross-IDs. | `pytest -q tests/test_soak_store.py -k 'migration or immutable or append or reopen or unique'` | `tests/test_soak_store.py` |
| 09-03-02 | 09-03 | 3 | SOAK-02, SOAK-03 | T-09-08,09 | Accounting and freezes remain irreversible across restart. | `pytest -q tests/test_soak_store.py -k 'campaign or budget or failure or freeze or restart'` | same |
| 09-04-01 | 09-04 | 4 | SOAK-03 | T-09-13,15,16 | Complete touched-state snapshots reconcile every required dimension. | `pytest -q tests/test_soak_reconcile.py -k 'snapshot or pagination or comparison or unrelated'` | same |
| 09-04-02 | 09-04 | 4 | SOAK-03 | T-09-12,14 | Immutable-policy ambiguity/restart reconciliation never POSTs. | `pytest -q tests/test_soak_reconcile.py tests/test_kis_broker.py -k 'ambiguous or partial or restart or post'` | same |
| 09-09-01 | 09-09 | 5 | SOAK-01, SOAK-03 | T-09-34–37 | One authenticated proof POST is durably reconciled or truthfully frozen. | Focused 09-09 command + blocking manual approval | `proof-order.json` |
| 09-05-01 | 09-05 | 6 | SOAK-01–03 | T-09-18,20 | Day, budget, safety, and freeze dimensions remain independent. | `pytest -q tests/test_soak_campaign.py tests/test_soak_store.py -x` | `tests/test_soak_campaign.py` |
| 09-05-02 | 09-05 | 6 | SOAK-01–03 | T-09-17,19 | Triple-store commands execute reconciliation in exact order. | `pytest -q tests/test_soak_cli.py tests/test_soak_campaign.py tests/test_cli.py -x` | `tests/test_soak_cli.py` |
| 09-06-01 | 09-06 | 7 | SOAK-04 | T-09-22,25 | Controller commits/read-backs before injection and survives failures. | `pytest -q tests/test_soak_drills.py -k 'controller or journal or wal or restart or alias'` | `tests/test_soak_drills.py` |
| 09-06-02 | 09-06 | 7 | SOAK-04 | T-09-21,23,24 | FaultName registry injects one boundary with correct POST count. | `pytest -q tests/test_soak_drills.py tests/test_soak_cli.py -x` | same |
| 09-07-01 | 09-07 | 8 | SOAK-02–04 | T-09-26–28 | Reporting opens all stores read-only and validates primary references. | `pytest -q tests/test_soak_reporting.py tests/test_reporting.py -x` | `tests/test_soak_reporting.py` |
| 09-07-02 | 09-07 | 8 | SOAK-02–04 | T-09-29 | Status/runbook match registry, gates, recovery, and prohibitions. | `pytest -q tests/test_soak_cli.py tests/test_operator_runbook.py tests/test_soak_reporting.py -x` | `tests/test_operator_runbook.py` |
| 09-08-01 | 09-08 | 9 | SOAK-01–04 | T-09-30,32 | One real day and all drills have complete three-store evidence. | Full suite + blocking manual UAT | runtime three-store evidence |
| 09-08-02 | 09-08 | 9 | SOAK-01–04 | T-09-31,33 | Twenty eligible days finish within budget with zero breach. | Full suite + elapsed blocking manual UAT | runtime three-store evidence |

All commands above use `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m` before `pytest` when executed.

## Wave 0 Requirements

- [ ] `tests/test_soak_config.py`
- [ ] `tests/test_soak_store.py`
- [ ] `tests/test_soak_reconcile.py`
- [ ] `tests/test_soak_campaign.py`
- [ ] `tests/test_soak_drills.py`
- [ ] `tests/test_soak_cli.py`
- [ ] `tests/test_soak_reporting.py`
- [ ] `tests/test_operator_runbook.py`
- [ ] `tests/fixtures/kis_mock/accepted-profile.json` via 09-02 blocking authenticated read-only checkpoint
- [ ] `tests/fixtures/kis_mock/proof-order.json` via 09-09 blocking authenticated proof checkpoint

`wave_0_complete` remains false until these artifacts exist; `nyquist_compliant` is true because every final task has a bounded automated check and every irreducibly external behavior has an explicit blocking checkpoint.

## Manual-Only Verifications

| Plan/Task | Behavior | Blocking evidence |
|-----------|----------|-------------------|
| 09-02-01 | Accepted profile and fields | Sanitized complete POST-free authenticated fixture |
| 09-09-01 | One proof order | Exactly one POST plus durable primary/soak comparison or persistent ambiguity freeze |
| 09-08-01 | One designated day and all controlled drills | Complete KIS + primary/soak/controller report |
| 09-08-02 | Twenty eligible days | Target/budget/permanent-safety final report with no unknown references |

## Validation Sign-Off

- [x] Every final task ID, plan, wave, requirement, threat, and automated/manual checkpoint is mapped.
- [x] Reporting and runbook tests are included.
- [x] All Wave-0 artifacts are listed.
- [x] Sampling continuity and phase-gate commands are explicit.
- [x] Synthetic evidence cannot replace authenticated or elapsed-day evidence.

**Approval:** ready for execution; Wave-0/runtime/manual rows remain pending
