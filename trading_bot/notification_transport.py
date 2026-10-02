"""Credential-independent fail-soft transport; callers inject a webhook and client."""
from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any

from pydantic import SecretStr
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_fixed

logger = logging.getLogger(__name__)


class _TransientNotificationError(Exception):
    """Internal bounded marker; never includes webhook or exception bodies."""


class _WebhookRequestLogFilter(logging.Filter):
    """HTTPX logs request URLs at INFO; suppress secret-bearing request details."""

    def filter(self, record: logging.LogRecord) -> bool:
        # HTTPX's request logger is shared. A scoped generic filter avoids keeping
        # credentials in logger state and also protects concurrent webhook sends.
        if record.msg == 'HTTP Request: %s %s "%s %d %s"':
            record.msg = "HTTP notification request completed (details redacted)"
            record.args = ()
        return True


@contextmanager
def _redacted_request_logging():
    request_logger = logging.getLogger("httpx")
    redactor = _WebhookRequestLogFilter()
    request_logger.addFilter(redactor)
    try:
        yield
    finally:
        request_logger.removeFilter(redactor)


class NoopNotifier:
    """Notifier used when no webhook is configured."""

    def __repr__(self) -> str:
        return "NoopNotifier()"

    def send(self, summary: str) -> bool:
        """Skip delivery and report that no notification was sent."""
        logger.info("notification skipped: no webhook configured")
        return False


class DiscordNotifier:
    """Discord webhook notifier that never lets delivery failure escape."""

    def __init__(self, *, webhook_url: SecretStr | str, client: Any = None,
                 max_retries: int = 3, retry_backoff_seconds: float = 1.0,
                 timeout_seconds: float = 5.0) -> None:
        if client is None:
            import httpx
            client = httpx.Client()
        self._webhook_url = webhook_url.get_secret_value() if isinstance(webhook_url, SecretStr) else str(webhook_url)
        self._client = client
        self._max_retries = max(1, int(max_retries))
        self._retry_backoff_seconds = max(0.0, float(retry_backoff_seconds))
        self._timeout_seconds = float(timeout_seconds)

    def __repr__(self) -> str:
        return ("DiscordNotifier(webhook_url='REDACTED', "
                f"max_retries={self._max_retries}, "
                f"retry_backoff_seconds={self._retry_backoff_seconds}, "
                f"timeout_seconds={self._timeout_seconds})")

    def send(self, summary: str) -> bool:
        """Send one summary, returning False after the final bounded failure."""
        try:
            with _redacted_request_logging():
                self._post_with_retry(summary)
            return True
        except Exception:  # noqa: BLE001 - notification remains fail-soft.
            logger.warning("discord notification failed after bounded retry")
            return False

    def _post_with_retry(self, summary: str) -> None:
        @retry(reraise=True, stop=stop_after_attempt(self._max_retries),
               wait=wait_fixed(self._retry_backoff_seconds),
               retry=retry_if_exception_type(_TransientNotificationError))
        def _attempt() -> None:
            try:
                response = self._client.post(self._webhook_url, json={"content": summary},
                                             timeout=self._timeout_seconds)
            except Exception:  # noqa: BLE001 - injected transports vary.
                raise _TransientNotificationError("TRANSPORT_FAILED") from None
            status = getattr(response, "status_code", None)
            if status is None or not 200 <= int(status) < 300:
                raise _TransientNotificationError("RESPONSE_NOT_2XX")
            raise_for_status = getattr(response, "raise_for_status", None)
            if callable(raise_for_status):
                try:
                    raise_for_status()
                except Exception:  # noqa: BLE001 - do not expose response bodies.
                    raise _TransientNotificationError("RESPONSE_FAILED") from None
        _attempt()
