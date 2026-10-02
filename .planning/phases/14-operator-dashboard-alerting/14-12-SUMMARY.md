---
phase: 14-operator-dashboard-alerting
plan: "12"
subsystem: testing
tags: [pytest, chromium, playwright, capability-boundary, packaging, operator-runbook]
requires:
  - phase: "14-11"
    provides: Native refresh, conflict, session restore and independent observer evidence
  - phase: "14-13"
    provides: Saved calibration/readiness/soak boundary proofs
provides:
  - Fresh-child full web/report/observer authority and source invariance proofs
  - Real Chromium navigation, downloads, accessibility, themes and mobile workflows
  - Offline isolated wheel resource, independent CLI and factory rendering proof
  - Korean local/private operation, source ownership and observer lifecycle runbook
affects: [phase-14-verification, operator-operations, phase-15, phase-16]
tech-stack:
  added: []
  patterns:
    - Install tripwires before importing targets in a fresh subprocess
    - Compare every source owner schema, rows and file bytes after each supported action
    - Measure rendered contrast and targets in Chromium rather than relying on static tokens
    - Verify locally built distributions with isolated Python and no checkout fallback
key-files:
  created:
    - tests/test_web_capabilities.py
    - tests/test_operator_integration.py
    - tests/browser/test_operator_ui.py
    - tests/test_web_packaging.py
  modified:
    - tests/test_web_security.py
    - tests/test_web_ui_contract.py
    - trading_bot/static/operator.css
    - trading_bot/static/operator.js
    - trading_bot/templates/operator/base.html
    - docs/operator-runbook.md
key-decisions:
  - Preserve native details accessibility without a fixed expanded attribute; synchronize enhancement state on actual toggle.
  - Apply the existing 44px target token as minimum link width without changing approved theme or navigation tokens.
  - Report actual Python 3.14.3 verification; metadata >=3.10 does not establish StrEnum compatibility on 3.10.
  - Keep private VPN/HTTPS reachability and Korean readability as explicit human checks; no deployment or notification authority is granted.
  - Parent runs the final full regression suite once at the wave boundary and owns shared planning updates.
patterns-established:
  - Exact route enumeration detects unsupported methods and future security coverage omissions.
  - Temporary synthetic review screenshots survive pytest cleanup without entering repository history.
requirements-completed: [FUT-03, UI-01, UI-02, OPSV-01]
coverage:
  - id: D1
    description: Every supported web/report/observer action lacks trading/source mutation authority
    requirement: FUT-03
    verification:
      - kind: integration
        ref: tests/test_web_capabilities.py#test_fresh_supported_surface_and_each_source_owner_invariant
        status: pass
      - kind: integration
        ref: tests/test_web_security.py
        status: pass
    human_judgment: false
  - id: D2
    description: All 17 destinations and native details/download/read workflows work across desktop and mobile themes
    requirement: UI-01
    verification:
      - kind: automated_ui
        ref: tests/browser/test_operator_ui.py
        status: pass
      - kind: automated_ui
        ref: tests/browser/test_operator_refresh.py
        status: pass
    human_judgment: false
  - id: D3
    description: Rendered contrast, 44px targets, keyboard, zoom, local table scroll and native no-JS behavior
    requirement: UI-02
    verification:
      - kind: automated_ui
        ref: tests/browser/test_operator_ui.py#test_every_destination_detail_theme_contrast_and_mobile_targets
        status: pass
      - kind: automated_ui
        ref: tests/browser/test_operator_ui.py#test_keyboard_skip_menu_focus_local_scroll_and_200_percent_zoom
        status: pass
    human_judgment: false
  - id: D4
    description: Incident read/worsening/recovery/recurrence and producer-owned or UNKNOWN delivery remain truthful
    requirement: OPSV-01
    verification:
      - kind: integration
        ref: tests/test_operator_integration.py
        status: pass
    human_judgment: false
  - id: D5
    description: Offline installed wheel contains native resources and independent CLI/factory behavior
    verification:
      - kind: integration
        ref: tests/test_web_packaging.py#test_offline_installed_wheel_has_native_resources_independent_entrypoints_and_render
        status: pass
    human_judgment: false
  - id: D6
    description: Local/private operational instructions match tested CLI and evidence contracts
    verification:
      - kind: integration
        ref: tests/test_web_packaging.py#test_phase14_runbook_matches_local_private_and_observer_contract
        status: pass
    human_judgment: false
  - id: D7
    description: Actual private phone mobile-data/VPN/HTTPS reachability and Korean readability
    verification: []
    human_judgment: true
    rationale: Synthetic Chromium cannot prove the owner's chosen network/certificate setup or subjective Korean usability.
