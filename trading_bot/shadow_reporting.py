"""Deterministic descriptive comparison; no model/policy promotion authority."""
from __future__ import annotations
from collections import Counter
from decimal import Decimal
from .shadow_models import *
from .shadow_store import validate_events
from .backtest_engine import project_backtest_action
from .backtest_reporting import _write_evidence_bytes, BacktestResult, build_backtest_result


class ShadowComparison(Frozen):
    unit_id: str
    variant_id: str
    attempt_id: str
    status: str
    valid_pair: bool
    raw_agreement: bool | None = None
    confidence_delta: float | None = None
    baseline_action: str
    shadow_action: str
    baseline_quantity: int
    shadow_quantity: int
    gate_reason: str
    risk_override: bool
    baseline_risk_override: bool
    exact_equal: bool = False


def compare_shadow_action(snapshot,observation):
    base=None
    try:base=strict_trade_signal(snapshot.fixture_raw)
    except ValueError:pass
    shadow=strict_trade_signal(observation.raw_output) if observation.status=='SUCCESS' else None
    proposal=project_backtest_action(snapshot,observation.raw_output) if shadow else None
    valid=base is not None and shadow is not None
    return ShadowComparison(unit_id=snapshot.unit_id,variant_id=observation.variant_id,attempt_id=observation.attempt_id,status=observation.status,valid_pair=valid,raw_agreement=base.decision==shadow.decision if valid else None,confidence_delta=shadow.confidence-base.confidence if valid else None,baseline_action=snapshot.baseline_action,shadow_action=proposal.action if proposal else 'HOLD',baseline_quantity=snapshot.baseline_quantity,shadow_quantity=proposal.quantity if proposal else 0,gate_reason=proposal.reason if proposal else 'FAILED_OBSERVATION_NO_ACTION',risk_override=proposal.risk_override if proposal else False,baseline_risk_override=snapshot.baseline_risk_override,exact_equal=bool(valid and base==shadow and (proposal.action,proposal.quantity,proposal.risk_override)==(snapshot.baseline_action,snapshot.baseline_quantity,snapshot.baseline_risk_override)))


