"""Durable, mock-only one-order proof campaign.

The module deliberately exposes one submission capability and keeps all restart
and reconciliation behavior query-only.  It never imports the general runtime.
"""

from __future__ import annotations
from contextlib import nullcontext

import json
import os
import re
import sqlite3
import tempfile
import uuid
from dataclasses import dataclass, replace
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from trading_bot.audit_models import OrderEvent, OrderEventType, RunStatus
from trading_bot.domain import Money, Order, OrderSide, Ticker
from trading_bot.kis_order import KisOrderAccount, snap_to_tick
from trading_bot.soak_config import validate_store_topology
from trading_bot.soak_models import (
    MockIdentityReceipt,
    MockTrProfile,
    ReconciliationStage,
    SoakEvidenceClass,
)
from trading_bot.soak_reconcile import (
    AmbiguityPolicy,
    AmbiguousIntent,
    SnapshotCampaign,
    SnapshotWindow,
    collect_broker_snapshot,
    compare_broker_truth,
    persist_reconciliation,
    rebuild_ticker_freezes,
    reconcile_ambiguous_submission,
)
from trading_bot.soak_store import (
    append_campaign_event,
    connect_soak_store,
    create_or_load_proof_campaign,
    freeze_ticker,
)
from trading_bot import sqlite_audit


PROOF_FIXTURE_SCHEMA_VERSION = "kis-mock-proof-v1"
PROOF_EVIDENCE_VERSION = "proof-evidence-v1"


@dataclass(frozen=True)
class ProofOrderRequest:
    campaign_id: str
    ticker: str
    side: str
    quantity: int
    price: float
    account: KisOrderAccount
    receipt: MockIdentityReceipt
    primary_audit_db_path: Path
    soak_db_path: Path
    controller_db_path: Path
    accepted_profile_fingerprint: str
    field_contract_version: str
    ambiguity_policy: AmbiguityPolicy

    def __post_init__(self) -> None:
        if self.receipt.target != "mock" or self.receipt.domain_class != "KIS_MOCK_VTS":
            raise ValueError("proof order requires a passing mock identity receipt")
        if self.receipt.campaign_id != self.campaign_id:
            raise ValueError("proof campaign and receipt IDs differ")
        if self.receipt.profile_version != self.ambiguity_policy.profile_version:
            raise ValueError("proof profile and ambiguity policy differ")
        if self.field_contract_version != self.ambiguity_policy.field_contract_version:
            raise ValueError("proof field contract and ambiguity policy differ")
        if len(self.ticker) != 6 or not self.ticker.isdigit():
            raise ValueError("proof ticker must be a six-digit KRX code")
        object.__setattr__(self, "side", OrderSide(self.side.upper()).value)
        if not 1 <= self.quantity <= 10:
            raise ValueError("proof quantity must be explicitly bounded to 1..10")
        if not 1 <= self.price <= 100_000_000:
            raise ValueError("proof price must be explicitly bounded")
        if self.account.cano[-4:] != self.receipt.account_suffix:
            raise ValueError("proof account does not match sanitized receipt suffix")


@dataclass(frozen=True)
class ProofOrderResult:
    proof_id: str
    campaign_id: str
    run_id: str
    ticker: str
    order_intent_id: str
    submission_id: str
    broker_order_id: str | None
    acknowledgement_class: str
    snapshot_id: str
    comparison_id: str
    account_suffix: str
    profile_version: str
    ambiguity_policy_version: str
    evidence_class: SoakEvidenceClass
    freeze_active: bool
    cross_ids_validated: bool

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_class", SoakEvidenceClass(self.evidence_class))
        if self.acknowledgement_class not in {"ACCEPTED", "REJECTED", "AMBIGUOUS"}:
            raise ValueError("unknown proof acknowledgement class")


class _SingleUseSubmissionGuard:
    """Capability wrapper whose sole mutation method can be called once."""

    def __init__(self, adapter: Any) -> None:
        self._adapter = adapter
        self._used = False

    def place_order_cash(self, **kwargs: Any) -> Any:
        if self._used:
            raise RuntimeError("proof submission capability already consumed")
        self._used = True
        return self._adapter.place_order_cash(**kwargs)


ReconciliationRunner = Callable[[sqlite3.Connection, ProofOrderResult], tuple[str, str]]


