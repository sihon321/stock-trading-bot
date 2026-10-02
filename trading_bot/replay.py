"""Deterministic, offline replay of frozen policy-path scenarios."""

from __future__ import annotations

import json
import hashlib
import math
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import pandas as pd

from trading_bot.data_models import IndicatorConfig, SourceHealth, SourceStatus
from trading_bot.domain import Money, Position, Ticker
from trading_bot.execution import ExecutionAction, ExecutionConfig, execute_signal_cycle
from trading_bot.indicators import calculate_technicals
from trading_bot.mock_broker import MockBroker
from trading_bot.risk import DailyLossState, RiskConfig
from trading_bot.screener import ScreenerConfig, screen_candidates

from trading_bot.replay_evidence import (
    FutureDataAccessError,
    NON_PROFITABILITY_DISCLAIMER,
    REQUIRED_BOUNDARIES,
    ReplayCheck,
    ReplayCount,
    ReplayEvidenceError,
    ReplayFunnel,
    ReplayManifest,
    ReplayOutcome,
    ReplayOutputError,
    ReplayResult,
    ReplayVerification,
    SCHEMA_VERSION,
    _canonical_value,
    _deterministic_result_document,
    _sha256,
    build_replay_funnel,
    canonical_json_bytes,
    compute_result_id,
    verify_replay_expectations,
)

_TICKER = re.compile(r"^[0-9]{6}$")


def write_replay_result(
    result: ReplayResult,
    destination: str | Path,
    *,
    filename: str | None = None,
) -> Path:
    """Atomically persist normalized evidence within a trusted destination."""
    raw_destination = Path(destination)
    if raw_destination.is_symlink():
        raise ReplayOutputError("output destination may not be a symbolic link")
    raw_destination.mkdir(parents=True, exist_ok=True)
    if not raw_destination.is_dir():
        raise ReplayOutputError("output destination must be a directory")
    root = raw_destination.resolve(strict=True)

    selected_name = filename or f"{result.result_id}.json"
    selected = Path(selected_name)
    if selected.is_absolute() or selected.name != selected_name or selected_name in {"", ".", ".."}:
        raise ReplayOutputError("output filename must be a plain filename")
    target = root / selected_name
    if target.is_symlink():
        raise ReplayOutputError("output file may not be a symbolic link")
    if target.parent.resolve(strict=True) != root:
        raise ReplayOutputError("output path escapes selected destination")

    payload = result.normalized_bytes()
    if target.exists():
        if not target.is_file() or target.read_bytes() != payload:
            raise ReplayOutputError("output conflict: existing content differs")
        return target

    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=root, prefix=".replay-", suffix=".tmp", delete=False
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(payload)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, target)
        temporary_name = None
    finally:
        if temporary_name is not None:
            Path(temporary_name).unlink(missing_ok=True)
    return target


def _git_output(repo_root: Path, args: Sequence[str], *, binary: bool = False) -> bytes:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=repo_root,
            check=True,
            capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ReplayEvidenceError("unable to establish Git revision evidence") from exc
    return result.stdout if binary else result.stdout.strip()


def build_replay_manifest(
    *,
    scenario_fixtures: Any,
    ohlcv_fixtures: Any,
    raw_signal_fixtures: Any,
    policy: Mapping[str, Any],
    initial_state: Mapping[str, Any],
    evaluation_time: str,
    trading_date: str,
    fixture_schema_version: int,
    repo_root: str | Path = ".",
    relevant_paths: Sequence[str] = ("trading_bot", "pyproject.toml", "uv.lock"),
) -> ReplayManifest:
    """Build the complete deterministic input envelope for a replay."""
    root = Path(repo_root).resolve()
    head = _git_output(root, ("rev-parse", "HEAD")).decode("utf-8")
    diff = _git_output(
        root,
        ("diff", "--no-ext-diff", "--binary", "HEAD", "--", *relevant_paths),
        binary=True,
    ).replace(b"\r\n", b"\n")
    # Freeze caller-owned structures through a canonical round trip.
    frozen_policy = json.loads(canonical_json_bytes(policy))
    frozen_state = json.loads(canonical_json_bytes(initial_state))
    return ReplayManifest(
        scenario_hash=_sha256(scenario_fixtures),
        ohlcv_hash=_sha256(ohlcv_fixtures),
        raw_signal_hash=_sha256(raw_signal_fixtures),
        policy=frozen_policy,
        head_commit=head,
        relevant_tracked_diff_hash=hashlib.sha256(diff).hexdigest(),
        code_state="dirty" if diff else "clean",
        initial_state=frozen_state,
        evaluation_time=evaluation_time,
        trading_date=trading_date,
        fixture_schema_version=fixture_schema_version,
    )


