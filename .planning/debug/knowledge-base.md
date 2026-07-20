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
