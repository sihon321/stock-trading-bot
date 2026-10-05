---
status: resolved
trigger: "invalid request 뜨는데"
created: 2026-10-05
updated: 2026-10-05
---

# Tailscale login INVALID_REQUEST

## Symptoms

- Expected: MacBook opens the Tailscale HTTPS login and signs in as the provisioned operator.
- Actual: HTTPS GET /login returns HTTP 400 and INVALID_REQUEST.
- Timeline: Tailnet Serve was activated after the local web server was started.
- Reproduction: GET https://oceano-macmini.tail667338.ts.net/login.

## Current Focus

- hypothesis: The running web server still loads local-only web.json instead of the prepared private HTTPS config.
- test: Compare the running command and protected nonsecret settings, then restart with validated web-tailscale.json and repeat live HTTPS login.
- expecting: Exact HTTPS host/origin and trusted proxy make login succeed while the direct HTTP boundary remains closed.
- next_action: Resolved; owner should reload the HTTPS login page to obtain fresh CSRF state.

## Evidence

- Actual Serve status: tailnet-only HTTPS proxy to http://127.0.0.1:8765.
- Running PID 88445 loads ~/.config/stock-trading-bot/operator/config/web.json.
- web.json has default loopback allowed hosts and private_mode false.
- Prepared web-tailscale.json contains exact ts.net host/origin, HTTPS termination and one trusted 127.0.0.1 proxy.
- Live HTTPS GET /login returns HTTP 400 with INVALID_REQUEST before any password submission.

## Resolution

- root_cause: The live deployment had not switched from local-only config after Serve activation.
- fix: Restarted only the tracked owned web PID using validated web-tailscale.json; no application source changes required.
- verification: Actual certificate-valid HTTPS GET /login returns 200; valid CSRF/password POST redirects, authenticated dashboard returns 200. Cookie has Secure/HttpOnly/SameSite=Lax. Direct local HTTP returns 400 as required. Listener remains loopback only. MacBook-specific acceptance has not been independently observed.
