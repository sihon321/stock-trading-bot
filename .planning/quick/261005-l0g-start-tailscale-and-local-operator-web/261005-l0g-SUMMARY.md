---
quick_id: 261005-l0g
status: complete
---
# Local web running; Tailscale authentication pending

- Opened Tailscale.app and ran the bundled CLI `up`. Backend reported Logged out; opened its authentication page for the owner. Network-service Connected alone does not establish authenticated tailnet access.
- Reused the already installed documented Python userbase web dependencies; no package installation or source changes were needed.
- Created owner-only operator config, operations, artifacts, credentials and log paths beneath `~/.config/stock-trading-bot/operator`. Provisioned username `operator` with a random dedicated password stored only in the protected local credentials/login.txt; no credential contents are recorded here.
- Started `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m trading_bot.web_cli serve --config "$HOME/.config/stock-trading-bot/operator/config/web.json"` on 127.0.0.1:8765 and opened /login in the default browser.
- Live checks: / returns 302 to /login; /login returns 200; valid CSRF/password login and authenticated overview return 200. Listener is loopback only.
- No saved-evidence resources were registered because no deployment configuration or positively attributed registration existed. Initial evidence screens therefore remain UNKNOWN/unavailable.

Pending: owner must complete Tailscale login. No Tailscale Serve config exists yet; fixed private HTTPS host/origin and proxy configuration requires the actual authenticated tailnet hostname. External phone/Mac access remains unverified. No trading service was started.

## Resume: MacBook access (2026-10-05)

Tailscale authentication is now complete. Local node `oceano-macmini` has IP 100.92.151.80 and DNS name oceano-macmini.tail667338.ts.net. A second macOS peer is active on the same tailnet. The earlier web process had stopped; restarted Waitress detached with a separate session, stdin closed and owner-only file logging. Live /login returns HTTP 200 and the listener remains 127.0.0.1:8765.

Prepared and validated protected `~/.config/stock-trading-bot/operator/config/web-tailscale.json` using the exact HTTPS origin/host and one trusted loopback proxy. Existing credentials and registered evidence remain unchanged. This configuration is not active until the private proxy is enabled.

`tailscale serve --bg --https=443 http://127.0.0.1:8765` reports Serve is not enabled on this tailnet; opened its exact feature activation URL in the owner browser. Awaiting owner activation. After activation, restart the tracked local web PID using web-tailscale.json and verify actual certificate-valid HTTPS login through Serve. MacBook device acceptance remains pending. Direct HTTP at the Tailscale IP is not configured.

## Final deployment and login fix (2026-10-05)

Tailnet Serve activation is complete. The owner reported INVALID_REQUEST because the running app still loaded web.json and rejected the actual HTTPS host. Reproduced the exact HTTP 400 before password entry and restarted only the tracked web process with the already prepared validated web-tailscale.json. Runtime remains detached and logs to the protected local web-server.log.

Actual certificate-valid HTTPS checks at https://oceano-macmini.tail667338.ts.net: login GET 200, valid CSRF/password POST redirects, authenticated dashboard 200, session cookie Secure/HttpOnly/SameSite=Lax. Direct HTTP stays rejected and the upstream listener remains 127.0.0.1:8765. Existing operator credentials were reused. No source changes, trading process activation or broader network listeners were introduced. No saved evidence was fabricated or registered.

Owner next step: reload the exact HTTPS login URL on the Tailscale-connected MacBook. Remote MacBook acceptance is not independently observed. Debug record: ../../debug/resolved/tailscale-invalid-request.md.

## Browser login POST regression fix (2026-10-05)

The owner later supplied a screenshot showing POST /login HTTP 400 at the correct HTTPS origin. Temporary protected deployment diagnostics collected only fixed rejection codes and boolean matches, proving CSRF_MISMATCH on repeated owner submissions. This was distinct from the earlier local-host deployment issue and a separate password AUTH_FAILED event.

Reproduced a browser-like sequence: GET login, fetch favicon and follow its anonymous redirect, then submit the original visible login form. The unconditional anonymous session.clear() replaced the cookie CSRF state. Preserved anonymous prelogin state while retaining session clearing for any presented invalid/expired operator token and existing login/logout rotation. CSRF and origin validation remain enabled.

Added four regression paths (favicon, Apple icon, other page and protected API), all failing before the fix. Focused authentication/security/route suite: 71 passed. Restarted normal production Waitress CLI and verified the same actual HTTPS sequence through Serve: pending cookie unchanged, unauthenticated API 401, original login form POST 303 and dashboard 200. Secure session cookie flags retained. Temporary diagnostic wrapper is stopped. Debug record: ../../debug/resolved/tailscale-login-post.md. Owner refresh and MacBook confirmation requested.
