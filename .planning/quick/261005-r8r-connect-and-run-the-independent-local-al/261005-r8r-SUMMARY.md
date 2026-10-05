---
quick_id: 261005-r8r
mode: quick
status: complete
---

# Independent local alert observer connected

The owner requested connecting alerts after the web showed UNKNOWN. Created `~/.config/stock-trading-bot/operator/config/alerts.json` with mode 0600, the existing isolated operational DB and the four verified read-only mock registrations. No Discord webhook or service expectation registration is configured.

The existing CLI completed one scan successfully, then an independent detached `trading_bot.alert_cli --config <protected-config> watch` process was started. PID and log are tracked in the protected operator `logs/alert-observer.pid` and `logs/alert-observer.log`. Runtime PID at deployment: 96186. The web process did not need restarting. The observer has no trading credentials or execution authority.

## Verified result

- Observer RUNNING, no lifecycle failure; heartbeat advanced through 120 seconds with a recent heartbeat. Scans recur every 30 seconds.
- Operational alert schema now exists. Four active incidents are stored: two saved portfolio CRITICAL states (`RECONCILIATION_UNRESOLVED`, `BROKER_TRUTH_FAILED`) and two WARNING source-read failures.
- Authenticated private HTTPS `/alerts?period=30d` returned 200, showed RUNNING and four incident cards with total 4. All four detail URLs returned 200. The alerts API returned 200 with the same rendered incidents. No ALERT_STORAGE_UNAVAILABLE remained.
- Two historical producer delivery attempts retain FAILED. Two observer attempts are DISABLED because no webhook is configured. These are distinct from the healthy observer process; no external notification was sent.
- SHA256 digests of audit.db, soak.db and soak-controller.db matched the pre-registration protected baseline. No source migrations, order submissions, reconciliation, freeze release or trading activation occurred.

## Remaining evidence limits

The historical audit source cannot pass a full alert scan: some old provenance is missing/invalid and historical targets also differ from the registered mock scope. The soak campaign identifiers are rejected by the existing identifier sanitization (`INVALID_SOURCE_ID`, including date-shaped numeric components). The observer records these as unavailable source warnings, retains its checkpoint and avoids claiming complete coverage or recovery. Portfolio and controller reads succeeded. This task does not alter saved evidence or relax scope/redaction validation to suppress those warnings.

Missing lifecycle fields and unavailable historical/service/delivery proof may still display UNKNOWN. Local web alerts now have stored evidence; Discord delivery needs a separately supplied protected webhook. The detached observer runs while this Mac remains awake; no login/reboot autostart agent was installed.

## Local operation

Read status with the existing Python dependency environment and `python3 -m trading_bot.alert_cli --config ~/.config/stock-trading-bot/operator/config/alerts.json status`. To stop, verify the command for the tracked PID, then send SIGTERM; the CLI stores STOPPED and releases ownership. To restart, use the same watch command with protected logging, updating the tracked PID. Do not start a second observer while ownership is recent.

Configuration-only deployment: no application source changes or new tests. Validation used the actual CLI, operational read-only SQL, real HTTPS login/list/detail/API and unchanged source digests.
