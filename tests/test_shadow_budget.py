from decimal import Decimal
import pytest
from trading_bot.shadow_budget import *
from trading_bot.shadow_models import ShadowLimits, ShadowUsage
from test_shadow_models import pricing, observation


def test_exact_cap_and_next_call_blocked():
    p=pricing();b=reserve_bound(p,1024)
    limits=ShadowLimits(max_attempts=1,max_total_tokens=b.tokens,max_cost_usd=b.cost_usd)
    assert ShadowBudget(limits).reserve_attempt_group([(p,1024)])==(b,)
    with pytest.raises(ValueError,match='BUDGET_EXHAUSTED'):
        ShadowBudget(limits,[{'charged_tokens':b.tokens,'charged_cost_usd':str(b.cost_usd)}]).reserve_attempt_group([(p,1024)])


def test_paired_group_all_or_none_and_unknown_retained():
    p=pricing()
    with pytest.raises(ValueError): ShadowBudget(ShadowLimits(max_attempts=1)).reserve_attempt_group([(p,1024),(p,1024)])
    c=settle_attempt_usage(p,1024,observation(usage=ShadowUsage()))
    assert c['retained_reservation'] and c['charged_tokens']==2024 and c['estimated_cost_usd'] is None


def test_subdivisions_and_unclipped_breach():
    p=pricing();u=ShadowUsage(input_tokens=100,output_tokens=20,total_tokens=120,reasoning_tokens=10)
    c=settle_attempt_usage(p,1024,observation(usage=u,returned_model=p.model))
    assert c['charged_tokens']==120 and not c['breach']
    u=ShadowUsage(input_tokens=5000,output_tokens=20,total_tokens=5020)
    c=settle_attempt_usage(p,1024,observation(usage=u))
    assert c['breach'] and c['charged_tokens']==5020
    with pytest.raises(ValueError,match='ACCOUNTING_BREACH'): ShadowBudget(ShadowLimits(),[c]).reserve_attempt_group([(p,1024)])


def test_missing_cache_tariff_and_model_mismatch_retain_bound():
    p=pricing();u=ShadowUsage(input_tokens=100,output_tokens=20,total_tokens=120,cached_input_tokens=10)
    assert settle_attempt_usage(p,1024,observation(usage=u))['retained_reservation']
    assert settle_attempt_usage(p,1024,observation(returned_model='other'))['breach']
