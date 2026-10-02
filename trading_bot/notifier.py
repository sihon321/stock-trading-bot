"""Fail-soft operator notification adapters."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from trading_bot.config import Settings
from trading_bot.ports import Notifier
from trading_bot.notification_transport import DiscordNotifier, NoopNotifier


def _value(outcome: Any, key: str, default: Any = "") -> Any:
    if isinstance(outcome, Mapping):
        return outcome.get(key, default)
    return getattr(outcome, key, default)


def format_run_summary(
    *,
    run_id: str,
    trading_mode: str,
    dry_run: bool,
    outcomes: Sequence[Any],
) -> str:
    """Format one Discord message for a whole run, never one message per ticker."""

    lines = [
        f"Trading run {run_id}",
        f"Mode: {trading_mode} | dry_run: {dry_run}",
        "Decisions:",
    ]
    if not outcomes:
        lines.append("- no ticker outcomes recorded")
        return "\n".join(lines)

    for outcome in outcomes:
        ticker = _value(outcome, "ticker", "UNKNOWN")
        final_action = _value(outcome, "final_action", _value(outcome, "action", "UNKNOWN"))
        parsed_decision = _value(outcome, "parsed_decision", "")
        confidence = _value(outcome, "confidence", None)
        order_id = _value(outcome, "broker_order_id", None)
        filled_qty = _value(outcome, "filled_qty", None)
        reason = _value(outcome, "order_reason", _value(outcome, "reason", ""))

        details = [f"- {ticker}: {final_action}"]
        if parsed_decision:
            details.append(f"signal={parsed_decision}")
        if confidence is not None:
            details.append(f"confidence={confidence}")
        if order_id:
            details.append(f"order_id={order_id}")
        if filled_qty is not None:
            details.append(f"filled_qty={filled_qty}")
        if reason:
            details.append(f"reason={reason}")
        lines.append(" | ".join(str(item) for item in details))

    return "\n".join(lines)


def build_notifier(settings: Settings, *, client: Any = None) -> Notifier:
    """Build the configured notifier, constructing the HTTP client lazily."""

    if settings.discord_webhook_url is None:
        return NoopNotifier()
    return DiscordNotifier(
        webhook_url=settings.discord_webhook_url,
        client=client,
        max_retries=settings.kis_max_retries,
        retry_backoff_seconds=settings.kis_retry_backoff_seconds,
        timeout_seconds=settings.order_timeout_seconds,
    )
