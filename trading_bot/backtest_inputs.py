"""Bounded offline loading and point-in-time daily views."""
from __future__ import annotations

import json
import stat
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

from pydantic import ValidationError

from .backtest_models import BacktestBundle, BacktestInputError, Bar, CoverageStatus, Membership, TradingStatus

MAX_INPUT_BYTES = 64 * 1024 * 1024


def _unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise BacktestInputError('DUPLICATE_JSON_KEY')
        result[key] = value
    return result


def read_json_document(path: str | Path) -> dict:
    try:
        path = Path(path)
        if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode) or path.stat().st_size > MAX_INPUT_BYTES:
            raise BacktestInputError('UNSAFE_OR_OVERSIZE_INPUT')
        with path.open('rb') as handle:
            payload = handle.read(MAX_INPUT_BYTES + 1)
        if len(payload) > MAX_INPUT_BYTES:
            raise BacktestInputError('OVERSIZE_INPUT')
        raw = json.loads(payload, object_pairs_hook=_unique_pairs, parse_constant=lambda _: (_ for _ in ()).throw(BacktestInputError('NONFINITE_JSON')))
        if not isinstance(raw, dict):
            raise BacktestInputError('INVALID_DOCUMENT')
        return raw
    except BacktestInputError:
        raise
    except (OSError, ValueError, RecursionError) as exc:
        raise BacktestInputError('INVALID_INPUT') from exc


def load_backtest_bundle(path: str | Path) -> BacktestBundle:
    try:
        return BacktestBundle.model_validate(read_json_document(path))
    except (ValidationError, ValueError, RecursionError) as exc:
        if isinstance(exc, BacktestInputError):
            raise
        raise BacktestInputError('INVALID_BUNDLE_SCHEMA') from exc


@dataclass(frozen=True)
class BacktestWindow:
    requested_start: date
    requested_end: date
    sessions: tuple[date, ...]
    warmup_sessions: tuple[date, ...]
    coverage_status: CoverageStatus
    reasons: tuple[str, ...]

    def document(self):
        return {'requested_start': self.requested_start.isoformat(), 'requested_end': self.requested_end.isoformat(),
                'actual_start': self.sessions[0].isoformat() if self.sessions else None,
                'actual_end': self.sessions[-1].isoformat() if self.sessions else None,
                'warmup_sessions': len(self.warmup_sessions), 'coverage_status': self.coverage_status.value,
                'reasons': list(self.reasons)}


def resolve_backtest_window(bundle: BacktestBundle, start: date | None = None, end: date | None = None) -> BacktestWindow:
    completed = tuple(s.session for s in bundle.calendar if s.completed)
    if not completed:
        raise BacktestInputError('NO_COMPLETED_SESSIONS')
    end = end or completed[-1]
    if start is None:
        try:
            start = end.replace(year=end.year-3)
        except ValueError:
            start = end.replace(year=end.year-3, day=28)
    if start > end:
        raise BacktestInputError('INVALID_DATE_RANGE')
    sessions = tuple(s for s in completed if start <= s <= end)
    warmup = tuple(s for s in completed if s < start)
    reasons = []
    if start < bundle.sources.coverage_start or end > bundle.sources.coverage_end or not sessions:
        reasons.append('REQUESTED_COVERAGE_MISSING')
    for field in ('calendar_complete', 'membership_complete', 'corporate_actions_complete'):
        if not getattr(bundle.sources, field):
            reasons.append(field.upper()+'_UNKNOWN')
    required = max(bundle.policy.indicators.model_dump().values()) + 1
    if len(warmup) < required:
        reasons.append('WARMUP_INSUFFICIENT')
    if bundle.policy.universe_mode == 'ALLOWLIST':
        reasons.append('FIXED_UNIVERSE_SURVIVORSHIP')
    if any(r.synthetic for r in (*bundle.cost_rules, *bundle.tick_rules)):
        reasons.append('SYNTHETIC_MARKET_RULES')
    if sessions:
        first = next(s for s in bundle.calendar if s.session == sessions[0])
        from zoneinfo import ZoneInfo
        first_open = datetime.combine(first.session, datetime.min.time().replace(hour=9), ZoneInfo('Asia/Seoul'))
        if any(x.known_at > first_open for x in bundle.policy.initial_positions):
            raise BacktestInputError('FUTURE_INITIAL_POSITION')
    return BacktestWindow(start, end, sessions, warmup, CoverageStatus.INCOMPLETE if reasons else CoverageStatus.COMPLETE, tuple(reasons))


