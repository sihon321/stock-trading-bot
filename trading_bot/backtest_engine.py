"""Chronological daily-close simulation using shipped pure policy gates."""
from __future__ import annotations

import hashlib
import math
from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path

import pandas as pd

from .backtest_evidence import BacktestRun, DecisionEvidence, checked_float
from .backtest_costs import cost_profile, effective_rule, round_tick
from .backtest_fills import FILL_VERSION, model_session_fills, opening_cutoff
from .backtest_inputs import decision_view, resolve_backtest_window
from .backtest_ledger import PortfolioLedger, SETTLEMENT_VERSION, project_reservation
from .backtest_models import Amount, Bar, BenchmarkPoint, CorporateAction, CostRule, TickRule, Session, BacktestBundle, BacktestInputError, CoverageStatus, FillEvidence, Frozen, OpenIntent, SessionEvidence, content_hash
from .data_models import IndicatorConfig
from .domain import Money, Position, Ticker
from .execution import ExecutionConfig, execute_signal_cycle
from .indicators import calculate_technicals
from .risk import DailyLossState, RiskConfig
from .shadow_models import ShadowSnapshot, canonical_json, strict_json
from .screener import ScreenerConfig, screen_candidates


class _PolicyBroker:
    def __init__(self, ledger):
        self.ledger = ledger

    def get_position(self, ticker):
        lot = self.ledger.holdings.get(ticker.value)
        return Position(ticker, lot.quantity, Money(checked_float(lot.average_price))) if lot else None

    def place_order(self, order):
        raise BacktestInputError('LIVE_SUBMISSION_FORBIDDEN')


def code_identity() -> str:
    root = Path(__file__).parent
    names = ('backtest_models','backtest_inputs','backtest_costs','backtest_fills','backtest_ledger','backtest_engine','backtest_evidence','backtest_reporting','domain','execution','risk','signal_parser','trade_signal','screener','indicators','data_models')
    digest = hashlib.sha256()
    for name in names:
        digest.update(name.encode()); digest.update((root/(name+'.py')).read_bytes())
    return digest.hexdigest()


def run_backtest(bundle: BacktestBundle, start: date | None = None, end: date | None = None, profile: str = 'baseline', *, decision_observer=None) -> BacktestRun:
    with localcontext() as context:
        context.prec = 28
        return _run_backtest(bundle, start, end, profile, decision_observer)


