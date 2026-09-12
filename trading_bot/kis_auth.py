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

import hashlib
import hmac
import json
import os
import stat
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Iterator, Optional

from tenacity import (
    RetryError,
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_fixed,
)

from trading_bot.config import Settings
from trading_bot.data_models import SourceHealth, SourceStatus
from trading_bot.kis_rate_limit import KisRequestLimiter

_SOURCE = "kis_auth"
_TOKEN_PATH = "/oauth2/tokenP"
_CACHE_VERSION = 1
_MAX_CACHE_BYTES = 64 * 1024


class _TransientAuthError(Exception):
    """Internal retry marker carrying a bounded, non-secret diagnostic code."""

    def __init__(self, message: str, *, reason_code: str) -> None:
        super().__init__(message)
        self.reason_code = reason_code


class KisAuthError(Exception):
    """Raised when a KIS token cannot be obtained after the bounded policy.

    Carries a normalized :class:`SourceHealth` (``UNAVAILABLE``) so callers can
    apply source-health policy without inspecting vendor exceptions. The message
    and health reason are non-secret category strings only.
    """

    def __init__(
        self, health: SourceHealth, *, reason_code: str = "AUTH_UNAVAILABLE"
    ) -> None:
        super().__init__(health.reason)
        self.health = health
        self.reason_code = reason_code


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
    cache_path: Path | None = None

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
        cache_path=settings.kis_token_cache_path,
    )


def _unavailable(reason: str) -> SourceHealth:
    return SourceHealth(source=_SOURCE, status=SourceStatus.UNAVAILABLE, reason=reason)


