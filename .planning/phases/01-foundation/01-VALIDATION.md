---
phase: 01
slug: foundation
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-06-30
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.4.2 after the 01-01 package legitimacy checkpoint and dependency setup |
| **Config file** | `pyproject.toml` created by 01-01 |
| **Quick run command** | `python3 -m pytest tests/test_config.py tests/test_domain.py tests/test_ports.py -q` |
| **Full suite command** | `python3 -m pytest -q` |
| **Estimated runtime** | ~10 seconds |

---

## Sampling Rate

- **After every task commit:** Run `python3 -m pytest tests/test_config.py tests/test_domain.py tests/test_ports.py -q` when the relevant test files exist; for 01-01 before tests exist, run the dependency/import and skeleton checks in its task verification.
- **After every plan wave:** Run `python3 -m pytest -q`.
- **Before `$gsd-verify-work`:** Full suite must be green.
- **Max feedback latency:** 60 seconds.

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 1 | CFG-01 / CFG-02 / CFG-03 | T-01-SC | SUS package versions are human-approved before declaration or install | checkpoint | `python3 -c "import sys; print('package gate awaiting human verification')"` | ✅ | ⬜ pending |
| 01-01-02 | 01 | 1 | CFG-01 / CFG-02 / CFG-03 | T-01-SC | Approved dependencies are declared, installed, and importable before Wave 2 | setup/import | `python3 -m pytest --version && python3 -c "import pydantic, pydantic_settings"` | ✅ | ⬜ pending |
| 01-01-03 | 01 | 1 | CFG-01 / CFG-02 / CFG-03 | T-01-01 / T-01-02 / T-01-03 | `.env` is ignored; `.env.example` contains grouped placeholder-only variables | file check | `test -f .env.example && test -f .gitignore && git check-ignore .env` | ✅ | ⬜ pending |
| 01-02-01 | 02 | 2 | CFG-01 / CFG-02 / CFG-03 | T-01-04 / T-01-05 / T-01-06 / T-01-07 | Config safety tests specify fail-closed, redacted settings behavior | unit | `python3 -m pytest tests/test_config.py -q` | ❌ W0 | ⬜ pending |
| 01-02-02 | 02 | 2 | CFG-01 / CFG-02 / CFG-03 | T-01-04 / T-01-05 / T-01-06 / T-01-07 | Typed settings pass all config safety tests | unit | `python3 -m pytest tests/test_config.py -q` | ❌ W0 | ⬜ pending |
| 01-03-01 | 03 | 2 | CFG-01 / CFG-02 / CFG-03 | T-01-08 / T-01-09 / T-01-10 / T-01-11 | Domain and Protocol tests specify import/type shape and adapter absence | unit | `python3 -m pytest tests/test_domain.py tests/test_ports.py -q` | ❌ W0 | ⬜ pending |
| 01-03-02 | 03 | 2 | CFG-01 / CFG-02 / CFG-03 | T-01-08 / T-01-09 / T-01-10 / T-01-11 | Domain models and synchronous Protocols pass without adapter imports | unit | `python3 -m pytest tests/test_domain.py tests/test_ports.py -q` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `pyproject.toml` — package metadata, approved dependency pins, and pytest configuration.
- [ ] Dependency setup — after human package approval, run the project install/setup command from 01-01 so `pytest`, `pydantic`, and `pydantic_settings` are importable.
- [ ] `tests/test_config.py` — created by 01-02 before config implementation.
- [ ] `tests/test_domain.py` — created by 01-03 before domain implementation.
- [ ] `tests/test_ports.py` — created by 01-03 before ports implementation.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SUS package legitimacy approval | CFG-01 / CFG-02 / CFG-03 | Package gate requires operator review for packages marked SUS in research | Confirm `pydantic-settings==2.11.0`, `pydantic==2.13.4`, and `pytest==8.4.2` on PyPI and linked source repositories, then reply `approved` or describe concerns. |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies.
- [x] Sampling continuity: no 3 consecutive tasks without automated verify.
- [x] Wave 0 covers all MISSING references.
- [x] No watch-mode flags.
- [x] Feedback latency < 60s.
- [x] `nyquist_compliant: true` set in frontmatter.

**Approval:** pending
