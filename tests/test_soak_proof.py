from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest

from trading_bot.kis_order import KisOrderAccount, KisOrderPostResult
from trading_bot.soak_models import MockIdentityReceipt, SoakEvidenceClass
from trading_bot.soak_proof import (
    ProofOrderRequest,
    ProofOrderResult,
    ProofOrderService,
    build_proof_fixture,
    export_proof_fixture,
    validate_proof_cross_ids,
)
from trading_bot.soak_reconcile import AmbiguityPolicy


def _receipt() -> MockIdentityReceipt:
    return MockIdentityReceipt(
        target="mock", domain_class="KIS_MOCK_VTS", account_suffix="5678",
        profile_version="official-example-v1", buy_tr_id="VTTC0802U",
        sell_tr_id="VTTC0801U", daily_ccld_tr_id="VTTC8001R",
        balance_tr_id="VTTC8434R", campaign_id="proof-1",
        policy_version="mock-isolation-v1",
    )


def _request(tmp_path: Path) -> ProofOrderRequest:
    return ProofOrderRequest(
        campaign_id="proof-1", ticker="005930", side="BUY", quantity=1,
        price=70000, account=KisOrderAccount("12345678", "01"), receipt=_receipt(),
        primary_audit_db_path=tmp_path / "audit.db",
        soak_db_path=tmp_path / "soak.db",
        controller_db_path=tmp_path / "controller.db",
        accepted_profile_fingerprint="sha256:approved-profile",
        field_contract_version="kis-mock-compat-v1",
        ambiguity_policy=AmbiguityPolicy(
            "ambiguity-v1", 60, 5, 12, "official-example-v1", "kis-mock-compat-v1"
        ),
    )


class _Adapter:
    def __init__(self, outcome=None) -> None:
        self.posts = 0
        self.outcome = outcome or KisOrderPostResult("broker-1", "090000")

    def place_order_cash(self, **kwargs):
        self.posts += 1
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def _reconcile(soak_conn, result):
    from trading_bot import soak_store

    snapshot_id = "snapshot-1"
    comparison_id = "comparison-1"
    soak_store.append_snapshot(
        soak_conn, snapshot_id=snapshot_id, campaign_id=result.campaign_id,
        run_id=result.run_id, stage="POST_SUBMISSION", ticker=result.ticker,
        orders=[{"observation_id": "order-observed-1", "order_id": result.broker_order_id,
                 "status": "FILLED", "remaining_qty": 0}],
        accounts=[{"observation_id": "account-observed-1", "available_cash": 1}],
    )
    soak_store.append_comparison(
        soak_conn, comparison_id=comparison_id, campaign_id=result.campaign_id,
        snapshot_id=snapshot_id, run_id=result.run_id, ticker=result.ticker,
        order_intent_id=result.order_intent_id, verdict="MATCHED",
        remaining_order_terminal=True,
    )
    return snapshot_id, comparison_id


def test_primary_attempt_is_read_back_before_exactly_one_post_and_restart_cannot_resubmit(tmp_path) -> None:
    adapter = _Adapter()
    service = ProofOrderService(adapter=adapter, reconciliation_runner=_reconcile)
    request = _request(tmp_path)
    result = service.run(request)

    assert adapter.posts == 1
    observer = sqlite3.connect(request.primary_audit_db_path)
    assert [row[0] for row in observer.execute(
        "SELECT event_type FROM order_events WHERE order_intent_id=? ORDER BY id",
        (result.order_intent_id,),
    )][:3] == ["INTENT_CREATED", "DUPLICATE_CHECKED", "SUBMISSION_ATTEMPTED"]
    assert validate_proof_cross_ids(observer, sqlite3.connect(request.soak_db_path), result.proof_id)
    with pytest.raises(ValueError, match="already has a submission attempt"):
        service.run(request)
    assert adapter.posts == 1


def test_timeout_has_one_post_and_durable_ambiguity_freeze(tmp_path) -> None:
    adapter = _Adapter(TimeoutError("accepted then timeout"))
    result = ProofOrderService(adapter=adapter, reconciliation_runner=_reconcile).run(_request(tmp_path))
    assert adapter.posts == 1
    assert result.acknowledgement_class == "AMBIGUOUS"
    soak = sqlite3.connect(tmp_path / "soak.db")
    assert soak.execute("SELECT COUNT(*) FROM soak_ticker_freezes WHERE state='FROZEN'").fetchone()[0] == 1


def test_fixture_is_allowlisted_sanitized_idempotent_and_conflict_safe(tmp_path) -> None:
    result = ProofOrderResult(
        proof_id="proof-id", campaign_id="proof-1", run_id="run-1",
        ticker="005930", order_intent_id="intent-1", submission_id="submission-1",
        broker_order_id="broker-1", acknowledgement_class="ACCEPTED",
        snapshot_id="snapshot-1", comparison_id="comparison-1",
        account_suffix="5678", profile_version="official-example-v1",
        ambiguity_policy_version="ambiguity-v1", evidence_class=SoakEvidenceClass.KIS_OBSERVED,
        freeze_active=False, cross_ids_validated=True,
    )
    fixture = build_proof_fixture(result)
    assert set(fixture) == {"schema_version", "evidence_version", "identity", "policy_id", "acknowledgement_class", "cross_ids", "comparison", "freeze", "provenance"}
    path = tmp_path / "proof.json"
    assert export_proof_fixture(path, fixture) == path
    original = path.read_bytes()
    assert export_proof_fixture(path, fixture) == path
    assert path.read_bytes() == original
    with pytest.raises(ValueError, match="PROOF_FIXTURE_CONFLICT"):
        export_proof_fixture(path, {**fixture, "policy_id": "other"})
    assert path.read_bytes() == original
    text = json.dumps(fixture)
    assert "12345678" not in text and "secret" not in text.lower()


def test_fixture_rejects_unvalidated_or_synthetic_provenance() -> None:
    base = ProofOrderResult(
        proof_id="p", campaign_id="c", run_id="r", ticker="005930",
        order_intent_id="i", submission_id="s", broker_order_id=None,
        acknowledgement_class="AMBIGUOUS", snapshot_id="sn", comparison_id="co",
        account_suffix="5678", profile_version="official-example-v1",
        ambiguity_policy_version="ambiguity-v1", evidence_class=SoakEvidenceClass.SYNTHETIC,
        freeze_active=True, cross_ids_validated=True,
    )
    with pytest.raises(ValueError, match="KIS_OBSERVED"):
        build_proof_fixture(base)
