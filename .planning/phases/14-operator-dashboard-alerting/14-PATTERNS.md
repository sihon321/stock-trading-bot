# Phase 14: Operator Web UI, Dashboard & Alerting - Pattern Map

**Mapped:** 2026-10-02
**Files classified:** 42 named paths and 3 frontend resource families (proposed, not an implementation manifest).
**Analogs found:** 37 / 45 targets; 17 exact existing-file matches, 20 role/data-flow matches, 8 without a close analog.

## File Classification

Paths below are relative to the repository; comma-separated names represent separately classified files.
New backend names come from RESEARCH.md; compatibility edits and regression files are implied by its import boundary.

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `trading_bot/evidence_contracts.py` | model/config | transform | `audit_models.py`, schema constants in `sqlite_audit.py`/`portfolio_store.py` | role-match |
| `trading_bot/replay_evidence.py` | model/utility | transform | `replay.py:ReplayManifest, canonical_json_bytes, compute_result_id` | role-match |
| `trading_bot/backtest_evidence.py` | model/service | transform | `backtest_engine.py:BacktestRun`; `backtest_reporting.py:_validate_run` | role-match |
| `trading_bot/shadow_evidence.py` | model/service | transform | `shadow_runner.py:ShadowExecution`; `shadow_reporting.py:_checked_result` | role-match |
| `trading_bot/web_config.py` | config | file-I/O | `config.py:ReportSettings` | role-match |
| `trading_bot/web_cli.py` | controller | request-response | `report_cli.py:resolve_report_audit_db_path, parse_kst_date` | role-match |
| `trading_bot/web_app.py` | controller/route | request-response | None: new Flask factory/routes | none |
| `trading_bot/web_evidence.py` | service | request-response | `reporting.py:ReadOnlyAuditRepository`; `soak_reporting.py:ReadOnlySoakRepository` | role-match |
| `trading_bot/web_models.py` | model | transform | `shadow_models.py:Frozen`; `audit_models.py:TransitionObservation` | role-match |
| `trading_bot/web_auth.py` | middleware/service | request-response | None: no application session/password/CSRF implementation | none |
| `trading_bot/web_store.py` | store | CRUD/event-driven | `soak_store.py:_write, append_campaign_event` | role-match |
| `trading_bot/web_reports.py` | service | file-I/O/transform | `reporting.py:load_replay_results`; saved backtest/shadow loaders | role-match |
| `trading_bot/alert_models.py` | model | event-driven | `audit_models.py:OperationalSeverity, TransitionObservation` | role-match |
| `trading_bot/alert_store.py` | store | event-driven | `portfolio_store.py:record_transition_state, record_transition_notification` | role-match |
| `trading_bot/alert_observer.py` | service | batch/event-driven | `intraday.py:TransitionEvidenceGuard` (transport/evidence separation only) | flow-match |
| `trading_bot/alert_cli.py` | controller | request-response | `report_cli.py` (independent entry-point orchestration) | role-match |
| `trading_bot/notification_transport.py` | service | request-response | `notifier.py:DiscordNotifier, NoopNotifier` | role-match |
| `trading_bot/reporting.py`, `trading_bot/replay.py` | service/model | transform/file-I/O | Same files; extract pure contracts, retain exports | exact |
| `trading_bot/backtest_engine.py`, `trading_bot/backtest_reporting.py` | service/model | batch/transform | Same files; separate DTOs/offline validation | exact |
| `trading_bot/shadow_reporting.py`, `trading_bot/shadow_runner.py`, `trading_bot/shadow_inputs.py` | service/model | batch/transform | Same files; isolate saved validation from evaluation | exact |
| `trading_bot/notifier.py` | service | request-response | Same file; retain factory compatibility | exact |
| `trading_bot/sqlite_audit.py`, `trading_bot/portfolio_store.py` | store/config | event-driven | Same files; pure schema ownership exports if extraction requires edits | exact |
| `trading_bot/templates/operator/*` | component | request-response | `14-UI-SPEC.md` semantic Jinja screen contract | none |
| `trading_bot/static/operator.css` | component | transform | `14-UI-SPEC.md` native tokens/system themes | none |
| `trading_bot/static/operator.js` | component | event-driven | `14-UI-SPEC.md` progressive refresh contract | none |
| `pyproject.toml` | config | file-I/O | Same file, scripts lines 28–32 | exact |
| `docs/operator-runbook.md` | utility/documentation | file-I/O | Same runbook; setup/private access/observer operations | exact |
| `tests/test_web_evidence.py`, `tests/test_web_reports.py` | test | request-response/file-I/O | `test_reporting.py`, `test_report_cli.py`, saved-result tests | role-match |
| `tests/test_web_auth.py`, `tests/test_web_security.py` | test | request-response | None: new Flask security/session harness | none |
| `tests/test_alert_observer.py`, `tests/test_alert_store.py` | test | event-driven | `test_phase11_transitions.py`, `test_notifier.py` | role-match |
| `tests/test_web_capabilities.py` | test | request-response | `test_report_cli.py:test_calibration_terminal_file_and_inputs_are_byte_identical` | flow-match |
| `tests/browser/test_operator_ui.py` | test | event-driven | None: new local browser harness | none |
| `tests/test_reporting.py`, `tests/test_backtest_reporting.py`, `tests/test_shadow_reporting.py`, `tests/test_notifier.py`, `tests/test_phase11_transitions.py` | test | transform/event-driven | Same files; extraction regressions | exact |

