# SirenGrid — Phase 00 Architecture Lock & Feasibility Gates

> **Status:** READY TO EXECUTE
>
> **Goal:** Lock SirenGrid Technical Architecture v1.1 and prove the critical external/AI dependencies before Phase 1 begins.
>
> **Product authority:** `docs/MASTER_PLAN.md` v1.2
>
> **Technical authority:** `docs/TECHNICAL_ARCHITECTURE_PLAN.md` v1.1
>
> **Data authority:** `docs/DATA_LIST.md`
>
> **Agent rules:** `AGENTS.md`
>
> **Workflow:** ChatGPT plan → Codex task verification → Antigravity bounded implementation → tests → Codex review → ChatGPT final review.
>
> **Important:** This phase does NOT build the full backend. It removes hidden feasibility/provider blockers and locks the architecture decisions required to safely begin Phase 1.

---

# 0. Required Exit Result

Phase 00 is complete only when all are true:

- [ ] Technical Architecture v1.1 is committed in the repo.
- [ ] PD-006 through PD-015 are recorded in `docs/DECISIONS.md`, with PD-009 explicitly deferred.
- [ ] Python 3.12 development environment works.
- [ ] Groq provider health check works.
- [ ] TomTom credential/basic-response smoke test works.
- [ ] Gemini fallback health check works if credentials/quota are available.
- [ ] Egyptian Arabic ASR sample is tested using Groq Whisper Large v3.
- [ ] `qwen/qwen3.8-27b` and `openai/gpt-oss-120b` are compared on representative SirenGrid structured extraction cases.
- [ ] One image-evidence interpretation is tested.
- [ ] Strict Pydantic validation is applied to structured extraction.
- [ ] Invalid structured output has at most one controlled retry/reformat attempt.
- [ ] Raw inputs are preserved for replay.
- [ ] Provider/model/quota/latency/quality findings are documented.
- [ ] No hidden provider blocker remains.
- [ ] Codex returns `PHASE 00 REVIEW — PASS`.
- [ ] Phase 1 has not started before Phase 00 review passes.

---

# 1. Phase Boundary

## In scope
1. Architecture document update/lock preparation.
2. Decision-log updates.
3. Local Python 3.12 environment.
4. Minimal provider configuration contract.
5. AI/provider feasibility spike.
6. TomTom connectivity smoke test.
7. Provider failure/fallback behavior validation.
8. Benchmark notes used to choose initial configured model roles.
9. Minimal automated tests for the spike where useful.
10. Phase review.

## Out of scope
Do NOT implement yet:
- incident database/lifecycle,
- resource state engine,
- response planning,
- approval transaction logic,
- OSM routing integration,
- WorldPop coverage,
- TomTom-to-OSM matching,
- WebSocket operations stream,
- hospital selection,
- corridor,
- driver alerts,
- report fusion integration,
- dynamic replanning,
- benchmark scenario runner,
- frontend stack.

---

# 2. Mandatory User/Environment Preconditions

Before Codex executes this phase, the human developer should verify:

```powershell
git --version
py -3.12 --version
```

Expected:
- Git installed.
- Python 3.12.x available.

If `py -3.12` is unavailable, install Python 3.12 before proceeding.

No Node.js/frontend setup is required by Phase 00 because the exact frontend stack remains owner-controlled/deferred.

---

# 3. Secrets / API Access Required

Prepare these locally. Never paste them into Git or commit them.

Required:
```text
GROQ_API_KEY
TOMTOM_API_KEY
```

Recommended fallback:
```text
GEMINI_API_KEY
```

Rules:
- Never place secrets in source code.
- `.env` must be gitignored.
- A committed `.env.example` may contain variable names only, never values.
- Provider numeric quota assumptions must not be hardcoded as guaranteed architecture facts.

---

# 4. Local Workspace Layout

Recommended human workspace:

```text
Desktop/
└── Hackathon/
    ├── SirenGrid/
    └── reference-repos/
        └── Egypt-Smart-City-Digital-Twin/
```

Do NOT clone third-party repositories inside `SirenGrid/`.

Primary donor clone:

```powershell
cd "$HOME\Desktop\Hackathon"
mkdir reference-repos -Force
cd reference-repos
git clone https://github.com/MahmoudNagiubX/Egypt-Smart-City-Digital-Twin.git
```

If already cloned:

```powershell
cd "$HOME\Desktop\Hackathon\reference-repos\Egypt-Smart-City-Digital-Twin"
git pull --ff-only
```

Other reference repositories should NOT be cloned all at once. Clone them phase-by-phase only when the relevant subsystem is being implemented.

---

# 5. Git Preparation

```powershell
cd "$HOME\Desktop\Hackathon\SirenGrid"
git status
git remote -v
git pull --ff-only origin main
git switch -c research/phase-00-feasibility
```

