"""Deterministic descriptive comparison; no model/policy promotion authority."""
from __future__ import annotations
import os
import tempfile
from decimal import Decimal
from .shadow_models import *
from .shadow_evidence import (
    ShadowExecution, ShadowComparison, SavedShadowProof, RegisteredShadowProof,
    SavedShadowProofCatalog, SavedShadowUnavailable, validate_events,
    validate_saved_shadow_result, saved_metrics,
)
from .backtest_reporting import BacktestResult, build_backtest_result


def _write_evidence_bytes(payload,output):
    """Same bounded no-overwrite writer, without importing the report CLI."""
    try:
        if len(payload)>DOCUMENT_LIMIT:raise ShadowInputError('RESULT_TOO_LARGE')
        raw=Path(output)
        if raw.name in {'','.','..'} or '..' in raw.parts:
            raise ShadowInputError('INVALID_OUTPUT_PATH')
        if any(p.is_symlink() for p in (raw,*raw.parents)):
            raise ShadowInputError('UNSAFE_OUTPUT')
        raw.parent.mkdir(parents=True,exist_ok=True)
        root=raw.parent.resolve(strict=True);target=root/raw.name
        if target.is_symlink():raise ShadowInputError('UNSAFE_OUTPUT')
        if target.exists():
            if not target.is_file() or target.stat().st_size>DOCUMENT_LIMIT or target.read_bytes()!=payload:
                raise ShadowInputError('OUTPUT_CONFLICT')
            return target
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(dir=root,prefix='.shadow-',delete=False) as handle:
                temporary=Path(handle.name);handle.write(payload);handle.flush();os.fsync(handle.fileno())
            try:os.link(temporary,target)
            except FileExistsError:
                if target.is_symlink() or not target.is_file() or target.stat().st_size>DOCUMENT_LIMIT or target.read_bytes()!=payload:
                    raise ShadowInputError('OUTPUT_CONFLICT')
        finally:
            if temporary:temporary.unlink(missing_ok=True)
        return target
    except ShadowInputError:raise
    except (OSError,ValueError):raise ShadowInputError('INVALID_OUTPUT_PATH') from None

def compare_shadow_action(snapshot,observation):
    from .backtest_engine import project_backtest_action
    base=None
    try:base=strict_trade_signal(snapshot.fixture_raw)
    except ValueError:pass
    shadow=strict_trade_signal(observation.raw_output) if observation.status=='SUCCESS' else None
    proposal=project_backtest_action(snapshot,observation.raw_output) if shadow else None
    valid=base is not None and shadow is not None
    return ShadowComparison(unit_id=snapshot.unit_id,variant_id=observation.variant_id,attempt_id=observation.attempt_id,status=observation.status,valid_pair=valid,raw_agreement=base.decision==shadow.decision if valid else None,confidence_delta=shadow.confidence-base.confidence if valid else None,baseline_action=snapshot.baseline_action,shadow_action=proposal.action if proposal else 'HOLD',baseline_quantity=snapshot.baseline_quantity,shadow_quantity=proposal.quantity if proposal else 0,gate_reason=proposal.reason if proposal else 'FAILED_OBSERVATION_NO_ACTION',risk_override=proposal.risk_override if proposal else False,baseline_risk_override=snapshot.baseline_risk_override,exact_equal=bool(valid and base==shadow and (proposal.action,proposal.quantity,proposal.risk_override)==(snapshot.baseline_action,snapshot.baseline_quantity,snapshot.baseline_risk_override)))


def _metrics(manifest,observations,attempts):
    units={s.unit_id:s for s in manifest.snapshots}
    comparisons=tuple(compare_shadow_action(units[o.unit_id],o) for o in observations)
    return saved_metrics(manifest,observations,attempts,comparisons)


