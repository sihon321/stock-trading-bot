"""Explicit independent bot-alerts --config watch/once/status commands."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import sqlite3
from datetime import datetime, timezone
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
def root(ctx: typer.Context, config: Path = typer.Option(..., '--config'),
         expectation_service_config: Path | None = typer.Option(None,'--expectation-service-config')):
    ctx.obj = (config,expectation_service_config)


def build_expectation_producer(settings,*,service_config,clock=lambda:datetime.now(timezone.utc),login_probe=None):
    """Only secret-free registration, exact-date sources and narrow evidence writer."""
    from .service_config import ServiceSettings
    from .service_activation import _protected_json
    from .service_models import ServiceMode
    from .service_schedule import ExpectationProducer
    from .service_store import expectation_writer_from_settings
    from .control_store import control_request_capabilities
    from .web_config import ControlResourceDescriptor
    raw=_protected_json(service_config,65536)
    enabled=raw.get('service_enabled',False);mode=ServiceMode(raw.get('mode','DISABLED'))
    if type(enabled) is not bool or enabled!=(mode!=ServiceMode.DISABLED):
        raise ValueError('explicit source mode registration required')
    # Observer capabilities retain paths/scopes when trading-only inputs are absent.
    # publish rereads the actual active registration and records UNKNOWN on failure.
    registration=ServiceSettings(**(raw|{'service_enabled':False,'mode':'DISABLED'}))
    if any(overlaps(checked_path(service_config).parent,root) for root in
           (registration.service_db_path.absolute().parent,registration.control_db_path.absolute().parent,
            registration.lock_dir.absolute())): raise ValueError('separate observer registration required')
    if (settings.expectation_service_config_path is None
            or protected_registration_path(settings.expectation_service_config_path)!=protected_registration_path(service_config)):
        raise ValueError('explicit fixed expectation registration required')
    scopes=registration.registered_scopes
    for owner,path in [('service',registration.service_db_path),('control',registration.control_db_path)]:
        matching=[r for r in settings.registered_resources if r.owner==owner]
        if (len(matching)!=len(scopes) or {(r.account_hash,r.target) for r in matching}
                !={(s.account_scope_hash,s.execution_target) for s in scopes}
                or any(checked_path(r.path)!=checked_path(path) for r in matching)):
            raise ValueError('exact registered observer sources required')
    descriptor=ControlResourceDescriptor(resource_id='installation-control',path=registration.control_db_path,
        lock_dir=registration.lock_dir,registered_scopes=tuple((s.account_scope_hash,s.execution_target) for s in scopes))
    reader,_=control_request_capabilities(descriptor,actor=f'local-observer-uid-{os.getuid()}',clock=clock)
    if login_probe is None:
        from .service_launchd import gui_login_probe
        login_probe=gui_login_probe(service_config,clock=clock)
    return ExpectationProducer(registration,config_path=service_config,login_probe=login_probe,
        control_reader=reader,writer=expectation_writer_from_settings(registration,clock=clock),clock=clock)


def protected_registration_path(path):
    from .service_config import protected_file
    return protected_file(path)


def _run(config, command):
    try:
        config,expectation_config=config if isinstance(config,tuple) else (config,None)
        settings=load_settings(config)
        producer=None
        if command!='status' and expectation_config is not None:
            try:
                producer=build_expectation_producer(settings,service_config=expectation_config)
            except (ValueError,OSError,sqlite3.Error):
                # The observer publishes source-unavailable health and retains its
                # independent delivery lifetime rather than depending on trading startup.
                producer=None
        observer = AlertObserver(settings,expectation_producer=producer)
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