Do not implement directly on `main`.

---

# 6. Architecture Document Update

Replace the repo architecture file with the approved v1.1 file:

```text
docs/TECHNICAL_ARCHITECTURE_PLAN.md
```

After owner acceptance, update status to:

```text
🔒 TECHNICALLY LOCKED FOR IMPLEMENTATION — v1.1
```

---

# 7. Decision Log Updates

Modify `docs/DECISIONS.md` and add:

```text
PD-006 — Backend Architecture
PD-007 — MVP Operational Persistence
PD-008 — Geospatial/Routing Stack
PD-009 — Frontend Stack
PD-010 — Realtime Strategy
PD-011 — AI Integration Boundary + Initial Providers
PD-012 — Simulation Gateway Pattern
PD-013 — Coverage Model
PD-014 — Planning Strategy
PD-015 — Replanning Strategy
```

Use the exact approved meanings from Technical Architecture v1.1 section 48.

Important:

```text
PD-009 = DEFERRED / NOT APPROVED IN v1.1
```

---

# 8. Minimal Phase-00 File Structure

```text
backend/
├── feasibility/
│   ├── __init__.py
│   ├── config.py
│   ├── schemas.py
│   ├── providers.py
│   └── run_checks.py
├── tests/
│   └── test_feasibility_schemas.py
├── .env.example
└── requirements-feasibility.txt

data/
└── evaluation/
    └── phase00/
        ├── cases.json
        ├── audio/
        ├── images/
        └── README.md

docs/
└── phases/
    └── PHASE_00_ARCHITECTURE_LOCK_AND_FEASIBILITY.md
```

Do not create placeholders only to match the tree.

---

# 9. Feasibility Dependencies

Suggested `backend/requirements-feasibility.txt`:

```text
pydantic>=2,<3
httpx
pytest
groq
google-genai
python-dotenv
```

Do not add LangChain, LlamaIndex, Redis, Celery, vector databases, or orchestration frameworks.

---

# 10. Configuration Contract

`backend/.env.example` contains names only:

```text
GROQ_API_KEY=
GEMINI_API_KEY=
TOMTOM_API_KEY=
```

`backend/feasibility/config.py` should:
- read environment values,
- expose presence/absence checks,
- never print secret values,
- fail clearly when a required check cannot run because a key is missing.

---

# 11. Evaluation Cases

Create `data/evaluation/phase00/cases.json` with 8–12 representative Egyptian emergency examples.

At minimum include:
1. road crash + trapped person,
2. ambiguous casualty count,
3. vague landmark/location,
4. road blockage,
5. possible building fire,
6. conflicting/uncertain wording,
7. one low-information urgent report,
8. one case where required services are not explicitly known.

Unknown values remain `null`. Do not invent coordinates.

---

# 12. Structured Extraction Schema

Define a strict Pydantic v2 model:

```text
incident_type: str | None
location_text: str | None
latitude: float | None
longitude: float | None
severity: LOW | MODERATE | HIGH | CRITICAL | None
casualty_count: int | None
trapped_person: bool | None
road_blockage: bool | None
required_services: list[str]
missing_critical_fields: list[str]
support_level: LOW | MEDIUM | HIGH
```

Rules:
- latitude/longitude remain null unless authoritative metadata is supplied,
- unknown casualty count remains null,
- severity and support/confidence are separate,
- no route/resource/hospital decision fields.

---

# 13. Provider Interfaces for the Spike

Required conceptual functions:

```python
transcribe_audio(path: Path, model: str) -> str

extract_incident(
    text: str,
    model: str
) -> StructuredIncident

interpret_image(
    path: Path,
    model: str
) -> dict
```

Provider artifacts/logs record:
```text
provider
model
started_at
latency_ms
success
error_type if failed
schema_valid
retry_count
```

Never record API keys.

---

# 14. Task A — Groq Provider Health Check

Check access to:
```text
whisper-large-v3
whisper-large-v3-turbo
qwen/qwen3.8-27b
openai/gpt-oss-120b
```

Document each as:
```text
AVAILABLE | UNAVAILABLE | QUOTA_BLOCKED | MODEL_NOT_AVAILABLE
```

---

# 15. Task B — Egyptian Arabic ASR Spike

Use 3–5 short team-created Egyptian Arabic emergency recordings.

Place them in:
```text
data/evaluation/phase00/audio/
```

Compare:
```text
Groq whisper-large-v3
Groq whisper-large-v3-turbo
```

Record transcript quality and latency.

Do not claim production WER from this small sample.

---

# 16. Task C — Structured Extraction Benchmark

Compare:
```text
qwen/qwen3.8-27b
openai/gpt-oss-120b
```

