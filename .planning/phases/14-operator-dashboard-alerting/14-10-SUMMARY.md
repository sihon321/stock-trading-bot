---
phase: 14-operator-dashboard-alerting
plan: "10"
subsystem: web
tags: [flask, csrf, server-sessions, korean, readonly-evidence, tdd]
requires:
  - phase: 14-05
    provides: Independent WebSettings, authoritative WebAuth and operational WebStore
  - phase: 14-06
    provides: Bounded immutable saved evidence projections and source envelopes
  - phase: 14-08
    provides: Saved incident query interfaces
  - phase: 14-14
    provides: Approved Korean navigation, native CSS and escaped presentation macros
provides:
  - Guarded Flask factory, dedicated login/logout, origin/proxy/CSRF/session boundary
  - Safety overview and eight operational pages with canonical record/evidence drilldown
  - Sanitized HTML/status API envelopes for subsequent progressive refresh
  - All-date positive saved safety latches independent of observer startup
affects: [14-11, 14-12]
tech-stack:
  added: []
  patterns: [Fixed proxy boundary, central deny-by-default route guard, native GET review, readonly operational status]
key-files:
  created:
    - trading_bot/web_app.py
    - trading_bot/templates/operator/login.html
    - trading_bot/templates/operator/overview.html
    - trading_bot/templates/operator/list.html
    - trading_bot/templates/operator/detail.html
    - tests/test_web_security.py
    - tests/test_web_routes.py
  modified:
    - trading_bot/templates/operator/macros.html
    - tests/test_web_ui_contract.py
    - trading_bot/web_models.py
    - trading_bot/web_evidence.py
    - tests/test_web_evidence.py
key-decisions:
  - All non-login/non-fixed-static requests validate their authoritative server session, including unknown and subsequently registered routes.
  - Unknown aggregate totals remain nullable; original source observation time survives query failure.
  - Persisted campaign safety latches appear before health/account facts without requiring a running observer.
requirements-completed: [FUT-03, UI-01, UI-02]
coverage:
  - id: guarded-operational-http
    description: Server sessions, absolute expiry/reset revocation, CSRF, fixed origins/proxy trust and safe errors
    requirement: UI-02
    verification: [{kind: integration, ref: tests/test_web_security.py, status: pass}]
    human_judgment: false
  - id: operational-drilldown
    description: Safety-first native pages, exact snapshot/risk selections and sanitized durable record/evidence links
    requirement: UI-01
    verification: [{kind: integration, ref: tests/test_web_routes.py, status: pass}]
    human_judgment: false
duration: 24min
completed: 2026-10-02
status: complete
---

# Phase 14 Plan 10: Authenticated Operational Evidence Summary

**서버 만료 세션·CSRF·고정 프록시 경계와 모든 날짜의 안전 래치를 갖춘 한국어 저장 증거 화면 및 정확한 구성→기록→정제 증거 경로를 구현했습니다.**

## Accomplishments

