import pytest
from pydantic import ValidationError

from feasibility.providers import (
    ProviderError,
    StructuredOutputFailure,
    _gemini_output_text,
    parse_structured_output,
    run_with_single_retry,
    validate_explicit_services,
)
from feasibility.run_checks import _select_models, _structured_extraction_policy
from feasibility.schemas import StructuredIncident


def valid_payload() -> dict:
    return {
        "incident_type": "road_crash",
        "location_text": "Abbas El Akkad",
        "latitude": None,
        "longitude": None,
        "severity": "HIGH",
        "casualty_count": None,
        "trapped_person": True,
        "road_blockage": None,
        "required_services": ["ambulance", "rescue"],
        "missing_critical_fields": ["exact_location", "casualty_count"],
        "support_level": "MEDIUM",
    }


def test_structured_incident_accepts_unknown_fields_as_null() -> None:
    incident = StructuredIncident.model_validate(valid_payload())

    assert incident.casualty_count is None
    assert incident.latitude is None
    assert incident.longitude is None


def test_structured_incident_rejects_extra_operational_decision_fields() -> None:
    payload = valid_payload() | {"recommended_responder_id": "ambulance-1"}

    with pytest.raises(ValidationError):
        StructuredIncident.model_validate(payload)


def test_ai_coordinates_are_rejected_without_authoritative_metadata() -> None:
    payload = valid_payload() | {"latitude": 30.07, "longitude": 31.34}

    with pytest.raises(ValueError, match="authoritative"):
        parse_structured_output(payload, authoritative_coordinates=False)


def test_structured_output_retry_is_capped_at_one_retry() -> None:
    attempts: list[int] = []

    def request(attempt: int) -> dict:
        attempts.append(attempt)
        return {"invalid": True}

    with pytest.raises(StructuredOutputFailure):
        run_with_single_retry(
            request,
            lambda payload: StructuredIncident.model_validate(payload),
        )

    assert attempts == [0, 1]


def test_provider_schema_failure_gets_only_one_reformat_attempt() -> None:
    attempts: list[int] = []

    def request(attempt: int) -> dict:
        attempts.append(attempt)
        raise ProviderError("json_validate_failed", status_code=400)

    with pytest.raises(StructuredOutputFailure):
        run_with_single_retry(request, StructuredIncident.model_validate)

    assert attempts == [0, 1]


def test_retry_failure_keeps_earlier_unsupported_fact_diagnostic() -> None:
    attempts: list[int] = []

    def request(attempt: int) -> dict:
        attempts.append(attempt)
        if attempt == 0:
            return valid_payload() | {"required_services": ["ambulance"]}
        raise ProviderError("json_validate_failed", status_code=400)

    with pytest.raises(StructuredOutputFailure) as caught:
        run_with_single_retry(
            request,
            lambda payload: validate_explicit_services(
                "في حادثة كبيرة عند عباس العقاد.",
                StructuredIncident.model_validate(payload),
            ),
        )

    assert attempts == [0, 1]
    assert any("not explicit" in str(failure) for failure in caught.value.failures)


def test_required_services_must_be_explicit_in_the_report() -> None:
    incident = StructuredIncident.model_validate(valid_payload())

    with pytest.raises(ValueError, match="not explicit"):
        validate_explicit_services("في حادثة كبيرة عند عباس العقاد.", incident)


def test_gemini_interaction_text_is_extracted_from_documented_output_shape() -> None:
    payload = {
        "status": "completed",
        "outputs": [{"type": "text", "text": '{"support_level":"LOW"}'}],
    }

    assert _gemini_output_text(payload) == '{"support_level":"LOW"}'


def test_structured_extraction_stays_manual_until_explicit_provider_validation() -> None:
    policy = _structured_extraction_policy()

    assert _select_models() == {
        "primary": "NOT SELECTED",
        "secondary": "NOT SELECTED",
    }
    assert policy["default_enabled"] is False
    assert policy["safe_fallback"] == "manual/operator structured intake"
