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

## PD-016 — Phase 04 Population, Coverage, and Candidate Planning Policy

**Date:** 2026-09-07
**Status:** Approved
**Owner:** Project owner

### Decision
Phase 04 uses WorldPop Egypt 2025 constrained ~100 m population counts, geodata ID 56914 / R2024B v1, as its only population source. Population is allocated to the existing Nasr City 500 m zones using exact area-weighted raster-cell/zone overlap in a projected metric or equal-area representation. Processed zone population is `REAL_DERIVED`; WorldPop remains the underlying `REAL_PUBLIC` source. NoData is not treated as zero unless the source explicitly defines it as zero.

Coverage uses `PROTOTYPE_TARGET_RESPONSE_TIME_SECONDS = 600`. This is a SirenGrid prototype/benchmark parameter, not an official Egyptian emergency-service SLA, dispatch standard, or guarantee. Coverage is calculated independently for each required resource cohort: resource type plus its sorted required capability tags, when known. Unknown capability is not confirmed capability. Unreachable valid zones remain in the denominator, are undercovered, and are exposed without an invented ETA. When any zone is unreachable, `worst_zone_eta` is null and the result also exposes the finite worst ETA and unreachable-zone details.

Response Requirement Matrix v1 is limited to explicit traffic-collision inputs: LOW/MEDIUM requires one ambulance; HIGH/CRITICAL requires two ambulances and one fire/rescue unit. Requirement precedence is operator-confirmed, then structured/source requirements, then this prototype matrix. Unsupported or insufficient inputs require operator confirmation.

Candidate generation ranks eligible responders by captured incident ETA, route distance, and ID; retains at most five per required cohort; and evaluates at most 50 feasible combinations. The same physical resource may not be assigned twice. Unavailable, incompatible, committed, or unroutable resources are never candidates.

Plans use lower-is-better transparent prototype scoring. The weights are ETA 0.35, coverage 0.40, reserve 0.20, reposition 0.05, hospital 0.00. Terms, weights, policy version, and final score are persisted. Exact ties are resolved by lower raw maximum incident ETA, higher post-dispatch population-weighted coverage, no reposition proposal, then lexicographically sorted resource IDs.

Hypothetical repositioning is evaluated when a covered zone becomes undercovered or population-weighted coverage falls by at least 0.05. It inspects at most three newly undercovered zones and three eligible reserve responders per target; only proposals at or below 600 seconds that improve a primary coverage result without reducing coverage are retained. Repositioning does not mutate resources in Phase 04.

One candidate set has exactly one current `RECOMMENDED` plan and zero or more `ALTERNATIVE` plans. A version-safe selection command promotes one alternative, supersedes all other plans in that set, increments the incident version once, emits audit history, and performs no resource mutation. Existing approval remains limited to the current recommended plan and retains all Phase 01 transactional guards.

### Reason
These explicit prototype policies make population coverage, candidate comparison, and human selection reproducible without presenting prototype values as emergency doctrine or silently weakening existing approval/resource safety.

### Impact
Phase 04 adds deterministic file-backed population preprocessing, coverage/planning contracts, plan alternatives, and version-safe candidate selection. It must preserve the immutable OSM graph, Phase 02 traffic truth/fallback behavior, Phase 03 resource locking, and the existing Golden Flow.

### Notes
`rasterio` is approved as the narrowly scoped GeoTIFF dependency when required. A WorldPop release upgrade, changed target, changed matrix, changed candidate cap, changed score policy, or changed reposition policy requires a new approved decision.

## PD-017 — Phase 04 Joint Required-Cohort Coverage

**Date:** 2026-09-07
**Status:** Approved
**Owner:** Project owner

### Decision
Retain individual coverage snapshots for every required resource cohort and derive one plan-level `JOINT_ALL_REQUIRED_COHORTS_V1` snapshot. A modeled zone is jointly covered only when every required cohort covers it. When all cohort ETAs are finite, joint ETA is their maximum; if any cohort is unreachable, joint ETA is null, the zone is not covered, and the failing cohort IDs remain explicit.

Joint population-weighted coverage counts each zone's population once: the population of jointly covered zones divided by the common modeled-zone population total. Joint baseline, post-dispatch, and later reposition comparisons use the identical required cohort set and denominator. Any joint-unreachable zone makes joint `worst_zone_eta` null; finite worst ETA, unreachable count, IDs, and failing cohorts remain observable.

The existing coverage score penalty is `1 - post_dispatch_joint_population_weighted_coverage`. Per-cohort percentages are not averaged, summed, or dynamically reweighted. A single-cohort incident has joint coverage equal to that cohort. Later reposition candidates for a newly joint-undercovered zone must be eligible for a failing required cohort.

### Reason
This preserves separate service-cohort truth while making the plan-level coverage score reproducible without population double counting or a false claim that an incident area is covered when one required service cannot meet the prototype target.

### Impact
Phase 04 stores and exposes per-cohort and joint coverage facts. Plan-level coverage delta, affected zones, unreachable count, ranking coverage penalty, and reposition triggers use the explicit joint aggregate. Joint coverage remains a prototype model, not an emergency-response guarantee, SLA, simultaneous-arrival claim, or proof of capacity for future incidents.

## PD-018 — Phase 05 Hospital Registry Source

**Date:** 2026-09-07
**Status:** Approved
**Owner:** Project owner

