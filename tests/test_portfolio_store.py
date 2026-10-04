from __future__ import annotations

import sqlite3
from datetime import date, datetime, timezone

import pytest

from trading_bot.audit_models import DailyEvaluationEventType, DailyEvaluationStatus
from trading_bot.portfolio import (
    DivergenceSeverity,
    PortfolioAccountSummary,
    PortfolioCompleteness,
    PortfolioDivergence,
    PortfolioFill,
    PortfolioHolding,
    PortfolioOrder,
    PortfolioSnapshot,
)
from trading_bot.portfolio_store import (
    append_daily_evaluation_event,
    append_portfolio_snapshot,
    connect_portfolio_store,
    load_daily_evaluation,
    migrate_portfolio,
    recover_started_evaluations,
    start_daily_evaluation,
)


NOW = datetime(2026, 9, 4, 1, 0, tzinfo=timezone.utc)


def snapshot() -> PortfolioSnapshot:
    return PortfolioSnapshot(
        snapshot_id="snapshot-1",
        account_scope_hash="scope-sha256",
        trading_date=date(2026, 9, 4),
        previous_trading_date=date(2026, 9, 3),
        observed_at=NOW,
        completeness=PortfolioCompleteness.COMPLETE,
        reason_code="COMPLETE",
        daily_page_count=2,
        balance_page_count=1,
        holdings=(PortfolioHolding("005930", 3, 2, 70000),),
        orders=(
            PortfolioOrder(
                "ORDER-1", None, "005930", "SELL", 1, 0, 1, 0, 0,
                71000, "NO_FILL", "20260904", "100000",
            ),
        ),
        fills=(PortfolioFill("FILL-1", "ORDER-0", "005930", 1, 69000),),
        account=PortfolioAccountSummary(1000000, 1210000),
        divergences=(
            PortfolioDivergence("HOLDING_DRIFT", DivergenceSeverity.WARNING, "005930"),
        ),
    )


def test_snapshot_facts_are_append_only_and_immediately_visible(tmp_path):
    path = tmp_path / "audit.db"
    conn = connect_portfolio_store(path)

    append_portfolio_snapshot(
        conn, snapshot(), cycle_id="cycle-1", observation_id="observation-1"
    )

    observer = sqlite3.connect(path)
    assert observer.execute("SELECT COUNT(*) FROM portfolio_snapshots").fetchone()[0] == 1
    assert observer.execute("SELECT ticker, total_quantity FROM portfolio_holdings").fetchone() == ("005930", 3)
    assert observer.execute("SELECT status, remaining_quantity FROM portfolio_orders").fetchone() == ("NO_FILL", 1)
    assert observer.execute("SELECT code, severity FROM portfolio_divergences").fetchone() == ("HOLDING_DRIFT", "WARNING")
    with pytest.raises(sqlite3.IntegrityError):
        append_portfolio_snapshot(
            conn, snapshot(), cycle_id="cycle-2", observation_id="observation-2"
        )


def test_daily_identity_is_unique_and_canonical_input_is_immutable(tmp_path):
    path = tmp_path / "audit.db"
    first_conn = connect_portfolio_store(path)
    second_conn = connect_portfolio_store(path)

    first = start_daily_evaluation(
        first_conn,
        trading_date_kst=date(2026, 9, 4),
        ticker="005930",
        provenance=("HELD", "SCREENED"),
        canonical_input=b'{"ticker":"005930"}',
        account_scope_hash="scope-sha256",
        observed_at=NOW,
    )
    second = start_daily_evaluation(
        second_conn,
        trading_date_kst=date(2026, 9, 4),
        ticker="005930",
        provenance=("SCREENED",),
        canonical_input=b'{"different":true}',
        account_scope_hash="scope-sha256",
        observed_at=NOW,
    )

    assert second.evaluation_id == first.evaluation_id
    loaded = load_daily_evaluation(second_conn, first.evaluation_id)
    assert loaded.canonical_input == b'{"ticker":"005930"}'
    assert loaded.status is DailyEvaluationStatus.STARTED
    assert second_conn.execute("SELECT COUNT(*) FROM daily_evaluations").fetchone()[0] == 1


