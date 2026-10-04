"""Independent explicit observer authority; no trading settings or dotenv."""
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .web_config import ResourceDescriptor, checked_path, overlaps


class ObserverSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='BOT_ALERTS_', env_file=None,
        frozen=True, extra='forbid', hide_input_in_errors=True)
    operational_db_path: Path = Path('data/web-operations/operator.db')
    registered_resources: tuple[ResourceDescriptor, ...] = ()
    expectation_service_config_path: Path | None = None
    scan_interval_seconds: int = Field(default=30, ge=30, le=30)
    takeover_after_seconds: int = Field(default=300, ge=300, le=3600)
    webhook_url: SecretStr | None = Field(default=None, repr=False)

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings,
                                  dotenv_settings, file_secret_settings):
        return init_settings, env_settings

    @model_validator(mode='after')
    def contract(self):
        if len(self.registered_resources) > 64 or len({r.id for r in self.registered_resources}) != len(self.registered_resources):
            raise ValueError('bounded unique registered resources required')
        if self.expectation_service_config_path is not None:
            checked_path(self.expectation_service_config_path)
            if not {'service','control'}.issubset({r.owner for r in self.registered_resources}):
                raise ValueError('explicit service/control expectation registration required')
        if self.webhook_url is not None:
            url = urlsplit(self.webhook_url.get_secret_value())
            if (url.scheme != 'https' or url.hostname not in {'discord.com', 'discordapp.com'}
                    or not url.path.startswith('/api/webhooks/') or url.username or url.password
                    or url.port not in {None, 443} or url.query or url.fragment):
                raise ValueError('explicit Discord HTTPS webhook required')
        return self

    def resource(self, resource_id):
        for resource in self.registered_resources:
            if resource.id == resource_id:
                return resource
        raise ValueError('unregistered resource')

    def validate_topology(self):
        db = checked_path(self.operational_db_path)
        if db.exists() and not db.is_file():
            raise ValueError('regular operational DB required')
        if self.expectation_service_config_path is not None:
            config=checked_path(self.expectation_service_config_path)
            if overlaps(db.parent,config.parent):
                raise ValueError('expectation config must be separate from observer writes')
        for resource in self.registered_resources:
            source = checked_path(resource.path)
            root = source if source.is_dir() else source.parent
            if overlaps(db.parent, root):
                raise ValueError('operational root overlaps source authority')
        if db.parent.exists():
            for count, child in enumerate(db.parent.rglob('*'), 1):
                if count > 20000:
                    raise ValueError('storage topology bound exceeded')
                checked_path(child)
        return db
