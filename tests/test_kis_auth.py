"""Offline tests for the shared KIS token manager (DATA-03, D-02/D-14/D-15).

Every test injects a fake HTTP client and a monotonic clock; no test touches the
live KIS network. The manager must cache a token until the refresh margin, issue
exactly one refresh across repeated pre-expiry calls, bound retries, normalize
all failure modes into an UNAVAILABLE :class:`SourceHealth`, and never leak the
app key/secret or the access token into reprs, health reasons, or exceptions.
"""

import dataclasses
import json
import stat
from pathlib import Path

import httpx
import pytest

from trading_bot.config import Settings, TradingMode
from trading_bot.data_models import SourceHealth, SourceStatus
from trading_bot.kis_auth import (
    KisAuthConfig,
    KisAuthError,
    KisToken,
    KisTokenManager,
    build_kis_auth_config,
)

# Secret markers asserted to never surface in diagnostics (threat T-03-04-I).
APP_KEY = "mock-app-key-secret"
APP_SECRET = "mock-app-secret-secret"
ACCESS_TOKEN = "kis-access-token-secret-value"
DOMAIN = "https://mock.kis.example.test"

SECRET_VALUES = (APP_KEY, APP_SECRET, ACCESS_TOKEN)


def assert_no_secret_leaked(*texts: str) -> None:
    combined = "\n".join(texts)
    for secret in SECRET_VALUES:
        assert secret not in combined