def test_recovery_refuses_mutation_without_active_scoped_owner(tmp_path):
    conn = connect_portfolio_store(tmp_path / "audit.db")
    evaluation = start_daily_evaluation(
        conn,
        trading_date_kst=date(2026, 9, 4), ticker="005930",
        provenance=("HELD",), canonical_input=b"canonical",
        account_scope_hash="scope", observed_at=NOW,
    )

    with pytest.raises(RuntimeError, match="owner"):
        recover_started_evaluations(conn, observed_at=NOW)

    loaded = load_daily_evaluation(conn, evaluation.evaluation_id)
    assert loaded.status is DailyEvaluationStatus.STARTED
    assert len(loaded.events) == 1


def test_terminal_event_is_once_only_and_invalid_detail_rolls_back(tmp_path):
    conn = connect_portfolio_store(tmp_path / "audit.db")
    evaluation = start_daily_evaluation(
        conn,
        trading_date_kst=date(2026, 9, 4), ticker="005930",
        provenance=("HELD",), canonical_input=b"canonical",
        account_scope_hash="scope", observed_at=NOW,
    )
    with pytest.raises(ValueError, match="forbidden"):
        append_daily_evaluation_event(
            conn, evaluation.evaluation_id,
            event_type=DailyEvaluationEventType.PROVIDER_ATTEMPT,
            detail={"raw_payload": "secret"}, observed_at=NOW,
        )
    assert conn.execute("SELECT COUNT(*) FROM daily_evaluation_events").fetchone()[0] == 1

    append_daily_evaluation_event(
        conn, evaluation.evaluation_id,
        event_type=DailyEvaluationEventType.SIGNAL_FINALIZED,
        action="SELL", confidence=0.91, reason_code="MODEL_SELL",
        detail={"attempt": 1}, observed_at=NOW,
    )
    with pytest.raises(ValueError, match="already finalized"):
        append_daily_evaluation_event(
            conn, evaluation.evaluation_id,
            event_type=DailyEvaluationEventType.SIGNAL_FINALIZED,
            action="HOLD", reason_code="SECOND_FINAL", observed_at=NOW,
        )


def test_portfolio_migration_failure_rolls_back_and_retry_succeeds(tmp_path):
    path = tmp_path / "audit.db"
    conn = sqlite3.connect(path)
    with pytest.raises(RuntimeError, match="injected"):
        migrate_portfolio(conn, fail_after_step="snapshots")
    assert conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE name LIKE 'portfolio_%'"
    ).fetchone()[0] == 0

    migrate_portfolio(conn)
    assert conn.execute(
        "SELECT version FROM portfolio_schema_metadata WHERE owner='phase11'"
    ).fetchone()[0] == 4
    expected = {
        "portfolio_snapshots", "portfolio_holdings", "portfolio_orders",
        "portfolio_fills", "portfolio_divergences", "daily_evaluations",
        "daily_evaluation_events", "watch_iterations", "watch_observations",
        "transition_states", "mutation_leases", "mutation_lease_events",
    }
    actual = {
        row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }
    assert expected <= actual


# Synthetic evidence and temporary journals only; these do not activate trading.
def _dispatch_api():
    from trading_bot import portfolio_store as store
    from trading_bot.audit_models import DailyDispatchState
    assert store.SCHEMA_VERSION == 4
    return store, DailyDispatchState


def _envelope(prompt=b"frozen-first-input"):
    import hashlib
    from trading_bot.service_models import DailyDispatchEnvelope
    return DailyDispatchEnvelope(prompt_bytes=prompt,
        prompt_hash=hashlib.sha256(prompt).hexdigest(), system_prompt="synthetic system",
        schema_hash="b" * 64, provider="openai", model="synthetic-model",
        temperature=0, prompt_version="synthetic-v1")


def _owner(conn, tmp_path, scope="a" * 64):
    from trading_bot.mutation_lease import acquire_mutation_lease
    return acquire_mutation_lease(conn, account_scope_hash=scope,
        lock_dir=tmp_path / "locks", command="synthetic-test", cycle_id="synthetic-cycle",
        observed_at=NOW)


def _start(conn, owner, *, ticker="005930", envelope=None, **overrides):
    envelope = envelope or _envelope()
    values = dict(trading_date_kst=NOW.date(), ticker=ticker, provenance=("HELD",),
        canonical_input=envelope.prompt_bytes, account_scope_hash=owner.account_scope_hash,
        observed_at=NOW, execution_target="mock", envelope=envelope, lease=owner)
    return start_daily_evaluation(conn, **(values | overrides))


