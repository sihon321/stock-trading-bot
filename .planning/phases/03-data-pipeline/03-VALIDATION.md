---
phase: 03
slug: data-pipeline
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-01
---

# Phase 03 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.x |
| **Config file** | `pyproject.toml` / `setup.cfg` |
| **Quick run command** | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest tests/test_indicators.py tests/test_screener.py tests/test_pykrx_adapter.py tests/test_kis_auth.py tests/test_kis_quote.py tests/test_naver_news.py tests/test_data_source.py -q` |
| **Full suite command** | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` |
| **Estimated runtime** | ~10-30 seconds for mocked unit suite |

---

## Sampling Rate

- **After every task commit:** Run `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest tests/test_indicators.py tests/test_screener.py tests/test_pykrx_adapter.py tests/test_kis_auth.py tests/test_kis_quote.py tests/test_naver_news.py tests/test_data_source.py -q` once the referenced files exist.
- **After every plan wave:** Run `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q`
- **Before `$gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds for mocked tests; live-provider checks are manual-only

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 03-00-01 | 00 | 0 | DATA-01/DATA-02/DATA-03/DATA-04/DATA-05 | — | Runtime/dependency compatibility is explicit before adapter work starts | config/unit | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest tests/test_config.py -q` | ❌ W0 | ⬜ pending |
| 03-01-01 | 01 | 1 | DATA-01 | — | Empty/stale/holiday OHLCV cannot create actionable context | unit | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest tests/test_pykrx_adapter.py -q` | ❌ W0 | ⬜ pending |
| 03-01-02 | 01 | 1 | DATA-02 | — | Indicators include MAs, RSI, volatility metric, and volume ratio with NaN/warm-up handling | unit | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest tests/test_indicators.py -q` | ❌ W0 | ⬜ pending |
| 03-02-01 | 02 | 2 | DATA-05 | — | Screener hard-excludes unsafe tickers before ranking | unit | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest tests/test_screener.py -q` | ❌ W0 | ⬜ pending |
| 03-03-01 | 03 | 2 | DATA-03 | — | KIS token is cached/shared and failures become unavailable price, not retries without bound | unit | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest tests/test_kis_auth.py tests/test_kis_quote.py -q` | ❌ W0 | ⬜ pending |
| 03-04-01 | 04 | 2 | DATA-04 | — | Naver failures and disallowed/unapproved scraping degrade to empty sanitized news | unit | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest tests/test_naver_news.py -q` | ❌ W0 | ⬜ pending |
| 03-05-01 | 05 | 3 | DATA-01/DATA-02/DATA-03/DATA-04/DATA-05 | — | DataSource emits compact DataContext only when source policy permits it | integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest tests/test_data_source.py tests/test_ports.py -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_pykrx_adapter.py` - stale/empty/holiday OHLCV and trading-date assertions.
- [ ] `tests/test_indicators.py` - MAs, RSI, ATR/historical volatility, and volume-ratio transform coverage.
- [ ] `tests/test_screener.py` - configurable markets/caps, liquidity floor, abnormal ticker exclusion, and ranking policy.
- [ ] `tests/test_kis_auth.py` - cached shared token, expiry margin, bounded retry, and failure normalization.
- [ ] `tests/test_kis_quote.py` - KIS price request mapping and unavailable-price behavior.
- [ ] `tests/test_naver_news.py` - compliance gate, parser failure, sanitizer, and compact rendered news.
- [ ] `tests/test_data_source.py` - orchestrator integration, `SKIP_CANDIDATE`, `FORCE_HOLD`, and compact `DataContext`.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| KIS token TTL and rate limits for the active account | DATA-03 | Public docs/samples expose different token contexts; account portal is authoritative | Operator checks KIS portal for active account token TTL/rate limits before enabling live quote calls; record values in config/test fixture notes. |
| Naver Finance scraping acceptable-use decision | DATA-04 | `robots.txt` currently disallows general crawlers; operator policy/legal acceptance cannot be automated | Operator explicitly approves or disables Naver adapter. If not approved, adapter must return empty news and continue. |
| pykrx adjusted/unadjusted default | DATA-01/DATA-02/DATA-05 | Project strategy choice affects indicator/screener semantics | Planner/executor records chosen adjusted-price default after verifying current pykrx behavior. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s for mocked tests
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
