# PHASE 04 REVIEW

Verdict: **PASS**

Phase 04 was reviewed from the Phase 03 reviewed baseline `b414f36` through
the Task 8 baseline `9ea1096`, including the final bounded integration fix
and this review. The review confirms that Phase 04 remains within coverage
and response-planning scope and does not begin Phase 05.

## Implemented

### Files changed

- `backend/app/candidate_evaluation.py`
- `backend/app/candidate_generation.py`
- `backend/app/candidate_persistence.py`
- `backend/app/config.py`
- `backend/app/coverage.py`
- `backend/app/planning.py`
- `backend/app/repositioning.py`
- `backend/app/response_requirements.py`
- `backend/app/routing.py`
- `backend/app/schemas.py`
- `backend/scripts/build_worldpop_zone_population.py`
- Phase 04 coverage, planning, persistence, selection, repositioning,
  response-requirement, and WorldPop tests under `backend/tests/`
- `data/processed/nasr_city/nasr_city_zone_population_worldpop_2025.geojson`
- `docs/DECISIONS.md`
- `docs/phases/PHASE_04_COVERAGE_AND_RESPONSE_PLANNING_DESIGN.md`
- `docs/phases/PHASE_04_TDD_IMPLEMENTATION_PLAN.md`
- `docs/PHASE_04_REVIEW.md`

### WorldPop preprocessing

The reproducible preprocessing tool performs exact area-weighted raster-cell
to zone allocation in equal-area CRS `EPSG:6933`. NoData cells are retained
as unknown and are not converted to population zero. Publication is staged
and atomic so failed refreshes preserve the prior validated artifact.

### Population artifact/provenance

- Modeled zones: **416**, exactly `NSR-GRID-001` through `NSR-GRID-416`.
- Total modeled population: **743827.6942895878**.
- Processed artifact reality: `REAL_DERIVED`.
- Underlying source reality: `REAL_PUBLIC`.
- Source: WorldPop Egypt constrained population counts, geodata ID `56914`.
- Release/version: `R2024B` / `v1`.
- DOI: `10.5258/SOTON/WP00803`.
- Source reference: `https://hub.worldpop.org/geodata/summary?id=56914`.
- NoData cells intersecting the modeled union: **945**.
- Conservation error: **-5.82e-10**.
- Artifact SHA-256:
  `d7f9a46642608a1cbae8796ff90b95183e214f59c2a6162215d8e3f6e8c471d9`.

No synthetic, equal-per-zone, random, donor-zero, or other fabricated
population fallback is used.

### Coverage engine

Coverage uses graph travel time for each eligible resource/cohort and the
locked boundary `zone_eta <= 600` seconds. Available, unassigned,
capability-compatible resources are used; unavailable, out-of-service,
committed, incompatible, and unroutable resources are excluded. Unreachable
zones remain in the denominator with null ETA, explicit IDs, and no fabricated
penalty ETA. Population-weighted coverage is bounded to `[0, 1]`.

### Per-cohort and joint coverage

Per-cohort snapshots are retained independently. The plan-level policy is
`JOINT_ALL_REQUIRED_COHORTS_V1`: a zone is jointly covered only when every
required cohort covers it; finite joint ETA is the maximum cohort ETA; any
unreachable required cohort makes joint ETA null and records the failing
cohort IDs. Population is counted once using the same denominator for
baseline, post-dispatch, and hypothetical reposition results.

### Dispatch-impact simulation

Baseline and post-dispatch coverage are calculated from captured resource
snapshots. Candidate evaluation removes selected resources only in
hypothetical copies. Live resource status, assignment, coordinates, incident
state, and approved routes are not mutated.

### Response requirements and Prototype Matrix

The versioned prototype matrix is limited to the approved traffic-collision
MVP patterns:

- LOW/MEDIUM: one `AMBULANCE`.
- HIGH/CRITICAL: two `AMBULANCE` and one `FIRE_RESCUE`.

Operator-confirmed and explicit source requirements take precedence. Unsupported
or insufficient cases fail visibly and require confirmation. No LLM changes or
selects matrix rules.

### Candidate generation

Hard constraints are applied first. Eligible responders are ranked per cohort
by captured incident ETA, route distance, and resource ID; the top five per
cohort are retained and enumeration is capped at 50 feasible combinations.
Physical resources cannot be assigned twice. Ordering is deterministic.

### Candidate metrics

Candidates persist incident ETA, arrival spread, per-cohort baseline and
post-dispatch snapshots, joint snapshots, coverage delta, affected and newly
undercovered zones, reserve state, routes, resource IDs, provenance, and
optional hypothetical reposition details.