duration: 244min
completed: 2026-10-02
status: complete
---

# Phase 14 Plan 12: Operator verification and private operations Summary

**Fresh-process authority traps, source inventories, actual Chromium workflows and an offline installed wheel prove the operator surface; the Korean runbook defines local/private access and independent observer operation.**

## Performance

- First recorded RED commit: 2026-10-02T05:24:33Z; completion: 2026-10-02T09:28Z (approximately 244 minutes elapsed, including a quota interruption).
- Tasks: 3/3. Deliverable/source files created or modified: 10, plus this summary.
- Runtime actually tested: Python 3.14.3 with the already reviewed dependency pins and installed Chromium. No new dependency or browser download was performed in this plan.
- Final full regression execution belongs to the parent wave boundary and is **pending at this summary's creation**. No earlier 1378-test baseline is claimed as the final result.

## Accomplishments

- The fresh child installs forbidden import/constructor, dotenv, socket, source SQL and filesystem tripwires before importing target modules. It bypasses shared conftest and credential fixture bootstrap. Factory, all registered routes/detail/evidence/APIs, all eight available report families and three export formats, acknowledgement, observer once/watch stop/status and independent help run behind the traps.
- Every source owner's complete schema, rows and bytes are compared after individual supported actions, including malformed/missing evidence. Separate owners retain separate read-only transactions even when audit and portfolio share a physical file. Negative controls demonstrate that the detectors reject attempted constructors, dotenv reads, sockets, mutating SQL/DDL and file writes.
- The security matrix enumerates the exact registered endpoint set, checks each method's authentication/CSRF requirements, expired/revoked sessions, wrong methods, actor IDOR, fixed path bounds, aliases, hostile text and forbidden trading endpoints. Existing Host/Origin/trusted proxy/cookie/CSP and redirect tests remain active.
- Saved-source integration proves read does not clear 000660/source latches, worsening produces a new unread revision, positive same-subject recovery permits a later unread recurrence, existing producer ownership prevents duplicate delivery, and crash-after-send UNKNOWN is retained without blind resend.
- Chromium visits all 17 destinations at 1280/390/320 in light/dark, inspects durable detail/evidence drill-downs, measures rendered text/control/focus contrast and 44px targets, enforces local table scrolling/no page overflow, tests keyboard/native mobile menu/skip focus/200% zoom/reduced motion, downloads real TXT/JSON/CSV, and exercises acknowledgement and no-JS behavior. Independent PC/phone contexts prove absolute 12-hour expiry. Actual incomplete zero facts stay UNKNOWN; all-date historic 000660 stays visible. Formula text is neutralized in actual downloaded CSV.
- The offline build copies only package/build inputs into a temporary source directory, builds `--no-index --no-deps --no-build-isolation`, installs that local wheel with `--no-index --no-deps` into a temporary target, and runs `python -I -S` outside the checkout. Every template/static resource is checked, all native templates compile, authenticated injected factory views/CSS/JS render, independent installed CLI metadata/help/setup/status work without KIS/LLM/Discord keys, and socket attempts are forbidden.
- The runbook adds protected independent source/operation/config/artifact ownership and backup, precise setup/reset/serve and watch/once/status syntax, default loopback, explicit optional private host/origin/TLS/single proxy configuration, one clearly optional primary-doc HTTPS example, observer signal stop/ownership/crash semantics, source/query time and UNKNOWN interpretation, read/reminder limits, advisory reports and CSV import caveats.

