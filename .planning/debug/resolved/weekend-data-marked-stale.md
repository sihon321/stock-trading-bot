---
status: resolved
trigger: "bot run marks 20260710 pykrx data stale because it expects 20260712"
created: 2026-07-13T13:07:58+09:00
updated: 2026-07-20T10:52:00+09:00
---

# Weekend data marked stale

## Symptoms

- expected_behavior: The latest confirmed KRX trading day should be accepted; on Monday before a newer completed daily bar is available, 2026-07-10 should not be rejected in favor of Sunday 2026-07-12.
- actual_behavior: All five candidates are skipped as stale because observed 20260710 is compared with expected 20260712.
- error_messages: `DATA WARNING ... status=STALE action=SKIP_CANDIDATE reason=latest data date is before the expected trading date observed=20260710 expected=20260712`
- timeline: Observed in the latest `bot run` on 2026-07-13 KST; prior behavior is unknown.
- reproduction: Run `bot run` under the same live-data conditions.

## Current Focus

- hypothesis: CONFIRMED — an all-zero pykrx holiday frame was normalized to an empty but AVAILABLE result, causing Sunday to be accepted as the previous trading day.
- test: COMPLETE — focused tests, exact combined reproduction, full suite, and committed-file integrity all passed.
- expecting: The session manager may commit the archived debug record without any implementation changes.
- next_action: No debugging work remains; the session manager owns the docs-only commit for this archived record.
- reasoning_checkpoint:
    hypothesis: "An all-zero pykrx whole-market holiday response causes the false stale warning because the old normalizer returns an empty frame as AVAILABLE and the old calendar treats any AVAILABLE non-None frame as a trading day."
    confirming_evidence:
      - "The pre-fix normalizer filters non-positive whole-market rows at lines 173-184 but has no post-filter empty check before returning AVAILABLE."
      - "The pre-fix calendar marks any AVAILABLE result with a non-None frame true, so Sunday becomes the immediately previous trading day."
      - "CLI runtime construction passes completed_bar_cutoff directly as both expected_date and accepted_latest_date, explaining expected=20260712 in the warning."
    falsification_test: "A combined all-zero-Sunday/valid-Friday adapter test would refute the hypothesis if the current policy still returned Sunday, or if a provider exception were treated as a closure instead of unknown."
    fix_rationale: "Rejecting a whole-market frame that becomes empty after OHLCV validation removes the false AVAILABLE signal at its source; additionally requiring a non-empty AVAILABLE frame in ObservedKRXCalendar makes the calendar robust to malformed adapters while preserving provider failures as unknown."
    blind_spots: "Verification is deterministic and offline; it does not call live pykrx/KRX, so upstream response-shape changes beyond empty/all-zero frames remain an operational risk."
- tdd_checkpoint:

## Evidence

- timestamp: 2026-07-20T10:43:30+09:00
  checked: Commit 628f5e6 metadata and exact diff.
  found: The commit exists and changes only trading_bot/data_source.py, trading_bot/pykrx_adapter.py, tests/test_market_cycle.py, and tests/test_pykrx_adapter.py; it adds empty-frame calendar handling and all-zero whole-market normalization tests.
  implication: The reported implementation boundary matches the handoff and can be verified without rewriting the fix.
- timestamp: 2026-07-20T10:43:52+09:00
  checked: Pre-fix adapter normalization, pre-fix ObservedKRXCalendar, and CLI cutoff propagation.
  found: Before 628f5e6 an all-zero whole-market frame was filtered to zero rows and still returned AVAILABLE; the calendar accepted that non-None frame as a trading day; CLI then used that date as the daily-data cutoff.
  implication: This directly explains observed=20260710 versus expected=20260712 on Monday 2026-07-13.
- timestamp: 2026-07-20T10:45:00+09:00
  checked: Focused test invocation via `uv run pytest`.
  found: The shell reports `uv: command not found`, so no tests executed.
  implication: Verification must use the repository's available Python/pytest runner; this is not evidence against the implementation.
- timestamp: 2026-07-20T10:45:05+09:00
  checked: Available local test runners.
  found: The repository contains `.venv/bin/pytest` and `.python-userbase/bin/pytest`; system Python is 3.9.6.
  implication: The focused and full suites can be run from the checked-in workspace environment without installing dependencies.
- timestamp: 2026-07-20T10:47:00+09:00
  checked: `.venv/bin/pytest tests/test_market_cycle.py tests/test_pykrx_adapter.py`.
  found: 38 tests passed in 0.45 seconds under Python 3.14.3 and pytest 8.4.2.
  implication: The focused regression coverage and adjacent adapter/calendar fail-safe behavior are green.
- timestamp: 2026-07-20T10:48:00+09:00
  checked: Combined deterministic adapter/calendar reproduction for requested date 2026-07-13.
  found: All-zero 2026-07-12 and 2026-07-11 frames classified closed, valid 2026-07-10 classified open, and completed_bar_cutoff returned 20260710 with available=True.
  implication: The exact weekend boundary that produced expected=20260712 now resolves to Friday 20260710.
- timestamp: 2026-07-20T10:50:00+09:00
  checked: Complete `.venv/bin/pytest` suite.
  found: 579 tests passed in 16.22 seconds, including CLI, execution, risk, soak, and reconciliation coverage.
  implication: The fix introduces no detected regression and preserves the broader Phase 9/safety behavior covered by the suite.
- timestamp: 2026-07-20T10:51:00+09:00
  checked: Affected working-tree files against implementation commit 628f5e6 and repository status.
  found: The four affected files have no diff from 628f5e6; HEAD is docs commit 5265e52 on top of 628f5e6, and only `.planning/debug/` is untracked.
  implication: Verification did not duplicate, amend, or otherwise alter the committed implementation.

## Eliminated

- hypothesis: The expected date is calculated by subtracting one calendar day without consulting KRX data.
  evidence: MarketCyclePolicy delegates to ObservedKRXCalendar.previous_trading_day; Sunday was selected because malformed all-zero holiday data was misclassified as AVAILABLE, not because of calendar arithmetic.
  timestamp: 2026-07-20T10:43:52+09:00

## Resolution

- root_cause: On closed dates pykrx can return an all-zero whole-market DataFrame. The old whole-market normalizer filtered all invalid rows but returned the now-empty frame as AVAILABLE, and ObservedKRXCalendar treated any AVAILABLE non-None frame as proof of a trading day. Consequently Sunday 2026-07-12 was selected as Monday's completed-bar cutoff and valid Friday data was marked stale.
- fix: Commit 628f5e6 rejects whole-market frames that become empty after validation and requires AVAILABLE calendar evidence to contain a non-empty frame, while continuing to classify explicit empty/no-OHLCV results as closures and unrelated provider failures as unknown.
- verification: Focused adapter/calendar suite passed 38/38; a combined Monday 20260713 reproduction resolved all-zero weekend dates to Friday 20260710; the full suite passed 579/579 under Python 3.14.3 and pytest 8.4.2.
- files_changed: [trading_bot/data_source.py, trading_bot/pykrx_adapter.py, tests/test_market_cycle.py, tests/test_pykrx_adapter.py]
