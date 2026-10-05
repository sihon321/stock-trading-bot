---
quick_id: 261005-teq
mode: quick
status: planned
---

# Display elapsed observations with calendar years, months and days

1. Extend the shared display formatter to show calendar years/months/days followed by HH:MM:SS using the saved observation timestamp in KST. Clamp month ends and retain UNKNOWN and nonnegative durations.
2. Supply timestamps for source ages, observer heartbeat, worker leases and incident durations; update display labels without changing numeric evidence or operational thresholds.
3. Verify existing web tests and calendar boundaries, restart only the tracked web server and inspect authenticated private HTTPS pages.
4. Record completion in SUMMARY.md and STATE.md, then commit and push following existing conventions. Execute inline per skill fallback.
