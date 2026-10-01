---
phase: 14
slug: operator-dashboard-alerting
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-10-01
---

# Phase 14 — Validation Strategy

> Draft validation contract derived from 14-RESEARCH.md. Plans and wave assignments are pending the UI design contract. This document does not claim implementation or verification completion.

## Test Infrastructure

| Property | Value |
|----------|-------|
| Framework | Existing pytest 8.4.2; planned Flask test client and pytest-playwright browser extra |
| Config file | `pyproject.toml`; shared existing fixtures in `tests/conftest.py` |
| Current baseline command | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_reporting.py tests/test_soak_reporting.py tests/test_phase11_transitions.py tests/test_shadow_reporting.py` |
| Planned quick command | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_web_evidence.py tests/test_web_auth.py tests/test_web_security.py tests/test_web_reports.py tests/test_alert_store.py tests/test_alert_observer.py tests/test_web_capabilities.py` |
| Full suite command | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` |
| Planned browser command | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/browser/test_operator_ui.py --browser chromium` |
| Baseline observation | Researcher reports 73 existing focused tests passed in 3.39s; future focused/browser latency must be measured during execution |

The planned commands require their listed modules and web/browser dependencies to be created first. Do not call a missing-test command and interpret collection failure as product verification. Do not skip browser coverage merely because backend tests pass. Browser installation and package verification follow the research artifact's explicit dependency setup protocol.

## Sampling Rate

- After each meaningful implementation task, run the relevant focused test module(s), including any directly affected existing regressions. Use targeted commands rather than repeatedly rerunning unrelated checks.
- At each plan wave boundary, run the full suite once after its final code change. Include dedicated browser verification when that wave changes user-visible behavior.
- Before phase verification, require the backend, fresh-process capability-negative and browser suites to pass with no suppressed missing dependencies.
- Target focused feedback latency: under 60 seconds. Actual latency is unmeasured until new tests exist; split slow integration/browser groups if needed without dropping required coverage.
- Tests use temporary frozen sources, controllable clocks and fake notifier/network collaborators. No authenticated KIS, live LLM, actual Discord delivery, private VPN deployment or real-account mutation is necessary for automated validation.

## Per-Task Verification Map

Task IDs and wave assignments below are intentionally TBD until the planner consumes UI-SPEC.md. The planner must replace TBD with its actual plan/task IDs and retain security references in PLAN.md `<threat_model>` blocks.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD-evidence | TBD | TBD | FUT-03, UI-01 | T14-EVIDENCE | Missing/incomplete snapshots, zero placeholders, source mismatch and stale observations remain UNKNOWN/INCOMPLETE; exact aggregate/detail identities; all-date 000660 preserved | unit/integration | `python3 -m pytest -q tests/test_web_evidence.py` | No — setup required | pending |
| TBD-auth | TBD | TBD | UI-02 | T14-AUTH | Dedicated account, password hashing, concurrent independent sessions, absolute 12h expiry unaffected by refresh; logout/reset invalidation | unit/integration | `python3 -m pytest -q tests/test_web_auth.py` | No — setup required | pending |
| TBD-security | TBD | TBD | UI-02 | T14-CSRF, T14-DISCLOSURE | Authentication/authorization on every page/API/download/action; CSRF including login/logout; escaped untrusted text; host/origin/proxy and path controls; secrets excluded | adversarial integration | `python3 -m pytest -q tests/test_web_security.py` | No — setup required | pending |
| TBD-reports | TBD | TBD | FUT-03, UI-01, UI-02 | T14-EXPORT | Bounded registered TXT/JSON/CSV reports preserve sources/denominators/unknowns; spreadsheet formula handling; no evaluation/provider invocation | unit/integration | `python3 -m pytest -q tests/test_web_reports.py` | No — setup required | pending |
| TBD-incidents | TBD | TBD | OPSV-01, UI-02 | T14-ACK | Durable episode/revision identity resets acknowledgement on worsening/recurrence; optional note with actor/time; acknowledgement never mutates safety/recovery facts | state transitions | `python3 -m pytest -q tests/test_alert_store.py` | No — setup required | pending |
| TBD-observer | TBD | TBD | OPSV-01 | T14-DELIVERY | Source-driven stale/failed worker/cycle/order/latch/divergence alerts; browser-independent observer; 30min CRITICAL-only reminders; Phase 11 dedup ownership; crash/shutdown/delivery uncertainty | clock-controlled integration | `python3 -m pytest -q tests/test_alert_observer.py` | No — setup required | pending |
| TBD-capabilities | TBD | TBD | UI-02, OPSV-01 | T14-AUTHORITY | Fresh-process module/import/constructor/socket and source-write tripwires; no broker/live LLM/settings/lease capability; source schema/data unchanged by all actions | subprocess/integration | `python3 -m pytest -q tests/test_web_capabilities.py` | No — setup required | pending |
| TBD-browser | TBD | TBD | FUT-03, UI-01, UI-02 | T14-CLIENT | Korean desktop/mobile navigation and drill-down, system themes, keyboard access, 30s/manual refresh and stale fallback, expiry, downloads and acknowledgement | browser E2E | `python3 -m pytest -q tests/browser/test_operator_ui.py --browser chromium` | No — setup required | pending |

