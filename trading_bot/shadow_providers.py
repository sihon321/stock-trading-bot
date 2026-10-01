"""Single-shot LLM-only adapters. No live settings, broker or executable tools."""
from __future__ import annotations
import os
import time
from dataclasses import dataclass, field
from typing import Protocol
import httpx
from .shadow_models import *

HTTP_LIMIT=1024*1024


class ShadowProvider(Protocol):
    def observe(self,snapshot,variant) -> ShadowObservation: ...


@dataclass(frozen=True)
class ShadowCredentials:
    provider: str
    api_key: str = field(repr=False)
    @classmethod
    def load(cls,provider):
        name={'openai':'SHADOW_OPENAI_API_KEY','claude':'SHADOW_ANTHROPIC_API_KEY'}.get(provider)
        if name is None: raise ShadowInputError('UNSUPPORTED_SHADOW_CAPABILITY')
        key=os.environ.get(name)
        if not key: raise ShadowInputError('MISSING_SHADOW_CREDENTIALS')
        return cls(provider,key)


def validate_provider_profile(variant,price,*,allow_synthetic=False):
    if variant.provider=='codex_cli': raise ShadowInputError('UNSUPPORTED_SHADOW_CAPABILITY')
    if (variant.provider,variant.model)!=(price.provider,price.model) or price.synthetic and not allow_synthetic: raise ShadowInputError('UNREVIEWED_PROVIDER_PROFILE')
    if not (allow_synthetic and price.synthetic):
        if not all((price.strict_schema_supported,price.output_ceiling_supported,price.usage_envelope_supported)) or variant.provider=='claude' and not price.forced_tool_supported:
            raise ShadowInputError('UNREVIEWED_PROVIDER_CAPABILITY')
    # Current official docs explicitly prohibit forced tool_choice on these families.
    unsupported=('claude-opus-5-5','claude-sonnet-5-5','claude-fable-5-1','claude-mythos-5-1')
    if variant.provider=='claude' and variant.model.startswith(unsupported): raise ShadowInputError('UNSUPPORTED_SHADOW_CAPABILITY')
    if variant.max_output_tokens>price.max_output_tokens: raise ShadowInputError('UNBOUNDED_OUTPUT')
    settings=strict_json(variant.settings_json); supported=strict_json(price.settings_supported_json)
    allowed={'temperature','top_p','seed'} if variant.provider=='openai' else {'temperature','top_p'}
    if not isinstance(supported,dict) or not set(settings)<=allowed or any(k not in supported or settings[k]!=supported[k] for k in settings): raise ShadowInputError('UNSUPPORTED_REQUEST_SETTINGS')
    if any(type(v) not in (int,float) or not __import__('math').isfinite(v) for v in settings.values()): raise ShadowInputError('INVALID_REQUEST_SETTINGS')
    return settings


class BoundedTransport(httpx.BaseTransport):
    """Read no more than one bounded response; no redirect/proxy/retry authority."""
    def __init__(self,provider,inner=None):
        self.host='api.openai.com' if provider=='openai' else 'api.anthropic.com'
        self.inner=inner or httpx.HTTPTransport(retries=0,trust_env=False)
    def handle_request(self,request):
        if request.url.scheme!='https' or request.url.host!=self.host or request.url.port not in (None,443): raise ShadowInputError('UNSUPPORTED_PROVIDER_ORIGIN')
        if len(request.content)>HTTP_LIMIT: raise ShadowInputError('PROVIDER_REQUEST_TOO_LARGE')
        request.headers['Accept-Encoding']='identity'
        response=self.inner.handle_request(request);buffer=bytearray();start=time.monotonic()
        try:
            if response.headers.get('content-encoding','identity').lower() not in ('','identity'): raise ShadowInputError('UNSUPPORTED_COMPRESSED_RESPONSE')
            chunks=(response.content,) if response.is_stream_consumed else response.iter_raw(chunk_size=65536)
            for chunk in chunks:
                if len(buffer)+len(chunk)>HTTP_LIMIT: raise ShadowInputError('PROVIDER_RESPONSE_TOO_LARGE')
                if time.monotonic()-start>60: raise httpx.ReadTimeout('bounded timeout',request=request)
                buffer.extend(chunk)
            return httpx.Response(response.status_code,headers=response.headers,content=bytes(buffer),request=request)
        finally: response.close()
    def close(self): self.inner.close()


def _dict(value):
    if hasattr(value,'model_dump'): return value.model_dump(mode='json')
    return value if isinstance(value,dict) else {}


def normalize_shadow_usage(provider,value):
    u=_dict(value)
    try:
        if provider=='openai':
            return ShadowUsage(input_tokens=u.get('prompt_tokens'),output_tokens=u.get('completion_tokens'),total_tokens=u.get('total_tokens'),cached_input_tokens=_dict(u.get('prompt_tokens_details')).get('cached_tokens'),reasoning_tokens=_dict(u.get('completion_tokens_details')).get('reasoning_tokens'))
        counts=[u.get('input_tokens'),u.get('cache_read_input_tokens',0),u.get('cache_creation_input_tokens',0)]
        if any(type(n) is not int or n<0 for n in counts) or type(u.get('output_tokens')) is not int: return ShadowUsage()
        total_input=sum(counts); output=u['output_tokens']
        return ShadowUsage(input_tokens=total_input,output_tokens=output,total_tokens=total_input+output,cached_input_tokens=counts[1],cache_creation_tokens=counts[2])
    except ValueError: return ShadowUsage()


