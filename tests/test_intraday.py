from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError
from typer.testing import CliRunner

from conftest import make_settings
from trading_bot.domain import Money
from trading_bot.intraday import (
    IntradayIterationOutcome,
    IntradaySessionPhase,
    run_intraday_check,
    run_intraday_watch,
    session_phase_at,
)
from trading_bot.mutation_lease import (
    LeaseOwnershipLost,
    acquire_mutation_lease,
)
from trading_bot.portfolio_store import connect_portfolio_store
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
        terminalize=lambda: reconciles.append("terminalized"),
        interval_seconds=60,
    )

    assert reconciles == ["reconciled", "terminalized", "reconciled"]
    assert watch.final_phase is IntradaySessionPhase.TERMINAL


def test_stop_request_interrupts_before_new_iteration_and_reconciles_then_releases() -> None:
    sequence = []
    lease = type(
        "Lease",
        (),
        {
            "release_after_reconciliation": lambda self, **kwargs: (
                kwargs["terminalize_cycle"](),
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
        terminalize=lambda: sequence.append("terminalize"),
    )
    assert sequence == ["terminalize", "reconcile", "release"]
    assert watch.interrupted is True


def test_stop_after_snapshot_terminalizes_before_any_exit_submission() -> None:
    sequence: list[str] = []
    lease = type("Lease", (), {"assert_active_owner": lambda self: sequence.append("lease")})()
    flags = iter((False, True))

    result = run_intraday_check(
        clock=lambda: datetime(2026, 9, 4, 10, 0, tzinfo=KST),
        snapshot_reader=lambda: (sequence.append("snapshot"), _snapshot())[1],
        quote_reader=lambda ticker: Money(80_000.0, "KRW"),
        risk_config=RiskConfig(0.05, 0.10),
        lease=lease,
        exit_submitter=lambda candidate, price: sequence.append("post"),
        audit_sink=lambda item: sequence.append(item.outcome.value),
        stop_requested=lambda: next(flags),
        terminalize=lambda item: sequence.append("terminalize"),
        reconcile=lambda: sequence.append("reconcile"),
    )

    assert result.outcome is IntradayIterationOutcome.INTERRUPTED
    assert result.reason_code == "STOP_REQUESTED"
    assert "post" not in sequence
    assert sequence[-2:] == ["terminalize", "INTERRUPTED"]


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


def test_cli_exposes_check_watch_and_rejects_short_interval_before_runtime(monkeypatch) -> None:
    from trading_bot import cli

    calls = []
    monkeypatch.setattr(cli, "_intraday_command_runner", lambda mode, interval: calls.append((mode, interval)))
    runner = CliRunner()

    root_help = runner.invoke(cli.app, ["--help"])
    group_help = runner.invoke(cli.app, ["intraday", "--help"])
    watch_help = runner.invoke(cli.app, ["intraday", "watch", "--help"])
    invalid = runner.invoke(cli.app, ["intraday", "watch", "--interval-seconds", "59"])
    check = runner.invoke(cli.app, ["intraday", "check"])

    assert root_help.exit_code == group_help.exit_code == watch_help.exit_code == 0
    assert "intraday" in root_help.stdout
    assert "check" in group_help.stdout and "watch" in group_help.stdout
    assert "--interval-seconds" in watch_help.stdout
    assert invalid.exit_code == 2 and calls == [("check", None)]
    assert check.exit_code == 0


def test_typed_ownership_loss_terminalizes_reconciles_persists_and_unlocks(
    tmp_path, monkeypatch
) -> None:
    """The real active-cycle path must never skip durable shutdown on lease loss."""

    conn = connect_portfolio_store(tmp_path / "audit.db")
    lease = acquire_mutation_lease(
        conn,
        account_scope_hash="a" * 64,
        lock_dir=tmp_path / "locks",
        command="intraday-check",
        cycle_id="typed-loss-cycle",
    )
    sequence: list[str] = []
    audited = []
    real_assert = lease.assert_active_owner
    real_release = lease.release
    assertions = 0

    def lose_before_submit(*args, **kwargs) -> None:
        nonlocal assertions
        assertions += 1
        if assertions == 2:
            conn.execute(
                "UPDATE mutation_leases SET owner_token='replacement' "
                "WHERE account_scope_hash=?",
                (lease.account_scope_hash,),
            )
            conn.commit()
        real_assert(*args, **kwargs)

    def record_release(*args, **kwargs) -> None:
        sequence.append("release")
        real_release(*args, **kwargs)

    import trading_bot.mutation_lease as lease_module

    real_flock = lease_module.fcntl.flock

    def record_unlock(fd: int, operation: int) -> None:
        if operation == lease_module.fcntl.LOCK_UN:
            sequence.append("unlock")
        real_flock(fd, operation)

    monkeypatch.setattr(lease, "assert_active_owner", lose_before_submit)
    monkeypatch.setattr(lease, "release", record_release)
    monkeypatch.setattr(lease_module.fcntl, "flock", record_unlock)

    result = run_intraday_check(
        clock=lambda: datetime(2026, 9, 4, 10, 0, tzinfo=KST),
        snapshot_reader=lambda: _snapshot(),
        quote_reader=lambda ticker: Money(80_000.0, "KRW"),
        risk_config=RiskConfig(0.05, 0.10),
        lease=lease,
        exit_submitter=lambda candidate, price: sequence.append("post"),
        audit_sink=audited.append,
        terminalize=lambda item: sequence.append("terminalize"),
        reconcile=lambda: sequence.append("reconcile") or False,
        persist_unresolved=lambda: sequence.append("unresolved"),
    )

    assert result.reason_code == "LEASE_OWNERSHIP_LOST"
    assert result.outcome is IntradayIterationOutcome.INTERRUPTED
    assert audited == [result]
    assert "post" not in sequence
    assert sequence == ["terminalize", "reconcile", "unresolved", "release", "unlock"]
    assert lease.closed