@dataclass(frozen=True)
class ReplayStep:
    ticker: str
    raw_signal: str
    current_price: float
    fill: str
    expected_action: str
    boundary_id: str
    expected_stage: str = "action"
    realized_loss_after: float | None = None


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
    expected_error: str | None = None


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


_INDICATOR_CONFIG_FIELDS = {
    "sma_short_window", "sma_long_window", "rsi_window", "atr_window",
    "historical_volatility_window", "volume_ratio_window",
}
_HISTORY_FIELDS = {
    "ticker", "market", "state", "trading_value", "health", "ohlcv",
}
_OHLCV_FIELDS = {"observed_at", "open", "high", "low", "close", "volume"}


def _indicator_config(policy: Mapping[str, Any]) -> IndicatorConfig:
    raw = policy.get("indicator_config")
    if not isinstance(raw, Mapping):
        raise ValueError("policy.indicator_config must be an object")
    _keys(raw, _INDICATOR_CONFIG_FIELDS, "indicator_config")
    values: dict[str, int] = {}
    for name in _INDICATOR_CONFIG_FIELDS:
        value = raw[name]
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise ValueError(f"indicator_config.{name} must be a positive integer")
        values[name] = value
    return IndicatorConfig(**values)


def _guard_market_history(
    records: Iterable[Mapping[str, Any]], cutoff: str
) -> tuple[Mapping[str, Any], ...]:
    guarded: list[Mapping[str, Any]] = []
    for record in records:
        guarded_historical_view(record["ohlcv"], cutoff)
        guarded.append(record)
    return tuple(guarded)


def _validate_market_history(
    records: Iterable[Mapping[str, Any]],
    indicator_config: IndicatorConfig,
) -> tuple[Mapping[str, Any], ...]:
    validated: list[Mapping[str, Any]] = []
    tickers: set[str] = set()
    minimum_rows = max(
        indicator_config.sma_short_window,
        indicator_config.sma_long_window,
        indicator_config.rsi_window,
        indicator_config.atr_window,
        indicator_config.volume_ratio_window,
        indicator_config.historical_volatility_window + 1,
    )
    for record in records:
        _keys(record, _HISTORY_FIELDS, "market_history record")
        ticker = str(record["ticker"])
        if not _TICKER.fullmatch(ticker):
            raise ValueError("invalid historical ticker")
        if ticker in tickers:
            raise ValueError("market_history ticker must be unique")
        tickers.add(ticker)
        _finite(record["trading_value"], "trading_value", minimum=0)
        if not isinstance(record["market"], str) or not isinstance(record["state"], str):
            raise ValueError("market and state must be strings")
        if not isinstance(record["health"], Mapping):
            raise ValueError("health must be an object")
        try:
            SourceStatus(record["health"].get("status", "AVAILABLE"))
        except ValueError as exc:
            raise ValueError("unsupported source health status") from exc

        rows = record["ohlcv"]
        if not isinstance(rows, list) or len(rows) < minimum_rows:
            raise ValueError(
                f"ticker {ticker} has insufficient warm-up: "
                f"{len(rows) if isinstance(rows, list) else 0} < {minimum_rows}"
            )
        observed_times: list[datetime] = []
        for row in rows:
            _keys(row, _OHLCV_FIELDS, "OHLCV row")
            observed = datetime.fromisoformat(str(row["observed_at"]))
            if observed.utcoffset() is None:
                raise ValueError("OHLCV observed_at must be timezone-aware")
            observed_times.append(observed)
            opening = _finite(row["open"], "open", minimum=0)
            high = _finite(row["high"], "high", minimum=0)
            low = _finite(row["low"], "low", minimum=0)
            close = _finite(row["close"], "close", minimum=0)
            _finite(row["volume"], "volume", minimum=0)
            if min(opening, high, low, close) <= 0:
                raise ValueError("OHLC prices must be positive")
            if high < max(opening, close) or low > min(opening, close) or high < low:
                raise ValueError("OHLC high/low consistency violation")
        if len(set(observed_times)) != len(observed_times):
            raise ValueError("OHLCV observed_at values must be unique")
        if observed_times != sorted(observed_times):
            raise ValueError("OHLCV observed_at values must be strictly increasing")
        validated.append(record)
    return tuple(validated)


def _ohlcv_frame(rows: Sequence[Mapping[str, Any]]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "시가": [row["open"] for row in rows],
            "고가": [row["high"] for row in rows],
            "저가": [row["low"] for row in rows],
            "종가": [row["close"] for row in rows],
            "거래량": [row["volume"] for row in rows],
        },
        index=pd.DatetimeIndex(
            [datetime.fromisoformat(str(row["observed_at"])) for row in rows]
        ),
    )


