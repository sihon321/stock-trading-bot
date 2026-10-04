# Phase 15: Unattended Scheduling & Service Resilience - Pattern Map

**Mapped:** 2026-10-04
**Files classified:** 47 candidate new/modified files; 31 exact analog assignments, 13 role matches, 3 partial matches. Novel contracts without complete analogs are listed below.
**Scope:** Candidate files from 15-CONTEXT.md / 15-RESEARCH.md plus required integration companions. New filenames and contracts below are proposals, not existing callable APIs. Source inspection only; no runtime journal queries or activation.
**Strong analog families:** portfolio evidence, mutation leases, protected operational stores, authenticated actions, independent observer. References describe the inspected pre-Phase-15 code.

## File Classification

Paths below are relative to `trading_bot/` unless prefixed otherwise. Grouped rows assign each listed file the same role/flow.

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| **new** `service_models.py` | model | transform | `audit_models.py:75-130`; `web_config.py:17-32` | role-match |
| **new** `service_config.py` | config | file-I/O | `alert_config.py:11-51` | exact |
| **new** `service_store.py` | store | CRUD/event-driven | `portfolio_store.py:178-234`; `web_store.py:108-154` | exact |
| **new** `control_store.py` | store | CRUD/event-driven | `web_store.py:133-220`; `web_app.py:835-863` | exact |
| **new** `service_schedule.py` | utility | event-driven/transform | `market_cycle.py:71-105`; `intraday.py:228-238` | partial |
| **new** `service_runtime.py` | service | event-driven | `intraday.py:241-387`; `alert_observer.py:193-204` | role-match |
| **new** `service_activation.py` | utility | transform | existing preflight / evidence readers; no approval-receipt analog | partial |
| **new** `submission_authority.py` | middleware | request-response | `kis_broker.py:139-308`; `cli.py:185-218` | role-match |
| **new** `service_launchd.py` | utility | file-I/O/event-driven | protected loading in `alert_cli.py:21-38`; no launchd implementation | partial |
| **new** `service_cli.py` | controller | request-response | `alert_cli.py:41-86` | exact |
| `market_cycle.py`, `data_source.py` | utility/service | request-response | `MarketCyclePolicy.classify`; `ObservedKRXCalendar` | exact |
| `intraday.py`, `mutation_lease.py` | service | event-driven | `run_intraday_check`; `acquire_mutation_lease` | exact |
| `audit_models.py`, `portfolio_store.py` | model/store | CRUD/event-driven | `DailyEvaluationEvent`; `start_daily_evaluation` | exact |
| `llm_provider.py`, `cli.py` | provider/controller | request-response | `_call_provider_with_retry`; `_load_or_generate_daily_signal` | exact |
| `kis_broker.py`, `exit_manager.py`, `mock_broker.py` | service | request-response | `KISBroker.place_order`; `submit_exit`; `MockBroker.place_order` | exact |
| `web_config.py`, `web_models.py`, `evidence_contracts.py` | config/model | transform | `ResourceDescriptor`; `WorkerDTO`; owner schema declarations | exact |
| `web_evidence.py` | service | request-response | `_transaction:108-153`; `_workers:415-473` | exact |
| `web_app.py`, `web_store.py` | controller/store | request-response/CRUD | `acknowledge_alert:835-863`; `append_action:218-220` | exact |
| `alert_config.py`, `alert_detector.py`, `alert_observer.py` | config/service | event-driven | `ObserverSettings`; `AlertDetector._worker`; `AlertObserver._scan` | exact |
| **new** `templates/operator/controls.html`; `templates/operator/overview.html` | component | request-response | `templates/operator/alerts.html:7-10` | exact |
| `pyproject.toml`, `docs/operator-runbook.md` | config | file-I/O | script/package-data entries `pyproject.toml:28-41`; existing runbook | role-match |
| **new** `tests/test_service_{activation,schedule,recovery,authority,controls,health,launchd,dry_run}.py` | test | event-driven/request-response | `tests/test_mutation_lease.py`; `tests/test_alert_observer.py`; `tests/capability_probe.py` | role-match |
| **new** `tests/test_web_control_routes.py` | test | request-response | `tests/test_web_alert_routes.py:41-58` | exact |
| `tests/test_portfolio_store.py`, `tests/test_phase11_cli.py`, `tests/test_evidence_contracts.py`, `tests/test_web_capabilities.py` | test | CRUD/request-response | existing identity/recovery/schema/tripwire suites | exact |

## Pattern Assignments

