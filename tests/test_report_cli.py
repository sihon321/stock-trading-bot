"""Offline contract tests for the nested report command group."""

from __future__ import annotations

from datetime import date
import inspect
from pathlib import Path

import pytest
from typer.testing import CliRunner

from trading_bot import sqlite_audit, soak_store
from trading_bot.config import ReportSettings
from trading_bot.report_cli import (
    calibration_command,
    parse_kst_date,
    report_app,
    write_report_text,
)


REPLAY_FIXTURES = Path(__file__).parent / "fixtures" / "replay"


def _clear_live_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "KIS_MOCK__APP_KEY",
        "KIS_MOCK__APP_SECRET",
        "KIS_REAL__APP_KEY",
        "KIS_REAL__APP_SECRET",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)


def test_report_settings_has_only_the_offline_audit_path() -> None:
    assert set(ReportSettings.model_fields) == {"audit_db_path"}
    assert ReportSettings().audit_db_path == Path("./data/audit.db")


def test_parse_kst_date_is_strict() -> None:
    assert parse_kst_date("2026-07-14") == date(2026, 7, 14)
    for malformed in ("20260714", "2026-7-14", "2026-02-30", " 2026-07-14"):
        with pytest.raises(ValueError, match="YYYY-MM-DD"):
            parse_kst_date(malformed)


def test_daily_and_period_are_offline_and_use_lightweight_default_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import trading_bot.report_cli as report_cli

    _clear_live_credentials(monkeypatch)
    audit_path = tmp_path / "audit.db"
    audit_path.write_bytes(b"offline-test")
    monkeypatch.setenv("AUDIT_DB_PATH", str(audit_path))
    seen: list[tuple[Path, object]] = []

    class Repository:
        def __init__(self, path: Path) -> None:
            self.path = path

    def build_daily(repository: Repository, selected: date) -> object:
        seen.append((repository.path, selected))
        return object()

    def build_period(repository: Repository, start: date, end: date) -> object:
        seen.append((repository.path, (start, end)))
        return object()

    monkeypatch.setattr(report_cli, "ReadOnlyAuditRepository", Repository)
    monkeypatch.setattr(report_cli, "build_daily_report", build_daily)
    monkeypatch.setattr(report_cli, "build_period_report", build_period)
    monkeypatch.setattr(report_cli, "render_daily_report", lambda _: "일일 전체 보고서\n")
    monkeypatch.setattr(report_cli, "render_period_report", lambda _: "기간 전체 보고서\n")
    monkeypatch.setattr(report_cli, "_today_kst", lambda: date(2026, 7, 14))

    runner = CliRunner()
    daily = runner.invoke(report_app, ["daily"])
    period = runner.invoke(
        report_app, ["period", "--from", "2026-07-01", "--to", "2026-07-14"]
    )

    assert daily.exit_code == 0
    assert daily.stdout == "일일 전체 보고서\n"
    assert period.exit_code == 0
    assert period.stdout == "기간 전체 보고서\n"
    assert seen == [
        (audit_path, date(2026, 7, 14)),
        (audit_path, (date(2026, 7, 1), date(2026, 7, 14))),
    ]


def test_period_rejects_reversed_range_with_bounded_diagnostic() -> None:
    result = CliRunner().invoke(
        report_app, ["period", "--from", "2026-07-15", "--to", "2026-07-14"]
    )
    assert result.exit_code == 2
    assert "ValueError" in result.stderr
    assert len(result.stderr) < 300


