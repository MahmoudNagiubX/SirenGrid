from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.fusion import FusionDecision, FusionReport, evaluate_report_association


BASE_TIME = datetime(2026, 9, 8, tzinfo=timezone.utc)


def report(**overrides: object) -> FusionReport:
    values: dict[str, object] = {
        "report_id": "report-a",
        "category": "road_crash",
        "latitude": 30.063,
        "longitude": 31.342,
        "coordinates_trusted": True,
        "received_at": BASE_TIME,
        "location_phrase": "Tayaran Street",
        "source_reference": "caller-1",
        "facts": {"casualty_count": 2},
        "has_committed_operational_state": False,
    }
    values.update(overrides)
    return FusionReport.model_validate(values)


def test_related_reports_auto_associate_with_explanation_facts() -> None:
    result = evaluate_report_association(
        report(),
        report(
            report_id="report-b",
            latitude=30.064,
            longitude=31.343,
            received_at=BASE_TIME + timedelta(minutes=5),
            source_reference="caller-2",
        ),
    )

    assert result.decision is FusionDecision.AUTO_ASSOCIATE
    assert result.distance_m is not None and result.distance_m <= 500
    assert result.time_delta_seconds == 300
    assert result.category_match is True
    assert result.location_phrase_match is True


def test_missing_trusted_coordinates_requires_review() -> None:
    result = evaluate_report_association(
        report(coordinates_trusted=False, latitude=None, longitude=None),
        report(report_id="report-b"),
    )

    assert result.decision is FusionDecision.REQUIRES_REVIEW
    assert result.reason_code == "trusted_coordinates_required"


def test_far_reports_are_separate_incidents() -> None:
    result = evaluate_report_association(
        report(),
        report(report_id="report-b", latitude=30.110, longitude=31.390),
    )

    assert result.decision is FusionDecision.SEPARATE_INCIDENT
    assert result.reason_code == "outside_spatial_window"


def test_unknown_category_requires_review_and_different_known_category_is_separate() -> None:
    unknown = evaluate_report_association(
        report(category=None),
        report(report_id="report-b"),
    )
    different = evaluate_report_association(
        report(),
        report(report_id="report-b", category="building_fire"),
    )

    assert unknown.decision is FusionDecision.REQUIRES_REVIEW
    assert unknown.reason_code == "category_unknown"
    assert different.decision is FusionDecision.SEPARATE_INCIDENT
    assert different.reason_code == "category_incompatible"


def test_conflict_or_committed_state_blocks_auto_association() -> None:
    conflict = evaluate_report_association(
        report(),
        report(report_id="report-b", facts={"casualty_count": 5}),
    )
    committed = evaluate_report_association(
        report(),
        report(report_id="report-b", has_committed_operational_state=True),
    )

    assert conflict.decision is FusionDecision.REQUIRES_REVIEW
    assert conflict.conflicting_field_names == ["casualty_count"]
    assert committed.decision is FusionDecision.REQUIRES_REVIEW
    assert committed.reason_code == "committed_operational_state"


def test_time_window_and_context_gate_are_explicit() -> None:
    stale = evaluate_report_association(
        report(),
        report(report_id="report-b", received_at=BASE_TIME + timedelta(minutes=16)),
    )
    no_context = evaluate_report_association(
        report(),
        report(
            report_id="report-b",
            location_phrase="Makram Ebeid",
            source_reference="caller-2",
        ),
    )

    assert stale.decision is FusionDecision.SEPARATE_INCIDENT
    assert stale.reason_code == "outside_temporal_window"
    assert no_context.decision is FusionDecision.REQUIRES_REVIEW
    assert no_context.reason_code == "context_match_required"
