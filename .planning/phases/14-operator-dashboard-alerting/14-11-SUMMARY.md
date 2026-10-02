---
phase: 14-operator-dashboard-alerting
plan: "11"
subsystem: operator-web
tags: [saved-evidence, flask, csrf, acknowledgement, chromium, progressive-refresh, tdd]
requires:
  - phase: 14-07
    provides: SavedReportService exact selections, safe serializers and owned artifacts
  - phase: 14-08
    provides: Durable episode/revision/read CAS and delivery histories
  - phase: 14-09
    provides: Persisted observer lifecycle and independent monitoring
  - phase: 14-10
    provides: Guarded native views, session/origin/CSRF boundaries and saved render envelopes
provides:
  - Six saved validation families with attributable metric constituent and record evidence links
  - Authenticated audited native/enhanced report generation and sealed owned TXT/JSON/CSV downloads
  - All-date active incidents, period history, revision-safe acknowledgement and separate recovery/delivery states
  - Visible 30-second saved reads, 10-second timeout, preserved drafts/focus/disclosures and cache revalidation
affects: [14-12, phase-verification]
tech-stack:
  added: []
  patterns: [server-owned-escaped-fragments, native-progressive-forms, parameterized-operational-history, conceal-before-cache-revalidation]
key-files:
  created:
    - trading_bot/templates/operator/validation.html
    - trading_bot/templates/operator/reports.html
    - trading_bot/templates/operator/alerts.html
    - trading_bot/static/operator.js
    - tests/test_web_report_routes.py
    - tests/test_web_alert_routes.py
    - tests/browser/test_operator_refresh.py
  modified:
    - trading_bot/web_app.py
    - trading_bot/templates/operator/base.html
    - tests/test_web_security.py
key-decisions:
  - "Validation projections, metric details and downloads reuse registered SavedReportService contracts; missing calibration/readiness proof remains named UNKNOWN."
  - "Only the authenticated server actor and clock can acknowledge a current revision; sanitized notes and read facts never change source recovery or freeze evidence."
  - "Native GET/forms remain usable without JavaScript; enhanced actions never retry or replay POST after authentication loss."
requirements-completed: [FUT-03, UI-01, UI-02, OPSV-01]
coverage:
  - id: D1
    description: Six saved families, exact constituent selectors, named uncertainty and authenticated owned three-format export
    requirement: FUT-03
    verification:
      - {kind: integration, ref: "tests/test_web_report_routes.py", status: pass}
      - {kind: automated_ui, ref: "tests/browser/test_operator_refresh.py#test_enhanced_report_three_real_downloads", status: pass}
    human_judgment: false
  - id: D2
    description: Active all-date and history incidents, delivery uncertainty and audited read CAS without source mutation
    requirement: OPSV-01
    verification:
      - {kind: integration, ref: "tests/test_web_alert_routes.py", status: pass}
      - {kind: automated_ui, ref: "tests/browser/test_operator_refresh.py#test_enhanced_ack_conflict_retains_draft_then_server_success", status: pass}
    human_judgment: false
  - id: D3
    description: Visible saved refresh, virtual timeout/failure/visibility/draft preservation and absolute/revoked/cache session concealment
    requirement: UI-02
    verification:
      - {kind: automated_ui, ref: "tests/browser/test_operator_refresh.py", status: pass}
    human_judgment: false
duration: 22min
completed: 2026-10-02
status: complete
---

# Phase 14 Plan 11: Saved Validation, Incident Reading and Progressive Refresh Summary

**등록된 저장 검증의 정확한 지표 구성·원천 증거, 소유 보고서 세 형식 다운로드, revision별 읽음 CAS 및 세션 보호 자동 새로고침을 한국어 기본 화면과 실제 Chromium에서 연결했습니다.**

## Performance

- Recorded execution clock: 2026-10-02T04:50:22Z.
- Final implementation commit: 2026-10-02T05:11:59Z.
- Tasks: 3/3. Implementation/test files: 10, plus this SUMMARY.
- Main checkout; no worktrees or branches. Normal Git hooks enabled.

## Accomplishments and Consumer Interfaces

