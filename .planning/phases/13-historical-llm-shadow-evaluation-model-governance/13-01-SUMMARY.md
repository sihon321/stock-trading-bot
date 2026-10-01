---
phase: "13-historical-llm-shadow-evaluation-model-governance"
plan: "01"
subsystem: "shadow-evaluation"
tags: ["offline-evidence", "llm", "budget", "governance"]
requires: [{"phase": "12", "provides": "canonical frozen replay"}]
provides: ["Strict shadow contracts and immutable provenance"]
affects: ["13", "14"]
tech-stack: {"added": [], "patterns": ["frozen evidence", "fail-closed capabilities"]}
key-files: {"created": ["trading_bot/shadow_models.py", "tests/test_shadow_models.py", "tests/fixtures/shadow/minimal_manifest.json"], "modified": []}
key-decisions: ["Dedicated shadow facts and no broker/configuration-write capability"]
requirements-completed: ["FUT-02", "GOV-01"]
coverage: [{"id": "T1", "description": "Task 1: Define bounded manifest, snapshot and variant contracts", "requirement": "FUT-02", "verification": [{"kind": "unit", "ref": "PYTHONUSERBASE=\"$PWD/.python-userbase\" python3 -m pytest -q tests/test_shadow_models.py", "status": "pass"}], "human_judgment": false}, {"id": "T2", "description": "Task 2: Define observations and validate evidence attribution", "requirement": "FUT-02", "verification": [{"kind": "unit", "ref": "PYTHONUSERBASE=\"$PWD/.python-userbase\" python3 -m pytest -q tests/test_shadow_models.py", "status": "pass"}], "human_judgment": false}]
duration: "recorded in Git commit times"
completed: "2026-10-01"
status: "complete"
---

# Phase 13 Plan 01 Summary

Strict shadow contracts and immutable provenance.

## Performance

- Completed: 2026-10-01T11:08:41.901434+00:00
- Tasks: 2
- Files: 3

## Accomplishments

- Strict shadow contracts and immutable provenance
- Automated evidence: 22 model/observation tests passed (0.07s). Task 1 checked 12 tests before task 2; task 2 and final plan checked 22.
- Inline execution under Codex skill-adapter spawn restriction; no paid LLM or KIS call.

## Task Commits

- `8213076` — enhancement(13-01): freeze bounded shadow manifests and provenance
- `46f7cc6` — enhancement(13-01): preserve distinct observations and unknown billing facts

## Files Created/Modified

- `trading_bot/shadow_models.py`
- `tests/test_shadow_models.py`
- `tests/fixtures/shadow/minimal_manifest.json`

## Decisions Made

Followed the locked Phase 13 decisions. Strict provider schema naming uses signal_schema_json to avoid Pydantic method shadowing.

## Deviations from Plan

None — accepted behavior implemented; naming details use agent discretion.

## Issues Encountered

None outstanding.

## User Setup Required

No setup for automated tests. Optional paid runtime later requires dedicated provider credentials and reviewed model/pricing profiles; synthetic fixtures do not authorize paid calls.

## Next Phase Readiness

Ready for dependent plans; overall phase verification remains pending until all seven plans complete.

## Self-Check: PASSED

All owned files exist; task commits exist; stated automated checks passed.
