from __future__ import annotations

import pytest

from app.response_requirements import (
    PROTOTYPE_RESPONSE_REQUIREMENT_MATRIX_VERSION,
    RequirementSource,
    ResponseRequirement,
    ResponseRequirementsUnavailableError,
    resolve_response_requirements,
)
from app.schemas import ResourceType, Severity


def test_operator_confirmed_requirements_override_source_and_prototype_matrix() -> None:
    resolution = resolve_response_requirements(
        incident_type="traffic_collision",
        severity=Severity.CRITICAL,
        operator_confirmed_requirements=(
            ResponseRequirement(
                resource_type=ResourceType.AMBULANCE,
                minimum_count=1,
                required_capability_tags=("operator_confirmed_capability",),
            ),
        ),
        source_requirements=(
            ResponseRequirement(
                resource_type=ResourceType.FIRE_RESCUE,
                minimum_count=1,
            ),
        ),
    )

    assert resolution.source is RequirementSource.OPERATOR_CONFIRMED
    assert resolution.matrix_version is None
    assert resolution.requirements == (
        ResponseRequirement(
            resource_type=ResourceType.AMBULANCE,
            minimum_count=1,
            required_capability_tags=("operator_confirmed_capability",),
        ),
    )


def test_structured_source_requirements_override_prototype_matrix() -> None:
    resolution = resolve_response_requirements(
        incident_type="traffic_collision",
        severity=Severity.HIGH,
        source_requirements=(
            ResponseRequirement(
                resource_type=ResourceType.AMBULANCE,
                minimum_count=1,
                required_capability_tags=("basic_life_support",),
            ),
        ),
    )

    assert resolution.source is RequirementSource.STRUCTURED_SOURCE
    assert resolution.matrix_version is None
    assert resolution.requirements[0].minimum_count == 1


@pytest.mark.parametrize(
    ("severity", "expected"),
    [
        (Severity.LOW, ((ResourceType.AMBULANCE, 1),)),
        (Severity.MODERATE, ((ResourceType.AMBULANCE, 1),)),
        (
            Severity.HIGH,
            ((ResourceType.AMBULANCE, 2), (ResourceType.FIRE_RESCUE, 1)),
        ),
        (
            Severity.CRITICAL,
            ((ResourceType.AMBULANCE, 2), (ResourceType.FIRE_RESCUE, 1)),
        ),
    ],
)
def test_prototype_matrix_v1_supports_only_locked_traffic_collision_rules(
    severity: Severity,
    expected: tuple[tuple[ResourceType, int], ...],
) -> None:
    resolution = resolve_response_requirements(
        incident_type="traffic_collision",
        severity=severity,
    )

    assert resolution.source is RequirementSource.PROTOTYPE_MATRIX
    assert resolution.matrix_version == PROTOTYPE_RESPONSE_REQUIREMENT_MATRIX_VERSION
    assert tuple(
        (requirement.resource_type, requirement.minimum_count)
        for requirement in resolution.requirements
    ) == expected
    assert resolution.prototype_policy_label == "SirenGrid prototype demo configuration"


@pytest.mark.parametrize(
    ("incident_type", "severity"),
    [
        ("medical_emergency", Severity.HIGH),
        ("traffic_collision", None),
    ],
)
def test_unsupported_or_incomplete_matrix_input_requires_operator_confirmation(
    incident_type: str,
    severity: Severity | None,
) -> None:
    with pytest.raises(ResponseRequirementsUnavailableError, match="operator confirmation"):
        resolve_response_requirements(
            incident_type=incident_type,
            severity=severity,
        )


def test_unknown_capability_is_not_treated_as_confirmed_capability() -> None:
    requirement = ResponseRequirement(
        resource_type=ResourceType.AMBULANCE,
        minimum_count=1,
        required_capability_tags=("advanced_life_support",),
    )

    assert not requirement.known_capabilities_satisfy(())
    assert not requirement.known_capabilities_satisfy(("basic_life_support",))
    assert requirement.known_capabilities_satisfy(("advanced_life_support",))
