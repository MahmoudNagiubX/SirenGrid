# SirenGrid Decision Log

This file records approved product and architecture decisions that materially affect the project.

The detailed product behavior remains defined by `docs/MASTER_PLAN.md`.

## How to Record a Decision

Use the following format:

```markdown
## PD-### — Short Decision Title

**Date:** YYYY-MM-DD  
**Status:** Approved / Superseded  
**Owner:** Name or role

### Decision
What was decided.

### Reason
Why this option was selected.

### Impact
Which flows, files, interfaces, or features are affected.

### Notes
Any constraints or follow-up work.
```

---

## PD-001 — Product Name

**Date:** 2026-09-06  
**Status:** Approved

### Decision
The project name is **SirenGrid**.

### Reason
The name represents an emergency signal (`Siren`) and the coordinated network of incidents, responders, roads, coverage, hospitals, and alerts (`Grid`).

### Impact
Use `SirenGrid` as the primary product name across the repository and product-facing interfaces.

---

## PD-002 — MVP Geography

**Date:** 2026-09-06  
**Status:** Approved

### Decision
The MVP targets **Nasr City, Cairo**.

Initial working/demo zone:
**Rabaa → Tayaran → Abbas El Akkad → Makram Ebeid → El Nasr Road**.

Long-term product vision may expand to Greater Cairo.

---

## PD-003 — Final Demo Scenario

**Date:** 2026-09-06  
**Status:** Open / Not Locked

### Decision
Do not hardcode the product around one final demo incident yet.

Current leading reference candidate: **multi-casualty urban road incident**.
A major urban building fire remains an alternative.

### Impact
Implementation must support the approved product workflow without depending structurally on one exact demo story.

---

## PD-004 — Bonus Feature Gate

**Date:** 2026-09-06  
**Status:** Approved

### Decision
**Social Media Intelligence** is the only currently approved bonus feature.

It should begin only after the core end-to-end workflow is stable and demo-ready.

---

## PD-005 — Control-Room-Side Emergency Intake

**Date:** 2026-09-06  
**Status:** Approved

### Decision
SirenGrid is an **operator/control-room system**, not a citizen-facing emergency-reporting application.

Citizens continue using normal existing emergency behavior, such as calling the relevant emergency service. SirenGrid begins on the control-room side when emergency information reaches the operator environment.

Primary intake may include emergency-call audio/transcripts, operator-entered information, available caller location/metadata, evidence received or forwarded through existing authorized operational channels, responder updates, and hospital updates.

The MVP must not require citizens to discover, install, open, or submit reports through a SirenGrid application.

Social Media Intelligence remains a separate bonus source of unverified external signals and is not a citizen reporting workflow.

### Reason
This matches realistic emergency behavior and keeps SirenGrid focused on its actual primary user: the Emergency Control Room Operator / Dispatcher.

### Impact
The intake model, golden flow, multimodal intake wording, reference demo stories, and final Master Plan summary are updated to use a control-room-side intake boundary. The immediate-response rule is unchanged: one credible urgent report received by the control room can activate the incident workflow.

---

## PD-006 — Backend Architecture

**Date:** 2026-09-06  
**Status:** Approved  
**Owner:** Project owner

### Decision
Use Python 3.12 with a FastAPI modular monolith, one backend instance/worker for the MVP, and no microservices or event bus.

### Reason
The Golden Flow requires a small, inspectable runtime with deterministic state ownership and low operational overhead.

### Impact
Backend modules share one process and explicit contracts. Phase 1 must not introduce distributed runtime infrastructure.

### Notes
CPU-heavy work must not block the async event loop; the single-worker boundary remains explicit.

## PD-007 — MVP Operational Persistence

**Date:** 2026-09-06  
**Status:** Approved  
**Owner:** Project owner

### Decision
Use SQLite with SQLAlchemy for mutable runtime state. Keep geospatial assets file/graph based.

### Reason
This is sufficient for the MVP’s single-worker operational state while preserving the approved geospatial asset model.

### Impact
Incident, resource, hospital, plan, approval, and related mutable state use the Phase 1 persistence boundary. Geospatial assets remain separately versioned files/graphs.

### Notes
No production persistence subsystem is started in Phase 00.

## PD-008 — Geospatial and Routing Stack

**Date:** 2026-09-06  
**Status:** Approved  
**Owner:** Project owner

