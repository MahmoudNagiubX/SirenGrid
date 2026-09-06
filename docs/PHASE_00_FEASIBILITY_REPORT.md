# SirenGrid Phase 00 Feasibility Report

> Generated: `2026-09-06T14:59:26Z`
> Scope: Phase 00 only. Phase 1 production subsystems were not started.
> Provider responses and credentials are not included in this report.

## Architecture alignment

Phase 00 matches Technical Architecture Plan v1.1 on the following controls: Day-1 AI/provider gates; Groq Whisper Large v3 ASR; Qwen vs GPT-OSS structured extraction; one controlled structured-output retry; Pydantic validation; Gemini fallback; TomTom credential/basic-response smoke test; raw-input replay; non-authoritative AI coordinates; visible/manual AI failure fallback; and a hard stop before Phase 1.

Technical Architecture Plan v1.1 is owner-locked and PD-006 through PD-015 are recorded in `docs/DECISIONS.md`.
- Architecture status: `TECHNICALLY LOCKED FOR IMPLEMENTATION — v1.1`
- PD-006 through PD-015 present: `PD-006, PD-007, PD-008, PD-009, PD-010, PD-011, PD-012, PD-013, PD-014, PD-015`

## Environment

- Python: `3.12.10`
- Required key presence only: `{"GEMINI_API_KEY": true, "GROQ_API_KEY": true, "TOMTOM_API_KEY": true}`
- External media upload authorized for this run: `True`
- Structured extraction enabled by default: `False`
- Raw replay cases: `data/evaluation/phase00/cases.json` (8 cases)
- Audio inputs found: `3`; image inputs found: `1`
- Secrets check: values were not printed, persisted, or included in artifacts.

## Groq health

```json
{
  "status": "AVAILABLE",
  "models": {
    "whisper-large-v3": {
      "status": "AVAILABLE"
    },
    "whisper-large-v3-turbo": {
      "status": "AVAILABLE"
    },
    "qwen/qwen3.8-27b": {
      "status": "AVAILABLE"
    },
    "openai/gpt-oss-120b": {
      "status": "AVAILABLE"
    }
  },
  "rate_limit_headers_present": false
}
```

## ASR sample results

```json
{
  "status": "COMPLETE",
  "files_found": 3,
  "results": [
    {
      "file": "data/evaluation/phase00/audio/case_01.wav",
      "model": "whisper-large-v3",
      "status": "PASS",
      "transcript": " في حريق في عمارة عند مكرم عبيد وفي ناس جوة.",
      "latency_ms": 1087.4,
      "quality_note": "no_same_stem_ground_truth"
    },
    {
      "file": "data/evaluation/phase00/audio/case_01.wav",
      "model": "whisper-large-v3-turbo",
      "status": "PASS",
      "transcript": " في حريق في عمارة عند مقرم عبيد وفي ناس جوه",
      "latency_ms": 752.0,
      "quality_note": "no_same_stem_ground_truth"
    },
    {
      "file": "data/evaluation/phase00/audio/case_02.wav",
      "model": "whisper-large-v3",
      "status": "PASS",
      "transcript": " في حدثة كبيرة عند عباسة العقاد وفي حد مش عارف يطلع من العربية.",
      "latency_ms": 1027.1,
      "quality_note": "no_same_stem_ground_truth"
    },
    {
      "file": "data/evaluation/phase00/audio/case_02.wav",
      "model": "whisper-large-v3-turbo",
      "status": "PASS",
      "transcript": " في حدثة كبيرة عند عباس العقاد وفي حد مش عارف يطلع من العربية",
      "latency_ms": 1137.5,
      "quality_note": "no_same_stem_ground_truth"
    },
    {
      "file": "data/evaluation/phase00/audio/case_03.wav",
      "model": "whisper-large-v3",
      "status": "PASS",
      "transcript": " في عربية عاملة حدثة على طريق النصر والطريق مقفول",
      "latency_ms": 1001.9,
      "quality_note": "no_same_stem_ground_truth"
    },
    {
      "file": "data/evaluation/phase00/audio/case_03.wav",
      "model": "whisper-large-v3-turbo",
      "status": "PASS",
      "transcript": " في عربية عاملة حدثة على طريق النصر والطريق مقفول",
      "latency_ms": 793.4,
      "quality_note": "no_same_stem_ground_truth"
    }
  ]
}
```