## Pattern Assignments

### Evidence readers: `web_evidence.py`, pure schema contracts

Copy `reporting.py:ReadOnlyAuditRepository._connect` lines 306–312:
```python
connection = sqlite3.connect(
    f"{self._path.as_uri()}?mode=ro", uri=True, isolation_level=None
)
connection.row_factory = sqlite3.Row
connection.execute("PRAGMA query_only=ON")
return connection
```
Copy `_validate_schema` lines 315–325 and `load_period` lines 337–355: validate supported version/capabilities, BEGIN, parameterized values, rollback on error and always close.
Use bounded keyed queries instead of loading an entire period every 30 seconds; never return a mutable connection to routes.
`soak_reporting.py:ReadOnlySoakRepository.__init__` lines 187–195 rejects path/inode aliases; extend that check to writable operational/artifact paths.
Its `transactions` lines 256–286 opens/validates each owner independently and explicitly disclaims cross-store atomicity.
Copy source-link checks from `_valid_primary_reference` lines 396–408 and `_valid_snapshot_reference` lines 411–445; missing links stay UNKNOWN.
Primary audit `user_version` and Phase 11 portfolio metadata are separate capabilities. Copy the read query from `portfolio_store.py:portfolio_schema_version` lines 172–175:
```python
row = conn.execute(
    "SELECT version FROM portfolio_schema_metadata WHERE owner='phase11'"
).fetchone()
return int(row[0]) if row else 0
```
Keep version/table/column declarations in capability-free contracts. Do not import portfolio collection, connect/migrate functions or mutation leases into readers.
Portfolio totals/holdings use one complete snapshot; incomplete zero placeholders are UNKNOWN. Target requires attributable run/resource scope; an account hash cannot establish mock/real.
Join watch facts through `snapshot_id` where outer watch cycle and iteration IDs differ; expose actual iteration age separately from lease age.

### Frozen DTOs: `web_models.py`, `alert_models.py`, extracted contracts

Copy validation style from `shadow_models.py:Frozen` lines 72–81:
```python
class Frozen(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)

    @model_validator(mode='after')
    def validate_text_and_dates(self):
        for name in type(self).model_fields:
            value = getattr(self, name)
```
Retain aware timestamps/UTC normalization and UTF-8 bounds (lines 79–89); use strict numeric fields and nullable unknown values.
`audit_models.py:TransitionObservation.__post_init__` lines 236–251 checks severity, aware time, bounded identity/detail and freezes MappingProxyType.
Presentation DTOs explicitly allowlist fields; never wholesale-dump source models containing prompts, raw_output, embedded documents or tokens.
Carry resource/schema/record IDs, target/provenance, observation/query times, completeness and exact numerator/denominator selections.

### Saved reports and compatibility: `web_reports.py`, `*_evidence.py`, existing exporters

