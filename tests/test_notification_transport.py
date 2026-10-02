"""Pure notification transport contract: injected clients only, no Discord calls."""
import logging
import os
import subprocess
import sys
from types import SimpleNamespace

import pytest
from pydantic import SecretStr

from trading_bot.notification_transport import DiscordNotifier, NoopNotifier

SECRET = "https://discord.invalid/api/webhooks/sentinel-secret/token"


class Client:
    def __init__(self, outcomes):
        self.outcomes = iter(outcomes)
        self.calls = []

    def post(self, url, *, json, timeout):
        self.calls.append((url, json, timeout))
        result = next(self.outcomes)
        if isinstance(result, Exception):
            raise result
        return result


def notifier(client, retries=3):
    return DiscordNotifier(webhook_url=SecretStr(SECRET), client=client,
                           max_retries=retries, retry_backoff_seconds=0, timeout_seconds=2.5)


def test_transport_import_has_no_trading_settings_broker_cli_or_provider_graph():
    script = """
import importlib.abc
import sys
blocked = ('trading_bot.config', 'trading_bot.cli', 'trading_bot.ports',
           'trading_bot.broker', 'trading_bot.kis', 'trading_bot.provider', 'pykis', 'openai', 'anthropic')
class Guard(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if any(fullname == name or fullname.startswith(name + '.') for name in blocked):
            raise AssertionError('forbidden capability import')
sys.meta_path.insert(0, Guard())
from trading_bot.notification_transport import DiscordNotifier, NoopNotifier
assert NoopNotifier().send('bounded fake summary') is False
assert not any(name in sys.modules for name in blocked)
"""
    process = subprocess.run([sys.executable, "-c", script], env=os.environ.copy(),
                             text=True, capture_output=True, timeout=10)
    assert process.returncode == 0, process.stderr
    assert SECRET not in process.stdout + process.stderr


def test_transport_bounded_retry_timeout_and_success_without_external_network():
    client = Client([RuntimeError(SECRET), SimpleNamespace(status_code=503), SimpleNamespace(status_code=204)])
    assert notifier(client).send("saved evidence summary") is True
    assert len(client.calls) == 3
    assert all(call[2] == 2.5 for call in client.calls)
    assert client.calls[-1][1] == {"content": "saved evidence summary"}


def test_transport_fail_soft_redacts_secret_exception_response_and_repr(caplog):
    caplog.set_level(logging.DEBUG)
    client = Client([RuntimeError("exception body: " + SECRET)] * 3)
    transport = notifier(client)
    assert transport.send("safe summary") is False
    assert len(client.calls) == 3
    assert "sentinel-secret" not in repr(transport) + caplog.text
    def raise_body():
        raise RuntimeError("response body: " + SECRET)
    response = SimpleNamespace(status_code=204, raise_for_status=raise_body)
    failed = notifier(Client([response]), retries=1)
    assert failed.send("safe summary") is False
    assert "sentinel-secret" not in repr(failed) + caplog.text


@pytest.mark.parametrize("status", [None, 199, 302, 400, 429, 503])
def test_transport_requires_positive_2xx_response(status):
    client = Client([SimpleNamespace(status_code=status)] * 2)
    assert notifier(client, retries=2).send("safe summary") is False
    assert len(client.calls) == 2


def test_transport_compatibility_reexports_factory_and_noop():
    from trading_bot.notifier import DiscordNotifier as LegacyDiscord
    from trading_bot.notifier import NoopNotifier as LegacyNoop, build_notifier
    from conftest import make_settings
    assert LegacyDiscord is DiscordNotifier and LegacyNoop is NoopNotifier
    assert isinstance(build_notifier(make_settings(discord_webhook_url=None)), NoopNotifier)
    client = Client([SimpleNamespace(status_code=204)])
    built = build_notifier(make_settings(discord_webhook_url=SecretStr(SECRET)), client=client)
    assert isinstance(built, DiscordNotifier) and built.send("safe summary") is True
