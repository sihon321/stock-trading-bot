---
phase: 14
slug: operator-dashboard-alerting
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-10-01
---

# Phase 14 — Validation Strategy

> Executed automated validation contract for approved UI-SPEC and all 33 tasks. Dependencies, fixtures, focused/browser/package checks and final full regression passed. Phase goal verification and manual-only usability/network checks are tracked separately; this is not a phase-completion claim.

## Test Infrastructure

| Property | Value |
|----------|-------|
| Framework | pytest 8.4.2; installed Flask 3.1.3 test client and pytest-playwright 0.9.0 / Playwright 1.63.0 |
| Config file | `pyproject.toml`; shared existing fixtures in `tests/conftest.py` |
| Current baseline command | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_reporting.py tests/test_soak_reporting.py tests/test_phase11_transitions.py tests/test_shadow_reporting.py` |
| Planned quick command | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_web_evidence.py tests/test_web_auth.py tests/test_web_security.py tests/test_web_reports.py tests/test_alert_store.py tests/test_alert_observer.py tests/test_web_capabilities.py` |
| Full suite command | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` |
| Planned browser command | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/browser/test_operator_ui.py --browser chromium` |
| Actual observation | Final full suite after verification fixes: 1418 passed in 336.19s; focused results and browser group splits below |

The planned commands require their listed modules and web/browser dependencies to be created first. Do not call a missing-test command and interpret collection failure as product verification. Do not skip browser coverage merely because backend tests pass. Browser installation and package verification follow the research artifact's explicit dependency setup protocol.

## Sampling Rate

- After each meaningful implementation task, run the relevant focused test module(s), including any directly affected existing regressions. Use targeted commands rather than repeatedly rerunning unrelated checks.
- At each plan wave boundary, run the full suite once after its final code change. Include dedicated browser verification when that wave changes user-visible behavior.
- Before phase verification, require the backend, fresh-process capability-negative and browser suites to pass with no suppressed missing dependencies.
- Target focused feedback latency: under 60 seconds. Actual latency is unmeasured until new tests exist; split slow integration/browser groups if needed without dropping required coverage.
- Tests use temporary frozen sources, controllable clocks and fake notifier/network collaborators. No authenticated KIS, live LLM, actual Discord delivery, private VPN deployment or real-account mutation is necessary for automated validation.

## Per-Task Verification Map