### Scoring/ranking

The stored policy is lower-is-better `SIRENGRID_PROTOTYPE_PLAN_SCORE_V1`:

- ETA weight `0.35`, normalized as `max_incident_eta / 600` without clamping.
- Coverage weight `0.40`, penalty `1 - post_dispatch_joint_coverage`.
- Reserve weight `0.20`, penalty `1` only when any required cohort has no
  remaining eligible reserve.
- Reposition weight `0.05`, proposal ETA divided by `600`, otherwise `0`.
- Hospital weight `0.00`, neutral in Phase 04.

Raw terms, normalized terms, weights, weighted terms, policy version, and
final score are persisted. Ties use lower score, lower raw maximum ETA,
higher joint post-dispatch coverage, no reposition, and lexicographically
sorted resource IDs.

### Repositioning simulation

Repositioning is hypothetical only. It triggers only for a newly undercovered
zone or a population-coverage drop of at least `0.05`. It considers at most
three target zones, the approved top three eligible reserve resources per
failing cohort, and immediately adjacent operational-zone centroids. Travel
to the staging centroid must be at most 600 seconds. Staging points are
explicitly `SIMULATED` strategic planning points derived from the real zone
grid, not emergency stations. Accepted proposals recompute per-cohort and
joint coverage and must improve both an approved joint outcome and the target
zone's failing-service condition without reducing joint coverage.

### Candidate persistence

Each candidate set persists exactly one current `RECOMMENDED` plan and zero or
more `ALTERNATIVE` plans. `incident.current_plan_id` references the current
recommendation. Stored plan data includes assignments, routes, coverage,
joint/per-cohort metrics, reserve state, reposition facts, scores,
requirements metadata, prototype labels, and provenance.

### Alternative selection

Alternative selection uses the existing SQLite `BEGIN IMMEDIATE` protection,
validates incident/candidate-set/current-plan/status/version guards, promotes
one alternative, supersedes the old recommendation and remaining alternatives,
increments the incident version once, rebinds the selected plan, appends an
audit timeline event, and mutates no resources. Competing selections have one
winner.

### Approval compatibility

The existing approval boundary remains authoritative. Approval requires the
current plan, `RECOMMENDED` status, matching incident and plan versions,
expected versions, available non-conflicting resources, and the transactional
resource lock. Old recommendations cannot be approved after alternative
selection; the selected recommendation can be approved with its resulting
versions.

### API comparison contract

The existing list/detail contracts expose persisted comparison data. A bounded
Phase 04 endpoint is also available at:

`POST /api/v1/incidents/{incident_id}/plans/generate-candidates`

It resolves the approved requirements, captures one routing/traffic state,
generates and ranks candidates, persists the comparison set, and returns the
recommendation plus alternatives. The Phase 01 single-plan endpoint remains
unchanged for backward compatibility.

## Tests

- Focused Phase 04 population/coverage/requirements/candidate/reposition/
  persistence/selection suite: **40 passed**.
- Approval/version/resource/concurrency regression suite:
  **22 passed**.
- Candidate generation/evaluation determinism: **3 passed on each of three
  repeated runs** (9 executions total).
- Golden Flow and Phase 03 live-state regression: **3 passed**.
- Full pytest: **303 passed**, 8 non-failing dependency deprecation warnings.
- Ruff: **PASS** (`ruff check backend`).
- Compileall: **PASS** (`python -m compileall -q backend`).
- Diff check: **PASS** (`git diff --check`).

### Live smoke

**PASS.** A one-worker Uvicorn process used a temporary SQLite database,
seeded scenario resources, and the real Nasr City graph and WorldPop artifact.
The flow was:

manual incident → Phase 04 candidate generation → recommendation/alternative
inspection → joint-coverage contract inspection → approval → resource
assignment.

The smoke produced one `RECOMMENDED` and two `ALTERNATIVE` candidates, then
approved the recommendation and assigned one resource. TomTom was explicitly
disabled for this smoke; no live traffic value was claimed.

## Repo reconnaissance

### Relevant references

- `MahmoudNagiubX/Egypt-Smart-City-Digital-Twin`, pinned commit
  `93ca9e90e2fc52c914dd5ccbe42bdc84ce745d3d`.
- `ashwinnm13/ResQPath` for resource-selection concepts.
- `joshua-ong/AmbulanceDeployment` for coverage/deployment concepts.
- Existing SirenGrid Phase 01–03 routing, resource, timeline, approval, and
  provenance implementation.

