# GSD Debug Knowledge Base

Resolved debug sessions. Used by `gsd-debugger` to surface known-pattern hypotheses at the start of new investigations.

---

## resume-reconciliation-unknown — Campaign-scoped reconciliation snapshots reported as cross-store UNKNOWN
- **Date:** 2026-07-20
- **Error patterns:** RECONCILIATION_INCOMPLETE:RESUME, cross-store UNKNOWN, resume sentinel, startup sentinel, reconciliation snapshot, missing primary run
- **Root cause:** `soak_reporting._valid_primary_reference` unconditionally treated `soak_snapshots.run_id` as a foreign key to `primary.runs`, although STARTUP and RESUME store reserved campaign-operation sentinels in that field.
- **Fix:** Added stage-aware snapshot reference validation for the exact STARTUP and RESUME sentinels while retaining strict primary-run validation for run-scoped snapshots.
- **Files changed:** `trading_bot/soak_reporting.py`, `tests/test_soak_reporting.py`
---

## soak-unknown-date-transient — Transient KIS calendar witness returned UNKNOWN_DATE
- **Date:** 2026-08-31
- **Error patterns:** SOAK_RUN_NOT_ADMITTED:UNKNOWN_DATE, UNKNOWN_DATE, KRX_SESSION_OPEN, calendar witness, transient
- **Root cause:** `KisOrderAdapter.fetch_trading_day()` returned after one semantically unavailable calendar payload because the existing retry boundary covered only transport/HTTP exceptions; `ObservedKRXCalendar` then cached the unavailable witness as current-day UNKNOWN.
- **Fix:** Added a bounded read-only retry loop around both KIS calendar requests and semantic normalization failures, accepting only exact requested-date `Y/N` evidence and returning `None` after exhaustion.
- **Files changed:** `trading_bot/kis_order.py`, `tests/test_kis_order.py`
---