`reporting.py:_strict_json` lines 598–619 checks regular/non-symlink/bounded JSON; `_load_replay_result` lines 727–768 validates identity, manifest, funnel and disclaimer.
Copy identity validation from `_load_replay_result` lines 736–739:
```python
evidence = _exact_keys(document["evidence"], _REPLAY_EVIDENCE_FIELDS, "replay evidence")
expected_identity = hashlib.sha256(canonical_json_bytes(evidence)).hexdigest()
if document["result_id"] != expected_identity:
    raise ValueError("replay result identity mismatch")
```
`load_replay_results` lines 771–786 deduplicates stable IDs without losing source attribution. Preserve canonical output order and `replay.py:canonical_json_bytes` lines 71–79.
Move replay DTOs/hash helpers from `replay.py` into `replay_evidence.py`; preserve former import names with re-exports. Leave run/build-manifest execution outside the web graph.
Move `backtest_engine.py:DecisionEvidence, BacktestRun` lines 26–54 into `backtest_evidence.py`; retain field types/defaults and original exports.
`backtest_reporting.py:load_backtest_result` lines 210–220 validates the saved model and recomputes evidence/metrics with `build_backtest_result`; preserve checks in a capability-free verifier.
Move `shadow_runner.py:ShadowExecution` lines 14–21 into pure contracts and preserve exports; remove provider/journal imports from saved-result validation.
**Critical boundary:** `shadow_reporting.py:build_shadow_result` lines 61–78 calls `shadow_inputs.validate_shadow_preparation`; `_validate_frozen_document` lines 119–130 calls `collect_shadow_snapshots`, which evaluates a backtest.
Therefore importing fewer modules or avoiding provider calls alone is insufficient: design saved-evidence-only integrity validation without replay/backtest/shadow execution, retaining attribution/hash/metrics/journal/baseline checks and forged-evidence rejection. Unsupported validation must make the resource unavailable, never silently bypass a check.
Preserve stored result/manifest hashes and canonical bytes. `backtest_engine.py:code_identity` lines 76–82 hashes a named source set; `shadow_inputs.py:shadow_code_identity` lines 94–98 hashes sorted Python sources.
Extraction changes source bytes, so newly generated code hashes can legitimately change. Preserve documented hash algorithms and old saved identities; cover moved behavior in future source hashing without rewriting historical evidence or equating old/new hashes.
Writers: prefer `backtest_reporting.py:_write_evidence_bytes` lines 235–260 (fsync then no-overwrite `os.link`) over `report_cli.py:write_report_text` lines 112–139 (`os.replace`). Reuse only pure path/byte helpers, not report CLI imports.
Registered output IDs and operational artifact roots replace request-supplied paths; TXT/JSON/CSV retain scope/IDs/unknowns, and CSV cells need spreadsheet-safe escaping.

### Operational persistence: `web_store.py`, `alert_store.py`, observer

Copy append-only event signatures from `soak_store.py:append_campaign_event` lines 597–610 and transactional rollback from `_write` lines 308–315:
```python
try:
    cursor = conn.execute(sql, values)
    conn.commit()
    return int(cursor.lastrowid)
except Exception:
    conn.rollback()
    raise
```
Independently version operational storage; only its own connectors may create/migrate it. Store sessions/revocations/actions, episodes/revisions/read acknowledgements/cursors, observer health and outbox/attempts there.
`portfolio_store.py:record_transition_state` lines 389–493 supplies BEGIN IMMEDIATE, appended observations and atomic projection updates; `record_transition_notification` lines 510–549 supplies durable attempt bookkeeping.
Do not reuse state_identity as a permanent episode ID: it includes normalized state (`audit_models.py:canonical_transition_identity`, lines 203–222), and an old identity suppresses notifications (`portfolio_store.py`, lines 494–495).
New-source IDs drive counts; worsening and recurrence create unread revisions/episodes. Reading never sets recovery; recovery needs positive same-subject durable evidence.
Phase 11 owns existing occurrence/change/recovery sends. Link its attempts; missing attempts mean UNKNOWN. Observer owns new derived alerts and unread CRITICAL reminders every 30 minutes only.
Commit claim/outbox before sending; restart after uncertain delivery stays UNKNOWN. No exactly-once guarantee or automatic assumption that an unknown attempt was unsent.
`intraday.py:TransitionEvidenceGuard.notify` lines 70–83 separates soft transport failure from mandatory evidence failure; preserve that trading contract without importing its mutation/broker module into the observer.
No foreground non-trading observer lifecycle analog exists. Implement the research watch/once/status contract with injected clock/transport, durable start/heartbeat/stop/ownership, bounded scans and graceful stop.

### Transport and config/CLI separation

