---
quick_id: 261005-rob
mode: quick
status: planned
---

# Connect the supplied Discord webhook

1. Store the owner-supplied webhook only in the protected observer config, validate with ObserverSettings, and retain the exact existing source registry and operational path.
2. Stop the tracked observer gracefully, confirm ownership release and restart watch using the same protected logging and dependency environment.
3. Send one explicit connection-check notification with a single transport attempt. Record only a bounded delivery result, never the webhook or raw response body. Do not replay prior finalized notification attempts.
4. Verify RUNNING/fresh heartbeat, preserved source DB digests and secret-free repository changes. Update workflow records and commit/push.

Configuration-only task. No application source edits or new tests required. Existing historical source warnings and trading authority remain unchanged.