class ProofOrderService:
    """Create durable evidence, release one POST, then reconcile without retry."""

    def __init__(
        self,
        *,
        adapter: Any,
        reconciliation_runner: ReconciliationRunner | None = None,
        sleeper: Callable[[float], None] | None = None,
        submission_context: Any = None,
    ) -> None:
        self._adapter = adapter
        self._reconciliation_runner = reconciliation_runner
        self._sleeper = sleeper or (lambda _: None)
        self._submission_context = submission_context

    @staticmethod
    def _ids(request: ProofOrderRequest) -> tuple[str, str, str, str]:
        basis = f"{request.campaign_id}:{request.ticker}:{request.side}:{request.quantity}:{request.price:g}"
        proof_id = str(uuid.uuid5(uuid.NAMESPACE_URL, "proof:" + basis))
        return (
            proof_id,
            str(uuid.uuid5(uuid.NAMESPACE_URL, "run:" + proof_id)),
            str(uuid.uuid5(uuid.NAMESPACE_URL, "intent:" + proof_id)),
            str(uuid.uuid5(uuid.NAMESPACE_URL, "submission:" + proof_id)),
        )

    def run(self, request: ProofOrderRequest) -> ProofOrderResult:
        from .kis_order import KisOrderAdapter
        from .submission_authority import ProofSubmissionContext
        if isinstance(self._adapter,KisOrderAdapter) and type(self._submission_context) is not ProofSubmissionContext:
            raise ValueError('PROOF_FINAL_SUBMISSION_AUTHORITY_REQUIRED')
        validate_store_topology(
            request.primary_audit_db_path,
            request.soak_db_path,
            request.controller_db_path,
        )
        proof_id, run_id, intent_id, submission_id = self._ids(request)
        primary = sqlite_audit.connect(request.primary_audit_db_path)
        soak = connect_soak_store(request.soak_db_path)
        try:
            create_or_load_proof_campaign(
                soak,
                campaign_id=request.campaign_id,
                accepted_profile_fingerprint=request.accepted_profile_fingerprint,
                accepted_profile_version=request.receipt.profile_version,
                field_contract_version=request.field_contract_version,
                ambiguity_policy=request.ambiguity_policy,
            )
            rebuild_ticker_freezes(soak, request.campaign_id)
            if primary.execute(
                "SELECT 1 FROM order_events WHERE order_intent_id=? AND event_type='SUBMISSION_ATTEMPTED'",
                (intent_id,),
            ).fetchone() is not None:
                raise ValueError("proof intent already has a submission attempt")

            sqlite_audit.start_run(
                primary,
                run_id=run_id,
                trading_mode="mock",
                dry_run=False,
                target="kis_mock",
                policy_snapshot={
                    "campaign_id": request.campaign_id,
                    "proof_id": proof_id,
                    "ambiguity_policy_version": request.ambiguity_policy.version,
                },
                provenance={"evidence_class": SoakEvidenceClass.KIS_OBSERVED.value},
            )
            common = dict(
                order_intent_id=intent_id,
                origin_run_id=run_id,
                observer_run_id=run_id,
                ticker=request.ticker,
                side=request.side,
                requested_qty=request.quantity,
            )
            sqlite_audit.append_order_event(primary, OrderEvent(
                **common,
                event_type=OrderEventType.INTENT_CREATED,
                detail={"campaign_id": request.campaign_id, "proof_id": proof_id, "snapped_price": snap_to_tick(request.price, side=OrderSide(request.side))},
            ))
            sqlite_audit.append_order_event(primary, OrderEvent(
                **common,
                event_type=OrderEventType.DUPLICATE_CHECKED,
                broker_status="CLEAR",
                detail={"campaign_id": request.campaign_id, "proof_id": proof_id},
            ))
            order = Order(
                ticker=Ticker(request.ticker),
                side=OrderSide(request.side),
                quantity=request.quantity,
                limit_price=Money(float(request.price)),
            )
            boundary=(self._submission_context(request,order,(proof_id,run_id,intent_id,submission_id))
                if self._submission_context is not None else nullcontext(None))
            with boundary as admission:
                sqlite_audit.append_order_event(primary, OrderEvent(
                    **common,
                    event_type=OrderEventType.SUBMISSION_ATTEMPTED,
                    submission_id=submission_id,
                    detail={"campaign_id": request.campaign_id, "proof_id": proof_id,
                        **(admission.detail() if admission is not None else {})},
                ))
                append_campaign_event(
                    soak,
                    observation_id=proof_id,
                    campaign_id=request.campaign_id,
                    run_id=run_id,
                    ticker=request.ticker,
                    order_intent_id=intent_id,
                    event_code="PROOF_SUBMISSION_ATTEMPTED",
                    evidence_class=SoakEvidenceClass.KIS_OBSERVED,
                    detail={"submission_id": submission_id, "profile_version": request.receipt.profile_version},
                )
                self._verify_primary_attempt(request.primary_audit_db_path, run_id, intent_id, submission_id)

                if admission is not None:
                    self._submission_context.verify_attempt()
                guard = _SingleUseSubmissionGuard(self._adapter)
                broker_order_id: str | None = None
                try:
                    response = guard.place_order_cash(
                        account=request.account,
                        order=order,
                        snapped_price=snap_to_tick(request.price, side=order.side),
                        **(self._submission_context.post_kwargs if admission is not None else {}),
                    )
                    broker_order_id = str(getattr(response, "order_id", "") or "") or None
                    acknowledgement = "ACCEPTED" if broker_order_id else "REJECTED"
                    event_type = (
                        OrderEventType.SUBMISSION_ACCEPTED
                        if acknowledgement == "ACCEPTED"
                        else OrderEventType.RECONCILED
                    )
                    broker_status = acknowledgement
                except Exception as exc:
                    acknowledgement = "AMBIGUOUS"
                    event_type = OrderEventType.SUBMISSION_AMBIGUOUS
                    broker_status = "ACK_UNKNOWN"
                    error_type = type(exc).__name__
                detail: dict[str, Any] = {"campaign_id": request.campaign_id, "proof_id": proof_id}
                if acknowledgement == "AMBIGUOUS":
                    detail["error_type"] = error_type
                sqlite_audit.append_order_event(primary, OrderEvent(
                    **common,
                    event_type=event_type,
                    submission_id=submission_id,
                    broker_order_id=broker_order_id,
                    broker_status=broker_status,
                    detail=detail,
                ))
                freeze_active = acknowledgement == "AMBIGUOUS"
                if freeze_active:
                    freeze_ticker(
                        soak,
                        freeze_id=str(uuid.uuid5(uuid.NAMESPACE_URL, "freeze:" + proof_id)),
                        campaign_id=request.campaign_id,
                        ticker=request.ticker,
                        order_intent_id=intent_id,
                        freeze_kind="AMBIGUITY",
                        detail={"reason_code": "AMBIGUOUS_SUBMISSION", "submission_id": submission_id},
                    )
                append_campaign_event(
                    soak,
                    campaign_id=request.campaign_id,
                    run_id=run_id,
                    ticker=request.ticker,
                    order_intent_id=intent_id,
                    event_code=f"PROOF_{acknowledgement}",
                    evidence_class=SoakEvidenceClass.KIS_OBSERVED,
                    detail={"proof_id": proof_id, "submission_id": submission_id, "broker_order_id": broker_order_id or ""},
                )
            draft = ProofOrderResult(
                proof_id=proof_id,
                campaign_id=request.campaign_id,
                run_id=run_id,
                ticker=request.ticker,
                order_intent_id=intent_id,
                submission_id=submission_id,
                broker_order_id=broker_order_id,
                acknowledgement_class=acknowledgement,
                snapshot_id="",
                comparison_id="",
                account_suffix=request.receipt.account_suffix,
                profile_version=request.receipt.profile_version,
                ambiguity_policy_version=request.ambiguity_policy.version,
                evidence_class=SoakEvidenceClass.KIS_OBSERVED,
                freeze_active=freeze_active,
                cross_ids_validated=False,
            )
            if self._reconciliation_runner is not None:
                snapshot_id, comparison_id = self._reconciliation_runner(soak, draft)
            else:
                snapshot_id, comparison_id = self._reconcile_default(soak, request, draft)
            result = replace(draft, snapshot_id=snapshot_id, comparison_id=comparison_id)
            if not validate_proof_cross_ids(primary, soak, proof_id):
                raise ValueError("proof cross-store IDs are incomplete or contradictory")
            sqlite_audit.finish_run(
                primary,
                run_id=run_id,
                status=(RunStatus.COMPLETED if acknowledgement != "AMBIGUOUS" else RunStatus.COMPLETED_WITH_ERRORS),
            )
            return replace(result, cross_ids_validated=True)
        finally:
            primary.close()
            soak.close()

    @staticmethod
    def _verify_primary_attempt(path: Path, run_id: str, intent_id: str, submission_id: str) -> None:
        observer = sqlite3.connect(f"file:{Path(path).resolve()}?mode=ro", uri=True)
        try:
            run = observer.execute(
                "SELECT target,trading_mode FROM runs WHERE run_id=?", (run_id,)
            ).fetchone()
            rows = observer.execute(
                "SELECT event_type,submission_id FROM order_events WHERE order_intent_id=? ORDER BY id",
                (intent_id,),
            ).fetchall()
        finally:
            observer.close()
        if run != ("kis_mock", "mock"):
            raise ValueError("primary proof run identity was not durably read back")
        if [row[0] for row in rows] != [
            "INTENT_CREATED", "DUPLICATE_CHECKED", "SUBMISSION_ATTEMPTED"
        ] or rows[-1][1] != submission_id:
            raise ValueError("primary proof attempt was not durably read back")

    def _reconcile_default(
        self,
        soak: sqlite3.Connection,
        request: ProofOrderRequest,
        result: ProofOrderResult,
    ) -> tuple[str, str]:
        profile = MockTrProfile(
            request.receipt.profile_version,
            request.receipt.buy_tr_id,
            request.receipt.sell_tr_id,
            request.receipt.daily_ccld_tr_id,
            request.receipt.balance_tr_id,
        )
        campaign = SnapshotCampaign(
            request.campaign_id,
            result.run_id,
            request.account,
            request.receipt.account_suffix,
            profile,
        )
        window = SnapshotWindow(date.today(), date.today())
        if result.acknowledgement_class == "AMBIGUOUS":
            intent = AmbiguousIntent(
                campaign_id=request.campaign_id,
                run_id=result.run_id,
                order_intent_id=result.order_intent_id,
                submission_id=result.submission_id,
                account_suffix=request.receipt.account_suffix,
                ticker=request.ticker,
                side=request.side,
                quantity=request.quantity,
                snapped_price=float(snap_to_tick(request.price, side=OrderSide(request.side))),
                submitted_at=datetime.now(timezone.utc),
            )
            reconcile_ambiguous_submission(
                conn=soak,
                adapter=self._adapter,
                campaign=campaign,
                intent=intent,
                query_window=window,
                sleeper=self._sleeper,
            )
        snapshot = collect_broker_snapshot(
            self._adapter,
            campaign,
            ReconciliationStage.POST_SUBMISSION,
            window,
            {"order_ids": ((result.broker_order_id,) if result.broker_order_id else ()), "tickers": (request.ticker,)},
        )
        comparison = compare_broker_truth(
            {
                "ticker": request.ticker,
                "order_id": result.broker_order_id,
                "order_intent_id": result.order_intent_id,
                "requested_qty": request.quantity,
            },
            snapshot,
        )
        return persist_reconciliation(soak, snapshot, comparison)


