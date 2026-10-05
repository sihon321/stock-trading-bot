---
quick_id: 261005-l0g
status: incomplete
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