### Durable service/control models, config and stores

`service_models.py`: use frozen typed evidence, bounded identifiers, aware timestamps and scalar diagnostics from `audit_models.DailyEvaluationEvent:106-130`. Strict request/config models copy `web_config.ResourceDescriptor:17-25`:
```python
model_config = ConfigDict(frozen=True, extra='forbid', hide_input_in_errors=True)
```
`service_config.py`: copy `alert_config.py:5-13,20-23`; retain a dedicated prefix and explicit protected config, with no ambient trading dotenv in control/read-only paths:
```python
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
# ObserverSettings analog; the new service prefix is a planning choice.
model_config = SettingsConfigDict(env_prefix='BOT_ALERTS_', env_file=None,
    frozen=True, extra='forbid', hide_input_in_errors=True)
```
`service_store.py`: copy owner/version rejection and atomic rollback from `portfolio_store.migrate_portfolio:178-234`; combine protected creation/no-follow/mode checks from `web_store.initialize:108-130`. Use a separate service owner and journal, preserving trading facts. `control_store.py` gets narrowly scoped request writes and service-only application evidence; it must not expose service-job or trading mutation APIs to the web.
```python
# web_store.WebStore.connection, lines 142-152
conn = sqlite3.connect(db.as_uri() + '?mode=rw', uri=True, timeout=5)
conn.row_factory = sqlite3.Row
try:
    conn.execute('PRAGMA foreign_keys=ON')
    conn.execute('PRAGMA secure_delete=ON')
    conn.execute('BEGIN IMMEDIATE')
    yield conn
    conn.commit()
except BaseException:
    conn.rollback()
    raise
```
Commit claims/control revisions before external work; use bounded contention handling. Do not hold a transaction across provider calls or reconcile separate journals as one atomic DB. Restrictive requests deny affected submissions immediately while applied evidence remains separate; pending resume grants nothing.

### Daily dispatch migration and stored input

`audit_models.py`, `portfolio_store.py`, `llm_provider.py`, `cli.py`: preserve `StoredDailyEvaluation.canonical_input/hash`, date/ticker uniqueness and first-input wins (`portfolio_store.py:132-143,576-633`). Current statuses are only STARTED/FINALIZED (`audit_models.py:75-84`). **Proposed** dispatch states/claim APIs are absent and need owner migration; do not call imagined `claim_dispatch` methods.
```python
# cli._load_or_generate_daily_signal, lines 297-304
append_daily_evaluation_event(
    conn, evaluation.evaluation_id,
    event_type=DailyEvaluationEventType.PROVIDER_ATTEMPT,
    detail={"attempt": attempt},
)
try:
    signal = provider.generate_signal(context)
```
Existing event-before-provider is the ordering analog, not a safe retry implementation. Current `context` is reconstructed, outer retries exist at `cli.py:296-315`, and SDK/subprocess retries wrap all transport exceptions (`llm_provider.py:177-200`). Introduce explicit stored-input dispatch at provider boundaries; pin prompt/system/model identity or retain sufficient frozen structured context. Disable blind retries after uncertain dispatch, including nested provider retries.
`recover_started_evaluations:726-742` currently finalizes **all** STARTED rows unavailable; `run_cycle:1658-1660` invokes it before account authority. Replace that behavior under proper ownership: any old PROVIDER_ATTEMPT is conservatively dispatched; only proven never-dispatched work resumes before 09:20. Preserve finalized signals and immutable inputs. `tests/test_portfolio_store.py:109` and `tests/test_phase11_cli.py:145` encode the old behavior and require deliberate updates.
Migration companions: `evidence_contracts.py` and `web_evidence._transaction:124-143` currently require portfolio version **3** and exact columns. Update supported reader contracts/fixtures with the owner migration so saved web/report/observer readers fail closed consistently without losing existing evidence.

### Schedule, bounded account work and recovery

