"""Canonical saved simulation evidence, ledger revalidation and Korean reports."""
from __future__ import annotations

import os
import tempfile
from collections import Counter
from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path
from typing import Literal

from pydantic import Field, StrictInt, ValidationError

from .backtest_costs import calculate_fill_costs, cost_profile, effective_rule
from .backtest_engine import BacktestRun
from .backtest_fills import opening_cutoff
from .backtest_inputs import read_json_document
from .backtest_ledger import PortfolioLedger
from .backtest_models import Amount, BacktestInputError, BacktestPolicy, CoverageStatus, Frozen, canonical_bytes, content_hash

ZERO = Decimal('0')


class BacktestMetrics(Frozen):
    net_return: Amount | None
    gross_return: Amount | None
    max_drawdown: Amount | None
    gross_max_drawdown: Amount | None
    exposure: tuple[Amount | None, ...]
    turnover: Amount | None
    realized_pnl: Amount
    unrealized_pnl: Amount | None
    commission: Amount
    sell_tax: Amount
    surtax: Amount
    slippage_drag: Amount
    fill_count: StrictInt
    partial_count: StrictInt
    nonfill_count: StrictInt
    expired_quantity: StrictInt
    benchmark_return: Amount | None
    decision_reasons: dict[str, StrictInt]
    nonfill_reasons: dict[str, StrictInt]


class BacktestResult(Frozen):
    schema_version: Literal[1]
    result_id: str = Field(pattern=r'^[0-9a-f]{64}$')
    run: BacktestRun
    metrics: BacktestMetrics

    def identity_document(self):
        return {'schema_version':self.schema_version,'run':self.run.model_dump(mode='json'),'metrics':self.metrics.model_dump(mode='json')}


def _exact_keys(value, expected):
    if not isinstance(value, dict) or set(value) != set(expected):
        raise BacktestInputError('INVALID_EVIDENCE_FIELDS')


