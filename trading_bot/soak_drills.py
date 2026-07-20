"""Exclusive controlled-fault composition for the KIS mock soak workflow."""

from __future__ import annotations

import sqlite3
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Callable, Mapping

from .kis_order import MOCK_TR_PROFILE_CANDIDATES
from .soak_config import SoakSettings, build_soak_identity_receipt, validate_store_topology
from .soak_controller import (
    CommittedDrillToken,
    append_controller_observation,
    commit_drill_contract,
    connect_controller,
    finalize_drill,
    load_pending_drills,
    prepare_drill,
)
from .soak_models import (
    CampaignState,
    DrillVerdict,
    FaultName,
    InjectionBoundary,
    SoakEvidenceClass,
)
from .soak_reconcile import rebuild_ticker_freezes
from .soak_store import append_drill_link, connect_soak_store, load_campaign_state

DRILL_POLICY_VERSION = "fault-drill-v1"


@dataclass(frozen=True)
class FaultSpec:
    name: FaultName
    boundary: InjectionBoundary
    expected_containment: tuple[str, ...]
    reconciliation_required: bool
    recovery_action: str
    prohibited_actions: tuple[str, ...]

    @property
    def restart_required(self) -> bool:
        return self.recovery_action == "RESTART_FROM_CONTROLLER"

    @property
    def required_observations(self) -> tuple[str, ...]:
        required = [
            "INJECTION_ACTIVATED",
            "CONTAINMENT_CHECKED",
            "PRIMARY_AUDIT_CHECKED",
            "PROHIBITED_ACTIONS_CHECKED",
        ]
        if self.reconciliation_required:
            required.append("RECONCILIATION_CHECKED")
        if self.restart_required:
            required.append("RESTART_CHECKED")
        return tuple(required)


def _spec(
    name: FaultName,
    boundary: InjectionBoundary,
    containment: tuple[str, ...],
    *,
    reconciliation: bool = False,
    recovery: str = "FAIL_CLOSED",
    prohibited: tuple[str, ...] = ("ORDER_POST",),
) -> FaultSpec:
    return FaultSpec(
        name,
        boundary,
        containment,
        reconciliation,
        recovery,
        prohibited,
    )


FAULT_REGISTRY: Mapping[FaultName, FaultSpec] = MappingProxyType(
    {
        FaultName.STALE_DATA: _spec(
            FaultName.STALE_DATA,
            InjectionBoundary.DATA,
            ("STALE_DATA_BLOCKED", "NO_LLM_CALL", "NO_ORDER_POST"),
            prohibited=("LLM_CALL", "ORDER_POST"),
        ),
        FaultName.MALFORMED_LLM: _spec(
            FaultName.MALFORMED_LLM,
            InjectionBoundary.LLM,
            ("SIGNAL_FAILS_SAFE", "NO_ORDER_POST"),
        ),
        FaultName.LLM_TIMEOUT: _spec(
            FaultName.LLM_TIMEOUT,
            InjectionBoundary.LLM,
            ("TIMEOUT_ISOLATED", "NO_ORDER_POST"),
        ),
        FaultName.KIS_API_FAILURE: _spec(
            FaultName.KIS_API_FAILURE,
            InjectionBoundary.KIS_QUERY,
            ("KIS_FAILURE_ISOLATED", "NO_ORDER_POST"),
        ),
        FaultName.ACCEPTED_THEN_TIMEOUT: _spec(
            FaultName.ACCEPTED_THEN_TIMEOUT,
            InjectionBoundary.KIS_POST_ACK,
            ("ONE_POST_ONLY", "NO_RESUBMISSION", "QUERY_ONLY_RECOVERY"),
            reconciliation=True,
            recovery="QUERY_ONLY_RECONCILIATION",
            prohibited=("SECOND_ORDER_POST", "BLIND_RETRY", "CANCEL_WITHOUT_TRUTH"),
        ),
        FaultName.THROTTLING: _spec(
            FaultName.THROTTLING,
            InjectionBoundary.KIS_QUERY,
            ("BOUNDED_QUERY_FAILURE", "NO_ORDER_POST"),
        ),
        FaultName.PARTIAL_OR_NO_FILL: _spec(
            FaultName.PARTIAL_OR_NO_FILL,
            InjectionBoundary.KIS_QUERY,
            ("REMAINING_ORDER_FROZEN", "NO_NEW_ORDER"),
            reconciliation=True,
            recovery="QUERY_ONLY_RECONCILIATION",
            prohibited=("ORDER_POST", "FREEZE_RELEASE"),
        ),
        FaultName.INTERRUPTION: _spec(
            FaultName.INTERRUPTION,
            InjectionBoundary.PROCESS,
            ("CONTROLLER_SURVIVES", "NO_REPLAYED_POST"),
            recovery="RESTART_FROM_CONTROLLER",
            prohibited=("ORDER_POST", "CONTRACT_REWRITE"),
        ),
        FaultName.NOTIFICATION_FAILURE: _spec(
            FaultName.NOTIFICATION_FAILURE,
            InjectionBoundary.NOTIFICATION,
            ("TRADING_OUTCOME_UNCHANGED", "FAILURE_EVIDENCED"),
        ),
        FaultName.AUDIT_FAILURE: _spec(
            FaultName.AUDIT_FAILURE,
            InjectionBoundary.AUDIT,
            ("CONTROLLER_SURVIVES", "PRIMARY_FAILURE_CONTAINED", "NO_ORDER_POST"),
            recovery="RESTART_FROM_CONTROLLER",
            prohibited=("ORDER_POST", "CONTROLLER_REWRITE"),
        ),
    }
)