The sample is not a production WER claim. A comparable WER is reported only when a same-stem ground-truth transcript is supplied.

## Qwen structured extraction results

```json
{
  "status": "COMPLETE",
  "model": "qwen/qwen3.8-27b",
  "schema_success_rate": 0.25,
  "field_match_accuracy": 0.8,
  "unknown_null_preservation": 1.0,
  "critical_hallucination_count": 5,
  "average_latency_ms": 1655.8,
  "cases": [
    {
      "case_id": "case-01-crash-trapped",
      "status": "FAIL",
      "reason": "invalid_after_one_retry",
      "retry_count": 1,
      "critical_hallucinations": 1,
      "latency_ms": 1898.3
    },
    {
      "case_id": "case-02-ambiguous-casualties",
      "status": "FAIL",
      "reason": "invalid_after_one_retry",
      "retry_count": 1,
      "critical_hallucinations": 1,
      "latency_ms": 2020.7
    },
    {
      "case_id": "case-03-vague-landmark",
      "status": "PASS",
      "retry_count": 0,
      "latency_ms": 1025.6,
      "matched_fields": 4,
      "expected_fields": 5,
      "unknown_fields_preserved": true,
      "critical_hallucinations": 0
    },
    {
      "case_id": "case-04-road-blockage",
      "status": "FAIL",
      "reason": "invalid_after_one_retry",
      "retry_count": 1,
      "critical_hallucinations": 1,
      "latency_ms": 2169.9
    },
    {
      "case_id": "case-05-building-fire",
      "status": "FAIL",
      "reason": "invalid_after_one_retry",
      "retry_count": 1,
      "critical_hallucinations": 1,
      "latency_ms": 2200.6
    },
    {
      "case_id": "case-06-conflicting-details",
      "status": "PASS",
      "retry_count": 0,
      "latency_ms": 1043.8,
      "matched_fields": 4,
      "expected_fields": 5,
      "unknown_fields_preserved": true,
      "critical_hallucinations": 0
    },
    {
      "case_id": "case-07-low-information-urgent",
      "status": "FAIL",
      "reason": "invalid_after_one_retry",
      "retry_count": 1,
      "critical_hallucinations": 1,
      "latency_ms": 2133.8
    },
    {
      "case_id": "case-08-unknown-service",
      "status": "FAIL",
      "reason": "rate_limited",
      "critical_hallucinations": 0,
      "latency_ms": 753.9
    }
  ]
}
```

## GPT-OSS structured extraction results

```json
{
  "status": "COMPLETE",
  "model": "openai/gpt-oss-120b",
  "schema_success_rate": 0.125,
  "field_match_accuracy": 0.8,
  "unknown_null_preservation": 1.0,
  "critical_hallucination_count": 1,
  "average_latency_ms": 3225.6,
  "cases": [
    {
      "case_id": "case-01-crash-trapped",
      "status": "FAIL",
      "reason": "invalid_after_one_retry",
      "retry_count": 1,
      "critical_hallucinations": 0,
      "latency_ms": 2924.2
    },
    {
      "case_id": "case-02-ambiguous-casualties",
      "status": "FAIL",
      "reason": "invalid_after_one_retry",
      "retry_count": 1,
      "critical_hallucinations": 0,
      "latency_ms": 3060.9
    },
    {
      "case_id": "case-03-vague-landmark",
      "status": "FAIL",
      "reason": "invalid_after_one_retry",
      "retry_count": 1,
      "critical_hallucinations": 0,
      "latency_ms": 3319.8
    },
    {
      "case_id": "case-04-road-blockage",
      "status": "PASS",
      "retry_count": 0,
      "latency_ms": 3717.2,
      "matched_fields": 4,
      "expected_fields": 5,
      "unknown_fields_preserved": true,
      "critical_hallucinations": 0
    },
    {
      "case_id": "case-05-building-fire",
      "status": "FAIL",
      "reason": "invalid_after_one_retry",
      "retry_count": 1,
      "critical_hallucinations": 1,
      "latency_ms": 3004.4
    },
    {
      "case_id": "case-06-conflicting-details",
      "status": "FAIL",
      "reason": "invalid_after_one_retry",
      "retry_count": 1,
      "critical_hallucinations": 0,
      "latency_ms": 2871.9
    },
    {
      "case_id": "case-07-low-information-urgent",
      "status": "FAIL",
      "reason": "invalid_after_one_retry",
      "retry_count": 1,
      "critical_hallucinations": 0,
      "latency_ms": 3646.1
    },
    {
      "case_id": "case-08-unknown-service",
      "status": "FAIL",
      "reason": "invalid_after_one_retry",
      "retry_count": 1,
      "critical_hallucinations": 0,
      "latency_ms": 3260.3
    }
  ]
}
```

