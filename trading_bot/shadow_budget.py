"""Conservative whole-call reservations; tariff costs are estimates, not bills."""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from .shadow_models import ShadowInputError, ShadowLimits, ShadowPricing, ShadowUsage


@dataclass(frozen=True)
class Reservation:
    tokens: int
    cost_usd: Decimal


def reserve_bound(price: ShadowPricing, output_limit: int) -> Reservation:
    if output_limit > price.max_output_tokens: raise ShadowInputError('UNBOUNDED_OUTPUT')
    rates=[price.input_per_million]
    # Enabled caching must be priced; higher cache-write tariffs enter the bound.
    rates.extend(r for r in (price.cache_read_per_million,price.cache_write_per_million) if r is not None)
    amount=(price.context_upper_bound*max(rates)+output_limit*price.output_per_million)/Decimal(1000000)
    return Reservation(price.context_upper_bound+output_limit,amount*(price.usd_per_native or Decimal(1)))


def usage_cost(price: ShadowPricing, usage: ShadowUsage):
    if not usage.known: return None
    cached=usage.cached_input_tokens or 0; creation=usage.cache_creation_tokens or 0
    if cached+creation>usage.input_tokens: return None
    if cached and price.cache_read_per_million is None: return None
    if creation and price.cache_write_per_million is None: return None
    cost=((usage.input_tokens-cached-creation)*price.input_per_million+cached*(price.cache_read_per_million or 0)+creation*(price.cache_write_per_million or 0)+usage.output_tokens*price.output_per_million)/Decimal(1000000)
    return cost*(price.usd_per_native or Decimal(1))


def settle_attempt_usage(price, output_limit, observation):
    bound=reserve_bound(price,output_limit); usage=observation.usage
    estimated=usage_cost(price,usage)
    model_mismatch=observation.returned_model is not None and observation.returned_model!=price.model
    breach=model_mismatch or (usage.known and (usage.input_tokens>price.context_upper_bound or usage.output_tokens>output_limit)) or (estimated is not None and estimated>bound.cost_usd)
    uncertain=not usage.known or estimated is None or observation.status=='TIMEOUT_UNKNOWN'
    tokens=max(bound.tokens,usage.total_tokens or 0) if uncertain or breach else usage.total_tokens
    cost=max(bound.cost_usd,estimated or Decimal(0)) if uncertain or breach else estimated
    return {'charged_tokens':tokens,'charged_cost_usd':str(cost),'estimated_cost_usd':str(estimated) if estimated is not None else None,'retained_reservation':uncertain or breach,'breach':bool(breach),'actual_billed_cost':str(usage.billed_cost) if usage.billed_cost is not None else None,'billing_currency':usage.billed_currency,'billing_reference':usage.billing_reference}


class ShadowBudget:
    def __init__(self, limits: ShadowLimits, charges=()):
        self.limits=limits; self.charges=tuple(charges)
    def reserve_attempt_group(self, profiles):
        bounds=tuple(reserve_bound(p,o) for p,o in profiles)
        if any(c.get('breach') for c in self.charges): raise ShadowInputError('ACCOUNTING_BREACH')
        if len(self.charges)+len(bounds)>self.limits.max_attempts or sum(c['charged_tokens'] for c in self.charges)+sum(b.tokens for b in bounds)>self.limits.max_total_tokens or sum((Decimal(c['charged_cost_usd']) for c in self.charges),Decimal(0))+sum((b.cost_usd for b in bounds),Decimal(0))>self.limits.max_cost_usd:
            raise ShadowInputError('BUDGET_EXHAUSTED')
        return bounds

reserve_attempt_group=lambda budget,profiles: budget.reserve_attempt_group(profiles)
