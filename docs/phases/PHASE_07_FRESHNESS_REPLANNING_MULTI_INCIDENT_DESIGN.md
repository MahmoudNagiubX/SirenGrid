# SirenGrid Phase 07 - Freshness, Replanning, and Multi-Incident Design

## Boundary

Phase 07 adds deterministic freshness visibility, material-change detection,
safe replacement-plan evaluation, renewed approval, and multi-incident
contention handling. Existing Phase 00-06 operational truth remains
authoritative. AI claims never directly trigger authoritative changes.

## Active versus pending plans

`Incident.current_plan_id` remains the active approved plan after approval.
`pending_replan_plan_id` identifies the one current unapproved replacement
recommendation. The active plan remains operational until replacement approval;
hospital, movement, corridor, and driver-alert services read only the active
approved plan.

## Materiality

Policy version: `SIRENGRID_REPLAN_MATERIALITY_V1`.

- Confirmed active-route closure, route unreachability, required resource loss
  or conflict, material requirement change, selected-hospital invalidation,
  and required-resource contention are material.
- ETA deterioration is material at `>= 60` seconds or `>= 15%`.
- Route edge overlap `< 0.80` is material; `0.80` is not by overlap alone.
- Joint coverage is material for a newly undercovered previously covered zone
  or a joint population-coverage drop `>= 0.05`.
- Unknown state alone is never material.

## Trigger lifecycle

Qualifying events record a pending per-incident trigger. Events within the
five-second prototype debounce window coalesce by incident and active plan,
union reasons, and retain the latest coherent input references. There is no
background scheduler. An explicit flush/evaluation operation evaluates the
latest state. Input fingerprints make identical repeats idempotent.

## Replacement approval

Candidate evaluation is hypothetical. A new pending set increments incident
version once and records deterministic explanation facts. A replacement remains
`RECOMMENDED`/`AWAITING_APPROVAL` until operator approval. Approval atomically
switches the active plan pointer, clears the pending pointer, and applies only
allowed resource/route changes under existing locking and version checks.

Assigned/ reserved resources may be changed only during approval. Active
`EN_ROUTE` resources can keep the same physical resource and receive a route
starting from their current modeled coordinate with progress reset to zero.
`ON_SCENE` and `TRANSPORTING` resources are not generically rerouted or
substituted.

## Hospital and derived operational state

Confirmed hospital invalidation creates new options and requires operator
selection; it never redirects automatically. Existing pre-alert history is
immutable. Corridor and driver-alert state stay tied to the active approved
route and are superseded only after replacement approval.

## Multi-incident safety

Resource assignment remains serialized by SQLite `BEGIN IMMEDIATE`. Committed
resources remain unavailable to other incidents. No priority doctrine,
preemption, stealing, or global optimizer is introduced.