## Gemini structured extraction results

```json
{
  "status": "COMPLETE",
  "model": "gemini-3.8-flash",
  "schema_success_rate": 0.0,
  "field_match_accuracy": null,
  "unknown_null_preservation": null,
  "critical_hallucination_count": 0,
  "average_latency_ms": 7157.4,
  "cases": [
    {
      "case_id": "case-01-crash-trapped",
      "status": "FAIL",
      "reason": "provider_server_error",
      "critical_hallucinations": 0,
      "latency_ms": 4758.3
    },
    {
      "case_id": "case-02-ambiguous-casualties",
      "status": "FAIL",
      "reason": "rate_limited",
      "critical_hallucinations": 0,
      "latency_ms": 11793.8
    },
    {
      "case_id": "case-03-vague-landmark",
      "status": "FAIL",
      "reason": "rate_limited",
      "critical_hallucinations": 0,
      "latency_ms": 1559.2
    },
    {
      "case_id": "case-04-road-blockage",
      "status": "FAIL",
      "reason": "provider_server_error",
      "critical_hallucinations": 0,
      "latency_ms": 11273.1
    },
    {
      "case_id": "case-05-building-fire",
      "status": "FAIL",
      "reason": "rate_limited",
      "critical_hallucinations": 0,
      "latency_ms": 25576.4
    },
    {
      "case_id": "case-06-conflicting-details",
      "status": "FAIL",
      "reason": "rate_limited",
      "critical_hallucinations": 0,
      "latency_ms": 817.2
    },
    {
      "case_id": "case-07-low-information-urgent",
      "status": "FAIL",
      "reason": "rate_limited",
      "critical_hallucinations": 0,
      "latency_ms": 723.1
    },
    {
      "case_id": "case-08-unknown-service",
      "status": "FAIL",
      "reason": "rate_limited",
      "critical_hallucinations": 0,
      "latency_ms": 758.3
    }
  ]
}
```

- Selected initial structured-extraction primary: `NOT SELECTED`
- Selected secondary: `NOT SELECTED`
- Phase 1 safe fallback: `manual/operator structured intake`; AI structured extraction remains disabled by default until a `provider passes validation before Phase 6 integration`.
- Provider benchmark failures and rate limiting remain recorded findings; no provider is authorized as a default structured-extraction model.

## Image interpretation result

```json
{
  "status": "PASS",
  "file": "data/evaluation/phase00/img1.jpg",
  "retry_count": 0,
  "latency_ms": 1665.2,
  "evidence": {
    "observations": [
      "Multiple firefighters in full turnout gear are visible on a paved street.",
      "A large volume of dark grey and black smoke is rising from a structure in the background.",
      "Bright orange flames are visible within the smoke plume.",
      "A red fire truck is parked on the left side of the street.",
      "A white fire hose is lying on the asphalt road.",
      "A firefighter in the foreground is walking while dragging the hose.",
      "Residential buildings with light-colored siding are visible on the right.",
      "Overhead utility wires cross the scene.",
      "Street signs are visible, including a yellow sign reading 'TO PATERSON PLANK RD' with a left-pointing arrow and a white sign reading 'DO NOT BLOCK INTERSECTION'.",
      "A traffic light is visible on the left side of the street."
    ],
    "possible_smoke_or_fire": true,
    "possible_vehicle_damage": null,
    "possible_road_obstruction": true,
    "casualty_count": null,
    "uncertainty_notes": [
      "The exact extent of the fire and structural damage is obscured by smoke.",
      "It is unclear if the fire has spread to adjacent buildings.",
      "The specific cause of the fire is not visible."
    ]
  },
  "authority_note": "visual evidence is non-authoritative and contains no coordinates"
}
```