def _parse_expiry(body: dict, *, now: float, wall_now: float | None = None) -> float:
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
        remaining = deadline.timestamp() - (
            time.time() if wall_now is None else wall_now
        )
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
        wall_clock: Optional[Callable[[], float]] = None,
        request_limiter: KisRequestLimiter | None = None,
    ) -> None:
        if client is None:
            import httpx

            client = httpx.Client()
        self._config = config
        self._client = client
        self._clock = clock or time.monotonic
        self._wall_clock = wall_clock or time.time
        self._lock = threading.RLock()
        self._token: Optional[KisToken] = None
        self._last_request_at: Optional[float] = None
        self._request_limiter = request_limiter

    def __repr__(self) -> str:  # pragma: no cover - trivial redaction
        cached = self._token is not None
        return f"KisTokenManager(domain={self._config.domain!r}, cached={cached})"

    @property
    def app_key(self) -> str:
        """Expose the app key for KIS request headers (never logged)."""

        return self._config.app_key

    @property
    def app_secret(self) -> str:
        """Expose the app secret for KIS request headers (never logged)."""

        return self._config.app_secret

    def get_token(self) -> str:
        """Return a valid access token, refreshing only inside the margin window."""

        with self._lock:
            if self._token is not None and not self._needs_refresh(self._token):
                return self._token.access_token
            with self._process_cache_lock() as cache_available:
                if cache_available:
                    cached = self._load_cached_token()
                    if cached is not None:
                        self._token = cached
                        return cached.access_token
                return self._refresh_locked(persist=cache_available)

    def refresh_token(self) -> str:
        """Force a token refresh regardless of the cached token's remaining life."""

        with self._lock:
            with self._process_cache_lock() as cache_available:
                return self._refresh_locked(persist=cache_available)

    def _needs_refresh(self, token: KisToken) -> bool:
        return self._clock() >= (token.expires_at - self._config.refresh_margin_seconds)

    def _refresh_locked(self, *, persist: bool = False) -> str:
        token = self._issue_token()
        self._token = token
        if persist:
            self._store_cached_token(token)
        return token.access_token

    @property
    def _cache_path(self) -> Path | None:
        path = self._config.cache_path
        if path is None:
            return None
        resolved = Path(path).expanduser()
        if not resolved.name:
            return None
        return resolved

    @property
    def _credential_fingerprint(self) -> str:
        identity = "\0".join(
            (
                self._config.domain.rstrip("/"),
                self._config.app_key,
                self._config.app_secret,
            )
        ).encode("utf-8")
        return hashlib.sha256(identity).hexdigest()

    @contextmanager
    def _process_cache_lock(self) -> Iterator[bool]:
        """Serialize cache read/refresh/write across CLI processes when possible."""

        cache_path = self._cache_path
        if cache_path is None or not self._prepare_cache_directory(cache_path.parent):
            yield False
            return

        lock_path = cache_path.with_name(f"{cache_path.name}.lock")
        flags = os.O_CREAT | os.O_RDWR
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(lock_path, flags, 0o600)
            os.fchmod(descriptor, 0o600)
        except OSError:
            yield False
            return

        try:
            try:
                import fcntl

                fcntl.flock(descriptor, fcntl.LOCK_EX)
            except (ImportError, OSError):
                yield False
                return
            try:
                yield True
            finally:
                fcntl.flock(descriptor, fcntl.LOCK_UN)
        finally:
            os.close(descriptor)

    @staticmethod
    def _prepare_cache_directory(directory: Path) -> bool:
        try:
            if directory.exists():
                metadata = directory.lstat()
                return (
                    stat.S_ISDIR(metadata.st_mode)
                    and not directory.is_symlink()
                    and stat.S_IMODE(metadata.st_mode) & 0o077 == 0
                )
            directory.mkdir(parents=True, mode=0o700)
            metadata = directory.lstat()
            return (
                stat.S_ISDIR(metadata.st_mode)
                and not directory.is_symlink()
                and stat.S_IMODE(metadata.st_mode) & 0o077 == 0
            )
        except OSError:
            return False

    def _load_cached_token(self) -> KisToken | None:
        document = self._read_cache_document()
        entries = document.get("entries")
        if not isinstance(entries, dict):
            return None
        entry = entries.get(self._credential_fingerprint)
        if not isinstance(entry, dict):
            return None

        access_token = entry.get("access_token")
        expires_at_epoch = entry.get("expires_at_epoch")
        signature = entry.get("signature")
        if not isinstance(access_token, str) or not access_token.strip():
            return None
        if not isinstance(signature, str):
            return None
        try:
            expires_at_epoch = float(expires_at_epoch)
        except (TypeError, ValueError, OverflowError):
            return None
        expected = self._cache_signature(access_token, expires_at_epoch)
        if not hmac.compare_digest(signature, expected):
            return None

        remaining = expires_at_epoch - self._wall_clock()
        if remaining <= self._config.refresh_margin_seconds:
            return None
        return KisToken(
            access_token=access_token,
            expires_at=self._clock() + remaining,
        )

    def _read_cache_document(self) -> dict[str, Any]:
        cache_path = self._cache_path
        if cache_path is None:
            return {}
        try:
            metadata = cache_path.lstat()
            if (
                not stat.S_ISREG(metadata.st_mode)
                or stat.S_IMODE(metadata.st_mode) & 0o077
                or metadata.st_size > _MAX_CACHE_BYTES
            ):
                return {}
            flags = os.O_RDONLY
            if hasattr(os, "O_NOFOLLOW"):
                flags |= os.O_NOFOLLOW
            descriptor = os.open(cache_path, flags)
            with os.fdopen(descriptor, encoding="utf-8") as stream:
                document = json.load(stream)
        except (OSError, UnicodeError, json.JSONDecodeError, ValueError):
            return {}
        if not isinstance(document, dict) or document.get("version") != _CACHE_VERSION:
            return {}
        return document

    def _store_cached_token(self, token: KisToken) -> None:
        cache_path = self._cache_path
        if cache_path is None:
            return
        remaining = max(0.0, token.expires_at - self._clock())
        expires_at_epoch = round(self._wall_clock() + remaining, 6)
        document = self._read_cache_document()
        entries = document.get("entries")
        if not isinstance(entries, dict):
            entries = {}
        else:
            entries = dict(entries)
        entries[self._credential_fingerprint] = {
            "access_token": token.access_token,
            "expires_at_epoch": expires_at_epoch,
            "signature": self._cache_signature(token.access_token, expires_at_epoch),
        }
        payload = json.dumps(
            {"version": _CACHE_VERSION, "entries": entries},
            ensure_ascii=True,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
        if len(payload) > _MAX_CACHE_BYTES:
            return

        temporary = cache_path.with_name(
            f".{cache_path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        try:
            descriptor = os.open(temporary, flags, 0o600)
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, cache_path)
            cache_path.chmod(0o600)
        except OSError:
            try:
                if temporary.is_file() and not temporary.is_symlink():
                    temporary.unlink()
            except OSError:
                pass

    def _cache_signature(self, access_token: str, expires_at_epoch: float) -> str:
        message = "\0".join(
            (
                self._credential_fingerprint,
                access_token,
                f"{expires_at_epoch:.6f}",
            )
        ).encode("utf-8")
        return hmac.new(
            self._config.app_secret.encode("utf-8"),
            message,
            hashlib.sha256,
        ).hexdigest()

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
            raise KisAuthError(
                _unavailable(str(exc)), reason_code=exc.reason_code
            ) from None
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
            error_type = type(exc).__name__
            raise _TransientAuthError(
                f"token request failed: {error_type}",
                reason_code=(
                    "AUTH_TIMEOUT"
                    if "timeout" in error_type.lower()
                    else "AUTH_TRANSPORT_ERROR"
                ),
            ) from None

        status = getattr(response, "status_code", None)
        if status is None or int(status) >= 400:
            # Non-2xx (incl. 401/403/429/5xx) is retryable; do not leak body.
            numeric_status = int(status) if status is not None else None
            if numeric_status in {401, 403}:
                reason_code = "AUTH_HTTP_AUTH_ERROR"
            elif numeric_status == 429:
                reason_code = "AUTH_HTTP_RATE_LIMITED"
            else:
                reason_code = "AUTH_HTTP_ERROR"
            raise _TransientAuthError(
                f"token request returned HTTP {status}", reason_code=reason_code
            )

        try:
            body = response.json()
        except Exception:  # noqa: BLE001 - malformed/non-JSON body is terminal.
            raise KisAuthError(
                _unavailable("token response was not valid JSON"),
                reason_code="AUTH_RESPONSE_INVALID",
            ) from None

        if not isinstance(body, dict):
            raise KisAuthError(
                _unavailable("token response was not a JSON object"),
                reason_code="AUTH_RESPONSE_INVALID",
            )

        access_token = body.get("access_token")
        if not isinstance(access_token, str) or not access_token.strip():
            raise KisAuthError(
                _unavailable("token response missing access_token"),
                reason_code="AUTH_RESPONSE_INVALID",
            )

        try:
            expires_at = _parse_expiry(
                body,
                now=self._clock(),
                wall_now=self._wall_clock(),
            )
        except (ValueError, TypeError, OverflowError):
            raise KisAuthError(
                _unavailable("token response has missing or invalid expiry"),
                reason_code="AUTH_RESPONSE_INVALID",
            ) from None

        return KisToken(access_token=access_token, expires_at=expires_at)

    def _respect_min_interval(self) -> None:
        if self._request_limiter is not None:
            self._request_limiter.acquire()
            return
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
