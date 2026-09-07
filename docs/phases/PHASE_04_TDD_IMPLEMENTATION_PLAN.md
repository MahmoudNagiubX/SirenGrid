# SirenGrid Phase 04 — TDD Implementation Plan

**Status:** Owner-approved
**Design:** `PHASE_04_COVERAGE_AND_RESPONSE_PLANNING_DESIGN.md`
**Decision record:** PD-016

Every behavioral increment begins with a focused failing test, followed by the minimum implementation, focused test rerun, touched-scope Ruff, diff inspection, and one logical commit. Full regression checkpoints occur after risk-bearing integrations.

## Task 1 — WorldPop population artifact and provenance

**Task:** Reproducibly acquire the locked R2024B v1 source; build and validate the deterministic zone-population artifact.

**Expected files:** a focused preprocessing module/script, processed artifact/provenance, dependency declaration if needed, and focused tests.

**Acceptance tests:** exact overlap apportionment; non-negative values; NoData handling; deterministic output; conservation in the zone union; valid zone IDs; `REAL_DERIVED` output with WorldPop `REAL_PUBLIC` provenance; failed refresh retains a valid prior artifact.

**Out of scope:** runtime coverage/planning, synthetic fallback population, and mutable SQLite population truth.

## Task 2 — Coverage engine and snapshots

**Task:** Add cohort-aware graph coverage calculation over one captured graph/traffic state.

**Acceptance tests:** no-TomTom base routing works; 600-second inclusive boundary; separate resource cohorts; reachable/unreachable semantics; coverage ratio in `[0,1]`; zone-level explanations; graph immutability; source/reality/freshness propagation.

**Out of scope:** hypothetical dispatch, candidate planning, and API endpoints.

## Task 3 — Dispatch-impact simulation

**Task:** Compute baseline versus analytical post-dispatch coverage without changing resources.

**Acceptance tests:** removing a dispatched resource cannot mutate or magically improve baseline through state leakage; affected/newly undercovered zones are deterministic; simulated resources remain unchanged; captured traffic state is coherent throughout one evaluation.

**Checkpoint:** focused tests, full Phase 01–03 regression, Ruff.

## Task 4 — Response requirements and matrix v1

**Task:** Add typed requirements and deterministic resolution precedence.

**Acceptance tests:** explicit operator/source requirements override matrix; supported traffic-collision LOW/MEDIUM and HIGH/CRITICAL matrix results; unsupported/incomplete inputs fail visibly; unknown capabilities never satisfy a known requirement; matrix version is exposed.

**Out of scope:** AI inference, clinical guidance, or additional emergency patterns.

## Task 5 — Bounded candidate generation

**Task:** Filter, route-rank, and deterministically enumerate feasible combinations.

**Acceptance tests:** hard eligibility filtering; no unavailable/committed/incompatible/unroutable resource; capability filtering; no duplicate physical assignment; top-five ordering; 50-combination cap; deterministic enumeration.

## Task 6 — Candidate metrics, scoring, and ranking

**Task:** Derive validated `JOINT_ALL_REQUIRED_COHORTS_V1` coverage from retained per-cohort snapshots, evaluate candidate coverage, compute stored score terms, and select a deterministic recommendation.

**Acceptance tests:** joint all-cohort coverage uses one population denominator, finite bottleneck ETA, explicit failing cohorts, and null worst ETA for joint-unreachable zones; exact score reproduction; no ETA normalization clamp; all score weights/terms/policy version present; approved tie order; hospital term neutral; candidate evaluation has zero operational mutation.

## Task 7 — Hypothetical repositioning

**Task:** Generate and evaluate only the approved bounded reposition proposals.

**Acceptance tests:** both trigger conditions; zone/reserve ordering and caps; target-time rejection; usefulness condition; no-coverage-regression condition; proposed route/cost/result storage; zero live resource mutation.

## Task 8 — Persisted candidates, comparison, and selection

**Task:** Extend plan persistence/API minimally for alternatives and version-safe operator selection while retaining existing approval behavior.

**Acceptance tests:** one current recommendation; alternatives cannot be approved; selection atomically promotes one alternative, supersedes all others in its set, increments incident once, synchronizes plan/incident version, appends timeline audit, and performs no assignment; concurrent/stale selection fails without mutation; existing approval/current-plan guards still pass.

**Checkpoint:** focused planning/approval/resource tests, full regression, Ruff, compileall, Golden Flow.

## Task 9 — Final Phase 04 verification and review

Run full pytest, focused coverage/planning tests, Ruff, compileall, one-worker REST smoke, Golden Flow, approval/resource-locking regressions, population/provenance audit, coverage invariants, candidate determinism/score reproduction audits, secrets audit, and Phase 05 leakage audit. Inspect the complete diff before writing and committing `docs/PHASE_04_REVIEW.md`.
