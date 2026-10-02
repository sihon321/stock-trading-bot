"""Explicit independent bot-alerts --config watch/once/status commands."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import sqlite3
from threading import Event

import typer

from .alert_config import ObserverSettings
from .alert_observer import AlertObserver, ObserverEvidenceError
from .web_config import checked_path, overlaps

app = typer.Typer(no_args_is_help=True, help='독립 운영 알림 관찰; 거래 실행 권한 없음')
_SAFE_ERROR = '알림 설정 또는 운영 증거 저장소를 확인하세요. 비밀정보는 표시하지 않습니다.'


def load_settings(config: Path):
    path = checked_path(config)
    if (not path.is_file() or path.stat().st_size > 65536 or path.stat().st_mode & 0o077
            or path.stat().st_uid != os.getuid() or path.parent.stat().st_mode & 0o022):
        raise ValueError('owner-protected local config required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, encoding='utf-8') as file:
        content = json.load(file)
    if not isinstance(content, dict):
        raise ValueError('configuration object required')
    settings = ObserverSettings(**content)
    if path == settings.validate_topology():
        raise ValueError('config overlaps operational DB')
    for resource in settings.registered_resources:
        source = checked_path(resource.path)
        if overlaps(path.parent, source if source.is_dir() else source.parent):
            raise ValueError('config directory overlaps source authority')
    return settings


@app.callback()
def root(ctx: typer.Context, config: Path = typer.Option(..., '--config')):
    ctx.obj = config


def _run(config, command):
    try:
        observer = AlertObserver(load_settings(config))
        if command == 'status':
            typer.echo(json.dumps(observer.status(), ensure_ascii=False, sort_keys=True))
        elif command == 'once':
            observer.scan_once()
            typer.echo('알림 관찰 완료: STOPPED')
        else:
            stop = Event()
            previous = {}
            try:
                for sig in (signal.SIGINT, signal.SIGTERM):
                    previous[sig] = signal.getsignal(sig)
                    signal.signal(sig, lambda *_: stop.set())
                observer.watch(stop)
            finally:
                for sig, handler in previous.items():
                    signal.signal(sig, handler)
            typer.echo('알림 관찰 중지: STOPPED')
    except (ValueError, OSError, UnicodeError, sqlite3.Error, ObserverEvidenceError):
        typer.echo(_SAFE_ERROR, err=True)
        raise typer.Exit(1) from None


@app.command()
def status(ctx: typer.Context):
    """읽기 전용 상태; webhook 없이 확인합니다."""
    _run(ctx.obj, 'status')


@app.command()
def once(ctx: typer.Context):
    """한 번 관찰하고 전달 기록을 확정한 뒤 종료합니다."""
    _run(ctx.obj, 'once')


@app.command()
def watch(ctx: typer.Context):
    """전경 30초 관찰; SIGINT/SIGTERM으로 안전하게 종료합니다."""
    _run(ctx.obj, 'watch')


if __name__ == '__main__':
    app()
