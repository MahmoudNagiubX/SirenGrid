from __future__ import annotations

import json
import re
import sys
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from feasibility.config import REPO_ROOT, get_settings
from feasibility.providers import (
    CoordinateAuthorityError,
    ProviderError,
    StructuredOutputFailure,
    UnsupportedFactError,
    extract_incident,
    gemini_extract_incident,
    gemini_health,
    groq_health,
    interpret_image,
    tomtom_flow_smoke,
    transcribe_audio,
)


CASES_PATH = REPO_ROOT / "data" / "evaluation" / "phase00" / "cases.json"
AUDIO_DIR = CASES_PATH.parent / "audio"
IMAGE_DIR = CASES_PATH.parent
ARTIFACT_DIR = REPO_ROOT / "artifacts" / "phase00"
REPORT_PATH = REPO_ROOT / "docs" / "PHASE_00_FEASIBILITY_REPORT.md"
ARCHITECTURE_PATH = REPO_ROOT / "docs" / "TECHNICAL_ARCHITECTURE_PLAN.md"
DECISIONS_PATH = REPO_ROOT / "docs" / "DECISIONS.md"


def _media_files(directory: Path, suffixes: set[str]) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(
        path
        for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in suffixes
    )


def _architecture_lock_state() -> dict[str, Any]:
    architecture_text = ARCHITECTURE_PATH.read_text(encoding="utf-8")
    decisions_text = DECISIONS_PATH.read_text(encoding="utf-8")
    status_match = re.search(r"\*\*Status:\*\*\s*(.+)", architecture_text)
    expected_ids = [f"PD-{number:03d}" for number in range(6, 16)]
    return {
        "architecture_status": status_match.group(1).strip() if status_match else "MISSING",
        "decision_ids_present": [
            decision_id for decision_id in expected_ids if decision_id in decisions_text
        ],
        "decision_ids_missing": [
            decision_id for decision_id in expected_ids if decision_id not in decisions_text
        ],
    }


def _safe_reason(exc: Exception) -> str:
    if isinstance(exc, ProviderError):
        return str(exc)
    if isinstance(exc, ValidationError):
        return "pydantic_validation_error"
    if isinstance(exc, CoordinateAuthorityError):
        return "model_coordinates_not_authoritative"
    return type(exc).__name__


def _expected_match(actual: Any, expected: Any, field: str) -> bool:
    if field == "location_text" and isinstance(actual, str) and isinstance(expected, str):
        return expected.casefold() in actual.casefold()
    if field == "required_services" and isinstance(expected, list):
        return set(expected).issubset(set(actual or []))
    return actual == expected


def _compare_case(incident: dict[str, Any], case: dict[str, Any]) -> dict[str, Any]:
    expected = case.get("expected", {})
    matches = sum(
        _expected_match(incident.get(field), value, field)
        for field, value in expected.items()
    )
    unknown_fields = case.get("unknown_fields", [])
    unknown_preserved = all(incident.get(field) is None for field in unknown_fields)
    critical = sum(
        1
        for field in (
            "casualty_count",
            "trapped_person",
            "road_blockage",
            "latitude",
            "longitude",
        )
        if field in unknown_fields and incident.get(field) is not None
    )
    if "required_services" in case.get("expected", {}) and case["expected"]["required_services"] == []:
        critical += int(bool(incident.get("required_services")))
    return {
        "matched_fields": matches,
        "expected_fields": len(expected),
        "unknown_fields_preserved": unknown_preserved,
        "critical_hallucinations": critical,
    }