### Decision
Use the existing OSM/Overpass hospital asset as the Phase 05 real static hospital registry. Do not require MOHP data to begin Phase 05. Unavailable static capacity, specialty, service-availability, and emergency-capability fields remain unknown/null. Do not fuzzy-merge similar names; use stable source identity and only deterministic exact duplicate-source deduplication.

### Impact
Hospital location/identity is real public/derived OSM data. Simulated operational state is separate and never presented as static public fact.

## PD-019 — Phase 05 Transport and Hospital Capability Requirements

**Date:** 2026-09-07
**Status:** Approved
**Owner:** Project owner

### Decision
Represent `transport_required` as `true`, `false`, or `unknown`, and represent only explicitly known required hospital capability tags. Sources are operator-confirmed or explicit structured/source facts. Do not infer transport or hospital medical requirements from severity, casualty count, ambulance assignment, incident type, general knowledge, or LLM output. Unknown transport requires operator confirmation; false transport requires no hospital recommendation; true transport with no capability requirement may proceed without capability filtering.

## PD-020 — Phase 05 Simulated Hospital Operational State

**Date:** 2026-09-07
**Status:** Approved
**Owner:** Project owner

### Decision
Use an explicit `SimulatedHospitalGateway` for accepting state, simulated load/free capacity, incoming cases, and timestamps. Defaults are unknown/null until an explicit deterministic fixture/state is supplied. No random, hash-derived, background-evolving, or fake live values are allowed. All operational values are `SIMULATED`.

## PD-021 — Phase 05 Hospital Ranking Policy

**Date:** 2026-09-07
**Status:** Approved
**Owner:** Project owner

### Decision
Use lower-is-better policy `SIRENGRID_PROTOTYPE_HOSPITAL_SCORE_V1`. Hard-filter explicit not-accepting hospitals, confirmed incompatible capabilities, and unreachable destinations. Unknown capability is not incompatible. Use `HOSPITAL_ETA_NORMALIZER_SECONDS = 900` without clamping. Capability penalty is 0 for no requirement or confirmed presence, 0.5 for unknown required capability; load penalty is clamped known simulated load or 0.5 when unknown; freshness penalty is 0 for explicit current simulated state, 0.5 when unknown, and 1 when explicitly stale. Static capacity weight is 0.00 because no reliable static capacity is currently available.

Weights are ETA 0.55, capability 0.20, load 0.20, freshness 0.05, capacity 0.00. Persist raw values, normalized terms, uncertainty, weights, weighted terms, final score, and policy version. Tie-break by score, route ETA, confirmed capability, known load, known incoming cases, then hospital ID. Incoming cases are not a numeric score term.

## PD-022 — Phase 05 Destination Selection and Versioning

**Date:** 2026-09-07
**Status:** Approved
**Owner:** Project owner

### Decision
Destination selection is a separate operator action after response-plan approval. It requires the current approved plan, `transport_required == TRUE`, membership in the current hospital option set, and expected incident/plan/option versions. SQLite write protection applies; stale state returns HTTP 409. Selection creates exactly one current destination, increments incident version once, appends timeline history, and mutates no responder state.

A selected destination may be replaced only before pre-alert request, through another version-safe command. Replacement supersedes the prior selection, increments incident version once, and invalidates locally prepared unsent payloads. Once pre-alert state is `REQUESTED` or later, replacement returns HTTP 409.

## PD-023 — Phase 05 Simulated Hospital Pre-Alert

**Date:** 2026-09-07
**Status:** Approved
**Owner:** Project owner

### Decision
Use `REQUESTED`, `SENT`, `ACKNOWLEDGED`, and `FAILED` states through `SimulatedHospitalGateway`. The default deterministic flow may synchronously reach `ACKNOWLEDGED`; deterministic failure injection is allowed for tests/demo. Requests are idempotent, have no automatic retry, and failed alerts remain failed. Payloads contain known facts only and all delivery/acknowledgement state is `SIMULATED`.

## PD-024 — Phase 05 Corridor Extraction

**Date:** 2026-09-07
**Status:** Approved
**Owner:** Project owner

### Decision
Derive the corridor only from the approved active responder route. Use OSM signal points within `CORRIDOR_SIGNAL_BUFFER_METERS = 50`, project them onto the route, and order by distance along route. Deduplicate by stable source feature ID, or deterministic coordinate identity when unavailable. Do not invent intersections or use named demo roads, straight lines, alternate routes, or unapproved hospital routes.

## PD-025 — Phase 05 Simulated Signal Priority Timing

**Date:** 2026-09-07
**Status:** Approved
**Owner:** Project owner

### Decision
Use `SIGNAL_PRIORITY_SAFETY_LEAD_TIME_SECONDS = 30` for the simulated request-time calculation. Signal states are `NORMAL`, `REQUESTED`, `PREPARING`, `PRIORITY_ACTIVE`, `PASSED`, and `FAILED`. Priority is simulated only and must not modify OSM base ETA, validated TomTom ETA, or approved route ETA. No signal-delay reduction formula is implemented.

## PD-026 — Phase 05 Driver Alert Region

**Date:** 2026-09-07
**Status:** Approved
**Owner:** Project owner

### Decision
Use explicit simulated route progress with `DRIVER_ALERT_LOOKAHEAD_METERS = 500`, `DRIVER_ALERT_BUFFER_METERS = 30`, and `DRIVER_ALERT_EXPIRY_SECONDS = 120`. Recompute only on explicit movement or refresh commands. Replace/expire the previous region, exclude passed route sections, and expire the active region at route end. Driver-alert payloads contain no patient/private incident facts and delivery is simulated.

## PD-027 — Phase 05 API Contract