def build_shadow_result(execution):
    manifest=ShadowManifest.model_validate(execution.manifest.model_dump())
    from .shadow_inputs import validate_shadow_preparation
    inventory=validate_shadow_preparation(manifest,return_inventory=True)
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
    result=ShadowRunResult(stop_reason=getattr(execution,'stop_reason',None),manifest=manifest,run_id=execution.run_id,status=execution.status,observations=tuple(execution.observations),events_document_json=canonical_json(list(execution.events)),metrics_document_json=canonical_json(metrics))

    # This non-serialized creation proof is attached only after strict preparation
    # and canonical action projection. Saved JSON alone never recreates it.
    proof=SavedShadowProof(spec_id=manifest.spec_id,run_id=result.run_id,
        baseline_hash=manifest.baseline_hash,bundle_hash=manifest.bundle_hash,
        source_hashes=manifest.source_hashes,
        news_hash=shadow_content_hash(strict_json(manifest.news_document_json)),
        code_revision=manifest.code_revision,code_content_hash=manifest.code_content_hash,
        inventory=inventory,
        comparisons=tuple(ShadowComparison.model_validate(c) for c in metrics['comparisons']),
        events_hash=shadow_content_hash(strict_json(result.events_document_json)),
        observations_hash=shadow_content_hash([o.model_dump(mode='json') for o in result.observations]))
    catalog=SavedShadowProofCatalog((RegisteredShadowProof(spec_id=manifest.spec_id,
        run_id=result.run_id,expected_hash=shadow_content_hash(proof),document_json=canonical_json(proof)),))
    object.__setattr__(result,'_creation_proof_catalog',catalog)
    return result


def _checked_result(result,proof_catalog=None):
    catalog=proof_catalog if proof_catalog is not None else getattr(result,'_creation_proof_catalog',None)
    checked=validate_saved_shadow_result(result,catalog)
    if isinstance(checked,SavedShadowUnavailable):raise checked
    return checked.result


def load_shadow_result(path,*,proof_catalog=None):
    try:
        if any(p.is_symlink() for p in (Path(path),*Path(path).parents)):
            raise ShadowInputError('UNSAFE_SHADOW_RESULT_PATH')
        return _checked_result(ShadowRunResult.model_validate(read_shadow_json(path)),proof_catalog)
    except ShadowInputError:raise
    except (ValueError,TypeError,KeyError):raise ShadowInputError('INVALID_SHADOW_RESULT') from None


def write_shadow_result(result,output,*,proof_catalog=None):
    _checked_result(result,proof_catalog)
    payload=(canonical_json(result)+'\n').encode('utf-8')
    if len(payload)>DOCUMENT_LIMIT:raise ShadowInputError('RESULT_TOO_LARGE')
    return _write_evidence_bytes(payload,output)


def write_shadow_report(text,output):
    return _write_evidence_bytes((_safe_text(text).rstrip()+'\n').encode('utf-8'),output)


def _safe_text(text):
    import re
    text=re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]','',text)
    return ''.join(c for c in text if c in '\n\t' or ord(c)>=32 and ord(c)!=127 and not '\u0080'<=c<='\u009f')