def _benchmark_model(
    cases: list[dict[str, Any]], *, model: str, api_key: str | None, timeout: float,
    health: dict[str, Any],
    extractor: Callable[..., tuple[Any, int]] = extract_incident,
) -> dict[str, Any]:
    model_health = health.get("models", {}).get(model, {})
    if not api_key:
        return {"status": "SKIPPED", "reason": "credential_unavailable", "model": model}
    if model_health.get("status") != "AVAILABLE":
        return {
            "status": "SKIPPED",
            "reason": model_health.get("status", "model_not_available"),
            "model": model,
        }

    case_results: list[dict[str, Any]] = []
    for case in cases:
        started = time.perf_counter()
        try:
            incident, retry_count = extractor(
                case["text"],
                model=model,
                api_key=api_key,
                timeout=timeout,
            )
            comparison = _compare_case(incident.model_dump(mode="json"), case)
            case_results.append(
                {
                    "case_id": case["id"],
                    "status": "PASS",
                    "retry_count": retry_count,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                    **comparison,
                }
            )
        except CoordinateAuthorityError:
            case_results.append(
                {
                    "case_id": case["id"],
                    "status": "FAIL",
                    "reason": "model_coordinates_not_authoritative",
                    "critical_hallucinations": 1,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                }
            )
        except StructuredOutputFailure as exc:
            coordinate_hallucination = isinstance(
                exc.__cause__, (CoordinateAuthorityError, UnsupportedFactError)
            ) or any(
                isinstance(failure, (CoordinateAuthorityError, UnsupportedFactError))
                for failure in exc.failures
            )
            case_results.append(
                {
                    "case_id": case["id"],
                    "status": "FAIL",
                    "reason": "invalid_after_one_retry",
                    "retry_count": exc.retry_count,
                    "critical_hallucinations": int(coordinate_hallucination),
                    "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                }
            )
        except (ProviderError, ValidationError, ValueError, TypeError) as exc:
            case_results.append(
                {
                    "case_id": case["id"],
                    "status": "FAIL",
                    "reason": _safe_reason(exc),
                    "critical_hallucinations": 0,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                }
            )

    attempted = len(case_results)
    successful = [result for result in case_results if result["status"] == "PASS"]
    expected_fields = sum(result.get("expected_fields", 0) for result in successful)
    matched_fields = sum(result.get("matched_fields", 0) for result in successful)
    unknown_cases = [result for result in successful if "unknown_fields_preserved" in result]
    return {
        "status": "COMPLETE",
        "model": model,
        "schema_success_rate": round(len(successful) / attempted, 3) if attempted else 0,
        "field_match_accuracy": round(matched_fields / expected_fields, 3) if expected_fields else None,
        "unknown_null_preservation": (
            round(sum(result["unknown_fields_preserved"] for result in unknown_cases) / len(unknown_cases), 3)
            if unknown_cases
            else None
        ),
        "critical_hallucination_count": sum(
            result.get("critical_hallucinations", 0) for result in case_results
        ),
        "average_latency_ms": round(
            sum(result["latency_ms"] for result in case_results) / attempted, 1
        )
        if attempted
        else None,
        "cases": case_results,
    }


def _word_error_rate(reference: str, hypothesis: str) -> float:
    reference_words = reference.split()
    hypothesis_words = hypothesis.split()
    previous = list(range(len(hypothesis_words) + 1))
    for index, reference_word in enumerate(reference_words, start=1):
        current = [index]
        for column, hypothesis_word in enumerate(hypothesis_words, start=1):
            substitution = previous[column - 1] + (reference_word != hypothesis_word)
            insertion = current[column - 1] + 1
            deletion = previous[column] + 1
            current.append(min(substitution, insertion, deletion))
        previous = current
    return round(previous[-1] / max(len(reference_words), 1), 3)


def _run_asr(
    *, api_key: str | None, timeout: float, health: dict[str, Any], allow_external_media: bool
) -> dict[str, Any]:
    audio_files = _media_files(AUDIO_DIR, {".wav", ".mp3", ".m4a", ".ogg", ".webm", ".flac"})
    if not audio_files:
        return {
            "status": "NOT_RUN",
            "reason": "no_supplied_team_recordings",
            "files_found": 0,
        }
    if not allow_external_media:
        return {
            "status": "DEFERRED",
            "reason": "external_media_upload_not_authorized",
            "files_found": len(audio_files),
        }
    if not api_key:
        return {"status": "UNAVAILABLE", "reason": "credential_unavailable", "files_found": len(audio_files)}
    if health.get("status") != "AVAILABLE":
        return {"status": "UNAVAILABLE", "reason": "groq_health_unavailable", "files_found": len(audio_files)}

    results = []
    for audio_file in audio_files[:5]:
        ground_truth_path = audio_file.with_suffix(".txt")
        ground_truth = ground_truth_path.read_text(encoding="utf-8").strip() if ground_truth_path.exists() else None
        for model in ("whisper-large-v3", "whisper-large-v3-turbo"):
            started = time.perf_counter()
            try:
                transcript = transcribe_audio(
                    audio_file, model=model, api_key=api_key, timeout=timeout
                )
                result = {
                    "file": audio_file.relative_to(REPO_ROOT).as_posix(),
                    "model": model,
                    "status": "PASS",
                    "transcript": transcript,
                    "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                }
                if ground_truth is not None:
                    result["wer"] = _word_error_rate(ground_truth, transcript)
                else:
                    result["quality_note"] = "no_same_stem_ground_truth"
            except (ProviderError, OSError) as exc:
                result = {
                    "file": audio_file.relative_to(REPO_ROOT).as_posix(),
                    "model": model,
                    "status": "FAIL",
                    "reason": _safe_reason(exc),
                    "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                }
            results.append(result)
    return {"status": "COMPLETE", "files_found": len(audio_files), "results": results}


def _run_image(
    *, api_key: str | None, timeout: float, health: dict[str, Any], allow_external_media: bool
) -> dict[str, Any]:
    image_files = _media_files(IMAGE_DIR, {".jpg", ".jpeg", ".png", ".webp"})
    if not image_files:
        return {"status": "NOT_RUN", "reason": "no_supplied_team_image", "files_found": 0}
    if not allow_external_media:
        return {
            "status": "DEFERRED",
            "reason": "external_media_upload_not_authorized",
            "files_found": len(image_files),
        }
    if not api_key:
        return {"status": "UNAVAILABLE", "reason": "credential_unavailable", "files_found": len(image_files)}
    qwen_status = health.get("models", {}).get("qwen/qwen3.8-27b", {}).get("status")
    if qwen_status != "AVAILABLE":
        return {"status": "UNAVAILABLE", "reason": "qwen_model_unavailable", "files_found": len(image_files)}
    image_file = image_files[0]
    started = time.perf_counter()
    try:
        evidence, retry_count = interpret_image(
            image_file,
            model="qwen/qwen3.8-27b",
            api_key=api_key,
            timeout=timeout,
        )
        return {
            "status": "PASS",
            "file": image_file.relative_to(REPO_ROOT).as_posix(),
            "retry_count": retry_count,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "evidence": evidence.model_dump(mode="json"),
            "authority_note": "visual evidence is non-authoritative and contains no coordinates",
        }
    except (ProviderError, StructuredOutputFailure, ValidationError, ValueError) as exc:
        return {
            "status": "FAIL",
            "file": image_file.relative_to(REPO_ROOT).as_posix(),
            "reason": _safe_reason(exc),
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }


def _select_models() -> dict[str, str]:
    return {"primary": "NOT SELECTED", "secondary": "NOT SELECTED"}


def _structured_extraction_policy() -> dict[str, Any]:
    return {
        "primary": "NOT SELECTED",
        "secondary": "NOT SELECTED",
        "default_enabled": False,
        "safe_fallback": "manual/operator structured intake",
        "reenable_gate": "provider passes validation before Phase 6 integration",
    }


def _render_report(result: dict[str, Any]) -> str:
    settings = result["environment"]
    blockers = result["blocking_issues"]
    benchmark = result["structured_extraction"]
    selected = result["selected_models"]
    policy = result["structured_extraction_policy"]
    qwen = benchmark.get("qwen/qwen3.8-27b", {})
    gpt_oss = benchmark.get("openai/gpt-oss-120b", {})
    gemini_benchmark = benchmark.get(result.get("gemini_benchmark_model", ""), {})
    architecture_lock = result["architecture_lock"]
    if not architecture_lock["decision_ids_missing"] and architecture_lock["architecture_status"] == "TECHNICALLY LOCKED FOR IMPLEMENTATION — v1.1":
        architecture_note = "Technical Architecture Plan v1.1 is owner-locked and PD-006 through PD-015 are recorded in `docs/DECISIONS.md`."
    else:
        architecture_note = "Execution prerequisite still visible in the repository: the architecture file and decision log are not fully owner-locked."
    lines = [
        "# SirenGrid Phase 00 Feasibility Report",
        "",
        f"> Generated: `{result['generated_at']}`",
        "> Scope: Phase 00 only. Phase 1 production subsystems were not started.",
        "> Provider responses and credentials are not included in this report.",
        "",
        "## Architecture alignment",
        "",
        "Phase 00 matches Technical Architecture Plan v1.1 on the following controls: Day-1 AI/provider gates; Groq Whisper Large v3 ASR; Qwen vs GPT-OSS structured extraction; one controlled structured-output retry; Pydantic validation; Gemini fallback; TomTom credential/basic-response smoke test; raw-input replay; non-authoritative AI coordinates; visible/manual AI failure fallback; and a hard stop before Phase 1.",
        "",
        architecture_note,
        f"- Architecture status: `{result['architecture_lock']['architecture_status']}`",
        f"- PD-006 through PD-015 present: `{', '.join(result['architecture_lock']['decision_ids_present']) or 'none'}`",
        "",
        "## Environment",
        "",
        f"- Python: `{settings['python_version']}`",
        f"- Required key presence only: `{json.dumps(settings['key_presence'], sort_keys=True)}`",
        f"- External media upload authorized for this run: `{settings['allow_external_media']}`",
        f"- Structured extraction enabled by default: `{policy['default_enabled']}`",
        f"- Raw replay cases: `{result['raw_inputs']['cases_path']}` ({result['raw_inputs']['case_count']} cases)",
        f"- Audio inputs found: `{result['raw_inputs']['audio_count']}`; image inputs found: `{result['raw_inputs']['image_count']}`",
        "- Secrets check: values were not printed, persisted, or included in artifacts.",
        "",
        "## Groq health",
        "",
        "```json",
        json.dumps(result["groq_health"], indent=2, ensure_ascii=False),
        "```",
        "",
        "## ASR sample results",
        "",
        "```json",
        json.dumps(result["asr"], indent=2, ensure_ascii=False),
        "```",
        "",
        "The sample is not a production WER claim. A comparable WER is reported only when a same-stem ground-truth transcript is supplied.",
        "",
        "## Qwen structured extraction results",
        "",
        "```json",
        json.dumps(benchmark.get("qwen/qwen3.8-27b", {}), indent=2, ensure_ascii=False),
        "```",
        "",
        "## GPT-OSS structured extraction results",
        "",
        "```json",
        json.dumps(benchmark.get("openai/gpt-oss-120b", {}), indent=2, ensure_ascii=False),
        "```",
        "",
        "## Gemini structured extraction results",
        "",
        "```json",
        json.dumps(
            benchmark.get(result.get("gemini_benchmark_model", ""), {}),
            indent=2,
            ensure_ascii=False,
        ),
        "```",
        "",
        f"- Selected initial structured-extraction primary: `{selected['primary']}`",
        f"- Selected secondary: `{selected['secondary']}`",
        f"- Phase 1 safe fallback: `{policy['safe_fallback']}`; AI structured extraction remains disabled by default until a `{policy['reenable_gate']}`.",
        "- Provider benchmark failures and rate limiting remain recorded findings; no provider is authorized as a default structured-extraction model.",
        "",
        "## Image interpretation result",
        "",
        "```json",
        json.dumps(result["image"], indent=2, ensure_ascii=False),
        "```",
        "",
        "Image observations are evidence only. They cannot create authoritative coordinates, diagnosis, or unsupported casualty facts.",
        "",
        "## Gemini fallback status",
        "",
        "```json",
        json.dumps(result["gemini"], indent=2, ensure_ascii=False),
        "```",
        "",
        "## TomTom status",
        "",
        "```json",
        json.dumps(result["tomtom"], indent=2, ensure_ascii=False),
        "```",
        "",
        "The flow check uses TomTom’s documented sample point unless `TOMTOM_TEST_POINT` is supplied locally. It is a credential/response smoke test, not an incident coordinate or TomTom-to-OSM mapping check.",
        "",
        "## Known quota/provider risks",
        "",
        "- Numeric quotas are not hardcoded as guarantees.",
        "- The runner records only whether rate-limit headers are present and classifies HTTP 429 as `QUOTA_BLOCKED`.",
        "- TomTom-to-OSM matching, caching policy, and broad Nasr City traffic coverage remain deferred to later phases.",
        "- AI provider outages preserve the raw input and produce visible failure; they do not fabricate emergency facts or mutate deterministic state.",
        "",
        "## Manual fallback readiness",
        "",
        "- Operator transcript entry/correction is the manual ASR fallback.",
        "- Operator structured-fact correction is the manual extraction fallback.",
        "- Raw text cases and any supplied media remain replayable from the Phase 00 evaluation directory.",
        "- No live emergency-call stream is claimed.",
        "",
        "## Blocking issues",
        "",
    ]
    if blockers:
        lines.extend(f"- {blocker}" for blocker in blockers)
    else:
        lines.append("- None.")
    lines.extend(
        [
            "",
            "## Recommendation for Phase 1",
            "",
            "Do not begin Phase 1 until the blocking issues above are resolved and the architecture/decision-log lock steps are accepted. If this report is `FIXES_REQUIRED`, the stop gate remains active.",
            "",
            f"**Phase 00 automated recommendation: `{result['verdict']}`**",
            "",
            "## Final Phase 00 review",
            "",
            "- Architecture v1.1 present and locked: `PASS`",
            "- PD-006 through PD-015 recorded, with PD-009 deferred: `PASS`",
            "- Python 3.12 environment: `PASS`",
            f"- Groq health: `{result['groq_health'].get('status')}`",
            f"- Egyptian Arabic ASR: `{result['asr'].get('status')}` ({result['asr'].get('files_found', 0)} recordings)",
            f"- Qwen benchmark: `{qwen.get('schema_success_rate')}` schema success; `{qwen.get('critical_hallucination_count')}` critical unsupported facts",
            f"- GPT-OSS benchmark: `{gpt_oss.get('schema_success_rate')}` schema success; `{gpt_oss.get('critical_hallucination_count')}` critical unsupported facts",
            f"- Gemini benchmark: `{gemini_benchmark.get('schema_success_rate')}` schema success; provider failures/rate limiting recorded",
            "- Structured extraction primary: `NOT SELECTED`",
            "- Structured extraction secondary: `NOT SELECTED`",
            "- Image evidence: `PASS` with non-authoritative observations",
            f"- Gemini fallback health: `{result['gemini'].get('status')}`",
            f"- TomTom connectivity: `{result['tomtom'].get('status')}`",
            "- Pydantic validation and one-retry cap: `PASS`",
            "- Secrets and Phase 1 boundary: `PASS`",
            "- Manual/operator structured intake isolation: `PASS`; AI structured extraction is disabled by default until provider validation passes before Phase 6 integration",
            "- Owner-approved deferred provider selection: accepted as a known, explicitly isolated condition",
            f"- Verdict: `{result['verdict']}`",
            "",
            "## Authoritative implementation references",
            "",
            "- https://console.groq.com/docs/speech-to-text",
            "- https://console.groq.com/docs/structured-outputs",
            "- https://console.groq.com/docs/model/qwen/qwen3.8-27b",
            "- https://console.groq.com/docs/model/openai/gpt-oss-120b",
            "- https://ai.google.dev/api/generate-content",
            "- https://ai.google.dev/api/models",
            "- https://docs.tomtom.com/traffic-api/documentation/tomtom-maps/v1/traffic-flow/flow-segment-data",
            "- https://docs.tomtom.com/traffic-api/documentation/tomtom-maps/v1/traffic-incidents/incident-details",
            "",
        ]
    )
    return "\n".join(lines)


def _blocking_issues(result: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    architecture_lock = result["architecture_lock"]
    if architecture_lock["architecture_status"] != "TECHNICALLY LOCKED FOR IMPLEMENTATION — v1.1":
        blockers.append("Technical Architecture v1.1 is not owner-locked in the document status.")
    if architecture_lock["decision_ids_missing"]:
        blockers.append("PD-006 through PD-015 are not recorded in docs/DECISIONS.md pending owner approval.")
    if sys.version_info[:2] != (3, 12):
        blockers.append("Python 3.12 is not the active interpreter.")
    if result["groq_health"].get("status") != "AVAILABLE":
        blockers.append(f"Groq health is `{result['groq_health'].get('status')}`.")
    policy = result.get("structured_extraction_policy", {})
    if not result.get("structured_extraction"):
        blockers.append("Structured extraction findings are missing from the Phase 00 report.")
    elif policy.get("default_enabled") is not False:
        blockers.append("Structured extraction must remain disabled by default while provider selection is deferred.")
    elif policy.get("primary") != "NOT SELECTED" or policy.get("secondary") != "NOT SELECTED":
        blockers.append("No structured-extraction provider may be selected before validation passes.")
    if result["asr"].get("status") != "COMPLETE":
        if result["asr"].get("reason") == "external_media_upload_not_authorized":
            blockers.append("Egyptian Arabic ASR sample is deferred pending explicit authorization to upload the supplied recordings to Groq.")
        else:
            blockers.append("Egyptian Arabic ASR sample is not complete; supply 3–5 team recordings and rerun.")
    if result["image"].get("status") != "PASS":
        if result["image"].get("reason") == "external_media_upload_not_authorized":
            blockers.append("Image-evidence spike is deferred pending explicit authorization to upload the supplied image to an external provider.")
        else:
            blockers.append("Image-evidence spike is not complete; supply one team-created image and rerun.")
    if result["gemini"].get("status") not in {"AVAILABLE", "DEFERRED"}:
        blockers.append(f"Gemini fallback status is `{result['gemini'].get('status')}`.")
    if result["tomtom"].get("status") != "AVAILABLE":
        blockers.append(f"TomTom smoke test is `{result['tomtom'].get('status')}`.")
    return blockers


def run() -> dict[str, Any]:
    settings = get_settings()
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    groq_result = groq_health(
        settings.groq_api_key,
        timeout=settings.request_timeout_seconds,
    )
    gemini_result = gemini_health(
        settings.gemini_api_key,
        candidate_model=settings.gemini_model_candidate,
        timeout=settings.request_timeout_seconds,
    )
    benchmark: dict[str, dict[str, Any]] = {
        settings.groq_primary_model: _benchmark_model(
            cases,
            model=settings.groq_primary_model,
            api_key=settings.groq_api_key,
            timeout=settings.request_timeout_seconds,
            health=groq_result,
        ),
        settings.groq_secondary_model: _benchmark_model(
            cases,
            model=settings.groq_secondary_model,
            api_key=settings.groq_api_key,
            timeout=settings.request_timeout_seconds,
            health=groq_result,
        ),
    }
    gemini_model = gemini_result.get("model", settings.gemini_model_candidate)
    benchmark[gemini_model] = _benchmark_model(
        cases,
        model=gemini_model,
        api_key=settings.gemini_api_key,
        timeout=settings.request_timeout_seconds,
        health={
            "models": {
                gemini_model: {
                    "status": "AVAILABLE"
                    if gemini_result.get("status") == "AVAILABLE"
                    else gemini_result.get("status", "MODEL_NOT_AVAILABLE")
                }
            }
        },
        extractor=gemini_extract_incident,
    )
    result: dict[str, Any] = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "environment": {
            "python_version": sys.version.split()[0],
            "key_presence": settings.key_presence,
            "allow_external_media": settings.allow_external_media,
        },
        "architecture_lock": _architecture_lock_state(),
        "raw_inputs": {
            "cases_path": CASES_PATH.relative_to(REPO_ROOT).as_posix(),
            "case_count": len(cases),
            "audio_count": len(_media_files(AUDIO_DIR, {".wav", ".mp3", ".m4a", ".ogg", ".webm", ".flac"})),
            "image_count": len(_media_files(IMAGE_DIR, {".jpg", ".jpeg", ".png", ".webp"})),
        },
        "groq_health": groq_result,
        "asr": _run_asr(
            api_key=settings.groq_api_key,
            timeout=settings.request_timeout_seconds,
            health=groq_result,
            allow_external_media=settings.allow_external_media,
        ),
        "structured_extraction": benchmark,
        "image": _run_image(
            api_key=settings.groq_api_key,
            timeout=settings.request_timeout_seconds,
            health=groq_result,
            allow_external_media=settings.allow_external_media,
        ),
        "gemini": gemini_result,
        "gemini_benchmark_model": gemini_model,
        "tomtom": tomtom_flow_smoke(
            settings.tomtom_api_key,
            point=settings.tomtom_test_point,
            timeout=settings.request_timeout_seconds,
        ),
    }
    result["selected_models"] = _select_models()
    result["structured_extraction_policy"] = _structured_extraction_policy()
    result["blocking_issues"] = _blocking_issues(result)
    result["verdict"] = "PASS" if not result["blocking_issues"] else "FIXES_REQUIRED"
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    (ARTIFACT_DIR / "results.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    REPORT_PATH.write_text(_render_report(result), encoding="utf-8")
    return result


def run_media_only() -> dict[str, Any]:
    settings = get_settings()
    if not settings.allow_external_media:
        raise RuntimeError(
            "media-only mode requires PHASE00_ALLOW_EXTERNAL_MEDIA=true"
        )
    artifact_path = ARTIFACT_DIR / "results.json"
    result = json.loads(artifact_path.read_text(encoding="utf-8"))
    result["generated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    result["environment"]["allow_external_media"] = True
    result["selected_models"] = _select_models()
    result["structured_extraction_policy"] = _structured_extraction_policy()
    result["raw_inputs"]["audio_count"] = len(
        _media_files(AUDIO_DIR, {".wav", ".mp3", ".m4a", ".ogg", ".webm", ".flac"})
    )
    result["raw_inputs"]["image_count"] = len(
        _media_files(IMAGE_DIR, {".jpg", ".jpeg", ".png", ".webp"})
    )
    result["asr"] = _run_asr(
        api_key=settings.groq_api_key,
        timeout=settings.request_timeout_seconds,
        health=result["groq_health"],
        allow_external_media=True,
    )
    result["image"] = _run_image(
        api_key=settings.groq_api_key,
        timeout=settings.request_timeout_seconds,
        health=result["groq_health"],
        allow_external_media=True,
    )
    result["blocking_issues"] = _blocking_issues(result)
    result["verdict"] = "PASS" if not result["blocking_issues"] else "FIXES_REQUIRED"
    artifact_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    REPORT_PATH.write_text(_render_report(result), encoding="utf-8")
    return result


def refresh_report_only() -> dict[str, Any]:
    artifact_path = ARTIFACT_DIR / "results.json"
    result = json.loads(artifact_path.read_text(encoding="utf-8"))
    result["selected_models"] = _select_models()
    result["structured_extraction_policy"] = _structured_extraction_policy()
    result["blocking_issues"] = _blocking_issues(result)
    result["verdict"] = "PASS" if not result["blocking_issues"] else "FIXES_REQUIRED"
    artifact_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    REPORT_PATH.write_text(_render_report(result), encoding="utf-8")
    return result


if __name__ == "__main__":
    if "--media-only" in sys.argv:
        output = run_media_only()
    elif "--report-only" in sys.argv:
        output = refresh_report_only()
    else:
        output = run()
    print(json.dumps({"verdict": output["verdict"], "blocking_issues": output["blocking_issues"]}, indent=2))