Extract `notifier.py:DiscordNotifier` lines 41–116 to `notification_transport.py`; keep its injected client, redacted repr, timeout and bounded retries. Copy `send` lines 77–82:
```python
try:
    self._post_with_retry(summary)
    return True
except Exception:
    logger.warning("discord notification failed after bounded retry")
    return False
```
Keep `notifier.py:build_notifier` lines 168–179 compatible for trading callers; only observer settings own Discord secrets. The web process has no notification credentials/client.
`config.py:ReportSettings` lines 13–22 demonstrates a typed credential-free config; define WebSettings separately rather than inheriting Settings or importing live config through notifier.
Copy `report_cli.py:resolve_report_audit_db_path` lines 61–67 (injected lightweight settings) and `parse_kst_date` lines 49–58 (strict grammar), not its report/evaluation imports or raw exception diagnostic.
`web_cli.py` handles hidden local credential setup/reset and serve; `alert_cli.py` handles independent foreground monitor commands. Routes call bounded services, never `trading_bot.cli:build_runtime`.
`pyproject.toml` lines 28–32 supplies script/package discovery style; add separate entry points, researched extras and explicit template/static package data, followed by install-resource smoke validation.

## Shared Patterns

- **Auth/error handling:** no existing auth analog. Use RESEARCH.md session/CSRF contract; all routes and exports validate server-side sessions, exactly-12h absolute expiry, resource authorization and no-store. Safe diagnostic codes replace `report_cli.py:_diagnostic` raw exception strings.
- **Disclosure:** `audit_models.py:sanitize_detail` lines 151–169 rejects forbidden key shapes but cannot detect secrets inside allowed strings. Add allowlisted bounded plain-text projection, Jinja autoescape and secret-sentinel tests; do not treat that helper as sufficient web sanitization.
- **Freshness:** last successful complete source observation stays visible with query failure/stale state; source time never changes merely because a browser poll succeeds. Established expected workers use max(180s, 3 × documented cadence); otherwise UNKNOWN.
- **Tests:** `test_reporting.py:test_readonly_repository_refuses_missing_and_unsupported_databases` lines 506–516 proves reads do not create paths; extend to SQL/schema/data snapshots and every supported web/observer action.
- **Integrity:** `test_backtest_reporting.py:test_tampered_or_forged_evidence_rejected` lines 22–26 rehashes fabricated evidence and still expects rejection; `test_shadow_reporting.py:test_saved_result_recomputed_and_outputs_are_idempotent` lines 43–54 checks tampered metrics, conflicts and symlinks. Keep these after extraction, plus tripwires forbidding evaluation calls during saved reads.
- **Capabilities:** `test_report_cli.py` lines 285–295 compares input bytes before/after; line 334 onward checks absent live seams. Extend with fresh subprocess import/constructor/socket/mutating-SQL tripwires. `tests/conftest.py` imports Settings, so the child harness must not depend on its loaded modules.
- **Alerts:** `test_phase11_transitions.py` lines 38–52 tests durable repeated observations/one initial send; lines 104–132 tests fail-soft transport versus fail-closed evidence. Add recurrence/revision conflicts, source-ID idempotence, reminder boundaries and positive-recovery cases with controllable time.
- **Transport:** `test_notifier.py:_FakeWebhookClient` lines 14–29 and `test_fail_soft` lines 89–105 provide injected deterministic transport, bounded attempt count and credential redaction.

## No Analog Found

Eight targets lack a close analog: `web_app.py`, `web_auth.py`, three frontend families, `test_web_auth.py`, `test_web_security.py`, `tests/browser/test_operator_ui.py`.
Follow RESEARCH.md Flask factory/test-client/CSRF/session contract and approved `14-UI-SPEC.md`; do not invent React components or a Node build.
Templates share semantic Korean shell/nav/badges/forms/pagination and list → record → sanitized evidence links. Mobile preserves actions/exports; native CSS tokens follow system themes and 320px/44px accessibility limits.
Native JS progressively enhances functional server forms/routes: visible-tab 30s reads, no overlap, 10s timeout, last-success retention, dirty-form/focus/selection preservation and session-expiry hiding.
Browser tests use local saved fixtures/fake transport at desktop/mobile sizes, both themes, keyboard/zoom, failure/expiry/acknowledgement and all export paths.

## Metadata

**Scope:** `trading_bot/`, targeted existing tests, `pyproject.toml`, phase context/research/UI contract and project instructions.
**Source files inspected:** 24 backend/test/config files; five primary pattern families (readers, frozen evidence, saved reports, durable stores, transport), with bounded supporting excerpts.
**Limitations:** frontend/auth/observer lifecycle are new contracts; import extraction requires behavior tests, especially saved Shadow integrity without reevaluation. No production changes, installs, external calls, notifications or commits performed.
