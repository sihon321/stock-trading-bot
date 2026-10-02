"""Local operator provisioning and an independent production web entry point."""
from __future__ import annotations

import json
import os
import secrets
import sqlite3
import tempfile
from pathlib import Path

import typer

from .web_auth import WebAuth
from .web_config import WebSettings, checked_path, overlaps
from .web_store import WebStore

app = typer.Typer(no_args_is_help=True, help='운영자 웹 계정 설정 및 안전한 서버 실행')
_SAFE_ERROR = '웹 설정 또는 운영 저장소를 확인하세요. 비밀정보는 표시하지 않습니다.'


def _config_path(path: Path) -> Path:
    path = checked_path(path)
    if (not path.is_file() or path.stat().st_size > 65536
            or path.stat().st_mode & 0o077 or path.stat().st_uid != os.getuid()):
        raise ValueError('owner-protected local configuration required')
    if path.parent.stat().st_mode & 0o022:
        raise ValueError('configuration directory must be owner writable only')
    return path


def load_settings(config: Path, *, host: str | None = None, port: int | None = None) -> WebSettings:
    """Read only an explicit protected JSON configuration, never trading dotenv."""
    path = _config_path(config)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(descriptor, 'r', encoding='utf-8') as file:
        content = json.load(file)
    if not isinstance(content, dict):
        raise ValueError('local configuration must be an object')
    if host is not None:
        content['bind_host'] = host
    if port is not None:
        content['port'] = port
    settings = WebSettings(**content)
    db, artifacts = settings.validate_topology()
    if path == db or overlaps(path, artifacts):
        raise ValueError('configuration overlaps writable artifacts')
    for resource in settings.registered_resources:
        source = checked_path(resource.path)
        root = source if source.is_dir() else source.parent
        if overlaps(path.parent, root):
            raise ValueError('configuration write root overlaps source locations')
    return settings


def _signing_secret(config: Path, settings: WebSettings) -> None:
    if settings.cookie_secret is not None:
        return
    path = _config_path(config)
    content = json.loads(path.read_text(encoding='utf-8'))
    content['cookie_secret'] = secrets.token_urlsafe(48)
    # Only this explicitly registered, owner-protected local config is replaced.
    descriptor, temporary = tempfile.mkstemp(prefix='.web-config-', dir=path.parent)
    try:
        with os.fdopen(descriptor, 'w', encoding='utf-8') as file:
            json.dump(content, file, sort_keys=True, indent=2)
            file.flush()
            os.fsync(file.fileno())
        _config_path(config)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _password() -> str:
    return typer.prompt('운영자 암호 (12자 이상)', hide_input=True, confirmation_prompt='암호 확인')


@app.command()
def setup(config: Path = typer.Option(..., '--config'),
          username: str = typer.Option('operator', '--username')):
    """전용 운영자 계정 최초 설정. 기존 계정을 덮어쓰지 않습니다."""
    try:
        settings = load_settings(config)
        store = WebStore(settings)
        store.initialize()
        if store.get_operator() is not None:
            typer.echo('이미 설정된 계정입니다. reset-password를 사용하세요.', err=True)
            raise typer.Exit(1)
        # Signing configuration must be durable before successful provisioning.
        password = _password()
        _signing_secret(config, settings)
        WebAuth(store).provision_operator(username, password)
        typer.echo('운영자 계정 설정 완료')
    except (ValueError, OSError, UnicodeError, sqlite3.Error):
        typer.echo(_SAFE_ERROR, err=True)
        raise typer.Exit(1) from None


@app.command('reset-password')
def reset_password(config: Path = typer.Option(..., '--config')):
    """로컬에서 암호를 재설정하고 모든 클라이언트 세션을 폐기합니다."""
    try:
        settings = load_settings(config)
        store = WebStore(settings)
        store.initialize()
        if store.get_operator() is None:
            raise ValueError('operator provisioning required')
        WebAuth(store).reset_password(_password())
        typer.echo('암호 재설정 및 모든 세션 폐기 완료')
    except (ValueError, OSError, UnicodeError, sqlite3.Error):
        typer.echo(_SAFE_ERROR, err=True)
        raise typer.Exit(1) from None


def _create_app(settings: WebSettings):
    # 14-10 owns the concrete routes/security factory. Help/setup/reset work now.
    from .web_app import create_app
    return create_app(settings)


def _serve(application, **options):
    from waitress import serve as waitress_serve
    waitress_serve(application, **options)


@app.command()
def serve(config: Path = typer.Option(..., '--config'),
          host: str | None = typer.Option(None, '--host'),
          port: int | None = typer.Option(None, '--port')):
    """Waitress 실행. 기본 loopback; 명시적 사설 HTTPS 설정만 허용합니다."""
    try:
        settings = load_settings(config, host=host, port=port)
        if settings.cookie_secret is None:
            raise ValueError('local setup required')
        if settings.private_mode and len(settings.trusted_proxies) != 1:
            raise ValueError('Waitress requires one explicitly trusted proxy peer')
        store = WebStore(settings)
        store.initialize()
        if store.get_operator() is None:
            raise ValueError('local setup required')
        application = _create_app(settings)
        application.debug = False
        application.config.update(DEBUG=False, TESTING=False, PROPAGATE_EXCEPTIONS=False)
        options = dict(host=settings.bind_host, port=settings.port, expose_tracebacks=False,
                       clear_untrusted_proxy_headers=True, threads=4,
                       max_request_body_size=65536, max_request_header_size=16384)
        if settings.private_mode:
            options.update(trusted_proxy=settings.trusted_proxies[0], trusted_proxy_count=1,
                           trusted_proxy_headers={'x-forwarded-proto', 'x-forwarded-for',
                                                  'x-forwarded-host', 'x-forwarded-port'})
        _serve(application, **options)
    except ImportError:
        typer.echo('웹 앱 구현 또는 검증된 web 의존성이 필요합니다 (14-10).', err=True)
        raise typer.Exit(1) from None
    except (ValueError, OSError, UnicodeError, sqlite3.Error):
        typer.echo(_SAFE_ERROR, err=True)
        raise typer.Exit(1) from None


if __name__ == '__main__':
    app()