def _early():
    return NOW.replace(hour=0, minute=19, second=59)


def _deadline():
    return NOW.replace(hour=0, minute=20)


def test_first_envelope_and_scope_target_are_immutable_and_claim_consumes(tmp_path):
    store, state = _dispatch_api()
    path = tmp_path / "audit.db"
    conn = connect_portfolio_store(path)
    with _owner(conn, tmp_path) as owner:
        first = _start(conn, owner, observed_at=_early())
        again = _start(conn, owner, envelope=_envelope(b"replacement"))
        assert again.evaluation_id == first.evaluation_id
        saved = store.load_daily_dispatch(conn, first.evaluation_id)
        assert saved["envelope_hash"] == _envelope().envelope_hash
        assert again.canonical_input == _envelope().prompt_bytes
        assert saved["dispatch_state"] == state.NEVER_DISPATCHED
        consumed = store.claim_daily_dispatch(conn, first.evaluation_id, owner, _early(), _deadline())
        assert consumed["dispatch_state"] == state.DISPATCHED
        assert consumed["dispatch_id"] and consumed["dispatched_at"] == _early().isoformat()
        observer = sqlite3.connect(path)
        assert store.load_daily_dispatch(observer, first.evaluation_id) == consumed
        observer.close()
        with pytest.raises(RuntimeError, match="dispatch"):
            store.claim_daily_dispatch(conn, first.evaluation_id, owner, _early(), _deadline())
        with pytest.raises(RuntimeError, match="scope|target"):
            _start(conn, owner, execution_target="real")
        with pytest.raises(RuntimeError, match="scope|target"):
            _start(conn, owner, account_scope_hash="c" * 64)
        owner.release(observed_at=NOW)


@pytest.mark.parametrize("stamp", [_deadline(), NOW, NOW.replace(day=5, hour=0, minute=0)])
def test_exact_cutoff_and_date_do_not_dispatch(tmp_path, stamp):
    store, state = _dispatch_api()
    conn = connect_portfolio_store(tmp_path / "audit.db")
    with _owner(conn, tmp_path) as owner:
        evaluation = _start(conn, owner, observed_at=_early())
        with pytest.raises(RuntimeError, match="deadline|date|expired"):
            store.claim_daily_dispatch(conn, evaluation.evaluation_id, owner, stamp, _deadline())
        saved = store.load_daily_dispatch(conn, evaluation.evaluation_id)
        assert saved["dispatch_state"] == state.NEVER_DISPATCHED
        assert saved["dispatch_id"] is None


def test_recovery_retains_never_dispatched_then_expires_and_unknown_never_replays(tmp_path):
    store, state = _dispatch_api()
    conn = connect_portfolio_store(tmp_path / "audit.db")
    with _owner(conn, tmp_path) as owner:
        first = _start(conn, owner, observed_at=_early())
        second = _start(conn, owner, ticker="000001", observed_at=_early())
        consumed = store.claim_daily_dispatch(conn, second.evaluation_id, owner, _early(), _deadline())
        rows = store.recover_daily_dispatches(conn, lease=owner,
            account_scope_hash=owner.account_scope_hash, execution_target="mock",
            trading_date_kst=NOW.date(), now=_early(), deadline=_deadline())
        assert {r["evaluation_id"]: r["dispatch_state"] for r in rows} == {
            first.evaluation_id: state.NEVER_DISPATCHED, second.evaluation_id: state.DISPATCHED_UNKNOWN}
        unknown = store.load_daily_dispatch(conn, second.evaluation_id)
        assert unknown["dispatch_id"] == consumed["dispatch_id"]
        terminal = load_daily_evaluation(conn, second.evaluation_id)
        assert terminal.status == DailyEvaluationStatus.FINALIZED
        assert terminal.events[-1].action == "HOLD"
        assert terminal.events[-1].reason_code == "LLM_UNAVAILABLE"
        store.recover_daily_dispatches(conn, lease=owner,
            account_scope_hash=owner.account_scope_hash, execution_target="mock",
            trading_date_kst=NOW.date(), now=_deadline(), deadline=_deadline())
        assert store.load_daily_dispatch(conn, first.evaluation_id)["dispatch_state"] == state.EXPIRED_NEVER_DISPATCHED
        with pytest.raises(RuntimeError, match="dispatch"):
            store.claim_daily_dispatch(conn, second.evaluation_id, owner, _early(), _deadline())


