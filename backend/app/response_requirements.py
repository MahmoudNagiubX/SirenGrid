"""Typed Phase 04 response requirements and the locked prototype matrix."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Iterable

from app.schemas import ResourceType, Severity


PROTOTYPE_RESPONSE_REQUIREMENT_MATRIX_VERSION = "SIRENGRID_PROTOTYPE_RRM_V1"
PROTOTYPE_POLICY_LABEL = "SirenGrid prototype demo configuration"


class RequirementSource(str, Enum):
    OPERATOR_CONFIRMED = "OPERATOR_CONFIRMED"
    STRUCTURED_SOURCE = "STRUCTURED_SOURCE"
    PROTOTYPE_MATRIX = "PROTOTYPE_MATRIX"


class ResponseRequirementsUnavailableError(ValueError):
    """Raised when requirements need an operator rather than an invented rule."""


@dataclass(frozen=True)
class ResponseRequirement:
    """One explicit minimum resource cohort requirement."""

    resource_type: ResourceType
    minimum_count: int
    required_capability_tags: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.minimum_count < 1:
            raise ValueError("Response requirement minimum_count must be at least one")
        normalized_tags = tuple(sorted({tag.strip() for tag in self.required_capability_tags}))
        if any(not tag for tag in normalized_tags):
            raise ValueError("Response requirement capability tags must be non-empty")
        object.__setattr__(self, "required_capability_tags", normalized_tags)

    @property
    def cohort_key(self) -> tuple[ResourceType, tuple[str, ...]]:
        return self.resource_type, self.required_capability_tags

    def known_capabilities_satisfy(self, capability_tags: Iterable[str]) -> bool:
        """Unknown or omitted tags cannot satisfy a requirement with known tags."""
        known = {tag.strip() for tag in capability_tags if tag.strip()}
        return set(self.required_capability_tags).issubset(known)


@dataclass(frozen=True)
class ResolvedResponseRequirements:
    requirements: tuple[ResponseRequirement, ...]
    source: RequirementSource
    matrix_version: str | None
    prototype_policy_label: str | None


def _validate_explicit_requirements(
    requirements: Iterable[ResponseRequirement],
    source: RequirementSource,
) -> tuple[ResponseRequirement, ...]:
    validated = tuple(requirements)
    if not validated:
        raise ResponseRequirementsUnavailableError(
            f"{source.value} requirements are empty; operator confirmation is required"
        )
    cohorts = [requirement.cohort_key for requirement in validated]
    if len(cohorts) != len(set(cohorts)):
        raise ValueError("Response requirements must not duplicate a resource cohort")
    return tuple(sorted(validated, key=lambda requirement: requirement.cohort_key))


def _matrix_requirements(
    incident_type: str,
    severity: Severity | None,
) -> tuple[ResponseRequirement, ...]:
    if incident_type != "traffic_collision" or severity is None:
        raise ResponseRequirementsUnavailableError(
            "No approved matrix rule applies; operator confirmation is required"
        )
    if severity in (Severity.LOW, Severity.MODERATE):
        return (ResponseRequirement(ResourceType.AMBULANCE, 1),)
    if severity in (Severity.HIGH, Severity.CRITICAL):
        return (
            ResponseRequirement(ResourceType.AMBULANCE, 2),
            ResponseRequirement(ResourceType.FIRE_RESCUE, 1),
        )
    raise ResponseRequirementsUnavailableError(
        "No approved matrix rule applies; operator confirmation is required"
    )


def resolve_response_requirements(
    *,
    incident_type: str,
    severity: Severity | None,
    operator_confirmed_requirements: Iterable[ResponseRequirement] | None = None,
    source_requirements: Iterable[ResponseRequirement] | None = None,
) -> ResolvedResponseRequirements:
    """Resolve requirements with locked operator/source/matrix precedence."""
    if operator_confirmed_requirements is not None:
        return ResolvedResponseRequirements(
            requirements=_validate_explicit_requirements(
                operator_confirmed_requirements,
                RequirementSource.OPERATOR_CONFIRMED,
            ),
            source=RequirementSource.OPERATOR_CONFIRMED,
            matrix_version=None,
            prototype_policy_label=None,
        )
    if source_requirements is not None:
        return ResolvedResponseRequirements(
            requirements=_validate_explicit_requirements(
                source_requirements,
                RequirementSource.STRUCTURED_SOURCE,
            ),
            source=RequirementSource.STRUCTURED_SOURCE,
            matrix_version=None,
            prototype_policy_label=None,
        )
    return ResolvedResponseRequirements(
        requirements=_matrix_requirements(incident_type, severity),
        source=RequirementSource.PROTOTYPE_MATRIX,
        matrix_version=PROTOTYPE_RESPONSE_REQUIREMENT_MATRIX_VERSION,
        prototype_policy_label=PROTOTYPE_POLICY_LABEL,
    )