def _run_backtest(bundle, start, end, profile, decision_observer):
    window = resolve_backtest_window(bundle,start,end)
    cost = cost_profile(profile); policy = bundle.policy
    calendar = tuple(s.session for s in bundle.calendar if s.completed)
    ledger = PortfolioLedger(policy,calendar,window.requested_start)
    broker = _PolicyBroker(ledger)
    indicator = IndicatorConfig(**policy.indicators.model_dump())
    execution = ExecutionConfig(*(checked_float(getattr(policy,k)) for k in ('buy_confidence_threshold','sell_confidence_threshold','buy_cash_fraction','max_position_value')))
    risk = RiskConfig(checked_float(policy.stop_loss_pct),checked_float(policy.take_profit_pct))
    screener = ScreenerConfig(policy.max_candidates,('KOSPI','KOSDAQ'),checked_float(policy.min_trading_value),checked_float(policy.min_volume_ratio),('SUSPENDED','HALTED','DELISTING','ADMIN_ISSUE'))
    sessions = []; fills = []; decisions = []; expiries = []; intents = []; cash_events = []; all_unknowns = set(window.reasons)
    initial_equity = policy.initial_cash
    initial_marks = []
    if policy.initial_positions:
        prior = decision_view(bundle,window.warmup_sessions[-1],tuple(ledger.holdings)) if window.warmup_sessions else None
        if prior is None or any(t not in prior.prices for t in ledger.holdings):
            initial_equity = None
            all_unknowns.add('INITIAL_VALUATION_UNKNOWN')
        else:
            initial_equity += sum((prior.prices[t]*l.quantity for t,l in ledger.holdings.items()),Decimal('0'))
            initial_marks = [next(b for b in bundle.bars if b.ticker==t and b.session==window.warmup_sessions[-1]) for t in sorted(ledger.holdings)]
    for session in window.sessions:
        ledger.start_session(session)
        opening = opening_cutoff(session)
        # Known, effective actions precede old orders; dividend entitlement is frozen on ex-session.
        for action in sorted(bundle.corporate_actions,key=lambda a:(a.effective,{'SPLIT':0,'DIVIDEND':1,'DELIST':2}[a.kind],a.action_id)):
            before_action = ledger.action_cash
            before_flow = ledger.cash_flow
            ledger.apply_corporate_action(action,session,opening)
            if ledger.action_cash != before_action or ledger.cash_flow != before_flow:
                cash_events.append({'action_id':action.action_id,'session':session.isoformat(),'kind':action.kind,'cash_delta':str(ledger.action_cash-before_action),'liquidation_delta':str(ledger.cash_flow-before_flow)})
        ledger.settle_pending(session)
        eligible = tuple(i for i in ledger.intents.values() if i.eligible_session <= session)
        for fill in model_session_fills(bundle,session,eligible,profile):
            ledger.apply_fill(fill)
            fills.append(fill)
            remaining = ledger.expire(fill.intent_id)
            expiries.append({'intent_id':fill.intent_id,'session':session.isoformat(),'remaining_quantity':remaining,'reason':'END_SESSION_EXPIRED' if remaining else 'FULLY_FILLED'})
        view = decision_view(bundle,session,tuple(ledger.holdings))
        unknowns = set(view.unknowns) | ledger.unknowns
        for action in bundle.corporate_actions:
            if action.effective <= session and opening < action.known_at <= view.cutoff:
                unknowns.add('LATE_ACTION_UNKNOWN:'+action.action_id)
        rows = []; technical_map = {}; healthy = set()
        for ticker in view.universe:
            history = view.history[ticker]
            frame = pd.DataFrame([{'고가':checked_float(b.high),'저가':checked_float(b.low),'종가':checked_float(b.close),'거래량':b.volume} for b in history])
            technicals = calculate_technicals(frame,indicator)
            technical_map[ticker] = technicals.technicals
            if technicals.health.status.value == 'AVAILABLE': healthy.add(ticker)
            member = view.membership.get(ticker); status = view.statuses.get(ticker)
            if not history or ticker not in view.prices or member is None or status is None:
                continue
            rows.append({'ticker':ticker,'market':member.market,'state':status.state,
                         'trading_value':checked_float(view.prices[ticker]*history[-1].volume),
                         'technicals':technicals.technicals,'health':technicals.health})
            if technicals.health.status.value != 'AVAILABLE':
                unknowns.add('INDICATORS_UNAVAILABLE:'+ticker)
        screening = screen_candidates(session.strftime('%Y%m%d'),rows,screener)
        selected = {c.ticker for c in screening.candidates}
        for event in screening.audit_events:
            decisions.append(DecisionEvidence(session=session,ticker=event.ticker,action='HOLD',reason='SCREENER_EXCLUDED',selected=False,risk_override=False))
        order = list(sorted(ledger.holdings)) + [c.ticker for c in screening.candidates if c.ticker not in ledger.holdings]
        def capture(ticker, evaluated):
            lot = ledger.holdings.get(ticker)
            qty = lot.quantity if lot else 0
            sell = sum(i.reserved_quantity for i in ledger.intents.values() if i.ticker == ticker)
            member = view.membership.get(ticker); status = view.statuses.get(ticker)
            available = ticker in view.prices and member is not None and status is not None and status.state == 'NORMAL'
            critical = bool(unknowns or not bundle.sources.calendar_complete or not bundle.sources.membership_complete or not bundle.sources.corporate_actions_complete)
            rules = [r for r in bundle.tick_rules if member and r.market == member.market and r.effective_start <= session and (r.effective_end is None or session < r.effective_end) and r.known_at <= view.cutoff]
            costs = [r for r in bundle.cost_rules if member and r.market == member.market and r.effective_start <= session and (r.effective_end is None or session < r.effective_end) and r.known_at <= view.cutoff]
            next_sessions = [day for day in calendar if day > session]
            tech = technical_map.get(ticker, {})
            tech = {k:v for k,v in tech.items() if v is None or not isinstance(v,float) or math.isfinite(v)}
            reasons = (() if evaluated else ('SCREENER_EXCLUDED',)) + (() if available else ('OBSERVATION_UNAVAILABLE',)) + (() if ticker in healthy else ('INDICATORS_UNAVAILABLE',))
            return ShadowSnapshot(session=session,ticker=ticker,cutoff=view.cutoff,price=view.prices.get(ticker),technicals_json=canonical_json(tech),quantity=qty,average_price=lot.average_price if lot else Decimal('0'),orderable_quantity=qty-sell,open_sell_quantity=sell,available_cash=ledger.available_cash,settled_cash=ledger.settled_cash,reserved_cash=ledger.reserved_cash,pending_cash=ledger.pending_cash,daily_realized_loss=ledger.daily_realized_loss,selected=ticker in selected,held=bool(qty),eligible=not reasons,exclusions=reasons,unknowns=tuple(sorted(unknowns)),fixture_raw=view.signals.get(ticker,''),baseline_action='HOLD',baseline_reason='UNPROJECTED',policy=policy,profile=profile,market=member.market if member else None,tick_rule_json=canonical_json(rules[0]) if len(rules)==1 and len(costs)==1 else 'null',next_session=next_sessions[0] if next_sessions else None,critical_unknown=critical,observation_available=available)
        if decision_observer:
            for excluded in sorted(set(view.universe)-set(order)):
                snapshot=capture(excluded,False)
                decision_observer(ShadowSnapshot.model_validate({**snapshot.model_dump(), 'baseline_reason':'SCREENER_EXCLUDED','snapshot_id':''}))
        for ticker in order:
            snapshot = capture(ticker, True)
            proposal = project_backtest_action(snapshot, snapshot.fixture_raw)
            if decision_observer:
                decision_observer(ShadowSnapshot.model_validate({**snapshot.model_dump(), 'baseline_action':proposal.action,'baseline_reason':proposal.reason,'baseline_quantity':proposal.quantity,'baseline_risk_override':proposal.risk_override,'snapshot_id':''}))
            intent_id = None
            if proposal.quantity:
                intent_id = content_hash({'session':session.isoformat(),'ticker':ticker,'side':proposal.action,'sequence':len(decisions),'policy':policy.version})
                intent = OpenIntent(intent_id=intent_id,ticker=ticker,side=proposal.action,quantity=proposal.quantity,remaining_quantity=proposal.quantity,limit_price=proposal.limit_price,decision_session=session,eligible_session=snapshot.next_session)
                reserved = ledger.reserve(intent,cost)
                if reserved is None or reserved.quantity != proposal.quantity: raise BacktestInputError('PROJECTION_RESERVATION_MISMATCH')
                intents.append(reserved)
            decisions.append(DecisionEvidence(session=session,ticker=ticker,action=proposal.action,reason=proposal.reason,selected=ticker in selected,risk_override=proposal.risk_override,intent_id=intent_id,quantity=proposal.quantity))
        marks = dict(view.prices)
        for action in bundle.corporate_actions:
            if action.effective <= session and opening < action.known_at <= view.cutoff:
                marks.pop(action.ticker,None)
        for ticker in ledger.holdings:
            if any(reason.endswith(':'+ticker) for reason in ledger.unknowns):
                marks.pop(ticker,None)
        holdings, equity, unrealized = ledger.snapshot(marks)
        if ledger.unknowns and any('ACTION_TERMS' in u for u in ledger.unknowns):
            equity = None; unrealized = None
        all_unknowns.update(unknowns)
        sessions.append(SessionEvidence(session=session,settled_cash=ledger.settled_cash,reserved_cash=ledger.reserved_cash,pending_cash=ledger.pending_cash,holdings=holdings,net_equity=equity,gross_equity=equity+ledger.cost_drag if equity is not None else None,coverage_status=CoverageStatus.INCOMPLETE if unknowns or window.reasons else CoverageStatus.COMPLETE,unknowns=tuple(sorted(unknowns)),realized_pnl=ledger.realized_pnl,unrealized_pnl=unrealized,action_cash=ledger.action_cash))
    if any(p.due_session is None for p in ledger.pending):
        all_unknowns.add('SETTLEMENT_CALENDAR_MISSING')
    limitations = ['SIMULATED_NOT_PROMOTION_AUTHORITY','DAILY_CLOSE_NOT_INTRADAY_RECONSTRUCTION','OPENING_FILLS_NOT_QUEUE_PROOF','EX_POST_VOLUME_EXECUTION_ONLY','SYNTHETIC_FEES_SLIPPAGE_NOT_ACTUAL_TARIFF','SALE_PROCEEDS_T_PLUS_2_NOT_BROKER_BUYING_POWER',*sorted(all_unknowns)]
    manifest = {'schema_version':1,'input_hash':content_hash(bundle),'code_identity':code_identity(),'window':window.document(),'policy':policy.model_dump(mode='json'),'profile':cost.document(),'fill_version':FILL_VERSION,'settlement_version':SETTLEMENT_VERSION,'source_hashes':list(bundle.sources.source_hashes),'market_rule_ids':[r.rule_id for r in (*bundle.cost_rules,*bundle.tick_rules)],'scenario_group':content_hash({'input':content_hash(bundle),'window':window.document(),'code':code_identity()})}
    return BacktestRun(manifest=manifest,calendar=bundle.calendar,corporate_actions=bundle.corporate_actions,cost_rules=bundle.cost_rules,tick_rules=bundle.tick_rules,benchmark=tuple(b for b in bundle.benchmark if b.session in window.sessions and b.known_at <= next(s.close_at for s in bundle.calendar if s.session==b.session)),intents=tuple(intents),sessions=tuple(sessions),fills=tuple(fills),decisions=tuple(decisions),expiries=tuple(expiries),cash_events=tuple(cash_events),open_intents=tuple(ledger.intents.values()),initial_marks=tuple(initial_marks),initial_equity=initial_equity,final_coverage=CoverageStatus.INCOMPLETE if all_unknowns else CoverageStatus.COMPLETE,limitations=tuple(limitations))