def validate_proof_cross_ids(
    primary_conn: sqlite3.Connection,
    soak_conn: sqlite3.Connection,
    proof_id: str,
) -> bool:
    """Resolve every stable proof reference against its owning store."""

    soak_conn.row_factory = sqlite3.Row
    origin = soak_conn.execute(
        "SELECT * FROM soak_events WHERE observation_id=? AND event_code='PROOF_SUBMISSION_ATTEMPTED'",
        (proof_id,),
    ).fetchone()
    if origin is None:
        return False
    details = json.loads(origin["detail_json"] or "{}")
    run_id = str(origin["run_id"] or "")
    intent_id = str(origin["order_intent_id"] or "")
    submission_id = str(details.get("submission_id") or "")
    if primary_conn.execute(
        "SELECT 1 FROM runs WHERE run_id=? AND target='kis_mock' AND trading_mode='mock'",
        (run_id,),
    ).fetchone() is None:
        return False
    events = primary_conn.execute(
        "SELECT event_type,submission_id,ticker FROM order_events WHERE order_intent_id=? AND origin_run_id=? ORDER BY id",
        (intent_id, run_id),
    ).fetchall()
    types = [str(row[0]) for row in events]
    if types[:3] != ["INTENT_CREATED", "DUPLICATE_CHECKED", "SUBMISSION_ATTEMPTED"]:
        return False
    if types.count("SUBMISSION_ATTEMPTED") != 1 or not any(row[1] == submission_id for row in events):
        return False
    if any(str(row[2]) != str(origin["ticker"]) for row in events):
        return False
    comparison = soak_conn.execute(
        """SELECT c.snapshot_id FROM soak_comparisons c
           JOIN soak_snapshots s ON s.snapshot_id=c.snapshot_id
           WHERE c.campaign_id=? AND c.run_id=? AND c.ticker=? AND c.order_intent_id=?
             AND s.campaign_id=c.campaign_id AND s.run_id=c.run_id
           ORDER BY c.id DESC LIMIT 1""",
        (origin["campaign_id"], run_id, origin["ticker"], intent_id),
    ).fetchone()
    return comparison is not None