def test_all_dispatch_mutations_require_real_active_same_store_owner(tmp_path):
    store, _ = _dispatch_api()
    conn = connect_portfolio_store(tmp_path / "audit.db")
    with _owner(conn, tmp_path) as owner:
        evaluation = _start(conn, owner, observed_at=_early())
        for bad in (None, object()):
            with pytest.raises(RuntimeError, match="owner"):
                store.claim_daily_dispatch(conn, evaluation.evaluation_id, bad, _early(), _deadline())
        with pytest.raises(RuntimeError, match="scope"):
            store.recover_daily_dispatches(conn, lease=owner, account_scope_hash="c" * 64,
                execution_target="mock", trading_date_kst=NOW.date(), now=_early(), deadline=_deadline())
        other = connect_portfolio_store(tmp_path / "other.db")
        with pytest.raises(RuntimeError, match="owner"):
            store.claim_daily_dispatch(other, evaluation.evaluation_id, owner, _early(), _deadline())
        owner.release(observed_at=NOW)
        with pytest.raises(RuntimeError, match="owner"):
            store.finalize_daily_dispatch(conn, evaluation.evaluation_id, lease=owner,
                now=_early(), action="HOLD", confidence=0, reason_code="LLM_UNAVAILABLE", unknown=True)


def _legacy_db(conn, version=3):
    from trading_bot import portfolio_store as store
    for statement in store._SCHEMA:
        conn.execute(statement)
    if version == 3:
        for statement in store._LEASE_SCHEMA:
            conn.execute(statement)
    conn.execute("INSERT INTO portfolio_schema_metadata VALUES('phase11',?)", (version,))
    conn.execute("PRAGMA user_version=3")
    conn.execute("INSERT INTO daily_evaluations VALUES('legacy','2026-09-04','005930','[\"HELD\"]',?,?,'a' || ?, 'STARTED',?,NULL)",
        (b"legacy-exact-bytes", "d" * 64, "a" * 63, NOW.isoformat()))
    conn.execute("INSERT INTO daily_evaluation_events(evaluation_id,event_type,detail_json,observed_at) VALUES('legacy','PROVIDER_ATTEMPT','{}',?)", (NOW.isoformat(),))
    conn.commit()


@pytest.mark.parametrize("version", [1, 2, 3])
def test_legacy_attempts_never_replay_and_migration_preserves_old_facts(tmp_path, version):
    store, state = _dispatch_api()
    conn = sqlite3.connect(tmp_path / "legacy.db")
    _legacy_db(conn, version)
    before = tuple(conn.execute("SELECT * FROM daily_evaluations")), tuple(conn.execute("SELECT * FROM daily_evaluation_events"))
    migrate_portfolio(conn)
    migrate_portfolio(conn)
    assert (tuple(conn.execute("SELECT * FROM daily_evaluations")), tuple(conn.execute("SELECT * FROM daily_evaluation_events"))) == before
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 3
    assert store.load_daily_dispatch(conn, "legacy")["dispatch_state"] == state.DISPATCHED_UNKNOWN
    with _owner(conn, tmp_path) as owner:
        with pytest.raises(RuntimeError, match="dispatch"):
            store.claim_daily_dispatch(conn, "legacy", owner, _early(), _deadline())


def test_v4_migration_rolls_back_all_additions_and_foreign_owner_fails(tmp_path):
    store, _ = _dispatch_api()
    conn = sqlite3.connect(tmp_path / "legacy.db")
    _legacy_db(conn)
    before = tuple(conn.execute("SELECT type,name,sql FROM sqlite_master ORDER BY name"))
    with pytest.raises(RuntimeError, match="injected"):
        migrate_portfolio(conn, fail_after_step="dispatches")
    assert tuple(conn.execute("SELECT type,name,sql FROM sqlite_master ORDER BY name")) == before
    assert conn.execute("SELECT version FROM portfolio_schema_metadata").fetchone()[0] == 3
    conn.execute("UPDATE portfolio_schema_metadata SET owner='foreign'")
    conn.commit()
    with pytest.raises(RuntimeError, match="owner"):
        migrate_portfolio(conn)