def latest_record(records, ticker: str, session: date, cutoff: datetime):
    candidates = [r for r in records if r.ticker == ticker and r.effective <= session and r.known_at <= cutoff]
    return max(candidates, key=lambda r: (r.effective, r.known_at)) if candidates else None


@dataclass(frozen=True)
class DecisionView:
    session: date
    cutoff: datetime
    universe: tuple[str, ...]
    membership: dict[str, Membership]
    statuses: dict[str, TradingStatus]
    history: dict[str, tuple[Bar, ...]]
    prices: dict[str, Decimal]
    signals: dict[str, str]
    unknowns: tuple[str, ...]


def decision_view(bundle: BacktestBundle, session: date, held: tuple[str, ...] = ()) -> DecisionView:
    calendar = next((s for s in bundle.calendar if s.session == session and s.completed), None)
    if calendar is None:
        raise BacktestInputError('UNKNOWN_DECISION_SESSION')
    cutoff = calendar.close_at
    symbols = sorted({m.ticker for m in bundle.membership} | set(held))
    members = {}; statuses = {}; histories = {}; prices = {}; signals = {}; unknowns = []
    for ticker in symbols:
        member = latest_record(bundle.membership, ticker, session, cutoff)
        included = member is not None and member.member and member.ordinary
        if bundle.policy.universe_mode == 'ALLOWLIST':
            included = included and ticker in bundle.policy.allowlist
        if not included and ticker not in held:
            continue
        if member is not None:
            members[ticker] = member
        else:
            unknowns.append('MEMBERSHIP_UNKNOWN:'+ticker)
        status = latest_record(bundle.trading_status, ticker, session, cutoff)
        if status is None:
            unknowns.append('STATUS_UNKNOWN:'+ticker)
        else:
            statuses[ticker] = status
        history = tuple(b for b in bundle.bars if b.ticker == ticker and b.session <= session and b.known_at <= cutoff)
        current = next((b for b in history if b.session == session), None)
        if current:
            prices[ticker] = current.close
        else:
            unknowns.append('PRICE_UNKNOWN:'+ticker)
        if member is not None:
            expected = {s.session for s in bundle.calendar if s.completed and member.effective <= s.session <= session}
            observed = {b.session for b in history}
            if expected-observed:
                unknowns.append('HISTORY_GAP:'+ticker)
        adjusted = []
        for bar in history:
            ratio = Decimal('1')
            for action in bundle.corporate_actions:
                if action.ticker == ticker and action.kind == 'SPLIT' and bar.session < action.effective <= session and action.known_at <= cutoff:
                    ratio *= action.ratio
            adjusted.append(bar.model_copy(update={k: getattr(bar, k)/ratio for k in ('open','high','low','close')}))
        histories[ticker] = tuple(adjusted)
        signal = next((x for x in bundle.signals if x.ticker == ticker and x.session == session and x.known_at <= cutoff), None)
        if signal:
            signals[ticker] = signal.raw
    universe = tuple(sorted(histories))
    if not members:
        unknowns.append('UNIVERSE_UNKNOWN')
    # A missing expected daily bar is evidence uncertainty, even if older bars exist.
    return DecisionView(session, cutoff, universe, members, statuses, histories, prices, signals, tuple(sorted(set(unknowns))))
