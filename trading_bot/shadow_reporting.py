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


def _checked_result(result):
    from .shadow_runner import ShadowExecution
    checked=build_shadow_result(ShadowExecution(result.manifest,result.run_id,result.status,result.observations,tuple(strict_json(result.events_document_json))))
    if checked!=result:raise ShadowInputError('RESULT_METRICS_OR_HASH_MISMATCH')
    return checked


def load_shadow_result(path):
    try:return _checked_result(ShadowRunResult.model_validate(read_shadow_json(path)))
    except ShadowInputError:raise
    except (ValueError,TypeError,KeyError):raise ShadowInputError('INVALID_SHADOW_RESULT') from None


def write_shadow_result(result,output):
    _checked_result(result)
    payload=(canonical_json(result)+'\n').encode('utf-8')
    if len(payload)>DOCUMENT_LIMIT:raise ShadowInputError('RESULT_TOO_LARGE')
    return _write_evidence_bytes(payload,output)


def write_shadow_report(text,output):
    return _write_evidence_bytes((_safe_text(text).rstrip()+'\n').encode('utf-8'),output)


def _safe_text(text):
    import re
    text=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',text)
    return ''.join(c for c in text if c in '\n\t' or ord(c)>=32 and ord(c)!=127 and not '\u0080'<=c<='\u009f')


def render_shadow_report(result):
    _checked_result(result);m=strict_json(result.metrics_document_json);coverage=m['coverage']
    lines=['# 과거 LLM Shadow 비교 보고서','',f'상태: {result.status}',f'실행: {result.run_id}',f'명세: {result.manifest.spec_id}',f'기준 결과: {result.manifest.baseline_hash}',f'코드: {result.manifest.code_revision} / {result.manifest.code_content_hash}','',f'요청 {m["requested"]}, 호출 의도/완료 관측 {m["attempted"]}, 미호출 {m["not_dispatched"]}, 유효 비교 쌍 {m["valid_pairs"]}.','', '비교 입력은 기준 포트폴리오의 의사결정 직전 모의 상태입니다. 다른 전략의 후속 보유 수량이나 수익률을 계산하지 않습니다.', '일치율은 일관성 지표이며 정확도·수익성·신뢰도 보정·운영 준비 상태를 증명하지 않습니다.', '현재 모델이 과거 이후 정보를 학습했을 수 있습니다 (CURRENT_MODEL_HINDSIGHT_CONTAMINATION). 시간 제한 입력만으로 이 오염을 제거할 수 없습니다.', '모델·프롬프트·정책 채택은 별도 수동 결정입니다. 자동 승자 선정이나 실거래 승격 권한은 없습니다. Phase 9/10/11 운영 게이트가 계속 적용됩니다.','',f'관측/적격/선택/제외: {coverage.get("observed_units","UNKNOWN")} / {coverage.get("eligible_units","UNKNOWN")} / {coverage.get("selected_units","UNKNOWN")} / {coverage.get("excluded_units","UNKNOWN")}',f'뉴스 부재: {coverage.get("missing_news_units","UNKNOWN")}',f'빠진 결정 층: {canonical_json(coverage.get("missing_decision_strata",[]))}',f'층별 표본: {canonical_json(coverage.get("strata",{}))}',f'제외 사유: {canonical_json(coverage.get("exclusions",[]))}',f'기준 데이터·워밍업 한계: {canonical_json(coverage.get("baseline_limitations",[]))}','']
    for v in m['variants']:
        lines.extend([f'## {v["provider"]} / {v["requested_model"]}',f'변형: {v["variant_id"]}',f'반환 모델: {", ".join(v["returned_models"]) or "UNKNOWN"}; 알 수 없음 {v["unknown_returned_model_attempts"]}회',f'요청 {v["requested"]}, 적격 {v["eligible"]}, 제외 {v["excluded"]}, 미호출 {v["not_dispatched"]}, 호출 의도 {v["attempted"]}, 명시적 재시도 {v["retry_attempts"]}',f'원시 결정 일치: {v["agreement_numerator"]}/{v["agreement_denominator"]} (유효 쌍 기준)',f'실패: {v["failure_numerator"]}/{v["failure_denominator"]} (호출 의도 기준); 결과 {canonical_json(v["outcomes"])}',f'결정 행렬: {canonical_json(v["matrix"])}',f'신뢰도 평균 차이: {v["confidence_mean_delta"] if v["confidence_mean_delta"] is not None else "UNKNOWN"}; 가상 행동/수량/위험 변경 {v["action_changes"]}/{v["quantity_changes"]}/{v["risk_changes"]}',f'실제 보고된 토큰: 알려진 부분 {v["known_actual_tokens"]}; 사용량 UNKNOWN {v["unknown_usage_attempts"]}회',f'요금표 추정 비용 (ESTIMATED): {v["estimated_cost_usd"] if v["estimated_cost_usd"] is not None else "UNKNOWN"} USD; 알려진 부분 {v["estimated_known_subtotal_usd"]} USD',f'소비+유지 예약: {v["consumed_plus_retained_usd"]} USD / {v["charged_tokens"]} 토큰; 유지 예약 {v["retained_reservations"]}회','실제 청구 합계: UNKNOWN (요금표 추정은 청구서 증거가 아닙니다)',f'개별 청구 근거: {canonical_json(v["bill_facts"])}',f'판정: {v["judgment"]}',''])
    lines.extend(['동일성 판정은 모든 적격 비교의 신호(이유·신뢰도 포함)와 가상 행동·수량·위험 결과가 정확히 같은 경우에만 NO_MEANINGFUL_DIFFERENCE입니다. 그 외에는 INSUFFICIENT_EVIDENCE입니다.','저장된 임의 응답을 근거로 보고서를 재생성합니다. 모델을 다시 호출해 같은 답을 보장하지 않습니다.'])
    return _safe_text('\n'.join(lines)+'\n')
