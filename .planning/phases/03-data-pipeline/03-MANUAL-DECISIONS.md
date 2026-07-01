# Phase 3 Manual Decisions

**Recorded:** 2026-07-01
**Plan:** 03-01
**Gate:** Task 1 — `checkpoint:human-verify` (blocking-human). Resolved by operator before dependency lock-in.

These decisions gate DATA-01 through DATA-05 and drive the Phase 3 `Settings`
defaults. They must be recorded before any Phase 3 dependency install or
live-source enablement.

---

## 1. SUS Package Legitimacy Approval (T-03-01-SC, DATA-01/02/04)

Operator verified each pin on PyPI and its source repository before install.
**All six packages APPROVED. No package rejected.**

| Package | Pin | Reviewed | Status |
|---------|-----|----------|--------|
| `pykrx` | `1.2.8` | Yes (PyPI + source repo) | APPROVED |
| `ta` | `0.11.0` | Yes (PyPI + source repo) | APPROVED |
| `httpx` | `0.28.1` | Yes (PyPI + source repo) | APPROVED |
| `beautifulsoup4` | `4.15.0` | Yes (PyPI + source repo) | APPROVED |
| `lxml` | `6.1.1` | Yes (PyPI + source repo) | APPROVED |
| `tenacity` | `9.1.4` | Yes (PyPI + source repo) | APPROVED |

Because no package was rejected, the plan proceeds to declare and install these
pins (Task 2). Transitive deps `pandas` (>=2.2,<3.0) and `numpy` are pulled by
`pykrx`/`ta`.

---

## 2. KIS Token TTL & Rate-Limit Policy (DATA-03, T-03-01-T)

Standard KIS REST defaults for the mock (모의투자) account:

- **Access token TTL:** standard daily token (~86400s / 24h). The exact expiry
  is discovered from the token response at runtime; the app does not hardcode a
  TTL for validity — it uses the response's expiry.
- `kis_token_refresh_margin_seconds` = **600** (refresh 10 min before expiry).
- `kis_min_interval_seconds` = **0.5** (~2 requests/sec — conservative for the
  mock account).
- `kis_max_retries` = **3**.
- `kis_retry_backoff_seconds` = **1.0**.

---

## 3. Naver Finance Scraping Acceptable Use (DATA-04)

**DISABLED by default.** `naver_news_enabled = False`.

Rationale: Naver Finance `robots.txt` disallows general crawlers. The news
adapter must fail soft to empty sanitized news when disabled, disallowed,
throttled, or when DOM parsing fails. Enabling scraping is a deliberate future
opt-in, not the default.

---

## 4. pykrx Price Policy (DATA-01 / DATA-02 / DATA-05)

**ADJUSTED prices (수정주가).** `ohlcv_adjusted = True`.

Daily OHLCV and indicator inputs use split/dividend-adjusted prices so
technical indicators and screening are computed on a consistent price series.