Image observations are evidence only. They cannot create authoritative coordinates, diagnosis, or unsupported casualty facts.

## Gemini fallback status

```json
{
  "status": "AVAILABLE",
  "model": "gemini-3.8-flash",
  "latency_ms": 3305.6,
  "response_shape_valid": true
}
```

## TomTom status

```json
{
  "status": "AVAILABLE",
  "response_shape_valid": true,
  "rate_limit_headers_present": false,
  "test_point": "52.41072,4.84239",
  "source_note": "TomTom documentation sample point unless overridden locally"
}
```

The flow check uses TomTom’s documented sample point unless `TOMTOM_TEST_POINT` is supplied locally. It is a credential/response smoke test, not an incident coordinate or TomTom-to-OSM mapping check.

## Known quota/provider risks

- Numeric quotas are not hardcoded as guarantees.
- The runner records only whether rate-limit headers are present and classifies HTTP 429 as `QUOTA_BLOCKED`.
- TomTom-to-OSM matching, caching policy, and broad Nasr City traffic coverage remain deferred to later phases.
- AI provider outages preserve the raw input and produce visible failure; they do not fabricate emergency facts or mutate deterministic state.

## Manual fallback readiness

- Operator transcript entry/correction is the manual ASR fallback.
- Operator structured-fact correction is the manual extraction fallback.
- Raw text cases and any supplied media remain replayable from the Phase 00 evaluation directory.
- No live emergency-call stream is claimed.

## Blocking issues

- None.

## Recommendation for Phase 1

Do not begin Phase 1 until the blocking issues above are resolved and the architecture/decision-log lock steps are accepted. If this report is `FIXES_REQUIRED`, the stop gate remains active.

**Phase 00 automated recommendation: `PASS`**

## Final Phase 00 review

- Architecture v1.1 present and locked: `PASS`
- PD-006 through PD-015 recorded, with PD-009 deferred: `PASS`
- Python 3.12 environment: `PASS`
- Groq health: `AVAILABLE`
- Egyptian Arabic ASR: `COMPLETE` (3 recordings)
- Qwen benchmark: `0.25` schema success; `5` critical unsupported facts
- GPT-OSS benchmark: `0.125` schema success; `1` critical unsupported facts
- Gemini benchmark: `0.0` schema success; provider failures/rate limiting recorded
- Structured extraction primary: `NOT SELECTED`
- Structured extraction secondary: `NOT SELECTED`
- Image evidence: `PASS` with non-authoritative observations
- Gemini fallback health: `AVAILABLE`
- TomTom connectivity: `AVAILABLE`
- Pydantic validation and one-retry cap: `PASS`
- Secrets and Phase 1 boundary: `PASS`
- Manual/operator structured intake isolation: `PASS`; AI structured extraction is disabled by default until provider validation passes before Phase 6 integration
- Owner-approved deferred provider selection: accepted as a known, explicitly isolated condition
- Verdict: `PASS`

## Authoritative implementation references

- https://console.groq.com/docs/speech-to-text
- https://console.groq.com/docs/structured-outputs
- https://console.groq.com/docs/model/qwen/qwen3.8-27b
- https://console.groq.com/docs/model/openai/gpt-oss-120b
- https://ai.google.dev/api/generate-content
- https://ai.google.dev/api/models
- https://docs.tomtom.com/traffic-api/documentation/tomtom-maps/v1/traffic-flow/flow-segment-data
- https://docs.tomtom.com/traffic-api/documentation/tomtom-maps/v1/traffic-incidents/incident-details
