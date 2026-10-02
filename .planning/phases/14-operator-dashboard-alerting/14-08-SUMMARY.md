---
phase: 14-operator-dashboard-alerting
plan: "08"
subsystem: alerting
tags: [sqlite, incident-episodes, acknowledgement, outbox, discord, capability-separation, tdd]
requires:
  - phase: 14-02
    provides: Independent bounded read-only source contracts
  - phase: 14-03
    provides: Credential-free saved evidence authority
  - phase: 14-05
    provides: Independently owned phase14_web operational database
provides:
  - Immutable alert subjects and source facts with durable idempotent episode/revision projections
  - Server-time actor acknowledgement CAS and append-only operational audit
  - Producer-owned delivery links and committed observer claims with explicit crash uncertainty
  - Current-CRITICAL-only thirty-minute reminders without overdue catch-up bursts
  - Pure bounded notification transport with compatible trading imports and factory
affects: [14-09, 14-10, 14-11, 14-12]
tech-stack:
  added: []
  patterns: [independent schema metadata, source-ID deduplication, append-only read facts, committed claim before I/O, producer ownership]
key-files:
  created: [trading_bot/alert_models.py, trading_bot/alert_store.py, tests/test_alert_store.py, trading_bot/notification_transport.py, tests/test_notification_transport.py]
  modified: [trading_bot/notifier.py]
key-decisions:
  - "Acknowledgement time comes from the injected server clock; caller-supplied at cannot replace it."
  - "Producer events own their globally unique resource/owner/event key, including UNKNOWN when an attempt is missing."
  - "Reminder claims advance next due from actual claim time; UNKNOWN and FAILED events never regain QUEUED state."
  - "Backdated observations remain in their historical episode, and older producer attempts cannot replace newer delivery truth."
