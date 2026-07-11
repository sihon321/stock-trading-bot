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
| 06-01-01 | 06-01 | 1 | EVID-01, EVID-02, EVID-03 | T-06-AUDIT, T-06-OMIT | Green compatibility contracts plus reusable migration/evidence fixtures | migration/integration | `PYTHONUSERBASE="$PWD/.python-userbase" .venv/bin/python -m pytest -q tests/test_sqlite_audit.py` | ✅ extend | ⬜ pending |
| 06-01-02 | 06-01 | 1 | EVID-01, EVID-02, EVID-03 | T-06-AUDIT, T-06-INFO | Additive schema v2 preserves v1 rows and enforces normalized evidence | migration/integration | `PYTHONUSERBASE="$PWD/.python-userbase" .venv/bin/python -m pytest -q tests/test_sqlite_audit.py` | ✅ extend | ⬜ pending |
| 06-01-03 | 06-01 | 1 | EVID-04 | T-06-TIME | Implement pure confirmed-day/session/cutoff/quote-age policy with deterministic fakes | boundary/unit | `PYTHONUSERBASE="$PWD/.python-userbase" .venv/bin/python -m pytest -q tests/test_market_cycle.py tests/test_sqlite_audit.py` | ❌ create / ✅ extend | ⬜ pending |
| 06-02-01 | 06-02 | 2 | EVID-01 | T-06-AUDIT | Runs terminalize once, recover abandoned work, snapshot provenance, and link explicit retries | integration | `PYTHONUSERBASE="$PWD/.python-userbase" .venv/bin/python -m pytest -q tests/test_sqlite_audit.py tests/test_cli.py` | ✅ extend | ⬜ pending |
| 06-02-02 | 06-02 | 2 | EVID-02 | T-06-OMIT | Every attempted ticker has exactly one normalized, sanitized terminal outcome | parameterized integration | `PYTHONUSERBASE="$PWD/.python-userbase" .venv/bin/python -m pytest -q tests/test_cli.py tests/test_sqlite_audit.py` | ✅ extend | ⬜ pending |
| 06-03-01 | 06-03 | 3 | EVID-03 | T-06-ORDER | Intent, submission, duplicate, and reconciliation events remain append-only | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" .venv/bin/python -m pytest -q tests/test_kis_broker.py tests/test_sqlite_audit.py` | ✅ extend | ⬜ pending |
| 06-03-02 | 06-03 | 3 | EVID-02, EVID-03 | T-06-RETRY | Ambiguous submissions never blind-retry and later inquiry preserves dual-run attribution | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" .venv/bin/python -m pytest -q tests/test_kis_broker.py tests/test_cli.py tests/test_sqlite_audit.py` | ✅ extend | ⬜ pending |
| 06-04-01 | 06-04 | 4 | EVID-01, EVID-04 | T-06-TIME, T-06-LOOK | Authoritative KRX day/session and preceding completed-bar cutoff fail closed | boundary/integration | `PYTHONUSERBASE="$PWD/.python-userbase" .venv/bin/python -m pytest -q tests/test_market_cycle.py tests/test_cli.py tests/test_data_source.py` | ✅ extend | ⬜ pending |
| 06-04-02 | 06-04 | 4 | EVID-03, EVID-04 | T-06-STALE | Immediate pre-submit quote refresh enforces the inclusive 10-second maximum | boundary/integration | `PYTHONUSERBASE="$PWD/.python-userbase" .venv/bin/python -m pytest -q tests/test_market_cycle.py tests/test_kis_quote.py tests/test_kis_broker.py tests/test_cli.py` | ✅ extend | ⬜ pending |
| 06-04-03 | 06-04 | 4 | EVID-01, EVID-02, EVID-03, EVID-04 | T-06-AUDIT, T-06-RETRY, T-06-TIME | Full regression gate covers all evidence chains and safety boundaries | regression | `PYTHONUSERBASE="$PWD/.python-userbase" .venv/bin/python -m pytest -q` | ✅ extend | ⬜ pending |
| 06-05-01 | 06-05 | 5 | EVID-02 | T-06-OMIT-GAP | Selected, rejected, and failed screen attempts persist exactly once without duplicate selected rows | integration | `PYTHONUSERBASE="$PWD/.python-userbase" .venv/bin/python -m pytest -q tests/test_cli.py tests/test_screener.py tests/test_sqlite_audit.py` | ✅ extend | ⬜ pending |
| 06-05-02 | 06-05 | 5 | EVID-04 | T-06-STALE-GAP, T-06-INFO-GAP, T-06-RETRY-GAP | Successful and blocked real/mock pre-submit freshness decisions are durable and gate mutation | boundary/integration | `PYTHONUSERBASE="$PWD/.python-userbase" .venv/bin/python -m pytest -q tests/test_market_cycle.py tests/test_kis_quote.py tests/test_kis_broker.py tests/test_mock_broker.py tests/test_cli.py tests/test_sqlite_audit.py` | ✅ extend | ⬜ pending |
| 06-05-03 | 06-05 | 5 | EVID-02, EVID-04 | T-06-OMIT-GAP, T-06-STALE-GAP | Both verification blockers are directly disconfirmed and the full suite stays green | regression | `PYTHONUSERBASE="$PWD/.python-userbase" .venv/bin/python -m pytest -q` | ✅ extend | ⬜ pending |