- `/validation/<family>` and `/validation/<family>/<result_id>` expose the fixed replay/backtest/shadow/soak/calibration/readiness catalog. Registered source and optional saved result selectors are validated with ReportRequest. `metric_id` selects `projection.metric_detail()` constituents including excluded/UNKNOWN rows; `record_id` selects the same sanitized row. Selection/source IDs, exact metric numerator/denominator, determinate denominator, facts, labels, stored window and diagnostics remain from the saved service. Modeled/advisory/Shadow limitation Korean copy remains explicit. No approval booleans, policy, source path or evaluator inputs are accepted.
- `/reports` displays registered family/resource/target, source period/result and format selectors before generation. CSRF-protected `/reports/generate` uses the current authenticated actor, preserves service ATTEMPTED/SUCCEEDED/FAILED audits and adds INVALID_REQUEST/REQUEST_BOUND diagnostics for rejected web inputs. Successful generation displays saved selection/source IDs, generation time, opaque artifact identities and download links.
- `/reports/<artifact_id>` and `/downloads/<artifact_id>/<format>` revalidate the session, opaque 64-hex ID, actor ownership, registered resource, supported format and bounded sealed bytes through `load_owned_artifact`. Downloads use `OwnedArtifact.data` only, fixed MIME/attachment headers, no-store and nosniff; malformed, foreign, unavailable or incompatible artifacts remain safe 404s. Successful/refused downloads are audited without paths or raw exceptions.
- `/alerts` keeps all severities in an all-date active section and separate KST-filtered history, with bounded pages and explicit UNKNOWN total. Registered account/target/resource authorization excludes malformed subjects. Detail routes expose stable episode/current revision, occurrence/time/duration, linked source sequences, previous revisions/read facts, reminder due time, producer/observer delivery ownership, failed/UNKNOWN outcomes and delivery history. Observer state/heartbeat/failure and the local worker review link are independent of acknowledgement.
- CSRF-protected `/alerts/<episode_id>/ack` accepts only expected revision and an optional <=500-character note. Actor/time come from the server, redaction precedes bounded persistence, and all returned notes use escaped template/text nodes. Success stops only reminders; source recovery/freeze facts are untouched. CAS conflict returns 409 with latest revision and retained draft; validation/CSRF/write failure leaves safe input and explicit diagnostics. AlertStore's atomic read audit and WebStore's action audit both record outcomes.
- New fixed API builders are `validation-<family>`, `reports`, `alerts`, `record` and `evidence`, under the existing globally guarded `/api/views/<view_id>`. They share native rendered HTML, source/query metadata, exact selections and authoritative session expiry. `/api/session` provides guarded cache revalidation for authenticated pages without a saved view builder. Record/evidence refresh resolves the same registered source and ID as native GET.
- Local CSP-compatible `operator.js` polls visible saved views at 30 seconds with one in-flight operation and a 10-second AbortController deadline. Manual refresh shares that path. Hidden tabs pause and resume with one read. Failed/slow reads keep the last evidence and its actual observation timestamp; browser query metadata stays separate.
- Dirty forms, focused rows/text selection, disclosures and scroll defer automatic row replacement; compact source status and `새 증거가 있습니다` remain available. Explicit refresh applies server-owned escaped fragments while preserving notes/input selections/disclosures. Unchanged automated results do not repeat loading announcements; new active CRITICAL revisions announce once.
- Enhanced POST forms send CSRF headers, do not show optimistic acknowledgement, retain failed notes, and never retry a POST after timeout or reauthentication. Absolute expiry/revocation removes sensitive cache DOM and offers login. Persisted pageshow conceals the entire private wrapper before server revalidation; failed revalidation keeps it concealed. Native navigation, report/download and blank-note read forms work with JavaScript disabled.

## Task Commits

1. T1 RED: `88435bc` — define saved validation and owned report route gates.
2. T1 GREEN: `cf0d831` — connect saved validation metrics and authenticated owned exports.
3. T2 RED: `26853d0` — define incident/read CAS safety contracts.
4. T2 GREEN: `fefd3b7` — expose active/history incidents and audited revision-safe read actions.
5. T3 RED: `ded55c5` — define real Chromium timer/draft/session behavior.
6. T3 GREEN: `b90cca9` — implement saved refresh, preserved drafts and authoritative session concealment, plus required report/ack audit/scope follow-ups found by final route verification.

## Verification

Every command used `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q`; focused commands remained below 60 seconds.

