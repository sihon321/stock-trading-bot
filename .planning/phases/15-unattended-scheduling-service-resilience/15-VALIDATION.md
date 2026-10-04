---
phase: 15
slug: unattended-scheduling-service-resilience
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-10-04
---

# Phase 15 — Validation Strategy

> Execution feedback contract. Planning coverage does not mean implementation or operator acceptance has passed. The planner must replace the provisional areas below with actual plan/task/wave IDs.

## Test Infrastructure

| Property | Value |
|---|---|
| Framework | pytest 8.4.2; existing project infrastructure |
| Config | pyproject.toml |
| Existing quick regression | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_market_cycle.py tests/test_mutation_lease.py tests/test_portfolio_store.py tests/test_phase11_cli.py tests/test_intraday.py tests/test_web_capabilities.py tests/test_alert_observer.py` |
| Full suite | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` |
| Observed quick runtime | Research baseline: 103 passed in 21.90s |
| Target focused feedback | Under 30s; verify during implementation, do not assert an unmeasured future runtime |

## Sampling Rate

- After every implementation task: its focused offline tests and nearest existing regression module.
- After every wave: applicable cross-module regression; the complete suite is mandatory before phase verification. Broaden only when changes or unresolved failures justify it.
- No watch-mode test commands. No broker, paid LLM, Discord delivery, OS installation or production-store mutations from automated checks.
- Fake aware UTC/KST wall clocks, monotonic time, authoritative session fixtures, temporary SQLite stores, fake providers/brokers, deterministic crash barriers and spawn-safe process fixtures.

## Provisional Verification Map

The planner must map these areas to concrete task IDs, waves, commands and dependencies, and ensure every new test file is created before its verification command.

| Area | Requirement | Threat Ref | Secure Behavior | Test Type | Proposed test file | File Exists | Status |
|---|---|---|---|---|---|---|---|
| Admission | FUT-04 | T-15-ADMISSION | Missing/stale/synthetic approval and real target rejected; exact evidence and 000660 freeze preserved | unit/integration | tests/test_service_activation.py | ❌ W0 | pending |
| Schedule | AUTO-01 | T-15-REPLAY | 08:50 read-only, 09:00 risk, 09:10 daily, strict before-09:20 dispatch; holiday/UNKNOWN/delayed/wake behavior | unit | tests/test_service_schedule.py | ❌ W0 | pending |
| Dispatch/recovery | AUTO-01 | T-15-DUPLICATE | Crash barriers around input/dispatch/response/POST; no repeated uncertain provider or order | integration | tests/test_service_recovery.py | ❌ W0 | pending |
| Authority | AUTO-01 | T-15-OVERLAP | Two-process leader/account exclusion; risk cannot starve daily; LLM does not hold mutation lease | process/integration | tests/test_service_authority.py | ❌ W0 | pending |
| Controls | AUTO-02 | T-15-CONTROL | Pending/applicable restrictive requests affect final POST; stale resume fails; persistent pause/kill | unit/integration | tests/test_service_controls.py | ❌ W0 | pending |
| Health | AUTO-02 | T-15-BLINDNESS | Missed/stalled/stale/failed/UNKNOWN distinct from stopped/not-expected; independent observer | unit/integration | tests/test_service_health.py | ❌ W0 | pending |
| Supervision | AUTO-02 | T-15-RESTART | Login LaunchAgent, protected paths, 3 admitted restarts/600s, durable manual-attention latch | unit/process | tests/test_service_launchd.py | ❌ W0 | pending |
| Web control | AUTO-02 | T-15-FORGERY | Auth/authorization/CSRF/actor audit, fixed actions/scope/revisions; no trading collaborators | HTTP/capability | tests/test_web_control_routes.py | ❌ W0 | pending |
| Offline dry-run | All | T-15-CAPABILITY | Zero external calls/installation and unchanged production files while temp journal exercises recovery | integration | tests/test_service_dry_run.py | ❌ W0 | pending |

## Wave 0 Requirements

- [ ] New test files above, or documented equivalent names mapped by the planner.
- [ ] Temporary service/control/admission journals and immutable source bundles.
- [ ] Fake clocks/session evidence, crash barriers, fake provider/broker and process fixtures; extend tests/conftest.py only if shared ownership warrants it.
- [ ] Conservative legacy dispatch migration tests in tests/test_portfolio_store.py and safe signal reuse tests in tests/test_phase11_cli.py.
- Existing framework is installed; no dependency installation task needed for tests.

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Instructions |
|---|---|---|---|
| Phase 9 elapsed-day acceptance | FUT-04 | Tests cannot supply real operator approval or broker-observed eligible-day proof | Complete and approve 09-08 using exact campaign/source identities. Preserve unresolved freezes. Missing acceptance blocks activation, not planning/offline execution. |
| Mac login/logout, sleep/wake and service lifecycle | AUTO-02 | Real user GUI domain and machine lifecycle | Use explicitly installed disabled/offline configuration; check login start, logout stop, missed window on wake, kill persistence and uninstall preservation. Installation is a separate operator action. |
| Korean web control usability | AUTO-02 | Owner review of PC/phone affordances | Inspect pause/kill/resume effect, requested/applied distinction and active blocks; offline temp evidence, authenticated sessions. |
| External private phone access | AUTO-02 | Existing future deployment/device acceptance | Actual Tailscale/HTTPS/device configuration remains a separate follow-up. Do not assert external reachability from local browser tests. |

## Validation Sign-Off

- [ ] Every task has automated verify or a named prior Wave 0 dependency.
- [ ] No three consecutive implementation tasks lack automated feedback.
- [ ] All missing test references have producing tasks before use.
- [ ] No watch-mode flags or live collaborators.
- [ ] Measured focused feedback meets the target.
- [ ] nyquist_compliant: true only after the complete task map is validated.
- [ ] wave_0_complete: true only after required fixtures/tests actually exist.

**Approval:** pending; planning and actual execution sign-offs remain distinct.