**Date:** 2026-09-07
**Status:** Approved
**Owner:** Project owner

### Decision
Use separate domain action/state endpoints plus one aggregate read-only operational view under `/api/v1`. REST is canonical; WebSocket is invalidation/update transport only. The API must support hospital options/details/destination/pre-alert, corridor state/priority, driver-alert state/refresh, and an aggregate incident operational-state view. Exact endpoint schemas are implementation detail within these boundaries.

## PD-028 - Phase 06 Structured Extraction Provider

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

### Decision

Structured-extraction `PRIMARY` and `SECONDARY` remain `NOT_SELECTED`. Default
AI extraction is disabled. Phase 06 implements a provider-neutral adapter,
strict typed validation, exactly one schema-repair retry, visible provider
failure state, and manual structured-fact fallback. Qwen, GPT-OSS, and Gemini
remain benchmark evidence/candidates only; none is an operational default.

## PD-029 - Phase 06 Vision Provider

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

### Decision

Run one small fresh safety benchmark on synthetic/non-private fixture images
before enabling vision. The gate requires at least five bounded cases, 100%
schema-valid output, zero critical unsupported facts or identity claims,
explicit unknown preservation, and no invented casualty, location, diagnosis,
or injury facts. A passing candidate is benchmark-approved but remains opt-in
and default-off. A failed or unavailable candidate remains not selected and
manual image evidence remains available.

## PD-030 - Phase 06 Fact and Support Claim Schema

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

### Decision

Persist immutable per-field evidence claims containing the field, value,
`fact_state`, evidence/report reference, qualitative support, provider/model,
observation time, provenance, and uncertainty notes. Claim states are
`ASSERTED`, `EXPLICIT_NEGATIVE`, and `UNKNOWN`. Resolved fields may be
`CONSISTENT`, `CONFLICT`, or `REQUIRES_REVIEW`. Missing mention is unknown,
not an explicit negative.

## PD-031 - Phase 06 Confidence and Support

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

### Decision

Use qualitative support levels `LOW`, `MEDIUM`, and `HIGH`. No numeric
operational threshold is introduced. Provider-native confidence is retained
only as metadata when supplied and never becomes SirenGrid support
automatically. Support is informational/review-oriented and never authorizes
activation, dispatch, routing, hospital selection, signal control, or fact
overwrite.

## PD-032 - Phase 06 Conflicting Facts

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

### Decision

Preserve every evidence claim and never automatically choose the newest,
highest-support, or highest-provider-confidence claim when material facts
conflict. A material conflict sets the resolved field state to `CONFLICT` and
requires operator review. Operator resolution explicitly selects/confirms a
value, increments the incident version once, appends an audit timeline event,
and retains all historical claims.

## PD-033 - Phase 06 Conservative Duplicate Fusion

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

### Decision

Use deterministic prototype association parameters of 500 metres and 900
seconds. Automatic association requires trusted coordinates, both distance and
time gates, compatible known categories, no strong structured contradiction,
and at least one additional deterministic contextual match. No embeddings or
external embedding provider are introduced. Unknown categories or
insufficient evidence produce `REQUIRES_REVIEW`; different known categories
do not auto-associate. Incidents with committed operational state cannot be
auto-merged.

The explicit association results are `AUTO_ASSOCIATE`, `SEPARATE_INCIDENT`,
and `REQUIRES_REVIEW`, with deterministic explanation facts exposed.

## PD-034 - Phase 06 AI Fact Mutation and Activation

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

### Decision

AI creates evidence claims only. It never directly mutates authoritative
incident facts. Operator confirmation is required before projecting material
claims, including location, casualties, severity, trapped-person state, road
blockage, required services, hospital, or transport facts. A credible urgent
control-room report may activate immediately through the existing manual path;
AI, fusion, and corroboration are never activation gates.

## PD-035 - Phase 06 Provider Timeout and Failure

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

### Decision

Use one monotonic 30-second total processing budget per request. Structured
output permits at most one schema-repair retry and never automatically retries
429, 5xx, authentication, or unavailable-provider failures. The approved ASR
chain is Groq Whisper Large v3 followed by Turbo within the same budget, then
manual transcript fallback. No missing transcript or fact is fabricated.

## PD-036 - Phase 06 Evidence Media Contract

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

### Decision

Allow bounded control-room audio and image uploads: audio up to 15 MiB,
images up to 10 MiB, with the approved MIME allowlists and no video. Raw media
is stored outside SQLite under opaque generated media IDs/UUID filenames.
REST responses expose only opaque references, never filesystem paths. MIME and
size are validated before processing, and uploaded media is never committed to
git.

## PD-037 - Phase 06 Report Association and Versioning

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

### Decision

Raw reports, AI claims, and raw media persistence do not increment incident
version. A single authoritative material action increments it exactly once:
operator fact projection, explicit report fusion association, duplicate merge,
or conflict resolution. Any auto-association that attaches an independent
report increments the canonical incident exactly once. Timeline history is
append-only.

## PD-038 - Phase 06 Duplicate Incident State

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

### Decision

When an incident is confirmed as a duplicate, preserve every report/evidence
item, attach relevant reports to the canonical incident, mark the redundant
incident `DUPLICATE_MERGED`, store the canonical incident ID, and append an
auditable link event. Do not transfer resources, plans, hospital selection,
corridor state, or driver alerts automatically. If the redundant incident has
committed operational state, use `REQUIRES_REVIEW` instead.

### Phase 06 carry-forward

