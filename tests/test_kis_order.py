"""Wave 0 scaffolds for the direct-REST KIS order adapter.

These tests intentionally collect before ``trading_bot.kis_order`` exists. When
the module lands in 05-02, each pending marker turns RED until the behavior is
implemented with the fake-client pattern imported below.
"""

from __future__ import annotations

import pytest

from test_kis_quote import _FakeClient, _FakeTokenManager, _response

ORDER_MODULE = "trading_bot.kis_order"


def _pending_until_module_exists(test_name: str) -> None:
    pytest.importorskip(ORDER_MODULE, reason="pending: implemented in 05-02")
    pytest.fail(f"pending: {test_name} implemented in 05-02")


def test_tick_snap() -> None:
    _pending_until_module_exists("tick-size snapping")


def test_tr_id_selection() -> None:
    _pending_until_module_exists("mock/real TR_ID selection")


def test_order_cash_body_headers_and_single_post() -> None:
    _pending_until_module_exists("order-cash body, headers, and single POST")


def test_fill_parsing() -> None:
    _pending_until_module_exists("fill status parsing")


__all__ = ["_FakeClient", "_FakeTokenManager", "_response"]
