"""Wave 0 scaffolds for the fail-soft Discord notifier."""

from __future__ import annotations

import pytest

from conftest import make_settings

NOTIFIER_MODULE = "trading_bot.notifier"


class _FakeWebhookClient:
    def __init__(self) -> None:
        self.calls = []

    def post(self, url, *, json=None, timeout=None):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        raise AssertionError("pending fake client should be wired by 05-03")


def _pending_until_module_exists(test_name: str) -> None:
    pytest.importorskip(NOTIFIER_MODULE, reason="pending: implemented in 05-03")
    pytest.fail(f"pending: {test_name} implemented in 05-03")


def test_consolidated_summary() -> None:
    _pending_until_module_exists("one consolidated run summary")


def test_fail_soft() -> None:
    _pending_until_module_exists("notification failure is fail-soft")


__all__ = ["_FakeWebhookClient", "make_settings"]