All 33 task IDs are explicit below. Each owning task creates its missing tests after setup dependencies before verification. 14-01-T1 additionally requires the precise blocking-human package verification from the research audit. Threat IDs refer to PLAN threat registers (ASVS 5.0.0 L1 intent; high findings block release). 14-13 owns the calibration/readiness/soak fresh-process gates before downstream reuse; 14-14 owns the former shared shell/CSS task, split into two focused tasks. Operational page wiring is renumbered from 14-10-T3 to 14-10-T2.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 14-01-T1 | 14-01 | 1 | UI-02 | T14-SC | Seven specific SUS package projects/versions human-verified before installation | blocking-human + plan structure | `node .codex/gsd-core/bin/gsd-tools.cjs query verify.plan-structure .planning/phases/14-operator-dashboard-alerting/14-01-PLAN.md` | Owner verified exact seven-package set; structural check passed | passed (human verification) |
| 14-02-T1 | 14-02 | 2 | FUT-03, UI-01, UI-02, OPSV-01 | T14-SC | Install reviewed extras and define separate runtime packaging — Metadata contains reviewed exact web/browser extras, separate CLI entry points, operator template/static package data and registered browser marker. | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_operator_setup.py` | Implemented; focused and integration regressions passed; see plan SUMMARY | passed |
| 14-02-T2 | 14-02 | 2 | FUT-03, UI-01, UI-02, OPSV-01 | T14-FIXTURES | Create isolated saved-source and fresh-process harnesses — Fixture variants preserve account/target/source ID joins, snapshot_id watch joins, unknown marks, incomplete zero cash, cross-store broken links, historic unresolved 000660 and canonical saved reports. | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_operator_fixtures.py` | Implemented; focused and integration regressions passed; see plan SUMMARY | passed |
| 14-03-T1 | 14-03 | 1 | UI-02, FUT-03 | T14-AUTHORITY, T14-INTEGRITY | Extract pure schema and replay contracts — Former replay import names resolve to identical DTOs/helpers and saved result IDs/UTF-8 canonical payloads match frozen vectors. | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_evidence_contracts.py tests/test_reporting.py tests/test_replay.py` | Implemented; temporary owner schemas and fresh-process probes verified | passed: 73 tests, 1.06s |
| 14-03-T2 | 14-03 | 1 | UI-02, FUT-03 | T14-INTEGRITY, T14-AUTHORITY | Extract backtest DTOs and saved ledger integrity helpers — Loading valid saved modeled results reconstructs existing stored ledger/accounting integrity and metrics without invoking run_backtest or execute_signal_cycle. | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_saved_backtest_evidence.py tests/test_backtest_reporting.py` | Implemented; frozen identity, forged ledger and fresh-process evaluator probes verified | passed: 20 tests, 2.28s |
| 14-04-T1 | 14-04 | 2 | FUT-03, UI-01, UI-02 | T14-INTEGRITY | Implement pure saved Shadow contracts and provenance verification — Valid registered saved fixtures with sufficient frozen baseline/ledger/source provenance pass without preparation, collect_shadow_snapshots, run_backtest, project_backtest_action or execute_signal_cycle. | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_saved_shadow_evidence.py` | Implemented; focused and integration regressions passed; see plan SUMMARY | passed |
| 14-04-T2 | 14-04 | 2 | FUT-03, UI-01, UI-02 | T14-INTEGRITY, T14-AUTHORITY | Wire saved report APIs while preserving strict execution safeguards — Saved load/render/write integrity uses the pure verifier; preparation/runner dispatch retains original stricter evaluator checks. | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_shadow_reporting.py tests/test_shadow_saved_capabilities.py tests/test_shadow_inputs.py` | Implemented; focused and integration regressions passed; see plan SUMMARY | passed |
| 14-05-T1 | 14-05 | 3 | UI-02 | T14-PATH, T14-PROXY, T14-DISCLOSURE | Create independent settings and operational schema ownership — No KIS/LLM credentials are required and forbidden trading fields are rejected; default loopback and explicit private-mode conditions are validated. | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_web_config.py tests/test_web_store.py` | Implemented; focused regressions passed; browser proof remains assigned to 14-12 | passed |
| 14-05-T2 | 14-05 | 3 | UI-02 | T14-AUTH | Implement operator password and absolute concurrent sessions — Correct password creates distinct PC/phone sessions; wrong/unknown account returns generic failure with bounded brute-force throttle. | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_web_auth.py` | Implemented; focused regressions passed; browser proof remains assigned to 14-12 | passed |
| 14-05-T3 | 14-05 | 3 | UI-02 | T14-AUTH, T14-PROXY | Wire separate local setup/reset and production serve commands — bot-web setup/reset hides password input and invokes only operational credential writes; serve defaults loopback and disables debug. | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_web_cli.py tests/test_web_auth.py` | Implemented; focused regressions passed; browser proof remains assigned to 14-12 | passed |
| 14-06-T1 | 14-06 | 4 | FUT-03, UI-01, UI-02, OPSV-01 | T14-EVIDENCE | Define source envelopes and whole-account reader — Complete single-snapshot totals/holdings link exactly; newest incomplete cash/total zero is unavailable and last complete snapshot remains labeled historical. | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_web_evidence.py -k 'account or snapshot or scope or missing or cache'` | Implemented; meaningful focused and full-wave regressions passed | passed |
| 14-06-T2 | 14-06 | 4 | FUT-03, UI-01, UI-02, OPSV-01 | T14-EVIDENCE, T14-DISCLOSURE, T14-QUERY | Implement bounded histories and source drill-downs — KST midnight maps UTC saved rows correctly; today/7/30/custom history does not hide active unresolved 000660. | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_web_evidence.py -k 'history or detail or unresolved or disclosure or pagination'` | Implemented; meaningful focused and full-wave regressions passed | passed |
| 14-06-T3 | 14-06 | 4 | FUT-03, UI-01, UI-02, OPSV-01 | T14-EVIDENCE | Derive worker/source health from observed lifecycle only — Iteration/snapshot joins work when cycle IDs differ; actual latest observation controls health, lease age is separate. | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_web_evidence.py -k 'worker or freshness or watch or transition'` | Implemented; meaningful focused and full-wave regressions passed | passed |
| 14-07-T1 | 14-07 | 5 | FUT-03, UI-01, UI-02 | T14-AUTHORITY | Build saved-only report catalog and metric/detail projections — Each supported family loads registered saved evidence and exposes exact metrics, excluded/unknown rows and stable source IDs without execution. | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_web_reports.py -k 'catalog or projection or unavailable or capability'` | Implemented; focused and wave regressions passed; actual browser proof remains 14-11/12 | passed |
| 14-07-T2 | 14-07 | 5 | FUT-03, UI-01, UI-02 | T14-EXPORT, T14-PATH | Create consistent bounded TXT/JSON/CSV artifacts — TXT/JSON/CSV share source selection, exact scope/IDs/denominators and uncertainty/advisory/model labels. | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_web_reports.py -k 'export or csv or artifact or bounds'` | Implemented; focused and wave regressions passed; actual browser proof remains 14-11/12 | passed |
| 14-08-T1 | 14-08 | 4 | OPSV-01, UI-02 | T14-ACK | Implement independently versioned incident and read state — Repeated source ID idempotent; distinct durable observation increments count and duration. | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_alert_store.py -k 'episode or revision or acknowledge or schema'` | Implemented; meaningful focused and full-wave regressions passed | passed |
| 14-08-T2 | 14-08 | 4 | OPSV-01, UI-02 | T14-DELIVERY | Implement delivery ownership and uncertain outbox accounting — Concurrent claimers cannot dispatch the same event twice; phase11 owned event links attempts and never queues a duplicate. | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_alert_store.py -k 'outbox or delivery or reminder or claim'` | Implemented; meaningful focused and full-wave regressions passed | passed |
| 14-08-T3 | 14-08 | 4 | OPSV-01, UI-02 | T14-DISCLOSURE | Extract pure bounded Discord transport with compatibility factory — Pure transport import does not import trading config/CLI/provider/broker; injected client retains bounded retry/timeout/fail-soft bool behavior. | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_notification_transport.py tests/test_notifier.py tests/test_phase11_transitions.py` | Implemented; meaningful focused and full-wave regressions passed | passed |
| 14-09-T1 | 14-09 | 5 | OPSV-01, UI-02 | T14-HEALTH | Detect stable operational incidents and positive recovery — Failures/stalls/unresolved orders/latches/divergences create stable subjects across changed iteration IDs and dates. | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_alert_detector.py` | Implemented; focused and wave regressions passed; actual browser proof remains 14-11/12 | passed |
| 14-09-T2 | 14-09 | 5 | OPSV-01, UI-02 | T14-DELIVERY, T14-AUTHORITY | Run durable independent foreground observer and CLI — watch runs without browser; once performs one bounded scan; status is credential-free and readonly; graceful stop durably releases observer ownership. | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_alert_observer.py tests/test_alert_cli.py` | Implemented; focused and wave regressions passed; actual browser proof remains 14-11/12 | passed |
| 14-10-T1 | 14-10 | 5 | FUT-03, UI-01, UI-02 | T14-AUTH, T14-CSRF, T14-PROXY | Create guarded Flask factory and authentication routes — Anonymous all protected route requests redirect/401 without evidence; stale/forged/revoked/12h sessions fail on server. | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_web_security.py tests/test_web_routes.py -k 'auth or login or logout or host or proxy or headers'` | Implemented; focused and wave regressions passed; actual browser proof remains 14-11/12 | passed |
| 14-10-T2 | 14-10 | 5 | FUT-03, UI-01, UI-02 | T14-XSS | Wire complete operational overview and durable record pages — Overview places unresolved orders/blocks→health→source times→account/holdings→activity; all-date 000660 survives date filters, using 14-14 shared shell. | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_web_routes.py tests/test_web_ui_contract.py` | Implemented; focused and wave regressions passed; actual browser proof remains 14-11/12 | passed |
| 14-11-T1 | 14-11 | 6 | FUT-03, UI-01, UI-02, OPSV-01 | T14-CSRF, T14-EXPORT | Implement saved validation pages and report generation/download — Replay/backtest/Shadow/Soak/calibration/readiness list/record/evidence render safely with exact source/metric denominator selectors and named unavailable variants. | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_web_report_routes.py tests/test_web_reports.py` | Implemented; backend and real Chromium refresh tests passed | passed |
| 14-11-T2 | 14-11 | 6 | FUT-03, UI-01, UI-02, OPSV-01 | T14-ACK, T14-CSRF | Wire active/history incident views and read-only acknowledgement — INFO/WARNING/CRITICAL active all-date and selectable history show occurrence/duration/source/read/recovery/delivery states separately. | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_web_alert_routes.py tests/test_web_security.py` | Implemented; backend and real Chromium refresh tests passed | passed |
| 14-11-T3 | 14-11 | 6 | FUT-03, UI-01, UI-02, OPSV-01 | T14-CLIENT, T14-XSS | Implement saved-only refresh, dirty-form preservation and expiry handling — Visible-page timers fetch every 30s, no overlap, abort after 10s; hidden tabs pause and resume with one read; manual button reuses read. | browser E2E | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/browser/test_operator_refresh.py --browser chromium` | Implemented; backend and real Chromium refresh tests passed | passed |
| 14-12-T1 | 14-12 | 7 | FUT-03, UI-01, UI-02, OPSV-01 | T14-AUTHORITY, T14-CSRF, T14-DISCLOSURE | Prove route security and fresh-process capability absence — Fresh child starts without shared conftest and importing/creating/rendering web/report/observer services triggers no forbidden import/constructor/socket/mutating-source operation. | adversarial integration/subprocess | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_web_capabilities.py tests/test_web_security.py tests/test_operator_integration.py` | Implemented; fresh-child, actual Chromium and installed-wheel checks passed | passed |
| 14-12-T2 | 14-12 | 7 | FUT-03, UI-01, UI-02, OPSV-01 | T14-CLIENT | Verify full desktop/mobile/system-theme operator flows in Chromium — 1280px desktop and 390px/320px mobile discover every required screen/list/detail/evidence and every export/read action in both system themes. | browser E2E | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/browser/test_operator_ui.py --browser chromium` | Implemented; fresh-child, actual Chromium and installed-wheel checks passed | passed |
| 14-12-T3 | 14-12 | 7 | FUT-03, UI-01, UI-02, OPSV-01 | T14-VPN | Document exact local/private operations and prove installed package resources — Wheel installed into temporary isolated target contains every native template/static resource and independent entry point imports without checkout/trading config. | adversarial integration/subprocess | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_web_packaging.py tests/test_web_cli.py tests/test_alert_cli.py` | Implemented; fresh-child, actual Chromium and installed-wheel checks passed | passed |

| 14-13-T1 | 14-13 | 2 | UI-02, FUT-03 | T14-AUTHORITY, T14-INTEGRITY | Separate calibration DTOs/policy catalog/judgments from replay evaluation; clean-child pure import/judgment gates and unchanged evaluate_variants execution API. | subprocess + regression | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_saved_calibration_evidence.py tests/test_calibration.py` | Implemented; focused and integration regressions passed; see plan SUMMARY | passed |
| 14-13-T2 | 14-13 | 2 | UI-02, FUT-03 | T14-AUTHORITY, T14-INTEGRITY, T14-JUDGMENT | Rewire calibration/readiness to pure evidence/query contracts; separate per-family clean-child import/build/render gates preserve canonical IDs, exact denominators, nine checks and source bytes. | subprocess + regression | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_saved_calibration_evidence.py tests/test_calibration_reporting.py tests/test_promotion_readiness.py tests/test_report_cli.py` | Implemented; focused and integration regressions passed; see plan SUMMARY | passed |
| 14-13-T3 | 14-13 | 2 | UI-02, FUT-03 | T14-AUTHORITY, T14-INTEGRITY | Remove mutable soak/controller/store imports; shared query-schema aliases retain exact owner/version/link checks and UNKNOWN, with clean-child load/build/render and unchanged-source proof. | subprocess + regression | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_saved_soak_evidence.py tests/test_soak_reporting.py` | Implemented; focused and integration regressions passed; see plan SUMMARY | passed |
| 14-14-T1 | 14-14 | 3 | FUT-03, UI-01, UI-02 | T14-XSS, T14-CLIENT | Shared Korean semantic shell/macros preserve all 17 destinations, four groups, mobile evidence/actions and escaped synthetic DTO rendering independently of routes. | render/contract | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_web_ui_contract.py -k 'shell or navigation or macro or escape'` | Implemented; focused regressions passed; browser proof remains assigned to 14-12 | passed |
| 14-14-T2 | 14-14 | 3 | FUT-03, UI-01, UI-02 | T14-CLIENT | Exact native system light/dark tokens, numeric/text/icon/focus and responsive rules; actual computed browser proof remains 14-12. | render/contract | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_web_ui_contract.py -k 'theme or responsive or tokens'` | Implemented; focused regressions passed; browser proof remains assigned to 14-12 | passed |