| Selection | Result | Duration |
|---|---|---|
| `tests/test_web_report_routes.py --tb=short` T1 RED | 13 failed, expected missing 404 routes | 5.82s |
| `tests/test_web_report_routes.py tests/test_web_reports.py --tb=short` T1 GREEN | 62 passed | 22.74s |
| `tests/test_web_alert_routes.py --tb=short` T2 RED | 10 failed, expected missing 404 routes | 4.68s |
| `tests/test_web_alert_routes.py tests/test_web_security.py --tb=short` T2 final | 42 passed | 6.00s |
| `tests/browser/test_operator_refresh.py --browser chromium --tb=short` T3 RED | 7 failed, absent script/refresh mounting | 43.86s |
| Same browser selection, first GREEN | 7 passed | 9.89s |
| Same browser selection, final expanded coverage | 12 passed | 16.39s |
| `tests/test_web_alert_routes.py tests/test_web_report_routes.py tests/test_web_security.py tests/test_web_routes.py --tb=short` final | 73 passed | 23.04s |

Chromium tests exercised actual browser execution and download events. Playwright virtual clock and injected temporary source clock replaced real 30-second waits. Failure vectors include delayed aborted reads, visibility/inflight overlap refusal, a missing temporary saved source, dirty focused textarea/range/disclosure/scroll, revision conflict followed by authenticated server success, server-clock exactly-12h expiry, explicit revocation and persisted pageshow, and JavaScript-disabled native generation/download/blank acknowledgement. All test inputs, passwords, stores and server are synthetic/temporary; browser requests are restricted to the fixture origin. No requested browser cases were skipped and no backend substitute was used.

The expanded anonymous matrix initially expected page redirects for three new API entries; those test expectations were corrected to the established API 401 contract before T2 final pass. The original T1 fixture initialization collision was corrected before recording meaningful route RED failures. Neither required production changes.

`git diff --check` passed. No tracked files were deleted. Source byte invariance is asserted for validation/export/native actions and acknowledgement, including preservation of 000660 safety evidence. Full wave regression and phase completion remain parent-owned.

## Deviations from Plan

- **[Rule 3 - Blocking integration] Minimal base template mounting.** The planned JS file had no script mount or stable evidence/private-cache region in the existing shell. Parent explicitly preauthorized the narrow base.html change. Added the local deferred script, view/expiry data attributes and DOM wrappers; navigation, tokens, CSS and design were unchanged. The private wrapper avoids CSS display rules overriding hidden headers during cache revalidation. Commit `b90cca9`.
- **[Rule 2 - Missing critical selectors] Bounded incident history.** AlertStore's existing list API exposes neither dates nor offsets. The route uses a fixed parameterized readonly query against the operational alert database only, then the existing authenticated incident projections, to support KST history and active paging without modifying schema/source facts. Commit `fefd3b7`; selected resource scope enforcement was finalized in `b90cca9`.
- **[Rule 2 - Complete cache/refresh boundary] Record/evidence API and session validation.** Existing native detail routes lacked a saved refresh envelope; fixed registered builders now reuse their native readonly resolver. A guarded session endpoint supports authentication validation on the remaining authenticated artifact screen. Added bounded-web-request/unauthorized-ack audits and explicit registered target attribution during final planned route verification. Commit `b90cca9`.

## Known Stubs

None preventing this plan's goal. Missing registered calibration/readiness proofs, source timestamps or source records are intentional named UNKNOWN/unavailable evidence states, not fabricated data. No live lookup or request-supplied approval fills those gaps.

## Threat Surface Review

The report/ack writes, owned download routes, escaped saved fragments and guarded session/cache validation implement the planned T14-CSRF/T14-ACK/T14-EXPORT/T14-CLIENT/T14-XSS boundaries. No source schema, external endpoint, live provider, broker, policy mutation, trade, freeze release, observer start/stop or raw filesystem selector was introduced. Parent-owned STATE/ROADMAP/REQUIREMENTS/VALIDATION and browser fixture files were preserved.

## Documentation Lookup

Context7 MCP and ctx7 CLI were unavailable. Official [Flask JavaScript/fetch documentation](https://flask.palletsprojects.com/en/stable/patterns/javascript/) and [Playwright clock documentation](https://playwright.dev/python/docs/clock) were checked for the installed form/fetch and virtual-clock APIs. No package or browser installation was needed.

## Remaining Phase Verification

14-12/parent own broader desktop/mobile/system-theme/keyboard/zoom/contrast UI acceptance, full-wave regression, and final planning-state/phase completion. Optional private VPN/phone acceptance and owner Korean usability judgment remain manual phase checks. No persistent server, deployment, real operator password, owner DB, live KIS/LLM/Discord access or operational notification send occurred.

## Self-Check: PASSED

Verified all ten implementation/test files and this canonical SUMMARY exist, all six RED/GREEN task commits resolve through Git, final backend/real-Chromium selections passed, and diff checks are clean. No tracked deletion or generated untracked files remain. Shared planning artifacts were not changed or staged by this executor.