def build_proof_fixture(result: ProofOrderResult) -> dict[str, Any]:
    """Project a completed proof onto a fixed, normalized evidence allowlist."""

    if result.evidence_class is not SoakEvidenceClass.KIS_OBSERVED:
        raise ValueError("proof fixture provenance must be KIS_OBSERVED")
    if not result.cross_ids_validated or not result.snapshot_id or not result.comparison_id:
        raise ValueError("proof fixture requires durable reconciliation and cross-ID validation")
    if len(result.account_suffix) != 4 or not result.account_suffix.isdigit():
        raise ValueError("proof fixture account suffix is invalid")
    return {
        "schema_version": PROOF_FIXTURE_SCHEMA_VERSION,
        "evidence_version": PROOF_EVIDENCE_VERSION,
        "identity": {
            "target": "mock",
            "domain_class": "KIS_MOCK_VTS",
            "account_suffix": result.account_suffix,
            "profile_version": result.profile_version,
            "ticker": result.ticker,
        },
        "policy_id": result.ambiguity_policy_version,
        "acknowledgement_class": result.acknowledgement_class,
        "cross_ids": {
            "proof_id": result.proof_id,
            "campaign_id": result.campaign_id,
            "run_id": result.run_id,
            "order_intent_id": result.order_intent_id,
            "submission_id": result.submission_id,
            "broker_order_id": result.broker_order_id,
            "snapshot_id": result.snapshot_id,
            "comparison_id": result.comparison_id,
        },
        "comparison": {"stage": "POST_SUBMISSION", "cross_ids_validated": True},
        "freeze": {"active": result.freeze_active},
        "provenance": SoakEvidenceClass.KIS_OBSERVED.value,
    }