requirements-completed: [OPSV-01, UI-02]
coverage:
  - id: D1
    description: Unique saved source observations, durable duration, recurrence/worsening unread revisions and acknowledgement CAS
    requirement: UI-02
    verification: [{kind: integration, ref: tests/test_alert_store.py#episode-revision-acknowledge-schema, status: pass}]
    human_judgment: false
  - id: D2
    description: Producer-owned delivery links, one committed claimant, uncertain crash history and CRITICAL-only thirty-minute reminders
    requirement: OPSV-01
    verification: [{kind: integration, ref: tests/test_alert_store.py#outbox-delivery-reminder-claim, status: pass}]
    human_judgment: false
  - id: D3
    description: Config-independent bounded transport, legacy API compatibility and secret-free logs with fake HTTP clients
    requirement: OPSV-01
    verification: [{kind: integration, ref: tests/test_notification_transport.py, status: pass}]
    human_judgment: false
duration: 66min
completed: 2026-10-02
status: complete
---

# Phase 14 Plan 08: Durable Alert State and Isolated Transport Summary

**저장 source ID로 중복 집계를 막는 incident episode, revision별 읽음 CAS, 생산자 전송 소유권 및 crash UNKNOWN outbox, 30분 CRITICAL 리마인더와 설정에서 독립된 Discord 전송 계층을 구현했습니다.**

## Performance

- Started: 2026-10-02T02:28:53Z.
- Implementation verification completed: 2026-10-02T03:34:05Z.
- Elapsed duration includes the quota interruption and user-authorized resume; completed T1 was preserved.
- Tasks: 3/3. Owned implementation/test files: 6.

## Accomplishments

- `AlertSubject` excludes normalized state and iteration attribution from its stable resource/account/target/ticker-or-account/problem-family/broker-subject identity. `AlertSourceFact` validates durable source ownership/ID, nonnegative sequence, aware observation time, severity and explicit saved recovery proof. The immutable episode/revision/acknowledgement/delivery DTOs contain no trading collaborator or source write handle.
- `AlertStore` independently owns `phase14_alert_metadata` version 2. Initial schema creation and version-1 delivery upgrade use `BEGIN IMMEDIATE` transactions; injected upgrade failure rolls back. Existing `phase14_web_metadata` remains independently owned and unchanged. Unsupported versions, source tables, linked files and unsafe operational permissions are refused before mutation. WebStore-first initialization in the shared operational database is tested.
- Unique `(source_owner, resource_id, source_id)` observations, cursor progress and episode projection commit together. Repeated saved IDs never add another occurrence. Distinct IDs preserve minimum first/maximum last source time and duration across restart and backdated insertion. Historical facts belong to the closed episode even after a new recurrence, rather than reopening or inflating that recurrence.
- Worsening increments the current revision and creates unread state. Positive same-subject proof closes an episode; stale proof and unrelated-subject recovery cannot clear a current episode. A recurrence receives a separate unread episode. Lower current severity stops CRITICAL reminders; later worsening creates a fresh unread revision. Missing/UNKNOWN source observations do not establish recovery.
- Acknowledgement requires the selected current episode/revision and a bounded authenticated server actor. It stores server clock time and optional blank or at-most-500-character note, keeps earlier read facts immutable, audits success/conflict, and suppresses that revision's reminders. It never closes an incident or changes a freeze, latch, broker fact or trading gate.
- Producer occurrence/worsening/recovery events are linked to globally unique producer event ownership and saved attempt IDs. Missing attempts remain UNKNOWN and never enter the observer send queue. Repeated evidence is idempotent; the same producer event can be referenced by a recurrence without a second send. Backdated attempt evidence remains reviewable while the later current result remains authoritative.
- Observer events have unique episode/revision/kind/due-window keys. Claim identity and owner commit before the method returns to any network caller. Concurrent claimers yield exactly one winner. Finalization checks owner plus claim ID and preserves known DELIVERED/FAILED/UNKNOWN/DISABLED outcomes. Expired claimed events become UNKNOWN with append-only state history and cannot be automatically claimed again, covering crash before or after a fake send.
- Only active unread current-CRITICAL episodes produce periodic reminders. Equality at the thirty-minute boundary is eligible. One overdue event is dispatched and its next due is actual claim time plus thirty minutes. Acknowledgement or recovery suppresses queued reminders at claim time. An UNKNOWN prior attempt remains distinct from a subsequent independently due reminder window.
- `notification_transport` imports neither trading Settings nor ports/CLI/broker/provider. `notifier` re-exports the same DiscordNotifier/NoopNotifier classes and retains `format_run_summary` plus `build_notifier(settings, client=...)`. Retry count, injected client, timeout and fail-soft Boolean semantics remain compatible. Tests use fake clients and HTTPX MockTransport exclusively.

## Task Commits and Verification

1. **T1 incident/revision/read state:** RED `b56b4ff`; GREEN `d279fd5`. RED failed on the missing alert model module. Focused `episode or revision or acknowledge or schema`: **10 passed in 0.08s**.
2. **T2 delivery ownership/outbox/reminders:** RED `b172e30`; GREEN `f80555e`. RED produced eight expected absent-method failures. First focused `outbox or delivery or reminder or claim`: **8 passed in 0.10s**. Store suite after additional ownership/migration/backdated/current-severity checks: **23 passed in 0.21s**.
3. **T3 pure transport:** RED `f8b8895`; additional disclosure RED `3372b1b`; GREEN `5f4b7de`. Initial RED failed on the missing transport module. The additional fake HTTPX test demonstrated webhook URL disclosure at INFO before the fix. Focused transport/notifier/Phase11 transitions: **27 passed in 0.62s**.

Final plan command:

`PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_alert_store.py tests/test_notification_transport.py tests/test_notifier.py`

**38 passed in 0.71s.** All focused commands remained under sixty seconds. `git diff --check` passed. No tracked file deletions or generated untracked files remain. The full regression suite is parent-owned at the wave boundary.

## Consumer Interfaces

```python
from trading_bot.alert_models import AlertSubject, AlertSourceFact, Severity, DeliveryState
from trading_bot.alert_store import AlertStore, RevisionConflict
from trading_bot.notification_transport import DiscordNotifier, NoopNotifier

store = AlertStore(operation_db_path, clock=aware_server_clock)
store.initialize()  # WebStore initializes its own schema first in a shared DB.
episode = store.observe(typed_saved_source_fact)
ack = store.acknowledge(episode.episode_id, episode.revision, session_actor,
                        note=optional_note)

for event in store.pending_deliveries():
    claim = store.claim_delivery(event.event_key, observer_owner)
    if claim is not None:
        # Claim has committed here; the observer can now attempt isolated transport.
        store.finalize_attempt(claim.event_key, claim.owner, claim.claim_id,
                               DeliveryState.DELIVERED)
```

- `AlertSubject(resource_id, account_hash, target, ticker_or_account, problem_family, broker_subject='NONE')`. Account hash is 64 lowercase hex characters; target is mock/real/simulated/unknown; identity fields are bounded. Scope comes from the registered source authority, never a fabricated query timestamp.
- `AlertSourceFact(subject, source_owner, source_id, sequence, observed_at, normalized_state, severity, positive_recovery=False, recovery_proof_id=None, delivery_owner='observer', producer_event_id=None, producer_attempt_id=None, producer_delivery_state=None)`. **Phase11 adapters must explicitly use `delivery_owner='producer'`**. Recommended event ID is saved `state_identity:EVENT_CODE`, with original notification row identity as `producer_attempt_id`; iteration UUID is attribution only.
- `observe(fact)` returns the matched incident or null for recovery with no matching episode. The caller must supply distinct saved durable observation identities, not newly generated poll IDs. Replayed original IDs are safe.
- `get_incident(episode_id)` / `get(episode_id)`, `list_incidents(active=None, severity=None, resource_id=None, limit=100)`, `list_revisions(episode_id)`, `list_acknowledgements(episode_id)` and `list_actions()` expose bounded immutable operational views. Active selection spans all dates.
- `acknowledge(episode_id, revision, actor, at=None, note=None)` ignores caller time in favor of the server clock. Stale revision raises `RevisionConflict` after durably auditing the refusal. Actor authenticity and HTTP CSRF enforcement belong to the authenticated server route.
- `get_cursor(source_owner, resource_id)` retains maximum durable sequence. `get_checkpoint(stream='sources')` / `set_checkpoint(cursor, stream='sources')` retain the bounded opaque 14-06 stream cursor independently. **14-09 should commit every fact in a batch before storing that batch's checkpoint**; a crash before checkpoint repeats already committed IDs safely.
- `link_producer_delivery(episode_id, revision, kind, source_owner=..., resource_id=..., producer_event_id=..., producer_attempt_id=None, state=UNKNOWN, at=...)` attaches late saved producer attempt evidence. Kinds: OCCURRENCE/WORSENING/RECOVERY. A missing attempt ID cannot claim delivered truth.
- `pending_deliveries(limit=100)`, `claim_delivery(event_key, owner)`, `finalize_attempt(event_key, owner, claim_id, state, failure_code=None)`, `get_delivery(event_key)`, `list_attempts(episode_id)` and `list_delivery_history(event_key)` keep event ownership, claim identity and outcome history explicit. `expire_claims(now, stale_after_seconds=60, owner=None)` terminalizes up to 100 uncertain expired claims per call. The observer must use a stale boundary longer than its configured bounded transport attempt, or explicit known-lost ownership.
- `due_reminders(now)` returns at most 100 eligible existing/new reminder windows. Successful claim advances next due; polling and queue creation alone do not manufacture extra windows. Transport uncertainty does not reauthorize the same event.

## Deviations from Plan

**[Rule 1 - Bug] Reject non-2xx transport responses.** The original notifier treated HTTP 199/302 as successful because it rejected only status >=400. Pure transport now requires positive 200–299 evidence. Fake-status negative tests pass. Included in T3 GREEN `5f4b7de`.

**[Rule 2 - Missing Critical] Redact HTTPX's own webhook request logs.** The original class redacted its repr and exception warning, while HTTPX still logged the full token-bearing URL at INFO. A fake MockTransport negative test demonstrated the disclosure. During send, a credential-free scoped filter masks the HTTPX request detail message and is always removed afterward, including failure. It retains no webhook secret; concurrent sends remain redacted. RED `3372b1b`, GREEN `5f4b7de`.

Backdated observation/attempt handling, downgrade reminder suppression, opaque checkpoints and transactional delivery upgrade are correctness details of the planned durable reducer/outbox, not new trading authority. The initial WebSettings test fixture used the wrong field name and was corrected to `operational_db_path`; no production setting changed.

Shared STATE/ROADMAP/REQUIREMENTS/VALIDATION updates remain exclusively parent-owned, as instructed. Requirement metadata records this plan's scope and does not claim that the remaining Phase 14 application deliverables are already complete.

## Documentation Lookup

Context7 MCP and its `ctx7` executable were unavailable. Existing pinned Tenacity retry behavior was checked against [official Tenacity documentation](https://tenacity.readthedocs.io/en/latest/) for stop-after-attempt, exception filtering and fixed waiting; no package installation or substitution occurred.

## Issues Encountered

The execution was interrupted after T1 by a quota condition and resumed when the parent confirmed ordinary usage was available and the user requested resume. Completed commits were preserved.

## Known Stubs

None. Missing producer delivery evidence and uncertain in-flight transport are intentional UNKNOWN facts. No known delivered result, source recovery or retry authorization is synthesized.

## User Setup Required

None for this plan. No owner database, credential/password provisioning, real Discord/KIS/LLM call, persistent server, deployment, order, freeze/latch mutation or source migration occurred. Foreground observer lifecycle, authenticated routes and phase-wide human checks remain assigned to subsequent plans.

## Self-Check: PASSED

All six owned implementation/test files exist. Git verified commits `b56b4ff`, `d279fd5`, `b172e30`, `f80555e`, `f8b8895`, `3372b1b`, and `5f4b7de`. The 38-case final plan suite and 27-case transport/Phase11 compatibility suite passed. Stub scan found no TODO/FIXME/placeholder paths; no tracked files were deleted. This SUMMARY is written to its canonical plan path before returning to the parent.