def _validate_run(run: BacktestRun):
    m = run.manifest
    _exact_keys(m,('schema_version','input_hash','code_identity','window','policy','profile','fill_version','settlement_version','source_hashes','market_rule_ids','scenario_group'))
    _exact_keys(m['window'],('requested_start','requested_end','actual_start','actual_end','warmup_sessions','coverage_status','reasons'))
    _exact_keys(m['profile'],('name','version','commission_bps','slippage_bps','participation','rounding','assumption'))
    policy = BacktestPolicy.model_validate(m['policy'])
    if policy.model_dump(mode='json') != m['policy'] or m['profile'] != cost_profile(m['profile']['name']).document():
        raise BacktestInputError('INVALID_EVIDENCE_POLICY')
    from .backtest_fills import FILL_VERSION
    from .backtest_ledger import SETTLEMENT_VERSION
    if m['schema_version'] != 1 or m['fill_version'] != FILL_VERSION or m['settlement_version'] != SETTLEMENT_VERSION:
        raise BacktestInputError('UNSUPPORTED_EVIDENCE_VERSION')
    import re
    if any(not isinstance(m[k],str) or re.fullmatch(r'[0-9a-f]{64}',m[k]) is None for k in ('input_hash','code_identity','scenario_group')):
        raise BacktestInputError('INVALID_EVIDENCE_IDENTITY')
    if content_hash({'input':m['input_hash'],'window':m['window'],'code':m['code_identity']}) != m['scenario_group']:
        raise BacktestInputError('INVALID_SCENARIO_LINK')
    if not m['source_hashes'] or any(not isinstance(h,str) or re.fullmatch(r'[0-9a-f]{64}',h) is None for h in m['source_hashes']):
        raise BacktestInputError('INVALID_SOURCE_HASHES')
    if len(run.sessions)>20000 or len(run.fills)>250000 or len(run.decisions)>250000 or len(run.intents)>250000:
        raise BacktestInputError('EXCESS_EVIDENCE_ROWS')
    calendar = tuple(s.session for s in run.calendar if s.completed)
    if calendar != tuple(sorted(set(calendar))) or not calendar:
        raise BacktestInputError('INVALID_EVIDENCE_CALENDAR')
    start = date.fromisoformat(m['window']['requested_start']); end = date.fromisoformat(m['window']['requested_end'])
    if start > end or tuple(s.session for s in run.sessions) != tuple(s for s in calendar if start<=s<=end):
        raise BacktestInputError('INVALID_EVIDENCE_SESSIONS')
    if (run.sessions[0].session.isoformat() if run.sessions else None) != m['window']['actual_start'] or (run.sessions[-1].session.isoformat() if run.sessions else None) != m['window']['actual_end']:
        raise BacktestInputError('INVALID_COVERAGE_RANGE')
    if len(set(i.intent_id for i in run.intents)) != len(run.intents):
        raise BacktestInputError('DUPLICATE_EVIDENCE_INTENT')
    ledger = PortfolioLedger(policy,calendar); profile = cost_profile(m['profile']['name'])
    intent_map = {i.intent_id:i for i in run.intents}
    linked = set()
    for sequence,d in enumerate(run.decisions):
        if d.intent_id:
            if d.intent_id not in intent_map or d.intent_id in linked:
                raise BacktestInputError('INVALID_DECISION_LINK')
            i = intent_map[d.intent_id]
            expected_id = content_hash({'session':d.session.isoformat(),'ticker':d.ticker,'side':d.action,'sequence':sequence,'policy':policy.version})
            if i.intent_id != expected_id or (i.ticker,i.decision_session,i.side,i.quantity) != (d.ticker,d.session,d.action,d.quantity):
                raise BacktestInputError('INVALID_INTENT_DECISION')
            linked.add(i.intent_id)
    if linked != set(intent_map):
        raise BacktestInputError('UNLINKED_INTENT')
    observed_fills = []; expected_expiry = []; expected_cash_events = []
    for s in run.sessions:
        ledger.start_session(s.session)
        for action in sorted(run.corporate_actions,key=lambda a:(a.effective,{'SPLIT':0,'DIVIDEND':1,'DELIST':2}[a.kind],a.action_id)):
            old_action=ledger.action_cash;old_flow=ledger.cash_flow
            ledger.apply_corporate_action(action,s.session,opening_cutoff(s.session))
            if ledger.action_cash != old_action or ledger.cash_flow != old_flow:
                expected_cash_events.append({'action_id':action.action_id,'session':s.session.isoformat(),'kind':action.kind,'cash_delta':str(ledger.action_cash-old_action),'liquidation_delta':str(ledger.cash_flow-old_flow)})
        eligible = {i.intent_id for i in ledger.intents.values() if i.eligible_session <= s.session}
        supplied = [f for f in run.fills if f.session == s.session]
        if {f.intent_id for f in supplied} != eligible or len(supplied) != len(eligible):
            raise BacktestInputError('INVALID_FILL_COVERAGE')
        for f in supplied:
            if len(f.rule_ids)!=2:
                raise BacktestInputError('INVALID_FILL_RULES')
            tax = next((r for r in run.cost_rules if r.rule_id==f.rule_ids[0]),None)
            tick = next((r for r in run.tick_rules if r.rule_id==f.rule_ids[1]),None)
            if tax is None or tick is None or tax.market != tick.market:
                raise BacktestInputError('UNKNOWN_FILL_RULE')
            effective_rule(run.cost_rules,tax.market,f.session,opening_cutoff(f.session))
            effective_rule(run.tick_rules,tick.market,f.session,opening_cutoff(f.session))
            costs = calculate_fill_costs(f.side,f.quantity,f.executed_price,profile,tax)
            if (costs.commission,costs.sell_tax,costs.surtax) != (f.commission,f.sell_tax,f.surtax):
                raise BacktestInputError('INVALID_FILL_COSTS')
            if abs(f.executed_price-f.reference_price)*f.quantity != f.slippage_drag:
                raise BacktestInputError('INVALID_SLIPPAGE_ATTRIBUTION')
            ledger.apply_fill(f);observed_fills.append(f)
            remaining=ledger.expire(f.intent_id)
            expected_expiry.append({'intent_id':f.intent_id,'session':f.session.isoformat(),'remaining_quantity':remaining,'reason':'END_SESSION_EXPIRED' if remaining else 'FULLY_FILLED'})
        for intent in run.intents:
            if intent.decision_session == s.session:
                if ledger.reserve(intent,profile) != intent:
                    raise BacktestInputError('INVALID_INTENT_RESERVATION')
        prices={h.ticker:h.mark_price for h in s.holdings if h.mark_price is not None}
        holdings,equity,unrealized=ledger.snapshot(prices)
        if ledger.unknowns and any('ACTION_TERMS' in u for u in ledger.unknowns):
            equity=None;unrealized=None
        if (holdings,equity,unrealized,ledger.settled_cash,ledger.reserved_cash,ledger.pending_cash,ledger.realized_pnl,ledger.action_cash) != (s.holdings,s.net_equity,s.unrealized_pnl,s.settled_cash,s.reserved_cash,s.pending_cash,s.realized_pnl,s.action_cash):
            raise BacktestInputError('UNRECONCILED_PORTFOLIO_EVIDENCE')
        if s.gross_equity != (equity+ledger.cost_drag if equity is not None else None):
            raise BacktestInputError('UNRECONCILED_GROSS_EQUITY')
        if s.coverage_status == CoverageStatus.COMPLETE and (s.unknowns or equity is None or m['window']['reasons']):
            raise BacktestInputError('INVALID_COMPLETE_VERDICT')
    if tuple(observed_fills)!=run.fills or tuple(expected_expiry)!=run.expiries or tuple(expected_cash_events)!=run.cash_events or tuple(ledger.intents.values())!=run.open_intents:
        raise BacktestInputError('INVALID_TERMINAL_EVIDENCE')
    if run.final_coverage == CoverageStatus.COMPLETE and (m['window']['coverage_status']!='COMPLETE' or any(s.coverage_status!=CoverageStatus.COMPLETE for s in run.sessions) or any(r.synthetic for r in (*run.cost_rules,*run.tick_rules))):
        raise BacktestInputError('INVALID_COMPLETE_VERDICT')
    if 'SIMULATED_NOT_PROMOTION_AUTHORITY' not in run.limitations:
        raise BacktestInputError('MISSING_SIMULATION_LIMITATION')