Run all commands above with the repository's `PYTHONUSERBASE="$PWD/.python-userbase"` prefix unless dependencies are deliberately installed into a reviewed isolated environment. Never silently point tests at the owner's live evidence stores.

## Wave 0 Requirements

Dependency graph: Wave 1 = 14-01 (package gate), 14-03 (pure core/query contracts); Wave 2 = 14-02 (after 01), 14-04 (after 03), 14-13 (after 03; saved soak/calibration/readiness boundaries); Wave 3 = 14-05 (after 02/03), 14-14 (after 02; shared shell/CSS); Wave 4 = 14-06 (after 02/03/04/05/13), 14-08 (after 02/03/05); Wave 5 = 14-07 (after 04/05/06/13), 14-09 (after 05/06/08), 14-10 (after 05/06/08/14); Wave 6 = 14-11 (after 07/09/10); Wave 7 = 14-12 (after 11). Same-wave files have separate ownership. Test helpers in 14-03/04/13 use existing pytest/stdlib child probes directly; Flask/browser fixture infrastructure is owned by 14-02 and blocks downstream UI tests. 14-13 per-family fresh-import/build/render gates must pass before 14-06/07 consume those saved builders; 14-12 provides the final full-route integration matrix. 14-03 additionally validates shared query-schema/version declarations against temporary owner-migrated fixtures to detect drift without importing mutable owners in saved children.