def export_proof_fixture(destination: Path, fixture: Mapping[str, Any]) -> Path:
    """Atomically publish stable bytes; identical content is idempotent."""

    required = {
        "schema_version", "evidence_version", "identity", "policy_id",
        "acknowledgement_class", "cross_ids", "comparison", "freeze", "provenance",
    }
    if set(fixture) != required or fixture.get("provenance") != "KIS_OBSERVED":
        raise ValueError("proof fixture is not the versioned allowlisted shape")
    nested_shapes = {
        "identity": {"target", "domain_class", "account_suffix", "profile_version", "ticker"},
        "cross_ids": {
            "proof_id", "campaign_id", "run_id", "order_intent_id", "submission_id",
            "broker_order_id", "snapshot_id", "comparison_id",
        },
        "comparison": {"stage", "cross_ids_validated"},
        "freeze": {"active"},
    }
    for key, shape in nested_shapes.items():
        value = fixture.get(key)
        if not isinstance(value, Mapping) or set(value) != shape:
            raise ValueError("proof fixture is not the versioned allowlisted shape")
    identity = fixture["identity"]
    assert isinstance(identity, Mapping)
    if (
        identity.get("target") != "mock"
        or identity.get("domain_class") != "KIS_MOCK_VTS"
        or re.fullmatch(r"[0-9]{4}", str(identity.get("account_suffix", ""))) is None
        or re.fullmatch(r"[0-9]{6}", str(identity.get("ticker", ""))) is None
    ):
        raise ValueError("proof fixture identity is invalid")
    forbidden_markers = (
        "secret", "token", "authorization", "credential", "app_key", "app-key",
        "payload", "header", "response", "request",
    )

    def validate_scalar(value: Any) -> None:
        if isinstance(value, Mapping):
            for nested_key, nested_value in value.items():
                lowered = str(nested_key).lower()
                if any(marker in lowered for marker in forbidden_markers):
                    raise ValueError("proof fixture contains forbidden material")
                validate_scalar(nested_value)
            return
        if isinstance(value, (list, tuple, set)):
            raise ValueError("proof fixture cannot contain provider rows")
        if isinstance(value, str):
            lowered = value.lower()
            if any(marker in lowered for marker in forbidden_markers):
                raise ValueError("proof fixture contains forbidden material")
            if len(value) > 128:
                raise ValueError("proof fixture scalar is too long")

    validate_scalar(fixture)
    payload = (
        json.dumps(dict(fixture), ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
    ).encode("utf-8")
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if destination.read_bytes() == payload:
            return destination
        raise ValueError("PROOF_FIXTURE_CONFLICT")
    fd, temporary_name = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.link(temporary, destination)
        except FileExistsError:
            if destination.read_bytes() != payload:
                raise ValueError("PROOF_FIXTURE_CONFLICT") from None
        directory_fd = os.open(destination.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temporary.unlink(missing_ok=True)
    return destination


__all__ = [
    "ProofOrderRequest", "ProofOrderResult", "ProofOrderService",
    "validate_proof_cross_ids", "build_proof_fixture", "export_proof_fixture",
]
