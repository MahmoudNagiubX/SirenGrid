from __future__ import annotations

import base64
import json
import mimetypes
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from feasibility.schemas import ImageEvidence, StructuredIncident


GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
TOMTOM_BASE_URL = "https://api.tomtom.com"
GROQ_MODELS = (
    "whisper-large-v3",
    "whisper-large-v3-turbo",
    "qwen/qwen3.8-27b",
    "openai/gpt-oss-120b",
)


class ProviderError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


class StructuredOutputFailure(ProviderError):
    def __init__(
        self,
        message: str,
        *,
        retry_count: int,
        failures: tuple[Exception, ...] = (),
    ) -> None:
        super().__init__(message)
        self.retry_count = retry_count
        self.failures = failures


class CoordinateAuthorityError(ValueError):
    """Raised when a model proposes coordinates without authoritative metadata."""


class UnsupportedFactError(ValueError):
    """Raised when a model adds a fact not explicitly supported by the report."""


ModelT = TypeVar("ModelT", bound=BaseModel)

SERVICE_ALIASES = {
    "ambulance": ("ambulance", "اسعاف", "إسعاف"),
    "rescue": ("rescue", "انقاذ", "إنقاذ", "نجدة"),
    "fire": ("fire", "حريق", "مطافي", "مطافئ"),
    "police": ("police", "شرطة"),
}


def parse_structured_output(
    raw: str | dict[str, Any], *, authoritative_coordinates: bool
) -> StructuredIncident:
    if isinstance(raw, str):
        payload = json.loads(raw)
    elif isinstance(raw, dict):
        payload = raw
    else:
        raise TypeError("structured output must be a JSON object or JSON string")

    incident = StructuredIncident.model_validate(payload)
    if not authoritative_coordinates and (
        incident.latitude is not None or incident.longitude is not None
    ):
        raise CoordinateAuthorityError(
            "model coordinates require authoritative source metadata"
        )
    return incident


def validate_explicit_services(text: str, incident: StructuredIncident) -> StructuredIncident:
    normalized_text = text.casefold()
    for service in incident.required_services:
        aliases = SERVICE_ALIASES.get(service.casefold())
        if aliases is None or not any(alias.casefold() in normalized_text for alias in aliases):
            raise UnsupportedFactError(
                f"required service is not explicit in report: {service}"
            )
    return incident


def run_with_single_retry(
    request: Callable[[int], Any], parser: Callable[[Any], ModelT]
) -> tuple[ModelT, int]:
    """Parse once and allow exactly one controlled retry, never more."""
    failures: list[Exception] = []
    for attempt in (0, 1):
        try:
            return parser(request(attempt)), attempt
        except (json.JSONDecodeError, TypeError, ValueError, ValidationError) as exc:
            failures.append(exc)
        except ProviderError as exc:
            # A provider-side structured-output validation failure is the one
            # bounded case where the reformat attempt is useful. Auth, quota,
            # network, and server failures remain visible and are not retried.
            if exc.status_code != 400:
                raise
            failures.append(exc)
    raise StructuredOutputFailure(
        "structured output remained invalid after one controlled retry",
        retry_count=1,
        failures=tuple(failures),
    ) from failures[-1]


def _safe_error(response: httpx.Response) -> str:
    if response.status_code == 401:
        return "unauthorized"
    if response.status_code == 403:
        return "forbidden"
    if response.status_code == 429:
        return "rate_limited"
    if response.status_code >= 500:
        return "provider_server_error"
    return f"http_{response.status_code}"


def _raise_for_status(response: httpx.Response) -> None:
    if response.is_error:
        raise ProviderError(
            _safe_error(response), status_code=response.status_code
        )


def _json_request(
    method: str,
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    json_body: dict[str, Any] | None = None,
    files: Any = None,
    data: dict[str, str] | None = None,
    timeout: float,
) -> tuple[dict[str, Any], httpx.Headers]:
    try:
        response = httpx.request(
            method,
            url,
            headers=headers,
            params=params,
            json=json_body,
            files=files,
            data=data,
            timeout=timeout,
        )
    except httpx.HTTPError as exc:
        raise ProviderError(f"network_error:{type(exc).__name__}") from exc
    _raise_for_status(response)
    try:
        payload = response.json()
    except ValueError as exc:
        raise ProviderError("invalid_json_response", status_code=response.status_code) from exc
    if not isinstance(payload, dict):
        raise ProviderError("unexpected_json_response", status_code=response.status_code)
    return payload, response.headers


