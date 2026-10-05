---
quick_id: 261005-teq
status: complete
date: 2026-10-05
---

# Observation ages now include calendar years, months and days

Extended the shared web duration formatter to display `0년 1개월 2일 03:04:05`. Completed months are calculated from the saved observation timestamp in KST, with calendar month-end clamping and leap-year support. Remaining days and whole seconds follow; unknown timestamps/durations remain UNKNOWN. Source ages, heartbeat ages, leases and incident durations use the same format and matching labels. Numeric evidence and operational thresholds remain unchanged.

Validation: 85 existing web route/UI/alert-route tests passed. Direct checks covered zero, more than 24 hours, historical observation ages, January month-end, leap-day anniversary, mixed years/months/days, missing/nonfinite/invalid values, negative duration and fractional seconds.

Restarted only the tracked web server (PID 3318); alert observer PID 99863 remained running. Authenticated private HTTPS overview, workers, alerts and BROKER_TRUTH incident detail returned 200 and displayed the calendar format. The historical BROKER_TRUTH observation age rendered as `0년 0개월 27일 06:21:13` at verification time. No broker or LLM calls, trading activation, alert acknowledgement or source database changes were performed.

GSD quick planning and execution performed inline per the skill's spawn restriction fallback.
