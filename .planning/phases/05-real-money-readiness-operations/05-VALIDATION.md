---
phase: 05
slug: real-money-readiness-operations
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-07-02
---

# Phase 05 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Derived from `05-RESEARCH.md` § Validation Architecture. Adapters are tested fully offline via injected fake HTTP clients + deterministic clocks (mirror `test_kis_quote.py`, `test_kis_auth.py`, `conftest.py`). **No live KIS calls in tests.**

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.4.2 |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (testpaths=`tests`, pythonpath=`.`) |
| **Quick run command** | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_kis_broker.py -x` |
| **Full suite command** | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` |
| **Estimated runtime** | ~10 seconds (offline, no network) |

---

## Sampling Rate

- **After every task commit:** Run the relevant new `tests/test_*.py -x`
- **After every plan wave:** Run `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** ~10 seconds

---

## Per-Task Verification Map

| Requirement | Behavior | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists |
|-------------|----------|------------|-----------------|-----------|-------------------|-------------|
| EXEC-04 | Order POST never retried; blind-retry impossible | order-double-submit | Failed POST → no automatic re-POST | unit | `pytest tests/test_kis_broker.py::test_order_post_not_retried -x` | ❌ W0 |
| EXEC-04 | Query-before-POST returns existing ODNO, no second POST | order-double-submit | Reconcile finds existing order → skip | unit | `pytest tests/test_kis_broker.py::test_reconcile_skips_duplicate -x` | ❌ W0 |
| EXEC-04 | Partial fill read back; tracked position = filled qty (D-07) | position-drift | Position mirrors broker truth | unit | `pytest tests/test_kis_broker.py::test_partial_fill_reconciled -x` | ❌ W0 |
| EXEC-04 | KISBroker structurally satisfies `Broker` (like MockBroker) | — | N/A | unit | `pytest tests/test_kis_broker.py::test_kis_broker_is_broker -x` | ❌ W0 |
| EXEC-04 / D-08 | Off-tick price snapped to valid band; market-closed → HOLD | stale-order | Closed/stale → fail-safe HOLD | unit | `pytest tests/test_kis_broker.py::test_tick_snap_and_market_guard -x` | ❌ W0 |
| EXEC-04 | order-cash body/headers/TR_ID selection + fill parsing | wrong-domain-order | Mock/real TR_ID from atomic `active_kis` | unit | `pytest tests/test_kis_order.py -x` | ❌ W0 |
| CFG-04 / D-04 | Real execute without `--live-confirm` refuses | unguarded-real-order | Real+execute w/o confirm → refuse | unit | `pytest tests/test_cli.py::test_real_execute_requires_live_confirm -x` | ❌ W0 |
| OPS-01 / D-02,D-13 | Per-ticker failure isolated; run continues | run-abort | One ticker error captured, not fatal | unit | `pytest tests/test_cli.py::test_ticker_error_isolation -x` | ❌ W0 |
| OPS-01 / D-03 | Bare `bot run` places nothing (dry-run default) | accidental-order | No `--execute` → places nothing | unit | `pytest tests/test_cli.py::test_dry_run_default_no_orders -x` | ❌ W0 |
| OPS-02 / D-09 | Two-table write; runs↔decisions link queryable | — | N/A | unit | `pytest tests/test_sqlite_audit.py::test_two_table_write -x` | ❌ W0 |
| OPS-02 / D-10 | Correlation ID stored, matches structlog line | audit-gap | Every decision traceable to raw line | unit | `pytest tests/test_sqlite_audit.py::test_correlation_id -x` | ❌ W0 |
| OPS-03 / D-13 | One consolidated summary per run | — | N/A | unit | `pytest tests/test_notifier.py::test_consolidated_summary -x` | ❌ W0 |
| OPS-03 / D-14 | Notify failure never raises/blocks cycle | notify-blocks-trade | Notify error → log + continue | unit | `pytest tests/test_notifier.py::test_fail_soft -x` | ❌ W0 |
| ports | `Notifier` added but `ports.py` stays adapter-free | port-leak | No adapter imports in ports | unit | `pytest tests/test_ports.py -x` | ✅ (extend) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky · W0 = created in Wave 0*

---

## Wave 0 Requirements

- [ ] `tests/test_kis_broker.py` — EXEC-04 (no-retry POST, reconcile, partial fill, tick snap, market guard, `Broker` conformance)
- [ ] `tests/test_kis_order.py` — order-cash body/headers/TR_ID selection + fill parsing with a fake HTTP client (mirror `test_kis_quote.py`)
- [ ] `tests/test_cli.py` — CFG-04/OPS-01 gate + error isolation + dry-run default
- [ ] `tests/test_sqlite_audit.py` — OPS-02 two-table write + correlation ID (`:memory:` or `tmp_path` DB)
- [ ] `tests/test_notifier.py` — OPS-03 consolidated summary + fail-soft (fake `httpx` client)
- [ ] `tests/test_ports.py` — extend to assert `Notifier` is a runtime-checkable, adapter-free Protocol
- [ ] Framework/deps: install `typer==0.26.8` into `.python-userbase`, reinstall `-e .`

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Real order placed against KIS mock (모의투자) account end-to-end | EXEC-04 / CFG-04 | Requires live KIS mock credentials + open-market session; cannot run offline in CI | With mock creds set, market open: `bot run --ticker <code> --execute --live-confirm` in `TRADING_MODE=real` against 모의투자; confirm order appears in KIS balance/order query and reconciliation skips a resubmit on re-run |
| Discord webhook actually delivers a run summary | OPS-03 | Requires a real Discord webhook URL + external network | Set the webhook URL; run a dry-run cycle; confirm the consolidated summary embed arrives in the channel |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < ~10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
