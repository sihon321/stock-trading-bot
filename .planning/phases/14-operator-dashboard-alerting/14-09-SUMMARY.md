---
phase: 14-operator-dashboard-alerting
plan: "09"
subsystem: alerting
tags: [readonly, foreground-observer, incident-detection, sqlite, discord, tdd]
requires:
  - phase: 14-06
    provides: Immutable bounded saved source batches and worker observations
  - phase: 14-08
    provides: Durable alert episodes, producer ownership, claims and pure notification transport
provides:
  - Stable scoped incident detection and positive saved recovery
  - Independent ObserverSettings and foreground 30-second watch/once/status CLI
  - Exclusive operational observer ownership, lifecycle and conservative UNKNOWN takeover
  - Checkpoint-before-send and bounded producer receipt linkage
affects: [14-10, 14-11, 14-12]
tech-stack:
  added: []
  patterns: [query-only source adapters, isolated notification secrets, committed delivery claims, heartbeat operational ownership]
key-files:
  created: [trading_bot/alert_detector.py, tests/test_alert_detector.py, trading_bot/alert_config.py, trading_bot/alert_observer.py, trading_bot/alert_cli.py, tests/test_alert_observer.py, tests/test_alert_cli.py]
  modified: [trading_bot/web_evidence.py, tests/test_web_evidence.py]
key-decisions:
  - "Only saved same-subject recovery resolves an episode; campaign completion never clears the irreversible D-09 latch."
  - "Operational heartbeat takeover requires more than 300 seconds; prior in-flight delivery claims become UNKNOWN in the same ownership transaction."
  - "Observer Discord delivery uses one bounded transport attempt; uncertain terminal events are never reclaimed."
  - "Producer receipts may precede observations across bounded pages, so sanitized operational receipts remain pending until the episode exists."
requirements-completed: [OPSV-01, UI-02]
coverage:
  - id: D1
    description: Stable required incident families, source severity and positive recovery
    requirement: OPSV-01
    verification: [{kind: unit, ref: tests/test_alert_detector.py, status: pass}]
    human_judgment: false
  - id: D2
    description: Owned foreground lifecycle, committed delivery and critical-only reminder windows
    requirement: OPSV-01
    verification: [{kind: integration, ref: tests/test_alert_observer.py, status: pass}]
    human_judgment: false
  - id: D3
    description: Credential-free readonly status, protected configuration and graceful signal CLI
    requirement: UI-02
    verification: [{kind: integration, ref: tests/test_alert_cli.py, status: pass}]
    human_judgment: false
duration: 21min
completed: 2026-10-02
status: complete
---

# Phase 14 Plan 09: Foreground Operational Alerts Summary

**동일 소스·계좌·대상의 사건을 탐지하고, 명시적으로 실행한 전경 관찰기에서 전달 소유권·UNKNOWN·30분 CRITICAL 재알림을 운영 DB에 보존합니다.**

## Accomplishments

- `AlertDetector.detect(batch)` consumes immutable saved source facts and real observed worker expectation/cadence. Stable six-field subjects exclude iteration UUID and date. Failed cycles/evaluations/workers default WARNING; unresolved orders/freezes/latches and broker divergence default CRITICAL. Saved severity remains authoritative, including INFO. Worker stale equality at `max(180, 3*cadence)` remains fresh. UNKNOWN/failed read, absent record and stopped/not-expected state never invent recovery.
- Positive recovery requires later same-subject completed cycle, saved finalized signal, fresh positively running worker, complete terminal broker progression with broker identity, authoritative validated freeze release, or producer recovery code. An irreversible safety latch remains latched when its campaign completes. Broker divergence absence never resolves it; no current source adapter fabricates missing clear proof.
- Ordered Phase11 source observations retain producer ownership, stable `state_identity:EVENT_CODE`, and `transition-notification:<savedID>` attempts. Missing producer delivery evidence remains UNKNOWN. Sanitized receipts arriving before observations are persisted and linked later without another occurrence or Discord send.
- `ObserverSettings` is independent of trading Settings and `.env`, accepts explicit registered resource authority and an isolated optional SecretStr HTTPS Discord webhook, and rejects overlapping writable/source roots and storage links. The existing web configuration receives no webhook.
- `AlertObserver` uses SQLite writer transactions for exclusive operational identity/heartbeat/lifecycle. More than 300 seconds of heartbeat age is required for takeover; old in-flight claims become terminal UNKNOWN before the new owner is published. This ownership has no relationship to trading mutation leases. STARTED, STOPPED, FAILED and takeover failure events are durable.
- All source reductions and sanitized receipt staging commit before the batch checkpoint; the checkpoint commits before transport claims/send. Claims commit before network I/O. Mandatory source or operational evidence errors stop dispatch and persist observer failure; bounded transport errors retain terminal accounting. Discord uses one attempt with a 5-second per-phase timeout, conservatively shorter than ownership expiry. A stop flag prevents additional queued sends and finishes current bounded bookkeeping.
- `bot-alerts --config <protected.json> watch|once|status` explicitly controls foreground monitoring. Watch waits 30 seconds between scans, with no browser dependency or autostart. SIGINT/SIGTERM set a stop flag and restore previous handlers. Status uses `mode=ro`/`query_only`, requires no webhook, does not initialize a DB, acquire ownership or construct transport, and returns sanitized lifecycle/age/checkpoint/delivery counts.
- INFO remains web-only. WARNING/CRITICAL occurrence, worsening and positive recovery dispatch once by ownership. CRITICAL reminders use the existing durable store's exact 30-minute boundary, current revision acknowledgement suppression and next actual claim +30-minute scheduling, including a single overdue window after delay.

