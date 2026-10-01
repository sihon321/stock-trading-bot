"""Chronological daily-close simulation using shipped pure policy gates."""
from __future__ import annotations

import hashlib
import math
from datetime import date
from decimal import Decimal, localcontext
from pathlib import Path

import pandas as pd

from .backtest_costs import cost_profile, effective_rule, round_tick
from .backtest_fills import FILL_VERSION, model_session_fills, opening_cutoff
from .backtest_inputs import decision_view, resolve_backtest_window
from .backtest_ledger import PortfolioLedger, SETTLEMENT_VERSION
from .backtest_models import BacktestBundle, BacktestInputError, CoverageStatus, FillEvidence, Frozen, OpenIntent, SessionEvidence, content_hash
from .data_models import IndicatorConfig
from .domain import Money, Position, Ticker
from .execution import ExecutionConfig, execute_signal_cycle
from .indicators import calculate_technicals
from .risk import DailyLossState, RiskConfig
from .screener import ScreenerConfig, screen_candidates


class DecisionEvidence(Frozen):
    session: date
    ticker: str
    action: str
    reason: str
    selected: bool
    risk_override: bool
    intent_id: str | None = None
    quantity: int = 0


class BacktestRun(Frozen):
    manifest: dict
    sessions: tuple[SessionEvidence, ...]
    fills: tuple[FillEvidence, ...]
    decisions: tuple[DecisionEvidence, ...]
    expiries: tuple[dict, ...]
    initial_equity: Decimal | None
    final_coverage: CoverageStatus
    limitations: tuple[str, ...]


def checked_float(value: Decimal) -> float:
    number = float(value)
    if not math.isfinite(number) or abs(Decimal(str(number))-value) > max(Decimal('.00000001'),abs(value)*Decimal('1e-15')):
        raise BacktestInputError('UNSAFE_POLICY_FLOAT_BRIDGE')
    return number


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
    names = ('backtest_models','backtest_inputs','backtest_costs','backtest_fills','backtest_ledger','backtest_engine','domain','execution','risk','signal_parser','screener','indicators','data_models')
    digest = hashlib.sha256()
    for name in names:
        digest.update(name.encode()); digest.update((root/(name+'.py')).read_bytes())
    return digest.hexdigest()


def run_backtest(bundle: BacktestBundle, start: date | None = None, end: date | None = None, profile: str = 'baseline') -> BacktestRun:
    with localcontext() as context:
        context.prec = 28
        return _run_backtest(bundle, start, end, profile)