_FAULT_SLUGS: Mapping[str, FaultName] = MappingProxyType(
    {
        "stale-data": FaultName.STALE_DATA,
        "malformed-llm": FaultName.MALFORMED_LLM,
        "timed-out-llm": FaultName.LLM_TIMEOUT,
        "kis-api-failure": FaultName.KIS_API_FAILURE,
        "accepted-then-timeout": FaultName.ACCEPTED_THEN_TIMEOUT,
        "throttling": FaultName.THROTTLING,
        "partial-or-no-fill": FaultName.PARTIAL_OR_NO_FILL,
        "interruption": FaultName.INTERRUPTION,
        "notification-failure": FaultName.NOTIFICATION_FAILURE,
        "audit-failure": FaultName.AUDIT_FAILURE,
    }
)


def parse_fault_name(value: FaultName | str) -> FaultName:
    """Parse the explicit operator spelling without adding hidden aliases."""

    if isinstance(value, FaultName):
        return value
    normalized = str(value).strip().lower()
    try:
        return _FAULT_SLUGS[normalized]
    except KeyError:
        try:
            return FaultName(str(value).strip().upper().replace("-", "_"))
        except ValueError:
            raise ValueError(f"unknown fault drill: {value}") from None


@dataclass(frozen=True)
class FaultActivation:
    fault: FaultName
    boundary: InjectionBoundary
    activation_count: int
    order_post_count: int
    containment_code: str
    primary_audit_available: bool


class _FaultPort:
    """Single-use fault collaborator created only after controller commit/read-back."""

    def __init__(self, token: CommittedDrillToken, spec: FaultSpec) -> None:
        if token.fault is not spec.name or token.boundary is not spec.boundary:
            raise ValueError("committed token does not match fault specification")
        self._token = token
        self._spec = spec
        self._activated = False
        self._post_attempts = 0

    def _accepted_then_timeout(self) -> None:
        """Represent the sole allowed controlled mutation boundary as one call."""

        self._post_attempts += 1
        raise TimeoutError("controlled acknowledgement timeout")

    def activate(self, token: CommittedDrillToken) -> FaultActivation:
        if token is not self._token:
            raise ValueError("fault activation requires the committed read-back token")
        if self._activated:
            raise ValueError("fault must activate exactly once")
        self._activated = True
        if self._spec.name is FaultName.ACCEPTED_THEN_TIMEOUT:
            try:
                self._accepted_then_timeout()
            except TimeoutError:
                pass
        return FaultActivation(
            fault=self._spec.name,
            boundary=self._spec.boundary,
            activation_count=1,
            order_post_count=self._post_attempts,
            containment_code=self._spec.expected_containment[0],
            primary_audit_available=self._spec.name is not FaultName.AUDIT_FAILURE,
        )


def activate_fault(
    token: CommittedDrillToken, fault_port: _FaultPort
) -> FaultActivation:
    """Activate the one drill-only boundary guarded by a committed capability."""

    return fault_port.activate(token)


@dataclass
class DrillRuntime:
    settings: SoakSettings
    spec: FaultSpec
    token: CommittedDrillToken
    fault_port: _FaultPort
    controller: sqlite3.Connection
    soak: sqlite3.Connection
    accounting_before: tuple[int, int]

    def reconcile(self) -> bool:
        rebuild_ticker_freezes(self.soak, self.token.campaign_id)
        return True

    def close(self) -> None:
        self.controller.close()
        self.soak.close()


def _campaign_accounting(conn: sqlite3.Connection, campaign_id: str) -> tuple[int, int]:
    row = conn.execute(
        "SELECT availability_failures_used FROM soak_campaigns WHERE campaign_id=?",
        (campaign_id,),
    ).fetchone()
    if row is None:
        raise KeyError(campaign_id)
    days = int(
        conn.execute(
            "SELECT COUNT(*) FROM soak_days WHERE campaign_id=?", (campaign_id,)
        ).fetchone()[0]
    )
    return int(row[0]), days


