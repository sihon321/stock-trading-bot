---
phase: 14-operator-dashboard-alerting
plan: "02"
subsystem: testing
tags: [flask, playwright, chromium, fixtures, capability-isolation, tdd]
requires:
  - phase: 14-01
    provides: Explicit owner authorization of seven exact package pins
  - phase: 14-03
    provides: Pure audit/replay/backtest saved-report contracts
provides:
  - Reviewed installed web/browser extras and separate runtime packaging declarations
  - Canonical temporary linked audit/portfolio/soak/controller and saved-result fixtures
  - Fresh-interpreter import/network/source-SQL/filesystem tripwires
  - Lazy injected-app loopback browser server and origin-bounded page fixtures
affects: [14-04, 14-05, 14-06, 14-07, 14-08, 14-09, 14-10, 14-11, 14-12, 14-13]
tech-stack:
  added: [Flask 3.1.3, Flask-WTF 1.3.0, waitress 3.0.2, Werkzeug 3.1.9, Jinja2 3.1.6, playwright 1.63.0, pytest-playwright 0.9.0]
  patterns: [synthetic test-owned evidence, injected fixed clock, bounded fake transport, fresh-process negative capability checks]
key-files:
  created: [tests/test_operator_setup.py, tests/operator_fixtures.py, tests/capability_probe.py, tests/test_operator_fixtures.py, tests/browser/conftest.py]
  modified: [pyproject.toml]
key-decisions:
  - Preserve all 65 active existing distribution versions using exact-extra installation and editable --no-deps installation.
  - Browser app construction requires explicit temporary settings and injected saved services; collection performs no app import.
  - Keep fixture preparation writers outside fresh-child capability verification.
patterns-established:
  - make_operator_sources returns resources, paths, fixed clock, stable IDs and isolated operational/artifact roots.
  - Standalone capability_probe accepts module/action and JSON registry without pytest or shared conftest.
requirements-completed: [FUT-03, UI-01, UI-02, OPSV-01]
coverage:
  - id: D1
    description: Exact dependency metadata, framework imports, real Chromium and absent-binary failure
    requirement: UI-02
    verification:
      - kind: integration
        ref: tests/test_operator_setup.py
        status: pass
    human_judgment: false
  - id: D2
    description: Attributed canonical sources, negative scenarios and repeatable saved report identities
    requirement: UI-01
    verification:
      - kind: unit
        ref: tests/test_operator_fixtures.py
        status: pass
    human_judgment: false
  - id: D3
    description: Fresh-child forbidden capability negatives and lazy local browser harness
    requirement: UI-02
    verification:
      - kind: integration
        ref: tests/test_operator_fixtures.py
        status: pass
    human_judgment: false
duration: 11min
completed: 2026-10-02
status: complete
---

# Phase 14 Plan 02: Operator Test Infrastructure Summary

**Verified Flask/Chromium prerequisites, canonical synthetic saved evidence and fresh-process capability tripwires now support downstream operator testing.**

## Performance

- Duration: approximately 11 minutes; completed 2026-10-02T00:55:21Z.
- Tasks: 2/2; six implementation/test/config files and this summary.
- Focused final feedback: 22 passed in 7.95s, with every test command below 60 seconds.

## Accomplishments

- Declared seven owner-verified pins, independent bot-web/bot-alerts scripts, template/static package data and the browser marker, retaining every production dependency declaration and bot script.
- Installed exact dependencies in workspace `.python-userbase` with the existing `/opt/homebrew/opt/python@3.14/bin/python3.14` interpreter (Python 3.14.3). Confirmed all 65 prior active distribution versions remain unchanged.
- Provisioned Chromium 153.0.8010.12 / Playwright build 1243 and its matching headless shell in the standard local Playwright cache. Actual headless launch and page rendering passed; forcing an absent browser directory failed with the installation instruction.
- Created linked account/target/snapshot/watch/order/fill evidence, all-date unresolved 000660 history, missing marks, incomplete zero cash, broken cross-store links and conflicting target variants. Byte/schema/table captures prove reads do not mutate source facts.
- Created canonical replay/backtest/shadow documents using existing synthetic test builders and a fake provider. Fixed source timestamps and test-local shadow UUID generation make repeated document content and identities identical within the same checkout.
- Verified fresh child processes reject credential-bearing imports/construction, network, source DELETE/DDL/ATTACH, writable source access and `.env` reads. Read-only reporting imports and source reads succeed without shared conftest. Exact explicitly allowed loopback binding succeeds; remote connection remains forbidden.
- Added lazy create_app import, injected-service requirements, a temporary loopback Waitress server with bounded cleanup, and a browser page restricted to its exact server origin.