Required:
1. strict structured output where supported,
2. Pydantic validation,
3. exactly one controlled retry/reformat attempt if invalid,
4. visible failure if still invalid.

Measure:
```text
schema_success_rate
field_match_accuracy
unknown/null preservation
critical hallucination count
average latency_ms
```

Critical hallucinations include invented casualties, coordinates, road blockage, diagnosis, or unsupported service requirements.

---

# 17. Task D — Image Evidence Spike

Test:
```text
qwen/qwen3.8-27b
```

Fallback if available:
```text
Gemini Flash vision capability
```

Allowed evidence:
- possible smoke,
- visible vehicle damage,
- possible road obstruction,
- uncertainty.

Forbidden:
- diagnosis,
- authoritative location inference,
- invented casualties.

---

# 18. Task E — Gemini Fallback Health Check

If `GEMINI_API_KEY` is available:
- verify a currently working suitable Gemini Flash model,
- run one minimal fallback request,
- record actual working model name.

If no key:
```text
Status: DEFERRED — credential unavailable
```

---

# 19. Task F — TomTom Credential / Basic Response Smoke Test

Use `TOMTOM_API_KEY`.

Goal:
- credential works,
- endpoint reachable,
- response usable,
- rate-limit/error metadata detectable.

Do NOT implement TomTom→OSM mapping in Phase 00.

---

# 20. Task G — Provider Failure Behavior

Guarantee:
- raw input preserved,
- failed AI output does not mutate deterministic state,
- invalid JSON is rejected,
- one retry maximum,
- no infinite retry,
- manual fallback documented.

---

# 21. Phase-00 Feasibility Report

Create:
```text
docs/PHASE_00_FEASIBILITY_REPORT.md
```

Required sections:
```text
Environment
Groq health
ASR sample results
Qwen structured extraction results
GPT-OSS structured extraction results
Selected initial structured-extraction primary
Selected secondary
Image interpretation result
Gemini fallback status
TomTom status
Known quota/provider risks
Manual fallback readiness
Blocking issues
Recommendation for Phase 1
```

---

# 22. Verification Commands

```powershell
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements-feasibility.txt
python -m pytest tests/test_feasibility_schemas.py -q
python -m feasibility.run_checks
```

If activation is blocked:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_feasibility_schemas.py -q
.\.venv\Scripts\python.exe -m feasibility.run_checks
```

---

# 23. Codex Review Gate

Required final report:

```text
PHASE 00 REVIEW

Architecture v1.1 present:
DECISIONS updated:
Python 3.12 environment:
Groq health:
ASR feasibility:
Qwen benchmark:
GPT-OSS benchmark:
Selected primary:
Selected secondary:
Image feasibility:
Gemini fallback:
TomTom connectivity:
Schema validation:
Retry/failure behavior:
Secrets check:
Tests:
Repo reconnaissance:
Blocking issues:
Verdict: PASS | FIXES_REQUIRED
```

Do not begin Phase 1 until `PASS`.

---

# 24. Required Codex Orchestration Prompt

```text
We are executing SirenGrid Phase 00 only.

Read in this order:
1. AGENTS.md
2. docs/MASTER_PLAN.md
3. docs/DATA_LIST.md
4. docs/TECHNICAL_ARCHITECTURE_PLAN.md v1.1
5. docs/phases/PHASE_00_ARCHITECTURE_LOCK_AND_FEASIBILITY.md

You are the senior task verifier and implementation reviewer.

First verify this Phase 00 plan matches Technical Architecture v1.1.
Do not silently use the older v1.0/old Phase 01 assumptions.

Use agy-delegate for bounded implementation tasks where useful.
Keep the spike minimal and testable.

Do not build Phase 1 production subsystems.
Do not lock the frontend stack.
Do not invent provider quotas.
Do not expose or commit secrets.
Do not allow more than one structured-output retry.
Do not allow AI-generated coordinates to become authoritative.
Do not let AI failures fabricate emergency facts.

Run the provider/AI/TomTom feasibility checks, produce docs/PHASE_00_FEASIBILITY_REPORT.md, then YOU perform the final Phase 00 review.

Stop after PASS or FIXES_REQUIRED.
Do not start Phase 1.
```

---

# 25. After PASS

After Phase 00 passes, ChatGPT must create a NEW Phase 01 implementation plan based on:
- Technical Architecture v1.1,
- actual Phase-00 provider benchmark results,
- current repository state,
- donor repo reconnaissance.

The old pre-v1.1 Phase 01 plan must not be executed unchanged.

The new Phase 01 Golden-Flow slice is:

```text
manual intake
→ persisted incident
→ available simulated resources
→ minimal real candidate response plan
→ version-checked human approval
→ real OSM route
→ backend state update
→ frontend/mock contract payload
```