def _drawdown(values,initial):
    if initial is None or initial <= 0 or not values or any(v is None for v in values):
        return None
    peak=initial;worst=ZERO
    for v in values:
        peak=max(peak,v)
        worst=max(worst,(peak-v)/peak)
    return worst


def calculate_metrics(run: BacktestRun) -> BacktestMetrics:
    """Turnover=traded notional/mean daily net equity; exposure=holdings/net equity."""
    with localcontext() as context:
        context.prec=28
        net=[s.net_equity for s in run.sessions];gross=[s.gross_equity for s in run.sessions]
        valid=bool(net) and all(v is not None and v>0 for v in net) and run.initial_equity is not None and run.initial_equity>0
        exposure=tuple(sum((h.quantity*h.mark_price for h in s.holdings),ZERO)/s.net_equity if s.net_equity is not None and s.net_equity>0 and all(h.mark_price is not None for h in s.holdings) else None for s in run.sessions)
        notional=sum((f.quantity*f.executed_price for f in run.fills),ZERO)
        benchmark=None
        if run.sessions and tuple(b.session for b in run.benchmark)==tuple(s.session for s in run.sessions):
            benchmark=run.benchmark[-1].close/run.benchmark[0].close-1
        return BacktestMetrics(net_return=net[-1]/run.initial_equity-1 if valid else None,gross_return=gross[-1]/run.initial_equity-1 if valid else None,max_drawdown=_drawdown(net,run.initial_equity),gross_max_drawdown=_drawdown(gross,run.initial_equity),exposure=exposure,turnover=notional/(sum(net,ZERO)/len(net)) if valid else None,realized_pnl=run.sessions[-1].realized_pnl if run.sessions else ZERO,unrealized_pnl=run.sessions[-1].unrealized_pnl if run.sessions else None,commission=sum((f.commission for f in run.fills),ZERO),sell_tax=sum((f.sell_tax for f in run.fills),ZERO),surtax=sum((f.surtax for f in run.fills),ZERO),slippage_drag=sum((f.slippage_drag for f in run.fills),ZERO),fill_count=sum(f.quantity>0 for f in run.fills),partial_count=sum(f.reason=='PARTIAL' for f in run.fills),nonfill_count=sum(f.quantity==0 for f in run.fills),expired_quantity=sum(e['remaining_quantity'] for e in run.expiries),benchmark_return=benchmark,decision_reasons=dict(sorted(Counter(d.reason for d in run.decisions).items())),nonfill_reasons=dict(sorted(Counter(f.reason for f in run.fills if not f.quantity).items())))


