from __future__ import annotations

from dataclasses import dataclass

from app.schemas import CorridorSignalState

__all__ = ["TrafficSignalGateway", "SignalPriorityResult"]


@dataclass(frozen=True)
class SignalPriorityResult:
    state: CorridorSignalState
    data_reality: str = "SIMULATED"


class TrafficSignalGateway:
    """Simulation boundary for signal-priority requests; no real control exists."""

    data_reality = "SIMULATED"

    _allowed_transitions = {
        CorridorSignalState.NORMAL: {
            CorridorSignalState.REQUESTED,
            CorridorSignalState.FAILED,
        },
        CorridorSignalState.REQUESTED: {
            CorridorSignalState.PREPARING,
            CorridorSignalState.FAILED,
        },
        CorridorSignalState.PREPARING: {
            CorridorSignalState.PRIORITY_ACTIVE,
            CorridorSignalState.FAILED,
        },
        CorridorSignalState.PRIORITY_ACTIVE: {
            CorridorSignalState.PASSED,
            CorridorSignalState.FAILED,
        },
        CorridorSignalState.PASSED: set(),
        CorridorSignalState.FAILED: set(),
    }

    def transition(
        self,
        current: str,
        target: CorridorSignalState,
    ) -> SignalPriorityResult:
        current_state = CorridorSignalState(current)
        if target != current_state and target not in self._allowed_transitions[current_state]:
            raise ValueError(f"Illegal corridor priority transition {current} -> {target.value}")
        return SignalPriorityResult(state=target)
