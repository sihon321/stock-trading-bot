"""Frozen shadow evaluation evidence. No provider or trading capabilities."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt, ValidationError, model_validator

from .backtest_models import Amount, BacktestPolicy, Nonnegative, Positive, Symbol

DOCUMENT_LIMIT = 16 * 1024 * 1024
TEXT_LIMIT = 64 * 1024
NEWS_LIMIT = 1024 * 1024
Hash = Annotated[str, Field(pattern=r'^[0-9a-f]{64}$')]
Text = Annotated[str, Field(max_length=TEXT_LIMIT)]
Name = Annotated[str, Field(min_length=1, max_length=200, pattern=r'^[A-Za-z0-9_.:/-]+$')]
Count = Annotated[StrictInt, Field(ge=0)]


class ShadowInputError(ValueError):
    """A bounded public reason code, never a source payload."""


def strict_json(text: str, limit: int = DOCUMENT_LIMIT):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ShadowInputError('DUPLICATE_JSON_KEY')
            result[key] = value
        return result
    if not isinstance(text, str) or len(text.encode('utf-8')) > limit:
        raise ShadowInputError('INPUT_TOO_LARGE')
    try:
        return json.loads(text, object_pairs_hook=pairs, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except ShadowInputError:
        raise
    except (ValueError, TypeError, RecursionError):
        raise ShadowInputError('INVALID_JSON') from None


def canonical_json(value) -> str:
    if isinstance(value, BaseModel):
        value = value.model_dump(mode='json')
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def shadow_content_hash(value) -> str:
    return hashlib.sha256(canonical_json(value).encode()).hexdigest()


def read_shadow_json(path: str | Path, limit: int = DOCUMENT_LIMIT):
    try:
        path = Path(path)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
            raise ShadowInputError('UNSAFE_OR_OVERSIZED_INPUT')
        with path.open('rb') as stream:
            raw = stream.read(limit + 1)
        if len(raw) > limit:
            raise ShadowInputError('INPUT_TOO_LARGE')
        return strict_json(raw.decode('utf-8'), limit)
    except ShadowInputError:
        raise
    except (OSError, UnicodeError, ValueError):
        raise ShadowInputError('INVALID_INPUT_FILE') from None


class Frozen(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, allow_inf_nan=False)

    @model_validator(mode='after')
    def validate_text_and_dates(self):
        for name in type(self).model_fields:
            value = getattr(self, name)
            if isinstance(value, datetime):
                if value.tzinfo is None or value.utcoffset() is None:
                    raise ValueError('aware timestamp required')
                object.__setattr__(self, name, value.astimezone(timezone.utc))
            if isinstance(value, str):
                bound = DOCUMENT_LIMIT if name.endswith('document_json') else TEXT_LIMIT
                if len(value.encode('utf-8')) > bound:
                    raise ValueError('bounded UTF-8 required')
                if name.endswith('_json'):
                    strict_json(value, bound)
        return self


class ShadowLimits(Frozen):
    sample_limit: Annotated[StrictInt, Field(ge=1, le=10000)] = 100
    max_attempts: Annotated[StrictInt, Field(ge=1, le=100000)] = 100
    max_total_tokens: Annotated[StrictInt, Field(ge=1, le=100000000)] = 200000
    max_cost_usd: Positive = Decimal('5')
    concurrency: Annotated[StrictInt, Field(ge=1, le=4)] = 1
    variant_limit: Annotated[StrictInt, Field(ge=1, le=16)] = 2
    repetitions: Annotated[StrictInt, Field(ge=1, le=100)] = 1


class ShadowPricing(Frozen):
    provider: Literal['openai', 'claude', 'codex_cli']
    model: Name
    endpoint: Literal['chat.completions', 'messages', 'codex.exec']
    currency: Annotated[str, Field(pattern=r'^[A-Z]{3}$')] = 'USD'
    tier: Literal['standard'] = 'standard'
    source: Annotated[str, Field(min_length=1, max_length=1000)]
    reviewed_at: datetime
    synthetic: StrictBool = False
    strict_schema_supported: StrictBool = False
    output_ceiling_supported: StrictBool = False
    usage_envelope_supported: StrictBool = False
    forced_tool_supported: StrictBool = False
    context_upper_bound: Annotated[StrictInt, Field(ge=1, le=10000000)]
    max_output_tokens: Annotated[StrictInt, Field(ge=1, le=1000000)] = 1024
    input_per_million: Nonnegative
    output_per_million: Nonnegative
    cache_read_per_million: Nonnegative | None = None
    cache_write_per_million: Nonnegative | None = None
    usd_per_native: Positive | None = None
    fx_source: str | None = None
    fx_reviewed_at: datetime | None = None
    settings_supported_json: Text = '{}'

    @model_validator(mode='after')
    def currency_source(self):
        if not self.source.startswith('https://'):
            raise ValueError('HTTPS source required')
        if self.currency != 'USD' and (self.usd_per_native is None or not self.fx_source or self.fx_reviewed_at is None):
            raise ValueError('reviewed FX required')
        if self.currency == 'USD' and self.usd_per_native not in (None, Decimal('1')):
            raise ValueError('USD FX must be one')
        expected = {'openai': 'chat.completions', 'claude': 'messages', 'codex_cli': 'codex.exec'}
        if self.endpoint != expected[self.provider]:
            raise ValueError('provider endpoint mismatch')
        return self


class ShadowVariant(Frozen):
    provider: Literal['openai', 'claude', 'codex_cli']
    model: Name
    system_prompt: Text
    prompt_version: Name
    signal_schema_json: Text
    settings_json: Text = '{}'
    max_output_tokens: Annotated[StrictInt, Field(ge=1, le=1000000)] = 1024
    variant_id: str = ''

    @model_validator(mode='after')
    def identity(self):
        schema = strict_json(self.signal_schema_json, TEXT_LIMIT)
        from .trade_signal import TradeSignal
        if canonical_json(schema)!=canonical_json(TradeSignal.model_json_schema()):raise ValueError('shipped TradeSignal schema required')
        if not isinstance(schema,dict) or schema.get('additionalProperties') is not False or set(schema.get('required', ())) != {'decision', 'confidence', 'reason'} or set(schema.get('properties', {})) != {'decision', 'confidence', 'reason'}:
            raise ValueError('strict three-field schema required')
        if not isinstance(strict_json(self.settings_json), dict):
            raise ValueError('settings object required')
        expected = shadow_content_hash(self.model_dump(mode='json', exclude={'variant_id'}))
        if self.variant_id and self.variant_id != expected:
            raise ValueError('variant hash mismatch')
        object.__setattr__(self, 'variant_id', expected)
        return self

    @property
    def prompt_hash(self):
        return shadow_content_hash({'system': self.system_prompt, 'version': self.prompt_version})

    @property
    def schema_hash(self):
        return shadow_content_hash(strict_json(self.signal_schema_json))


class ShadowSnapshot(Frozen):
    session: date
    ticker: Symbol
    cutoff: datetime
    price: Positive | None
    technicals_json: Text = '{}'
    quantity: Count = 0
    orderable_quantity: Count = 0
    average_price: Nonnegative = Decimal('0')
    open_sell_quantity: Count = 0
    available_cash: Nonnegative
    settled_cash: Nonnegative
    reserved_cash: Nonnegative
    pending_cash: Nonnegative
    daily_realized_loss: Nonnegative
    selected: StrictBool
    held: StrictBool
    eligible: StrictBool
    exclusions: tuple[str, ...] = ()
    unknowns: tuple[str, ...] = ()
    fixture_raw: Text
    baseline_action: Literal['BUY', 'SELL', 'HOLD']
    baseline_reason: Text
    baseline_quantity: Count = 0
    baseline_risk_override: StrictBool = False
    policy: BacktestPolicy
    profile: Literal['baseline', 'stress'] = 'baseline'
    market: Literal['KOSPI', 'KOSDAQ'] | None = None
    tick_rule_json: Text = 'null'
    next_session: date | None = None
    critical_unknown: StrictBool = False
    observation_available: StrictBool = True
    rendered_prompt: Text = ''
    news: tuple[Text, ...] = ()
    news_source_hashes: tuple[Hash, ...] = ()
    news_available: StrictBool = False
    unit_id: str = ''
    snapshot_id: str = ''

    @model_validator(mode='after')
    def identity(self):
        if self.orderable_quantity + self.open_sell_quantity != self.quantity or self.reserved_cash + self.available_cash != self.settled_cash:
            raise ValueError('snapshot balance mismatch')
        if self.quantity and self.average_price <= 0:
            raise ValueError('held price required')
        from zoneinfo import ZoneInfo
        if self.cutoff.astimezone(ZoneInfo('Asia/Seoul')).date() != self.session:
            raise ValueError('cutoff session mismatch')
        unit = shadow_content_hash({'session': self.session.isoformat(), 'ticker': self.ticker})
        expected = shadow_content_hash(self.model_dump(mode='json', exclude={'unit_id', 'snapshot_id'}))
        if self.unit_id and self.unit_id != unit or self.snapshot_id and self.snapshot_id != expected:
            raise ValueError('snapshot hash mismatch')
        object.__setattr__(self, 'unit_id', unit)
        object.__setattr__(self, 'snapshot_id', expected)
        return self


class ShadowManifest(Frozen):
    bundle_document_json: str = '{}'
    news_document_json: str = '[]'
    parent_spec_id: Hash | None = None
    parent_run_id: Name | None = None
    schema_version: Literal[1] = 1
    baseline_hash: Hash
    bundle_hash: Hash
    baseline_document_json: str
    snapshots: tuple[ShadowSnapshot, ...]
    variants: tuple[ShadowVariant, ...]
    pricing: tuple[ShadowPricing, ...]
    limits: ShadowLimits = ShadowLimits()
    sampling_version: Literal['stratified-hash-v1'] = 'stratified-hash-v1'
    seed: Name = 'shadow-v1'
    coverage_json: Text = '{}'
    source_hashes: tuple[Hash, ...] = ()
    code_revision: Name
    code_content_hash: Hash
    spec_id: str = ''

    @model_validator(mode='after')
    def identity(self):
        if (self.parent_spec_id is None)!=(self.parent_run_id is None): raise ValueError('linked run requires both parent identities')
        if not self.variants or len(self.variants) > self.limits.variant_limit or len(self.snapshots) > self.limits.sample_limit:
            raise ValueError('selection bound')
        if len({s.unit_id for s in self.snapshots}) != len(self.snapshots) or len({v.variant_id for v in self.variants}) != len(self.variants):
            raise ValueError('duplicate selection')
        if len(self.pricing) != len(self.variants):
            raise ValueError('one price profile per variant required')
        for v, price in zip(self.variants, self.pricing):
            if (v.provider, v.model) != (price.provider, price.model) or v.max_output_tokens > price.max_output_tokens:
                raise ValueError('price profile mismatch')
        if shadow_content_hash(strict_json(self.bundle_document_json))!=self.bundle_hash:raise ValueError('bundle hash mismatch')
        if len(self.news_document_json.encode('utf-8'))>NEWS_LIMIT:raise ValueError('news bound')
        if shadow_content_hash(strict_json(self.baseline_document_json)) != self.baseline_hash:
            raise ValueError('baseline hash mismatch')
        expected = shadow_content_hash(self.model_dump(mode='json', exclude={'spec_id'}))
        if self.spec_id and self.spec_id != expected:
            raise ValueError('manifest hash mismatch')
        object.__setattr__(self, 'spec_id', expected)
        return self


def load_shadow_manifest(path: str | Path) -> ShadowManifest:
    try:
        return ShadowManifest.model_validate(read_shadow_json(path))
    except ShadowInputError:
        raise
    except (ValidationError, ValueError, TypeError):
        raise ShadowInputError('INVALID_SHADOW_MANIFEST') from None


class ShadowUsage(Frozen):
    input_tokens: Count | None = None
    output_tokens: Count | None = None
    total_tokens: Count | None = None
    cached_input_tokens: Count | None = None
    cache_creation_tokens: Count | None = None
    reasoning_tokens: Count | None = None
    billed_cost: Nonnegative | None = None
    billed_currency: Annotated[str, Field(pattern=r"^[A-Z]{3}$")] | None = None
    billing_reference: Name | None = None

    @model_validator(mode='after')
    def valid_usage(self):
        if self.billed_cost is not None and (not self.billed_currency or not self.billing_reference):
            raise ValueError('bill attribution required')
        if self.known and self.reasoning_tokens is not None and self.reasoning_tokens > self.output_tokens:
            raise ValueError('reasoning is an output subdivision')
        return self

    @property
    def known(self):
        return self.input_tokens is not None and self.output_tokens is not None and self.total_tokens is not None and self.total_tokens == self.input_tokens + self.output_tokens


Outcome = Literal['SUCCESS', 'MALFORMED', 'REFUSAL', 'PROVIDER_ERROR', 'TIMEOUT_UNKNOWN', 'EXCLUDED', 'NOT_DISPATCHED']


def strict_trade_signal(raw: str):
    from .signal_parser import parse_signal, SignalParseError
    value = strict_json(raw, TEXT_LIMIT)
    if not isinstance(value, dict) or set(value) != {'decision', 'confidence', 'reason'}:
        raise ShadowInputError('INVALID_SIGNAL_SCHEMA')
    try:
        return parse_signal(raw).signal
    except SignalParseError:
        raise ShadowInputError('INVALID_SIGNAL_VALUES') from None


class ShadowObservation(Frozen):
    provider: Literal['openai', 'claude', 'codex_cli']
    requested_model: Name
    returned_model: Name | None = None
    status: Outcome
    validation_code: Name
    raw_output: Text = ''
    output_complete: StrictBool = True
    output_hash: str | None = None
    observed_prefix_hash: str = ''
    signal_json: Text | None = None
    usage: ShadowUsage = ShadowUsage()
    request_id: Name | None = None
    spec_id: str = ''
    run_id: str = ''
    attempt_id: str = ''
    unit_id: str = ''
    variant_id: str = ''
    snapshot_id: str = ''
    repetition: Count = 0
    retry_of: str | None = None

    @model_validator(mode='after')
    def validate_outcome(self):
        hashed = hashlib.sha256(self.raw_output.encode()).hexdigest()
        if self.observed_prefix_hash and self.observed_prefix_hash != hashed:
            raise ValueError('output hash mismatch')
        if self.output_hash is not None and (not self.output_complete or self.output_hash != hashed):
            raise ValueError('full hash mismatch')
        object.__setattr__(self, 'observed_prefix_hash', hashed)
        object.__setattr__(self, 'output_hash', hashed if self.output_complete else None)
        if self.status == 'SUCCESS':
            signal = strict_trade_signal(self.raw_output)
            signal_json = canonical_json({'decision':signal.decision.value,'confidence':signal.confidence,'reason':signal.reason})
            if self.signal_json is not None and canonical_json(strict_json(self.signal_json)) != signal_json:
                raise ValueError('signal mismatch')
            if not self.output_complete:
                raise ValueError('successful output must be complete')
            object.__setattr__(self, 'signal_json', signal_json)
        elif self.signal_json is not None:
            raise ValueError('failed observation cannot carry successful signal')
        return self


RunStatus = Literal['COMPLETE','PARTIAL','BUDGET_EXHAUSTED','INTERRUPTED','ACCOUNTING_BREACH']


class ShadowRunResult(Frozen):
    stop_reason: Name | None = None
    schema_version: Literal[1] = 1
    manifest: ShadowManifest
    run_id: Name
    status: RunStatus
    observations: tuple[ShadowObservation, ...]
    events_document_json: str
    metrics_document_json: str
    result_id: str = ''

    @model_validator(mode='after')
    def identity(self):
        ids = [o.attempt_id for o in self.observations]
        if len(set(ids)) != len(ids) or any(not o.attempt_id or o.spec_id != self.manifest.spec_id or o.run_id != self.run_id for o in self.observations):
            raise ValueError('observation attribution mismatch')
        expected = shadow_content_hash(self.model_dump(mode='json',exclude={'result_id'}))
        if self.result_id and self.result_id != expected:
            raise ValueError('result hash mismatch')
        object.__setattr__(self, 'result_id', expected)
        return self