def build_backtest_result(run: BacktestRun) -> BacktestResult:
    with localcontext() as context:
        context.prec=28
        _validate_run(run)
        metrics=calculate_metrics(run)
        payload={'schema_version':1,'run':run.model_dump(mode='json'),'metrics':metrics.model_dump(mode='json')}
        return BacktestResult(schema_version=1,result_id=content_hash(payload),run=run,metrics=metrics)


def load_backtest_result(path: str | Path) -> BacktestResult:
    try:
        result=BacktestResult.model_validate(read_json_document(path))
        checked=build_backtest_result(result.run)
        if checked != result:
            raise BacktestInputError('EVIDENCE_HASH_OR_METRICS_MISMATCH')
        return result
    except BacktestInputError:
        raise
    except (ValueError,ValidationError,TypeError,KeyError,StopIteration) as exc:
        raise BacktestInputError('INVALID_BACKTEST_EVIDENCE') from exc


def write_backtest_result(result: BacktestResult, output: str | Path) -> Path:
    """No-overwrite atomic publish; another writer cannot replace conflicting bytes."""
    from .report_cli import _validated_output_parent
    if build_backtest_result(result.run) != result:
        raise BacktestInputError('INVALID_RESULT_FOR_OUTPUT')
    try:
        root,target=_validated_output_parent(Path(output))
        if target.is_symlink():
            raise BacktestInputError('UNSAFE_OUTPUT')
        payload=canonical_bytes(result)+b'\n'
        if target.exists():
            if not target.is_file() or target.read_bytes()!=payload:
                raise BacktestInputError('OUTPUT_CONFLICT')
            return target
        temporary=None
        try:
            with tempfile.NamedTemporaryFile(dir=root,prefix='.backtest-',delete=False) as handle:
                temporary=Path(handle.name);handle.write(payload);handle.flush();os.fsync(handle.fileno())
            try:
                os.link(temporary,target)
            except FileExistsError:
                if target.is_symlink() or not target.is_file() or target.read_bytes()!=payload:
                    raise BacktestInputError('OUTPUT_CONFLICT')
        finally:
            if temporary:temporary.unlink(missing_ok=True)
        return target
    except BacktestInputError:
        raise
    except (OSError,ValueError) as exc:
        raise BacktestInputError('INVALID_OUTPUT_PATH') from exc