## Task Commits

| Task | RED | GREEN |
|---|---|---|
| 1 — Full authority and route security | `934ae9d` | `0076aec` |
| 2 — Real Chromium desktop/mobile/theme workflows | `e0ec689` | `f89d257` |
| 3 — Isolated wheel and private operations runbook | `8cf0f46` | `17a1c0d` |

The RED tests first failed on absent test harness/runbook implementation, rather than asserting an invented production failure. Task 2 also uncovered and repaired two real rendered UI defects. This is a `type: execute` verification plan: T1/T3 GREEN commits use `test`, and T2 GREEN uses `fix`; all three required RED/GREEN gates exist.

## Actual Verification

All pytest commands used `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q`; browser commands additionally used `--browser chromium`. Focused selections kept feedback commands below 60 seconds. No browser case was skipped.

| Selection | Actual result |
|---|---|
| T1 first RED harness case | 1 failed in 1.01s |
| `tests/test_web_capabilities.py tests/test_web_security.py tests/test_operator_integration.py` | **48 passed in 26.53s** |
| Saved calibration/soak prerequisite files | **32 passed in 2.82s** |
| T2 first RED harness case | 1 failed, 5 deselected in 3.16s |
| Initial light destination matrix before width repair | 3 failed in 11.43s |
| Initial native/keyboard/concurrent group before native menu repair | 5 passed, 2 failed, 6 deselected in 54.24s; failures were keyboard menu state |
| Destination matrix, light (all widths) | **3 passed**, 10 deselected in 59.58s |
| Destination matrix, dark/1280 | **1 passed**, 12 deselected in 19.93s |
| Destination matrix, dark/390 and 320 | **2 passed**, 14 deselected in 22.94s |
| Native navigation/download/filter/ack, desktop/mobile including no-JS | **4 passed**, 12 deselected in 28.01s |
| Fixed keyboard, incomplete-zero, formula download and screenshots | **5 passed**, 11 deselected in 9.24s |
| Concurrent PC/phone case | Passed in the initial mixed group; independent absolute session boundary assertions passed |
| Existing `tests/browser/test_operator_refresh.py` | **12 passed in 15.79s** |
| `tests/test_web_ui_contract.py` after native menu repair | **53 passed in 2.73s**; subsequent token minimum-width assertion is included for parent final regression |
| T3 RED contract/installed wheel harness | 2 failed in 0.03s |
| `tests/test_web_packaging.py tests/test_web_cli.py tests/test_alert_cli.py tests/test_operator_runbook.py` | **27 passed in 3.14s**; resumed final run **27 passed in 3.45s** |
| Screenshot-only recapture into retained temporary output | **1 passed**, 15 deselected in 3.64s |

All 16 current operator UI cases have passing execution across the focused groups; no redundant refresh timer suite was added. The parent's final complete suite and fresh phase verifier remain the phase acceptance gate.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 — Bug] Individual source/action links were narrower than the approved 44px target.**
- Found during: Task 2 actual Chromium matrix. A source ID `1` on `/records/portfolio/worker%3Aportfolio%3Aintraday` measured 7.109375px wide despite its 44px height at narrow widths.
- Fix: Existing link rule uses `min-width: var(--target-min)`. Approved tokens, navigation labels, themes and spacing are preserved; static contract also checks that minimum width.
- Files: `trading_bot/static/operator.css`, `tests/test_web_ui_contract.py`.
- Verification: All six destination/theme/width cases pass computed target, contrast and overflow checks; keyboard/native workflow cases also pass.
- Commit: `f89d257`. Parent explicitly extended ownership for this necessary contract fix.

