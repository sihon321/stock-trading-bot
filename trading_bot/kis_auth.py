"""Shared KIS access-token manager (DATA-03, D-02/D-14/D-15).

This is the one place KIS bearer tokens are issued. Phase 3 quote calls consume
it now and Phase 5 broker/order calls reuse the same cached flow rather than
opening a second token path (D-14). The manager caches the access token until a
configurable refresh margin ahead of the runtime-discovered expiry (never a
hard-coded TTL), serializes refreshes behind a lock, bounds retries/backoff, and
normalizes every failure mode - HTTP error status, malformed JSON, missing or
invalid token/expiry, throttling, and exhausted retries - into an UNAVAILABLE
:class:`~trading_bot.data_models.SourceHealth` carried by :class:`KisAuthError`
(D-15).

Secret safety (threat T-03-04-I): the app key/secret and the access token never
appear in reprs, health reasons, logs, or exceptions. :class:`KisAuthConfig`
overrides ``__repr__`` to redact credentials and the cached token is stored on a
private attribute that is not surfaced through any repr.

The HTTP client and clock are injectable so tests run fully offline with fake
clients and a deterministic monotonic clock.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Optional

from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from trading_bot.config import Settings
from trading_bot.data_models import SourceHealth, SourceStatus

_SOURCE = "kis_auth"
_TOKEN_PATH = "/oauth2/tokenP"


class _TransientAuthError(Exception):
    """Internal marker for retryable transient token-issue failures."""


class KisAuthError(Exception):
    """Raised when a KIS token cannot be obtained after the bounded policy.

    Carries a normalized :class:`SourceHealth` (``UNAVAILABLE``) so callers can
    apply source-health policy without inspecting vendor exceptions. The message
    and health reason are non-secret category strings only.
    """

    def __init__(self, health: SourceHealth) -> None:
        super().__init__(health.reason)
        self.health = health


@dataclass(frozen=True)
class KisToken:
    """A cached KIS access token and its monotonic-clock expiry deadline."""

    access_token: str
    expires_at: float


@dataclass(frozen=True)
class KisAuthConfig:
    """Non-secret-safe KIS auth configuration sourced from ``Settings.active_kis``.

    ``app_key``/``app_secret`` are held as plain strings for the request body but
    are redacted from ``__repr__`` so the credentials never surface in logs or
    diagnostics (threat T-03-04-I).
    """

    domain: str
    app_key: str
    app_secret: str
    refresh_margin_seconds: int
    min_interval_seconds: float
    max_retries: int
    retry_backoff_seconds: float
    timeout_seconds: float = 5.0

    def __repr__(self) -> str:  # pragma: no cover - trivial redaction
        return (
            "KisAuthConfig("
            f"domain={self.domain!r}, app_key='REDACTED', app_secret='REDACTED', "
            f"refresh_margin_seconds={self.refresh_margin_seconds}, "
            f"min_interval_seconds={self.min_interval_seconds}, "
            f"max_retries={self.max_retries}, "
            f"retry_backoff_seconds={self.retry_backoff_seconds}, "
            f"timeout_seconds={self.timeout_seconds})"
        )


def build_kis_auth_config(settings: Settings) -> KisAuthConfig:
    """Build a :class:`KisAuthConfig` from the selected KIS credential group.

    Uses ``Settings.active_kis`` as the ONLY credential source (D-14) and the
    Phase 3 KIS token/rate controls for timing/retry defaults.
    """

    active = settings.active_kis
    return KisAuthConfig(
        domain=active.domain,
        app_key=active.app_key.get_secret_value(),
        app_secret=active.app_secret.get_secret_value(),
        refresh_margin_seconds=settings.kis_token_refresh_margin_seconds,
        min_interval_seconds=settings.kis_min_interval_seconds,
        max_retries=settings.kis_max_retries,
        retry_backoff_seconds=settings.kis_retry_backoff_seconds,
    )


def _unavailable(reason: str) -> SourceHealth:
    return SourceHealth(source=_SOURCE, status=SourceStatus.UNAVAILABLE, reason=reason)


def _parse_expiry(body: dict, *, now: float) -> float:
    """Derive a monotonic-clock expiry deadline from the token response.

    Prefers the numeric ``expires_in`` seconds; falls back to the wall-clock
    ``access_token_token_expired`` timestamp converted to a remaining duration.
    Never hard-codes a TTL. Raises ``ValueError`` on missing/invalid expiry.
    """

    if "expires_in" in body and body["expires_in"] is not None:
        seconds = float(body["expires_in"])  # raises ValueError/TypeError on bad input
        if seconds <= 0:
            raise ValueError("non-positive expires_in")
        return now + seconds

    expired_at = body.get("access_token_token_expired")
    if isinstance(expired_at, str) and expired_at.strip():
        deadline = datetime.strptime(expired_at.strip(), "%Y-%m-%d %H:%M:%S")
        remaining = deadline.timestamp() - time.time()
        if remaining <= 0:
            raise ValueError("token already expired")
        return now + remaining

    raise ValueError("token response missing a usable expiry")


class KisTokenManager:
    """Thread-safe cached KIS token manager reusable across KIS adapters.

    Args:
        config: Non-secret-safe :class:`KisAuthConfig`.
        client: An object exposing ``post(url, *, json, headers, timeout)`` that
            returns an ``httpx.Response``-like object. Injectable for offline
            tests; defaults to a real ``httpx.Client``.
        clock: A monotonic time source (seconds). Injectable for tests; defaults
            to :func:`time.monotonic`.
    """

    def __init__(
        self,
        config: KisAuthConfig,
        *,
        client: Any = None,
        clock: Optional[Callable[[], float]] = None,
    ) -> None:
        if client is None:
            import httpx

            client = httpx.Client()
        self._config = config
        self._client = client
        self._clock = clock or time.monotonic
        self._lock = threading.RLock()
        self._token: Optional[KisToken] = None
        self._last_request_at: Optional[float] = None

    def __repr__(self) -> str:  # pragma: no cover - trivial redaction
        cached = self._token is not None
        return f"KisTokenManager(domain={self._config.domain!r}, cached={cached})"

    def get_token(self) -> str:
        """Return a valid access token, refreshing only inside the margin window."""

        with self._lock:
            if self._token is not None and not self._needs_refresh(self._token):
                return self._token.access_token
            return self._refresh_locked()

    def refresh_token(self) -> str:
        """Force a token refresh regardless of the cached token's remaining life."""

        with self._lock:
            return self._refresh_locked()

    def _needs_refresh(self, token: KisToken) -> bool:
        return self._clock() >= (token.expires_at - self._config.refresh_margin_seconds)

    def _refresh_locked(self) -> str:
        token = self._issue_token()
        self._token = token
        return token.access_token

    def _issue_token(self) -> KisToken:
        """Issue a new token with bounded retry/backoff and failure normalization."""

        attempts = max(1, int(self._config.max_retries))
        wait_seconds = max(0.0, float(self._config.retry_backoff_seconds))

        @retry(
            reraise=True,
            stop=stop_after_attempt(attempts),
            wait=wait_fixed(wait_seconds),
            retry=retry_if_exception_type(_TransientAuthError),
        )
        def _attempt() -> KisToken:
            return self._request_token()

        try:
            return _attempt()
        except _TransientAuthError as exc:
            raise KisAuthError(_unavailable(str(exc))) from None
        except RetryError:  # pragma: no cover - reraise=True avoids this
            raise KisAuthError(_unavailable("token issue exhausted retries")) from None
        except KisAuthError:
            raise

    def _request_token(self) -> KisToken:
        self._respect_min_interval()

        url = self._config.domain.rstrip("/") + _TOKEN_PATH
        payload = {
            "grant_type": "client_credentials",
            "appkey": self._config.app_key,
            "appsecret": self._config.app_secret,
        }
        headers = {"content-type": "application/json"}

        try:
            response = self._client.post(
                url,
                json=payload,
                headers=headers,
                timeout=self._config.timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001 - transient network/transport failure.
            # Retryable: normalize to a category string, never the exception text.
            raise _TransientAuthError(
                f"token request failed: {type(exc).__name__}"
            ) from None

        status = getattr(response, "status_code", None)
        if status is None or int(status) >= 400:
            # Non-2xx (incl. 401/403/429/5xx) is retryable; do not leak body.
            raise _TransientAuthError(f"token request returned HTTP {status}")

        try:
            body = response.json()
        except Exception:  # noqa: BLE001 - malformed/non-JSON body is terminal.
            raise KisAuthError(_unavailable("token response was not valid JSON")) from None

        if not isinstance(body, dict):
            raise KisAuthError(_unavailable("token response was not a JSON object"))

        access_token = body.get("access_token")
        if not isinstance(access_token, str) or not access_token.strip():
            raise KisAuthError(_unavailable("token response missing access_token"))

        try:
            expires_at = _parse_expiry(body, now=self._clock())
        except (ValueError, TypeError, OverflowError):
            raise KisAuthError(
                _unavailable("token response has missing or invalid expiry")
            ) from None

        return KisToken(access_token=access_token, expires_at=expires_at)

    def _respect_min_interval(self) -> None:
        interval = float(self._config.min_interval_seconds)
        if interval <= 0:
            self._last_request_at = self._clock()
            return
        now = self._clock()
        if self._last_request_at is not None:
            elapsed = now - self._last_request_at
            if elapsed < interval:
                time.sleep(interval - elapsed)
        self._last_request_at = self._clock()