---

## Wave 0 Requirements

- [ ] **06-01-03 creates `trading_bot/market_cycle.py` and `tests/test_market_cycle.py` together** — pure KRX trading-day/session boundaries, half-open executable window, completed-bar cutoff, quote-age policy, and fixtures satisfy the Nyquist pre-implementation requirements while executing in Plan 06-01 Wave 1, without imports from later plans.
- [ ] **06-01-01 extends `tests/test_sqlite_audit.py`** — v1-to-current schema migration, uniqueness constraints, and append-only order-event fixtures.
- [ ] **06-01-01/03 extend `tests/conftest.py`** — injected clock/calendar, quote observation, ambiguous submission, and event-sink fakes.

---

## Manual-Only Verifications

All Phase 6 behaviors have automated verification. Exact KRX boundaries must be source-grounded during implementation, but their runtime behavior is exercised with deterministic fixtures.

---

## Multi-Source Coverage Audit

| Source | ID | Feature / constraint | Plan | Status | Notes |
|--------|----|----------------------|------|--------|-------|
| GOAL | — | Every cycle/ticker is complete, attributable, and evaluated against explicit KRX timing/freshness boundaries | 06-01–06-04 | COVERED | Schema → lifecycle → broker → cycle gate |
| REQ | EVID-01 | Terminal lifecycle, KST trading date, kind, target, policy, provenance | 06-01, 06-02, 06-04 | COVERED | Full ID appears in every plan frontmatter |
| REQ | EVID-02 | Exactly one terminal result per attempted ticker | 06-01, 06-02, 06-03 | COVERED | Includes all normalized failure/ambiguity paths |
| REQ | EVID-03 | Trace intent through submission/reconciliation or exact no-order reason | 06-01, 06-03, 06-04 | COVERED | Append-only dual-run reconciliation |
| REQ | EVID-04 | KRX session, cutoff, quote freshness, permitted window | 06-01, 06-04 | COVERED | Authoritative provider and deterministic fixtures |
| RESEARCH | R-01 | Additive versioned SQLite migration preserving shipped decisions | 06-01 | COVERED | `PRAGMA user_version`, transactional/idempotent |
| RESEARCH | R-02 | Typed stable vocabularies and DB constraints/indexes | 06-01, 06-02 | COVERED | Run-kind-specific terminal codes |
| RESEARCH | R-03 | Synchronous injected collaborators; no new packages | 06-01, 06-03, 06-04 | COVERED | Existing project pattern retained |
| RESEARCH | R-04 | Explicit retry CLI input compatible with Typer | 06-02 | COVERED | Optional validated `--parent-run-id` |
| RESEARCH | R-05 | Append-only intent/submission/reconciliation evidence and no blind POST retry | 06-03 | COVERED | Typed ambiguity plus later inquiry |
| RESEARCH | R-06 | Official KRX continuous interval 09:00–15:20 and authoritative special-closure seam | 06-01, 06-04 | COVERED | Half-open predicate; provider unknown fails closed |
| RESEARCH | R-07 | Previous completed KRX trading-day bar during open market | 06-04 | COVERED | Requested/cutoff/actual dates persisted |
| RESEARCH | R-08 | Timestamped pre-submit quote refresh with inclusive 10-second maximum | 06-01, 06-04 | COVERED | Invalid timestamp/future skew blocks |
| RESEARCH | R-09 | Secret/redaction boundary; normalized facts only | 06-01–06-04 | COVERED | Raw provider/KIS responses excluded |
| CONTEXT | D-01 | Screen and run create runs; status stays read-only | 06-02 | COVERED | Invocation envelope and tests |
| CONTEXT | D-02 | Four terminal run states; RUNNING eventually terminal | 06-01, 06-02 | COVERED | Single terminal transition |
| CONTEXT | D-03 | Next mutable invocation recovers abandoned RUNNING | 06-02 | COVERED | Recovery time and normalized reason |
| CONTEXT | D-04 | Fresh UUID each invocation; optional parent link | 06-02 | COVERED | No overwrite/reuse |
| CONTEXT | D-05 | Stable outcome code separate from reason/detail | 06-01, 06-02 | COVERED | Typed vocabulary |
| CONTEXT | D-06 | Run-kind-specific outcome vocabularies | 06-02 | COVERED | Screen vs evaluation codes |
| CONTEXT | D-07 | Exactly one result for every attempted ticker | 06-01, 06-02 | COVERED | DB uniqueness + exception terminalizer |
| CONTEXT | D-08 | Stable reasons and sanitized diagnostic detail | 06-01, 06-02 | COVERED | Central sanitizer |
| CONTEXT | D-09 | Append-only order events plus final summary | 06-01, 06-03 | COVERED | Compatibility summary retained |
| CONTEXT | D-10 | Separate intent and submission IDs | 06-01, 06-03 | COVERED | UUIDs per semantic level |
| CONTEXT | D-11 | Ambiguous terminal result, no retry, later dual-run reconciliation | 06-01, 06-03 | COVERED | Origin/observer IDs |
| CONTEXT | D-12 | Normalized broker facts and duplicate linkage only | 06-01, 06-03 | COVERED | No raw API payload |
| CONTEXT | D-13 | Conservative continuous session only; record other states | 06-01, 06-04 | COVERED | 09:00 inclusive, 15:20 exclusive |
| CONTEXT | D-14 | Previous completed day bar and three date facts | 06-01, 06-04 | COVERED | Data-source cutoff wiring |
| CONTEXT | D-15 | Immediate quote refresh; max age 10 seconds | 06-01, 06-04 | COVERED | Initial and pre-submit observations |
| CONTEXT | D-16 | Unknown day/session fails closed with policy evidence | 06-01, 06-04 | COVERED | Stable timing-policy version |
| VERIFICATION | EVID-02-screen-rejections | Rejected/failed screen events persist exactly once without duplicating selected tickers | 06-05 | COVERED | SQLite-backed gap test |
| VERIFICATION | EVID-04-successful-quote-evidence | Successful freshness facts are durable and executable mock orders share the immediate refresh gate | 06-05 | COVERED | Real/mock pass and block tests |

Excluded without gaps: replay (Phase 7), reporting/runbook (Phase 8), KIS mock soak/fault drills (Phase 9), and calibration/promotion (Phase 10).

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verification or dependencies supplied by Plan 06-01 Wave 1.
- [x] Sampling continuity: no 3 consecutive tasks without automated verification.
- [x] Plan 06-01 Wave 1 is independently green: every new test imports production symbols implemented in the same task, with no intentional failure or broad skip.
- [x] No watch-mode flags.
- [x] Targeted feedback latency remains below 30 seconds.
- [x] `nyquist_compliant: true` set in frontmatter.

**Approval:** plan-aligned; execution pending