The approved ASR chain is Groq Whisper Large v3, Groq Whisper Large v3 Turbo,
then manual operator transcript. Structured extraction infrastructure is
implemented but provider selection is not selected/default-enabled; manual
structured intake is the required fallback. Vision remains disabled by
default even if a benchmark candidate passes.

## PD-039 - Phase 07 Active and Pending Plans

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

After an approved response plan exists, `Incident.current_plan_id` remains the
active approved operational plan. A separate pending-replan pointer identifies
the current replacement recommendation. The old approved plan remains active
while the replacement awaits approval. Replacement approval atomically switches
the active pointer, clears the pending pointer, and preserves the old plan's
history.

## PD-040 - Phase 07 Replan Materiality V1

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

Policy version: `SIRENGRID_REPLAN_MATERIALITY_V1`. Confirmed active-route
closures, unreachable routes, required responder unavailability or conflict,
material requirement changes, unavailable/unreachable selected hospitals, and
multi-incident loss of a required resource are always material. Unknown state
alone is not material. ETA deterioration is material when the increase is at
least 60 seconds or 15 percent. Improvements alone are not material. Route
edge overlap below 0.80 is material; exactly 0.80 is not, unless an active
route closure applies. Coverage is material when a previously jointly covered
zone becomes undercovered or joint coverage drops by at least 0.05. These are
prototype safety parameters, not emergency-service standards.

## PD-041 - Phase 07 Freshness Outside TomTom

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

TomTom retains the Phase 02 60/120-second policy. Other inputs use provider
freshness where available and preserve explicit update timestamps. Inputs with
no approved TTL, including simulated resource GPS, hospital state, evidence,
corridor, and driver-alert state, remain visibly `UNKNOWN`; unknown freshness
alone never triggers replanning.

## PD-042 - Phase 07 Trigger Coalescing

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

Use a five-second per-incident debounce window. Qualifying events merge pending
replan reasons and retain the latest coherent input references. No scheduler,
polling loop, or background worker is introduced. An explicit evaluation/flush
operation is always available. A deterministic repeat of the same active-plan
inputs and trigger facts is idempotent and creates no new plan version.

## PD-043 - Old Plan While Replacement Waits

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

The old approved plan remains fully operational while a replacement is pending.
Recommendation-time evaluation never mutates assignments, positions,
route-progress, approved route, hospital, pre-alert, corridor, or driver-alert
state.

## PD-044 - Active Responder Replacement

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

Reserved/assigned resources may be released and replaced atomically at
replacement approval when availability, version, and locking checks pass.
`EN_ROUTE`, `ON_SCENE`, and `TRANSPORTING` responders are not silently
substituted. An `EN_ROUTE` responder may retain the same physical resource and
receive an approved replacement route calculated from its current modeled
coordinate; the new route starts at progress `0.0`, with old route history
preserved. `ON_SCENE` responders are not generically rerouted and transporting
responders follow hospital-specific rules.

## PD-045 - Phase 07 Hospital Invalidation

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

A confirmed selected-hospital `NOT_ACCEPTING` or unreachable state invalidates
the destination, preserves old pre-alert history, generates new options, and
requires explicit operator selection. No automatic redirect occurs. A new
simulated pre-alert requires approval of the new destination. Unknown state
does not trigger this exception.

## PD-046 - Phase 07 Pending Sets and Concurrency

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

Only one pending replacement candidate set may exist per incident and active
approved plan. Raw trigger recording and no-material-change evaluation do not
increment incident version. Creating or superseding a pending set increments
it exactly once; replacement approval increments it exactly once through the
existing approval transaction. SQLite `BEGIN IMMEDIATE` serializes writers;
stale competing evaluations return `409`, while identical deterministic
repeats return `200` idempotent/no-op.

## PD-047 - Phase 07 Multi-Incident Contention

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

Committed resources are never preempted or stolen. New incidents plan only
against remaining resources and fail visibly/require review when insufficient.
New commitments may invalidate an unapproved pending recommendation, but never
silently alter an approved assignment. No global optimizer or priority doctrine
is introduced.

## PD-048 — Phase 04 Reposition Proposal Selection Policy

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

### Decision

When `simulate_repositioning()` returns multiple accepted proposals for one
candidate response plan, select exactly one representative proposal by highest
post-reposition joint population-weighted coverage; then lowest
post-reposition undercovered-zone count; lowest post-reposition unreachable-
zone count; lowest reposition ETA; lowest reposition distance; and
lexicographically ascending target-zone ID, staging-zone ID, and
repositioned-resource ID.

Only the selected proposal supplies `proposed_reposition_eta_seconds`, the
reposition penalty and weighted term, and the candidate's persisted
hypothetical reposition proposal. The coverage score term remains based on
post-dispatch joint population-weighted coverage. The score remains
lower-is-better with weights ETA 0.35, coverage 0.40, reserve 0.20,
reposition 0.05, and hospital 0.00; the selected reposition penalty remains
selected ETA divided by 600.

### Reason

This makes candidate scoring and persistence deterministic when bounded
simulation produces more than one valid hypothetical recovery action without
changing the approved Phase 04 score policy.

### Impact

Production candidate planning selects and scores one representative
hypothetical reposition proposal before final ranking and persists that same
proposal. Repositioning remains non-operational and does not mutate resources
or graph state.

## PD-049 - Phase 08 Scenario Dataset

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

Phase 08 uses exactly 36 benchmark scenarios: one executable scenario for
each Master Plan case T01-T15 and 21 distinct cross-cutting scenarios. The
dataset is a SirenGrid fixture, not a model of Egyptian incident frequency.