- `create_app` consumes independent WebSettings and injected saved-only services. Its central guard applies to operational routes, API, unknown paths and future report/alert/download registrations. Only login and two fixed packaged asset names are public. It imports no trading Settings, CLI, broker, provider, notifier or observer constructor.
- WebAuth verifies opaque server sessions on every protected request. Concurrent clients, exact 12-hour expiry, password-reset revocation, login/logout CSRF, hostile Origin, fixed-host validation, explicit one-peer proxy trust and rejection of multi-value forwarding headers have temporary-store tests. Private mode enforces HTTPS origin and Secure/HttpOnly/SameSite=Lax cookies. All responses carry no-store, CSP, nosniff and frame denial; exceptions return bounded stable error codes.
- `/`, `/account`, `/holdings`, `/candidates`, `/decisions`, `/orders`, `/fills`, `/runs`, `/workers`, `/records/<resource_id>/<record_id>`, `/evidence/<resource_id>/<record_id>` and `/api/views/<view_id>` are wired. The existing 17 destinations/four navigation groups, CSS colors/fonts/spacing and native mobile cards are reused.
- Overview order is all-date unresolved orders/safety blocks, worker/observer health, per-source observation times, account/holdings and recent activity. Historical 000660 ambiguity remains visible under routine today/7/30/custom KST filters. Local intent and saved broker progression/fills retain separate wording and provenance. Daily LLM evaluations appear separately from audit decision records.
- Account totals and exact constituent links bind the same snapshot selection; risk selection links include unresolved local/broker/freezes across dates. UNKNOWN amounts/totals and unavailable confidence/rank/coverage/model/marks/completeness facts remain explicit. Source observation, age and browser query time are distinct; failed reads retain old complete cash/snapshot facts and their source time.
- All record/evidence routes validate registration and scope, render only sanitized DTO scalars and use escaped disclosure. Native GET filters and bounded pagination work without JS. Detail and evidence Back links retain the originating page cursor and period. Observer display inspects the existing operational database in `mode=ro`/`query_only`; it neither creates observer schema nor constructs transport, starts monitoring or sends notifications.

## Task Commits and TDD Gates

1. T1 RED — `95071b2`: server-session/CSRF/origin/proxy contracts; 26 expected missing-factory setup failures.
2. T1 GREEN — `fd8b377`: secure factory and login/logout; focused authentication selection 26 passed in 0.28s.
3. T2 RED — `4279d53`: operational overview/pages/selection/cache/drilldown contracts; 13 actual missing-route failures after correcting synthetic artifact permissions.
4. T2 required source-contract RED — `e4f21ff`: safety-latch and canonical-link regression coverage; latch test failed because OverviewDTO lacked safety_blocks.
5. T2 GREEN — `c8ee9a2`: operational pages, safe links, source-contract completion and scope guard.
6. T2 correctness follow-up — `a5cdcb2`: preserve second-page cursor in record Back links.
7. T2 correctness follow-up — `e9d355e`: preserve the same cursor through sanitized evidence links.

Each task has a RED commit before its GREEN implementation commit. The additional focused Back test exposed the missing `page` return-query allowlist before passing; no tests were reported as successful while setup or route wiring was missing.

## Verification

All commands use `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q`.

- T1 auth/login/logout/host/proxy/headers: **26 passed in 0.28s**.
- Initial operational routes plus existing native UI contracts: **54 passed in 8.25s**.
- Final owned integration command `tests/test_web_security.py tests/test_web_routes.py tests/test_web_ui_contract.py tests/test_web_evidence.py --tb=short`: **114 passed in 18.27s**. This includes absent target scope denial, canonical encoded link escape/traversal negatives, XSS escaping, secret redaction, daily evaluation display, observer-not-started safety latches and cache/source byte invariance.
- Subsequent necessary cursor regression `tests/test_web_routes.py -k second_page_cursor --tb=short`: **1 passed, 16 deselected in 1.18s**, after the record/evidence Back fixes. The parent owns the full wave regression; no redundant full repository run was performed.
- `git diff --check` passed. No tracked files were deleted or generated files left untracked.

Tests use test-only passwords, temporary operator/evidence stores and explicit clocks. No owner database, real credentials, KIS/LLM/Discord call, persistent server, deployment, order, freeze release or policy mutation occurred.

## Consumer Interfaces

`create_app(settings, *, evidence_service=None, report_service=None, alert_store=None, clock=None)` exposes capability-limited services in `app.extensions`: `web_settings`, `web_store`, `web_auth`, `evidence_service`, `report_service`, `alert_store`, `operator_clock`.

Extension helpers available for 14-11 are `operator_safe_error(code,status)`, `operator_query_context()`, `operator_contextual_url(path,context,**values)`, `operator_source_presentation(envelope,record_id=None,**extra)`, `operator_present_record(record,context,parent=None)`, and `operator_observer_status()`. Add fixed saved-view builders to `operator_view_builders` for the existing guarded `/api/views/<view_id>` handler. All later route registrations inherit the global authoritative-session/origin/CSRF guard.