Explicit setup commands after 14-01 package verification: `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pip install --user -e '.[web,browser]'`; `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m playwright install chromium`. No installation has been performed by planning. Browser tests requested by their plan fail explicitly if infrastructure is absent. Each new test file is created by its owning task; empty stubs do not count as proof.

- [x] All 33 mapped tasks implemented and verified; dependency, fixture and browser setup completed.
- [x] Owner-reviewed exact web/browser dependencies installed under the local setup protocol.
- [x] Create isolated saved audit/portfolio/soak/replay/backtest/shadow fixtures with exact linked IDs, schema ownership, account/target scope, positive and deliberately broken provenance, missing sources and incomplete placeholders.
- [x] Provide fake clock, temporary operational/session/alert store and fake transport fixtures independent of credential-bearing production setup.
- [x] Add meaningful tests in all listed modules alongside the implementation that satisfies them; empty test stubs do not establish coverage.
- [x] Build the fresh-process capability harness without imports from the credential-bearing shared production conftest. Check constructor attempts and filesystem authority as well as module names.
- [x] Register the browser marker and isolated local-server harness; provision a Chromium browser through the reviewed browser setup path. Backend success is not a substitute for browser verification.
- [x] Execute setup and measure quick-suite/browser latency; document actual commands/results without treating planned tests as passes.

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Owner's optional private VPN/HTTPS mobile access | FUT-03, UI-02; D-05 | Actual network/topology and phone are outside frozen local tests; no VPN vendor chosen | After explicit owner configuration, verify access from phone mobile data through private VPN, authentication, HTTPS/cookie behavior, concurrent PC session, logout and expiry. Confirm default remains local and no public access is introduced. |
| Korean visual usability | UI-01; D-01–D-04 | Browser checks automate behavior/layout but the owner judges readability | Review safety-first overview, four navigation groups, mobile details and system light/dark themes with realistic saved evidence. Unresolved warnings, UNKNOWN and age must be understandable without color alone. |