## PD-050 - Phase 08 Baseline Multi-Resource Selection

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

The baseline is greedy. It processes the most constrained required cohort
first, where constrained means fewest currently eligible physical resources.
Ties use canonical cohort ordering. Resources are selected by route ETA,
route distance, and resource ID; selected physical resources are removed from
the remaining pool. There is no backtracking or network optimization.
Insufficient results are visible expected failures.

## PD-051 - Phase 08 Fair Traffic Input

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

Baseline and SirenGrid receive identical scenario-captured traffic snapshots,
closures, freshness state, and fallback condition. Neither engine refreshes
TomTom during a comparison.

## PD-052 - Phase 08 Baseline Coverage Measurement

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

Baseline selection does not use coverage. Its selected resources are evaluated
afterward with the existing Phase 04 coverage engine and
`JOINT_ALL_REQUIRED_COHORTS_V1`, including the same population denominator and
unreachable-zone semantics.

## PD-053 - Phase 08 Baseline Hospital Policy

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

The baseline uses the same OSM registry, simulated state, graph, traffic
state, hard filters, and UNKNOWN semantics as SirenGrid, then chooses the
feasible hospital with the lowest route ETA, followed by route distance and
hospital ID. It does not use the SirenGrid weighted hospital score.

## PD-054 - Phase 08 Multi-Incident Event Order

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

Scenario manifests define event timestamps and explicit event indexes. Both
engines replay the same sequence. Committed resources remain unavailable;
there is no severity-based preemption or resource stealing.

## PD-055 - Phase 08 Traffic Fixture Mode

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

The official benchmark uses fixed reproducible traffic fixtures and makes no
external traffic-provider calls. Fixture metadata retains source,
provenance, original reality, fallback status, freshness semantics, and a
hash/version. Historical live captures are replay fixtures, not current live
data. Optional live-provider smoke is reported separately.

## PD-056 - Phase 08 Repetition and Aggregation

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

All 36 scenarios run exactly once per engine for authoritative functional and
model metrics. A separate ten-scenario performance subset runs one excluded
warm-up and three isolated measured repetitions per engine. Functional
aggregates include count, outcome counts, mean where useful, median, minimum,
maximum, and dataset-level p95 where meaningful. Performance samples are
retained individually; laptop timings are not production SLAs.

## PD-057 - Phase 08 Benchmark Pass Semantics

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

A scenario passes when its declared expected outcome is reached without
violating safety, data, or product contracts. Truthful expected failures,
review states, provider-unavailable states, no-path results, conflicts, and
idempotent no-ops can therefore pass. Comparative superiority is reported
separately from correctness.

## PD-058 - Phase 08 Benchmark Dimensions

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

Phase 08 does not create a composite benchmark score. ETA, coverage, reserve
resilience, hospital result, replanning, workflow success, latency, and
failure handling are reported as separate dimensions.

## PD-059 - Phase 08 Scenario Population and Provenance

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

Scenarios are balanced synthetic/simulated fixtures grounded in available
real OSM, WorldPop, hospital, and road assets. Incident facts and operational
states are synthetic or simulated. CAPMAS calibration is not required, and no
real incident-frequency claim is made.

## PD-060 - Phase 08 Scenario Runner and Demo Controls

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

Phase 08 provides an internal deterministic scenario runner and minimal local
demo REST controls under `/api/v1/simulation`: reset, load, events, and
status. Controls are explicitly simulated/demo-only, gated by configuration,
disabled by default, and have no background scheduler. They must not be
exposed unrestricted on a public deployment.

## PD-061 - Phase 08 Frontend Boundary

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner

This Phase 08 coding run is backend, benchmark, and demo-control only. No
frontend framework or benchmark UI is selected or implemented.

## PD-062 - WorldPop Artifact Integrity Manifest

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner (post-audit hardening mission, HD-016)

### Decision

The WorldPop-derived zone-population artifact carries its own committed
integrity manifest at `data/processed/nasr_city/worldpop_provenance.json`,
separate from the Phase 02 `provenance.json`. The manifest records the
artifact's canonical UTF-8/LF SHA-256, byte count, record count, population
totals, reality labels, and full WorldPop source lineage. It is generated by
`backend/scripts/build_worldpop_zone_population.py` from the same serializer
that writes the artifact, and is enforced by a test that normalizes line
endings before hashing.

### Reason

The artifact is the coverage engine's only population input, but it was absent
from committed artifact provenance and had no hash test, so a silent change
that preserved `zone_count` and `total_modeled_population` would pass every
test. A separate manifest is required because the Phase 02 geospatial refresh
rebuilds `provenance.json` from scratch via `build_provenance()` and would drop
any WorldPop entry recorded there.

### Impact

`provenance.json` continues to describe only the Phase 02 OSM acquisition and
its semantics are unchanged. Population values and geospatial outputs are
unchanged. A rebuild republishes both the artifact and its manifest.

## PD-063 - Single Canonical Response Planner

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner (post-audit hardening mission, HD-001/HD-002)

### Decision

The Phase 04 planning engine is SirenGrid's only response planner. All
planning entry points call one shared orchestration function,
`planning.generate_canonical_candidate_set()`, which resolves response
requirements, routes on the real graph with captured traffic, generates
bounded candidate combinations, computes joint required-cohort coverage,
evaluates hypothetical repositioning, scores and ranks transparently, and
persists the candidate set under the optimistic capture/revalidate guard.