## Task Commits

1. Task 1 RED: `acf0c21` — test(14-02): define reviewed web and browser prerequisites.
2. Task 1 GREEN: `9f56807` — feat(14-02): declare and provision isolated web browser extras.
3. Task 2 RED: `bee5b47` — test(14-02): specify isolated evidence and fresh process tripwires.
4. Task 2 GREEN: `7e1d633` — feat(14-02): add synthetic sources and fresh process capability harness.

Task 2 RED was prepared while Chromium finished provisioning; its GREEN followed Task 1 GREEN. Both tasks have their required RED-before-GREEN commits. Normal git hooks were retained; no deletions occurred.

## Actual Installation and Verification

All Python commands used `PYTHONUSERBASE="$PWD/.python-userbase"`.

1. `python3 -m pip install --user --dry-run -e '.[web,browser]'` — Homebrew PEP 668 blocked this before package installation.
2. `python3 -m pip install --user --break-system-packages --dry-run -e '.[web,browser]'` — successful resolution; revealed an unwanted python-dotenv upgrade from active 1.2.1 to declared 1.2.2.
3. Captured existing distribution metadata and constraints in `/tmp/gsd-14-02-installed.json` and `/tmp/gsd-14-02-constraints.txt`.
4. `python3 -m pip install --user --break-system-packages -c /tmp/gsd-14-02-constraints.txt 'Flask==3.1.3' 'Flask-WTF==1.3.0' 'waitress==3.0.2' 'Werkzeug==3.1.9' 'Jinja2==3.1.6' 'playwright==1.63.0' 'pytest-playwright==0.9.0'` — installed all seven exact extras and their required transitive dependencies.
5. `python3 -m pip install --user --break-system-packages --no-deps -e '.[web,browser]'` — successful editable registration and script generation without upgrading production requirements.
6. `python3 -m pip install --user --break-system-packages --no-deps certifi==2026.6.17` — restored the original active certifi after duplicate global/user metadata caused the constraint capture to select the lower global version. The corrected active baseline and all 65 versions then matched. Active python-dotenv remains 1.2.1; the pre-existing metadata discrepancy remains unchanged.
7. `python3 -m playwright install chromium` — Chromium and headless shell provisioned successfully; no separate Node installation or system Python package mutation.
8. `python3 -m pytest -q tests/test_operator_setup.py` — RED: three expected failures; GREEN: 3 passed in 4.08s.
9. `python3 -m pytest -q tests/test_operator_fixtures.py` — RED: missing helper collection failure; implementation iteration: 16 passed and one incorrect fixture-state expectation; corrected expectation to canonical FROZEN.
10. `python3 -m pytest -q tests/test_operator_setup.py tests/test_operator_fixtures.py` — 22 passed in 7.95s after deterministic-ID and server cleanup checks.
11. `git diff --check` and post-commit deletion/untracked checks — clean; only intentional plan files were staged.

## Downstream Interfaces

