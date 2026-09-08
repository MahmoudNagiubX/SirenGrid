# Phase 09 Social Media Intelligence — Design and TDD Plan

## Boundary

Phase 09 consumes bounded public social content as unverified external
intelligence for the control room. It reuses the existing `Report`, evidence
claims, fusion, timeline, and WebSocket invalidation contracts. A social signal
cannot activate dispatch, assign resources, approve plans, select hospitals,
control signals, or trigger driver alerts by itself.

## Providers

- `BlueskyPublicProvider`: unauthenticated public `GET` search with bounded
  timeout/results and strict response validation.
- `DeterministicSyntheticSocialProvider`: explicit `SYNTHETIC/DEMO` fixtures
  for offline demos and tests.
- X is not implemented in the MVP; it remains an optional disabled adapter.

The provider boundary returns normalized posts plus provider status and does
not silently relabel synthetic content as Bluesky content.

## Normalization and persistence

Normalized social signals are persisted as standalone Phase 06-compatible
`Report` rows (`incident_id = NULL`) with `source_type = social_media`,
minimal provider provenance, safe bounded metadata, location clues, and
an unverified social-signal review state (`POTENTIALLY_RELEVANT`,
`INSUFFICIENT_CONTEXT`, `IRRELEVANT`, or an operator review state). Provider
post IDs make refresh idempotent. No media download or profile-history storage
occurs.

Deterministic filtering emits inspectable states such as `POTENTIALLY_RELEVANT`,
`INSUFFICIENT_CONTEXT`, and `IRRELEVANT`. Explicit provider coordinates are
preserved only when marked trusted; vague location text remains unresolved.

Conservative text rules may create immutable unverified claims only for
explicitly supported facts. Claims never update authoritative Incident fields
without the existing operator confirmation endpoint.

## Association and operator actions

Refresh evaluates each signal against existing incidents using the Phase 06
deterministic fusion inputs and stores the explanation. It never attaches a
signal automatically. An explicit operator association is transactional,
version-safe, append-only, and does not mutate operational state or project
claims. `POSSIBLE_NEW_INCIDENT` remains a review state; manual intake creates a
new incident.

Dismissal is a version-safe review-state update and cannot mutate an incident.

## REST and realtime contracts

The Phase 09 router provides bounded refresh, signal list/detail, dismiss,
association, and possible-new review actions under `/api/v1/social`. REST is
canonical. Timeline events and existing `operations` WebSocket invalidation
events are emitted only for material operator actions.

## TDD sequence

1. Add strict provider/post/filter/response schemas and configuration tests.
2. Add synthetic provider and normalization/idempotency tests.
3. Add Bluesky response/error/timeout validation tests with a fake HTTP client.
4. Add Report-backed persistence and list/detail tests.
5. Add deterministic association explanation and explicit operator action tests.
6. Add dismissal/possible-new/no-auto-dispatch/privacy regression tests.
7. Run Phase 00–08 regression, smoke, Ruff, compileall, diff check, and audit.
