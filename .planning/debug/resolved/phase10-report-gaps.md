---
status: resolved
trigger: "코드 수정도 해줘"
created: 2026-10-01
---

# Phase 10 report integration gaps

## Symptoms

Current calibration/readiness readers reject the Phase 11 shared audit schema; readiness discards resolved historical ambiguity counts.

## Current Focus

Hypothesis: Readers must validate their own schema tables independently; readiness must derive historical warnings from valid same-subject terminal release evidence.
Next action: Add regression coverage, implement read-only fixes, run focused/full suites and current-store smoke checks, then update Phase 10 verification.

## Resolution

- Fix commit: `4e70abf`.
- Validate only primary-owned tables while retaining exact owned columns/version and exact soak/controller schemas.
- Derive historical ambiguity from valid same-subject terminal freeze releases; invalid release evidence retains blocking freezes and cross-store UNKNOWN.
- Real readiness CLI with strict replay loader, shared SQLite schema and active/resolved history passes; output is deterministic and inputs remain unchanged.
- Focused suite: 116 passed. Full suite: 828 passed. Runtime campaign remains 16/20 and runtime DB bytes are unchanged.
- Phase 10 re-verification: passed, 24/24. No live request or mutation was performed.

## Evidence

- Prior final verification reproduces `unsupported primary audit schema tables` in both production readers.
- `readiness_command` hardcodes `resolved_historical_ambiguity=0`.
- Existing primary schema/version/column checks and active ambiguity gates must remain fail closed.