Optional private-network acceptance is distinct from automated application correctness. No manual check authorizes KIS/LLM calls, notification sending, policy writes or a real-money transition.

## Validation Sign-Off

- [x] Every task has automated verification with explicit test creation/setup dependencies; package task additionally has a blocking-human gate.
- [x] Sampling continuity: every implementation task has focused verification.
- [x] Setup dependencies cover missing frameworks/fixtures/browser; each owning task creates its tests before verification.
- [x] No watch-mode test commands.
- [x] Actual task/plan/wave and threat IDs replace pending mapping references.
- [x] Focused feedback latency target is measured and met or a documented split is used.
- [x] FUT-03/UI-01/UI-02/OPSV-01 and D-01 through D-16 have concrete task coverage; multi-source audit is in 14-12-PLAN.md.
- [x] nyquist_compliant and wave_0_complete now include actual setup and all task checks; focused browser groups keep feedback under 60s, while the full suite intentionally includes every regression.

**Approval:** Plans and verification mapping passed independent checking before execution. Implementation results are tracked below; phase-wide product verification remains pending. No product verification was run by the planner.

## Execution Observations — 2026-10-02

- Independent plan verification passed before execution: 14 plans, 33 tasks, 7 waves; no blockers or warnings.
- 14-03 completed both tasks with RED/GREEN commits and committed self-check. Integrated saved-evidence and engine compatibility selection: 66 passed.
- Parent full regression after 14-03: `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` — 999 passed in 38.06s.
- Schema drift gate found no drift; codebase drift gate skipped because no structure map exists.
- 14-01 remains at its explicit seven-package human verification checkpoint. No package was installed. Wave 1 and Phase 14 remain incomplete; later setup, browser checks and phase verification are pending.

