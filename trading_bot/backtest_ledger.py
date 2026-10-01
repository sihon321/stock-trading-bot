"""One Decimal account ledger with explicit reservations and settlement."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from .backtest_costs import BPS, CostProfile, ceil_krw
from .backtest_models import BacktestInputError, BacktestPolicy, FillEvidence, HoldingEvidence, OpenIntent

ZERO = Decimal('0')
SETTLEMENT_VERSION = 'conservative-sale-proceeds-T+2-KRX-v1'


@dataclass(frozen=True)
class Lot:
    quantity: int
    average_price: Decimal


@dataclass(frozen=True)
class PendingSettlement:
    origin_id: str
    amount: Decimal
    due_session: date | None


class PortfolioLedger:
    """settled_cash includes reservations; only available_cash may fund a BUY."""

    def __init__(self, policy: BacktestPolicy, sessions: tuple[date, ...]):
        self.initial_cash = policy.initial_cash
        self.settled_cash = policy.initial_cash
        self.sessions = sessions
        self.holdings = {x.ticker: Lot(x.quantity, x.average_price) for x in policy.initial_positions}
        self.intents: dict[str, OpenIntent] = {}
        self.pending: list[PendingSettlement] = []
        self.seen_intents: set[str] = set()
        self.applied_fills: set[tuple[str,date]] = set()
        self.applied_actions: set[str] = set()
        self.dividend_entitlements: dict[str, int] = {}
        self.realized_pnl = ZERO
        self.daily_realized_loss = ZERO
        self.action_cash = ZERO
        self.cash_flow = ZERO
        self.cost_drag = ZERO
        self.unknowns: set[str] = set()
        self.reconcile()

    @property
    def reserved_cash(self):
        return sum((x.reserved_cash for x in self.intents.values()), ZERO)

    @property
    def pending_cash(self):
        return sum((x.amount for x in self.pending), ZERO)

    @property
    def available_cash(self):
        return self.settled_cash-self.reserved_cash

    def reserve(self, intent: OpenIntent, profile: CostProfile) -> OpenIntent | None:
        if intent.intent_id in self.seen_intents or intent.remaining_quantity != intent.quantity or intent.eligible_session <= intent.decision_session:
            raise BacktestInputError('INVALID_OR_DUPLICATE_INTENT')
        quantity = intent.quantity
        if intent.side == 'BUY':
            # Binary search exact principal + rounded commission affordability.
            lo, hi = 0, quantity
            while lo < hi:
                mid = (lo+hi+1)//2
                budget = mid*intent.limit_price + ceil_krw(mid*intent.limit_price*profile.commission_bps/BPS)
                if budget <= self.available_cash:
                    lo = mid
                else:
                    hi = mid-1
            quantity = lo
            if not quantity:
                return None
            reservation = quantity*intent.limit_price + ceil_krw(quantity*intent.limit_price*profile.commission_bps/BPS)
            intent = intent.model_copy(update={'quantity': quantity, 'remaining_quantity': quantity, 'reserved_cash': reservation, 'reserved_quantity': 0})
        else:
            available = self.holdings.get(intent.ticker, Lot(0,ZERO)).quantity - sum(x.reserved_quantity for x in self.intents.values() if x.ticker == intent.ticker)
            if quantity > available:
                raise BacktestInputError('OVERSELL_RESERVATION')
            intent = intent.model_copy(update={'reserved_cash': ZERO, 'reserved_quantity': quantity})
        self.intents[intent.intent_id] = intent
        self.seen_intents.add(intent.intent_id)
        self.reconcile()
        return intent

    def apply_fill(self, fill: FillEvidence):
        key = (fill.intent_id, fill.session)
        intent = self.intents.get(fill.intent_id)
        if intent is None or key in self.applied_fills or fill.ticker != intent.ticker or fill.side != intent.side or fill.quantity > intent.remaining_quantity or fill.session < intent.eligible_session:
            raise BacktestInputError('INVALID_OR_DUPLICATE_FILL')
        if not fill.quantity:
            return
        if fill.executed_price <= 0 or (fill.side == 'BUY' and fill.executed_price > intent.limit_price) or (fill.side == 'SELL' and fill.executed_price < intent.limit_price):
            raise BacktestInputError('INVALID_FILL_PRICE')
        notional = fill.executed_price*fill.quantity
        costs = fill.commission+fill.sell_tax+fill.surtax
        lot = self.holdings.get(fill.ticker, Lot(0,ZERO))
        if fill.side == 'BUY':
            charge = notional+costs
            if fill.sell_tax or fill.surtax or charge > intent.reserved_cash:
                raise BacktestInputError('UNRESERVED_BUY_COST')
            basis = lot.quantity*lot.average_price+charge
            self.holdings[fill.ticker] = Lot(lot.quantity+fill.quantity, basis/(lot.quantity+fill.quantity))
            self.settled_cash -= charge
            self.cash_flow -= charge
            updated = intent.model_copy(update={'remaining_quantity': intent.remaining_quantity-fill.quantity, 'reserved_cash': intent.reserved_cash-charge})
        else:
            proceeds = notional-costs
            if fill.quantity > lot.quantity or proceeds < 0:
                raise BacktestInputError('INVALID_SELL_PROCEEDS')
            realized = proceeds-lot.average_price*fill.quantity
            self.realized_pnl += realized
            self.daily_realized_loss += max(ZERO,-realized)
            remaining = lot.quantity-fill.quantity
            if remaining:
                self.holdings[fill.ticker] = Lot(remaining,lot.average_price)
            else:
                self.holdings.pop(fill.ticker)
            index = self.sessions.index(fill.session)
            due = self.sessions[index+2] if index+2 < len(self.sessions) else None
            self.pending.append(PendingSettlement(fill.intent_id,proceeds,due))
            self.cash_flow += proceeds
            updated = intent.model_copy(update={'remaining_quantity': intent.remaining_quantity-fill.quantity, 'reserved_quantity': intent.reserved_quantity-fill.quantity})
        self.cost_drag += costs+fill.slippage_drag
        self.applied_fills.add(key)
        self.intents[intent.intent_id] = updated
        self.reconcile()

    def expire(self, intent_id: str):
        if intent_id not in self.intents:
            raise BacktestInputError('UNKNOWN_INTENT')
        intent = self.intents.pop(intent_id)
        self.reconcile()
        return intent.remaining_quantity

    def start_session(self, session: date):
        self.daily_realized_loss = ZERO
        due = [p for p in self.pending if p.due_session is not None and p.due_session <= session]
        self.settled_cash += sum((p.amount for p in due),ZERO)
        self.pending = [p for p in self.pending if p not in due]
        self.reconcile()

    def reconcile(self):
        if self.available_cash < 0 or self.settled_cash < 0 or self.pending_cash < 0:
            raise BacktestInputError('LEDGER_NEGATIVE_CASH')
        if self.settled_cash+self.pending_cash != self.initial_cash+self.cash_flow+self.action_cash:
            raise BacktestInputError('LEDGER_CASH_UNRECONCILED')
        for ticker, lot in self.holdings.items():
            if lot.quantity <= 0 or lot.average_price <= 0 or sum(x.reserved_quantity for x in self.intents.values() if x.ticker == ticker) > lot.quantity:
                raise BacktestInputError('LEDGER_INVENTORY_UNRECONCILED')
        if any(x.reserved_quantity and x.ticker not in self.holdings for x in self.intents.values()):
            raise BacktestInputError('LEDGER_MISSING_INVENTORY')

    def snapshot(self, prices: dict[str, Decimal]):
        rows = tuple(HoldingEvidence(ticker=t, quantity=l.quantity, average_price=l.average_price, mark_price=prices.get(t)) for t,l in sorted(self.holdings.items()))
        if any(h.mark_price is None for h in rows):
            return rows, None, None
        market_value = sum((h.mark_price*h.quantity for h in rows),ZERO)
        unrealized = sum(((h.mark_price-h.average_price)*h.quantity for h in rows),ZERO)
        return rows, self.settled_cash+self.pending_cash+market_value, unrealized


    def apply_corporate_action(self, action, session: date, cutoff):
        """Apply known actions before the opening opportunity, with explicit terms."""
        if action.known_at > cutoff or action.effective > session:
            return
        lot = self.holdings.get(action.ticker)
        if action.kind == 'DIVIDEND':
            if action.action_id not in self.dividend_entitlements:
                if session != action.effective:
                    self.unknowns.add('DIVIDEND_ENTITLEMENT_UNKNOWN:'+action.action_id)
                    return
                self.dividend_entitlements[action.action_id] = lot.quantity if lot else 0
            if action.action_id not in self.applied_actions and action.payable_session <= session:
                cash = Decimal(self.dividend_entitlements[action.action_id])*action.cash_per_share
                self.settled_cash += cash
                self.action_cash += cash
                self.applied_actions.add(action.action_id)
        elif action.action_id not in self.applied_actions:
            for id, intent in tuple(self.intents.items()):
                if intent.ticker == action.ticker:
                    self.expire(id)
            if lot and action.kind == 'SPLIT':
                shares = Decimal(lot.quantity)*action.ratio
                integer = int(shares)
                fraction = shares-integer
                if fraction and action.fractional_cash_price is None:
                    self.unknowns.add('FRACTIONAL_ACTION_TERMS_UNKNOWN:'+action.action_id)
                    return
                adjusted_basis = lot.average_price/action.ratio
                if integer:
                    self.holdings[action.ticker] = Lot(integer, adjusted_basis)
                else:
                    self.holdings.pop(action.ticker)
                if fraction:
                    cash = fraction*action.fractional_cash_price
                    self.settled_cash += cash
                    self.action_cash += cash
                    self.realized_pnl += cash-fraction*adjusted_basis
            elif lot and action.kind == 'DELIST':
                if action.disposition_price is None or action.payable_session is None:
                    self.unknowns.add('DELIST_DISPOSITION_UNKNOWN:'+action.ticker)
                    return
                proceeds = Decimal(lot.quantity)*action.disposition_price
                self.holdings.pop(action.ticker)
                self.pending.append(PendingSettlement(action.action_id,proceeds,action.payable_session))
                # Disposition is a liquidation cash flow, not a dividend contribution.
                self.cash_flow += proceeds
                realized = proceeds-lot.quantity*lot.average_price
                self.realized_pnl += realized
                self.daily_realized_loss += max(ZERO,-realized)
            self.applied_actions.add(action.action_id)
        self.reconcile()


class SimulatedPortfolioBroker:
    """Explicit offline capability; production submission is intentionally absent."""
    def __init__(self, ledger: PortfolioLedger):
        self.ledger = ledger

    def submit_order(self, order):
        raise BacktestInputError('SIMULATOR_REQUIRES_RESERVED_INTENT')

