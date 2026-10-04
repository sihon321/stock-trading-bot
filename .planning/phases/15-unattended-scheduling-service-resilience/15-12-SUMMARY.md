---
phase: 15-unattended-scheduling-service-resilience
plan: "12"
subsystem: web
tags: [flask, csrf, native-forms, control-requests, korean, sqlite]
requires:
  - phase: 15-05
    provides: Protected installation-global request journal and narrow reader/writer capabilities
  - phase: 15-08
    provides: Final submission admission serialized with accepted restrictive requests
  - phase: 15-11
    provides: Fixed ControlResourceDescriptor and saved service/control DTOs
provides:
  - Authenticated fixed-resource pause/resume/kill requests with durable replay correlation
  - Korean native controls showing accepted restrictions separately from service application and admission history
affects: [15-13, 15-14, operator-dashboard]
tech-stack:
  added: []
  patterns: [request-only descriptor composition, idempotent cross-store audit correlation, conservative saved-health resume affordance]
key-files:
  created: [trading_bot/web_control.py, trading_bot/templates/operator/controls.html, tests/test_web_control_routes.py]
  modified: [trading_bot/web_app.py, trading_bot/control_store.py, trading_bot/web_store.py, trading_bot/templates/operator/base.html, trading_bot/templates/operator/overview.html, trading_bot/static/operator.css, tests/test_web_security.py]
key-decisions:
  - "Web requests use a fixed descriptor and narrow read/request ports; server session actor and immutable server time identify replay."
  - "Durable control acceptance precedes web audit; missing audit correlation stays visible and a manual retry retains the original request ID and revision."
  - "Only fresh saved RISK evidence for every registered scope enables a new resume request; acceptance never applies resume or grants trading authority."
requirements-completed: []
coverage:
  - id: D1
    description: Fixed authenticated request authority and immutable correlation without service application capability
    requirement: AUTO-02
    verification:
      - kind: integration
        ref: tests/test_web_control_routes.py#test_request_only_durable_actor_revision_replay_and_correlation
        status: pass
      - kind: integration
        ref: tests/test_web_control_routes.py#test_web_audit_failure_truth_and_same_id_repair
        status: pass
      - kind: integration
        ref: tests/test_web_control_routes.py#test_descriptor_factory_has_no_service_or_trading_capabilities
        status: pass
    human_judgment: false
  - id: D2
    description: Native Korean controls, escaped notes, stale/unknown resume denial and separate applied/rejected/in-flight facts
    requirement: AUTO-02
    verification:
      - kind: automated_ui
        ref: tests/test_web_control_routes.py#test_native_controls_reachable_and_exact_consequences
        status: pass
      - kind: automated_ui
        ref: tests/test_web_control_routes.py#test_notes_escaped_bounded_and_unknown_blocks_remain_visible
        status: pass
      - kind: integration
        ref: tests/test_web_control_routes.py#test_resume_unknown_and_stale_disabled_without_disabling_stop
        status: pass
      - kind: automated_ui
        ref: tests/test_web_ui_contract.py
        status: pass
    human_judgment: false
  - id: D3
    description: Actual Korean desktop/phone visual usability and configured private phone access
    verification: []
    human_judgment: true
    rationale: Rendered HTML and existing responsive CSS contracts do not prove device visuals or configured private access; phase-end owner review remains required.
duration: 12min
completed: 2026-10-04
status: complete
---

# Phase 15 Plan 12: Authenticated Mobile and Desktop Control Requests Summary

**Fixed authenticated pause/resume/kill requests with immutable replay correlation and Korean native forms that separate accepted restrictions from actual service application.**

## Performance

- **Measured implementation interval:** 12min, from first RED commit to final GREEN; preparatory context discovery excluded because its start timestamp was not recorded.
- **Started:** 2026-10-04T11:55:14Z (first RED commit)
- **Completed:** 2026-10-04T12:07:35Z (final GREEN)
- **Tasks:** 2
- **Files created/modified:** 10 source/test files

## Accomplishments

- Added GET `/controls`, GET `/controls/<resource_id>` and exact lowercase POST pause/resume/kill routes under the existing session, host, proxy, origin and CSRF protections. All fields except csrf_token/request_id/expected_revision/bounded optional note are rejected; duplicate fields, forged authority, arbitrary resources and malformed UUID/revision inputs fail safely.
- Request helper consumes only the fixed ControlResourceDescriptor, request/read facades and server actor/time. It imports no trading Settings, broker/provider, service composition or application writer. The factory opens only already initialized protected control/lock resources, reusing exact owner/schema/setup/lock identity checks; it cannot bootstrap storage or mint service authority.
- Replays reuse the original committed server timestamp and exact UUID lookup, independently of the bounded history page. Control request and control audit commit atomically before web audit. The web action stores the same UUID/revision once; web-audit failure returns truthful 503 while durable restrictions remain visible, and manual retry retains the original request ID/revision to repair correlation without another action.
- Korean native forms distinguish current restriction/latest accepted revision, applied mode/revision, pending requests, rejected resume reasons and older IN_FLIGHT/UNKNOWN admissions. Pause preserves otherwise eligible protective SELL and reconciliation; kill blocks all new submissions including protective SELL and keeps reconciliation. No cancellation is promised for an already admitted order.
- A new resume request needs fresh complete saved RISK evidence for every registered scope and the current accepted revision; unknown/stale/blocked evidence disables permissive requests. Healthy request storage still permits pause/kill when the service is stopped or its saved health is unavailable. The service alone validates and applies resume; acceptance leaves existing PAUSED/KILLED state intact.
- Preserved prior navigation labels/inventory, approved tokens, responsive single-column/grid behavior, 320px minimum viewport and 44px controls. Added a separate semantic control navigation link, overview link, native kill consequence disclosure and one destructive-token color rule. Notes, IDs and errors remain escaped/sanitized; no automatic POST retry occurs after errors/session expiry.

