"""Wave 0 scaffolds for the SQLite audit writer."""

from __future__ import annotations

import pytest

AUDIT_MODULE = "trading_bot.sqlite_audit"


def _pending_until_module_exists(test_name: str) -> None:
    pytest.importorskip(AUDIT_MODULE, reason="pending: implemented in 05-03")
    pytest.fail(f"pending: {test_name} implemented in 05-03")


def test_two_table_write(tmp_path) -> None:
    _ = tmp_path
    _pending_until_module_exists("runs and decisions two-table write")


def test_correlation_id(tmp_path) -> None:
    _ = tmp_path
    _pending_until_module_exists("correlation ID persistence")
