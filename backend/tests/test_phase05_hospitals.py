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


def _route(eta_seconds: float) -> dict[str, object]:
    return {"eta_seconds": eta_seconds, "distance_m": eta_seconds * 10.0}


def test_farther_hospital_wins_on_simulated_burn_capability() -> None:
    hospitals = load_static_hospitals()
    nearer, farther = hospitals[0], hospitals[1]
    candidates = [
        HospitalRouteCandidate(
            hospital=nearer,
            operational_state=HospitalOperationalSnapshot(
                hospital_id=nearer.id,
                accepting_state="ACCEPTING",
                simulated_load_ratio=0.9,
                freshness_status="FRESH",
            ),
            route=_route(300.0),
        ),
        HospitalRouteCandidate(
            hospital=farther,
            operational_state=HospitalOperationalSnapshot(
                hospital_id=farther.id,
                accepting_state="ACCEPTING",
                simulated_load_ratio=0.1,
                simulated_capability_tags=("BURN_CARE",),
                freshness_status="FRESH",
            ),
            route=_route(420.0),
        ),
    ]

    ranked = rank_hospital_candidates(candidates, required_capabilities=("burn care",))

    assert [candidate.hospital.id for candidate in ranked] == [farther.id, nearer.id]
    winner = ranked[0].score_breakdown
    assert winner["capability_status"] == "CONFIRMED"
    assert winner["capability_source"] == "SIMULATED_OVERLAY"
    assert winner["capability_data_reality"] == "SIMULATED"
    assert winner["simulated_capability_tags"] == ["BURN_CARE"]
    assert winner["route_eta_seconds"] > ranked[1].score_breakdown["route_eta_seconds"]
    assert ranked[0].score < ranked[1].score


def test_without_a_simulated_overlay_capability_remains_unknown() -> None:
    hospital = load_static_hospitals()[0]
    ranked = rank_hospital_candidates(
        [
            HospitalRouteCandidate(
                hospital=hospital,
                operational_state=HospitalOperationalSnapshot.unknown(hospital.id),
                route=_route(300.0),
            )
        ],
        required_capabilities=("burn care",),
    )

    breakdown = ranked[0].score_breakdown
    assert breakdown["capability_status"] == "UNKNOWN"
    assert breakdown["capability_source"] == "UNKNOWN"
    assert breakdown["simulated_capability_tags"] == []
    assert len(ranked) == 1


def test_real_registry_capability_is_labelled_real_not_simulated() -> None:
    hospital = next(hospital for hospital in load_static_hospitals() if hospital.static_capabilities)
    ranked = rank_hospital_candidates(
        [
            HospitalRouteCandidate(
                hospital=hospital,
                operational_state=HospitalOperationalSnapshot.unknown(hospital.id),
                route=_route(300.0),
            )
        ],
        required_capabilities=(hospital.static_capabilities[0],),
    )

    breakdown = ranked[0].score_breakdown
    assert breakdown["capability_status"] == "CONFIRMED"
    assert breakdown["capability_source"] == "REAL_PUBLIC_REGISTRY"
    assert breakdown["capability_data_reality"] == "REAL_PUBLIC"