## Task Commits

1. **Task 1 RED:** `ebd7b44` — authenticated request boundaries and durable correlation tests.
2. **Task 1 GREEN:** `ee52125` — request-only endpoints and descriptor/audit seams.
3. **Task 2 RED:** `103b2f1` — Korean native controls and saved-state safety affordance tests.
4. **Task 2 GREEN:** `eb1554c` — saved health, controls rendering, truthful audit status and preserved manual-retry identity.

## Verification

- Task 1 focused control routes/alert routes/service controls/web store: **92 passed in 21.03s**.
- Task 2 control routes/UI contracts: **77 passed in 5.59s**.
- Broader control/alert/UI/service/store/capability/security run: **193 passed**, with three route-inventory fixture failures caused by the new action parameter. Capability/store/control checks passed; the inventory was updated to cover both new endpoints without weakening authentication assertions.
- Final required suites plus all three affected security inventory/expired/revoked-session checks: **95 passed in 16.00s**. There are **24** new control-route test cases, including eight forged-field and four action-allowlist cases.
- `git diff --check` and py_compile for all four changed Python production modules passed. No unexpected tracked deletion or generated untracked file remains.
- All implementation tests used temporary stores and injected/fake clocks. No broker, paid LLM, Discord, production journal read/migration, installer, acceptance approval or launchctl action occurred. Whole-wave full regression is delegated to the orchestrator after plan 15-13.

## Decisions Made

Use descriptor-based request/read composition rather than constructing a service owner in HTTP handlers. Keep independent control/web audit transactions truthful: missing web correlation is visible and repairable but never erases committed restrictions or invents service application. Saved health controls whether a new resume request is offered; it remains advisory to the stricter live service validation.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added narrow capability and audit correlation seams.**
- **Found during:** Task 1.
- **Issue:** Existing ports required a full ControlStore(ServiceSettings) owner; generic web action details accepted only integer counts and could not link request UUIDs.
- **Fix:** Added descriptor-only read/request factory and exact replay lookup in control_store.py, plus a separate bounded UUID/revision/note idempotent control audit method preserving the generic audit API. Parent explicitly extended ownership before edits.
- **Verification:** Descriptor capability, correlated replay, audit failure/repair and existing service/store tests passed.
- **Commit:** `ee52125` (further safe control-owner check in `eb1554c`).

**2. [Rule 3 - Blocking] Extended the existing security route inventory and consumed the approved destructive token.**
- **Found during:** Task 2.
- **Issue:** Route inventory could not substitute `<action>` or enumerate the two new endpoints. The destructive token had no selector available for a kill button.
- **Fix:** Added the pause action substitution and new endpoint inventory entries without weakening guards; added only the kill button background/border/foreground token rule. Parent explicitly granted both narrow file extensions.
- **Verification:** Three affected security cases and existing UI contracts passed in the final 95-test run.
- **Commit:** `eb1554c`.

## TDD Gate Compliance

Both tasks have expected failing RED commits followed by passing GREEN commits. Task 1 produced 18 missing-feature failures after correcting temporary fixture setup; Task 2 produced five expected rendering/state failures after correcting its service-applier fixture API. No RED gate was skipped.

## Issues Encountered

The initial inline route shell used a Jinja rendering function whose `source` parameter conflicted with the existing source metadata keyword. It was corrected before Task 1 GREEN and replaced by the final native template in Task 2. Security inventory maintenance was completed under the approved narrow assignment; no unresolved implementation issue remains.

## User Setup Required

Actual Korean PC/phone visual review and configured private access/device acceptance remain pending and are not claimed. Both actual 09-08 approvals remain absent; the authenticated 000660 ambiguity freeze is preserved. Actual Codex single-shot capabilities remain unverified/closed. No real-money promotion or installed service activation occurred. AUTO-02 remains pending final whole-phase verification, so requirements-completed intentionally stays empty.

## Next Phase Readiness

Plan 15-13 can retain the web request boundary while composing independent service/observer supervision. Plan 15-14 must verify installed composition, actual process behavior and phase-end human acceptance. Durable restrictive requests and final POST admission continue sharing the existing installation-global lock; web resume grants no activation, application, freeze-release or policy authority.

## Self-Check: PASSED

All ten declared/explicitly extended source/test files exist, and all four TDD commits exist. Required native/auth/CSRF/replay/state tests passed. No unfinished stub prevents this plan's implementation goal; external activation and actual visual/private access acceptance remain deliberate gates.
