---
quick_id: 261005-rob
mode: quick
status: complete
---

# Discord webhook connected

The owner supplied a Discord webhook for the existing independent observer. The secret is stored only in the owner-protected external `~/.config/stock-trading-bot/operator/config/alerts.json` (0600), validated with ObserverSettings. The resource registrations, operational DB and trading authority were preserved.

The tracked prior watch process was verified and stopped with SIGTERM. STOPPED and released ownership were confirmed before starting the replacement process with the protected log and PID tracking. Deployment PID: 96919. The new observer reports RUNNING with a fresh heartbeat and no lifecycle failure.

One connection-check message was sent using the existing DiscordNotifier with exactly one attempt. The transport reported DELIVERED at 2026-10-05T10:56:46.180301Z. A secret-free receipt is saved locally in `logs/discord-connection-check.json` (0600), separately from incident delivery history. No raw webhook or response body is included in this record or repository artifacts.

Existing four incident records and their two producer FAILED/two observer DISABLED attempts remain unchanged. Previously finalized attempts were not reset or replayed. Future observer-owned events and eligible reminders use the configured webhook; historical producer failure evidence remains a separate fact.

Verified: owner-protected config, graceful lifecycle transition, real single-attempt Discord send, RUNNING/fresh heartbeat, preserved original source DB SHA256 digests and absence of the webhook from runtime log/repository changes. Configuration-only task, no application source changes or new tests.

The prior historical audit/soak source-read warnings remain visible. Automatic login/reboot startup has not been installed; the observer depends on the running awake Mac.
