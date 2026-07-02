"""Behavior tests for the fail-soft Discord notifier."""

from __future__ import annotations

import logging
from typing import Any

from pydantic import SecretStr

from trading_bot.ports import Notifier
from conftest import make_settings


class _FakeWebhookClient:
    def __init__(self, *, responses=None, error: Exception | None = None) -> None:
        self.calls = []
        self._responses = list(responses or [])
        self._error = error

    def post(self, url, *, json=None, timeout=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        if self._error is not None:
            raise self._error
        if self._responses:
            response = self._responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response
        return _FakeResponse(204)


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def test_consolidated_summary() -> None:
    from trading_bot.notifier import DiscordNotifier, format_run_summary

    client = _FakeWebhookClient()
    notifier = DiscordNotifier(
        webhook_url=SecretStr("https://discord.example/webhook/sentinel-secret"),
        client=client,
        max_retries=1,
        retry_backoff_seconds=0,
    )
    outcomes: list[dict[str, Any]] = [
        {
            "ticker": "005930",
            "final_action": "BUY",
            "parsed_decision": "BUY",
            "confidence": 0.91,
            "broker_order_id": "KIS-1",
            "filled_qty": 2,
        },
        {
            "ticker": "000660",
            "final_action": "HOLD",
            "parsed_decision": "HOLD",
            "confidence": 0.42,
            "order_reason": "confidence below threshold",
        },
    ]

    summary = format_run_summary(
        run_id="run-001",
        trading_mode="mock",
        dry_run=False,
        outcomes=outcomes,
    )
    assert notifier.send(summary) is True

    assert isinstance(notifier, Notifier)
    assert len(client.calls) == 1
    body = client.calls[0]["json"]
    assert set(body) == {"content"}
    assert "005930" in body["content"]
    assert "BUY" in body["content"]
    assert "KIS-1" in body["content"]
    assert "000660" in body["content"]
    assert "HOLD" in body["content"]
    assert "sentinel-secret" not in body["content"]


def test_fail_soft(caplog) -> None:
    from trading_bot.notifier import DiscordNotifier

    caplog.set_level(logging.WARNING)
    secret = "https://discord.example/webhook/sentinel-secret"
    client = _FakeWebhookClient(responses=[_FakeResponse(500), _FakeResponse(500)])
    notifier = DiscordNotifier(
        webhook_url=SecretStr(secret),
        client=client,
        max_retries=2,
        retry_backoff_seconds=0,
    )

    assert notifier.send("run summary without webhook value") is False
    assert len(client.calls) == 2
    assert "sentinel-secret" not in repr(notifier)
    assert "sentinel-secret" not in str(caplog.records)


def test_missing_webhook_builds_noop_notifier() -> None:
    from trading_bot.notifier import NoopNotifier, build_notifier

    notifier = build_notifier(make_settings(discord_webhook_url=None))

    assert isinstance(notifier, NoopNotifier)
    assert isinstance(notifier, Notifier)
    assert notifier.send("anything") is False


__all__ = ["_FakeWebhookClient", "make_settings"]
