# PHASE 07 REVIEW

Implemented:

Freshness:
Existing TomTom LIVE/FRESH/STALE semantics remain unchanged. Phase 07 preserves
explicit source, update, freshness, and reality metadata; inputs without an
approved TTL remain observable as UNKNOWN and do not trigger replanning by
themselves.

Materiality:
Implemented `SIRENGRID_REPLAN_MATERIALITY_V1` with inclusive 60-second / 15%
ETA deterioration thresholds, route-overlap `< 0.80` materiality, closure and
confirmed operational-failure triggers, and the approved joint-coverage loss
rules. Boundary tests cover the locked values and unknown-state behavior.

Replan triggers:
Added version-safe trigger recording for traffic, route, resource, requirement,
hospital, coverage, and contention facts. Trigger reasons are deterministic,
auditable, and coalesced per incident and active approved plan.

Replan evaluation:
Added an explicit evaluation/flush operation. It reuses the Phase 04 candidate,
routing, traffic, joint-coverage, and repositioning calculations without
mutating live operational state. Deterministic input fingerprints make exact
repeats idempotent.

Replacement plan/versioning:
Added one pending replacement pointer and replacement candidate persistence.
The active approved `current_plan_id` is never repointed at recommendation time;
only one pending replacement set is retained, with supersession and explanation
facts preserved in history.

Renewed approval:
Extended the existing transactional approval boundary for pending replacements.
Approval atomically switches active/pending pointers, increments the incident
version once, preserves old plan history, validates resources, and rejects stale
or unsafe replacement commands.

Coverage integration:
Replanning reuses `JOINT_ALL_REQUIRED_COHORTS_V1`, per-cohort snapshots, Phase
04 dispatch-impact simulation, and hypothetical repositioning. Same-incident
precommitted responders are retained only for the relevant replan evaluation;
the default Phase 04 eligibility behavior remains strict.

Hospital integration:
Confirmed selected-hospital NOT_ACCEPTING or unreachable events invalidate the
destination, preserve prior pre-alert history, refresh options, and require a
new explicit destination decision. Unknown state does not trigger invalidation.

Corridor integration:
Corridor state remains tied to the active approved route. Replacement approval
supersedes old route-derived state and derives replacement state only after the
new route is approved.

Driver-alert integration:
Driver-alert state remains tied to the active approved route and is replaced or
expired only after replacement approval. Pending routes do not affect live
alerts.

Multi-incident:
Committed resources remain committed and are excluded from other incidents'
candidate sets. No resource preemption, priority doctrine, stealing, or global
optimizer was introduced.

Concurrency:
SQLite `BEGIN IMMEDIATE` serializes trigger, evaluation, approval, and resource
mutations. Identical concurrent evaluations produce one replacement set; stale
competing state returns conflict.

API:
Added REST trigger, evaluation/flush, and pending-replan read contracts under
`/api/v1`. Existing planning and approval contracts remain authoritative.

WebSocket/timeline:
Replan trigger/generation, invalidation, route-derived state, and existing
resource/approval actions remain append-only/auditable and publish operations
updates through the existing process-local stream.

Files changed:

Phase 07 implementation and tests include `backend/app/materiality.py`,
`backend/app/replanning.py`, the existing planning/candidate/coverage/resource/
hospital/incident/API/model/config/db modules, and
`backend/tests/test_phase07_materiality.py`,
`backend/tests/test_phase07_replan_state.py`, and
`backend/tests/test_phase07_integrated_smoke.py`. Authoritative updates are in
`docs/DECISIONS.md` and the Phase 07 design/TDD documents.

Tests:

Focused Phase 07: 29 passed.
Full pytest: 398 passed, 8 warnings.
Golden Flow: PASS; explicit Golden Flow and WebSocket regression: 10 passed.
No-AI Golden Flow: PASS; Phase 06 integrated/no-AI smoke: 2 passed.
Integrated smoke: PASS; one-worker real OSM/WorldPop replan and multi-incident
smoke passed. TomTom was unavailable in this bounded test and the approved OSM
fallback was used; no live traffic was claimed.
Ruff: PASS (`python -m ruff check backend`).
Compileall: PASS (`python -m compileall -q backend`).
Diff check: PASS (`git diff --check 1c670ef..HEAD`).

Freshness audit:
TomTom thresholds remain the Phase 02 locked 60/120-second policy. No new TTL
was invented for resources, hospitals, evidence, corridor state, or alerts.

Materiality audit:
Absolute, percentage, route-overlap, closure, coverage, and unknown boundaries
are covered by focused tests and persisted explanation facts.

Resource-integrity audit:
Replan evaluation is hypothetical. It does not mutate resource assignment,
status, coordinates, route progress, or approved route state. Replacement
approval alone performs the explicitly permitted transactional changes.

Plan-history audit:
The active approved plan remains operational while a replacement is pending;
the pending pointer references only the current replacement recommendation.
Replacement approval clears it and preserves superseded plan history.

Concurrency audit:
Concurrent identical flushes yielded one `REPLACEMENT_RECOMMENDED` result and
one idempotent result, one pending set, and one incident-version increment.

Multi-incident audit:
The integrated smoke confirmed that a resource committed to Incident A is not
selected for Incident B. Insufficient resources fail visibly; no automatic
preemption exists.

Reality/provenance audit:
WorldPop/OSM/TomTom/resource and simulated operational labels remain distinct.
Replan outputs retain source and snapshot references; simulated operational
state is not represented as live provider truth.

Replan-storm audit:
Five-second per-incident trigger coalescing, reason union, latest references,
and deterministic exact-repeat idempotency are tested. There is no scheduler,
polling loop, or background worker.

Secrets audit:
No credential-shaped literals were found in tracked files. Provider secrets
remain environment/config driven and were not printed or committed.

Phase 08 leakage audit:
No Phase 08 functionality, distributed infrastructure, social-media behavior,
or global optimization was introduced.

Repo reconnaissance:

The Phase 00–06 authoritative documents, current routing/traffic, planning,
coverage, resource, hospital, corridor, driver-alert, evidence, timeline, and
WebSocket implementations were reviewed. Existing SQLite locking, Phase 04
candidate evaluation, Phase 05 hospital invalidation, Phase 03 route-progress,
and Phase 01 approval/version safeguards were reused.

Reuse:

Replanning adapts the existing Phase 04 planning/coverage stack, Phase 05
hospital and route-derived-state contracts, Phase 03 modeled route position,
and the established REST/WebSocket/timeline patterns. No new external service
or donor behavior was added.

Not implemented:

No Phase 08 functionality, automatic resource preemption, global optimizer,
background scheduler, silent hospital redirect, automatic route switch, or
unapproved operational mutation was implemented.

Owner decisions:

PD-039 through PD-047 are recorded in `docs/DECISIONS.md` and reflected in the
implementation and tests.

Deviations:

The integrated smoke intentionally uses one real WorldPop-derived zone to keep
the bounded test practical, while production evaluation loads the validated
artifact. The smoke patches TomTom unavailable to exercise the approved OSM
fallback and makes no live-provider claim. Trigger creation and explicit flush
are the operational event boundary, as approved by PD-042; no background
replan loop was added.

Blocking issues:

None.

Verdict: PASS
