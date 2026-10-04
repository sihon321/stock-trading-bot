"""Protected service registration, independently readable without trading secrets."""
from __future__ import annotations

import json
import os
from pathlib import Path
import stat
import sys
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .service_models import ServiceMode, ServiceScope
from .web_config import checked_path, overlaps


def protected_file(path: Path) -> Path:
    path = checked_path(path)
    info = path.stat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.getuid()
            or info.st_mode & 0o077 or path.parent.stat().st_mode & 0o022):
        raise ValueError('owner-protected local file required')
    return path


class ServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='BOT_SERVICE_', env_file=None,
        frozen=True, extra='forbid', hide_input_in_errors=True, validate_default=True)
    service_enabled: bool = False
    mode: ServiceMode = ServiceMode.DISABLED
    execution_target: Literal['mock'] = 'mock'
    registered_scopes: tuple[ServiceScope, ...] = ()
    trading_config_path: Path = Field(default=Path('config/trading.json'), repr=False)
    acceptance_receipt_path: Path = Field(default=Path('config/acceptance.json'), repr=False)
    session_evidence_path: Path = Field(default=Path('config/sessions.json'), repr=False)
    observer_config_path: Path = Field(default=Path('config/observer.json'), repr=False)
    interpreter_path: Path = Field(default=Path(os.path.realpath(sys.executable)), repr=False)
    service_db_path: Path = Field(default=Path('service-data/journal/service.db'), repr=False)
    control_db_path: Path = Field(default=Path('service-data/control/control.db'), repr=False)
    lock_dir: Path = Field(default=Path('service-data/locks'), repr=False)
    trading_journal_paths: tuple[Path, ...] = Field(default=(Path('data/audit.db'),
        Path('data/soak.db'), Path('data/soak-controller.db')), repr=False)
    artifact_roots: tuple[Path, ...] = Field(default=(Path('data/web-artifacts'),), repr=False)
    risk_interval_seconds: int = Field(default=60, ge=60, le=60, strict=True)
    provider_timeout_seconds: int = Field(default=90, ge=90, le=90, strict=True)
    account_work_timeout_seconds: int = Field(default=45, ge=45, le=45, strict=True)
    post_timeout_seconds: int = Field(default=10, ge=10, le=10, strict=True)
    control_lock_timeout_seconds: int = Field(default=1, ge=1, le=1, strict=True)
    provider_admission_timeout_seconds: int = Field(default=1, ge=1, le=1, strict=True)
    restart_window_seconds: int = Field(default=600, ge=600, le=600, strict=True)
    max_automatic_restarts: int = Field(default=3, ge=3, le=3, strict=True)
    shutdown_timeout_seconds: int = Field(default=30, ge=30, le=30, strict=True)
    worker_stale_seconds: int = Field(default=120, ge=120, le=120, strict=True)

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings,
                                  dotenv_settings, file_secret_settings):
        return init_settings, env_settings

    def model_copy(self, *, update=None, deep=False):
        return type(self)(**(self.model_dump() | (update or {})))

    @model_validator(mode='after')
    def registration_contract(self):
        if self.service_enabled != (self.mode != ServiceMode.DISABLED):
            raise ValueError('enabled registration requires an explicit active mode')
        if len(self.registered_scopes) > 64 or len(set(self.registered_scopes)) != len(self.registered_scopes):
            raise ValueError('bounded unique registered scopes required')
        if self.service_enabled and not self.registered_scopes:
            raise ValueError('enabled registration requires explicit registered scopes')
        self.validate_topology()
        return self

    def validate_topology(self) -> tuple[Path, Path, Path]:
        """Check before owner opens; does not open/migrate evidence or create paths."""
        service = checked_path(self.service_db_path)
        controls = checked_path(self.control_db_path)
        locks = checked_path(self.lock_dir)
        roots = (service.parent, controls.parent, locks)
        for index, root in enumerate(roots):
            if any(overlaps(root, other) for other in roots[index + 1:]):
                raise ValueError('service, control and lock roots must be separate')
            if root.exists() and not root.is_dir():
                raise ValueError('writable root must be a directory')
        for db in (service, controls):
            if db.exists() and not db.is_file():
                raise ValueError('operational DB must be a regular file')
        sources = [checked_path(p) for p in self.trading_journal_paths]
        if len(sources) > 64 or len(self.artifact_roots) > 64:
            raise ValueError('bounded source locations required')
        source_roots = [p.parent for p in sources]
        source_roots.extend(checked_path(p) for p in self.artifact_roots)
        for name in ('trading_config_path', 'acceptance_receipt_path',
                     'session_evidence_path', 'observer_config_path'):
            path = checked_path(getattr(self, name))
            if path.exists():
                protected_file(path)
            elif self.service_enabled:
                raise ValueError('enabled registration requires protected source files')
            source_roots.append(path.parent)
        for root in roots:
            if any(overlaps(root, source) for source in source_roots):
                raise ValueError('writable root overlaps evidence or artifact authority')
            if root.exists():
                if root.stat().st_uid != os.getuid() or root.stat().st_mode & 0o022:
                    raise ValueError('owner-controlled writable root required')
                for count, child in enumerate(root.rglob('*'), 1):
                    if count > 20000:
                        raise ValueError('storage topology bound exceeded')
                    checked_path(child)
        interpreter = checked_path(self.interpreter_path)
        if not interpreter.is_file() or not os.access(interpreter, os.X_OK):
            raise ValueError('fixed executable interpreter required')
        return service, controls, locks


def load_service_settings(config: Path) -> ServiceSettings:
    """Explicit bounded JSON load; no dotenv or trading settings are consulted."""
    path = protected_file(config)
    if path.stat().st_size > 65536:
        raise ValueError('bounded service config required')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, encoding='utf-8') as file:
        info = os.fstat(file.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077 or info.st_uid != os.getuid():
            raise ValueError('owner-protected service config required')
        content = file.read(65537)
        if len(content) > 65536:
            raise ValueError('bounded service config required')
        values = json.loads(content)
    if not isinstance(values, dict):
        raise ValueError('configuration object required')
    settings = ServiceSettings(**values)
    if any(overlaps(path.parent, root) for root in
           (settings.service_db_path.absolute().parent, settings.control_db_path.absolute().parent,
            settings.lock_dir.absolute())):
        raise ValueError('registration directory overlaps writable authority')
    return settings
