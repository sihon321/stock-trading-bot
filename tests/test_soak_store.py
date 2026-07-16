"""Durability and state-machine tests for the independent soak ledger."""

from __future__ import annotations

import sqlite3

import pytest

from trading_bot.soak_models import CampaignKind, CampaignState, FreezeState


def _campaign(store, *, campaign_id: str = "campaign-1") -> None:
    store.create_campaign(
        campaign_id=campaign_id,
        accepted_profile_fingerprint="sha256:approved-profile",
        accepted_profile_version="official-example-v1",
        field_contract_version="kis-mock-compat-v1",
        ambiguity_policy_version="ambiguity-v1",
        ambiguity_window_seconds=60,
        ambiguity_poll_cadence_seconds=5,
        ambiguity_max_observations=12,
    )


def test_migration_is_idempotent_and_reopen_preserves_schema(tmp_path) -> None:
    from trading_bot import soak_store

    path = tmp_path / "soak.db"
    first = soak_store.connect_soak_store(path)
    assert first.execute("PRAGMA user_version").fetchone()[0] == soak_store.SOAK_SCHEMA_VERSION
    assert first.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    tables = {
        row[0]
        for row in first.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'soak_%'"
        )
    }
    assert tables == {
        "soak_campaigns", "soak_identity_receipts", "soak_days", "soak_events",
        "soak_snapshots", "soak_snapshot_orders", "soak_snapshot_fills",
        "soak_snapshot_holdings", "soak_snapshot_accounts", "soak_comparisons",
        "soak_ambiguity_observations", "soak_ticker_freezes", "soak_drill_links",
    }
    first.close()
    reopened = soak_store.connect_soak_store(path)
    assert reopened.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_migration_failure_rolls_back_atomically(tmp_path) -> None:
    from trading_bot import soak_store

    path = tmp_path / "soak.db"
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys=ON")
    with pytest.raises(RuntimeError, match="injected"):
        soak_store.migrate_soak_store(conn, fail_after_step="snapshots")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 0
    assert conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'soak_%'"
    ).fetchall() == []
    conn.close()
    assert soak_store.connect_soak_store(path).execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_immutable_campaign_policy_and_terminal_failure_are_database_enforced(tmp_path) -> None:
    from trading_bot import soak_store

    conn = soak_store.connect_soak_store(tmp_path / "soak.db")
    _campaign(soak_store.bind(conn))
    immutable_columns = {
        "target_eligible_days": 21,
        "availability_failure_budget": 3,
        "accepted_profile_fingerprint": "sha256:other",
        "field_contract_version": "other",
        "ambiguity_policy_version": "other",
        "ambiguity_window_seconds": 99,
        "ambiguity_poll_cadence_seconds": 9,
        "ambiguity_max_observations": 99,
    }
    for column, value in immutable_columns.items():
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(f"UPDATE soak_campaigns SET {column}=? WHERE campaign_id='campaign-1'", (value,))
    conn.execute(
        "UPDATE soak_campaigns SET state='FAILED', safety_failure_code='D09_DUPLICATE_ORDER' "
        "WHERE campaign_id='campaign-1'"
    )
    conn.commit()
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE soak_campaigns SET state='ACTIVE' WHERE campaign_id='campaign-1'")


def test_proof_campaign_is_immutable_and_permanently_non_credit(tmp_path) -> None:
    from trading_bot import soak_store
    from trading_bot.soak_reconcile import AmbiguityPolicy

    conn = soak_store.connect_soak_store(tmp_path / "soak.db")
    policy = AmbiguityPolicy("ambiguity-v1", 60, 5, 12, "official-example-v1", "kis-mock-compat-v1")
    created = soak_store.create_or_load_proof_campaign(
        conn,
        campaign_id="proof-1",
        accepted_profile_fingerprint="sha256:approved-profile",
        accepted_profile_version="official-example-v1",
        field_contract_version="kis-mock-compat-v1",
        ambiguity_policy=policy,
    )
    assert created["campaign_kind"] is CampaignKind.PROOF_ORDER
    assert created["credit_eligible"] is False
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE soak_campaigns SET credit_eligible=1 WHERE campaign_id='proof-1'")
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE soak_campaigns SET campaign_kind='SOAK' WHERE campaign_id='proof-1'")
    with pytest.raises(ValueError, match="immutable proof campaign"):
        soak_store.create_or_load_proof_campaign(
            conn,
            campaign_id="proof-1",
            accepted_profile_fingerprint="sha256:approved-profile",
            accepted_profile_version="official-example-v1",
            field_contract_version="kis-mock-compat-v1",
            ambiguity_policy=AmbiguityPolicy("ambiguity-v2", 60, 5, 12, "official-example-v1", "kis-mock-compat-v1"),
        )