## Task Commits

1. **T1 RED:** `c7c932c` — stable subjects, source families, recovery, severity and ownership tests; expected missing detector module failure.
2. **T1 GREEN:** `82132cd` — detector and narrow readonly source contract completion; 26 detector/source tests passed in 7.22s.
3. **T2 RED:** `daa6061` — lifecycle, dispatch, reminder, receipt and CLI negative contracts; expected missing observer/config/CLI failures.
4. **T1 correctness follow-up:** `d15179d` — finalized evaluations require their actual saved terminal event type; synthetic freeze release tests cover matching and conflicting subject proof.
5. **T2 GREEN:** `c4c26b2` — isolated configuration, durable observer and signal-aware CLI, additional crash/evidence/coexistence tests.

## Verification

Final command:

`PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q tests/test_alert_detector.py tests/test_alert_observer.py tests/test_alert_cli.py tests/test_alert_store.py tests/test_web_evidence.py`

**71 passed in 10.07s.** Earlier T2-only verification: 15 passed in 1.18s. `git diff --check` passed. Created files and all five implementation/test commit objects were checked. No tracked files were deleted or generated files left untracked. Parent owns the full regression at the wave boundary.

Tests cover exact stale/reminder equality, restart replay original ID deduplication, receipt-before-observation, producer no duplicate send, severity worsening/ack reset, recovery/recurrence, unknown source, source failure, checkpoint failure before transport, crash after send, stale takeover and old-owner refusal, CLI protected config/secret errors, no dotenv credentials, status byte invariance, graceful signals, WebStore/AlertStore coexistence, and synthetic source byte/schema/data invariance. No real KIS, LLM or Discord call, owner database access, actual password, server, deployment, or freeze mutation occurred.

## Consumer Interfaces

```python
from trading_bot.alert_config import ObserverSettings
from trading_bot.alert_detector import AlertDetector
from trading_bot.alert_observer import AlertObserver

facts = AlertDetector().detect(saved_alert_source_batch)
settings = ObserverSettings(operational_db_path=operation_path,
                            registered_resources=registered_resources)
observer = AlertObserver(settings, evidence=readonly_reader,
                         notifier=fake_transport, clock=aware_clock)
observer.scan_once()             # explicit acquire, scan, release
observer.watch(stop_event)       # explicit acquire, 30s loop, finally release
snapshot = observer.status()    # no creation, acquisition or transport
```

`start()`, `heartbeat()` and `stop(failure_code=None)` expose explicit operational lifecycle. `scan_once(now=None)` accepts an aware test clock boundary; production injects one coherent clock for source freshness and store windows. `after_send` is an injected crash seam. Competing recent observer raises `ObserverBusy`; mandatory source/operational failure raises sanitized `ObserverEvidenceError`.

Status returns `state`, `heartbeat_age_seconds`, `started_at`, `stopped_at`, `failure_code`, `cursor`, and grouped `deliveries`. States include NOT_STARTED, RUNNING, STALE, STOPPED and FAILED. The observer's operational tables use `alert_`/`phase14_alert_` namespaces and coexist with existing WebStore/AlertStore ownership checks.

## Deviations from Plan

**[Rule 2 - Missing Critical] Completed the existing readonly alert source contract.** During T1, `observe_alert_sources` omitted daily evaluations/evaluation events and positively proven freeze-release facts. Phase11 observation/receipt DTOs omitted the subject fields needed to attribute records across bounded pages/restarts. The parent explicitly expanded ownership to `web_evidence.py` and `tests/test_web_evidence.py`. The adapter now emits saved evaluations and terminal event type, adds three allowlisted subject scalar fields through the existing validated same-account state join, derives producer event code from saved source order/terminal meaning, and emits only releases accepted by the existing same-campaign/ticker/intent determinate-terminal proof. Original IDs, cursor bounds and readonly schema/source invariance remain intact. Commits `82132cd`, `d15179d`.

No broader trading capability or architecture was added. Initial synthetic fixture column/value mistakes were corrected before the affected green checks; the production schema did not change. Shared STATE/ROADMAP/REQUIREMENTS/VALIDATION mutations remain exclusively parent-owned as instructed.

## Documentation Lookup

Context7 MCP/CLI was unavailable. Checked official [Pydantic Settings customization](https://pydantic.dev/docs/validation/dev/concepts/pydantic_settings/) and [Typer command callbacks](https://typer.tiangolo.com/tutorial/commands/callback/) for independent settings sources and root configuration options. Existing pinned SDK usage remains unchanged.

## Known Stubs

None. UNKNOWN source health, unavailable worker cadence/expectation, missing producer receipt, uncertain transport and absent same-subject broker/latch clear proof remain explicit unavailable evidence. No placeholder claims healthy operation or authorizes a trade.

## User Setup Required

No setup was performed. Actual monitoring requires an explicit protected observer JSON configuration and foreground command; Discord credentials are optional. This plan does not start a persistent observer or send a live notification. External acceptance and full phase integration belong to later phase checks.

## Self-Check: PASSED

All seven created implementation/test files, both modified source regression files and this SUMMARY exist. Git confirms `c7c932c`, `82132cd`, `daa6061`, `d15179d`, and `c4c26b2`. The final 71-test focused command passed, and no tracked deletions or generated untracked files remain. Parent-owned STATE was preserved.
