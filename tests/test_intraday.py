from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from conftest import make_settings
from trading_bot.domain import Money
from trading_bot.intraday import (
    IntradayIterationOutcome,
    IntradaySessionPhase,
    run_intraday_check,
    run_intraday_watch,
    session_phase_at,
)
from trading_bot.portfolio import PortfolioCompleteness
from trading_bot.risk import RiskConfig
from test_exit_manager import _snapshot


KST = ZoneInfo("Asia/Seoul")


@pytest.mark.parametrize(
    ("hour", "minute", "phase"),
    [
        (8, 59, IntradaySessionPhase.PREFLIGHT_READ_ONLY),
        (9, 0, IntradaySessionPhase.ACTIVE),
        (15, 19, IntradaySessionPhase.ACTIVE),
        (15, 20, IntradaySessionPhase.RECONCILE_ONLY),
        (15, 29, IntradaySessionPhase.RECONCILE_ONLY),
        (15, 30, IntradaySessionPhase.TERMINAL),
    ],
)
def test_session_phase_half_open_matrix(hour, minute, phase) -> None:
    assert session_phase_at(datetime(2026, 9, 4, hour, minute, tzinfo=KST)) is phase


def test_check_uses_new_snapshot_and_llm_free_risk_exit() -> None:
    calls: list[str] = []
    lease = type("Lease", (), {"assert_active_owner": lambda self: calls.append("lease")})()

    result = run_intraday_check(
        clock=lambda: datetime(2026, 9, 4, 10, 0, tzinfo=KST),
        snapshot_reader=lambda: (calls.append("snapshot"), _snapshot())[1],
        quote_reader=lambda ticker: Money(80_000.0, "KRW"),
        risk_config=RiskConfig(0.05, 0.10),
        lease=lease,
        exit_submitter=lambda candidate, price: calls.append("post"),
        audit_sink=lambda result: calls.append(result.outcome.value),
    )

    assert result.outcome is IntradayIterationOutcome.COMPLETED
    assert calls == ["snapshot", "lease", "lease", "post", "COMPLETED"]


def test_incomplete_iteration_is_blocked_and_next_watch_iteration_queries_again() -> None:
    snapshots = iter(
        (
            replace(_snapshot(), completeness=PortfolioCompleteness.INCOMPLETE),
            _snapshot(),
        )
    )
    times = iter(
        (
            datetime(2026, 9, 4, 10, 0, tzinfo=KST),
            datetime(2026, 9, 4, 10, 1, tzinfo=KST),
        )
    )
    audits = []
    posts = []
    lease = type("Lease", (), {"assert_active_owner": lambda self: None})()

    watch = run_intraday_watch(
        clock=lambda: next(times),
        sleeper=lambda seconds: None,
        stop_requested=lambda: False,
        snapshot_reader=lambda: next(snapshots),
        quote_reader=lambda ticker: Money(80_000.0, "KRW"),
        risk_config=RiskConfig(0.05, 0.10),
        lease=lease,
        exit_submitter=lambda candidate, price: posts.append(candidate),
        audit_sink=audits.append,
        interval_seconds=60,
        max_iterations=2,
    )

    assert [item.outcome for item in watch.iterations] == [
        IntradayIterationOutcome.BLOCKED,
        IntradayIterationOutcome.COMPLETED,
    ]
    assert len({item.iteration_id for item in watch.iterations}) == 2
    assert len(posts) == 1


def test_cutoff_reconciles_without_post_and_terminal_exits() -> None:
    phases = iter(
        (
            datetime(2026, 9, 4, 15, 20, tzinfo=KST),
            datetime(2026, 9, 4, 15, 30, tzinfo=KST),
        )
    )
    reconciles = []
    watch = run_intraday_watch(
        clock=lambda: next(phases),
        sleeper=lambda seconds: None,
        stop_requested=lambda: False,
        snapshot_reader=lambda: pytest.fail("cutoff must not start a mutable iteration"),
        quote_reader=lambda ticker: pytest.fail("cutoff must not quote"),
        risk_config=RiskConfig(0.05, 0.10),
        lease=object(),
        exit_submitter=lambda candidate, price: pytest.fail("cutoff must not POST"),
        audit_sink=lambda result: None,
        reconcile=lambda: reconciles.append("reconciled"),
        interval_seconds=60,
    )

    assert reconciles and set(reconciles) == {"reconciled"}
    assert watch.final_phase is IntradaySessionPhase.TERMINAL


def test_stop_request_interrupts_before_new_iteration_and_reconciles_then_releases() -> None:
    sequence = []
    lease = type(
        "Lease",
        (),
        {
            "release_after_reconciliation": lambda self, **kwargs: (
                kwargs["reconcile_submitted"](), sequence.append("release")
            )
        },
    )()
    watch = run_intraday_watch(
        clock=lambda: datetime(2026, 9, 4, 10, 0, tzinfo=KST),
        sleeper=lambda seconds: None,
        stop_requested=lambda: True,
        snapshot_reader=lambda: pytest.fail("stop must prevent next snapshot"),
        quote_reader=lambda ticker: pytest.fail("stop must prevent quote"),
        risk_config=RiskConfig(0.05, 0.10),
        lease=lease,
        exit_submitter=lambda candidate, price: pytest.fail("stop must prevent POST"),
        audit_sink=lambda result: sequence.append("audit"),
        reconcile=lambda: sequence.append("reconcile"),
    )
    assert sequence == ["reconcile", "release"]
    assert watch.interrupted is True


def test_intraday_settings_defaults_and_bounds() -> None:
    settings = make_settings()
    assert settings.intraday_watch_interval_seconds == 60
    assert settings.intraday_min_interval_seconds == 60
    with pytest.raises(ValidationError):
        make_settings(intraday_watch_interval_seconds=59)
    for field in (
        "intraday_reconciliation_timeout_seconds",
        "intraday_reconciliation_poll_seconds",
        "mutation_lease_heartbeat_seconds",
        "intraday_long_open_warning_seconds",
    ):
        with pytest.raises(ValidationError):
            make_settings(**{field: 0})
