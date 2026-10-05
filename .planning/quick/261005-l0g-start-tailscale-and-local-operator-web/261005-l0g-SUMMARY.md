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