def render_backtest_report(result: BacktestResult) -> str:
    """One deterministic Korean report with explicit modeled-data limitations."""
    if build_backtest_result(result.run) != result:
        raise BacktestInputError('INVALID_REPORT_EVIDENCE')
    run=result.run;metrics=result.metrics;window=run.manifest['window'];profile=run.manifest['profile']
    def value(number, percent=False):
        if number is None:return '자료 부족으로 산출 불가'
        if percent:return f'{number*100:.4f}%'
        return f'{number:.4f}'
    lines=['포트폴리오 백테스트 보고서 — 모의 계산',f'결과 ID: {result.result_id}',f'시나리오 그룹: {run.manifest["scenario_group"]}',
           f'프로필: {profile["name"]} / 비용 버전: {profile["version"]}',
           f'요청 기간: {window["requested_start"]} ~ {window["requested_end"]}',
           f'실제 계산 기간: {window["actual_start"]} ~ {window["actual_end"]}',
           f'워밍업 거래일: {window["warmup_sessions"]}',
           f'자료 충족 상태: {"완전" if run.final_coverage==CoverageStatus.COMPLETE else "불완전"}',
           f'수수료 가정: 양방향 {profile["commission_bps"]} bps / 슬리피지: {profile["slippage_bps"]} bps',
           f'거래량 참여 한도: {profile["participation"]} / 반올림: {profile["rounding"]}',
           f'결제 가정: {run.manifest["settlement_version"]}',
           f'순수익률(net): {value(metrics.net_return,True)}',f'비용 전 귀속 수익률(gross): {value(metrics.gross_return,True)}',
           f'최대 낙폭(net): {value(metrics.max_drawdown,True)} / gross: {value(metrics.gross_max_drawdown,True)}',
           f'회전율: {value(metrics.turnover)}',f'실현 손익: {value(metrics.realized_pnl)} KRW / 미실현 손익: {value(metrics.unrealized_pnl)} KRW',
           f'체결: {metrics.fill_count} / 부분 체결: {metrics.partial_count} / 미체결: {metrics.nonfill_count} / 만료 수량: {metrics.expired_quantity}',
           f'수수료: {value(metrics.commission)} / 매도 거래세: {value(metrics.sell_tax)} / 부가세목: {value(metrics.surtax)} / 슬리피지 귀속: {value(metrics.slippage_drag)} KRW',
           f'비교 지수 매수 후 보유 수익률: {value(metrics.benchmark_return,True)}',
           '일별 자산 및 노출:']
    for s,exposure in zip(run.sessions,metrics.exposure):
        lines.append(f'{s.session} | net {value(s.net_equity)} | gross {value(s.gross_equity)} | 노출 {value(exposure,True)} | 정산 현금 {value(s.settled_cash)} | 예약 {value(s.reserved_cash)} | 결제 대기 {value(s.pending_cash)}')
    lines.extend(['의사결정·제외 사유:']+[f'{reason}: {count}' for reason,count in metrics.decision_reasons.items()])
    lines.extend(['미체결 사유:']+[f'{reason}: {count}' for reason,count in metrics.nonfill_reasons.items()])
    lines.extend(['한계 및 자료 누락:','모델 결과이며 수익 보장이나 실거래 승인이 아닙니다.',
                  '일봉 종가 판단·다음 거래일 시가 체결 가정입니다. 장중 경로·호가 대기열은 재현하지 않습니다.',
                  'gross는 net과 같은 체결 수량·시점에서 비용과 가격 마찰을 되돌린 귀속값입니다.',
                  '수수료·슬리피지는 모델 가정이며 실제 계좌 요금이 아닙니다. 거래세·호가는 날짜별 입력 규칙을 사용합니다.',
                  '매도대금은 KRX 거래일 T+2에 가용합니다. 실제 증권사 주문 가능 금액과 다를 수 있습니다.',
                  '누락 평가액은 0으로 대체하지 않습니다. 비교 지수가 없으면 산출하지 않습니다.'])
    if 'FIXED_UNIVERSE_SURVIVORSHIP' in run.limitations:
        lines.append('고정 종목 목록은 생존 편향이 있으며 시장 전체의 과거 구성 검증이 아닙니다.')
    lines.extend('- '+limitation for limitation in run.limitations)
    return '\n'.join(lines)+'\n'