### Checkpoint Resolved and Wave 2 Completed — 2026-10-02

- Owner response `1` explicitly verified all seven listed package versions and authorized local installation; 14-01 SUMMARY records the exact set.
- 14-02 installed the seven reviewed pins and Chromium, preserving all 65 existing active dependency versions. Focused infrastructure tests: 22 passed in 7.95s.
- 14-04 saved Shadow integrity and compatibility selection: 68 passed in 27.31s. Insufficient registered provenance returns typed unavailable rather than a fabricated successful verdict.
- 14-13 pure calibration/consumer/soak selections: 24, 48 and 44 passed respectively.
- Full collection exposed a browser/root conftest namespace collision; adding the browser test package fixed collection without changing existing test imports.
- Full regression after Wave 2 and the collection fix: `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` — 1071 passed in 58.46s.
- Completed plans: 14-01, 14-02, 14-03, 14-04, 14-13 (5/14). Wave 3 implementation and phase-wide browser/product verification remain pending.

### Wave 3 Completed — 2026-10-02

- 14-05 operational settings/store/auth/CLI focused suite: 37 passed in 1.58s; real operator provisioning and persistent server operation remain owner setup.
- 14-14 shared Korean shell, 17 destinations and approved native CSS contract: 40 passed in 1.41s; actual computed browser verification remains 14-12.
- Parent full regression after Wave 3: 1148 passed in 62.13s. Focused selections remain under 60s; the full wave suite is intentionally broader.
- Schema drift gate passed; advisory codebase drift skipped because no structure map exists.
- Completed plans: 14-01, 02, 03, 04, 05, 13, 14 (7/14); phase-wide verification remains pending.