class _APIProvider:
    provider=''
    def __init__(self,client,price,*,secret=''):
        self._client=client;self.price=price;self._secret=secret
    def __repr__(self): return f'{type(self).__name__}(model={self.price.model!r})'
    def close(self): self._client.close()
    def observe(self,snapshot,variant):
        validate_provider_profile(variant,self.price,allow_synthetic=self.price.synthetic)
        if not snapshot.eligible or not snapshot.rendered_prompt: raise ShadowInputError('INELIGIBLE_SHADOW_INPUT')
        validate_shadow_request(snapshot,variant)
        # Frozen text models enforce UTF-8 bounds before any request.
        try:
            response=self._call(snapshot,variant);r=_dict(response)
        except (httpx.TimeoutException,TimeoutError):
            return ShadowObservation(provider=self.provider,requested_model=variant.model,status='TIMEOUT_UNKNOWN',validation_code='TRANSPORT_TIMEOUT',output_complete=False)
        except Exception:
            return ShadowObservation(provider=self.provider,requested_model=variant.model,status='PROVIDER_ERROR',validation_code='PROVIDER_REQUEST_FAILED',output_complete=False)
        usage=normalize_shadow_usage(self.provider,r.get('usage'));status='SUCCESS';code='VALID_SIGNAL';complete=True
        try:
            raw,refusal,complete=self._output(r)
            if not isinstance(raw,str): raw='';complete=False
            encoded=raw.encode('utf-8')
            if len(encoded)>TEXT_LIMIT: raw=encoded[:TEXT_LIMIT].decode('utf-8','ignore');complete=False;code='OUTPUT_TOO_LARGE'
            if self._secret and self._secret in raw: raw=raw.replace(self._secret,'[REDACTED]');complete=False;code='REDACTED_SECRET'
            if refusal: status='REFUSAL';code='PROVIDER_REFUSAL'
            elif not complete: status='MALFORMED';code=code if code!='VALID_SIGNAL' else 'TRUNCATED_OUTPUT'
            else:
                try: strict_trade_signal(raw)
                except ValueError: status='MALFORMED';code='INVALID_SIGNAL'
        except (KeyError,IndexError,TypeError,ValueError): raw='';status='MALFORMED';code='INVALID_ENVELOPE';complete=False
        model=r.get('model');request=getattr(response,'_request_id',None) or r.get('id')
        import re
        clean=lambda v:v if isinstance(v,str) and len(v)<=200 and re.fullmatch(r'[A-Za-z0-9_.:/-]+',v) and (not self._secret or self._secret not in v) else None
        return ShadowObservation(provider=self.provider,requested_model=variant.model,returned_model=clean(model),request_id=clean(request),status=status,validation_code=code,raw_output=raw,output_complete=complete,usage=usage)


class OpenAIShadowProvider(_APIProvider):
    provider='openai'
    def _call(self,s,v):
        return self._client.chat.completions.create(**validate_shadow_request(s,v))
    def _output(self,r):
        c=r['choices'][0];m=c['message']; return m.get('content') or '',bool(m.get('refusal')),c.get('finish_reason')=='stop'


class ClaudeShadowProvider(_APIProvider):
    provider='claude'
    def _call(self,s,v):
        return self._client.messages.create(**validate_shadow_request(s,v))
    def _output(self,r):
        if r.get('stop_reason')=='refusal': return '',True,True
        tools=[c for c in r.get('content',[]) if c.get('type')=='tool_use']
        if len(tools)!=1 or tools[0].get('name')!='emit_signal': return canonical_json(r.get('content',[])),False,False
        return canonical_json(tools[0]['input']),False,r.get('stop_reason')=='tool_use'


def build_shadow_provider(variant,price,*,transport=None):
    validate_provider_profile(variant,price)
    credentials=ShadowCredentials.load(variant.provider)
    client=httpx.Client(transport=BoundedTransport(variant.provider,transport),trust_env=False,follow_redirects=False,timeout=httpx.Timeout(60))
    if variant.provider=='openai':
        from openai import OpenAI
        sdk=OpenAI(api_key=credentials.api_key,base_url='https://api.openai.com/v1',max_retries=0,timeout=60,http_client=client)
        return OpenAIShadowProvider(sdk,price,secret=credentials.api_key)
    from anthropic import Anthropic
    sdk=Anthropic(api_key=credentials.api_key,base_url='https://api.anthropic.com',max_retries=0,timeout=60,http_client=client)
    return ClaudeShadowProvider(sdk,price,secret=credentials.api_key)


def validate_shadow_request(s,v):
    if not s.eligible or not s.rendered_prompt: raise ShadowInputError('INELIGIBLE_SHADOW_INPUT')
    schema=strict_json(v.signal_schema_json)
    if v.provider=='openai':
        payload=dict(model=v.model,messages=[{'role':'system','content':v.system_prompt},{'role':'user','content':s.rendered_prompt}],max_completion_tokens=v.max_output_tokens,response_format={'type':'json_schema','json_schema':{'name':'TradeSignal','strict':True,'schema':schema}},**strict_json(v.settings_json))
    elif v.provider=='claude':
        payload=dict(model=v.model,system=v.system_prompt,messages=[{'role':'user','content':s.rendered_prompt}],max_tokens=v.max_output_tokens,tools=[{'name':'emit_signal','description':'Emit one trading signal.','strict':True,'input_schema':schema}],tool_choice={'type':'tool','name':'emit_signal'},**strict_json(v.settings_json))
    else: raise ShadowInputError('UNSUPPORTED_SHADOW_CAPABILITY')
    if len(__import__('json').dumps(payload,ensure_ascii=True).encode())>HTTP_LIMIT-4096: raise ShadowInputError('PROVIDER_REQUEST_TOO_LARGE')
    return payload