`POST /api/v1/incidents/{incident_id}/plans/generate` is retained as a
backward-compatible facade. It returns only the current `RECOMMENDED` plan so
existing single-plan clients keep working; callers that need alternatives use
`POST /api/v1/incidents/{incident_id}/plans/generate-candidates`.

### Reason

The legacy endpoint previously ran its own nearest-by-ETA selection. It
bypassed traffic-aware routing, joint coverage, candidate comparison,
repositioning, and the planning concurrency guard, so the Golden Flow's
primary planning step did not exercise the approved Phase 04 policy.

It also held no write lock and derived `plan_version` from a stale read.
Concurrent generation therefore returned `201` to every caller and persisted
several current `RECOMMENDED` plans with duplicate `plan_version` values while
incrementing the incident version only once. Routing both entry points through
one engine removes the second algorithm and the race together.

### Impact

Plans returned by the legacy endpoint now carry the canonical
`SIRENGRID_PROTOTYPE_PLAN_SCORE_V1` score breakdown and joint-coverage metrics
instead of the removed Phase 01 stub, and its route records carry responder
`data_reality`/`source` provenance. The route records no longer include the
`resource_name` display field; `resource_id` remains the authoritative
identifier. Scoring weights, the 600-second coverage target, candidate caps,
and the approval boundary are unchanged.

Concurrent generation now yields exactly one persisted candidate set; stale
losers receive `409` rather than silently persisting duplicates.

## PD-064 - Immutable Geospatial Runtime Caching

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner (post-audit hardening mission, HD-001/FX-019)

### Decision

Three immutable geospatial derivations are cached in process:

1. the parsed base GraphML graph, keyed by file path with modification-time
   and size revalidation, so a republished asset is picked up;
2. the graph fingerprint, memoized per graph object and revalidated against
   node and edge counts, so a structurally changed graph never receives a
   stale hash;
3. the zone-centroid to graph-node mapping, keyed by graph fingerprint, zone
   ID, and exact centroid.

Single-source travel-time trees remain per-request because each is large.
Each cache exposes an explicit clear function for tests and asset refreshes.

### Reason

Routing an incident through the canonical planner took roughly 39 seconds.
`graph_fingerprint` serialized all 7,348 nodes and 17,439 edges on every
coverage snapshot (about 40 times per plan, roughly 8.4 seconds), the GraphML
file was reparsed on every request, and every zone centroid was snapped by
scanning all graph nodes, roughly three million haversine evaluations per
plan.

This is safe because the base OSM graph is already specified as immutable
runtime truth: routing copies the graph before removing edges and traffic is
applied as a frozen overlay rather than graph attributes. Regression tests
assert this by comparing `node_link_data` before and after routing and
matching.

### Impact

A canonical plan call drops from about 39 seconds to about 13 seconds, and the
backend test suite from 12m55s to 4m16s. No scoring weight, coverage target,
candidate cap, cohort, or reposition policy changes; the remaining cost is the
approved bounded reposition simulation. Coverage still evaluates every modeled
zone.

## PD-065 - Non-Actionable Incident Planning Fence

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner (post-audit hardening mission, HD-003)

### Decision

`CLOSED`, `CANCELLED_FALSE_REPORT`, `DUPLICATE_MERGED`, and `REQUIRES_REVIEW`
are non-actionable incident statuses. Response-plan generation and response-
plan approval both reject them with HTTP 409 through one shared predicate,
`incidents.ensure_incident_actionable()`.

### Reason

Planning previously fenced only `CLOSED` and `CANCELLED_FALSE_REPORT`. An
incident marked `DUPLICATE_MERGED` could therefore have a plan generated for
it, which reset its status to `AWAITING_APPROVAL` and revived a duplicate that
had already been merged into a canonical incident. Approving that plan would
have committed real responders to an incident no longer being worked.

Approval is fenced separately because an incident can become non-actionable
after its plan was recommended, and the replacement-approval path deliberately
skips the `AWAITING_APPROVAL` status check.

`REQUIRES_REVIEW` is a pre-dispatch hold: automated planning must wait for the
operator to resolve the ambiguity.

### Impact

A merged, cancelled, closed, or review-held incident cannot be revived or
receive responders. Active and replanning states are unaffected, and the
canonical incident of a merge remains fully plannable.

## PD-066 - Deterministic Timeline Event Ordering

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner (post-audit hardening mission)

### Decision

`TimelineEvent.id` is a time-ordered UUIDv7 rather than a random UUID4. The
identifier keeps the canonical 36-character UUID form and remains parseable as
a UUID. The 12 bits after the millisecond timestamp carry a monotonic counter,
so events created inside the same millisecond still order correctly, and a
backwards clock step is absorbed rather than reissuing a lower identifier.

Timeline reads continue to order by `created_at` then `id`.

### Reason

Timeline reads order by `created_at` then `id`, and wall-clock resolution is
coarse enough that consecutive operator commands share a `created_at` value.
With a random UUID4 tiebreak the audit trail was returned in arbitrary order:
measured over 40 reproductions of an
`ASSIGNED -> EN_ROUTE -> ON_SCENE -> TRANSPORTING` sequence, 8 runs produced a
duplicate timestamp and 4 returned the events out of order, including
`ON_SCENE` before `EN_ROUTE`.

This is an auditability defect against Master Plan F16, which requires a
traceable operational history, and it made an existing regression test
intermittently fail once planning became fast enough for commands to land
inside one clock tick.

### Impact

