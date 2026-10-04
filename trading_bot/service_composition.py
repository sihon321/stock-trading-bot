"""Lazy mock-only service seams. Final POST guard/worker wiring belongs to 15-08/09.

Importing this module constructs no settings, clients, broker, provider or store.
Offline composition is labeled explicitly and cannot supply production acceptance.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol, Sequence, TYPE_CHECKING

from .service_activation import (
    ActivationVerdict, OfflineActivationAuthority, ReadOnlyAcceptanceEvidenceReader,
    SavedEvidenceReader, SafetyReader, _protected_json, load_acceptance_receipt,
    validate_unattended_activation,
)
from .service_config import ServiceSettings
from .service_models import AcceptanceReceipt, ServiceMode, ServiceScope

if TYPE_CHECKING:
    from .kis_broker import KISBroker, OrderEvidenceSink
    from .kis_order import KisOrderAdapter
    from .market_cycle import MarketCyclePolicy, MarketCycleEvidence
    from .portfolio import PortfolioSnapshot
    from .kis_quote import KisQuoteResult


class ServiceCompositionBlocked(RuntimeError):
    """Bounded category only; credential/vendor exception text is never exposed."""


@dataclass(frozen=True)
class PortfolioReadRequest:
    trading_date: date
    previous_trading_date: date
    local_unresolved: Sequence[Mapping[str, Any]] = field(default=(), repr=False)


class PortfolioReader(Protocol):
    def __call__(self, request: PortfolioReadRequest) -> PortfolioSnapshot: ...


class QuoteReader(Protocol):
    def __call__(self, ticker: str) -> KisQuoteResult: ...


@dataclass(frozen=True)
class BrokerGuardContext:
    scope: ServiceScope
    validate_activation: Callable[[], ActivationVerdict]
    read_freezes: Callable[[], tuple[str, ...]]
    policy: MarketCyclePolicy
    session_provider: Any
    clock: Callable[[], datetime]
    post_timeout_seconds: int = 10


class OrderAdapterGuardBuilder(Protocol):
    """15-08 must wrap the actual POST entry, not merely a future job launch."""
    def __call__(self, adapter: KisOrderAdapter, context: BrokerGuardContext) -> Any: ...


@dataclass(frozen=True)
class BrokerGuardBindings:
    order_adapter_guard: OrderAdapterGuardBuilder | None
    evidence_sink: OrderEvidenceSink | None
    data_fresh: Callable[[], bool]
    submission_authority: Any = None


@dataclass(frozen=True)
class OfflineServiceCollaborators:
    authority: OfflineActivationAuthority
    prep_read_only: Callable[[], Any]
    read_portfolio: Callable[[PortfolioReadRequest], Any]
    read_quote: Callable[[str], Any]
    reconcile_orders: Callable[[PortfolioReadRequest], Any]
    read_freezes: Callable[[], tuple[str, ...]]


@dataclass(frozen=True)
class OfflineMockClients:
    """Injected harness only; real adapters with fake transports are not KIS proof."""
    authority: OfflineActivationAuthority
    auth_client: Any = field(repr=False)
    order_client: Any = field(repr=False)
    quote_client: Any = field(repr=False)
    provider_transport: Any = field(default=None, repr=False)
    popen: Any = field(default=None, repr=False)


@dataclass(frozen=True)
class ServiceComposition:
    mode: ServiceMode
    activation: ActivationVerdict
    authentication: str
    execution_target: str = 'mock'
    runtime_wired: bool = False
    scope: ServiceScope | None = None
    prep_read_only: Callable[[], Any] | None = field(default=None, repr=False)
    read_portfolio: PortfolioReader | None = field(default=None, repr=False)
    read_quote: QuoteReader | None = field(default=None, repr=False)
    reconcile_orders: PortfolioReader | None = field(default=None, repr=False)
    read_freezes: Callable[[], tuple[str, ...]] | None = field(default=None, repr=False)
    provider_factory: Callable[[], Any] | None = field(default=None, repr=False)
    guarded_broker_builder: Callable[[BrokerGuardBindings], KISBroker] | None = field(default=None, repr=False)
    close: Callable[[], None] | None = field(default=None, repr=False)
    # Only a temporary explicit harness can inspect its fake adapter. Live
    # compositions never publish an unguarded order adapter/account/client.
    _test_order_adapter: Any = field(default=None, repr=False)


def load_mock_trading_settings(path: Path):
    """An explicit protected JSON path, init-only sources, no real credential graph."""
    from pydantic import SecretStr, model_validator
    from pydantic_settings import SettingsConfigDict
    from .config import LLMProviderName
    from .soak_config import SoakSettings

    class MockServiceTradingSettings(SoakSettings):
        model_config = SettingsConfigDict(env_file=None, extra='forbid', frozen=True,
            hide_input_in_errors=True, validate_default=True)
        llm_provider: LLMProviderName = LLMProviderName.CODEX_CLI
        anthropic_api_key: SecretStr | None = None
        anthropic_auth_token: SecretStr | None = None
        openai_api_key: SecretStr | None = None
        anthropic_model: str = 'claude-opus-4-8'
        anthropic_temperature: float = 0
        openai_model: str = 'gpt-4.1'
        openai_temperature: float = 0
        codex_cli_binary: str = 'codex'
        codex_cli_model: str | None = None
        codex_cli_temperature: float = 0
        codex_cli_timeout_seconds: float = 90
        codex_cli_extra_args: tuple[str, ...] = ()
        llm_max_retries: int = 1
        llm_retry_backoff_seconds: float = 0

        @classmethod
        def settings_customise_sources(cls, settings_cls, init_settings, env_settings,
                dotenv_settings, file_secret_settings):
            return (init_settings,)

        @model_validator(mode='after')
        def fixed_service_bounds(self):
            if (self.target_eligible_days != 20 or self.availability_failure_budget != 2
                    or not 1 <= self.kis_max_retries <= 3
                    or not 0 < self.kis_timeout_seconds <= 10
                    or not 0 < self.kis_query_timeout_seconds <= 15
                    or not 0 <= self.kis_retry_backoff_seconds <= 1
                    or self.codex_cli_timeout_seconds != 90
                    or self.llm_max_retries != 1 or self.llm_retry_backoff_seconds != 0):
                raise ValueError('fixed bounded mock service controls required')
            return self

        @property
        def active_llm_api_key(self):
            value = self.openai_api_key if self.llm_provider is LLMProviderName.OPENAI else self.anthropic_api_key
            if value is None or not value.get_secret_value().strip():
                raise ServiceCompositionBlocked('PROVIDER_CREDENTIAL_MISSING')
            return value

    return MockServiceTradingSettings(**_protected_json(path, 65536))


def _blocked(settings, reason: str, receipt=None) -> ServiceComposition:
    return ServiceComposition(mode=settings.mode, activation=ActivationVerdict(allowed=False,
        reason_codes=(reason,), receipt_id=getattr(receipt, 'receipt_id', None)), authentication='NONE')


def build_service_composition(settings: ServiceSettings, *, receipt: AcceptanceReceipt | None = None,
        saved_evidence_reader: SavedEvidenceReader | None = None, current_safety: SafetyReader | None = None,
        clock: Callable[[], datetime] | None = None, policy: MarketCyclePolicy | None = None,
        offline: OfflineServiceCollaborators | None = None,
        offline_mock_clients: OfflineMockClients | None = None) -> ServiceComposition:
    """Acquire capability only after mode, both approvals, sources and current safety.

    No soak runner, day accounting, proof-order or in-memory MockBroker is used.
    `reconcile_orders` collects fresh normalized whole-account broker truth; its
    later owner persists comparisons/terminal transitions under 15-09 authority.
    The broker seam requires a final operational adapter guard from 15-08.
    """
    clock = clock or (lambda: datetime.now(timezone.utc))
    if settings.execution_target != 'mock' or any(s.execution_target!='mock' for s in settings.registered_scopes):
        return _blocked(settings, 'REAL_TARGET_FORBIDDEN', receipt)
    if not settings.service_enabled or settings.mode is ServiceMode.DISABLED:
        return _blocked(settings, 'SERVICE_DISABLED', receipt)
    if settings.mode is ServiceMode.DRY_RUN:
        try:
            if type(offline) is not OfflineServiceCollaborators:
                return _blocked(settings, 'OFFLINE_COLLABORATORS_REQUIRED')
            offline.authority.assert_settings(settings)
            callbacks = (offline.prep_read_only, offline.read_portfolio, offline.read_quote,
                         offline.reconcile_orders, offline.read_freezes)
            if not all(callable(c) for c in callbacks):
                return _blocked(settings, 'OFFLINE_COLLABORATORS_REQUIRED')
        except Exception:
            return _blocked(settings, 'OFFLINE_TOPOLOGY_REQUIRED')
        return ServiceComposition(mode=settings.mode, activation=ActivationVerdict(allowed=True,
            reason_codes=('OFFLINE_ONLY',), authority='OFFLINE_ONLY'), authentication='OFFLINE_ONLY',
            prep_read_only=offline.prep_read_only, read_portfolio=offline.read_portfolio,
            read_quote=offline.read_quote, reconcile_orders=offline.reconcile_orders,
            read_freezes=offline.read_freezes)
    if settings.mode is not ServiceMode.KIS_MOCK:
        return _blocked(settings, 'SERVICE_MODE_UNKNOWN', receipt)
    if receipt is None:
        try:
            receipt = load_acceptance_receipt(settings.acceptance_receipt_path)
        except Exception:
            return _blocked(settings, 'ACCEPTANCE_RECEIPT_UNKNOWN')
    authority = offline_mock_clients.authority if type(offline_mock_clients) is OfflineMockClients else None
    if offline_mock_clients is not None and authority is None:
        return _blocked(settings, 'OFFLINE_CLIENTS_REQUIRED', receipt)
    activation = validate_unattended_activation(settings, receipt, saved_evidence_reader,
        current_safety, now=clock(), offline_authority=authority)
    if not activation.allowed:
        return ServiceComposition(mode=settings.mode, activation=activation, authentication='NONE')
    if activation.authority=='OFFLINE_ONLY' and authority is None:
        return _blocked(settings, 'AUTHENTIC_ACCEPTANCE_REQUIRED', receipt)
    if policy is None or getattr(policy, 'session_evidence_provider', None) is None:
        return _blocked(settings, 'SESSION_POLICY_REQUIRED', receipt)
    try:
        trading = load_mock_trading_settings(settings.trading_config_path)
        from .kis_order import MOCK_TR_PROFILE_CANDIDATES
        from .soak_config import build_soak_identity_receipt
        from .portfolio import canonical_account_scope_hash
        evidence = saved_evidence_reader.read(receipt)
        profiles = [p for p in MOCK_TR_PROFILE_CANDIDATES if p.version==evidence.profile_version]
        if len(profiles)!=1:
            return _blocked(settings, 'MOCK_PROFILE_UNKNOWN', receipt)
        profile = profiles[0]
        identity = build_soak_identity_receipt(trading,receipt.campaign_id,profile)
        if (trading.kis_mock.domain.rstrip('/')!='https://openapivts.koreainvestment.com:29443'
                or identity.target!='mock' or any(not t.startswith('V') for t in profile.tr_ids)
                or canonical_account_scope_hash('mock',identity.account_suffix)!=receipt.scope.account_scope_hash
                or tuple(Path(p).resolve() for p in (trading.primary_audit_db_path,
                    trading.soak_db_path,trading.controller_db_path)) !=
                    tuple(Path(p).resolve() for p in settings.trading_journal_paths)):
            return _blocked(settings, 'MOCK_IDENTITY_MISMATCH', receipt)
    except Exception:
        return _blocked(settings, 'MOCK_CONFIGURATION_UNKNOWN', receipt)

    def validate_current():
        verdict = validate_unattended_activation(settings, receipt, saved_evidence_reader,
            current_safety, now=clock(), offline_authority=authority)
        if not verdict.allowed:
            raise ServiceCompositionBlocked(verdict.reason_codes[0])
        return verdict

    # Reread after credential/profile processing, before any client constructor.
    try:
        validate_current()
    except ServiceCompositionBlocked as exc:
        return _blocked(settings,str(exc),receipt)
    from .kis_auth import KisAuthConfig, KisTokenManager
    from .kis_order import KisOrderAdapter, KisOrderAccount, KisOrderTrIds
    from .kis_quote import KisQuoteAdapter
    from .kis_rate_limit import KisRequestLimiter
    from .portfolio import collect_portfolio_snapshot
    from .kis_broker import KISBroker
    from .llm_provider import build_single_shot_llm_provider
    limiter = KisRequestLimiter(trading.kis_min_interval_seconds)
    credential = trading.kis_mock
    clients = offline_mock_clients
    manager = KisTokenManager(KisAuthConfig(domain=credential.domain,
        app_key=credential.app_key.get_secret_value(), app_secret=credential.app_secret.get_secret_value(),
        refresh_margin_seconds=trading.kis_token_refresh_margin_seconds,
        min_interval_seconds=trading.kis_min_interval_seconds, max_retries=trading.kis_max_retries,
        retry_backoff_seconds=trading.kis_retry_backoff_seconds, timeout_seconds=trading.kis_timeout_seconds,
        cache_path=trading.kis_token_cache_path), client=clients.auth_client if clients else None,
        request_limiter=limiter)
    adapter = KisOrderAdapter(token_manager=manager,domain=credential.domain,tr_id_profile='mock',
        client=clients.order_client if clients else None,min_interval_seconds=trading.kis_min_interval_seconds,
        max_retries=trading.kis_max_retries,retry_backoff_seconds=trading.kis_retry_backoff_seconds,
        timeout_seconds=10,query_timeout_seconds=trading.kis_query_timeout_seconds,request_limiter=limiter)
    # The legacy mode-derived POST IDs differ from the explicitly authenticated
    # profile. Bind its exact accepted V family to the shipped adapter logic.
    adapter._tr_ids = KisOrderTrIds(profile.buy_tr_id,profile.sell_tr_id,
                                    profile.daily_ccld_tr_id,profile.balance_tr_id)
    account = KisOrderAccount(cano=trading.kis_mock_account_cano.get_secret_value(),
                              account_product_code=trading.kis_mock_account_product_code)
    quote = KisQuoteAdapter(token_manager=manager,domain=credential.domain,tr_id='FHKST01010100',
        client=clients.quote_client if clients else None,min_interval_seconds=trading.kis_min_interval_seconds,
        max_retries=trading.kis_max_retries,retry_backoff_seconds=trading.kis_retry_backoff_seconds,
        timeout_seconds=trading.kis_timeout_seconds,request_limiter=limiter,clock=clock)

    def read_freezes():
        # A new unrelated campaign freeze must affect the next pass as well.
        return tuple(saved_evidence_reader.read_freezes())

    def prep_read_only():
        validate_current()
        return policy.classify(clock())

    def read_portfolio(request: PortfolioReadRequest):
        validate_current()
        current = clock()
        from .service_models import KST
        cutoff = policy.completed_bar_cutoff(current.astimezone(KST).date())
        if (request.trading_date!=current.astimezone(KST).date()
                or not cutoff.available or request.previous_trading_date!=cutoff.cutoff_date):
            raise ServiceCompositionBlocked('PORTFOLIO_DATE_UNKNOWN')
        return collect_portfolio_snapshot(adapter=adapter,account=account,profile=profile,
            trading_date=request.trading_date,previous_trading_date=request.previous_trading_date,
            account_scope_hash=receipt.scope.account_scope_hash,
            local_unresolved=request.local_unresolved,observed_at=current)

    def read_quote(ticker: str):
        validate_current()
        if ticker in read_freezes():
            raise ServiceCompositionBlocked('UNRESOLVED_FREEZE')
        return quote.fetch_current_price(ticker)

    def provider_factory():
        validate_current()
        provider = build_single_shot_llm_provider(trading,
            transport=clients.provider_transport if clients else None,popen=clients.popen if clients else None)
        if (getattr(provider,'_single_shot',None) is not True
                and getattr(provider,'_single_shot_transport',None) is None):
            raise ServiceCompositionBlocked('PROVIDER_SINGLE_SHOT_UNVERIFIED')
        return provider

    def guarded_broker_builder(bindings: BrokerGuardBindings):
        validate_current()
        if bindings is None or not callable(bindings.order_adapter_guard):
            raise ServiceCompositionBlocked('FINAL_ORDER_GUARD_REQUIRED')
        if not callable(bindings.evidence_sink) or not callable(bindings.data_fresh):
            raise ServiceCompositionBlocked('AUDIT_SINK_REQUIRED')
        from .submission_authority import SubmissionAuthority, OwnedActivationCheck
        final_authority=bindings.submission_authority
        if final_authority is not None:
            if type(final_authority) is not SubmissionAuthority or final_authority.store.settings!=settings:
                raise ServiceCompositionBlocked('FINAL_ORDER_GUARD_REQUIRED')
            if clients is None:
                final_authority=SubmissionAuthority(final_authority.store,policy=policy,clock=clock,
                    unattended=True,activation_check=OwnedActivationCheck(settings,saved_evidence_reader,current_safety,clock))
        elif clients is None:
            raise ServiceCompositionBlocked('FINAL_ORDER_GUARD_REQUIRED')
        context = BrokerGuardContext(scope=receipt.scope,validate_activation=validate_current,
            read_freezes=read_freezes,policy=policy,session_provider=policy.session_evidence_provider,clock=clock)
        guarded = bindings.order_adapter_guard(adapter,context)
        if guarded is adapter or guarded is None:
            raise ServiceCompositionBlocked('FINAL_ORDER_GUARD_REQUIRED')
        # Arbitrary adapter wrappers cannot acquire permission. With a concrete
        # authority use the actual bounded adapter at the broker boundary.
        return KISBroker(order_adapter=adapter if final_authority is not None else guarded,account=account,
            market_clock=lambda:bool(policy.classify(clock()).executable),data_fresh=bindings.data_fresh,
            evidence_sink=bindings.evidence_sink,pre_submit_quote_reader=read_quote,clock=clock,
            submission_authority=final_authority)

    def close():
        # No capability is invoked; only already constructed HTTP resources close.
        for client in (manager._client,adapter._client,quote._client):
            closer=getattr(client,'close',None)
            if callable(closer):closer()

    return ServiceComposition(mode=settings.mode,activation=activation,
        authentication='OFFLINE_FIXTURE' if clients else 'AUTHENTICATED_KIS_MOCK',scope=receipt.scope,
        prep_read_only=prep_read_only,read_portfolio=read_portfolio,read_quote=read_quote,
        reconcile_orders=read_portfolio,read_freezes=read_freezes,provider_factory=provider_factory,
        guarded_broker_builder=guarded_broker_builder,close=close,
        _test_order_adapter=adapter if clients else None)
