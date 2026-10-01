import json
from types import SimpleNamespace
import httpx
import pytest
from trading_bot.shadow_providers import *
from test_shadow_models import variant,pricing
from test_shadow_store import frozen
from trading_bot.shadow_models import ShadowVariant,ShadowPricing


def snapshot(): return frozen().snapshots[0]


def live_price():
    return ShadowPricing.model_validate({**pricing().model_dump(),'synthetic':False})

@pytest.mark.parametrize('content,finish,refusal,status',[
    ('{"decision":"HOLD","confidence":0.4,"reason":"fixture"}','stop',None,'SUCCESS'),
    ('bad','stop',None,'MALFORMED'),('partial','length',None,'MALFORMED'),('', 'stop','refused','REFUSAL'),
])
def test_one_sdk_request_preserves_usage(monkeypatch,content,finish,refusal,status):
    calls=[];monkeypatch.setenv('SHADOW_OPENAI_API_KEY','secret-test')
    def handler(req):
        calls.append(json.loads(req.content));return httpx.Response(200,json={'id':'req-fixture','object':'chat.completion','created':1,'model':'fixture-model','choices':[{'index':0,'message':{'role':'assistant','content':content,'refusal':refusal},'finish_reason':finish}], 'usage':{'prompt_tokens':20,'completion_tokens':4,'total_tokens':24}})
    p=build_shadow_provider(variant(),live_price(),transport=httpx.MockTransport(handler))
    try:
        o=p.observe(snapshot(),variant());assert o.status==status and o.usage.total_tokens==24
        assert len(calls)==1 and calls[0]['max_completion_tokens']==1024
        assert calls[0]['messages'][1]['content']==snapshot().rendered_prompt
        assert p._client.max_retries==0 and p._client.timeout==60
        assert 'secret-test' not in repr(p)+canonical_json(o)
    finally:p.close()

@pytest.mark.parametrize('failure',['http','timeout'])
def test_no_hidden_retry_on_failure(monkeypatch,failure):
    monkeypatch.setenv('SHADOW_OPENAI_API_KEY','secret-test');calls=[]
    def handler(req):
        calls.append(req)
        if failure=='timeout':raise httpx.ReadTimeout('sensitive',request=req)
        return httpx.Response(500,json={'error':{'message':'sensitive','type':'server_error'}})
    p=build_shadow_provider(variant(),live_price(),transport=httpx.MockTransport(handler))
    o=p.observe(snapshot(),variant());p.close()
    assert len(calls)==1 and o.status in ('PROVIDER_ERROR','TIMEOUT_UNKNOWN') and not o.usage.known
    assert 'sensitive' not in canonical_json(o)


def test_claude_forced_tool_and_inclusive_usage():
    v=ShadowVariant.model_validate({**variant().model_dump(),'provider':'claude','variant_id':''})
    p=ShadowPricing.model_validate({**pricing().model_dump(),'provider':'claude','endpoint':'messages'})
    calls=[]
    def create(**kw):
        calls.append(kw);return {'model':v.model,'id':'r','stop_reason':'tool_use','content':[{'type':'tool_use','name':'emit_signal','input':{'decision':'SELL','confidence':0.9,'reason':'fixture'}}],'usage':{'input_tokens':10,'cache_read_input_tokens':3,'cache_creation_input_tokens':2,'output_tokens':5}}
    adapter=ClaudeShadowProvider(SimpleNamespace(messages=SimpleNamespace(create=create)),p)
    o=adapter.observe(snapshot(),v)
    assert o.status=='SUCCESS' and o.usage.total_tokens==20 and o.usage.input_tokens==15
    assert len(calls)==1 and len(calls[0]['tools'])==1 and calls[0]['tools'][0]['strict']


def test_unsupported_cli_and_synthetic_profile_before_credentials(monkeypatch):
    import subprocess
    monkeypatch.setattr(subprocess,'run',lambda *a,**k:pytest.fail('process forbidden'))
    v=ShadowVariant.model_validate({**variant().model_dump(),'provider':'codex_cli','variant_id':''})
    p=ShadowPricing.model_validate({**pricing().model_dump(),'provider':'codex_cli','endpoint':'codex.exec'})
    with pytest.raises(ValueError,match='UNSUPPORTED_SHADOW_CAPABILITY'): build_shadow_provider(v,p)
    with pytest.raises(ValueError,match='UNREVIEWED'): build_shadow_provider(variant(),pricing())


def test_origin_redirect_and_oversize_fail_closed(monkeypatch):
    monkeypatch.setenv('SHADOW_OPENAI_API_KEY','key-test');calls=[]
    def handle(req): calls.append(req);return httpx.Response(307,headers={'location':'https://evil.example/'})
    p=build_shadow_provider(variant(),live_price(),transport=httpx.MockTransport(handle))
    assert p.observe(snapshot(),variant()).status=='PROVIDER_ERROR';p.close();assert len(calls)==1
    transport=BoundedTransport('openai',httpx.MockTransport(handle))
    with pytest.raises(ValueError,match='ORIGIN'): transport.handle_request(httpx.Request('POST','https://evil.example/'))
    p=build_shadow_provider(variant(),live_price(),transport=httpx.MockTransport(lambda req:httpx.Response(200,content=b'x'*(HTTP_LIMIT+1))))
    assert not p.observe(snapshot(),variant()).usage.known;p.close()


def test_only_dedicated_credentials_and_no_live_settings(monkeypatch):
    from trading_bot import config
    monkeypatch.setattr(config,'Settings',lambda *a,**k:pytest.fail('live settings forbidden'))
    monkeypatch.delenv('SHADOW_OPENAI_API_KEY',raising=False);monkeypatch.setenv('OPENAI_API_KEY','live-key')
    with pytest.raises(ValueError,match='MISSING_SHADOW'): build_shadow_provider(variant(),live_price())
    assert 'live-key' not in repr(ShadowCredentials('openai','live-key'))


def test_unsupported_settings_and_invalid_usage():
    v=ShadowVariant.model_validate({**variant().model_dump(),'settings_json':'{"tools":1}','variant_id':''})
    with pytest.raises(ValueError,match='UNSUPPORTED'): validate_provider_profile(v,live_price())
    assert not normalize_shadow_usage('openai',{'prompt_tokens':True,'completion_tokens':2,'total_tokens':3}).known
    assert not normalize_shadow_usage('claude',{'input_tokens':-1,'output_tokens':2}).known


def test_compressed_response_is_rejected_before_decompression():
    class Stream(httpx.SyncByteStream):
        def __iter__(self):pytest.fail('compressed body must not be read')
    transport=BoundedTransport('openai',httpx.MockTransport(lambda req:httpx.Response(200,headers={'content-encoding':'gzip'},stream=Stream())))
    with pytest.raises(ValueError,match='COMPRESSED'):transport.handle_request(httpx.Request('POST','https://api.openai.com/v1/chat/completions'))