BacktestDecisionSnapshot = ShadowSnapshot


class ActionProjection(Frozen):
    action: str
    reason: str
    quantity: int = 0
    risk_override: bool = False
    limit_price: Amount | None = None


class _SnapshotBroker:
    def __init__(self, snapshot): self.snapshot = snapshot
    def get_position(self, ticker):
        s = self.snapshot
        return Position(ticker,s.quantity,Money(checked_float(s.average_price))) if s.quantity else None
    def place_order(self, order): raise BacktestInputError('LIVE_SUBMISSION_FORBIDDEN')


def project_backtest_action(snapshot: ShadowSnapshot, raw_signal: str) -> ActionProjection:
    """Same shipped policy and reservation gates, without any account mutation."""
    s=snapshot; p=s.policy
    if not s.observation_available: return ActionProjection(action='HOLD',reason='OBSERVATION_UNAVAILABLE')
    config=ExecutionConfig(*(checked_float(getattr(p,k)) for k in ('buy_confidence_threshold','sell_confidence_threshold','buy_cash_fraction','max_position_value')))
    result=execute_signal_cycle(raw_signal,Ticker(s.ticker),Money(checked_float(s.price)),checked_float(s.available_cash),_SnapshotBroker(s),config,RiskConfig(checked_float(p.stop_loss_pct),checked_float(p.take_profit_pct)),DailyLossState(checked_float(s.daily_realized_loss),checked_float(p.daily_loss_threshold)),dry_run=True)
    action=result.action.value; reason='MISSING_OR_MALFORMED_SIGNAL' if result.audit and result.audit.parse_error else result.reason
    risk=bool(result.audit and result.audit.risk_override)
    if action=='BUY' and s.critical_unknown: action='HOLD'; reason='NEW_BUY_BLOCKED_DATA_UNKNOWN'
    if action=='HOLD' or result.order is None: return ActionProjection(action=action,reason=reason,risk_override=risk)
    if s.next_session is None: return ActionProjection(action='HOLD',reason='NO_NEXT_EXECUTION_SESSION',risk_override=risk)
    if s.tick_rule_json=='null': raise BacktestInputError('MARKET_RULE_COVERAGE_MISSING')
    tick=TickRule.model_validate(strict_json(s.tick_rule_json)); limit=round_tick(s.price,tick,'floor' if action=='BUY' else 'ceil')
    intent=OpenIntent(intent_id='projection',ticker=s.ticker,side=action,quantity=result.order.quantity,remaining_quantity=result.order.quantity,limit_price=limit,decision_session=s.session,eligible_session=s.next_session)
    reserved=project_reservation(intent,cost_profile(s.profile),s.available_cash,s.orderable_quantity)
    if reserved is None: return ActionProjection(action='HOLD',reason='INSUFFICIENT_RESERVED_CASH',risk_override=risk)
    return ActionProjection(action=action,reason=reason,quantity=reserved.quantity,risk_override=risk,limit_price=limit)
