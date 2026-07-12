"""Deterministic, offline replay of frozen policy-path scenarios."""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from trading_bot.data_models import SourceHealth, SourceStatus
from trading_bot.domain import Money, Position, Ticker
from trading_bot.execution import ExecutionAction, ExecutionConfig, execute_signal_cycle
from trading_bot.mock_broker import MockBroker
from trading_bot.risk import DailyLossState, RiskConfig
from trading_bot.screener import ScreenerConfig, screen_candidates

SCHEMA_VERSION = 1
_TICKER = re.compile(r"^[0-9]{6}$")
REQUIRED_BOUNDARIES = frozenset({
    "buy_at_threshold", "buy_below_threshold", "hold", "sell",
    "malformed_signal", "stale_data", "stop_loss", "take_profit",
    "daily_loss_block", "sizing_boundary", "future_access",
})


class FutureDataAccessError(ValueError):
    """Raised whenever frozen data crosses its declared evaluation cutoff."""


@dataclass(frozen=True)
class ReplayStep:
    ticker: str
    raw_signal: str
    current_price: float
    fill: str
    market_row: Mapping[str, Any]
    expected_action: str


@dataclass(frozen=True)
class ReplayScenario:
    scenario_id: str
    mode: str
    trading_date: str
    evaluation_time: str
    policy: Mapping[str, Any]
    initial_cash: float
    initial_positions: tuple[Mapping[str, Any], ...]
    daily_loss: Mapping[str, float]
    market_history: tuple[Mapping[str, Any], ...]
    steps: tuple[ReplayStep, ...]


@dataclass(frozen=True)
class ReplayOutcome:
    scenario_id: str
    ticker: str
    rank: int
    action: str
    has_order: bool
    fill: str
    reason: str
    cash_after: float
    position_quantity_after: int
    expected_action: str
    matched: bool


def guarded_historical_view(
    rows: Iterable[Mapping[str, Any]], cutoff: str
) -> tuple[Mapping[str, Any], ...]:
    """Return rows through cutoff, failing loudly if any future row is supplied."""
    cutoff_dt = datetime.fromisoformat(cutoff)
    result = []
    for row in rows:
        observed = datetime.fromisoformat(str(row["observed_at"]))
        if observed > cutoff_dt:
            raise FutureDataAccessError(
                f"row observed at {observed.isoformat()} exceeds cutoff {cutoff_dt.isoformat()}"
            )
        result.append(row)
    return tuple(result)


def _finite(value: Any, name: str, *, minimum: float | None = None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number")
    number = float(value)
    if minimum is not None and number < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return number


def _keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"{label} fields mismatch: expected {sorted(expected)}, got {sorted(value)}")


