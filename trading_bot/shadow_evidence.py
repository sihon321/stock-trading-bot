"""Saved Shadow proof contracts; no preparation, evaluation or dispatch capability.

A catalog entry is an operator-registered immutable trust anchor, supplied outside
the result document. Its expected hash must never be taken from an uploaded proof.
Historical v1 results lack full inventory/action provenance and remain UNKNOWN
without this separately registered evidence.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext

from .shadow_models import *
from .shadow_budget import ShadowBudget, reserve_bound, settle_attempt_usage
from .backtest_models import BacktestBundle, content_hash
from .backtest_reporting import BacktestResult, build_backtest_result
from .backtest_inputs import decision_view
from .backtest_costs import cost_profile
from .backtest_fills import opening_cutoff
from .backtest_ledger import PortfolioLedger


@dataclass(frozen=True)
class ShadowExecution:
    manifest: ShadowManifest
    run_id: str
    status: str
    observations: tuple
    events: tuple
    stop_reason: str | None = None


class SavedShadowUnavailable(ShadowInputError):
    status = 'UNKNOWN'
    code = 'SAVED_SHADOW_PROVENANCE_UNAVAILABLE'

    def __init__(self, predicates, *, spec_id=None, run_id=None):
        self.predicates = tuple(predicates)
        self.spec_id = spec_id
        self.run_id = run_id
        super().__init__(self.code)


@dataclass(frozen=True)
class VerifiedSavedShadow:
    result: ShadowRunResult
    metrics: dict
    comparisons: tuple
    status: str = 'VERIFIED'


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


class SavedShadowProof(Frozen):
    schema_version: Literal[1] = 1
    spec_id: Hash
    run_id: Name
    baseline_hash: Hash
    bundle_hash: Hash
    source_hashes: tuple[Hash, ...]
    news_hash: Hash
    code_revision: Name
    code_content_hash: Hash
    inventory: tuple[ShadowSnapshot, ...]
    comparisons: tuple[ShadowComparison, ...]
    events_hash: Hash
    observations_hash: Hash


class RegisteredShadowProof(Frozen):
    """Expected hash and spec/run identity come from trusted resource registration."""
    spec_id: Hash
    run_id: Name
    expected_hash: Hash
    document_json: str


@dataclass(frozen=True)
class SavedShadowProofCatalog:
    proofs: tuple[RegisteredShadowProof, ...]

    def __post_init__(self):
        object.__setattr__(self, 'proofs', tuple(self.proofs))
        keys = [(p.spec_id, p.run_id) for p in self.proofs]
        if len(set(keys)) != len(keys):
            raise ShadowInputError('DUPLICATE_REGISTERED_PROOF')

    def resolve(self, spec_id, run_id):
        return next((p for p in self.proofs if (p.spec_id, p.run_id) == (spec_id, run_id)), None)


def _verify_inventory(manifest, proof, bundle, baseline):
    """Fold recorded ledger transitions, never derive decisions or modeled fills.

    Indicator/screener/prompt facts are anchored in the registered capture inventory.
    Source rows, cutoff, cash and positions are additionally checked independently.
    """
    run = baseline.run
    m = run.manifest
    if (content_hash(bundle) != m['input_hash'] or m['input_hash'] != manifest.bundle_hash
            or tuple(m['source_hashes']) != bundle.sources.source_hashes
            or manifest.source_hashes != bundle.sources.source_hashes
            or m['policy'] != bundle.policy.model_dump(mode='json')
            or run.calendar != bundle.calendar or run.corporate_actions != bundle.corporate_actions
            or run.cost_rules != bundle.cost_rules or run.tick_rules != bundle.tick_rules):
        raise ShadowInputError('SAVED_BASELINE_SOURCE_LINK_MISMATCH')
    units = {s.unit_id: s for s in proof.inventory}
    if len(units) != len(proof.inventory) or len(units) > 250000:
        raise ShadowInputError('SAVED_UNIT_INVENTORY_CARDINALITY')
    sessions = tuple(s.session for s in run.calendar if s.completed)
    ledger = PortfolioLedger(bundle.policy, sessions, run.sessions[0].session if run.sessions else None)
    profile = cost_profile(m['profile']['name'])
    intents = {i.intent_id: i for i in run.intents}
    decisions = {(d.session, d.ticker): d for d in run.decisions}
    news = strict_json(manifest.news_document_json)
    if not isinstance(news, list):
        raise ShadowInputError('INVALID_SAVED_NEWS')
    parsed_news = tuple(FrozenHistoricalNews.model_validate(n) for n in news)
    seen = set()
    for session in run.sessions:
        day = session.session
        ledger.start_session(day)
        for action in sorted(run.corporate_actions, key=lambda a: (a.effective,
                {'SPLIT': 0, 'DIVIDEND': 1, 'DELIST': 2}[a.kind], a.action_id)):
            ledger.apply_corporate_action(action, day, opening_cutoff(day))
        ledger.settle_pending(day)
        for fill in run.fills:
            if fill.session == day:
                ledger.apply_fill(fill)
                ledger.expire(fill.intent_id)
        view = decision_view(bundle, day, tuple(ledger.holdings))
        captured = [s for s in proof.inventory if s.session == day]
        if {s.ticker for s in captured} != set(view.universe):
            raise ShadowInputError('SAVED_UNIT_INVENTORY_COVERAGE')
        # Fold the observer's recorded order and check reservation ordering below.
        reservation_order = []
        for s in captured:
            seen.add(s.unit_id)
            d = decisions.get((day, s.ticker))
            if d is None or (s.baseline_action, s.baseline_quantity, s.baseline_reason,
                    s.baseline_risk_override, s.selected) != (
                    d.action, d.quantity, d.reason, d.risk_override, d.selected):
                raise ShadowInputError('SNAPSHOT_BASELINE_MISMATCH')
            if s.policy != bundle.policy or s.profile != profile.name:
                raise ShadowInputError('SAVED_SNAPSHOT_POLICY_MISMATCH')
            lot = ledger.holdings.get(s.ticker)
            quantity = lot.quantity if lot else 0
            average = lot.average_price if lot else Decimal(0)
            selling = sum(i.reserved_quantity for i in ledger.intents.values() if i.ticker == s.ticker)
            if (s.quantity, s.average_price, s.orderable_quantity, s.open_sell_quantity,
                    s.available_cash, s.settled_cash, s.reserved_cash, s.pending_cash,
                    s.daily_realized_loss, s.held) != (
                    quantity, average, quantity - selling, selling, ledger.available_cash,
                    ledger.settled_cash, ledger.reserved_cash, ledger.pending_cash,
                    ledger.daily_realized_loss, bool(quantity)):
                raise ShadowInputError('SAVED_PRE_DECISION_ACCOUNT_MISMATCH')
            member = view.membership.get(s.ticker)
            rules = [r for r in bundle.tick_rules if member and r.market == member.market
                and r.effective_start <= day and (r.effective_end is None or day < r.effective_end)
                and r.known_at <= view.cutoff]
            costs = [r for r in bundle.cost_rules if member and r.market == member.market
                and r.effective_start <= day and (r.effective_end is None or day < r.effective_end)
                and r.known_at <= view.cutoff]
            later = [day2 for day2 in sessions if day2 > day]
            if (s.cutoff, s.price, s.fixture_raw, s.market, s.next_session, s.tick_rule_json) != (
                    view.cutoff, view.prices.get(s.ticker), view.signals.get(s.ticker, ''),
                    member.market if member else None, later[0] if later else None,
                    canonical_json(rules[0]) if len(rules) == len(costs) == 1 else 'null'):
                raise ShadowInputError('SAVED_SNAPSHOT_SOURCE_MISMATCH')
            visible = tuple(n for n in parsed_news if n.ticker == s.ticker and n.known_at <= s.cutoff)
            if (s.news, s.news_source_hashes, s.news_available) != (
                    tuple(n.text for n in visible), tuple(n.source_hash for n in visible), bool(visible)):
                raise ShadowInputError('SAVED_SNAPSHOT_NEWS_MISMATCH')
            if d.intent_id:
                intent = intents[d.intent_id]
                if ledger.reserve(intent, profile) != intent:
                    raise ShadowInputError('SAVED_PRE_DECISION_RESERVATION_MISMATCH')
                reservation_order.append(d.intent_id)
        if reservation_order != [d.intent_id for d in run.decisions if d.session == day and d.intent_id]:
            raise ShadowInputError('SAVED_DECISION_ORDER_MISMATCH')
    if seen != set(units):
        raise ShadowInputError('SAVED_UNIT_INVENTORY_SESSIONS')
    selected = select_shadow_sample(proof.inventory, manifest.limits.sample_limit, manifest.seed)
    if selected != manifest.snapshots:
        raise ShadowInputError('SAVED_SELECTION_MISMATCH')
    if canonical_json(_coverage(proof.inventory, selected, baseline)) != manifest.coverage_json:
        raise ShadowInputError('SAVED_COVERAGE_MISMATCH')


class FrozenHistoricalNews(Frozen):
    ticker: str
    known_at: datetime
    source_hash: Hash
    text: Text


def _verify_comparisons(manifest, observations, comparisons):
    if len(comparisons) != len(observations):
        raise ShadowInputError('SAVED_ACTION_CARDINALITY_MISMATCH')
    units = {s.unit_id: s for s in manifest.snapshots}
    for o, c in zip(observations, comparisons):
        s = units[o.unit_id]
        if (c.unit_id, c.variant_id, c.attempt_id, c.status, c.baseline_action,
                c.baseline_quantity, c.baseline_risk_override) != (
                o.unit_id, o.variant_id, o.attempt_id, o.status, s.baseline_action,
                s.baseline_quantity, s.baseline_risk_override):
            raise ShadowInputError('SAVED_ACTION_ATTRIBUTION_MISMATCH')
        try:
            base = strict_trade_signal(s.fixture_raw)
        except ValueError:
            base = None
        shadow = strict_trade_signal(o.raw_output) if o.status == 'SUCCESS' else None
        valid = base is not None and shadow is not None
        agreement = base.decision == shadow.decision if valid else None
        delta = shadow.confidence - base.confidence if valid else None
        exact = bool(valid and base == shadow and (c.shadow_action, c.shadow_quantity,
            c.risk_override) == (s.baseline_action, s.baseline_quantity, s.baseline_risk_override))
        if (c.valid_pair, c.raw_agreement, c.confidence_delta, c.exact_equal) != (valid, agreement, delta, exact):
            raise ShadowInputError('SAVED_SIGNAL_COMPARISON_MISMATCH')
        if shadow is None and (c.shadow_action, c.shadow_quantity, c.gate_reason, c.risk_override) != (
                'HOLD', 0, 'FAILED_OBSERVATION_NO_ACTION', False):
            raise ShadowInputError('FAILED_SAVED_OBSERVATION_ACTION')


def validate_saved_shadow_result(result, proof_catalog=None):
    """Return a verified projection or UNKNOWN; forged/invalid facts raise safely.

    No proof is inferred from embedded self-consistent hashes. The explicit catalog
    must register the original observer inventory and original action projections.
    """
    try:
        with localcontext() as context:
            context.prec = 28
            return _validate_saved_shadow_result(result, proof_catalog)
    except ShadowInputError:
        raise
    except (ValueError, TypeError, KeyError, AttributeError, ArithmeticError, RecursionError):
        raise ShadowInputError('INVALID_SAVED_SHADOW_EVIDENCE') from None


def _validate_saved_shadow_result(result, proof_catalog):
    result = ShadowRunResult.model_validate(result.model_dump() if isinstance(result, ShadowRunResult) else result)
    if len(canonical_json(result).encode()) > DOCUMENT_LIMIT:
        raise ShadowInputError('RESULT_TOO_LARGE')
    m = result.manifest
    baseline = BacktestResult.model_validate(strict_json(m.baseline_document_json))
    if build_backtest_result(baseline.run) != baseline:
        raise ShadowInputError('INVALID_CANONICAL_BASELINE')
    bundle = BacktestBundle.model_validate(strict_json(m.bundle_document_json))
    if content_hash(bundle) != baseline.run.manifest['input_hash'] or m.source_hashes != bundle.sources.source_hashes:
        raise ShadowInputError('SAVED_BASELINE_SOURCE_LINK_MISMATCH')
    events = strict_json(result.events_document_json)
    if not isinstance(events, list):
        raise ShadowInputError('INVALID_SAVED_JOURNAL')
    attempts = validate_events(m, result.run_id, events)
    expected = tuple(a['observation'] for a in attempts.values() if a['observation'] is not None)
    if any(a['observation'] is None for a in attempts.values()) or expected != result.observations:
        raise ShadowInputError('RESULT_JOURNAL_CARDINALITY_MISMATCH')
    metrics = strict_json(result.metrics_document_json)
    if not isinstance(metrics, dict):
        raise ShadowInputError('INVALID_SAVED_METRICS')
    # Fold journal-only facts even when provenance is unavailable: a tampered
    # denominator/cost does not get excused by the UNKNOWN outcome.
    recorded = tuple(ShadowComparison.model_validate(c) for c in metrics.get('comparisons', ()))
    _verify_comparisons(m, result.observations, recorded)
    derived = saved_metrics(m, result.observations, attempts, recorded)
    if canonical_json(derived) != result.metrics_document_json:
        raise ShadowInputError('RESULT_METRICS_OR_HASH_MISMATCH')
    if any(a['charge']['breach'] for a in attempts.values()) and result.status != 'ACCOUNTING_BREACH':
        raise ShadowInputError('INVALID_BREACH_STATUS')
    if result.status == 'COMPLETE' and (derived['not_dispatched'] or not m.snapshots
            or any(o.status == 'TIMEOUT_UNKNOWN' for o in result.observations)):
        raise ShadowInputError('FALSE_COMPLETE_STATUS')
    entry = proof_catalog.resolve(m.spec_id, result.run_id) if proof_catalog is not None else None
    if entry is None:
        return SavedShadowUnavailable(('UNIT_INVENTORY', 'PRE_DECISION_FACTS', 'RECORDED_ACTIONS'),
            spec_id=m.spec_id, run_id=result.run_id)
    document = strict_json(entry.document_json)
    if shadow_content_hash(document) != entry.expected_hash:
        raise ShadowInputError('REGISTERED_PROOF_HASH_MISMATCH')
    proof = SavedShadowProof.model_validate(document)
    if (proof.spec_id, proof.run_id, proof.baseline_hash, proof.bundle_hash, proof.source_hashes,
            proof.news_hash, proof.code_revision, proof.code_content_hash) != (
            m.spec_id, result.run_id, m.baseline_hash, m.bundle_hash, m.source_hashes,
            shadow_content_hash(strict_json(m.news_document_json)), m.code_revision, m.code_content_hash):
        raise ShadowInputError('REGISTERED_PROOF_LINK_MISMATCH')
    if proof.events_hash != shadow_content_hash(events) or proof.observations_hash != shadow_content_hash(
            [o.model_dump(mode='json') for o in result.observations]):
        raise ShadowInputError('REGISTERED_JOURNAL_LINK_MISMATCH')
    _verify_inventory(m, proof, bundle, baseline)
    _verify_comparisons(m, result.observations, proof.comparisons)
    if recorded != proof.comparisons:
        raise ShadowInputError('SAVED_RECORDED_ACTION_MISMATCH')
    return VerifiedSavedShadow(result, derived, proof.comparisons)


def validate_events(manifest, run_id, events):
    attempts={}; previous='0'*64
    units={s.unit_id:s for s in manifest.snapshots}; variants={v.variant_id:(v,p) for v,p in zip(manifest.variants,manifest.pricing)}
    for seq,e in enumerate(events,1):
        if set(e)!={'seq','prev','type','data','hash'} or e['seq']!=seq or e['prev']!=previous or shadow_content_hash({k:v for k,v in e.items() if k!='hash'})!=e['hash']:
            raise ShadowInputError('JOURNAL_CHAIN_MISMATCH')
        previous=e['hash']; d=e['data']
        if e['type']=='DISPATCH_STARTED':
            if set(d)!={'attempt_id','unit_id','variant_id','repetition','retry_of','snapshot_id','charge'} or d['attempt_id'] in attempts or d['unit_id'] not in units or d['variant_id'] not in variants or type(d['repetition']) is not int or not 0<=d['repetition']<manifest.limits.repetitions or d['snapshot_id']!=units[d['unit_id']].snapshot_id:
                raise ShadowInputError('INVALID_DISPATCH_IDENTITY')
            if not units[d['unit_id']].eligible: raise ShadowInputError('INELIGIBLE_DISPATCH')
            logical=(d['unit_id'],d['variant_id'],d['repetition'])
            prior=d['retry_of']
            if prior:
                if prior not in attempts or attempts[prior].get('observation') is None or attempts[prior]['observation'].status=='SUCCESS' or logical!=tuple(attempts[prior][k] for k in ('unit_id','variant_id','repetition')): raise ShadowInputError('INVALID_RETRY_LINK')
            elif any(logical==tuple(a[k] for k in ('unit_id','variant_id','repetition')) for a in attempts.values()): raise ShadowInputError('DUPLICATE_LOGICAL_DISPATCH')
            v,p=variants[d['variant_id']];bound=reserve_bound(p,v.max_output_tokens)
            expected={'charged_tokens':bound.tokens,'charged_cost_usd':str(bound.cost_usd),'retained_reservation':True,'breach':False}
            if d['charge']!=expected: raise ShadowInputError('INVALID_RESERVATION')
            ShadowBudget(manifest.limits,[a['charge'] for a in attempts.values()]).reserve_attempt_group([(p,v.max_output_tokens)])
            attempts[d['attempt_id']]={**d,'observation':None}
        elif e['type']=='OBSERVATION':
            if set(d)!={'observation','charge'}: raise ShadowInputError('INVALID_OBSERVATION_EVENT')
            o=ShadowObservation.model_validate(d['observation']);a=attempts.get(o.attempt_id)
            if a is None or a['observation'] is not None or o.spec_id!=manifest.spec_id or o.run_id!=run_id or any(getattr(o,k)!=a[k] for k in ('unit_id','variant_id','snapshot_id','repetition','retry_of')): raise ShadowInputError('INVALID_OBSERVATION_TRANSITION')
            v,p=variants[a['variant_id']]
            if o.provider!=v.provider or o.requested_model!=v.model or o.status in ('EXCLUDED','NOT_DISPATCHED'): raise ShadowInputError('INVALID_PROVIDER_ATTRIBUTION')
            charge=settle_attempt_usage(p,v.max_output_tokens,o)
            if charge!=d['charge']: raise ShadowInputError('INVALID_SETTLEMENT')
            a['observation']=o;a['charge']=charge
        else: raise ShadowInputError('UNKNOWN_JOURNAL_EVENT')
    return attempts


def _stratum(s):
    try: action=strict_trade_signal(s.fixture_raw).decision.value
    except ValueError: action='INVALID'
    return f'{s.session.year}-{(s.session.month-1)//3+1}/{action}/{"HELD" if s.held else "SCREENED"}/{"RISK" if s.baseline_risk_override else "NORMAL"}'


def select_shadow_sample(snapshots, limit=100, seed='shadow-v1'):
    # Period -> signal/provenance/risk -> ticker -> date units. Each layer rotates.
    groups={}
    for s in snapshots:
        if not s.eligible:continue
        label=_stratum(s);period,category=label.split('/',1)
        groups.setdefault(period,{}).setdefault(category,{}).setdefault(s.ticker,[]).append(s)
    rank=lambda text:hashlib.sha256((seed+text).encode()).hexdigest()
    periods=[]
    for period,categories in sorted(groups.items(),key=lambda item:rank(item[0])):
        queue=[]
        for category,tickers in sorted(categories.items()):
            bucket=[]
            for ticker,units in sorted(tickers.items(),key=lambda item:rank(item[0])):
                bucket.append(sorted(units,key=lambda s:rank(s.unit_id)))
            queue.append(bucket)
        periods.append(queue)
    selected=[]
    while periods and len(selected)<limit:
        period=periods.pop(0);category=period.pop(0);ticker=category.pop(0)
        selected.append(ticker.pop(0))
        if ticker:category.append(ticker)
        if category:period.append(category)
        if period:periods.append(period)
    return tuple(sorted(selected,key=lambda s:(s.session,s.ticker)))


def _coverage(snapshots, selected, baseline):
    strata={}
    for s in selected: strata[_stratum(s)]=strata.get(_stratum(s),0)+1
    decisions=set(k.split('/')[1] for k in strata)
    coverage={'observed_units':len(snapshots),'eligible_units':sum(s.eligible for s in snapshots),'selected_units':len(selected),'excluded_units':sum(not s.eligible for s in snapshots),'exclusions':sorted({r for s in snapshots for r in s.exclusions}),'strata':strata,'missing_decision_strata':sorted({'BUY','HOLD','SELL'}-decisions),'missing_news_units':sum(not s.news_available for s in selected),'missing_position_strata':sorted({'HELD','SCREENED'}-{k.split('/')[2] for k in strata}),'missing_risk_strata':sorted({'NORMAL','RISK'}-{k.split('/')[3] for k in strata}),'missing_period_buckets':sorted({str(s.session.year)+'-'+str((s.session.month-1)//3+1) for s in snapshots}-{k.split('/')[0] for k in strata}),'baseline_limitations':list(baseline.run.limitations),'limitations':['CURRENT_MODEL_HINDSIGHT_CONTAMINATION','AGREEMENT_IS_NOT_QUALITY','CANONICAL_SIMULATED_STATE_NOT_ALTERNATIVE_PORTFOLIO']}
    return coverage

def saved_metrics(manifest,observations,attempts,recorded_comparisons):
    units={s.unit_id:s for s in manifest.snapshots}; comparisons=[];latest={}
    for o,c in zip(observations,recorded_comparisons):
        comparisons.append(c.model_dump(mode='json'))
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
        variants.append({'variant_id':v.variant_id,'provider':v.provider,'requested_model':v.model,'returned_models':sorted({o.returned_model for o in obs if o.returned_model}),'unknown_returned_model_attempts':sum(o.returned_model is None for o in obs),'requested':requested,'eligible':eligible,'excluded':requested-eligible,'not_dispatched':eligible-logical,'attempted':len(obs),'finalized':len(obs),'retry_attempts':sum(o.retry_of is not None for o in obs),'unknown_outcome':counts.get('TIMEOUT_UNKNOWN',0),'outcomes':counts,'valid_pairs':len(valid),'agreement_numerator':sum(c.raw_agreement for o,c in valid),'agreement_denominator':len(valid),'matrix':dict(sorted(matrix.items())),'failure_numerator':sum(o.status!='SUCCESS' for o in obs),'failure_denominator':len(obs),'confidence_mean_delta':sum(c.confidence_delta for o,c in valid)/len(valid) if valid else None,'action_changes':sum(c.shadow_action!=c.baseline_action for o,c in paired),'quantity_changes':sum(c.shadow_quantity!=c.baseline_quantity for o,c in paired),'risk_changes':sum(c.risk_override!=c.baseline_risk_override for o,c in paired),'rare_baseline_risk_pairs':sum(c.baseline_risk_override for o,c in valid),'known_actual_tokens':sum(o.usage.total_tokens for o in known),'unknown_usage_attempts':len(obs)-len(known),'estimated_known_subtotal_usd':str(sum(estimated,Decimal(0))),'estimated_cost_usd':str(sum(estimated,Decimal(0))) if len(estimated)==len(obs) and obs else None,'charged_tokens':sum(c['charged_tokens'] for c in charges),'consumed_plus_retained_usd':str(sum((Decimal(c['charged_cost_usd']) for c in charges),Decimal(0))),'retained_reservations':sum(c['retained_reservation'] for c in charges),'actual_billed_cost':str(sum((o.usage.billed_cost for o in obs),Decimal(0))) if obs and all(o.usage.billed_cost is not None and o.usage.billed_currency==obs[0].usage.billed_currency for o in obs) else None,'actual_billed_currency':obs[0].usage.billed_currency if obs and all(o.usage.billed_cost is not None and o.usage.billed_currency==obs[0].usage.billed_currency for o in obs) else None,'native_estimates':[{'amount':c.get('estimated_cost_native'),'currency':c.get('pricing_currency'),'usd_per_native':c.get('usd_per_native')} for c in charges],'bill_facts':[{'amount':str(o.usage.billed_cost),'currency':o.usage.billed_currency,'reference':o.usage.billing_reference} for o in obs if o.usage.billed_cost is not None],'judgment':'NO_MEANINGFUL_DIFFERENCE' if len(valid)==eligible and eligible>0 and all(c.exact_equal for o,c in valid) else 'INSUFFICIENT_EVIDENCE'})
    return {'variants':variants,'comparisons':comparisons,'attempted':len(observations),'requested':sum(v['requested'] for v in variants),'not_dispatched':sum(v['not_dispatched'] for v in variants),'valid_pairs':sum(v['valid_pairs'] for v in variants),'coverage':strict_json(manifest.coverage_json),'judgment_rule':'Exact signal including confidence/reason and projected action/quantity/risk equality for every eligible paired observation; consistency only.','promotion_authority':False,'alternative_portfolio_pnl':None}