API view envelopes expose `view_id`, `rendered_html`, escaped `status_html`, per-source statuses, `queried_at`, preserved `source_observed_at`, `query_status`, exact selection/nullable total, ISO `expires_at`, `expires_at_kst`, and fixed `login_url`. HTML matches native GET views; refresh implementation remains 14-11.

`OverviewDTO.safety_blocks` is an added default immutable tuple. Records use existing campaign IDs and sanitized fields; missing matching latch events or primary links retain UNKNOWN. Query failures preserve last-positive latch records; campaign completion/disappearance does not claim irreversible latch release.

## Deviations from Plan

**[Rule 1 - Bug] Corrected canonical evidence link validation.** Shared `ui.link` originally rejected the planned `/records` and `/evidence` paths and encoded colon record IDs. The parent explicitly granted narrow ownership of macros and UI contract tests. Fixed app-relative prefixes and `%3A`/`%3a` separators are accepted; encoded controls, slash/backslash traversal, arbitrary encodings, schemes and authorities remain denied. Colors/navigation/CSS were unchanged. Commit `c8ee9a2`.

**[Rule 2 - Missing Critical] Added all-date positive saved safety blocks.** Existing OverviewDTO omitted campaign latches, making safety-block coverage depend on prior observer execution. The parent explicitly granted narrow `web_models.py`, `web_evidence.py`, `tests/test_web_evidence.py` ownership. The existing schema-validated readonly reader now projects positive campaign safety/availability failures independently of date and observer startup, checks saved latch/primary links, preserves cached positives and never treats routine completion as latch release. No mutable source imports, source schema, migrations or execution authority were added. Commit `c8ee9a2`.

**[Rule 1 - Bug] Closed scope fallback and paginated Back context.** An explicitly selected, known but unregistered target previously yielded scope=None and could broaden reads. Such requests now fail with 400. Record/evidence Back links subsequently needed cursor/page preservation and a fixed `page` return parameter. Adversarial and second-page native GET regressions cover these cases. Commits `c8ee9a2`, `a5cdcb2`, `e9d355e`.

## Known Stubs

None preventing this plan's operational goal. Missing saved marks, provider/model/rank/coverage/completeness numbers and missing source/latch timestamps remain attributable UNKNOWN values. No live lookup fabricates them. Report/validation/alert/action/download implementations are assigned to 14-11 and remain guarded unavailable routes here; the shared navigation does not constitute their implementation.

## Documentation Lookup

Context7 MCP/CLI was unavailable; no package was installed. Checked official [Flask configuration](https://flask.palletsprojects.com/en/stable/config/), [Flask-WTF CSRF](https://flask-wtf.readthedocs.io/en/latest/csrf/) and [Waitress reverse proxy](https://docs.pylonsproject.org/projects/waitress/en/latest/reverse-proxy.html) documentation for the installed configuration/CSRF/proxy interfaces.

## Remaining Phase Verification

14-11 owns report/validation/incident pages, authenticated generation/download/read actions and progressive refresh/expiry UI. 14-12 owns actual computed Chromium desktop/mobile/theme/keyboard/zoom/contrast/no-JS and full-route capability/security coverage. Static CSS success is not browser proof. Optional private VPN/HTTPS/phone acceptance and owner Korean usability judgment remain separate manual checks.

Shared STATE/ROADMAP/REQUIREMENTS/VALIDATION updates remain parent-owned and were not edited or staged by this executor. The parent-owned dirty STATE was preserved.

## Self-Check: PASSED

All twelve owned implementation/test files and this canonical SUMMARY exist. Git confirms `95071b2`, `fd8b377`, `4279d53`, `e4f21ff`, `c8ee9a2`, `a5cdcb2`, and `e9d355e`. Final focused verification and the necessary cursor follow-up passed; no tracked deletion or generated untracked output remains. Shared planning changes are excluded from this plan's commits.
