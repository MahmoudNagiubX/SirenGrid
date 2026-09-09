from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import REPO_ROOT
import app.db as db_module
from app.mobile_auth import generate_pin_salt, hash_pin
from app.models import CitizenProfile, EmergencyResource
from app.schemas import DataReality, FreshnessStatus, ResourceStatus, ResourceType

__all__ = [
    "DEFAULT_SCENARIO_PATH",
    "seed_resources",
    "seed_demo_citizen",
    "main",
]

logger = logging.getLogger(__name__)

DEFAULT_SCENARIO_PATH = (
    REPO_ROOT / "data" / "scenarios" / "phase01_resources.json"
)

# Synthetic hackathon citizen. Not a real identity. The PIN is a demo secret
# that only ever appears here and in test setup, never in logs or API output.
DEMO_CITIZEN = {
    "citizen_reference": "demo-citizen-001",
    "display_name": "Demo Citizen",
    "phone": "01000000000",
    "registered_address_text": "12 Demo Street, Nasr City, Cairo",
    # Account context only — never used as an emergency dispatch location.
    "registered_latitude": 30.0566,
    "registered_longitude": 31.3300,
    "national_id_last4": "1234",
    "identity_status": "DEMO_VERIFIED",
    "identity_provider": "SYNTHETIC_DEMO_IDENTITY",
}
DEMO_CITIZEN_PIN = "1234"


def _parse_datetime(val: Any) -> datetime:
    if isinstance(val, datetime):
        return val
    if isinstance(val, str):
        try:
            return datetime.fromisoformat(val.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def seed_resources(
    db: Session,
    scenario_path: Path | str | None = None,
) -> list[EmergencyResource]:
    """Seed simulated emergency resources into the database from a scenario file.

    This operation is strictly idempotent:
    - If a resource with the deterministic ID already exists, it is preserved intact
      and never overwritten (retaining any active operational changes).
    - Only resources whose IDs are not yet present in the database are inserted.

    Returns:
        list[EmergencyResource]: The newly inserted resource ORM instances.
    """
    path = Path(scenario_path) if scenario_path else DEFAULT_SCENARIO_PATH
    if not path.exists():
        raise FileNotFoundError(f"Resources scenario file not found at: {path}")

    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    resources_raw: list[dict[str, Any]] = (
        data.get("resources", data) if isinstance(data, dict) else data
    )

    existing_ids = set(
        db.scalars(select(EmergencyResource.id)).all()
    )

    now_utc = datetime.now(timezone.utc)
    new_resources: list[EmergencyResource] = []

    for raw in resources_raw:
        res_id = str(raw["id"])
        if res_id in existing_ids:
            logger.debug("Resource %s already exists in database; skipping.", res_id)
            continue

        raw_type = raw["resource_type"]
        resource_type = (
            ResourceType(raw_type)
            if isinstance(raw_type, str)
            else raw_type
        )

        raw_status = raw.get("status", "AVAILABLE")
        resource_status = (
            ResourceStatus(raw_status)
            if isinstance(raw_status, str)
            else raw_status
        )

        provenance_raw = raw.get("provenance", {})
        provenance = {
            "source": provenance_raw.get("source", "scenario_phase01_seed"),
            "data_reality": provenance_raw.get(
                "data_reality", DataReality.SIMULATED.value
            ),
            "freshness_status": provenance_raw.get(
                "freshness_status", FreshnessStatus.STATIC.value
            ),
            "last_updated": provenance_raw.get(
                "last_updated", now_utc.isoformat()
            ),
            "source_reference": provenance_raw.get(
                "source_reference", str(path)
            ),
        }

        resource = EmergencyResource(
            id=res_id,
            version=int(raw.get("version", 1)),
            name=str(raw["name"]),
            resource_type=resource_type,
            capability_tags_json=list(
                raw.get("capability_tags", raw.get("capabilities", []))
            ),
            status=resource_status,
            latitude=float(raw["latitude"]),
            longitude=float(raw["longitude"]),
            home_zone=raw.get("home_zone"),
            assigned_incident_id=raw.get("assigned_incident_id"),
            last_updated=_parse_datetime(raw.get("last_updated", now_utc)),
            provenance_json=provenance,
        )

        db.add(resource)
        new_resources.append(resource)
        existing_ids.add(res_id)

    if new_resources:
        db.commit()
        for r in new_resources:
            db.refresh(r)

    return new_resources


def seed_demo_citizen(db: Session) -> CitizenProfile:
    """Idempotently ensure the synthetic demo citizen exists.

    Rerunning never duplicates the account and never overwrites an existing
    row (its active state, PIN hash, and identity fields are left intact).
    """
    existing = db.scalars(
        select(CitizenProfile).where(
            CitizenProfile.citizen_reference == DEMO_CITIZEN["citizen_reference"]
        )
    ).first()
    if existing is not None:
        logger.debug(
            "Demo citizen %s already exists; leaving it untouched.",
            DEMO_CITIZEN["citizen_reference"],
        )
        return existing

    salt = generate_pin_salt()
    now_utc = datetime.now(timezone.utc)
    citizen = CitizenProfile(
        citizen_reference=DEMO_CITIZEN["citizen_reference"],
        display_name=DEMO_CITIZEN["display_name"],
        phone=DEMO_CITIZEN["phone"],
        registered_address_text=DEMO_CITIZEN["registered_address_text"],
        registered_latitude=DEMO_CITIZEN["registered_latitude"],
        registered_longitude=DEMO_CITIZEN["registered_longitude"],
        national_id_last4=DEMO_CITIZEN["national_id_last4"],
        identity_status=DEMO_CITIZEN["identity_status"],
        identity_provider=DEMO_CITIZEN["identity_provider"],
        identity_verified_at=now_utc,
        pin_hash=hash_pin(DEMO_CITIZEN_PIN, salt),
        pin_salt=salt,
        is_active=True,
        data_reality=DataReality.SYNTHETIC,
        created_at=now_utc,
        updated_at=now_utc,
    )
    db.add(citizen)
    db.commit()
    db.refresh(citizen)
    return citizen


def main() -> None:
    """Entry point when executed as `python -m app.seed`."""
    db_module.init_db()
    with db_module.SessionLocal() as db:
        newly_seeded = seed_resources(db=db)
        citizen = seed_demo_citizen(db=db)
        total_count = len(db.scalars(select(EmergencyResource.id)).all())
        print(
            f"SirenGrid seed completed: {len(newly_seeded)} new resource(s) inserted. "
            f"Total resources in operational DB: {total_count}. "
            f"Demo citizen: {citizen.citizen_reference}."
        )


if __name__ == "__main__":
    main()
