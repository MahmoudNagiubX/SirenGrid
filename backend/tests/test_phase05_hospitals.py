from __future__ import annotations

from app.hospitals import (
    HospitalOperationalSnapshot,
    HospitalRouteCandidate,
    load_static_hospitals,
    rank_hospital_candidates,
)


def test_static_osm_registry_loads_expected_hospitals_truthfully() -> None:
    hospitals = load_static_hospitals()

    assert len(hospitals) == 27
    assert len({hospital.id for hospital in hospitals}) == 27
    assert all(hospital.source_id for hospital in hospitals)
    assert all(hospital.provenance["data_reality"] == "REAL_PUBLIC" for hospital in hospitals)
    assert all(hospital.static_capacity is None for hospital in hospitals)


def test_unknown_operational_state_does_not_become_static_or_live_capacity() -> None:
    hospitals = load_static_hospitals()

    hospital = hospitals[0]
    state = HospitalOperationalSnapshot.unknown(hospital.id)

    assert state.accepting_state == "UNKNOWN"
    assert state.simulated_load_ratio is None
    assert state.simulated_free_capacity is None
    assert state.incoming_cases is None
    assert state.data_reality == "SIMULATED"
    assert hospital.static_capacity is None


def test_hospital_ranking_uses_approved_score_and_unknown_capability_penalty() -> None:
    hospitals = load_static_hospitals()
    first = hospitals[0]
    second = hospitals[1]
    candidates = [
        HospitalRouteCandidate(
            hospital=first,
            operational_state=HospitalOperationalSnapshot.unknown(first.id),
            route={"eta_seconds": 300.0, "routing_source": "OSM_BASE_TRAVEL_TIME"},
        ),
        HospitalRouteCandidate(
            hospital=second,
            operational_state=HospitalOperationalSnapshot(
                hospital_id=second.id,
                accepting_state="ACCEPTING",
                simulated_load_ratio=0.0,
                simulated_free_capacity=None,
                incoming_cases=0,
                freshness_status="FRESH",
                data_reality="SIMULATED",
            ),
            route={"eta_seconds": 420.0, "routing_source": "OSM_BASE_TRAVEL_TIME"},
        ),
    ]

    ranked = rank_hospital_candidates(candidates, required_capabilities=("TRAUMA",))

    assert len(ranked) == 2
    first_score = next(
        candidate.score_breakdown
        for candidate in ranked
        if candidate.hospital.id == first.id
    )
    assert first_score["policy_version"] == "SIRENGRID_PROTOTYPE_HOSPITAL_SCORE_V1"
    assert first_score["weights"] == {
        "eta": 0.55,
        "capability": 0.20,
        "load": 0.20,
        "freshness": 0.05,
        "capacity": 0.0,
    }
    assert first_score["eta_normalizer_seconds"] == 900
    assert first_score["capability_penalty"] == 0.5
    assert first_score["load_penalty"] == 0.5
    assert first_score["freshness_penalty"] == 0.5


def test_confirmed_incompatible_and_not_accepting_candidates_are_filtered() -> None:
    hospitals = load_static_hospitals()
    hospital = hospitals[0]
    incompatible = hospital.model_copy(
        update={"confirmed_incompatible_capabilities": ("TRAUMA",)}
    )
    not_accepting = hospitals[1]
    candidates = [
        HospitalRouteCandidate(
            hospital=incompatible,
            operational_state=HospitalOperationalSnapshot.unknown(incompatible.id),
            route={"eta_seconds": 100.0},
        ),
        HospitalRouteCandidate(
            hospital=not_accepting,
            operational_state=HospitalOperationalSnapshot(
                hospital_id=not_accepting.id,
                accepting_state="NOT_ACCEPTING",
                simulated_load_ratio=None,
                simulated_free_capacity=None,
                incoming_cases=None,
                freshness_status="FRESH",
                data_reality="SIMULATED",
            ),
            route={"eta_seconds": 100.0},
        ),
    ]

    assert rank_hospital_candidates(candidates, required_capabilities=("TRAUMA",)) == []