### What was reused

The existing Nasr City boundary/grid provenance, OSM-derived graph loader,
route snapping/geometry, resource abstractions, SQLite transaction strategy,
plan/approval contracts, and backend reality-label conventions were reused.

### What was adapted

WorldPop processing was implemented as reproducible file-backed preprocessing;
coverage and candidate planning were added as deterministic simulations;
candidate persistence was extended to one recommendation plus alternatives;
the API gained the bounded Phase 04 generation path needed to exercise the
persisted candidate-set contract.

### What was rejected

The donor's zero/insufficiently-provenanced population, unsafe unavailable-
resource fallbacks, zeroed route failures, straight-line movement, weather
behavior, OpenRouteService, Redis/queues/distributed locks, full GIS matching,
hospital ranking, corridor control, AI intake, and later-phase behavior were
not reused.

## Audit results

### Population audit

PASS. The exact approved WorldPop release and DOI are recorded; the artifact
has the expected 416 zones, non-negative deterministic values, projected
area allocation, explicit NoData count, conservation check, source hash, and
`REAL_DERIVED`/`REAL_PUBLIC` labels.

### Coverage invariants

PASS. Tests cover below/equal/above 600-second behavior, graph ETA, eligibility
and capability filtering, unreachable-zone retention, null worst ETA, finite
worst ETA, IDs/counts, and `[0, 1]` coverage bounds.

### Joint coverage audit

PASS. Tests cover all-required-cohort semantics, bottleneck ETA, explicit
failing cohorts, null joint ETA for unreachable zones, one population
denominator, and single-cohort equivalence.

### Candidate determinism audit

PASS. Top-five/max-50 bounds, hard constraints, no duplicate assignment, route
failure exclusion, stable tie ordering, and repeated identical ordering pass.

### Scoring transparency audit

PASS. Stored scores reproduce from the approved raw terms, normalized terms,
weights, weighted terms, policy version, and lower-is-better tie order. The
hospital term is neutral and no Phase 05 hospital behavior exists.

### Repositioning immutability audit

PASS. Tests verify adjacent-centroid-only staging, failing-cohort eligibility,
600-second staging travel limit, target improvement, joint recomputation, and
no live resource mutation or actual reposition execution.

### Selection concurrency audit

PASS. SQLite immediate-write serialization yields one competing-selection
winner, one current recommendation, superseded losers, one incident-version
increment, and no resource mutation.

### Approval/version audit

PASS. Existing current-plan, status, incident-version, plan-version,
availability, assignment, repeat-approval, and transactional safeguards remain
green, including approval after alternative selection.

### Reality/provenance audit

PASS. WorldPop is `REAL_PUBLIC` at source and `REAL_DERIVED` after processing;
the OSM graph is real-derived public-source data; responders remain
`SIMULATED`; TomTom is only `REAL_LIVE` after validated retrieval; coverage
and planning are derived outputs; staging points are simulated prototype
planning locations.

### Secrets audit

PASS. No credentials or secret values were added, printed, or committed.
TomTom access remains environment-configured. The live smoke used an empty
TomTom key and made no live-data claim.

### Phase 05 leakage audit

PASS. No hospital ranking/destination approval/pre-alert, corridor or signal
priority, driver alert, actual reposition execution, AI intake, ASR/image
flow, replanning, frontend, social-media behavior, or later-phase subsystem
was added. The neutral hospital score field is present only because the
approved Phase 04 score contract requires a zero-valued term.

## Not implemented

Phase 05 hospital behavior, corridor/signal priority, driver alerts, actual
reposition execution, frontend implementation, AI/ASR/image intake, report
fusion, dynamic replanning, multi-incident optimization, benchmark/scenario
engine, and social-media behavior remain out of scope.

## Owner decisions made

The implementation follows the approved Phase 04 decisions recorded in
`docs/DECISIONS.md`, including PD-016 and PD-017: exact WorldPop release and
allocation, 600-second prototype target, cohort and unreachable semantics,
prototype response matrix, top-five/max-50 candidate bounds, score policy,
adjacent-zone simulated staging, joint required-cohort aggregation, and
one-recommendation/alternative persistence with transactional selection.

## Deviations

During the fresh Task 9 review, persistence was found to be internally
implemented but not reachable through a Phase 04 candidate-generation API.
The bounded fix added the endpoint above, persisted requirement metadata, and
added an integration regression. It does not change the approved scoring,
coverage, resource, selection, or approval policy, and it preserves the
Phase 01 single-plan endpoint.

## Blocking issues

None.

**Verdict: PASS**