def test_missing_legacy_authority_and_scope_collisions_fail_closed(tmp_path):
    store, state = _dispatch_api()
    conn = connect_portfolio_store(tmp_path / "audit.db")
    legacy = start_daily_evaluation(conn, trading_date_kst=NOW.date(), ticker="005930",
        provenance=("HELD",), canonical_input=b"old", account_scope_hash="a" * 64, observed_at=NOW)
    assert store.load_daily_dispatch(conn, legacy.evaluation_id)["dispatch_state"] == state.BLOCKED_LEGACY
    with _owner(conn, tmp_path) as owner:
        with pytest.raises(RuntimeError, match="legacy|target"):
            _start(conn, owner, observed_at=_early())
        with pytest.raises(RuntimeError, match="dispatch"):
            store.claim_daily_dispatch(conn, legacy.evaluation_id, owner, _early(), _deadline())


def test_frozen_envelope_tampering_and_wrong_deadline_refuse_recovery(tmp_path):
    store, _ = _dispatch_api()
    conn = connect_portfolio_store(tmp_path / "audit.db")
    with _owner(conn, tmp_path) as owner:
        evaluation = _start(conn, owner, observed_at=_early())
        with pytest.raises(RuntimeError, match="deadline"):
            store.claim_daily_dispatch(conn, evaluation.evaluation_id, owner, _early(), NOW)
        # A corrupt durable source cannot authorize a call even when the owner is current.
        conn.execute("DROP TRIGGER immutable_daily_dispatch_envelope")
        conn.execute("UPDATE daily_evaluation_dispatches SET envelope_hash=?", ("c" * 64,))
        conn.commit()
        with pytest.raises(RuntimeError, match="envelope"):
            store.claim_daily_dispatch(conn, evaluation.evaluation_id, owner, _early(), _deadline())


def test_scoped_concurrent_claim_has_one_winner_and_terminal_cannot_reset(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    store, state = _dispatch_api()
    path = tmp_path / "audit.db"
    conn = connect_portfolio_store(path)
    with _owner(conn, tmp_path) as owner:
        evaluation = _start(conn, owner, observed_at=_early())
        # After the real owner's outer check, independent connections serialize the
        # durable token recheck and claim; no external call occurs in this test.
        owner.assert_active_owner(observed_at=_early())
        def claim():
            from unittest.mock import patch
            connection = sqlite3.connect(path)
            try:
                with patch.object(owner, 'assert_active_owner'):
                    try:
                        return store.claim_daily_dispatch(connection, evaluation.evaluation_id,
                            owner, _early(), _deadline())["dispatch_id"]
                    except RuntimeError:
                        return None
            finally:
                connection.close()
        # Sharing a real lease's SQLite handle across threads is forbidden. The
        # helper's provenance lookup is read-only, so allow that test handle only.
        shared = sqlite3.connect(path, check_same_thread=False)
        owner._conn = shared
        try:
            with ThreadPoolExecutor(max_workers=2) as pool:
                results = list(pool.map(lambda _: claim(), range(2)))
            assert sum(value is not None for value in results) == 1
        finally:
            owner._conn = conn
            shared.close()
        final = store.finalize_daily_dispatch(conn, evaluation.evaluation_id, lease=owner,
            now=_early(), action="HOLD", confidence=0.5, reason_code="MODEL_HOLD")
        assert final["dispatch_state"] == state.FINALIZED
        assert final["execution_intent_id"] is None
        with pytest.raises(RuntimeError, match="consumed"):
            store.finalize_daily_dispatch(conn, evaluation.evaluation_id, lease=owner, now=_early())
        with pytest.raises(sqlite3.IntegrityError, match="reset"):
            conn.execute("UPDATE daily_evaluation_dispatches SET dispatch_state='NEVER_DISPATCHED'")
        conn.rollback()
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            conn.execute("UPDATE daily_evaluations SET canonical_input=?", (b"replaced",))
        conn.rollback()


def test_unknown_versions_and_legacy_finalized_classification(tmp_path):
    store, state = _dispatch_api()
    conn = sqlite3.connect(tmp_path / "legacy.db")
    _legacy_db(conn)
    conn.execute("UPDATE daily_evaluations SET status='FINALIZED',finalized_at=?", (NOW.isoformat(),))
    conn.commit()
    migrate_portfolio(conn)
    assert store.load_daily_dispatch(conn, 'legacy')["dispatch_state"] == state.FINALIZED
    conn.execute("UPDATE portfolio_schema_metadata SET version=999")
    conn.commit()
    with pytest.raises(RuntimeError, match="version"):
        migrate_portfolio(conn)
