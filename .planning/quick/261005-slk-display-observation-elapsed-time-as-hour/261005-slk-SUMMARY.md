---
quick_id: 261005-slk
mode: quick
status: complete
---

# Elapsed durations now display as HH:MM:SS

Added one presentation formatter and applied it to observation age, observer heartbeat age, worker lease age and alert duration, including source metadata on detail pages. Labels identify the hours/minutes/seconds format. Missing values remain UNKNOWN; total hours do not wrap after 24. Fractional seconds are omitted from the display.

The numeric evidence values, freshness/cadence thresholds and independent observer behavior remain unchanged. No source DB edits, observer restart or trading operations were performed.

Validation: existing affected route/UI/alert-route suite passed 85 tests. Direct boundary checks covered missing, zero, minute/hour transitions, fractional seconds and durations beyond 24 hours. Real authenticated HTTPS overview/workers/alerts/alert-detail pages returned 200 and showed HH:MM:SS, including historical ages with more than two hour digits and current heartbeat age.

Restarted only the tracked protected web CLI process; deployment PID 1334. User can refresh the existing web page to see the change.