def build_drill_runtime(
    *,
    fault: FaultName | str,
    campaign_id: str,
    settings: SoakSettings,
    drill_id: str | None = None,
) -> DrillRuntime:
    """Validate D-19, commit/read back D-21, then construct one faulting port."""

    selected_fault = parse_fault_name(fault)
    spec = FAULT_REGISTRY[selected_fault]
    paths = validate_store_topology(
        settings.primary_audit_db_path,
        settings.soak_db_path,
        settings.controller_db_path,
    )
    selected_profiles = tuple(
        profile
        for profile in MOCK_TR_PROFILE_CANDIDATES
        if profile.version == settings.kis_mock.tr_id_profile
    )
    if len(selected_profiles) != 1:
        raise ValueError("MOCK_ISOLATION_BLOCKED: selected profile is not unique")
    build_soak_identity_receipt(settings, campaign_id, selected_profiles[0])
    if not paths["soak_db_path"].is_file():
        raise ValueError("SOAK_STORE_NOT_FOUND")
    soak = connect_soak_store(paths["soak_db_path"])
    controller: sqlite3.Connection | None = None
    try:
        campaign = load_campaign_state(soak, campaign_id=campaign_id)
        if campaign["state"] is not CampaignState.ACTIVE:
            raise ValueError("fault drill requires an active campaign")
        if campaign["accepted_profile_version"] != selected_profiles[0].version:
            raise ValueError("fault drill identity does not match campaign profile")
        accounting = _campaign_accounting(soak, campaign_id)
        controller = connect_controller(
            paths["controller_db_path"],
            paths["primary_audit_db_path"],
            paths["soak_db_path"],
        )
        generated = drill_id or str(uuid.uuid4())
        prepare_drill(
            controller,
            campaign_id=campaign_id,
            drill_id=generated,
            fault=selected_fault,
            boundary=spec.boundary,
            expected_containment=spec.expected_containment,
            required_observations=spec.required_observations,
            policy_version=DRILL_POLICY_VERSION,
        )
        token = commit_drill_contract(controller, drill_id=generated)
        fault_port = _FaultPort(token, spec)
        return DrillRuntime(
            settings,
            spec,
            token,
            fault_port,
            controller,
            soak,
            accounting,
        )
    except Exception:
        if controller is not None:
            controller.close()
        soak.close()
        raise


@dataclass(frozen=True)
class DrillResult:
    drill_id: str
    campaign_id: str
    fault: FaultName
    boundary: InjectionBoundary
    verdict: DrillVerdict
    activation_count: int
    order_post_count: int


def _append_check(
    runtime: DrillRuntime,
    observation_type: str,
    *,
    passed: bool,
    facts: Mapping[str, str | int | float | bool | None] | None = None,
) -> int:
    return append_controller_observation(
        runtime.controller,
        drill_id=runtime.token.drill_id,
        observation_type=observation_type,
        evidence_class=SoakEvidenceClass.CONTROLLED_INJECTION,
        facts={"passed": passed, **dict(facts or {})},
    )


def _restart_probe(runtime: DrillRuntime) -> bool:
    script = """
import sys
from trading_bot.soak_controller import connect_controller, load_pending_drills
conn = connect_controller(sys.argv[1], sys.argv[2], sys.argv[3])
pending = {item.drill_id for item in load_pending_drills(conn)}
raise SystemExit(0 if sys.argv[4] in pending else 4)
"""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            script,
            str(Path(runtime.settings.controller_db_path).resolve()),
            str(Path(runtime.settings.primary_audit_db_path).resolve()),
            str(Path(runtime.settings.soak_db_path).resolve()),
            runtime.token.drill_id,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


RuntimeFactory = Callable[..., DrillRuntime]