**2. [Rule 1 — Bug] Static expanded state disagreed with the native mobile details menu.**
- Found during: Task 2 actual Space/Enter navigation. Closing the native menu left `aria-expanded="true"` fixed on its summary.
- Fix: Remove static attribute so no-JS native accessibility remains correct; the optional fixed script synchronizes the summary on initialization and actual details `toggle`.
- Files: `trading_bot/templates/operator/base.html`, `trading_bot/static/operator.js`, `tests/test_web_ui_contract.py`.
- Verification: Actual Chromium open/closed keyboard assertions and native no-JS navigation pass. `aria-labelledby` connected to an actual table caption is accepted as valid table semantics.
- Commit: `f89d257`. Parent explicitly approved the narrow repair.

No new endpoint, source schema, trading authority, network deployment or architecture was introduced.

## Issues Encountered

- Quota interruption delayed T3 completion; completed T1/T2 work was preserved and only the required T3 focus and retained screenshots were rerun on resume.
- The existing capability audit resolves relative filesystem events without `dir_fd`; the report test child changes cwd to its already pinned synthetic artifact root so legitimate openat/link operations are audited against that root. Source invariance and forbidden source writes remain enforced.
- Synthetic protected artifacts/config must satisfy the same 0700/0600 topology requirements as production. No source protection check was weakened.
- No authentication gate, owner credential request or package legitimacy substitution occurred.

## Documentation Lookup

Version-sensitive browser behavior was checked against official [Playwright emulation](https://playwright.dev/python/docs/emulation) and [downloads](https://playwright.dev/python/docs/downloads) documentation. The optional private example was checked against official [Waitress reverse proxy](https://docs.pylonsproject.org/projects/waitress/en/stable/reverse-proxy.html), [Caddy bind](https://caddyserver.com/docs/caddyfile/directives/bind), [Caddy TLS](https://caddyserver.com/docs/caddyfile/directives/tls) and [Caddy global options](https://caddyserver.com/docs/caddyfile/options) documentation. These references support instructions; actual private phone access was not exercised.

## Retained Synthetic Review Output

These three bounded overview examples contain test fixture data only and live outside repository/pytest cleanup:

- `/var/folders/xk/mkg191bs19q22t08wpm3b0k00000gn/T/phase14-review-xxercb1t/operator-overview-1280-light.png`
- `/var/folders/xk/mkg191bs19q22t08wpm3b0k00000gn/T/phase14-review-xxercb1t/operator-overview-390-dark.png`
- `/var/folders/xk/mkg191bs19q22t08wpm3b0k00000gn/T/phase14-review-xxercb1t/operator-overview-320-light.png`

## Known Stubs

None introduced. Synthetic fixtures deliberately cover missing and incomplete evidence as UNKNOWN. The runbook's reference to an INCOMPLETE zero placeholder describes that tested source condition, not an unfinished UI. Families without registered trusted proof intentionally remain unavailable/UNKNOWN; the runbook does not claim automatic proof provisioning.

## Remaining Human Checks and Phase Readiness

- Parent must record the final full-suite result after `17a1c0d` and run the fresh phase verifier. Shared STATE/ROADMAP/REQUIREMENTS/VALIDATION updates remain with the parent by the plan's ownership instruction.
- Owner optional actual mobile-data/private VPN/HTTPS/certificate/auth/session reachability and Korean safety/readability review remain unclaimed. The runbook gives concrete checks; screenshots enable bounded visual review without owner data.
- Local setup is documented but was exercised only in temporary synthetic protected storage. No owner DB/password configuration, persistent server, real notification, live broker/provider, freeze change or policy change was performed.

## Self-Check: PASSED

All ten deliverable/source files and this summary exist; all six RED/GREEN task commits resolve in repository history. The three retained screenshot files exist. Task commits contain no tracked deletions, `git diff --check` passed, and stub/threat scans found no unfinished functionality or new security surface outside the planned boundaries.