`service_schedule.py`, `market_cycle.py`, `data_source.py`: copy injected calendar policy, aware KST conversion and UNKNOWN behavior (`market_cycle.py:74-105`). **Proposed SessionEvidence** does not exist; normal hours are hardcoded there and in `intraday.session_phase_at:228-238`. Feed reviewed date-specific session evidence through scheduling, preflight, risk and final POST.
`service_runtime.py`, `intraday.py`, `mutation_lease.py`, `cli.py`: `run_intraday_check:241-255` is the existing one-pass API with injected clock, snapshot/quote readers, lease, submitter, audit and mutation guards. Adapt the composition; wrapping current `run_intraday_watch` keeps one lease across sleep (`cli.py:2359-2365,2519-2535`; `intraday.py:463-489`).
```python
# mutation_lease.acquire_mutation_lease, lines 432-440
fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
os.fchmod(fd, 0o600)
try:
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
except OSError as exc:
    os.close(fd)
    if exc.errno in (errno.EACCES, errno.EAGAIN):
        raise LeaseBusyError(_busy_metadata(conn, scope)) from None
```
Separate leader exclusion from account authority. Acquire/recover/reconcile/release for bounded work, never sleep or await the LLM with the account lease. Reuse `MutationLease.recover_to_active:288-343` callbacks: terminalize predecessors → fresh complete same-account snapshot → determinate prior-order reconciliation → ACTIVE. Preserve `release_after_reconciliation:558-585` terminalization/unresolved-evidence-before-release semantics. A stale heartbeat cannot steal a live lock or clear a freeze.
Schedule 08:50 non-order prep, 09:00 risk/60s, 09:10 daily, strict `<09:20` never-dispatched catch-up; stop new POST at 15:20, reconcile through close, terminate watch at 15:30. Persist missed/partial/unknown honestly. Failed daily evaluation alone does not terminate independently healthy protection.

### Shared final submission authority and activation

`submission_authority.py` is **new**; extend existing guarded composition in `cli._LeaseGuardedBroker:185-218`, `KISBroker.place_order:139-308`, `exit_manager.submit_exit:185-222`, and `MockBroker.place_order:71`. Include daily/manual/intraday/designated mock paths; reconcile/observe remain available.
```python
# kis_broker.KISBroker.place_order, lines 280-285 and 305-308
try:
    lease_guard.assert_active_owner()
except Exception:
    raise MarketClosedError("KIS order skipped: mutation ownership lost") from None
# Existing SUBMISSION_ATTEMPTED evidence is emitted at lines 292-304.
try:
    result = self._order_adapter.place_order_cash(
        account=self._account, order=order, snapped_price=snapped_price,
    )
```
Check pause against every BUY, including previously saved signals; global kill against every new submission, including risk SELL. Define a serialized control/POST admission boundary and test a restrictive request arriving after the earlier check or event: a check only at scheduler start or before mutable evidence callbacks is insufficient. Do not hold transactions over network POST, cancel outstanding orders, liquidate, clear freezes, or clear pause/kill through date rollover/recovery.
`service_activation.py` is **new**. Receipt validation is not equivalent to existing preflight PASS. Gate before trading collaborators and again at final unattended authorization: both 09-08 operator approvals, immutable campaign/profile/evidence identities, drills/verdicts and current applicable freezes. Synthetic fixture receipts never grant production authority. Reject REAL categorically for this phase; ordinary local `MockBroker` simulation is not authenticated KIS mock acceptance.

### Authenticated requests and mobile requested/applied state

`web_app.py`, `web_store.py`, `control_store.py`, `templates/operator/controls.html`, overview: reuse app authentication/origin/CSRF guard (`web_app.py:177-204`), resource authorization, existing action audit (`609-611`, `web_store.py:205-220`) and alert action validation:
```python
# web_app.acknowledge_alert, lines 844-848
if set(request.form) - {'csrf_token','expected_revision','note'} or any(
        len(request.form.getlist(k)) != 1 for k in request.form) or len(note)>500:
    raise ValueError()
revision = int(request.form.get('expected_revision',''))
if revision<1:
    raise ValueError()
```
Adapt allowed fields/actions, never accept arbitrary paths, scopes or jobs. Bind request ID/actor/time/scope/expected revision; replay is idempotent or conflicts, with bounded errors (400/409/503 analog at `835-863`). Cross-store action/request persistence needs explicit correlation and truthful failure evidence. Render CSRF/revision hidden fields and escaped values using `templates/operator/alerts.html:10`; show request pending separately from applied/rejected state. Web imports/config expose neither credentials/provider nor service execution/policy-write capabilities.

### Saved health and independent incident observation

