---
phase: "13-historical-llm-shadow-evaluation-model-governance"
plan: "07"
subsystem: "shadow-evaluation"
tags: ["offline-evidence", "llm", "budget", "governance"]
requires: [{"phase": "12", "provides": "canonical frozen replay"}]
provides: ["Operator CLI, runbook and full offline verification"]
affects: ["13", "14"]
tech-stack: {"added": [], "patterns": ["frozen evidence", "fail-closed capabilities"]}
key-files: {"created": ["trading_bot/shadow_cli.py", "tests/test_shadow_cli.py", "docs/shadow-evaluation-runbook.md", "README.md"], "modified": ["trading_bot/cli.py", "trading_bot/report_cli.py"]}
key-decisions: ["Dedicated shadow facts and no broker/configuration-write capability"]
requirements-completed: ["FUT-02", "GOV-01"]
coverage: [{"id": "T1", "description": "Task 1: Expose offline preparation/report and explicit paid-run handlers", "requirement": "FUT-02", "verification": [{"kind": "unit", "ref": "PYTHONUSERBASE=\"$PWD/.python-userbase\" python3 -m pytest -q tests/test_shadow_cli.py", "status": "pass"}], "human_judgment": false}, {"id": "T2", "description": "Task 2: Document operator workflow and verify integration without paid calls", "requirement": "FUT-02", "verification": [{"kind": "unit", "ref": "PYTHONUSERBASE=\"$PWD/.python-userbase\" python3 -m pytest -q tests/test_shadow_cli.py", "status": "pass"}], "human_judgment": false}]
duration: "recorded in Git commit times"
completed: "2026-10-01"
status: "complete"
---

# Phase 13 Plan 07 Summary

Operator CLI, runbook and full offline verification.

## Performance

- Completed: 2026-10-01T12:04:17.488479+00:00
- Tasks: 2
- Files: 6

## Accomplishments

- Operator CLI, runbook and full offline verification
- Automated evidence: Task 1: 3 passed; Task 2: CLI 6 passed in 3.78s; final full suite 986 passed in 36.22s. 80 shadow cases plus 78 backtest cases are included. Installed bot prepare/report run outside repository with credentials absent; foreign store and live write tripwires, partial artifacts, explicit resume/retry and safe paths verified.
- Inline execution under Codex skill-adapter spawn restriction; no paid LLM or KIS call.

## Task Commits

- `bbde7f6` — enhancement(13-07): expose isolated shadow prepare run resume retry and report commands
- `23c394d` — fix(13-07): validate frozen source replay and bound provider evidence before dispatch
- `95b88d4` — fix(13-07): require reviewed API capabilities and reject incompatible forced tools
- `a460cf8` — enhancement(13-07): document operator workflow and verify installed offline commands

## Files Created/Modified

- `trading_bot/shadow_cli.py`
- `trading_bot/cli.py`
- `trading_bot/report_cli.py`
- `tests/test_shadow_cli.py`
- `docs/shadow-evaluation-runbook.md`
- `README.md`

## Decisions Made

Followed the locked Phase 13 decisions. Strict provider schema naming uses signal_schema_json to avoid Pydantic method shadowing.

## Deviations from Plan

Integration inspection added linked parent runs, full frozen bundle/news replay validation, missing-period/ticker strata, request/compression/output-space guards, retained unknown-model costs, native/billed facts and positive API capability review. Official Claude docs identify forced-tool-incompatible model families; reject before credentials rather than change contract. Existing global dotenv loading moved into live-command callback so shadow/report/backtest remain credential-free. Local setuptools build runtime and editable bot script installed under the existing project userbase; dependencies were not upgraded. Earlier integration test assumptions/fixture serialization and cwd provenance lookup were corrected; all final tests pass.

## Issues Encountered

None outstanding.

## User Setup Required

No setup for automated tests. Optional paid runtime later requires dedicated provider credentials and reviewed model/pricing profiles; synthetic fixtures do not authorize paid calls.

## Next Phase Readiness

Ready for dependent plans; overall phase verification remains pending until all seven plans complete.

## Self-Check: PASSED

All owned files exist; task commits exist; stated automated checks passed.
