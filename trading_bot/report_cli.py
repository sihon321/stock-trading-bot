"""Credential-free Typer controllers for deterministic evidence reports."""

from __future__ import annotations

import os
import tempfile
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import typer

from .config import ReportSettings
from .reporting import (
    ReadOnlyAuditRepository,
    build_daily_report,
    build_period_report,
    build_replay_report,
    load_replay_results,
    render_daily_report,
    render_period_report,
    render_replay_report,
)

report_app = typer.Typer(no_args_is_help=True, help="저장된 감사·replay 증거 보고서")


def _today_kst() -> date:
    return datetime.now(ZoneInfo("Asia/Seoul")).date()


def parse_kst_date(value: str) -> date:
    """Parse only the exact operator-facing YYYY-MM-DD grammar."""

    try:
        parsed = datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("date must use valid YYYY-MM-DD format") from exc
    if parsed.isoformat() != value:
        raise ValueError("date must use valid YYYY-MM-DD format")
    return parsed


def resolve_report_audit_db_path(
    explicit: Path | None,
    settings_factory: Callable[[], ReportSettings] = ReportSettings,
) -> Path:
    """Resolve report storage without constructing credential-bearing Settings."""

    return Path(explicit) if explicit is not None else settings_factory().audit_db_path


def _normalized_text_bytes(rendered: str) -> bytes:
    normalized = rendered.replace("\r\n", "\n").replace("\r", "\n")
    normalized = normalized.rstrip("\n") + "\n"
    return normalized.encode("utf-8")


def _validated_output_parent(output: Path) -> tuple[Path, Path]:
    raw = Path(output)
    if raw.name in {"", ".", ".."} or ".." in raw.parts:
        raise ValueError("report output path is ambiguous")
    if raw.is_symlink():
        raise ValueError("report output may not be a symbolic link")

    current = Path(raw.anchor) if raw.is_absolute() else Path()
    for part in raw.parts[1:] if raw.is_absolute() else raw.parts:
        current /= part
        if current.is_symlink():
            raise ValueError("report output path may not contain symbolic links")

    parent = raw.parent
    cursor = parent
    missing: list[Path] = []
    while not cursor.exists():
        if cursor.is_symlink():
            raise ValueError("report output parent may not be a symbolic link")
        missing.append(cursor)
        next_cursor = cursor.parent
        if next_cursor == cursor:
            raise ValueError("report output parent is unavailable")
        cursor = next_cursor
    if cursor.is_symlink() or not cursor.is_dir():
        raise ValueError("report output parent must be a regular directory")

    for directory in reversed(missing):
        directory.mkdir()
    resolved_parent = parent.resolve(strict=True)
    if resolved_parent.is_symlink() or not resolved_parent.is_dir():
        raise ValueError("report output parent must be a regular directory")
    target = resolved_parent / raw.name
    return resolved_parent, target


def write_report_text(output: Path, rendered: str) -> None:
    """Atomically persist the same normalized UTF-8 report shown in the terminal."""

    root, target = _validated_output_parent(Path(output))
    if target.is_symlink():
        raise ValueError("report output may not be a symbolic link")
    payload = _normalized_text_bytes(rendered)
    if target.exists():
        if not target.is_file():
            raise ValueError("report output must be a regular file")
        if target.read_bytes() != payload:
            raise ValueError("report output conflict: existing content differs")
        return

    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=root, prefix=".report-", suffix=".tmp", delete=False
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, target)
        temporary_name = None
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)


def _diagnostic(exc: Exception) -> str:
    message = str(exc).replace("\r", " ").replace("\n", " ")[:200]
    return f"Report failed: {type(exc).__name__}: {message or 'invalid input'}"


def _deliver(rendered: str, output: Path | None) -> None:
    normalized = _normalized_text_bytes(rendered).decode("utf-8")
    if output is not None:
        write_report_text(output, normalized)
    typer.echo(normalized, nl=False)


@report_app.command("daily")
def daily_command(
    date_text: str | None = typer.Option(None, "--date"),
    audit_db: Path | None = typer.Option(None, "--audit-db"),
    output: Path | None = typer.Option(None, "--output"),
) -> None:
    """KST 거래일 하루의 실행·티커 증거를 보고합니다."""

    try:
        selected = _today_kst() if date_text is None else parse_kst_date(date_text)
        repository = ReadOnlyAuditRepository(resolve_report_audit_db_path(audit_db))
        rendered = render_daily_report(build_daily_report(repository, selected))
        _deliver(rendered, output)
    except (OSError, ValueError, RuntimeError) as exc:
        typer.echo(_diagnostic(exc), err=True)
        raise typer.Exit(2) from None


@report_app.command("period")
def period_command(
    from_text: str = typer.Option(..., "--from"),
    to_text: str = typer.Option(..., "--to"),
    audit_db: Path | None = typer.Option(None, "--audit-db"),
    output: Path | None = typer.Option(None, "--output"),
) -> None:
    """포함 범위의 KST 거래일 증거를 보고합니다."""

    try:
        start = parse_kst_date(from_text)
        end = parse_kst_date(to_text)
        if start > end:
            raise ValueError("period start must not be after end")
        repository = ReadOnlyAuditRepository(resolve_report_audit_db_path(audit_db))
        rendered = render_period_report(build_period_report(repository, start, end))
        _deliver(rendered, output)
    except (OSError, ValueError, RuntimeError) as exc:
        typer.echo(_diagnostic(exc), err=True)
        raise typer.Exit(2) from None


@report_app.command("replay")
def replay_report_command(
    inputs: list[Path] = typer.Argument(...),
    output: Path | None = typer.Option(None, "--output"),
) -> None:
    """하나 이상의 정규화 replay 결과를 검증·집계합니다."""

    try:
        if not inputs:
            raise ValueError("at least one replay result is required")
        loaded = load_replay_results(inputs)
        rendered = render_replay_report(build_replay_report(loaded))
        _deliver(rendered, output)
    except (OSError, ValueError, RuntimeError) as exc:
        typer.echo(_diagnostic(exc), err=True)
        raise typer.Exit(2) from None