### Wave 4 Completed — 2026-10-02

- 14-06 read-only account/history/evidence/worker/source API: 16 passed in 7.19s, including late backdated saved-record detection and durable-ID replay contract.
- 14-08 incident/acknowledgement/outbox/transport suite: 38 passed in 0.71s; notifier and Phase11 compatibility selection: 27 passed in 0.62s. Source databases and live endpoints were not used.
- A provider usage-limit interruption stopped 14-08 after T1. The owner requested restart; current usage allowed execution, so T2/T3 resumed while preserving completed T1 commits.
- Parent full regression after Wave 4: 1198 passed in 69.80s. Schema drift passed; advisory codebase drift skipped for absent structure map.
- Completed plans: 9/14. Wave 5 report/observer/page implementations and phase-wide browser/product verification remain pending.

### Wave 5 Completed — 2026-10-02

- 14-07 saved report/export tests and existing pure report gates: 90 passed in 19.15s (49 new report tests).
- 14-09 detector/foreground observer/source/store integration: 71 passed in 10.07s. Required saved evaluation, transition subject and positively verified freeze-release facts were added to the source projection; no source mutation authority.
- 14-10 auth/routes/UI/evidence: 114 passed in 18.27s, plus one focused cursor Back regression passed in 1.18s after necessary fixes. Saved safety blocks are displayed before observer startup; unknown target scope is rejected.
- Narrow source/macro contract gaps discovered by integration were fixed under explicit parent ownership delegation, preserving immutable source schemas and native UI tokens.
- Parent full regression after Wave 5: 1335 passed in 92.45s. Schema drift passed; advisory structure-map gate skipped.
- Completed plans: 12/14. Report/incident pages, real Chromium refresh and final product/capability/package verification remain pending.

### Wave 6 Completed — 2026-10-02

- 14-11 report/service/routes: 62 passed in 22.74s; alert/security: 42 passed in 6.00s; final backend report/alert/security/routes: 73 passed in 23.04s.
- Actual Chromium refresh suite: 12 passed in 16.39s, including virtual cadence/timeout, hidden-tab resume, dirty note/focus/disclosure/selection/scroll, source failure retention, expiry/restore/no-POST-replay, real format downloads and JavaScript-disabled native actions.
- First full wave regression found four integration-test failures: an independent Playwright sync launch nested under the browser plugin session loop, and three old XSS assertions rejecting the newly fixed packaged script. A fresh-process real Chromium launch and exact fixed-script allowlist preserved the negative security checks. Related selection: 68 passed in 19.11s; fix commit cee28cb.
- Parent full regression after the integration fix: 1378 passed in 122.58s. Schema drift passed; structure-map advisory skipped.
- Completed plans: 13/14. Final fresh-process capability, all-screen/theme/mobile/browser, installed-package and human usability verification remain pending.

### Wave 7 and Final Regression Completed — 2026-10-02

