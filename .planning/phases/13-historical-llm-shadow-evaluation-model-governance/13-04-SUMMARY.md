---
phase: "13-historical-llm-shadow-evaluation-model-governance"
plan: "04"
subsystem: "shadow-evaluation"
tags: ["offline-evidence", "llm", "budget", "governance"]
requires: [{"phase": "12", "provides": "canonical frozen replay"}]
provides: ["Single-shot isolated API providers with usage envelopes"]
affects: ["13", "14"]
tech-stack: {"added": [], "patterns": ["frozen evidence", "fail-closed capabilities"]}
key-files: {"created": ["trading_bot/shadow_providers.py", "tests/test_shadow_providers.py"], "modified": ["trading_bot/shadow_providers.py", "tests/test_shadow_providers.py"]}
key-decisions: ["Dedicated shadow facts and no broker/configuration-write capability"]
requirements-completed: ["FUT-02", "GOV-01"]
coverage: [{"id": "T1", "description": "Task 1: Implement API calls preserving failed output and cost facts", "requirement": "FUT-02", "verification": [{"kind": "unit", "ref": "PYTHONUSERBASE=\"$PWD/.python-userbase\" python3 -m pytest -q tests/test_shadow_providers.py", "status": "pass"}], "human_judgment": false}, {"id": "T2", "description": "Task 2: Enforce provider capability boundary and explicit unsupported CLI", "requirement": "FUT-02", "verification": [{"kind": "unit", "ref": "PYTHONUSERBASE=\"$PWD/.python-userbase\" python3 -m pytest -q tests/test_shadow_providers.py", "status": "pass"}], "human_judgment": false}]
duration: "recorded in Git commit times"
completed: "2026-10-01"
status: "complete"
---

# Phase 13 Plan 04 Summary

Single-shot isolated API providers with usage envelopes.

## Performance

- Completed: 2026-10-01T11:25:41.137226+00:00
- Tasks: 2
- Files: 2

## Accomplishments

- Single-shot isolated API providers with usage envelopes
- Automated evidence: Task 1: 7 passed; Task 2: 11 passed. Official SDK fake transports prove one call, zero retries, explicit limits, distinct refusal/malformed/timeout/error, unknown usage, oversized responses, origin/redirect denial and no Codex process call. Initial fake pre-buffered response handling failed 4 tests; bounded transport corrected and all rechecks pass.
- Inline execution under Codex skill-adapter spawn restriction; no paid LLM or KIS call.

## Task Commits

- `d1c4bfc` — enhancement(13-04): preserve single-shot API observations and usage facts
- `2f16a80` — enhancement(13-04): verify isolated credentials and forbidden provider capabilities

## Files Created/Modified

- `trading_bot/shadow_providers.py`
- `tests/test_shadow_providers.py`

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
