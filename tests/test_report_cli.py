"""Offline contract tests for the nested report command group."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

from trading_bot.config import ReportSettings
from trading_bot.report_cli import parse_kst_date, report_app


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