def groq_health(
    api_key: str | None, *, timeout: float, models: tuple[str, ...] = GROQ_MODELS
) -> dict[str, Any]:
    if not api_key:
        return {"status": "UNAVAILABLE", "reason": "credential_unavailable"}
    try:
        payload, headers = _json_request(
            "GET",
            f"{GROQ_BASE_URL}/models",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )
    except ProviderError as exc:
        status = "QUOTA_BLOCKED" if exc.status_code == 429 else "UNAVAILABLE"
        return {"status": status, "reason": str(exc)}

    listed = {
        item.get("id")
        for item in payload.get("data", [])
        if isinstance(item, dict)
    }
    return {
        "status": "AVAILABLE",
        "models": {
            model: {
                "status": "AVAILABLE" if model in listed else "MODEL_NOT_AVAILABLE"
            }
            for model in models
        },
        "rate_limit_headers_present": any(
            key.lower().startswith("x-ratelimit-") for key in headers
        ),
    }


def _incident_schema() -> dict[str, Any]:
    # Groq strict schemas reject Pydantic's nullable-enum `anyOf` because its
    # branches are not disambiguated. Use the equivalent explicit union form
    # from the provider's supported JSON Schema subset, then validate again
    # with StructuredIncident after the response returns.
    def nullable(type_name: str, enum: list[str] | None = None) -> dict[str, Any]:
        value: dict[str, Any] = {"type": [type_name, "null"]}
        if enum is not None:
            value["enum"] = [*enum, None]
        return value

    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "incident_type": nullable("string"),
            "location_text": nullable("string"),
            "latitude": nullable("number"),
            "longitude": nullable("number"),
            "severity": nullable("string", ["LOW", "MODERATE", "HIGH", "CRITICAL"]),
            "casualty_count": {"type": ["integer", "null"], "minimum": 0},
            "trapped_person": nullable("boolean"),
            "road_blockage": nullable("boolean"),
            "required_services": {"type": "array", "items": {"type": "string"}},
            "missing_critical_fields": {"type": "array", "items": {"type": "string"}},
            "support_level": {"type": "string", "enum": ["LOW", "MEDIUM", "HIGH"]},
        },
        "required": [
            "incident_type",
            "location_text",
            "latitude",
            "longitude",
            "severity",
            "casualty_count",
            "trapped_person",
            "road_blockage",
            "required_services",
            "missing_critical_fields",
            "support_level",
        ],
    }


def _image_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "observations": {"type": "array", "items": {"type": "string"}},
            "possible_smoke_or_fire": {"type": ["boolean", "null"]},
            "possible_vehicle_damage": {"type": ["boolean", "null"]},
            "possible_road_obstruction": {"type": ["boolean", "null"]},
            "casualty_count": {"type": ["integer", "null"], "minimum": 0},
            "uncertainty_notes": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "observations",
            "possible_smoke_or_fire",
            "possible_vehicle_damage",
            "possible_road_obstruction",
            "casualty_count",
            "uncertainty_notes",
        ],
    }


def _groq_chat(
    api_key: str,
    *,
    model: str,
    messages: list[dict[str, Any]],
    schema: dict[str, Any],
    strict: bool,
    timeout: float,
) -> str:
    response_format: dict[str, Any]
    if strict:
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "siren_grid_output",
                "strict": True,
                "schema": schema,
            },
        }
    else:
        response_format = {"type": "json_object"}
    body: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "max_completion_tokens": 512,
        "response_format": response_format,
    }
    if model.startswith("qwen/"):
        body["reasoning_effort"] = "none"
    elif model.startswith("openai/gpt-oss"):
        # Groq's GPT-OSS guidance uses the Harmony message contract: keep
        # instructions in the user message and hide the low-effort reasoning
        # channel when the response must be JSON.
        body["messages"] = [
            {
                "role": "user",
                "content": "\n\n".join(
                    message["content"]
                    for message in messages
                    if isinstance(message.get("content"), str)
                ),
            }
        ]
        body["reasoning_effort"] = "low"
        body["reasoning_format"] = "hidden"
    payload, _ = _json_request(
        "POST",
        f"{GROQ_BASE_URL}/chat/completions",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        json_body=body,
        timeout=timeout,
    )
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ProviderError("missing_model_content") from exc
    if not isinstance(content, str):
        raise ProviderError("unexpected_model_content")
    return content