def test_append_only_evidence_is_committed_sanitized_and_ordered(tmp_path) -> None:
    from trading_bot import soak_store

    path = tmp_path / "soak.db"
    conn = soak_store.connect_soak_store(path)
    _campaign(soak_store.bind(conn))
    first = soak_store.append_campaign_event(
        conn, campaign_id="campaign-1", event_code="CAMPAIGN_STARTED", detail={"attempt": 1}
    )
    second = soak_store.append_campaign_event(
        conn, campaign_id="campaign-1", event_code="PREFLIGHT_PASSED", detail={"attempt": 2}
    )
    assert first < second
    observer = sqlite3.connect(path)
    assert observer.execute("SELECT event_code FROM soak_events ORDER BY id").fetchall() == [
        ("CAMPAIGN_STARTED",), ("PREFLIGHT_PASSED",)
    ]
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute("UPDATE soak_events SET event_code='ERASED' WHERE id=?", (first,))
    with pytest.raises(ValueError, match="forbidden"):
        soak_store.append_campaign_event(
            conn, campaign_id="campaign-1", event_code="BAD", detail={"access_token": "x"}
        )
    assert conn.execute("SELECT COUNT(*) FROM soak_events").fetchone()[0] == 2


def test_unique_designated_day_and_snapshot_survive_second_connection(tmp_path) -> None:
    from trading_bot import soak_store

    path = tmp_path / "soak.db"
    conn = soak_store.connect_soak_store(path)
    _campaign(soak_store.bind(conn))
    soak_store.designate_day(
        conn, campaign_id="campaign-1", trading_date="2026-07-16", run_id="run-1",
        run_kind="RUN", terminal=True,
    )
    with pytest.raises(sqlite3.IntegrityError):
        soak_store.designate_day(
            conn, campaign_id="campaign-1", trading_date="2026-07-16", run_id="run-2",
            run_kind="RUN", terminal=True,
        )
    snapshot_id = soak_store.append_snapshot(
        conn, snapshot_id="snapshot-1", campaign_id="campaign-1", run_id="run-1",
        stage="PRE_RUN", ticker="005930",
        orders=[{"observation_id": "order-1", "order_id": "broker-1", "status": "OPEN", "remaining_qty": 1}],
        fills=[], holdings=[{"ticker": "005930", "quantity": 1}],
        accounts=[{"available_cash": 1000}], detail={"page_count": 1},
    )
    observer = soak_store.connect_soak_store(path)
    loaded = soak_store.read_snapshot(observer, snapshot_id=snapshot_id)
    assert loaded["snapshot"]["snapshot_id"] == "snapshot-1"
    assert loaded["orders"][0]["observation_id"] == "order-1"
    assert loaded["holdings"][0]["ticker"] == "005930"
    with pytest.raises(sqlite3.IntegrityError):
        soak_store.append_snapshot(
            conn, snapshot_id="snapshot-2", campaign_id="campaign-1", run_id="run-1",
            stage="PRE_RUN", orders=[{"observation_id": "order-1"}],
        )


def test_campaign_state_enum_is_reconstructed(tmp_path) -> None:
    from trading_bot import soak_store

    conn = soak_store.connect_soak_store(tmp_path / "soak.db")
    _campaign(soak_store.bind(conn))
    loaded = soak_store.load_campaign_state(conn, campaign_id="campaign-1")
    assert loaded["state"] is CampaignState.ACTIVE
    assert FreezeState.FROZEN.value == "FROZEN"


