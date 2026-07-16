"""Read-only KIS mock compatibility characterization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
from types import MappingProxyType
from typing import Mapping, Sequence

from trading_bot.kis_order import KisOrderAccount, KisOrderAdapter
from trading_bot.soak_models import (
    BrokerPageEnvelope,
    CompatibilityState,
    MockTrProfile,
    PageCompleteness,
    SoakEvidenceClass,
)


@dataclass(frozen=True)
class CompatibilityResult:
    state: CompatibilityState
    evidence_class: SoakEvidenceClass
    profile_version: str | None
    daily: BrokerPageEnvelope
    balance: BrokerPageEnvelope
    facts: Mapping[str, str | int | bool]

    def __post_init__(self) -> None:
        object.__setattr__(self, "state", CompatibilityState(self.state))
        object.__setattr__(self, "evidence_class", SoakEvidenceClass(self.evidence_class))
        object.__setattr__(self, "facts", MappingProxyType(dict(self.facts)))


def probe_mock_profile(
    adapter: KisOrderAdapter,
    account: KisOrderAccount,
    candidates: Sequence[MockTrProfile],
    window: tuple[date, date],
    *,
    evidence_class: SoakEvidenceClass = SoakEvidenceClass.KIS_OBSERVED,
    page_cap: int = 10,
) -> CompatibilityResult:
    """Characterize candidates with GET-only complete inquiries."""

    last_daily = BrokerPageEnvelope()
    last_balance = BrokerPageEnvelope()
    for profile in candidates:
        last_daily = adapter.query_daily_ccld_pages(
            account=account,
            profile=profile,
            start_date=window[0],
            end_date=window[1],
            page_cap=page_cap,
        )
        last_balance = adapter.query_balance_pages(
            account=account, profile=profile, page_cap=page_cap
        )
        complete = (
            last_daily.completeness is PageCompleteness.COMPLETE
            and last_balance.completeness is PageCompleteness.COMPLETE
        )
        if complete:
            state = (
                CompatibilityState.ACCEPTED
                if evidence_class is SoakEvidenceClass.KIS_OBSERVED
                else CompatibilityState.UNKNOWN
            )
            return CompatibilityResult(
                state=state,
                evidence_class=evidence_class,
                profile_version=profile.version,
                daily=last_daily,
                balance=last_balance,
                facts={
                    "daily_pages": last_daily.page_count,
                    "balance_pages": last_balance.page_count,
                    "daily_fields": ",".join(sorted({key for row in last_daily.rows for key in row})),
                    "balance_fields": ",".join(sorted({key for row in last_balance.rows for key in row})),
                },
            )
    return CompatibilityResult(
        state=CompatibilityState.UNKNOWN,
        evidence_class=evidence_class,
        profile_version=None,
        daily=last_daily,
        balance=last_balance,
        facts={"candidate_count": len(candidates)},
    )


def export_compatibility_fixture(result: CompatibilityResult, destination: Path) -> Path:
    """Publish deterministic allowlisted evidence without overwriting conflicts."""

    document = {
        "schema_version": "kis-mock-compat-v1",
        "state": result.state.value,
        "evidence_class": result.evidence_class.value,
        "profile_version": result.profile_version,
        "facts": dict(result.facts),
        "daily": {
            "rows": [dict(row) for row in result.daily.rows],
            "page_count": result.daily.page_count,
            "completeness": result.daily.completeness.value,
            "reason_code": result.daily.reason_code,
        },
        "balance": {
            "rows": [dict(row) for row in result.balance.rows],
            "summary": dict(result.balance.summary),
            "page_count": result.balance.page_count,
            "completeness": result.balance.completeness.value,
            "reason_code": result.balance.reason_code,
        },
    }
    payload = (json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode()
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with destination.open("xb") as handle:
            handle.write(payload)
    except FileExistsError:
        if destination.read_bytes() != payload:
            raise ValueError("COMPATIBILITY_FIXTURE_CONFLICT") from None
    return destination