The operator timeline, and every audit consumer ordering by `created_at` then
`id`, now reflects true insertion order. No schema migration is required
because the column type and format are unchanged, and existing stored events
keep working; only ordering among identically stamped events changes. No new
dependency is introduced.

## PD-067 - Controlled False-Report Cancellation

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner (post-audit hardening mission, HD-004)

### Decision

`POST /api/v1/incidents/{incident_id}/cancel` terminates an incident that
turned out to be a false report, setting `CANCELLED_FALSE_REPORT`.

It is permitted only before an operational response is committed. If the
incident has an approved active plan, or any responder assigned to it is
`ASSIGNED`, `EN_ROUTE`, `ON_SCENE`, or `TRANSPORTING`, the command returns
HTTP 409 `RESPONSE_ALREADY_COMMITTED` and names the blocking responders.
Responders are never released automatically; controlled operator resolution is
required instead.

A permitted cancellation is version checked, runs under `BEGIN IMMEDIATE`,
supersedes any unapproved candidate plans, clears the current and pending plan
pointers, increments the incident version exactly once, appends an
`INCIDENT_CANCELLED` timeline event, commits once, and publishes afterwards.

Repeat cancellation returns HTTP 409 `INCIDENT_NOT_CANCELLABLE`, matching the
existing repeat-approval convention rather than introducing a second style.

`REQUIRES_REVIEW` may be cancelled; `CLOSED`, `DUPLICATE_MERGED`, and an
already cancelled incident may not.

### Reason

`CANCELLED_FALSE_REPORT` existed in the lifecycle but no code path ever
assigned it, and `close` only accepts `HANDOVER`. An operator who created an
incident and then learned it was a false alarm had no way to terminate it, so
the queue accumulated incidents that could still be planned against.

### Impact

Cancelled incidents are non-actionable under PD-065, so they cannot be planned
or approved afterwards. No emergency demobilization doctrine is introduced.

## PD-068 - Incident Lifecycle Contract

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner (post-audit hardening mission, HD-005/HD-006)

### Decision

Incident status reaches the database by two explicit paths:

1. **Operator lifecycle progression** through
   `POST /incidents/{id}/transition`, governed by the locked transition table.
2. **Domain commands** that own a status as part of a larger atomic change:
   canonical planning persisting a candidate set (`AWAITING_APPROVAL`), plan
   approval (`RESPONSE_ACTIVE`), duplicate merge (`DUPLICATE_MERGED`), and
   false-report cancellation (`CANCELLED_FALSE_REPORT`).

The canonical path is:

```text
ACTIVE_UNCONFIRMED -> AWAITING_APPROVAL -> RESPONSE_ACTIVE -> EN_ROUTE
-> ON_SCENE -> TRANSPORT_ACTIVE or HANDOVER -> HANDOVER -> CLOSED
```

`ACTIVE_UNCONFIRMED -> AWAITING_APPROVAL` is now legal on the transition table
as well, matching what production persists.

`REQUIRES_REVIEW` is an operator pre-dispatch hold with an explicit entry and
exit: `ACTIVE_UNCONFIRMED <-> REQUIRES_REVIEW`, and it may be terminated
through the cancellation command.

`DUPLICATE_MERGED` and `CANCELLED_FALSE_REPORT` are terminal and are not
reachable as transition targets, because their owning commands carry safety
guards (committed operational state, committed response) that a bare
transition would bypass.

`RESPONSE_PROPOSED` is deprecated/reserved. Production never persists it and
it is not on the canonical path; it remains in the enum and the transition
table only so existing API clients keep working.

### Reason

The transition table previously required `ACTIVE_UNCONFIRMED ->
RESPONSE_PROPOSED -> AWAITING_APPROVAL`, while production set
`AWAITING_APPROVAL` directly, so the documented lifecycle did not describe the
system and `RESPONSE_PROPOSED` was unreachable in practice. `REQUIRES_REVIEW`
had no entry or exit at all, leaving the approved review hold unusable.

### Impact

No extra database write is introduced to visit `RESPONSE_PROPOSED`. The review
hold is now usable and, being non-actionable under PD-065, stops automated
planning until the operator resolves it.

## PD-069 - Unresolved Incident Location

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner (post-audit hardening mission, HD-007)

### Decision

Incident coordinates are optional. A credible urgent report activates an
incident even when its exact location is not yet known.

- `Incident.latitude` and `Incident.longitude` are nullable. There is no
  sentinel coordinate; unresolved means `NULL`.
- Manual intake accepts `location_text` without `location`.
- Serialization returns `location: null` when either coordinate is missing,
  and intake provenance records `location_resolved`.
- Operations that genuinely need a coordinate fail visibly with HTTP 422
  `INCIDENT_LOCATION_REQUIRED` until an operator correction supplies one.
  Response-plan generation is guarded directly; hospital, corridor, and
  driver-alert operations are guarded transitively because they require an
  approved plan.
- `PATCH /incidents/{id}/facts` resolves the coordinates, increments the
  incident version exactly once, and records the correction with an `old`
  value of `null`.
- Duplicate fusion treats an incident without coordinates as having no trusted
  coordinate, so association falls back to review rather than a distance gate.

AI still cannot make coordinates authoritative; only explicit source metadata,
operator input, or deterministic resolution can.

### Reason

Master Plan section 26.1 requires that an emergency with no reliable location
is marked missing rather than pretending routing is possible, but the schema
forced non-null coordinates, so such an incident could not be represented at
all.

### Impact