def render_shadow_report(result,*,proof_catalog=None):
    _checked_result(result,proof_catalog);m=strict_json(result.metrics_document_json);coverage=m['coverage']
    lines=['# 과거 LLM Shadow 비교 보고서','',f'상태: {result.status}',f'중단 사유: {result.stop_reason or "상태 및 결과별 사유 참조"}',f'실행: {result.run_id}',f'명세: {result.manifest.spec_id}',f'연결된 이전 명세/실행: {result.manifest.parent_spec_id or "없음"} / {result.manifest.parent_run_id or "없음"}',f'기준 결과: {result.manifest.baseline_hash}',f'코드: {result.manifest.code_revision} / {result.manifest.code_content_hash}','',f'요청 {m["requested"]}, 호출 의도/완료 관측 {m["attempted"]}, 미호출 {m["not_dispatched"]}, 유효 비교 쌍 {m["valid_pairs"]}.','', '비교 입력은 기준 포트폴리오의 의사결정 직전 모의 상태입니다. 다른 전략의 후속 보유 수량이나 수익률을 계산하지 않습니다.', '일치율은 일관성 지표이며 정확도·수익성·신뢰도 보정·운영 준비 상태를 증명하지 않습니다.', '현재 모델이 과거 이후 정보를 학습했을 수 있습니다 (CURRENT_MODEL_HINDSIGHT_CONTAMINATION). 시간 제한 입력만으로 이 오염을 제거할 수 없습니다.', '모델·프롬프트·정책 채택은 별도 수동 결정입니다. 자동 승자 선정이나 실거래 승격 권한은 없습니다. Phase 9/10/11 운영 게이트가 계속 적용됩니다.','',f'관측/적격/선택/제외: {coverage.get("observed_units","UNKNOWN")} / {coverage.get("eligible_units","UNKNOWN")} / {coverage.get("selected_units","UNKNOWN")} / {coverage.get("excluded_units","UNKNOWN")}',f'뉴스 부재: {coverage.get("missing_news_units","UNKNOWN")}',f'빠진 결정 층: {canonical_json(coverage.get("missing_decision_strata",[]))}',f'층별 표본: {canonical_json(coverage.get("strata",{}))}',f'빠진 보유/위험/기간 층: {canonical_json([coverage.get("missing_position_strata",[]),coverage.get("missing_risk_strata",[]),coverage.get("missing_period_buckets",[])])}',f'제외 사유: {canonical_json(coverage.get("exclusions",[]))}',f'기준 데이터·워밍업 한계: {canonical_json(coverage.get("baseline_limitations",[]))}','']
    for v in m['variants']:
        lines.extend([f'## {v["provider"]} / {v["requested_model"]}',f'변형: {v["variant_id"]}',f'반환 모델: {", ".join(v["returned_models"]) or "UNKNOWN"}; 알 수 없음 {v["unknown_returned_model_attempts"]}회',f'요청 {v["requested"]}, 적격 {v["eligible"]}, 제외 {v["excluded"]}, 미호출 {v["not_dispatched"]}, 호출 의도 {v["attempted"]}, 명시적 재시도 {v["retry_attempts"]}',f'원시 결정 일치: {v["agreement_numerator"]}/{v["agreement_denominator"]} (유효 쌍 기준)',f'실패: {v["failure_numerator"]}/{v["failure_denominator"]} (호출 의도 기준); 결과 {canonical_json(v["outcomes"])}',f'결정 행렬: {canonical_json(v["matrix"])}',f'신뢰도 평균 차이: {v["confidence_mean_delta"] if v["confidence_mean_delta"] is not None else "UNKNOWN"}; 가상 행동/수량/위험 변경 {v["action_changes"]}/{v["quantity_changes"]}/{v["risk_changes"]}',f'실제 보고된 토큰: 알려진 부분 {v["known_actual_tokens"]}; 사용량 UNKNOWN {v["unknown_usage_attempts"]}회',f'요금표 추정 비용 (ESTIMATED): {v["estimated_cost_usd"] if v["estimated_cost_usd"] is not None else "UNKNOWN"} USD; 알려진 부분 {v["estimated_known_subtotal_usd"]} USD',f'소비+유지 예약: {v["consumed_plus_retained_usd"]} USD / {v["charged_tokens"]} 토큰; 유지 예약 {v["retained_reservations"]}회',f'실제 청구 합계: {v["actual_billed_cost"] or "UNKNOWN"} {v["actual_billed_currency"] or ""} (요금표 추정은 청구서 증거가 아닙니다)',f'원통화 추정/환율: {canonical_json(v["native_estimates"])}',f'개별 청구 근거: {canonical_json(v["bill_facts"])}',f'판정: {v["judgment"]}',''])
    lines.extend(['동일성 판정은 모든 적격 비교의 신호(이유·신뢰도 포함)와 가상 행동·수량·위험 결과가 정확히 같은 경우에만 NO_MEANINGFUL_DIFFERENCE입니다. 그 외에는 INSUFFICIENT_EVIDENCE입니다.','저장된 임의 응답을 근거로 보고서를 재생성합니다. 모델을 다시 호출해 같은 답을 보장하지 않습니다.'])
    return _safe_text('\n'.join(lines)+'\n')