def test_replay_report_is_offline_and_uses_reporting_domain(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import trading_bot.report_cli as report_cli

    _clear_live_credentials(monkeypatch)
    replay_path = tmp_path / "result.json"
    replay_path.write_text("{}", encoding="utf-8")
    seen: list[tuple[Path, ...]] = []

    def load(paths: list[Path]) -> tuple[object, ...]:
        seen.append(tuple(paths))
        return (object(),)

    monkeypatch.setattr(report_cli, "load_replay_results", load)
    monkeypatch.setattr(report_cli, "build_replay_report", lambda _: object())
    monkeypatch.setattr(
        report_cli,
        "render_replay_report",
        lambda _: "Replay 검증 보고서\nevaluated=1/1\n수익성을 입증하지 않습니다\n",
    )

    result = CliRunner().invoke(report_app, ["replay", str(replay_path)])

    assert result.exit_code == 0
    assert "Replay 검증 보고서" in result.stdout
    assert "evaluated=1/1" in result.stdout
    assert "수익성을 입증하지 않습니다" in result.stdout
    assert seen == [(replay_path,)]


def test_report_commands_reject_missing_and_malformed_inputs_without_mutation(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.json"
    malformed_date = CliRunner().invoke(report_app, ["daily", "--date", "20260714"])
    missing_replay = CliRunner().invoke(report_app, ["replay", str(missing)])

    assert malformed_date.exit_code == 2
    assert missing_replay.exit_code == 2
    assert not missing.exists()


def test_terminal_and_saved_report_are_byte_identical_and_idempotent(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import trading_bot.report_cli as report_cli

    monkeypatch.setattr(report_cli, "ReadOnlyAuditRepository", lambda _: object())
    monkeypatch.setattr(report_cli, "build_daily_report", lambda *_: object())
    monkeypatch.setattr(
        report_cli, "render_daily_report", lambda _: "첫 줄\r\n둘째 줄\r\n"
    )
    output = tmp_path / "nested" / "daily.txt"
    command = [
        "daily",
        "--date",
        "2026-07-14",
        "--audit-db",
        str(tmp_path / "ignored.db"),
        "--output",
        str(output),
    ]

    first = CliRunner().invoke(report_app, command)
    second = CliRunner().invoke(report_app, command)

    assert first.exit_code == second.exit_code == 0
    assert first.stdout.encode("utf-8") == output.read_bytes()
    assert second.stdout.encode("utf-8") == output.read_bytes()
    assert output.read_bytes() == "첫 줄\n둘째 줄\n".encode()


def test_report_writer_rejects_conflicts_symlinks_nonregular_and_escaping_paths(
    tmp_path: Path,
) -> None:
    target = tmp_path / "report.txt"
    target.write_text("기존 내용\n", encoding="utf-8")
    with pytest.raises(ValueError, match="conflict"):
        write_report_text(target, "새 내용\n")
    assert target.read_text(encoding="utf-8") == "기존 내용\n"

    directory_target = tmp_path / "directory"
    directory_target.mkdir()
    with pytest.raises(ValueError, match="regular file"):
        write_report_text(directory_target, "보고서\n")

    symlink_target = tmp_path / "link.txt"
    symlink_target.symlink_to(target)
    with pytest.raises(ValueError, match="symbolic link"):
        write_report_text(symlink_target, "보고서\n")

    real_parent = tmp_path / "real-parent"
    (real_parent / "nested").mkdir(parents=True)
    parent_link = tmp_path / "parent-link"
    parent_link.symlink_to(real_parent, target_is_directory=True)
    with pytest.raises(ValueError, match="symbolic link"):
        write_report_text(parent_link / "nested" / "report.txt", "보고서\n")

    with pytest.raises(ValueError, match="ambiguous"):
        write_report_text(tmp_path / "nested" / ".." / "escape.txt", "보고서\n")

    assert not tuple(tmp_path.glob(".report-*.tmp"))


def _calibration_stores(tmp_path: Path) -> tuple[Path, Path]:
    audit_path = tmp_path / "audit.db"
    soak_path = tmp_path / "soak.db"
    sqlite_audit.connect(audit_path).close()
    soak = soak_store.connect_soak_store(soak_path)
    soak_store.create_campaign(
        soak,
        campaign_id="campaign-cli",
        accepted_profile_fingerprint="sha256:test",
        accepted_profile_version="official-example-v1",
        field_contract_version="kis-mock-compat-v1",
        ambiguity_policy_version="ambiguity-v1",
        ambiguity_window_seconds=60,
        ambiguity_poll_cadence_seconds=5,
        ambiguity_max_observations=12,
    )
    soak.close()
    return audit_path, soak_path


def _calibration_command(
    fixture: Path, audit_path: Path, soak_path: Path, output: Path | None = None
) -> list[str]:
    command = [
        "calibration",
        str(fixture),
        "--audit-db",
        str(audit_path),
        "--soak-db",
        str(soak_path),
        "--campaign-id",
        "campaign-cli",
    ]
    if output is not None:
        command.extend(("--output", str(output)))
    return command


@pytest.mark.parametrize("with_portfolio", [False, True])
def test_calibration_command_is_offline_and_renders_every_locked_group(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, with_portfolio: bool
) -> None:
    _clear_live_credentials(monkeypatch)
    audit_path, soak_path = _calibration_stores(tmp_path)
    if with_portfolio:
        from trading_bot.portfolio_store import connect_portfolio_store
        connect_portfolio_store(audit_path).close()
    fixture = REPLAY_FIXTURES / "focused.json"

    result = CliRunner().invoke(
        report_app, _calibration_command(fixture, audit_path, soak_path)
    )

    assert result.exit_code == 0
    assert "CALIBRATION_ADVISORY_ONLY" in result.stdout
    assert "INSUFFICIENT_EVIDENCE" in result.stdout
    for field in (
        "buy_confidence_threshold",
        "sell_confidence_threshold",
        "max_position_value",
        "stop_loss_pct",
        "take_profit_pct",
    ):
        assert field in result.stdout
    assert "profitability" in result.stdout


def test_calibration_terminal_file_and_inputs_are_byte_identical(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    audit_path, soak_path = _calibration_stores(tmp_path)
    fixture = REPLAY_FIXTURES / "focused.json"
    env_path = tmp_path / ".env"
    env_path.write_text("TRADING_MODE=mock\n", encoding="utf-8")
    output = tmp_path / "reports" / "calibration.txt"
    inputs = (audit_path, soak_path, fixture, env_path)
    before = {path: path.read_bytes() for path in inputs}
    command = _calibration_command(fixture, audit_path, soak_path, output)

    first = CliRunner().invoke(report_app, command)
    second = CliRunner().invoke(report_app, command)

    assert first.exit_code == second.exit_code == 0
    assert first.stdout == second.stdout
    assert first.stdout.encode("utf-8") == output.read_bytes()
    assert before == {path: path.read_bytes() for path in inputs}


def test_calibration_rejects_missing_duplicate_symlink_and_conflicting_output(
    tmp_path: Path,
) -> None:
    audit_path, soak_path = _calibration_stores(tmp_path)
    fixture = REPLAY_FIXTURES / "focused.json"
    missing = tmp_path / "missing.json"
    missing_result = CliRunner().invoke(
        report_app, _calibration_command(missing, audit_path, soak_path)
    )
    duplicate_result = CliRunner().invoke(
        report_app,
        [
            "calibration", str(fixture), str(fixture),
            "--audit-db", str(audit_path), "--soak-db", str(soak_path),
            "--campaign-id", "campaign-cli",
        ],
    )
    linked = tmp_path / "linked.json"
    linked.symlink_to(fixture)
    linked_result = CliRunner().invoke(
        report_app, _calibration_command(linked, audit_path, soak_path)
    )
    conflict = tmp_path / "conflict.txt"
    conflict.write_text("keep\n", encoding="utf-8")
    conflict_result = CliRunner().invoke(
        report_app, _calibration_command(fixture, audit_path, soak_path, conflict)
    )

    for result in (missing_result, duplicate_result, linked_result, conflict_result):
        assert result.exit_code == 2
        assert len(result.stderr) < 300
    assert not missing.exists()
    assert conflict.read_text(encoding="utf-8") == "keep\n"
    assert not tuple(tmp_path.rglob(".report-*.tmp"))


def test_calibration_controller_has_no_live_or_policy_mutation_seam() -> None:
    source = inspect.getsource(calibration_command)

    for forbidden in (
        "Settings(", "build_runtime", "Kis", "Broker", "place_order",
        "write_text", "write_bytes", "dotenv", "schedule", "reconcile",
    ):
        assert forbidden not in source
