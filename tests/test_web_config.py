"""Credential and writable-authority boundaries use only temporary paths."""
import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from trading_bot.web_config import ResourceDescriptor, WebSettings


def settings(tmp_path, **kwargs):
    return WebSettings(operational_db_path=tmp_path / 'operations' / 'web.db',
                       artifact_root=tmp_path / 'artifacts', **kwargs)


def resource(path, **kwargs):
    return ResourceDescriptor(id='audit', path=path, owner='audit',
                              account_hash='a' * 64, target='mock', **kwargs)


def test_defaults_no_env_credentials(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / '.env').write_text('KIS_APP_KEY=secret\nBIND_HOST=0.0.0.0')
    value = settings(tmp_path)
    assert value.bind_host == '127.0.0.1' and value.port == 8765
    assert value.max_rows == 100 and value.default_rows == 50
    assert value.export_days == 31 and value.export_rows == 10000
    assert value.export_bytes == 10 * 1024 * 1024
    with pytest.raises(ValidationError):
        settings(tmp_path, kis_app_key='secret')
    with pytest.raises(ValidationError):
        value.port = 9000


@pytest.mark.parametrize('host', ['0.0.0.0', '::', '*', '8.8.8.8', '192.168.1.1'])
def test_public_or_implicit_private_bind_rejected(tmp_path, host):
    with pytest.raises(ValidationError):
        settings(tmp_path, bind_host=host)


def test_private_endpoint_must_be_explicit_and_fixed(tmp_path):
    config = dict(private_mode=True, bind_host='100.100.1.2',
                  allowed_hosts=('bot.example.internal',),
                  allowed_origin='https://bot.example.internal', tls_termination=True,
                  trusted_proxies=('127.0.0.1',))
    assert settings(tmp_path, **config).private_mode
    for change in ({'allowed_hosts': ('*',)}, {'tls_termination': False},
                   {'allowed_origin': 'http://bot.example.internal'},
                   {'allowed_origin': 'https://evil.internal'},
                   {'allowed_origin': 'https://user@bot.example.internal'},
                   {'trusted_proxies': ('*',)}, {'bind_host': '0.0.0.0'}):
        with pytest.raises(ValidationError):
            settings(tmp_path, **(config | change))


def test_registration_is_immutable_positive_and_id_only(tmp_path):
    src = tmp_path / 'sources' / 'audit.db'
    src.parent.mkdir()
    src.write_bytes(b'evidence')
    value = settings(tmp_path, registered_resources=(resource(src),))
    assert value.resource('audit').path == src
    for request_id in ('../../sources/audit.db', str(src), 'unregistered'):
        with pytest.raises(ValueError):
            value.resource(request_id)
    for changes in ({'account_hash': ''}, {'target': 'unknown'}, {'id': '../audit'},
                    {'owner': 'broker'}, {'schema_family': 'unknown'}):
        with pytest.raises(ValidationError):
            ResourceDescriptor.model_validate(resource(src).model_dump() | changes)
    with pytest.raises(ValidationError):
        settings(tmp_path, registered_resources=(resource(src), resource(src)))


@pytest.mark.parametrize('kind', ['equal', 'parent', 'artifact', 'symlink', 'hardlink', 'nested'])
def test_topology_rejects_source_overlap_before_write(tmp_path, kind):
    src = tmp_path / 'source' / 'audit.db'
    src.parent.mkdir()
    src.write_bytes(b'unchanged-source')
    db, artifacts = tmp_path / 'operations' / 'web.db', tmp_path / 'artifacts'
    if kind == 'equal':
        db = src
    elif kind == 'parent':
        db = src.parent / 'web.db'
    elif kind == 'artifact':
        artifacts = src.parent
    elif kind == 'nested':
        artifacts = src.parent / 'child'
    elif kind == 'symlink':
        (tmp_path / 'operations').symlink_to(src.parent, target_is_directory=True)
    else:
        db.parent.mkdir()
        os.link(src, db)
    with pytest.raises((ValidationError, ValueError)):
        value = WebSettings(operational_db_path=db, artifact_root=artifacts,
                            registered_resources=(resource(src),))
        value.validate_topology()
    assert src.read_bytes() == b'unchanged-source'
    if kind != 'artifact':
        assert not artifacts.exists()


def test_bounds_and_cookie_secret_redaction(tmp_path):
    value = settings(tmp_path, cookie_secret='secret-sentinel-' + 'a' * 32)
    assert 'secret-sentinel' not in repr(value)
    for changes in ({'export_days': 367}, {'max_rows': 101}, {'export_rows': 10001},
                    {'export_bytes': 10485761}, {'default_rows': 101}):
        with pytest.raises(ValidationError):
            settings(tmp_path, **changes)


def test_artifact_nested_hardlink_or_symlink_is_rejected(tmp_path):
    src = tmp_path / 'source' / 'audit.db'
    src.parent.mkdir()
    src.write_bytes(b'unchanged')
    artifacts = tmp_path / 'artifacts'
    artifacts.mkdir()
    for hardlink in (True, False):
        alias = artifacts / 'report.json'
        if hardlink:
            os.link(src, alias)
        else:
            alias.symlink_to(src)
        with pytest.raises(ValueError):
            settings(tmp_path, registered_resources=(resource(src),)).validate_topology()
        alias.unlink()