def test_campaign_defaults_budget_and_safety_failure_are_independent(tmp_path) -> None:
    from trading_bot import soak_store

    path = tmp_path / "soak.db"
    conn = soak_store.connect_soak_store(path)
    _campaign(soak_store.bind(conn))
    initial = soak_store.load_campaign_state(conn, campaign_id="campaign-1")
    assert initial["target_eligible_days"] == 20
    assert initial["availability_failure_budget"] == 2

    assert soak_store.consume_availability_failure(
        conn, campaign_id="campaign-1", reason_code="KIS_UNAVAILABLE", run_id="run-1"
    )["state"] is CampaignState.ACTIVE
    assert soak_store.consume_availability_failure(
        conn, campaign_id="campaign-1", reason_code="LLM_UNAVAILABLE", run_id="run-2"
    )["state"] is CampaignState.ACTIVE
    exceeded = soak_store.consume_availability_failure(
        conn, campaign_id="campaign-1", reason_code="DATA_UNAVAILABLE", run_id="run-3"
    )
    assert exceeded["state"] is CampaignState.FAILED
    assert exceeded["safety_failure_code"] is None
    assert exceeded["availability_failure_code"] == "D08_BUDGET_EXCEEDED"

    other = "campaign-safety"
    _campaign(soak_store.bind(conn), campaign_id=other)
    failed = soak_store.latch_safety_failure(
        conn, campaign_id=other, reason_code="D09_BLIND_POST_RETRY", run_id="run-x"
    )
    assert failed["state"] is CampaignState.FAILED
    assert failed["availability_failures_used"] == 0
    assert failed["safety_failure_code"] == "D09_BLIND_POST_RETRY"
    reopened = soak_store.connect_soak_store(path)
    assert soak_store.load_campaign_state(reopened, campaign_id=other)["state"] is CampaignState.FAILED
    with pytest.raises(ValueError, match="not active"):
        soak_store.consume_availability_failure(
            reopened, campaign_id=other, reason_code="KIS_UNAVAILABLE"
        )


def test_freeze_transition_matrix_requires_determinate_terminal_broker_evidence(tmp_path) -> None:
    from trading_bot import soak_store

    conn = soak_store.connect_soak_store(tmp_path / "soak.db")
    _campaign(soak_store.bind(conn))
    frozen_id = soak_store.freeze_ticker(
        conn, freeze_id="freeze-1", campaign_id="campaign-1", ticker="005930",
        order_intent_id="intent-1", freeze_kind="AMBIGUITY",
        detail={"reason_code": "AMBIGUOUS_SUBMISSION"},
    )
    assert frozen_id > 0
    cases = [
        ("obs-inconclusive", "MULTIPLE_OR_INCONCLUSIVE", False),
        ("obs-one-open", "ONE_MATCH_DETERMINATE", False),
    ]
    for observation_id, verdict, terminal in cases:
        soak_store.append_ambiguity_observation(
            conn, observation_id=observation_id, campaign_id="campaign-1", run_id="run-1",
            ticker="005930", order_intent_id="intent-1", verdict=verdict,
            remaining_order_terminal=terminal,
        )
        with pytest.raises(ValueError, match="determinate terminal"):
            soak_store.transition_freeze(
                conn, freeze_id="freeze-1", release_evidence_type="AMBIGUITY_OBSERVATION",
                release_evidence_id=observation_id,
            )

    soak_store.append_ambiguity_observation(
        conn, observation_id="obs-terminal", campaign_id="campaign-1", run_id="run-2",
        ticker="005930", order_intent_id="intent-1", verdict="ONE_MATCH_DETERMINATE",
        remaining_order_terminal=True,
    )
    released_id = soak_store.transition_freeze(
        conn, freeze_id="freeze-1", release_evidence_type="AMBIGUITY_OBSERVATION",
        release_evidence_id="obs-terminal", detail={"broker_status": "CANCELLED"},
    )
    assert released_id > frozen_id
    with pytest.raises(ValueError, match="already released"):
        soak_store.transition_freeze(
            conn, freeze_id="freeze-1", release_evidence_type="AMBIGUITY_OBSERVATION",
            release_evidence_id="obs-terminal",
        )


def test_remaining_order_freeze_and_day_credit_coexist_after_restart(tmp_path) -> None:
    from trading_bot import soak_store

    path = tmp_path / "soak.db"
    conn = soak_store.connect_soak_store(path)
    _campaign(soak_store.bind(conn))
    soak_store.freeze_ticker(
        conn, freeze_id="remaining-1", campaign_id="campaign-1", ticker="000660",
        order_intent_id="intent-partial", freeze_kind="REMAINING_ORDER",
    )
    soak_store.designate_day(
        conn, campaign_id="campaign-1", trading_date="2026-07-17", run_id="run-partial",
        run_kind="RUN", terminal=True, credit_state="CREDITED",
        detail={"reconciliation_complete": True, "fill_state": "PARTIAL"},
    )
    reopened = soak_store.connect_soak_store(path)
    state = soak_store.load_campaign_state(reopened, campaign_id="campaign-1")
    assert state["credited_days"] == 1
    assert [(row["ticker"], row["freeze_kind"]) for row in state["active_freezes"]] == [
        ("000660", "REMAINING_ORDER")
    ]
