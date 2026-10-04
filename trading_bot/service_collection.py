"""Spawn-safe daily collection with no account, journal, leader or LLM authority.

Only public prompt identity, bounded collection policy and mock quote credentials
cross this boundary. Credentials for a quote never include an account number,
order adapter, accepted profile, receipt, provider secret or production path.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Callable

from pydantic import Field, SecretStr

from .service_activation import OfflineActivationAuthority
from .service_models import DailyDispatchEnvelope, ServiceContract

RESULT_LIMIT = 8 * 1024 * 1024


class QuoteSettings(ServiceContract):
    domain: str
    app_key: SecretStr = Field(repr=False)
    app_secret: SecretStr = Field(repr=False)
    refresh_margin_seconds: int = Field(gt=0)
    min_interval_seconds: float = Field(gt=0)
    max_retries: int = Field(ge=1,le=3)
    retry_backoff_seconds: float = Field(ge=0,le=1)
    timeout_seconds: float = Field(gt=0,le=10)

    def build(self):
        from .kis_auth import KisAuthConfig,KisTokenManager
        from .kis_quote import KisQuoteAdapter
        from .kis_rate_limit import KisRequestLimiter
        from .soak_config import MOCK_DOMAIN,MOCK_PORT
        from urllib.parse import urlsplit
        url=urlsplit(self.domain)
        if (url.scheme!='https' or url.hostname!=MOCK_DOMAIN or url.port!=MOCK_PORT
                or url.username or url.password or url.query or url.fragment):
            raise ValueError('read-only mock quote domain required')
        limiter=KisRequestLimiter(self.min_interval_seconds)
        # In-memory token only; never inherit or update the parent's token cache.
        manager=KisTokenManager(KisAuthConfig(domain=self.domain,
            app_key=self.app_key.get_secret_value(),app_secret=self.app_secret.get_secret_value(),
            refresh_margin_seconds=self.refresh_margin_seconds,min_interval_seconds=self.min_interval_seconds,
            max_retries=self.max_retries,retry_backoff_seconds=self.retry_backoff_seconds,
            timeout_seconds=self.timeout_seconds,cache_path=None),request_limiter=limiter)
        return KisQuoteAdapter(token_manager=manager,domain=self.domain,tr_id='FHKST01010100',
            min_interval_seconds=self.min_interval_seconds,max_retries=self.max_retries,
            retry_backoff_seconds=self.retry_backoff_seconds,timeout_seconds=self.timeout_seconds,
            request_limiter=limiter)


class PromptIdentity(ServiceContract):
    system_prompt: str
    schema_hash: str
    provider: str
    model: str
    temperature: float
    prompt_version: str


@dataclass(frozen=True)
class ProductionInputSource:
    policy: tuple[tuple[str,object], ...]
    quote: QuoteSettings
    prompt: PromptIdentity
    offline_factory: Callable | None = field(default=None,repr=False)
    offline_authority: OfflineActivationAuthority | None = None

    def __post_init__(self):
        if type(self.quote) is not QuoteSettings or type(self.prompt) is not PromptIdentity:
            raise TypeError('quote-only settings and public prompt identity required')
        allowed={'ohlcv_adjusted','pykrx_request_timeout_seconds','screener_max_candidates',
            'screener_markets','screener_min_trading_value','screener_min_volume_ratio',
            'screener_excluded_states','naver_news_enabled','naver_news_max_items','naver_news_max_chars'}
        if {key for key,value in self.policy}!=allowed or len(self.policy)!=len(allowed):
            raise ValueError('collection-only policy required')
        if self.offline_factory is not None and type(self.offline_authority) is not OfflineActivationAuthority:
            raise ValueError('injected collection requires explicit temporary authority')

    def collect(self, snapshot, cutoff: date):
        """Runs only in the child; every held fact uses this exact frozen snapshot."""
        policy=SimpleNamespace(**dict(self.policy))
        if self.offline_factory is not None:
            source=self.offline_factory(policy,cutoff)
        else:
            from .data_source import build_data_source
            source=build_data_source(policy,expected_date=cutoff.strftime('%Y%m%d'),quote_adapter=self.quote.build())
        from .portfolio import held_first_targets,build_held_position_context
        from .domain import Ticker
        from .data_models import TickerRole
        from .prompts import render_prompt
        screened=source.screen_daily_candidates(cutoff.strftime('%Y%m%d'))
        held=tuple(h.ticker for h in snapshot.holdings)
        targets=held_first_targets(held,(c.ticker for c in screened.candidates))
        if len(targets)>4096:raise ValueError('bounded universe required')
        result=[]; size=0
        for target in targets:
            data=source.build_context_result(Ticker(target.ticker),ticker_role=TickerRole.HOLDING
                if 'HELD' in target.provenance else TickerRole.CANDIDATE)
            if data.context is None:raise ValueError('daily input incomplete')
            position=build_held_position_context(snapshot,target.ticker,current_price=data.context.current_price.amount) if target.ticker in held else None
            prompt=render_prompt(data.context,held_position=position).encode()
            envelope=DailyDispatchEnvelope(prompt_bytes=prompt,prompt_hash=hashlib.sha256(prompt).hexdigest(),
                **self.prompt.model_dump())
            encoded=envelope.model_dump_json()
            size+=len(encoded.encode())
            if size>RESULT_LIMIT:raise ValueError('bounded result required')
            result.append((target.ticker,tuple(str(p) for p in target.provenance),encoded))
        return result


def collection_child(source, snapshot, cutoff, directory):
    """Atomic result bytes only; spawn cannot inherit parent account/leader FDs.

    There are no callbacks into the parent. Terminated work can only leave
    disposable bytes under this unique child output directory.
    """
    try:
        inputs=source.collect(snapshot,cutoff)
        payload=json.dumps({'snapshot_id':snapshot.snapshot_id,'inputs':inputs},ensure_ascii=False).encode()
        if len(payload)>RESULT_LIMIT:raise ValueError('bounded result required')
    except BaseException:
        payload=b'{"error":"INPUT_COLLECTION_UNKNOWN"}'
    temporary=Path(directory)/'pending.json'
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'wb') as output:
        output.write(payload);output.flush();os.fsync(output.fileno())
    os.replace(temporary,Path(directory)/'result.json')