Existing local databases are migrated in place. SQLite cannot relax a NOT NULL
constraint, so `init_db` rebuilds the incidents table through a
rename/copy/drop sequence inside one transaction, preserving every row. The
migration is skipped once the column is already nullable.

## PD-070 - Co-Located Responder Routing

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner (post-audit hardening mission, HD-008)

### Decision

A responder whose origin snaps to the same routable graph node as the
destination is treated as effectively on location, not as a routing failure.
It yields a valid route with distance 0, ETA 0, and a geometry that repeats the
node coordinate so it stays a structurally valid GeoJSON LineString.

Route metric bounds relax from `> 0` to `>= 0` on `RouteResult`,
`TrafficAwareRouteResult`, and `RoutePreviewResponse`. A zero-length route
traverses no edge, so its traffic coverage ratio is 0 and no overlay or
closure can change it. Route preview returns the zero route instead of 422.

Movement over a zero-length route resolves to the single occupied point at any
progress value rather than raising.

### Reason

Routing raised `RouteNotFoundError` for a same-node snap, and planning treated
that as an unroutable candidate. The closest possible responder, one already
standing at the incident, was therefore silently excluded and planning could
report insufficient resources while a unit was on scene.

Route preview additionally duplicated the same-node policy with its own 422
before routing was called, which is exactly the kind of drift a single
canonical implementation removes.

### Impact

No straight-line or otherwise fabricated travel is introduced; a zero route is
a real measurement of zero distance. Malformed stored geometry, such as
non-numeric or out-of-bounds coordinates, is still rejected visibly. Only the
zero-length case, which is now legitimate, became valid.

## PD-071 - Simulated Hospital Capability Overlay

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner (post-audit hardening mission, HD-009)

### Decision

Hospital operational state gains an explicitly `SIMULATED` capability overlay,
`simulated_capability_tags`, stored on `HospitalOperationalState` and set
through `PATCH /hospitals/{id}/simulation-state`.

The static OSM registry is never modified. Ranking confirms a required
capability from the real public registry first and consults the simulated
overlay only when the registry does not already confirm it. Every score
breakdown records `capability_source`
(`NOT_REQUIRED`, `REAL_PUBLIC_REGISTRY`, `SIMULATED_OVERLAY`, or `UNKNOWN`),
`capability_data_reality`, and the static and simulated tag sets separately,
so a demo capability can never be read as a published hospital fact.

Absence of an overlay remains `UNKNOWN`, never a confirmed incompatibility.

### Reason

Of the 27 OSM hospitals in the Nasr City asset, only one carries any
`healthcare:speciality`, none declares a confirmed incompatibility, and none
publishes capacity. With static capacity weighted 0.00, every non-ETA term was
a uniform constant, so hospital ranking collapsed to nearest-by-ETA and Master
Plan F13, preferring a farther but more suitable hospital, could not be
demonstrated at all.

Inventing specialties in the OSM asset was rejected outright: it would present
simulated data as real public fact.

### Impact

A deterministic fixture can now show a farther hospital winning because it
carries the required burn-care capability, is accepting, and has a lighter
modeled load, with the explanation naming the simulated source. Existing local
databases receive the column through the additive migration path.

## PD-072 - Conservative Fusion Context Gate

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner (post-audit hardening mission, HD-010)

### Decision

The additional deterministic context match required for automatic association
(PD-033) is strengthened. Location phrases are Unicode NFKC normalized and
casefolded, then reduced to significant tokens by dropping fragments shorter
than three characters and a small explicit set of generic road and place words
in English and Arabic.

Overlap-only association now requires at least two shared significant tokens.
An exact normalized significant-phrase match and an identical trusted source
reference remain sufficient on their own. No embeddings or external model are
introduced.

### Reason

The gate accepted any single shared token. Two genuinely separate collisions
400 metres apart, in the same category and ten minutes apart, automatically
associated purely because both phrases contained the word "street"; the same
held in Arabic for "شارع". A false merge attaches one real incident's evidence
to another and is more dangerous than a missed automatic merge.

### Impact

Ambiguous pairs fall back to `REQUIRES_REVIEW` rather than merging. Genuine
corroboration is unaffected: an exact phrase match, two or more shared
significant tokens, or a shared trusted source reference still auto-associate.
Fusion remains a non-activation gate.

## PD-073 - Atomic Fact Correction and Replan Trigger

**Date:** 2026-09-08
**Status:** Approved
**Owner:** Project owner (post-audit hardening mission, HD-014)

### Decision

Recording a replan trigger is split by transaction ownership:

- `record_replan_trigger()` acquires the write lock, records, and commits. It
  is for a REST command that owns the whole request.
- `apply_replan_trigger()` acquires no lock and does not commit. It is for a
  command already inside its own write transaction.

`PATCH /incidents/{id}/facts` uses `apply_replan_trigger()`, so the fact
correction and its trigger commit together in one transaction with one
incident-version increment. The WebSocket event is published after the commit,
with no write lock held during notification.

### Reason

The correction previously committed first and the trigger committed second.
Reproduced with a controlled failure in the second step: the endpoint returned
500 while the correction was durably applied, the incident version had already
advanced from 3 to 4, the facts had changed, a `FACTS_CORRECTED` event was
written, and no WebSocket event was published. The operator saw a failure
while the incident had silently changed.

### Impact

A failure recording the trigger now rolls the whole request back: no version
bump, no fact change, no audit event. The five-second debounce and
idempotency rules are unchanged, and the REST trigger endpoint keeps its
existing commit behaviour.
