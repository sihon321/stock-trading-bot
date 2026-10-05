---
status: resolved
trigger: "요래 뜨는데 invalid request"
created: 2026-10-05
updated: 2026-10-05
---

# Tailscale login POST rejected on owner MacBook

## Symptoms

- Expected: Login form POST creates an operator session.
- Actual: Owner screenshot shows POST /login returning HTTP 400 INVALID_REQUEST at the exact HTTPS hostname and Tailscale address :443.
- Timeline: After the initial host configuration fix; the request in the screenshot occurred at 07:25:30 UTC.
- Reproduction: Owner browser login POST. Fresh server-side HTTPS GET/CSRF/password POST succeeds.

## Current Focus

- hypothesis: Anonymous background requests clear the entire signed Flask session, replacing the CSRF state belonging to the open login form.
- test: Reproduce login GET, unauthenticated favicon GET/redirect, then POST the original visible form; run four regression paths and existing authentication/security/route tests.
- expecting: Background requests preserve anonymous CSRF state; invalid or expired presented operator sessions remain cleared, and successful login/logout still rotate sessions.
- next_action: Resolved in code and deployed runtime; owner should refresh the existing login page and confirm MacBook acceptance.

## Evidence

- Exact hostname, HTTPS scheme and Tailscale remote address are correct in the screenshot.
- Actual failure is HTTP 400, which occurs before password authentication; a prior AUTH_FAILED (401) is a separate event.
- Tailnet peer ping and live TLS-verified server GET/POST/dashboard succeed.
- The runtime uses private HTTPS config with one loopback proxy; upstream listener is loopback only.
- Bounded diagnostics from owner retries at 16:32:54, 16:33:02, 16:33:14 and 16:33:37 KST show CSRF_MISMATCH. Host, HTTPS, Origin, Referer, session cookie and form token presence pass.
- Reproduced actual HTTPS flow: favicon GET redirects to login, replaces the session cookie and makes the original visible form POST return 400.
- All four regression cases fail before the fix: favicon, Apple touch icon, second page and protected API request before login submission.

## Resolution

- root_cause: The anonymous guard unconditionally clears the session even without an operator token. Background icon/other-tab/API requests invalidate the pending login CSRF token.
- fix: Preserve anonymous session state; clear the session only when an invalid/expired operator token was actually presented. Keep CSRF, origin, HTTPS, host, authentication and session-rotation checks.
- verification: 71 authentication/security/route tests pass, including four regressions proven failing before the fix. Actual certificate-valid HTTPS original-form POST succeeds after favicon, Apple touch icon, second-page and unauthenticated API requests; login returns 303 and dashboard 200. Secure/HttpOnly/SameSite=Lax retained. Normal production CLI restarted; temporary diagnostic bootstrap is no longer running. Owner MacBook confirmation remains pending.
