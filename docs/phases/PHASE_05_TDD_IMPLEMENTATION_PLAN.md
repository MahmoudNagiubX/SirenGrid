# Phase 05 TDD Implementation Plan

## Slice 1 — Hospital registry and state

Add failing tests for the 27 OSM hospital records, stable source identity,
unknown static capacity/capabilities, deterministic simulated defaults and
fixtures, and provenance. Implement a file-backed static registry plus a
separate simulated state boundary.

## Slice 2 — Hospital routing, filtering, and ranking

Add tests for explicit transport gating, unknown capability handling, hard
filters, unreachable routes, the 900-second ETA normalizer, approved score
terms/weights, uncertainty penalties, tie-breaking, and deterministic output.
Expose hospital options and detail data through REST.

## Slice 3 — Destination selection and pre-alert

Add tests for approved-plan ownership, version conflicts, one current
destination, replacement before pre-alert, replacement rejection after
REQUESTED, no resource mutation, known-facts-only payloads, simulated gateway
transitions, failure injection, and idempotency. Implement transactional
selection, timeline/WebSocket updates, and pre-alert state endpoints.

## Slice 4 — Corridor and signal priority

Add tests for approved-route-only extraction, 50 m matching, deterministic
projection/order/deduplication, empty/no-signal behavior, 30-second request
timing, simulated state transitions, and unchanged route ETA. Implement the
corridor state/action contract and `TrafficSignalGateway`.

## Slice 5 — Driver alert and operational view

Add tests for explicit route progress, 500 m look-ahead, 30 m buffer, 120-second
expiry, passed-section removal, route-end expiry, privacy, simulated delivery,
and aggregate state. Implement `DriverAlertGateway`, alert state/refresh, and
the aggregate incident operational endpoint.

## Slice 6 — Integrated verification

Run the real one-worker path: manual incident → Phase 04 candidate generation
→ plan approval → explicit transport fact → hospital options → destination
selection → simulated pre-alert → corridor → simulated priority → resource
movement → driver alert → aggregate state. Then run all regression, lint,
compile, diff, provenance, concurrency, secrets, privacy, and Phase 06 leakage
audits before writing `docs/PHASE_05_REVIEW.md`.
