# SirenGrid Phase 07 - TDD Implementation Plan

1. Add Phase 07 constants, pending-trigger/replan contracts, and pure
   materiality/fingerprint tests.
2. Add pending-replan persistence and migration-safe incident pointer fields.
3. Add deterministic trigger recording, five-second coalescing, and explicit
   evaluation/flush API.
4. Reuse existing routing, joint coverage, candidate, and hospital services to
   evaluate replacement plans without mutating operational state.
5. Persist replacement candidate sets, explanations, supersession, and pending
   plan identity with exact version increments.
6. Extend approval transaction for pending replacements, including reserved /
   assigned resource replacement and active-plan pointer switching.
7. Add same-resource `EN_ROUTE` rerouting from current modeled coordinate;
   reject generic `ON_SCENE`/`TRANSPORTING` reroute.
8. Integrate hospital invalidation, corridor/driver-alert route-version
   behavior, timeline, and WebSocket events.
9. Add multi-incident contention and concurrent evaluation/approval tests.
10. Run full regression, integrated smoke, audits, and publish
    `docs/PHASE_07_REVIEW.md`.

Each increment follows RED -> GREEN -> focused verification -> Ruff/
compileall where relevant -> reviewed commit. No Phase 08 functionality is
included.