- `make_operator_sources(tmp_path, scenario="linked")` returns `OperatorSources.resources`, `.paths`, `.clock`, `.expected_ids`, `.account_hash`, `.operational_db`, `.artifact_root`; variants are `unknown_marks`, `incomplete_zero_cash`, `broken_links`, `scope_conflict`.
- FixtureResource has id/resource_id, path, owner, account_hash and target; convert to the production descriptor contract when 14-05 introduces it. Audit and portfolio owners share one canonical source file but have distinct registered IDs.
- `capture_sources(sources)` captures exact file bytes and, for SQLite, owner schema, table names and row contents. `FixedClock.advance(seconds=...)` and `FakeTransport(outcomes, max_calls=...)` support incident/session tests.
- `sources.probe_registry()` serializes source paths, authorized writable roots and expected IDs. Run `sys.executable tests/capability_probe.py --module MODULE --action import --registry JSON`; a named target callable receives that registry. Optional `allow_loopback=["127.0.0.1", PORT]` permits only that endpoint. Violations return code 23 with a bounded JSON diagnostic; no raw secret/error body is emitted.
- Browser tests override `operator_app_kwargs` with explicit `settings`, `evidence_service`, `report_service`, `alert_store`, `clock`. Fixtures expose `operator_app`, `operator_server`, `operator_page`; `serve_saved_app(app)` is also reusable. The app import occurs only during fixture use after 14-10 supplies it.

## Decisions Made

Use a split local install to respect the explicit requirement that production versions remain unchanged. Require injected saved collaborators rather than runtime fallback. The probe catches accidental capability acquisition and is a test harness, not an OS sandbox for hostile Python.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Adapted installation to Homebrew and existing metadata discrepancy.**
- Issue: PEP 668 prevented the planned user install; full editable dependency resolution would upgrade the pre-existing python-dotenv version.
- Fix: workspace-only `--user --break-system-packages`, exact extras plus editable `--no-deps`; restore original active certifi after duplicate distribution capture and verify the entire active baseline.
- Files: pyproject.toml, tests/test_operator_setup.py; committed in `9f56807`. No production pin was changed.

**2. [Rule 1 - Bug] Accounted for deliberate server shutdown socket race.**
- Issue: closing the test listener during select could emit EBADF from the server thread.
- Fix: bounded loop timeout, deliberate-stop signal, suppression only for teardown EBADF, propagation of other server failures and explicit thread termination verification.
- Files: tests/browser/conftest.py, tests/test_operator_fixtures.py; committed in `7e1d633`.

## Known Stubs and Remaining Verification

- Packaging declares future `trading_bot.web_cli:app` and `trading_bot.alert_cli:app`; runtime imports/help and packaged templates/static rendering are intentionally verified after their creation in 14-05/14-09/14-10 and installed-distribution checks in 14-12. This plan verifies metadata and framework/browser infrastructure, not nonexistent app execution.
- `operator_app_kwargs` deliberately fails unless overridden with saved services/settings. No product browser UI result is claimed; the lazy harness and a synthetic Flask loopback app were verified.
- Requirement IDs above identify supported prerequisite work. Phase 14 product acceptance and checkbox completion remain with the parent after downstream implementation.
- Full regression suite is delegated to the parent at the wave boundary. STATE/ROADMAP/REQUIREMENTS and validation tracking were preserved per the plan ownership contract.
- No authentication gate, external deployment, scheduler/VPN installation, owner database access, live KIS/LLM call or Discord notification occurred. No secret material was printed.

## Documentation Lookup

Context7 MCP and ctx7 CLI were unavailable. Official fallback references: [Playwright browser provisioning](https://playwright.dev/python/docs/browsers), [Waitress API](https://docs.pylonsproject.org/projects/waitress/en/stable/api.html), [Python sqlite3 authorizer](https://docs.python.org/3/library/sqlite3.html#sqlite3.Connection.set_authorizer). Server cleanup was additionally checked against the locally installed Waitress implementation and tested through a real loopback request.

## Self-Check: PASSED

- All six implementation/test/config files and this SUMMARY exist.
- RED/GREEN task commits `acf0c21`, `9f56807`, `bee5b47`, `7e1d633` exist in local history; no tracked files were deleted.
- Exact seven installed pins and preservation of all 65 active prior distribution versions were asserted.
- Final focused verification: 22 passed; no requested test was skipped.
- No goal-blocking implementation stubs or new production trust surface was introduced. The only listener is the temporary test-owned loopback server covered above.