def extract_incident(
    text: str,
    *,
    model: str,
    api_key: str,
    timeout: float,
    authoritative_coordinates: bool = False,
) -> tuple[StructuredIncident, int]:
    system_prompt = (
        "Extract only facts explicitly supported by the control-room report. "
        "Return the requested JSON object. Use null for unknown values. "
        "Do not produce routes, resources, hospitals, diagnosis, or coordinates."
    )

    def request(attempt: int) -> str:
        user_text = text
        if attempt == 1:
            user_text += (
                "\nPrevious output was rejected. Return JSON only, with every schema field "
                "present and unknown values set to null or empty lists."
            )
        return _groq_chat(
            api_key,
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            schema=_incident_schema(),
            strict=attempt == 0,
            timeout=timeout,
        )

    return run_with_single_retry(
        request,
        lambda raw: validate_explicit_services(
            text,
            parse_structured_output(
                raw, authoritative_coordinates=authoritative_coordinates
            ),
        ),
    )


def transcribe_audio(
    path: Path, *, model: str, api_key: str, timeout: float
) -> str:
    mime_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    try:
        with path.open("rb") as audio_file:
            payload, _ = _json_request(
                "POST",
                f"{GROQ_BASE_URL}/audio/transcriptions",
                headers={"Authorization": f"Bearer {api_key}"},
                files={"file": (path.name, audio_file, mime_type)},
                data={
                    "model": model,
                    "response_format": "json",
                    "language": "ar",
                    "temperature": "0",
                },
                timeout=timeout,
            )
    except OSError as exc:
        raise ProviderError("audio_read_error") from exc
    transcript = payload.get("text")
    if not isinstance(transcript, str):
        raise ProviderError("missing_transcript")
    return transcript


def interpret_image(
    path: Path, *, model: str, api_key: str, timeout: float
) -> tuple[ImageEvidence, int]:
    try:
        encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    except OSError as exc:
        raise ProviderError("image_read_error") from exc
    mime_type = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    system_prompt = (
        "Describe only operationally visible evidence. Use null when uncertain. "
        "Do not infer coordinates, diagnoses, or authoritative casualty counts."
    )

    def request(attempt: int) -> str:
        prompt = "Return JSON only with observations and uncertainty notes."
        if attempt == 1:
            prompt += " Every schema field must be present; use null for unknowns."
        return _groq_chat(
            api_key,
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{encoded}"
                            },
                        },
                    ],
                },
            ],
            schema=_image_schema(),
            strict=attempt == 0,
            timeout=timeout,
        )

    def parse(raw: str) -> ImageEvidence:
        payload = json.loads(raw)
        return ImageEvidence.model_validate(payload)

    return run_with_single_retry(request, parse)


def _gemini_output_text(payload: dict[str, Any]) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str):
        return output_text

    outputs = payload.get("outputs")
    if isinstance(outputs, list):
        for output in reversed(outputs):
            if isinstance(output, dict) and output.get("type") == "text":
                text = output.get("text")
                if isinstance(text, str):
                    return text

    steps = payload.get("steps")
    if isinstance(steps, list):
        for step in reversed(steps):
            if not isinstance(step, dict) or step.get("type") != "model_output":
                continue
            content = step.get("content")
            if not isinstance(content, list):
                continue
            for part in reversed(content):
                if isinstance(part, dict) and part.get("type") == "text":
                    text = part.get("text")
                    if isinstance(text, str):
                        return text

    raise ProviderError("missing_model_content")


def _gemini_interaction(
    api_key: str,
    *,
    model: str,
    input_text: str,
    schema: dict[str, Any],
    timeout: float,
) -> str:
    payload, _ = _json_request(
        "POST",
        f"{GEMINI_BASE_URL}/interactions",
        headers={
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        },
        json_body={
            "model": model,
            "input": input_text,
            "response_format": {
                "type": "text",
                "mime_type": "application/json",
                "schema": schema,
            },
            "generation_config": {
                "temperature": 0,
                "max_output_tokens": 512,
            },
        },
        timeout=timeout,
    )
    return _gemini_output_text(payload)