`web_models.py`, `web_config.py`, `web_evidence.py`, `alert_config.py`, `alert_detector.py`, `alert_observer.py`: extend registered owner/schema declarations and saved DTOs; copy read-only bounded transactions (`web_evidence.py:108-153`) and expected/UNKNOWN handling (`_workers:429-470`). Add schedule expectation evidence so absent runs can be detected; existing detector requires a positive source time/ID (`alert_detector.py:118-119`) and cannot invent absent schedule facts.
```python
# alert_observer.AlertObserver._scan, lines 154-159
for fact in self.detector.detect(batch):
    self.store.observe(fact)
self._receipts(batch)
if batch.cursor is not None:
    self.store.set_checkpoint(batch.cursor)
self.store.due_reminders(now)
```
Reuse durable observer/outbox ownership, UNKNOWN delivery and reminders (`_scan:165-178`), preserving producer receipt deduplication. Add service sources to mandatory-source failure handling (`148-153`) deliberately. Expected health depends on confirmed session/control/login/schedule evidence; paused risk protection can still be expected. Keep observer supervision independent of trading restart exhaustion. Same stopped Mac cannot notify during its total outage.

### CLI, launchd and offline tests

`service_cli.py`: copy protected explicit JSON loading (`alert_cli.load_settings:21-38`), Typer root/subcommands and signal-restoring Event shutdown (`46-68`). Register the proposed entrypoint beside `bot-alerts` (`pyproject.toml:28-31`); refresh installed package entrypoints at implementation/deployment. `service_launchd.py`: use stdlib plist rendering; **no existing launchd or sliding restart-budget API exists**. Render disabled setup first; absolute owner-protected paths, owner GUI domain, separate observer label, bounded shutdown. Durable admission before recovery/worker construction: at most three automatic worker restarts/600s, conservative clock reversal, persistent MANUAL_ATTENTION and clean launcher exit on exhaustion. Native KeepAlive/ThrottleInterval do not implement the budget. Explicit reset never erases history or operator kill.
Tests: copy `tests/test_mutation_lease.py:34-73` child ownership/crash barriers; `tests/test_alert_observer.py:15-44` fake Clock/Reader/Transport; `tests/test_web_alert_routes.py:41-55` CSRF/actor/action/source-byte assertions. Extend fresh-interpreter `tests/capability_probe.py` / `tests/test_web_capabilities.py:204-253` tripwires. Service dry-run must construct only injected/frozen collaborators and temporary journals, with zero KIS/LLM/pykrx/Discord/provider-subprocess/install calls or production/policy writes. Existing `bot run` without execute still calls data/provider collaborators; it is not the offline dry-run analog.

## Shared Patterns / Ownership and Sequence Constraints

1. Agree service/control/dispatch/session/receipt schemas and capabilities first. One implementation owner each for `portfolio_store.py`/`audit_models.py`, shared `cli.py`, and web/evidence schema surfaces; parallel plans must sequence these shared files or use explicit handoffs.
2. Migrate dispatch state and all saved-reader contracts together before restart-resume work. Reserve dispatch atomically under authority; release account authority before bounded provider work; revalidate saved results with fresh controls/truth/session at execution.
3. Deliver controls and final guard wiring across all order-capable compositions before exposing active scheduler/resume. Pending restrictive requests must block even when the service is stalled. Request/application evidence and service job facts have distinct writer capabilities.
4. Bounded service composition precedes scheduling, restart supervision and health acceptance. Leader generation is not logical daily job identity; service ownership never replaces account mutation ownership.
5. Preserve append-only sanitized evidence (`audit_models.sanitize_detail:151-168`), terminal/UNKNOWN POST facts and 000660 freezes. Owner-specific migrations/readers cannot amend broker facts; no new dependency pins are needed.
6. Offline fixtures validate contracts, not elapsed-day acceptance, authenticated broker proof, real promotion, macOS login/wake operation or phone access. Actual launchctl activation and operator acceptance remain explicit separate steps.

## No Analog Found

| Proposed contract | Gap / planner responsibility |
|---|---|
| LaunchAgent renderer and durable restart admission | No existing supervisor; implement research contract and injected launcher tests. |
| Date-scoped exceptional-session authority | Calendar/current-day witness exists; no reviewed exception feed contract. UNKNOWN blocks. |
| 09-08 machine-readable acceptance receipt | Human checkpoints exist; no equivalent receipt/gate API to copy. |
| Operational request/application revision protocol | Alert acknowledgement supplies validation/audit analog only; execution control authority is new. |
| Resumable never-dispatched provider boundary | Existing STARTED recovery/retries conflict with Phase 15; explicit migration and provider seam required. |

## Metadata

**Search scope:** `trading_bot/`, `tests/`, `pyproject.toml`, project instructions/skills and Phase 15 context/research. Five strong analog families; additional contract sites inspected only for required integration seams. **Extraction date:** 2026-10-04. **Changed file:** this pattern map only. Tests were not run by the mapper.