def _metrics(manifest,observations,attempts):
    units={s.unit_id:s for s in manifest.snapshots}; comparisons=[];latest={}
    for o in observations:
        c=compare_shadow_action(units[o.unit_id],o);comparisons.append(c.model_dump(mode='json'))
        latest[(o.unit_id,o.variant_id,o.repetition)]=(o,c)
    variants=[]
    for v in manifest.variants:
        obs=[o for o in observations if o.variant_id==v.variant_id]
        paired=[(o,c) for (u,vid,r),(o,c) in latest.items() if vid==v.variant_id]
        valid=[(o,c) for o,c in paired if c.valid_pair]
        counts=dict(sorted(Counter(o.status for o in obs).items()))
        matrix=Counter()
        for o,c in valid:matrix[strict_trade_signal(units[o.unit_id].fixture_raw).decision.value+'->'+strict_trade_signal(o.raw_output).decision.value]+=1
        requested=len(manifest.snapshots)*manifest.limits.repetitions
        eligible=sum(s.eligible for s in manifest.snapshots)*manifest.limits.repetitions
        logical=sum(1 for _,vid,_ in latest if vid==v.variant_id)
        known=[o for o in obs if o.usage.known];charges=[a['charge'] for a in attempts.values() if a['variant_id']==v.variant_id]
        estimated=[Decimal(c['estimated_cost_usd']) for c in charges if c.get('estimated_cost_usd') is not None]
        variants.append({'variant_id':v.variant_id,'provider':v.provider,'requested_model':v.model,'returned_models':sorted({o.returned_model for o in obs if o.returned_model}),'unknown_returned_model_attempts':sum(o.returned_model is None for o in obs),'requested':requested,'eligible':eligible,'excluded':requested-eligible,'not_dispatched':eligible-logical,'attempted':len(obs),'finalized':len(obs),'retry_attempts':sum(o.retry_of is not None for o in obs),'unknown_outcome':counts.get('TIMEOUT_UNKNOWN',0),'outcomes':counts,'valid_pairs':len(valid),'agreement_numerator':sum(c.raw_agreement for o,c in valid),'agreement_denominator':len(valid),'matrix':dict(sorted(matrix.items())),'failure_numerator':sum(o.status!='SUCCESS' for o in obs),'failure_denominator':len(obs),'confidence_mean_delta':sum(c.confidence_delta for o,c in valid)/len(valid) if valid else None,'action_changes':sum(c.shadow_action!=c.baseline_action for o,c in paired),'quantity_changes':sum(c.shadow_quantity!=c.baseline_quantity for o,c in paired),'risk_changes':sum(c.risk_override!=c.baseline_risk_override for o,c in paired),'rare_baseline_risk_pairs':sum(c.baseline_risk_override for o,c in valid),'known_actual_tokens':sum(o.usage.total_tokens for o in known),'unknown_usage_attempts':len(obs)-len(known),'estimated_known_subtotal_usd':str(sum(estimated,Decimal(0))),'estimated_cost_usd':str(sum(estimated,Decimal(0))) if len(estimated)==len(obs) and obs else None,'charged_tokens':sum(c['charged_tokens'] for c in charges),'consumed_plus_retained_usd':str(sum((Decimal(c['charged_cost_usd']) for c in charges),Decimal(0))),'retained_reservations':sum(c['retained_reservation'] for c in charges),'actual_billed_cost':None,'bill_facts':[{'amount':str(o.usage.billed_cost),'currency':o.usage.billed_currency,'reference':o.usage.billing_reference} for o in obs if o.usage.billed_cost is not None],'judgment':'NO_MEANINGFUL_DIFFERENCE' if len(valid)==eligible and eligible>0 and all(c.exact_equal for o,c in valid) else 'INSUFFICIENT_EVIDENCE'})
    return {'variants':variants,'comparisons':comparisons,'attempted':len(observations),'requested':sum(v['requested'] for v in variants),'not_dispatched':sum(v['not_dispatched'] for v in variants),'valid_pairs':sum(v['valid_pairs'] for v in variants),'coverage':strict_json(manifest.coverage_json),'judgment_rule':'Exact signal including confidence/reason and projected action/quantity/risk equality for every eligible paired observation; consistency only.','promotion_authority':False,'alternative_portfolio_pnl':None}


def build_shadow_result(execution):
    manifest=ShadowManifest.model_validate(execution.manifest.model_dump())
    baseline=BacktestResult.model_validate(strict_json(manifest.baseline_document_json))
    if build_backtest_result(baseline.run)!=baseline:raise ShadowInputError('INVALID_CANONICAL_BASELINE')
    # Final saved evidence retains all random outputs; recompute derived facts offline.
    attempts=validate_events(manifest,execution.run_id,list(execution.events))
    expected=tuple(a['observation'] for a in attempts.values() if a['observation'] is not None)
    if any(a['observation'] is None for a in attempts.values()) or expected!=tuple(execution.observations): raise ShadowInputError('RESULT_JOURNAL_CARDINALITY_MISMATCH')
    decisions={(d.session,d.ticker):d for d in baseline.run.decisions}
    for s in manifest.snapshots:
        d=decisions.get((s.session,s.ticker))
        if d is None or (s.baseline_action,s.baseline_quantity,s.baseline_reason,s.baseline_risk_override)!=(d.action,d.quantity,d.reason,d.risk_override) or s.policy.model_dump(mode='json')!=baseline.run.manifest['policy']:raise ShadowInputError('SNAPSHOT_BASELINE_MISMATCH')
    metrics=_metrics(manifest,execution.observations,attempts)
    if any(a['charge']['breach'] for a in attempts.values()) and execution.status!='ACCOUNTING_BREACH':raise ShadowInputError('INVALID_BREACH_STATUS')
    if execution.status=='COMPLETE' and (metrics['not_dispatched'] or not manifest.snapshots or any(o.status=='TIMEOUT_UNKNOWN' for o in execution.observations)): raise ShadowInputError('FALSE_COMPLETE_STATUS')
    return ShadowRunResult(manifest=manifest,run_id=execution.run_id,status=execution.status,observations=tuple(execution.observations),events_document_json=canonical_json(list(execution.events)),metrics_document_json=canonical_json(metrics))
