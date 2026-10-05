---
quick_id: 261005-tor
status: complete
date: 2026-10-05
---

# Account display refresh and valuation support

Implemented the owner's approved account-screen follow-up inline through GSD quick. Added a dedicated `account_view` schema/reader and a `bot-account once/watch` mock-only balance worker. Protected credentials stay outside Git and the web process. The actual transport permits only fixed mock OAuth and balance GET with the expected account tuple and TR_ID; order/hashkey/real-domain requests are rejected. Shared token caching is reused; no LLM or trading service is constructed.

Persisted broker-supplied current price, evaluation, signed unrealized profit and percent return alongside each holding and account P/L. Nullable marks stay UNKNOWN; invalid account totals, duplicate identities, invalid quantities or incomplete pagination cannot replace the last complete snapshot. Every refresh outcome is saved atomically. Failed updates preserve the previous success across reader restarts.

Account/holding views prefer the display source for the same scope while retaining all legacy risk/order sources. Last complete holdings display outside today's history filter, with exact snapshot/holding drill-down and stale/missing/failure explanations. Cash from `dnca_tot_amt` is labeled 예수금. Source badges distinguish saved-record queries from KIS refresh results. ROADMAP/REQUIREMENTS now include the completed follow-up (UI-03/UI-04); the runbook documents commands and limits.

Validation: the broad affected suite passed 334 tests, covering web source/security/report/capability/installed-package boundaries plus KIS auth/order/broker and portfolio contracts. The final affected route/UI/alert-route/account suite passed 97 tests after the last presentation changes and the added no-collection regression. Offline regressions cover negative P/L, missing/nonfinite marks, zero balances, invalid identities/pages, prohibited order/real/account transport, scope mismatch, old holding visibility, exact details, failed refresh retention and uncollected-versus-failed states.

Runtime: verified protected mock credentials against the registered legacy account scope, successfully queried the actual mock balance and saved 7 holdings with all four valuation fields present. Registered `account-display-mock` in both protected web configs. A separate 60-second refresh worker is running; no login/reboot autostart was installed. Authenticated private HTTPS overview/account/holdings/workers/alerts/reports, holding detail and holding API returned 200; default holdings showed 7 priced rows and the API reported SUCCESS. Legacy trading/source database SHA256 digests matched the before-deployment baseline. Existing alert observer remained running and retains its original sources and critical episodes.

The old tracked web PID was already absent during deployment; started the web with the new configuration and verified its private HTTPS listener. No orders, broker reconciliation, alert acknowledgement, freeze/latch release, real-mode activation or paid LLM calls were performed. Current prices are saved balance-query marks, not a streaming quote feed.
