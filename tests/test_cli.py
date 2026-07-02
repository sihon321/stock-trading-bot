"""Wave 0 scaffolds for the Typer CLI real-money gate and run loop."""

from __future__ import annotations

import pytest

from conftest import make_settings

CLI_MODULE = "trading_bot.cli"


def _pending_until_module_exists(test_name: str) -> None:
    pytest.importorskip(CLI_MODULE, reason="pending: implemented in 05-04")
    pytest.fail(f"pending: {test_name} implemented in 05-04")


def test_real_execute_requires_live_confirm() -> None:
    _pending_until_module_exists("real execute requires --live-confirm")


def test_ticker_error_isolation() -> None:
    _pending_until_module_exists("per-ticker error isolation")


def test_dry_run_default_no_orders() -> None:
    _pending_until_module_exists("dry-run default places no orders")


def test_immediate_error_push() -> None:
    _pending_until_module_exists("cycle-level error sends immediate push")


__all__ = ["make_settings"]