def _run_backtest(bundle, start, end, profile):
    window = resolve_backtest_window(bundle,start,end)
    cost = cost_profile(profile); policy = bundle.policy
    calendar = tuple(s.session for s in bundle.calendar if s.completed)
    ledger = PortfolioLedger(policy,calendar)
    broker = _PolicyBroker(ledger)
    indicator = IndicatorConfig(**policy.indicators.model_dump())
    execution = ExecutionConfig(*(checked_float(getattr(policy,k)) for k in ('buy_confidence_threshold','sell_confidence_threshold','buy_cash_fraction','max_position_value')))
    risk = RiskConfig(checked_float(policy.stop_loss_pct),checked_float(policy.take_profit_pct))
    screener = ScreenerConfig(policy.max_candidates,('KOSPI','KOSDAQ'),checked_float(policy.min_trading_value),checked_float(policy.min_volume_ratio),('SUSPENDED','HALTED','DELISTING','ADMIN_ISSUE'))
    sessions = []; fills = []; decisions = []; expiries = []; all_unknowns = set(window.reasons)
    initial_equity = policy.initial_cash
    if policy.initial_positions:
        prior = decision_view(bundle,window.warmup_sessions[-1],tuple(ledger.holdings)) if window.warmup_sessions else None
        if prior is None or any(t not in prior.prices for t in ledger.holdings):
            initial_equity = None
            all_unknowns.add('INITIAL_VALUATION_UNKNOWN')
        else:
            initial_equity += sum((prior.prices[t]*l.quantity for t,l in ledger.holdings.items()),Decimal('0'))
    for session in window.sessions:
        ledger.start_session(session)
        opening = opening_cutoff(session)
        # Known, effective actions precede old orders; dividend entitlement is frozen on ex-session.
        for action in sorted(bundle.corporate_actions,key=lambda a:(a.effective,{'SPLIT':0,'DIVIDEND':1,'DELIST':2}[a.kind],a.action_id)):
            ledger.apply_corporate_action(action,session,opening)
        eligible = tuple(i for i in ledger.intents.values() if i.eligible_session <= session)
        for fill in model_session_fills(bundle,session,eligible,profile):
            ledger.apply_fill(fill)
            fills.append(fill)
            remaining = ledger.expire(fill.intent_id)
            expiries.append({'intent_id':fill.intent_id,'session':session.isoformat(),'remaining_quantity':remaining,'reason':'END_SESSION_EXPIRED' if remaining else 'FULLY_FILLED'})
        view = decision_view(bundle,session,tuple(ledger.holdings))
        unknowns = set(view.unknowns) | ledger.unknowns
        for action in bundle.corporate_actions:
            if action.effective <= session and action.known_at > opening:
                unknowns.add('LATE_ACTION_UNKNOWN:'+action.action_id)
        rows = []
        for ticker in view.universe:
            history = view.history[ticker]
            frame = pd.DataFrame([{'고가':checked_float(b.high),'저가':checked_float(b.low),'종가':checked_float(b.close),'거래량':b.volume} for b in history])
            technicals = calculate_technicals(frame,indicator)
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
        for ticker in order:
            price = view.prices.get(ticker)
            status = view.statuses.get(ticker)
            if price is None or status is None or status.state != 'NORMAL' or ticker not in view.membership:
                decisions.append(DecisionEvidence(session=session,ticker=ticker,action='HOLD',reason='OBSERVATION_UNAVAILABLE',selected=ticker in selected,risk_override=False))
                continue
            result = execute_signal_cycle(view.signals.get(ticker,''),Ticker(ticker),Money(checked_float(price)),checked_float(ledger.available_cash),broker,execution,risk,DailyLossState(checked_float(ledger.daily_realized_loss),checked_float(policy.daily_loss_threshold)),dry_run=True)
            reason = 'MISSING_OR_MALFORMED_SIGNAL' if result.audit and result.audit.parse_error else result.reason
            action = result.action.value; intent_id = None; quantity = 0
            # Evidence gaps block new BUY capital, but observable valid held exits stay eligible.
            critical = unknowns or not bundle.sources.calendar_complete or not bundle.sources.membership_complete or not bundle.sources.corporate_actions_complete
            if action == 'BUY' and critical:
                action = 'HOLD'; reason = 'NEW_BUY_BLOCKED_DATA_UNKNOWN'
            if action != 'HOLD' and result.order is not None:
                next_sessions = [s for s in calendar if s > session]
                if not next_sessions:
                    action = 'HOLD';reason = 'NO_NEXT_EXECUTION_SESSION'
                else:
                    market = view.membership[ticker].market
                    tick = effective_rule(bundle.tick_rules,market,session,view.cutoff)
                    effective_rule(bundle.cost_rules,market,session,view.cutoff)
                    limit = round_tick(price,tick,'floor' if action=='BUY' else 'ceil')
                    identity = {'session':session.isoformat(),'ticker':ticker,'side':action,'sequence':len(decisions),'policy':policy.version}
                    intent_id = content_hash(identity)
                    intent = OpenIntent(intent_id=intent_id,ticker=ticker,side=action,quantity=result.order.quantity,remaining_quantity=result.order.quantity,limit_price=limit,decision_session=session,eligible_session=next_sessions[0])
                    reserved = ledger.reserve(intent,cost)
                    if reserved is None:
                        action = 'HOLD';reason = 'INSUFFICIENT_RESERVED_CASH';intent_id = None
                    else:
                        quantity = reserved.quantity
            decisions.append(DecisionEvidence(session=session,ticker=ticker,action=action,reason=reason,selected=ticker in selected,risk_override=bool(result.audit and result.audit.risk_override),intent_id=intent_id,quantity=quantity))
        marks = dict(view.prices)
        for ticker in ledger.holdings:
            if any(reason.endswith(':'+ticker) for reason in ledger.unknowns):
                marks.pop(ticker,None)
        holdings, equity, unrealized = ledger.snapshot(marks)
        if ledger.unknowns and any('ACTION_TERMS' in u for u in ledger.unknowns):
            equity = None; unrealized = None
        all_unknowns.update(unknowns)
        sessions.append(SessionEvidence(session=session,settled_cash=ledger.settled_cash,reserved_cash=ledger.reserved_cash,pending_cash=ledger.pending_cash,holdings=holdings,net_equity=equity,gross_equity=equity+ledger.cost_drag if equity is not None else None,coverage_status=CoverageStatus.INCOMPLETE if unknowns or window.reasons else CoverageStatus.COMPLETE,unknowns=tuple(sorted(unknowns)),realized_pnl=ledger.realized_pnl,unrealized_pnl=unrealized,action_cash=ledger.action_cash))
    if ledger.pending_cash:
        all_unknowns.add('PENDING_SETTLEMENT_AT_END')
    limitations = ['SIMULATED_NOT_PROMOTION_AUTHORITY','DAILY_CLOSE_NOT_INTRADAY_RECONSTRUCTION','OPENING_FILLS_NOT_QUEUE_PROOF','EX_POST_VOLUME_EXECUTION_ONLY','SYNTHETIC_FEES_SLIPPAGE_NOT_ACTUAL_TARIFF','SALE_PROCEEDS_T_PLUS_2_NOT_BROKER_BUYING_POWER',*sorted(all_unknowns)]
    manifest = {'schema_version':1,'input_hash':content_hash(bundle),'code_identity':code_identity(),'window':window.document(),'policy':policy.model_dump(mode='json'),'profile':cost.document(),'fill_version':FILL_VERSION,'settlement_version':SETTLEMENT_VERSION,'source_hashes':list(bundle.sources.source_hashes),'market_rule_ids':[r.rule_id for r in (*bundle.cost_rules,*bundle.tick_rules)],'scenario_group':content_hash({'input':content_hash(bundle),'window':window.document(),'code':code_identity()})}
    return BacktestRun(manifest=manifest,sessions=tuple(sessions),fills=tuple(fills),decisions=tuple(decisions),expiries=tuple(expiries),initial_equity=initial_equity,final_coverage=CoverageStatus.INCOMPLETE if all_unknowns else CoverageStatus.COMPLETE,limitations=tuple(limitations))
