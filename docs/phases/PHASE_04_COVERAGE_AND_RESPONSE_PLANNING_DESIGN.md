# SirenGrid Phase 04 — Coverage and Response Planning Design

**Status:** Owner-approved design
**Scope:** Phase 04 only
**Product authority:** `docs/MASTER_PLAN.md` v1.2
**Architecture authority:** `docs/TECHNICAL_ARCHITECTURE_PLAN.md` v1.1
**Decision record:** PD-016, PD-017

## Boundary

Phase 04 adds deterministic population-derived coverage and candidate response planning. It preserves immutable OSM graph truth, Phase 02 captured traffic-overlay semantics, Phase 03 simulated operational resource state, transactional approval, and REST as canonical state.

It does not add hospital ranking, live hospital data, corridor/preemption, driver alerts, AI intake/fusion, replanning, multi-incident optimization, a scenario engine, frontend work, or Phase 05 behavior.

## Reconnaissance

SirenGrid already has 416 file-backed Nasr City 500 m zones, a real OSM-derived GraphML graph, point-to-point base/traffic-aware routing, simulated resource positions, and one-current-plan approval safeguards. It has no WorldPop raster or populated-zone artifact.

The local pinned Egypt-Smart-City-Digital-Twin donor at `93ca9e90e2fc52c914dd5ccbe42bdc84ce745d3d` was inspected. SirenGrid already uses its compatible Nasr City boundary/grid provenance pattern. Its zero-valued, insufficiently-provenanced population CSV is rejected; no donor code is copied. ResQPath's MIT-licensed repository was inspected conceptually for resource-selection flow, but its unavailable-resource fallback, zeroed route failures, and straight-line movement are rejected. AmbulanceDeployment was inspected as a coverage/deployment concept only; its Austin-specific optimization stack is not reused.

## Population artifact

The only accepted source is WorldPop Egypt 2025 constrained ~100 m, geodata ID 56914 / R2024B v1. Acquisition metadata records URL, DOI/release reference, retrieval timestamp, checksum, source CRS, NoData declaration, and source filename. A failed acquisition or validation fails visibly and preserves the last validated artifact.

Raster cells intersecting the modeled zone union are allocated by exact overlap fraction in a projected metric/equal-area CRS:

`allocated_population = pixel_population * overlap_area / pixel_area`

Each intersecting pixel is apportioned across zones, not duplicated. Non-negative values, deterministic zone IDs, spatial coverage, conservation within the modeled clipping union, and provenance are validated. The generated zone artifact is `REAL_DERIVED`; its WorldPop input is `REAL_PUBLIC`.

## Coverage snapshot

A coverage calculation captures one graph/traffic state before evaluation. It uses the Phase 02 overlay only when the captured snapshot is valid and usable; otherwise it visibly uses immutable `OSM_BASE_TRAVEL_TIME`. The base graph is never mutated.

Each cohort is `resource_type` plus sorted required capability tags. For every eligible AVAILABLE resource in that cohort, the engine snaps its current simulated coordinate to the graph and performs one single-source graph travel-time computation. Zone ETA is the finite minimum ETA to its centroid. A zone is covered when `zone_eta <= 600` seconds.

All valid modeled zones remain in the denominator. An unreachable zone is undercovered and explicit. If any exist, `worst_zone_eta` is null; the snapshot exposes `worst_finite_zone_eta`, `unreachable_zone_count`, and IDs. The snapshot retains source/provenance, input reality, modeled-at timestamp, graph/traffic references, target, population totals, coverage metrics, and zone explanations.

For a multi-cohort incident, individual cohort snapshots remain separately available and a `JOINT_ALL_REQUIRED_COHORTS_V1` plan-level snapshot is derived over the same zones and denominator. A zone is joint-covered only if every required cohort covers it. Its finite joint ETA is the maximum cohort ETA; any unreachable cohort makes joint ETA null and is recorded as a failing cohort. Joint population-weighted coverage counts zone population once. Joint coverage delta, affected zones, unreachable facts, scoring coverage penalty, and later reposition triggers use this aggregate; a single cohort's joint snapshot is identical to its cohort snapshot.

## Hypothetical dispatch and planning

Candidate evaluation first computes the baseline from currently AVAILABLE eligible resources. It removes only candidate-dispatched resources from a copied analytical availability set, then recomputes post-dispatch coverage. It never mutates resource state.

Requirements resolve in this order: explicit operator-confirmed requirements, explicit structured/source requirements, Prototype Response Requirement Matrix v1. The matrix supports only traffic-collision LOW/MEDIUM and HIGH/CRITICAL inputs as recorded in PD-016. Unsupported or incomplete inputs fail visibly.

Eligible candidates must have assignable state, required type/capability, an uncommitted compatible assignment, valid location, and feasible captured-state route. Resources are ranked by ETA, route distance, then ID; the top five per cohort are considered and no more than 50 feasible combinations are evaluated. A physical resource cannot fill two requirements.

## Metrics, ranking, and repositioning

Each candidate persists assignments, route facts, baseline/post-dispatch per-cohort snapshots, baseline/post-dispatch joint snapshots, joint coverage delta, undercovered/unreachable zones with failing cohorts, reserve state, score terms, score policy version, and optional hypothetical reposition facts. Hospital fields remain null/empty in Phase 04.

The lower-is-better score and exact normalized terms are recorded in PD-016. The score is reproducible from stored raw terms, configured weights, and weighted terms. No LLM contributes to planning or scoring.

Repositioning is only simulated. It runs after qualifying coverage loss, considers only the approved bounded reserve/zone candidates, rejects ETAs above the target, and retains a proposal only when it improves a primary coverage result without reducing coverage versus the same post-dispatch plan.

## Candidate lifecycle and contracts

One generated candidate set has one current `RECOMMENDED` candidate and zero or more `ALTERNATIVE` candidates. Only the current recommendation can be approved. A version-safe operator-selection command promotes a chosen alternative, supersedes all remaining plans in that candidate set, increments the incident once, synchronizes the chosen plan version, appends timeline history, and does not mutate resource state.

REST comparison responses expose deterministic facts only: the recommendation, alternatives, assignments, route facts, coverage comparison, affected zones, reserve/reposition facts, score and score breakdown, prototype labels, and routing/data provenance. Existing single-plan response fields remain available where practical.

## Reality and safety rules

- WorldPop source: `REAL_PUBLIC`; processed zone population: `REAL_DERIVED`.
- OSM graph: existing `REAL_DERIVED` public-source provenance; immutable.
- TomTom is `REAL_LIVE` only when Phase 02 validation establishes that fact.
- Resource state and positions: `SIMULATED`.
- Coverage/planning: derived calculations retaining their input provenance.
- Candidate evaluation and repositioning never mutate operational state.
- Approval remains the sole resource-assignment boundary.
