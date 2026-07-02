"""Fail-soft operator notification adapters."""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import SecretStr
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from trading_bot.config import Settings
from trading_bot.ports import Notifier

logger = logging.getLogger(__name__)


class _TransientNotificationError(Exception):
    """Internal marker for retryable notification delivery failures."""


class NoopNotifier:
    """Notifier used when no webhook is configured."""

    def __repr__(self) -> str:  # pragma: no cover - trivial
        return "NoopNotifier()"

    def send(self, summary: str) -> bool:
        """Skip delivery and report that no notification was sent."""

        _ = summary
        logger.info("notification skipped: no webhook configured")
        return False


class DiscordNotifier:
    """Discord webhook notifier that never lets delivery failure escape."""

    def __init__(
        self,
        *,
        webhook_url: SecretStr | str,
        client: Any = None,
        max_retries: int = 3,
        retry_backoff_seconds: float = 1.0,
        timeout_seconds: float = 5.0,
    ) -> None:
        if client is None:
            import httpx

            client = httpx.Client()
        if isinstance(webhook_url, SecretStr):
            self._webhook_url = webhook_url.get_secret_value()
        else:
            self._webhook_url = str(webhook_url)
        self._client = client
        self._max_retries = max(1, int(max_retries))
        self._retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))
        self._timeout_seconds = float(timeout_seconds)

    def __repr__(self) -> str:  # pragma: no cover - trivial redaction
        return (
            "DiscordNotifier(webhook_url='REDACTED', "
            f"max_retries={self._max_retries}, "
            f"retry_backoff_seconds={self._retry_backoff_seconds}, "
            f"timeout_seconds={self._timeout_seconds})"
        )

    def send(self, summary: str) -> bool:
        """Send a consolidated run summary, returning False after final failure."""

        try:
            self._post_with_retry(summary)
            return True
        except Exception:  # noqa: BLE001 - notification must never block trading.
            logger.warning("discord notification failed after bounded retry")
            return False

    def _post_with_retry(self, summary: str) -> None:
        @retry(
            reraise=True,
            stop=stop_after_attempt(self._max_retries),
            wait=wait_fixed(self._retry_backoff_seconds),
            retry=retry_if_exception_type(_TransientNotificationError),
        )
        def _attempt() -> None:
            try:
                response = self._client.post(
                    self._webhook_url,
                    json={"content": summary},
                    timeout=self._timeout_seconds,
                )
            except Exception as exc:  # noqa: BLE001 - transports vary.
                raise _TransientNotificationError(
                    f"discord webhook transport failed: {type(exc).__name__}"
                ) from None

            status = getattr(response, "status_code", None)
            if status is None or int(status) >= 400:
                raise _TransientNotificationError("discord webhook returned non-2xx")

            raise_for_status = getattr(response, "raise_for_status", None)
            if callable(raise_for_status):
                try:
                    raise_for_status()
                except Exception as exc:  # noqa: BLE001 - httpx-compatible clients vary.
                    raise _TransientNotificationError(
                        f"discord webhook response failed: {type(exc).__name__}"
                    ) from None

        _attempt()


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