Run all commands above with the repository's `PYTHONUSERBASE="$PWD/.python-userbase"` prefix unless dependencies are deliberately installed into a reviewed isolated environment. Never silently point tests at the owner's live evidence stores.

## Wave 0 Requirements

- [ ] Define the concrete plans/task dependency mapping after UI-SPEC.md is available; populate the verification map with real plan and wave IDs.
- [ ] Add web dependencies and browser extra using reviewed versions; no installation has been performed by planning/research.
- [ ] Create isolated saved audit/portfolio/soak/replay/backtest/shadow fixtures with exact linked IDs, schema ownership, account/target scope, positive and deliberately broken provenance, missing sources and incomplete placeholders.
- [ ] Provide fake clock, temporary operational/session/alert store and fake transport fixtures independent of credential-bearing production setup.
- [ ] Add meaningful tests in all listed modules alongside the implementation that satisfies them; empty test stubs do not establish coverage.
- [ ] Build the fresh-process capability harness without imports from the credential-bearing shared production conftest. Check constructor attempts and filesystem authority as well as module names.
- [ ] Register the browser marker and isolated local-server harness; provision a Chromium browser through the reviewed browser setup path. Backend success is not a substitute for browser verification.
- [ ] Measure quick-suite/browser latency and document deterministic commands. Update this draft after plans are created and verified.

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Owner's optional private VPN/HTTPS mobile access | FUT-03, UI-02; D-05 | Actual network/topology and phone are outside frozen local tests; no VPN vendor chosen | After explicit owner configuration, verify access from phone mobile data through private VPN, authentication, HTTPS/cookie behavior, concurrent PC session, logout and expiry. Confirm default remains local and no public access is introduced. |
| Korean visual usability | UI-01; D-01–D-04 | Browser checks automate behavior/layout but the owner judges readability | Review safety-first overview, four navigation groups, mobile details and system light/dark themes with realistic saved evidence. Unresolved warnings, UNKNOWN and age must be understandable without color alone. |

Optional private-network acceptance is distinct from automated application correctness. No manual check authorizes KIS/LLM calls, notification sending, policy writes or a real-money transition.

## Validation Sign-Off

- [ ] Every task has automated verification or an explicit setup dependency.
- [ ] Sampling continuity: no three consecutive implementation tasks without automated verification.
- [ ] Setup dependencies cover all currently missing test modules/framework/browser references.
- [ ] No watch-mode test commands.
- [ ] Actual task/plan/wave and threat IDs replace TBD references before execution readiness.
- [ ] Focused feedback latency target is measured and met or a documented split is used.
- [ ] Required coverage for FUT-03, UI-01, UI-02, OPSV-01 and D-01 through D-16 is assigned and checked.
- [ ] `nyquist_compliant: true` is set only after the final plan validation contract meets these conditions.

**Approval:** Pending final plans and validation; no implementation tests are represented as complete.