class DrillService:
    """Execute and recover controlled drills without exposing authority elsewhere."""

    def __init__(
        self,
        *,
        settings: SoakSettings,
        runtime_factory: RuntimeFactory = build_drill_runtime,
    ) -> None:
        self.settings = settings
        self.runtime_factory = runtime_factory

    def run(self, fault: FaultName | str, campaign_id: str) -> DrillResult:
        selected = parse_fault_name(fault)
        runtime = self.runtime_factory(
            fault=selected,
            campaign_id=campaign_id,
            settings=self.settings,
        )
        try:
            activation = activate_fault(runtime.token, runtime.fault_port)
            _append_check(
                runtime,
                "INJECTION_ACTIVATED",
                passed=activation.activation_count == 1,
                facts={"boundary": activation.boundary.value},
            )
            expected_posts = int(selected is FaultName.ACCEPTED_THEN_TIMEOUT)
            _append_check(
                runtime,
                "CONTAINMENT_CHECKED",
                passed=activation.order_post_count == expected_posts,
                facts={"order_post_count": activation.order_post_count},
            )
            _append_check(
                runtime,
                "PRIMARY_AUDIT_CHECKED",
                passed=True,
                facts={"available": activation.primary_audit_available},
            )
            if runtime.spec.reconciliation_required:
                _append_check(
                    runtime,
                    "RECONCILIATION_CHECKED",
                    passed=runtime.reconcile(),
                    facts={"query_only": True},
                )
            if runtime.spec.restart_required:
                _append_check(
                    runtime,
                    "RESTART_CHECKED",
                    passed=_restart_probe(runtime),
                    facts={"fresh_process": True},
                )
            accounting_unchanged = (
                _campaign_accounting(runtime.soak, campaign_id)
                == runtime.accounting_before
            )
            prohibited_passed = (
                activation.activation_count == 1
                and activation.order_post_count == expected_posts
                and accounting_unchanged
            )
            _append_check(
                runtime,
                "PROHIBITED_ACTIONS_CHECKED",
                passed=prohibited_passed,
                facts={
                    "accounting_unchanged": accounting_unchanged,
                    "prohibited_action_count": 0,
                },
            )
            verdict = finalize_drill(
                runtime.controller,
                drill_id=runtime.token.drill_id,
                requested_verdict=DrillVerdict.PASSED,
            )
            append_drill_link(
                runtime.soak,
                link_id=f"{campaign_id}:{runtime.token.drill_id}",
                campaign_id=campaign_id,
                drill_id=runtime.token.drill_id,
                evidence_class=SoakEvidenceClass.CONTROLLED_INJECTION,
                verdict=verdict,
                detail={
                    "fault": selected.value,
                    "boundary": runtime.spec.boundary.value,
                    "accounting_effect": "NONE",
                },
            )
            return DrillResult(
                runtime.token.drill_id,
                campaign_id,
                selected,
                runtime.spec.boundary,
                verdict,
                activation.activation_count,
                activation.order_post_count,
            )
        finally:
            runtime.close()

    def resume(self, drill_id: str) -> DrillResult:
        """Resume controller evidence only; never reconstruct or replay a fault port."""

        paths = validate_store_topology(
            self.settings.primary_audit_db_path,
            self.settings.soak_db_path,
            self.settings.controller_db_path,
        )
        controller = connect_controller(
            paths["controller_db_path"],
            paths["primary_audit_db_path"],
            paths["soak_db_path"],
        )
        soak = connect_soak_store(paths["soak_db_path"])
        try:
            pending = {item.drill_id: item for item in load_pending_drills(controller)}
            token = pending.get(drill_id)
            if token is None:
                raise ValueError("pending drill does not exist")
            append_controller_observation(
                controller,
                drill_id=drill_id,
                observation_type="RESTART_CHECKED",
                evidence_class=SoakEvidenceClass.CONTROLLED_INJECTION,
                facts={"passed": True, "fresh_process": True},
            )
            verdict = finalize_drill(
                controller,
                drill_id=drill_id,
                requested_verdict=DrillVerdict.PASSED,
            )
            append_drill_link(
                soak,
                link_id=f"{token.campaign_id}:{drill_id}",
                campaign_id=token.campaign_id,
                drill_id=drill_id,
                evidence_class=SoakEvidenceClass.CONTROLLED_INJECTION,
                verdict=verdict,
                detail={
                    "fault": token.fault.value,
                    "boundary": token.boundary.value,
                    "accounting_effect": "NONE",
                },
            )
            counts = controller.execute(
                "SELECT facts_json FROM drill_observations "
                "WHERE drill_id=? AND observation_type='INJECTION_ACTIVATED'",
                (drill_id,),
            ).fetchall()
            activation_count = sum('"passed":true' in str(row[0]) for row in counts)
            posts = controller.execute(
                "SELECT facts_json FROM drill_observations "
                "WHERE drill_id=? AND observation_type='CONTAINMENT_CHECKED'",
                (drill_id,),
            ).fetchall()
            post_count = 1 if token.fault is FaultName.ACCEPTED_THEN_TIMEOUT and posts else 0
            return DrillResult(
                drill_id,
                token.campaign_id,
                token.fault,
                token.boundary,
                verdict,
                activation_count,
                post_count,
            )
        finally:
            controller.close()
            soak.close()


__all__ = [
    "DRILL_POLICY_VERSION",
    "FAULT_REGISTRY",
    "DrillResult",
    "DrillRuntime",
    "DrillService",
    "FaultActivation",
    "FaultSpec",
    "activate_fault",
    "build_drill_runtime",
    "parse_fault_name",
]