def load_replay_bundle(path: str | Path) -> tuple[ReplayScenario, ...]:
    """Load and strictly validate a versioned replay fixture bundle."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    _keys(data, {"schema_version", "boundaries", "scenarios"}, "bundle")
    if data["schema_version"] != SCHEMA_VERSION:
        raise ValueError("unsupported replay schema version")
    if set(data["boundaries"]) != REQUIRED_BOUNDARIES:
        raise ValueError("fixture boundary catalog is incomplete or unknown")
    scenarios = []
    scenario_fields = {"id", "mode", "trading_date", "evaluation_time", "policy", "initial_state", "market_history", "steps", "expected_error"}
    step_fields = {"ticker", "raw_signal", "current_price", "fill", "expected_action", "boundary_id", "expected_stage", "realized_loss_after"}
    state_fields = {"cash", "positions", "daily_loss"}
    for raw in data["scenarios"]:
        if set(raw) not in (scenario_fields, scenario_fields - {"expected_error"}):
            raise ValueError("scenario fields mismatch")
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
        indicator_config = _indicator_config(raw["policy"])
        history = _validate_market_history(raw["market_history"], indicator_config)
        expected_error = raw.get("expected_error")
        if expected_error not in {None, "FUTURE_DATA_ACCESS"}:
            raise ValueError("unsupported expected_error")
        if expected_error == "FUTURE_DATA_ACCESS":
            try:
                _guard_market_history(history, raw["evaluation_time"])
            except FutureDataAccessError:
                pass
            else:
                raise ValueError("future-access scenario must contain a future row")
        else:
            history = _guard_market_history(history, raw["evaluation_time"])
        steps = []
        for step in raw["steps"]:
            required_step_fields = step_fields - {"realized_loss_after", "expected_stage", "boundary_id"}
            if not required_step_fields.issubset(step) or not set(step).issubset(step_fields):
                raise ValueError("step fields mismatch")
            if not _TICKER.fullmatch(step["ticker"]): raise ValueError("invalid ticker")
            if not isinstance(step["raw_signal"], str): raise ValueError("raw_signal must be a string")
            if step["fill"] not in {"COMPLETE", "NONE"}: raise ValueError("unsupported fill")
            price = _finite(step["current_price"], "current_price", minimum=0)
            loss_after = step.get("realized_loss_after")
            if loss_after is not None:
                loss_after = _finite(loss_after, "realized_loss_after", minimum=0)
                if loss_after < daily_loss["realized_loss"]:
                    raise ValueError("realized_loss_after may not decrease")
                if loss_after > daily_loss["threshold"]:
                    raise ValueError("realized_loss_after may not exceed policy threshold")
            steps.append(ReplayStep(
                step["ticker"], step["raw_signal"], price, step["fill"],
                step["expected_action"], step.get("boundary_id", ""),
                step.get("expected_stage", "action"), loss_after,
            ))
        if raw["mode"] == "FULL_DAY" and any(s.realized_loss_after is None for s in steps):
            raise ValueError("FULL_DAY steps require explicit realized_loss_after")
        scenarios.append(ReplayScenario(raw["id"], raw["mode"], raw["trading_date"], raw["evaluation_time"], raw["policy"], cash, positions, daily_loss, history, tuple(steps), expected_error))
    return tuple(scenarios)


def _position(raw: Mapping[str, Any]) -> Position:
    return Position(Ticker(raw["ticker"]), int(raw["quantity"]), Money(float(raw["average_price"]), "KRW"))


def run_replay_scenarios(scenarios: Sequence[ReplayScenario]) -> tuple[ReplayOutcome, ...]:
    """Run frozen scenarios through production screening and execution seams."""
    outcomes: list[ReplayOutcome] = []
    for scenario in scenarios:
        try:
            history = _guard_market_history(
                scenario.market_history, scenario.evaluation_time
            )
        except FutureDataAccessError:
            if scenario.expected_error != "FUTURE_DATA_ACCESS" or len(scenario.steps) != 1:
                raise
            step = scenario.steps[0]
            outcomes.append(ReplayOutcome(
                scenario.scenario_id, step.ticker, 0, "REJECTED", False, "NONE",
                "future data access rejected", scenario.initial_cash, 0,
                step.expected_action, step.expected_action == "REJECTED",
                selected=False, blocked_reason="FUTURE_DATA_ACCESS",
                realized_loss_after=float(scenario.daily_loss["realized_loss"]),
                boundary_id=step.boundary_id, expected_stage=step.expected_stage,
            ))
            continue
        p = scenario.policy
        indicator_config = _indicator_config(p)
        screener = ScreenerConfig(int(p["max_candidates"]), tuple(p["markets"]), float(p["min_trading_value"]), float(p["min_volume_ratio"]), tuple(p["excluded_states"]))
        risk = RiskConfig(float(p["stop_loss_pct"]), float(p["take_profit_pct"]))
        execution = ExecutionConfig(float(p["buy_confidence_threshold"]), float(p["sell_confidence_threshold"]), float(p["buy_cash_fraction"]), float(p["max_position_value"]))
        broker = MockBroker(Money(scenario.initial_cash, "KRW"), [_position(x) for x in scenario.initial_positions])
        daily = DailyLossState(float(scenario.daily_loss["realized_loss"]), float(scenario.daily_loss["threshold"]))
        by_ticker = {s.ticker: s for s in scenario.steps}
        history_by_ticker = {str(record["ticker"]): record for record in history}
        rows = []
        for step in scenario.steps:
            if step.ticker not in history_by_ticker:
                raise ValueError(f"missing historical screener input for ticker {step.ticker}")
            record = history_by_ticker[step.ticker]
            indicator_result = calculate_technicals(
                _ohlcv_frame(record["ohlcv"]), indicator_config
            )
            health_raw = record["health"]
            fixture_health = SourceHealth(
                source="fixture",
                status=SourceStatus(health_raw.get("status", "AVAILABLE")),
                reason=health_raw.get("reason", "fixture"),
                observed_date=health_raw.get("observed_date", scenario.trading_date),
                expected_date=scenario.trading_date,
            )
            health = (
                fixture_health
                if fixture_health.status is not SourceStatus.AVAILABLE
                else indicator_result.health
            )
            rows.append({
                "ticker": record["ticker"],
                "market": record["market"],
                "state": record["state"],
                "trading_value": record["trading_value"],
                "technicals": dict(indicator_result.technicals),
                "health": health,
            })
        screening = screen_candidates(scenario.trading_date, rows, screener)
        selected = screening.candidates
        selected_tickers = {candidate.ticker for candidate in selected}
        for step in scenario.steps:
            if step.ticker not in selected_tickers:
                outcomes.append(ReplayOutcome(
                    scenario.scenario_id, step.ticker, 0, "HOLD", False, "NONE",
                    "excluded by production screener", broker.cash.amount, 0,
                    step.expected_action, step.expected_action == "HOLD",
                    selected=False, blocked_reason="SCREENER_EXCLUDED",
                    realized_loss_after=daily.realized_loss,
                    boundary_id=step.boundary_id, expected_stage=step.expected_stage,
                ))
        for rank, candidate in enumerate(selected, 1):
            step = by_ticker[candidate.ticker]
            result = execute_signal_cycle(step.raw_signal, Ticker(step.ticker), Money(step.current_price, "KRW"), broker.cash.amount, broker, execution, risk, daily, dry_run=True)
            if step.fill == "COMPLETE" and result.order is not None:
                broker.place_order(result.order)
            held = broker.get_position(Ticker(step.ticker))
            action = result.action.value
            audit = result.audit
            buy_signaled = bool(audit and audit.parsed_decision == "BUY")
            confidence_qualified = bool(
                buy_signaled and result.confidence is not None
                and result.confidence >= execution.buy_confidence_threshold
            )
            risk_qualified = bool(confidence_qualified and action == "BUY")
            validly_sized = bool(risk_qualified and result.order is not None)
            blocked_reason = None
            if audit and audit.parse_error:
                blocked_reason = "MALFORMED_SIGNAL"
            elif buy_signaled and not confidence_qualified:
                blocked_reason = "LOW_CONFIDENCE"
            elif confidence_qualified and not risk_qualified:
                blocked_reason = "RISK_BLOCK"
            elif risk_qualified and not validly_sized:
                blocked_reason = "INVALID_SIZE"
            outcomes.append(ReplayOutcome(
                scenario.scenario_id, step.ticker, rank, action,
                result.order is not None, step.fill, result.reason,
                broker.cash.amount, held.quantity if held else 0,
                step.expected_action, action == step.expected_action,
                True, buy_signaled, confidence_qualified, risk_qualified,
                validly_sized, validly_sized, blocked_reason,
                step.realized_loss_after if step.realized_loss_after is not None else daily.realized_loss,
                step.boundary_id, step.expected_stage,
            ))
            if step.realized_loss_after is not None:
                if step.realized_loss_after < daily.realized_loss:
                    raise ValueError("realized_loss_after may not decrease")
                daily = DailyLossState(step.realized_loss_after, daily.threshold)
    return tuple(outcomes)
