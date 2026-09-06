from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Severity(StrEnum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class SupportLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class StructuredIncident(BaseModel):
    model_config = ConfigDict(extra="forbid")

    incident_type: str | None
    location_text: str | None
    latitude: float | None
    longitude: float | None
    severity: Severity | None
    casualty_count: int | None = Field(default=None, ge=0)
    trapped_person: bool | None
    road_blockage: bool | None
    required_services: list[str]
    missing_critical_fields: list[str]
    support_level: SupportLevel

    @field_validator("required_services", "missing_critical_fields")
    @classmethod
    def reject_blank_items(cls, values: list[str]) -> list[str]:
        if any(not value.strip() for value in values):
            raise ValueError("list values must not be blank")
        return values


class ImageEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    observations: list[str]
    possible_smoke_or_fire: bool | None
    possible_vehicle_damage: bool | None
    possible_road_obstruction: bool | None
    casualty_count: int | None = Field(default=None, ge=0)
    uncertainty_notes: list[str]
