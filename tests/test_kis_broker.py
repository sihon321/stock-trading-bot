"""Wave 0 scaffolds for the KIS Broker adapter."""

from __future__ import annotations

import pytest

from conftest import make_settings

BROKER_MODULE = "trading_bot.kis_broker"


def _pending_until_module_exists(test_name: str) -> None:
    pytest.importorskip(BROKER_MODULE, reason="pending: implemented in 05-02")
    pytest.fail(f"pending: {test_name} implemented in 05-02")


def test_order_post_not_retried() -> None:
    _pending_until_module_exists("order POST is never retried")


def test_reconcile_skips_duplicate() -> None:
    _pending_until_module_exists("query-before-POST duplicate reconciliation")


def test_partial_fill_reconciled() -> None:
    _pending_until_module_exists("partial-fill reconciliation")


def test_kis_broker_is_broker() -> None:
    _pending_until_module_exists("Broker Protocol structural conformance")


def test_tick_snap_and_market_guard() -> None:
    _pending_until_module_exists("tick snapping and market-hours guard")


__all__ = ["make_settings"]