def load_replay_bundle(path: str | Path) -> tuple[ReplayScenario, ...]:
    """Load and strictly validate a versioned replay fixture bundle."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    _keys(data, {"schema_version", "boundaries", "scenarios"}, "bundle")
    if data["schema_version"] != SCHEMA_VERSION:
        raise ValueError("unsupported replay schema version")
    if set(data["boundaries"]) != REQUIRED_BOUNDARIES:
        raise ValueError("fixture boundary catalog is incomplete or unknown")
    scenarios = []
    scenario_fields = {"id", "mode", "trading_date", "evaluation_time", "policy", "initial_state", "market_history", "steps"}
    step_fields = {"ticker", "raw_signal", "current_price", "fill", "market_row", "expected_action"}
    state_fields = {"cash", "positions", "daily_loss"}
    for raw in data["scenarios"]:
        _keys(raw, scenario_fields, "scenario")
        if raw["mode"] not in {"FOCUSED", "FULL_DAY"}:
            raise ValueError("mode must be FOCUSED or FULL_DAY")
        datetime.fromisoformat(raw["evaluation_time"])
        if raw["evaluation_time"][:10].replace("-", "") != raw["trading_date"]:
            raise ValueError("evaluation_time must fall on trading_date")
        state = raw["initial_state"]
        _keys(state, state_fields, "initial_state")
        cash = _finite(state["cash"], "cash", minimum=0)
        positions = tuple(state["positions"])
        for position in positions:
            _keys(position, {"ticker", "quantity", "average_price"}, "position")
            if not _TICKER.fullmatch(position["ticker"]): raise ValueError("invalid ticker")
            _finite(position["quantity"], "quantity", minimum=1)
            _finite(position["average_price"], "average_price", minimum=0)
        _keys(state["daily_loss"], {"realized_loss", "threshold"}, "daily_loss")
        daily_loss = {k: _finite(v, k, minimum=0) for k, v in state["daily_loss"].items()}
        history = guarded_historical_view(raw["market_history"], raw["evaluation_time"])
        steps = []
        for step in raw["steps"]:
            _keys(step, step_fields, "step")
            if not _TICKER.fullmatch(step["ticker"]): raise ValueError("invalid ticker")
            if not isinstance(step["raw_signal"], str): raise ValueError("raw_signal must be a string")
            if step["fill"] not in {"COMPLETE", "NONE"}: raise ValueError("unsupported fill")
            price = _finite(step["current_price"], "current_price", minimum=0)
            steps.append(ReplayStep(step["ticker"], step["raw_signal"], price, step["fill"], step["market_row"], step["expected_action"]))
        scenarios.append(ReplayScenario(raw["id"], raw["mode"], raw["trading_date"], raw["evaluation_time"], raw["policy"], cash, positions, daily_loss, history, tuple(steps)))
    return tuple(scenarios)


def _position(raw: Mapping[str, Any]) -> Position:
    return Position(Ticker(raw["ticker"]), int(raw["quantity"]), Money(float(raw["average_price"]), "KRW"))


def run_replay_scenarios(scenarios: Sequence[ReplayScenario]) -> tuple[ReplayOutcome, ...]:
    """Run frozen scenarios through production screening and execution seams."""
    outcomes: list[ReplayOutcome] = []
    for scenario in scenarios:
        guarded_historical_view(scenario.market_history, scenario.evaluation_time)
        p = scenario.policy
        screener = ScreenerConfig(int(p["max_candidates"]), tuple(p["markets"]), float(p["min_trading_value"]), float(p["min_volume_ratio"]), tuple(p["excluded_states"]))
        risk = RiskConfig(float(p["stop_loss_pct"]), float(p["take_profit_pct"]))
        execution = ExecutionConfig(float(p["buy_confidence_threshold"]), float(p["sell_confidence_threshold"]), float(p["buy_cash_fraction"]), float(p["max_position_value"]))
        broker = MockBroker(Money(scenario.initial_cash, "KRW"), [_position(x) for x in scenario.initial_positions])
        daily = DailyLossState(float(scenario.daily_loss["realized_loss"]), float(scenario.daily_loss["threshold"]))
        by_ticker = {s.ticker: s for s in scenario.steps}
        rows = []
        for step in scenario.steps:
            row = dict(step.market_row)
            observed = row.pop("observed_at", scenario.evaluation_time)
            guarded_historical_view(({"observed_at": observed},), scenario.evaluation_time)
            health_raw = row.get("health", {})
            row["health"] = SourceHealth(source="fixture", status=SourceStatus(health_raw.get("status", "AVAILABLE")), reason=health_raw.get("reason", "fixture"), observed_date=health_raw.get("observed_date", scenario.trading_date), expected_date=scenario.trading_date)
            rows.append(row)
        selected = screen_candidates(scenario.trading_date, rows, screener).candidates
        for rank, candidate in enumerate(selected, 1):
            step = by_ticker[candidate.ticker]
            result = execute_signal_cycle(step.raw_signal, Ticker(step.ticker), Money(step.current_price, "KRW"), broker.cash.amount, broker, execution, risk, daily, dry_run=True)
            if step.fill == "COMPLETE" and result.order is not None:
                broker.place_order(result.order)
            held = broker.get_position(Ticker(step.ticker))
            action = result.action.value
            outcomes.append(ReplayOutcome(scenario.scenario_id, step.ticker, rank, action, result.order is not None, step.fill, result.reason, broker.cash.amount, held.quantity if held else 0, step.expected_action, action == step.expected_action))
    return tuple(outcomes)