### Decision
Use OSMnx, NetworkX, GeoPandas, Shapely, and pyproj around a refreshed OSM/Geofabrik graph, GraphML storage, and a GeoJSON map contract. Claim turn restrictions only when explicitly processed and validated.

### Reason
This matches the approved real-road-network and progressive routing strategy without overstating turn-restriction support.

### Impact
Phase 1 routing and map contracts must preserve graph/version provenance and explicit restriction-support semantics.

### Notes
TomTom-to-OSM mapping remains progressive and is not implemented in Phase 00.

## PD-009 — Frontend Stack

**Date:** 2026-09-06  
**Status:** Deferred / Not Approved  
**Owner:** Project owner

### Decision
Defer the exact frontend technology stack. Frontend owner review and approval are required separately.

### Reason
The architecture review intentionally leaves frontend framework selection owner-controlled.

### Impact
Phase 1 may define frontend-neutral backend/mock contracts, but must not treat this decision as approval of a frontend framework.

### Notes
No frontend stack is locked by this decision log entry.

## PD-010 — Realtime Strategy

**Date:** 2026-09-06  
**Status:** Approved  
**Owner:** Project owner

### Decision
Use a FastAPI WebSocket operations stream in the single backend process, with REST recovery after reconnects or version gaps.

### Reason
Operators need live updates while retaining a deterministic recovery path.

### Impact
Realtime contracts must include versions/gaps and a REST resynchronization path.

### Notes
The operations stream is a Phase 1 contract, not a Phase 00 subsystem.

## PD-011 — AI Integration Boundary and Initial Providers

**Date:** 2026-09-06  
**Status:** Approved  
**Owner:** Project owner

### Decision
Use provider adapters for ASR and structured multimodal interpretation. The deterministic core owns operational calculations. Initial benchmark-gated providers are Groq Whisper Large v3, Groq Qwen 3.8 27B, GPT-OSS 120B as the secondary candidate, Gemini Flash as the cross-provider fallback, and validated local/manual fallbacks.

### Reason
This separates evidence interpretation from operational truth and avoids making the MVP dependent on one provider.

### Impact
AI output remains validated, non-authoritative evidence. Provider selection is based on Phase 00 evidence and may not bypass safety gates.

### Notes
Coordinates from AI are never authoritative without approved source/operator/deterministic resolution. Structured output gets at most one controlled retry.

## PD-012 — Simulation Gateway Pattern

**Date:** 2026-09-06  
**Status:** Approved  
**Owner:** Project owner

### Decision
Keep fleet, hospital, traffic-signal, driver-alert, and acknowledgement integrations as explicit simulated adapters in the MVP.

### Reason
The project does not claim unavailable government, emergency-service, hospital, telecom, or traffic-control integrations.

### Impact
Simulation status must be visible at integration boundaries and must drive real SirenGrid logic where specified.

### Notes
No simulated operational subsystem is implemented in Phase 00.

## PD-013 — Coverage Model

**Date:** 2026-09-06  
**Status:** Approved  
**Owner:** Project owner

### Decision
Aggregate WorldPop data to SirenGrid zones and calculate graph-based response-time coverage using a configurable prototype threshold.

### Reason
This preserves the approved population-derived coverage model and keeps the prototype threshold explicit.

### Impact
Coverage calculations must retain source/provenance metadata and must not imply an official emergency-service coverage standard.

### Notes
Coverage computation is out of scope for Phase 00.

## PD-014 — Planning Strategy

**Date:** 2026-09-06  
**Status:** Approved  
**Owner:** Project owner

### Decision
Use the approved prototype response-requirement matrix, hard-constraint filtering, and transparent candidate-plan scoring. Do not use autonomous ethical triage or hidden LLM scoring.

### Reason
Response planning must be inspectable, bounded, and separate from AI evidence interpretation.

### Impact
Phase 1 planning contracts must expose constraints, scoring inputs, and the human approval boundary.

### Notes
The prototype matrix is not official dispatch doctrine.

## PD-015 — Replanning Strategy

**Date:** 2026-09-06  
**Status:** Approved  
**Owner:** Project owner

### Decision
Use event-driven deterministic replan orchestration with materiality/debouncing, plan versioning, and renewed human approval for material changes.

### Reason
Operational updates must trigger explainable plan changes without churn or unauthorized dispatch changes.

### Impact
Phase 1 replan commands must be version-checked and must preserve the approval boundary.

### Notes
Dynamic replanning remains out of scope for Phase 00.
