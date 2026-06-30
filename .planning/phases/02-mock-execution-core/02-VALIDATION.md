---
phase: 02
slug: mock-execution-core
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-07-01
---

# Phase 2 - Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.4.2 |
| **Config file** | `pyproject.toml` |
| **Quick run command** | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest tests/test_signal_parser.py tests/test_risk.py tests/test_execution.py tests/test_mock_broker.py -q` |
| **Full suite command** | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest tests/test_signal_parser.py tests/test_risk.py tests/test_execution.py tests/test_mock_broker.py -q` once the relevant test files exist.
- **After every plan wave:** Run `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q`.
- **Before `$gsd-verify-work`:** Full suite must be green.
- **Max feedback latency:** 60 seconds.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 1 | EXEC-01 | T-02-01 | Implements parser contract for strict validation: valid JSON becomes `ParsedSignal`, malformed/schema-invalid payloads raise `SignalParseError`, and parser thresholds stay out of parsing | unit | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest tests/test_signal_parser.py -q` | No, W0 | pending |
| 02-01-02 | 01 | 1 | EXEC-01 | T-02-01 / T-02-02 | Hardens parser diagnostics and import boundary: canonical `LLMSignal`, raw input, ignored-field diagnostics, and no forbidden external/adapter imports | unit | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest tests/test_signal_parser.py -q` | No, W0 | pending |
| 02-02-01 | 02 | 2 | EXEC-01 / EXEC-02 / EXEC-03 / RISK-01 / RISK-02 / RISK-03 | T-02-04 | Adds execution and risk settings defaults for independent BUY/SELL thresholds, sizing caps, stop-loss/take-profit percentages, and daily-loss threshold | unit | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest tests/test_config.py -q` | No, W0 | pending |
| 02-02-02 | 02 | 2 | RISK-01 / RISK-02 / RISK-03 | T-02-03 / T-02-05 | Implements pure risk decisions: stop-loss, take-profit, and daily-loss checks are deterministic, LLM-independent, and allow SELL/risk exits | unit | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest tests/test_risk.py -q` | No, W0 | pending |
| 02-02-03 | 02 | 2 | EXEC-01 / EXEC-02 / EXEC-03 / RISK-02 / RISK-03 | T-02-03 / T-02-04 / T-02-06 | Implements execution rules and risk override core: parser failures become HOLD, thresholds and sizing are enforced, and risk suppresses conflicting LLM actions before broker mutation | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest tests/test_execution.py tests/test_risk.py tests/test_signal_parser.py -q` | No, W0 | pending |
| 02-03-01 | 03 | 3 | EXEC-05 | T-02-09 / T-02-10 | Implements in-memory `MockBroker` satisfying `Broker`, with deterministic order IDs and state mutation only through `place_order` | unit | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest tests/test_mock_broker.py -q` | No, W0 | pending |
| 02-03-02 | 03 | 3 | EXEC-05 / RISK-02 | T-02-07 / T-02-08 | Adds dry-run side-effect gate and audit chain: would-be orders and risk overrides are recorded while `Broker.place_order`, cash, positions, and order history remain unchanged | unit/integration | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest tests/test_execution.py tests/test_mock_broker.py -q` | No, W0 | pending |
| 02-03-03 | 03 | 3 | EXEC-01 / EXEC-02 / EXEC-03 / EXEC-05 / RISK-01 / RISK-02 / RISK-03 | T-02-07 / T-02-08 / T-02-09 / T-02-10 | Verifies full mock-safe Phase 2 chain: parse -> risk -> execute -> log stays adapter-free, dry-run safe, and externally safe | suite | `PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest tests/test_signal_parser.py tests/test_risk.py tests/test_execution.py tests/test_mock_broker.py -q && PYTHONUSERBASE="$PWD/.python-userbase" python3 -m pytest -q` | No, W0 | pending |

*Status values: pending, green, red, flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_signal_parser.py` - parser validity, extra-field diagnostics, and malformed/schema-invalid no-trade boundary.
- [ ] `tests/test_risk.py` - stop-loss, take-profit, risk precedence inputs, and daily-loss BUY gate.
- [ ] `tests/test_execution.py` - confidence thresholds, sizing cap, dry-run, risk override logging, and end-to-end chain.
- [ ] `tests/test_mock_broker.py` - in-memory broker state, `Broker` Protocol conformance, and no external calls.
- [ ] Import-boundary assertions - parser, risk, execution, and mock broker must not import KIS, LLM SDKs, `pykrx`, `requests`, `httpx`, or future concrete adapters.

---

## Manual-Only Verifications

All phase behaviors have automated verification.

---

## Validation Sign-Off

- [x] All tasks have automated verify or Wave 0 dependencies.
- [x] Sampling continuity: no 3 consecutive tasks without automated verify.
- [x] Wave 0 covers all MISSING references.
- [x] No watch-mode flags.
- [x] Feedback latency < 60s.
- [x] `nyquist_compliant: true` set in frontmatter.

**Approval:** pending
