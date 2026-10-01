import json
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import pytest
from pydantic import ValidationError
from trading_bot.shadow_models import *


def variant():
    from trading_bot.trade_signal import TradeSignal
    return ShadowVariant(provider='openai',model='fixture-model',system_prompt='Fixture system',prompt_version='1',signal_schema_json=canonical_json(TradeSignal.model_json_schema()))


def pricing(**updates):
    return ShadowPricing(provider='openai',model='fixture-model',endpoint='chat.completions',source='https://example.invalid/synthetic',reviewed_at=datetime(2026,10,1,tzinfo=timezone.utc),synthetic=True,context_upper_bound=1000,input_per_million='1',output_per_million='2',**updates)


def manifest():
    return ShadowManifest(baseline_hash=shadow_content_hash({}),bundle_hash='b'*64,baseline_document_json='{}',snapshots=(),variants=(variant(),),pricing=(pricing(),),code_revision='fixture',code_content_hash='c'*64)


def test_manifest_roundtrip_and_reordered_keys(tmp_path):
    m=manifest();p=tmp_path/'m.json';p.write_text(json.dumps(m.model_dump(mode='json'),sort_keys=True))
    assert load_shadow_manifest(p)==m
    assert manifest().spec_id==m.spec_id


@pytest.mark.parametrize('field,value',[('max_attempts',True),('concurrency',5),('max_total_tokens',0),('max_cost_usd','NaN'),('max_cost_usd','-1')])
def test_limits_fail_closed(field,value):
    with pytest.raises(ValidationError):ShadowLimits(**{field:value})


def test_identity_changes_and_tamper_rejected():
    m=manifest();raw=m.model_dump(mode='json');raw['limits']['max_attempts']=99
    with pytest.raises(ValidationError):ShadowManifest.model_validate(raw)
    raw['spec_id']='';assert ShadowManifest.model_validate(raw).spec_id!=m.spec_id
    raw['unknown_key']=True
    with pytest.raises(ValidationError):ShadowManifest.model_validate(raw)


@pytest.mark.parametrize('text',['{"x":1,"x":2}','{"x":NaN}','[Infinity]'])
def test_duplicate_nonfinite_json_rejected(text):
    with pytest.raises(ShadowInputError):strict_json(text)


def test_fx_and_aware_pricing():
    with pytest.raises(ValidationError):pricing(currency='KRW')
    raw=pricing().model_dump(mode='json');raw['reviewed_at']='2026-10-01T00:00:00'
    with pytest.raises(ValidationError):ShadowPricing.model_validate(raw)


def test_utf8_bound_and_synthetic_fixture():
    raw=variant().model_dump(mode='json');raw['system_prompt']='한'*TEXT_LIMIT
    with pytest.raises(ValidationError):ShadowVariant.model_validate(raw)
    fixture=Path('tests/fixtures/shadow/minimal_manifest.json')
    m=load_shadow_manifest(fixture)
    assert m.pricing[0].synthetic and 'api_key' not in fixture.read_text()
