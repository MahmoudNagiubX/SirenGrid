from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from app.schemas import HospitalPreAlertStatus

__all__ = ["SimulatedHospitalGateway", "SimulatedPreAlertResult"]


@dataclass(frozen=True)
class SimulatedPreAlertResult:
    """Deterministic result of the Phase 05 simulated hospital boundary."""

    status: HospitalPreAlertStatus
    sent_at: datetime
    acknowledged_at: datetime | None
    failed_at: datetime | None
    failure_reason: str | None


class SimulatedHospitalGateway:
    """Simulate pre-alert delivery without claiming a hospital integration."""

    data_reality = "SIMULATED"
    source = "SIMULATED_HOSPITAL_GATEWAY"

    def request_pre_alert(
        self,
        *,
        payload: dict[str, Any],
        requested_at: datetime,
        simulate_failure: bool = False,
    ) -> SimulatedPreAlertResult:
        del payload  # The gateway does not reinterpret or enrich known facts.
        if simulate_failure:
            return SimulatedPreAlertResult(
                status=HospitalPreAlertStatus.FAILED,
                sent_at=requested_at,
                acknowledged_at=None,
                failed_at=requested_at,
                failure_reason="SIMULATED_GATEWAY_FAILURE",
            )
        return SimulatedPreAlertResult(
            status=HospitalPreAlertStatus.ACKNOWLEDGED,
            sent_at=requested_at,
            acknowledged_at=requested_at,
            failed_at=None,
            failure_reason=None,
        )