def gemini_extract_incident(
    text: str,
    *,
    model: str,
    api_key: str,
    timeout: float,
    authoritative_coordinates: bool = False,
) -> tuple[StructuredIncident, int]:
    instructions = (
        "Extract only facts explicitly supported by this control-room report. "
        "Return the requested JSON object. Use null for unknown values. "
        "Do not produce routes, resources, hospitals, diagnosis, or coordinates."
    )

    def request(attempt: int) -> str:
        input_text = f"{instructions}\n\nReport:\n{text}"
        if attempt == 1:
            input_text += (
                "\nPrevious output was rejected. Return JSON only, with every schema field "
                "present and unknown values set to null or empty lists."
            )
        return _gemini_interaction(
            api_key,
            model=model,
            input_text=input_text,
            schema=_incident_schema(),
            timeout=timeout,
        )

    return run_with_single_retry(
        request,
        lambda raw: validate_explicit_services(
            text,
            parse_structured_output(
                raw, authoritative_coordinates=authoritative_coordinates
            ),
        ),
    )


def gemini_health(
    api_key: str | None, *, candidate_model: str, timeout: float
) -> dict[str, Any]:
    if not api_key:
        return {"status": "DEFERRED", "reason": "credential_unavailable"}
    headers = {"x-goog-api-key": api_key}
    try:
        model_payload, _ = _json_request(
            "GET",
            f"{GEMINI_BASE_URL}/models",
            headers=headers,
            params={"pageSize": "100"},
            timeout=timeout,
        )
        available = []
        for item in model_payload.get("models", []):
            if not isinstance(item, dict):
                continue
            methods = item.get("supportedGenerationMethods", [])
            name = item.get("name", "")
            base_id = item.get("baseModelId", "")
            if "generateContent" in methods and ("flash" in name or "flash" in base_id):
                available.append(base_id or name.removeprefix("models/"))
        model = candidate_model if candidate_model in available else (available[0] if available else None)
        if model is None:
            return {"status": "MODEL_NOT_AVAILABLE", "available_flash_models": sorted(available)}
        started = time.perf_counter()
        payload, _ = _json_request(
            "POST",
            f"{GEMINI_BASE_URL}/models/{model}:generateContent",
            headers={**headers, "Content-Type": "application/json"},
            json_body={
                "contents": [{"parts": [{"text": "Return the word OK."}]}],
                "generationConfig": {"maxOutputTokens": 8, "temperature": 0},
            },
            timeout=timeout,
        )
        return {
            "status": "AVAILABLE",
            "model": model,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "response_shape_valid": isinstance(payload.get("candidates"), list),
        }
    except ProviderError as exc:
        status = "QUOTA_BLOCKED" if exc.status_code == 429 else "UNAVAILABLE"
        return {"status": status, "reason": str(exc)}


def tomtom_flow_smoke(
    api_key: str | None, *, point: str, timeout: float
) -> dict[str, Any]:
    if not api_key:
        return {"status": "UNAVAILABLE", "reason": "credential_unavailable"}
    try:
        payload, headers = _json_request(
            "GET",
            f"{TOMTOM_BASE_URL}/traffic/services/4/flowSegmentData/absolute/10/json",
            params={"key": api_key, "point": point, "unit": "kmph"},
            timeout=timeout,
        )
    except ProviderError as exc:
        status = "QUOTA_BLOCKED" if exc.status_code == 429 else "UNAVAILABLE"
        return {"status": status, "reason": str(exc)}
    flow = payload.get("flowSegmentData")
    usable = isinstance(flow, dict) and all(
        field in flow
        for field in ("currentSpeed", "freeFlowSpeed", "currentTravelTime", "freeFlowTravelTime")
    )
    return {
        "status": "AVAILABLE" if usable else "UNUSABLE_RESPONSE",
        "response_shape_valid": usable,
        "rate_limit_headers_present": any(
            key.lower().startswith("x-ratelimit-") for key in headers
        ),
        "test_point": point,
        "source_note": "TomTom documentation sample point unless overridden locally",
    }