class _FakeClock:
    """Deterministic monotonic clock advanced explicitly by the test."""

    def __init__(self, start: float = 1_000_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class _FakeClient:
    """Records POSTs and returns queued responses or raises queued errors."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []
        self.closed = False

    def post(self, url, *, json=None, headers=None, timeout=None):
        self.calls.append(
            {"url": url, "json": json, "headers": headers, "timeout": timeout}
        )
        if not self._responses:
            raise AssertionError("no more fake responses queued")
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def close(self):
        self.closed = True


def _response(
    status_code: int = 200,
    *,
    access_token: str = ACCESS_TOKEN,
    expires_in: int = 86400,
    expired_at: str = "2099-01-01 00:00:00",
    body=None,
) -> httpx.Response:
    if body is None:
        body = {
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": expires_in,
            "access_token_token_expired": expired_at,
        }
    return httpx.Response(
        status_code=status_code,
        json=body,
        request=httpx.Request("POST", DOMAIN + "/oauth2/tokenP"),
    )


def _config(**overrides) -> KisAuthConfig:
    base = {
        "domain": DOMAIN,
        "app_key": APP_KEY,
        "app_secret": APP_SECRET,
        "refresh_margin_seconds": 600,
        "min_interval_seconds": 0.0,
        "max_retries": 3,
        "retry_backoff_seconds": 0.0,
        "timeout_seconds": 5.0,
    }
    base.update(overrides)
    return KisAuthConfig(**base)


def _manager(responses, *, clock=None, config=None) -> KisTokenManager:
    return KisTokenManager(
        config or _config(),
        client=_FakeClient(responses),
        clock=clock or _FakeClock(),
    )


# --- Typed model shape ------------------------------------------------------


def test_kis_models_are_frozen_dataclasses() -> None:
    token = KisToken(access_token=ACCESS_TOKEN, expires_at=1.0)
    config = _config()

    assert dataclasses.is_dataclass(token)
    assert dataclasses.is_dataclass(config)
    with pytest.raises(dataclasses.FrozenInstanceError):
        token.access_token = "mutated"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        config.app_key = "mutated"  # type: ignore[misc]


def test_build_kis_auth_config_uses_active_kis_only(monkeypatch) -> None:
    for key in (
        "TRADING_MODE",
        "CONFIRM_REAL_TRADING",
        "LLM_PROVIDER",
        "ANTHROPIC_API_KEY",
        "KIS_MOCK__DOMAIN",
        "KIS_MOCK__APP_KEY",
        "KIS_MOCK__APP_SECRET",
        "KIS_MOCK__TR_ID_PROFILE",
        "KIS_MOCK__LABEL",
        "KIS_REAL__DOMAIN",
        "KIS_REAL__APP_KEY",
        "KIS_REAL__APP_SECRET",
        "KIS_REAL__TR_ID_PROFILE",
        "KIS_REAL__LABEL",
        "KIS_TOKEN_CACHE_PATH",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("TRADING_MODE", "mock")
    monkeypatch.setenv("CONFIRM_REAL_TRADING", "no")
    monkeypatch.setenv("LLM_PROVIDER", "claude")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-api-key-secret")
    monkeypatch.setenv("KIS_MOCK__DOMAIN", DOMAIN)
    monkeypatch.setenv("KIS_MOCK__APP_KEY", APP_KEY)
    monkeypatch.setenv("KIS_MOCK__APP_SECRET", APP_SECRET)
    monkeypatch.setenv("KIS_MOCK__TR_ID_PROFILE", "mock")
    monkeypatch.setenv("KIS_MOCK__LABEL", "KIS mock account")
    monkeypatch.setenv("KIS_REAL__DOMAIN", "https://real.example.test")
    monkeypatch.setenv("KIS_REAL__APP_KEY", "real-app-key-secret")
    monkeypatch.setenv("KIS_REAL__APP_SECRET", "real-app-secret-secret")
    monkeypatch.setenv("KIS_REAL__TR_ID_PROFILE", "real")
    monkeypatch.setenv("KIS_REAL__LABEL", "KIS real account")

    settings = Settings()
    assert settings.trading_mode is TradingMode.MOCK

    config = build_kis_auth_config(settings)

    # Uses the mock (active) credential group and Phase 3 settings, not real.
    assert config.domain == DOMAIN
    assert config.app_key == APP_KEY
    assert config.app_secret == APP_SECRET
    assert config.refresh_margin_seconds == settings.kis_token_refresh_margin_seconds
    assert config.min_interval_seconds == settings.kis_min_interval_seconds
    assert config.max_retries == settings.kis_max_retries
    assert config.retry_backoff_seconds == settings.kis_retry_backoff_seconds
    assert config.cache_path == settings.kis_token_cache_path
    assert "real-app-key-secret" not in (config.app_key, config.app_secret)


# --- Caching and refresh margin ---------------------------------------------


def test_first_request_issues_and_caches_token() -> None:
    client = _FakeClient([_response()])
    manager = KisTokenManager(_config(), client=client, clock=_FakeClock())

    token = manager.get_token()

    assert token == ACCESS_TOKEN
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["url"].endswith("/oauth2/tokenP")
    assert call["json"]["grant_type"] == "client_credentials"
    assert call["json"]["appkey"] == APP_KEY
    assert call["json"]["appsecret"] == APP_SECRET


def test_repeated_calls_before_margin_reuse_one_token() -> None:
    client = _FakeClient([_response(expires_in=86400)])
    clock = _FakeClock()
    manager = KisTokenManager(_config(), client=client, clock=clock)

    first = manager.get_token()
    clock.advance(3600)  # 1h later, still far from expiry - margin.
    second = manager.get_token()
    clock.advance(3600)
    third = manager.get_token()

    assert first == second == third == ACCESS_TOKEN
    assert len(client.calls) == 1  # exactly one issuance.


def test_refresh_happens_inside_the_margin_window() -> None:
    client = _FakeClient(
        [
            _response(access_token=ACCESS_TOKEN, expires_in=86400),
            _response(access_token="second-token-secret-value", expires_in=86400),
        ]
    )
    clock = _FakeClock()
    manager = KisTokenManager(
        _config(refresh_margin_seconds=600), client=client, clock=clock
    )

    manager.get_token()
    # Advance to inside the refresh margin (>= expiry - 600s).
    clock.advance(86400 - 300)
    refreshed = manager.get_token()

    assert refreshed == "second-token-secret-value"
    assert len(client.calls) == 2


def test_explicit_refresh_forces_new_token() -> None:
    client = _FakeClient(
        [
            _response(access_token=ACCESS_TOKEN),
            _response(access_token="forced-token-secret-value"),
        ]
    )
    manager = KisTokenManager(_config(), client=client, clock=_FakeClock())

    manager.get_token()
    forced = manager.refresh_token()

    assert forced == "forced-token-secret-value"
    assert len(client.calls) == 2


def _persistent_manager(
    cache_path: Path,
    responses,
    *,
    app_key: str = APP_KEY,
    app_secret: str = APP_SECRET,
    monotonic_clock: _FakeClock | None = None,
    wall_clock: _FakeClock | None = None,
) -> tuple[KisTokenManager, _FakeClient]:
    client = _FakeClient(responses)
    manager = KisTokenManager(
        _config(
            app_key=app_key,
            app_secret=app_secret,
            cache_path=cache_path,
        ),
        client=client,
        clock=monotonic_clock or _FakeClock(),
        wall_clock=wall_clock or _FakeClock(start=1_700_000_000.0),
    )
    return manager, client


def test_separate_managers_reuse_valid_secure_cache_without_second_post(tmp_path) -> None:
    cache_path = tmp_path / "private-kis-cache" / "tokens.json"
    wall_clock = _FakeClock(start=1_700_000_000.0)
    first, first_client = _persistent_manager(
        cache_path, [_response(expires_in=86_400)], wall_clock=wall_clock
    )
    second, second_client = _persistent_manager(
        cache_path, [], monotonic_clock=_FakeClock(start=10.0), wall_clock=wall_clock
    )

    assert first.get_token() == ACCESS_TOKEN
    assert second.get_token() == ACCESS_TOKEN
    assert len(first_client.calls) == 1
    assert second_client.calls == []
    assert stat.S_IMODE(cache_path.stat().st_mode) == 0o600
    assert stat.S_IMODE(cache_path.parent.stat().st_mode) == 0o700


def test_persistent_cache_refreshes_inside_margin(tmp_path) -> None:
    cache_path = tmp_path / "private-kis-cache" / "tokens.json"
    wall_clock = _FakeClock(start=1_700_000_000.0)
    first, _ = _persistent_manager(
        cache_path, [_response(expires_in=900)], wall_clock=wall_clock
    )
    first.get_token()
    wall_clock.advance(301)
    second, second_client = _persistent_manager(
        cache_path,
        [_response(access_token="second-token-secret-value", expires_in=900)],
        wall_clock=wall_clock,
    )

    assert second.get_token() == "second-token-secret-value"
    assert len(second_client.calls) == 1


def test_persistent_cache_isolated_by_credential_identity(tmp_path) -> None:
    cache_path = tmp_path / "private-kis-cache" / "tokens.json"
    first, _ = _persistent_manager(cache_path, [_response()])
    first.get_token()
    second, second_client = _persistent_manager(
        cache_path,
        [_response(access_token="rotated-credential-token", expires_in=86_400)],
        app_secret="rotated-app-secret",
    )

    assert second.get_token() == "rotated-credential-token"
    assert len(second_client.calls) == 1


def test_tampered_signed_cache_is_not_reused(tmp_path) -> None:
    cache_path = tmp_path / "private-kis-cache" / "tokens.json"
    first, _ = _persistent_manager(cache_path, [_response()])
    first.get_token()
    document = json.loads(cache_path.read_text(encoding="utf-8"))
    entry = next(iter(document["entries"].values()))
    entry["access_token"] = "attacker-controlled-token"
    cache_path.write_text(json.dumps(document), encoding="utf-8")
    second, second_client = _persistent_manager(
        cache_path,
        [_response(access_token="fresh-after-tamper", expires_in=86_400)],
    )

    assert second.get_token() == "fresh-after-tamper"
    assert len(second_client.calls) == 1


@pytest.mark.parametrize("unsafe_mode", [False, True])
def test_corrupt_or_permission_unsafe_cache_is_not_reused(
    tmp_path, unsafe_mode: bool
) -> None:
    cache_path = tmp_path / "private-kis-cache" / "tokens.json"
    cache_path.parent.mkdir(mode=0o700)
    cache_path.write_text("not valid cache JSON", encoding="utf-8")
    cache_path.chmod(0o644 if unsafe_mode else 0o600)
    manager, client = _persistent_manager(cache_path, [_response()])

    assert manager.get_token() == ACCESS_TOKEN
    assert len(client.calls) == 1
    assert stat.S_IMODE(cache_path.stat().st_mode) == 0o600


# --- Bounded retry and failure normalization --------------------------------


def test_transient_errors_retry_then_succeed_within_bound() -> None:
    client = _FakeClient(
        [
            httpx.ConnectError("boom", request=httpx.Request("POST", DOMAIN)),
            _response(),
        ]
    )
    manager = KisTokenManager(
        _config(max_retries=3), client=client, clock=_FakeClock()
    )

    token = manager.get_token()

    assert token == ACCESS_TOKEN
    assert len(client.calls) == 2


def test_exhausted_retries_raise_kis_auth_error_with_health() -> None:
    err = httpx.ConnectError("down", request=httpx.Request("POST", DOMAIN))
    client = _FakeClient([err, err, err, err, err])
    manager = KisTokenManager(
        _config(max_retries=3), client=client, clock=_FakeClock()
    )

    with pytest.raises(KisAuthError) as excinfo:
        manager.get_token()

    # Bounded: at most max_retries attempts, not unbounded retry storm.
    assert len(client.calls) == 3
    health = excinfo.value.health
    assert isinstance(health, SourceHealth)
    assert health.source == "kis_auth"
    assert health.status is SourceStatus.UNAVAILABLE
    assert health.reason
    assert excinfo.value.reason_code == "AUTH_TRANSPORT_ERROR"


@pytest.mark.parametrize(
    ("response", "expected_reason_code"),
    [
        (_response(status_code=403), "AUTH_HTTP_AUTH_ERROR"),
        (_response(status_code=429), "AUTH_HTTP_RATE_LIMITED"),
        (_response(status_code=500), "AUTH_HTTP_ERROR"),
    ],
)
def test_http_error_status_normalizes_to_unavailable(
    response, expected_reason_code: str
) -> None:
    manager = _manager([response, response, response])

    with pytest.raises(KisAuthError) as excinfo:
        manager.get_token()

    assert excinfo.value.health.status is SourceStatus.UNAVAILABLE
    assert excinfo.value.reason_code == expected_reason_code


def test_token_timeout_preserves_bounded_reason_code() -> None:
    error = httpx.ReadTimeout("secret provider detail", request=httpx.Request("POST", DOMAIN))
    manager = _manager([error, error, error])

    with pytest.raises(KisAuthError) as excinfo:
        manager.get_token()

    assert excinfo.value.reason_code == "AUTH_TIMEOUT"
    assert "secret provider detail" not in str(excinfo.value)


@pytest.mark.parametrize(
    "body",
    [
        {"token_type": "Bearer"},  # missing access_token
        {"access_token": "", "access_token_token_expired": "2099-01-01 00:00:00"},
        {"access_token": ACCESS_TOKEN},  # missing expiry
        {"access_token": ACCESS_TOKEN, "expires_in": "not-a-number"},
    ],
)
def test_malformed_token_body_normalizes_to_unavailable(body) -> None:
    manager = _manager([_response(body=body)])

    with pytest.raises(KisAuthError) as excinfo:
        manager.get_token()

    assert excinfo.value.health.status is SourceStatus.UNAVAILABLE
    assert excinfo.value.reason_code == "AUTH_RESPONSE_INVALID"


def test_non_json_body_normalizes_to_unavailable() -> None:
    bad = httpx.Response(
        status_code=200,
        text="<html>not json</html>",
        request=httpx.Request("POST", DOMAIN + "/oauth2/tokenP"),
    )
    manager = _manager([bad])

    with pytest.raises(KisAuthError) as excinfo:
        manager.get_token()

    assert excinfo.value.health.status is SourceStatus.UNAVAILABLE
    assert excinfo.value.reason_code == "AUTH_RESPONSE_INVALID"


# --- Secret redaction (threat T-03-04-I) ------------------------------------


def test_no_secret_leaks_in_repr_or_health_or_exceptions(caplog) -> None:
    err = httpx.ConnectError("down", request=httpx.Request("POST", DOMAIN))
    client = _FakeClient([err, err, err])
    manager = KisTokenManager(
        _config(max_retries=3), client=client, clock=_FakeClock()
    )

    with pytest.raises(KisAuthError) as excinfo:
        manager.get_token()

    texts = [
        repr(manager),
        repr(manager._config),
        repr(excinfo.value),
        str(excinfo.value),
        repr(excinfo.value.health),
        excinfo.value.health.reason,
        caplog.text,
    ]
    assert_no_secret_leaked(*texts)


def test_no_access_token_leak_after_successful_issue() -> None:
    client = _FakeClient([_response()])
    manager = KisTokenManager(_config(), client=client, clock=_FakeClock())

    manager.get_token()

    # The cached token must not surface through the manager/config reprs.
    assert_no_secret_leaked(repr(manager), repr(manager._config))
