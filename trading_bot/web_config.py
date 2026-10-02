"""Credential-free, immutable resource authority for the operator application."""
from __future__ import annotations

import ipaddress
import re
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ResourceOwner = Literal['audit', 'portfolio', 'soak', 'controller', 'replay', 'backtest', 'shadow', 'calibration']
_ID = re.compile(r'\A[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}\Z')


class ResourceDescriptor(BaseModel):
    """An operator-registered location, never a client-selected path."""
    model_config = ConfigDict(frozen=True, extra='forbid', hide_input_in_errors=True)
    id: str = Field(pattern=_ID)
    path: Path
    owner: ResourceOwner
    schema_family: ResourceOwner | None = None
    account_hash: str = Field(pattern=r'^(?:sha256:)?[a-f0-9]{64}$')
    target: Literal['mock', 'real', 'dry_run', 'simulated', 'shadow']

    @model_validator(mode='after')
    def owned_schema(self):
        if self.schema_family is not None and self.schema_family != self.owner:
            raise ValueError('resource schema family must match owner')
        object.__setattr__(self, 'schema_family', self.owner)
        return self

    @property
    def resource_id(self) -> str:
        return self.id


def checked_path(raw: Path) -> Path:
    """Reject link components without resolving away their evidence."""
    raw = Path(raw)
    if '..' in raw.parts:
        raise ValueError('ambiguous storage path')
    path = raw.absolute()
    for part in (path, *path.parents):
        if part.is_symlink():
            raise ValueError('symbolic storage paths are forbidden')
    if path.exists() and path.is_file() and path.stat().st_nlink != 1:
        raise ValueError('hardlinked storage paths are forbidden')
    return path


def overlaps(left: Path, right: Path) -> bool:
    return left == right or left in right.parents or right in left.parents


class WebSettings(BaseSettings):
    """No trading Settings, dotenv, broker/provider fields or implicit capability."""
    model_config = SettingsConfigDict(env_prefix='BOT_WEB_', env_file=None,
                                     frozen=True, extra='forbid', hide_input_in_errors=True)
    operational_db_path: Path = Path('data/web-operations/operator.db')
    artifact_root: Path = Path('data/web-artifacts')
    registered_resources: tuple[ResourceDescriptor, ...] = ()
    bind_host: str = '127.0.0.1'
    port: int = Field(default=8765, ge=1, le=65535)
    private_mode: bool = False
    allowed_hosts: tuple[str, ...] = ('127.0.0.1', 'localhost', '::1')
    allowed_origin: str | None = None
    tls_termination: bool = False
    trusted_proxies: tuple[str, ...] = ()
    cookie_secret: SecretStr | None = Field(default=None, repr=False)
    default_rows: int = Field(default=50, ge=1, le=100)
    max_rows: int = Field(default=100, ge=1, le=100)
    export_days: int = Field(default=31, ge=1, le=366)
    export_rows: int = Field(default=10000, ge=1, le=10000)
    export_bytes: int = Field(default=10 * 1024 * 1024, ge=1, le=10 * 1024 * 1024)

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings,
                                  dotenv_settings, file_secret_settings):
        # Even _env_file cannot acquire a trading .env or unrelated file secrets.
        return init_settings, env_settings

    @model_validator(mode='after')
    def validate_contract(self):
        if len({r.id for r in self.registered_resources}) != len(self.registered_resources):
            raise ValueError('resource IDs must be unique')
        if len(self.registered_resources) > 64 or self.default_rows > self.max_rows:
            raise ValueError('resource/query bounds exceeded')
        if not self.allowed_hosts or len(self.allowed_hosts) > 16:
            raise ValueError('fixed allowed hosts required')
        for host in self.allowed_hosts:
            if host != '::1' and not re.fullmatch(r'[a-zA-Z0-9][a-zA-Z0-9.-]{0,252}', host):
                raise ValueError('invalid allowed host')
            if '*' in host or host.startswith('.') or host.endswith('.'):
                raise ValueError('wildcard hosts are forbidden')
        try:
            bind = ipaddress.ip_address(self.bind_host)
        except ValueError:
            if self.bind_host != 'localhost':
                raise ValueError('binding must be a fixed IP or localhost') from None
            bind = ipaddress.ip_address('127.0.0.1')
        if bind.is_unspecified or bind.is_multicast or bind.is_global:
            raise ValueError('public/wildcard binding forbidden')
        if not self.private_mode and (not bind.is_loopback or self.trusted_proxies or self.tls_termination):
            raise ValueError('remote access requires explicit private mode')
        for proxy in self.trusted_proxies:
            address = ipaddress.ip_address(proxy)
            if address.is_global or address.is_unspecified or address.is_multicast:
                raise ValueError('proxy must be a fixed private address')
        if len(self.trusted_proxies) > 8:
            raise ValueError('proxy bound exceeded')
        if self.private_mode and (not self.tls_termination or not self.trusted_proxies or not self.allowed_origin):
            raise ValueError('private mode requires HTTPS termination, origin and trusted proxies')
        if self.allowed_origin:
            parsed = urlsplit(self.allowed_origin)
            if (parsed.scheme != ('https' if self.private_mode else 'http')
                    or parsed.hostname not in self.allowed_hosts
                    or parsed.username or parsed.password or parsed.path or parsed.query or parsed.fragment):
                raise ValueError('fixed trusted origin required')
            try:
                parsed.port
            except ValueError:
                raise ValueError('invalid origin port') from None
        if self.cookie_secret is not None and len(self.cookie_secret.get_secret_value()) < 32:
            raise ValueError('cookie signing secret must have at least 32 characters')
        return self

    def resource(self, resource_id: str) -> ResourceDescriptor:
        if not isinstance(resource_id, str) or not _ID.fullmatch(resource_id):
            raise ValueError('unregistered resource')
        for descriptor in self.registered_resources:
            if descriptor.id == resource_id:
                return descriptor
        raise ValueError('unregistered resource')

    def validate_topology(self) -> tuple[Path, Path]:
        """Validate authority before *each* write/open; never open source contents."""
        db, artifact = checked_path(self.operational_db_path), checked_path(self.artifact_root)
        if db.exists() and not db.is_file():
            raise ValueError('operational DB must be a regular file')
        if artifact.exists() and not artifact.is_dir():
            raise ValueError('artifact root must be a directory')
        if overlaps(db.parent, artifact):
            raise ValueError('operational and artifact roots must be separate')
        sources = []
        for descriptor in self.registered_resources:
            source = checked_path(descriptor.path)
            # Missing registered evidence remains unavailable, with reserved authority.
            root = source if source.is_dir() else source.parent
            sources.append(source)
            if overlaps(db.parent, root) or overlaps(artifact, root):
                raise ValueError('writable roots overlap source locations')
        # Fail closed on links placed in an existing writable tree, including SQLite sidecars.
        for root in (db.parent, artifact):
            if root.exists():
                count = 0
                for child in root.rglob('*'):
                    count += 1
                    if count > 20000:
                        raise ValueError('storage topology bound exceeded')
                    checked_path(child)
        return db, artifact