- 14-12 fresh-process capability/security/integration: 48 passed in 26.53s. All eight AVAILABLE report families and three formats, views/details/APIs/ack/observer/CLI were exercised under before-import traps and per-action source inventories.
- Actual Chromium all-screen suite: all 16 cases passed across 17 destinations, detail/evidence/metric selectors, 1280/390/320 widths, both system themes, keyboard/zoom/contrast, no-JS actions/downloads and independent sessions. Focused groups were split under 60s (largest measured group 59.58s); existing refresh selection: 12 passed in 15.79s.
- Actual computed UI defects were fixed narrowly: tiny link target minimum width and a static expanded-state override on the native menu. Approved colors/navigation/tokens remain unchanged; UI contract: 53 passed in 2.73s.
- Offline wheel/isolated installed runtime/runbook and independent CLI selection: 27 passed in 3.45s. No checkout fallback, network or owner deployment. Optional private HTTPS and readability remain human-only checks.
- 14-12 resumed after a second provider quota interruption once current usage allowed execution, preserving completed T1/T2 commits. All 14 SUMMARY files are committed.
- Parent final full regression: PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q — 1412 passed in 320.01s, including all browser cases and all 37 extant test-file references from prior phase verifications.
- Wave drift checks passed (structure-map advisory skipped). execute:post and verify:post have no active review/security hooks; their gates were evaluated, with no bypass.
- All 14 plans and 33 automated task checks complete. Fresh goal-backward verification is next; Phase 14 remains in progress until its result and any required human acceptance are handled.

### Independent Verification Gaps Repaired — 2026-10-02

- Initial independent verification at `9ac4f28` found G-1 (global LIMIT before registered subject/CRITICAL filtering and mismatched drilldown) and G-2 (saved refresh left the safety header stale), score 34/36. Four added focused tests reproduced the defects; RED `1af0c88`. Initial verification is preserved in commit `4c7fa73`.
- Necessary narrow follow-up `e457357` applies complete registered resource/account/target/active/severity selection before COUNT and bounded page LIMIT, uses the same selector for header drilldown and pages, and consumes updated header text/link on saved refresh/actions. Unavailable storage stays UNKNOWN; source databases and trading authority remain untouched.
- Related routes/security/UI/Chromium: 153 passed in 50.23s. Additional boundary selection: 7 passed in 6.91s, covering 101 constituents, newer registered/unregistered/foreign subjects, manual and automatic state changes, scope change and preserved dirty drafts.
- Final full regression after the last change: `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` — **1418 passed in 336.19s**. This includes the 37 extant prior-phase test references and all Chromium cases. Schema drift still has no drift; execute:post/verify:post have no active hooks.
- All implementation plans remain executed; independent gap re-verification and required human acceptance remain the phase completion gates.

### Re-verification and Human Acceptance Gate — 2026-10-02

- Independent re-verification at `a1fc483`: **36/36 VERIFIED, gaps: [], human_needed**. Both G-1/G-2 resolved; independent narrow boundary/Chromium execution: **7 passed in 7.12s**.
- Canonical `verification.status` confirms human_needed. Required Korean visual usability and conditionally configured actual private phone access are persisted in 14-UAT.md. Optional unconfigured private deployment is not an implementation gap.
- Phase checkbox, requirement completion and phase advance remain pending until UAT acceptance; the 14/14 executed plans and 1418-test automated result do not substitute for that human check.

### UAT Accepted and Phase Completed — 2026-10-03

- Owner accepted Korean visual usability. The owner selected Tailscale for future external phone/Mac access; the original conditional device test applies only once that private HTTPS deployment is configured. It is preserved outside the current applicable UAT scope, without claiming an actual connection PASS.
- Applicable UAT: 1 passed, 0 issues, 0 pending/blocked. Canonical verification is passed; the shared `phase uat-passed 14 --require-verification` predicate returns passed=true and blockers=[]. The current-phase artifact scan has no open UAT, verification or context items.
- `phase.complete 14` marked the roadmap complete on 2026-10-03. Legacy current-milestone filtering returned no successor and missed future traceability; parent reconciled the documented next Phase 15 and the four Phase 14 requirement records. Phase 9 elapsed-day acceptance remains independent, and no Phase 15 work or external deployment was started.
