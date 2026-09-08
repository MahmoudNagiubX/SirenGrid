# SirenGrid Phase 08 - TDD Implementation Plan

1. Add the approved benchmark policy constants, typed baseline result
   contracts, and failing tests for eligibility, greedy constrained-cohort
   selection, hospital handling, and safety failures.
2. Implement the baseline engine using existing routing and hospital/coverage
   helpers, then verify it does not use coverage-aware selection,
   repositioning, or network optimization.
3. Add typed scenario manifests, deterministic isolated state construction,
   production-module orchestration, and replay tests.
4. Add the 36 committed scenarios, including executable T01-T15 cases and
   the approved cross-cutting matrix.
5. Add raw result contracts, functional/performance timing collection,
   transparent aggregation, and machine-readable artifact generation.
6. Add executable T01-T15 mapping and recovery/failure coverage; harden only
   concrete approved-contract defects found by tests.
7. Add configuration-gated local simulation reset/load/event/status endpoints
   with disabled/enabled and isolation tests.
8. Run the complete benchmark, replay it, audit fairness/provenance/privacy/
   concurrency/scope, and publish the benchmark report and Phase 08 review.

Each behavioral increment follows RED -> GREEN -> focused verification ->
Ruff/compileall where relevant -> reviewed commit. No Phase 09 functionality
is included.
