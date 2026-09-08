# PHASE 08 REVIEW

## Verdict

PASS

## Implemented

### Baseline engine

Added `backend/app/benchmark_baseline.py` with a safe, intentionally simple
greedy baseline. It applies the same routeable eligibility constraints as the
production path, processes the most constrained cohort first, removes selected
physical resources from the remaining pool, and reports visible
`INSUFFICIENT_RESOURCES` outcomes. Baseline coverage is measurement-only and
baseline hospital selection is nearest feasible ETA/distance/ID.

### Scenario runner and dataset

Added typed deterministic manifests and `Phase08ScenarioRunner` in
`backend/app/benchmark_scenarios.py` and `backend/app/benchmark_runner.py`.
The committed manifest contains exactly 36 scenarios: T01-T15 plus 21
cross-cutting cases. The runner uses production routing, planning, coverage,
repositioning, hospital, and materiality functions with the same fixed inputs
for both engines. No provider refresh occurs during benchmark runs.

### Metrics and artifacts

Added transparent raw result serialization, functional aggregation, timing
subset collection, expected-outcome validation, and metadata in
`backend/app/benchmark_metrics.py`, `backend/app/benchmark_validation.py`, and
`backend/app/benchmark_cli.py`. The generated artifacts are committed under
`data/evaluation/phase08/` and documented in
`docs/PHASE_08_BENCHMARK_REPORT.md`.

### T01-T15

Added executable Master Plan validation, with all 15 cases passing and mapped
to scenario IDs, expected results, actual results, and evidence in
`data/evaluation/phase08/t01_t15_validation.json`.

### Demo controls

Added minimal configuration-gated local simulation controls in
`backend/app/simulation_api.py`: reset, load scenario, trigger explicit events,
and status under `/api/v1/simulation`. They are disabled by default, labeled
`SIMULATED` and `DEMO/DEVELOPMENT ONLY`, and use no scheduler or background
worker.

### Hardening fix

The benchmark replay exposed that a travel-tree cache keyed only by traffic
identity fields could reuse a tree when a fixture reused its snapshot ID but
changed overlay contents. `backend/app/coverage.py` now hashes the complete
traffic snapshot JSON for cache identity. A focused regression proves distinct
overlay contents cause distinct computation and ETAs.

## Files changed

Implementation:

- `backend/app/benchmark_baseline.py`
- `backend/app/benchmark_scenarios.py`
- `backend/app/benchmark_runner.py`
- `backend/app/benchmark_metrics.py`
- `backend/app/benchmark_validation.py`
- `backend/app/benchmark_cli.py`
- `backend/app/simulation_api.py`
- `backend/app/config.py`
- `backend/app/main.py`
- `backend/app/coverage.py`
- `backend/app/routing.py`
- `backend/app/traffic/matching.py`
- `backend/app/candidate_generation.py`
- `backend/app/planning.py`
- `backend/app/repositioning.py`

Tests and fixtures:

- `backend/tests/test_phase08_baseline.py`
- `backend/tests/test_phase08_metrics.py`
- `backend/tests/test_phase08_scenarios.py`
- `backend/tests/test_phase08_simulation_api.py`
- `backend/tests/test_phase08_validation.py`
- `data/evaluation/phase08/scenarios.json`
- generated JSON artifacts under `data/evaluation/phase08/`

Documentation:

- `docs/DECISIONS.md` (PD-049 through PD-061)
- `docs/phases/PHASE_08_BENCHMARK_AND_HARDENING_DESIGN.md`
- `docs/phases/PHASE_08_TDD_IMPLEMENTATION_PLAN.md`
- `docs/PHASE_08_BENCHMARK_REPORT.md`
- `docs/PHASE_08_REVIEW.md`

## Verification

Focused Phase 08: 19 passed.

Full pytest: 431 passed, 8 warnings.

Golden Flow: PASS. Existing Phase 01-07 Golden Flow, approval/version,
hospital/corridor/driver-alert, evidence/fusion, stale-generation, and
replanning regressions remain green.

No-AI Golden Flow: PASS through the existing manual fallback path.

T01-T15 validation: 15/15 PASS.

36-scenario benchmark: 36/36 expected outcome checks PASS for both engines.

Replay determinism: PASS; decision/model output equality holds after excluding
wall-clock timing fields.

Integrated benchmark smoke: PASS; real OSM graph, WorldPop-derived zones,
OSM hospital data, fixed traffic replay, production planning, and explicit
simulation-control tests were exercised. No live provider result was fabricated.

Performance subset: 10 scenarios, one excluded warm-up, 30 retained samples
per engine. Results are in the benchmark report and raw performance artifact.

Ruff: PASS (`python -m ruff check .`).

Compileall: PASS (`python -m compileall -q backend`).

Diff check: PASS (`git diff --check`).

## Audits

### Benchmark fairness audit

PASS. Baseline and SirenGrid share scenario facts, resource state, graph,
traffic fixture/fallback state, hospitals, simulated hospital state, coverage
assets, event order, and seeds. Baseline is constrained but not intentionally
broken and does not receive a coverage-aware selection advantage.

### Baseline safety audit

PASS. Unavailable, committed, incompatible, unroutable, and no-path resources
are not selected. Multi-resource selection is deterministic with no backtracking
or preemption.

### Raw-vs-aggregate audit

PASS. Aggregate outputs are generated from raw scenario results; expected-outcome
checks cover all 36 scenarios. Missing measurements are represented by omitted
statistics rather than fabricated zeros.

### Reality/provenance audit

PASS. Scenario operational state is `SIMULATED`/`SYNTHETIC`; WorldPop zones are
`REAL_DERIVED`; OSM assets retain public/derived provenance; fixed traffic is a
replay fixture and not current `REAL_LIVE` traffic.

### Failure/recovery audit

PASS. The dataset and existing regressions cover no-path, outside-graph,
insufficient-resource, stale/fallback traffic, invalid hospital state,
stale-version, malformed/failed optional-provider, idempotent, and review
outcomes. Expected failures remain visible.

### Concurrency audit

PASS. Existing SQLite stale-generation, approval, multi-incident, and Phase 07
concurrency tests remain green. Scenario runs use isolated immutable state and
do not write operational truth.

### Simulation-control audit

PASS. `/api/v1/simulation` is disabled by default, explicitly gated for local
demo/test use, labeled simulated, and has no scheduler or distributed state.

### Privacy audit

PASS. Benchmark fixtures contain synthetic operational facts only. No raw
emergency media or private report content was added.

### Secrets audit

PASS. No credentials or API keys are included in fixtures or artifacts.

### Phase 09 leakage audit

PASS. No Phase 09 feature, global optimizer, analytics platform, frontend,
real-provider requirement, or unrelated product behavior was introduced.

## Repo reconnaissance and reuse

The authoritative Phase 00-07 plans/reviews, current test suite, routing and
traffic fallback, Phase 04 candidate/coverage/repositioning, Phase 05 hospital
logic, Phase 06 fallback, Phase 07 materiality/replanning, simulation gateways,
timeline/WebSocket, and SQLite locking patterns were inspected.

The Egypt Smart City Digital Twin reference informed deterministic scenario and
asset-handling patterns. Production SirenGrid modules were reused directly.
Unsafe unavailable-resource fallback behavior from ResQPath was rejected.
No external code was copied into the production decision path.

## Measured findings

The 36-case benchmark generated 31 plans and 5 visible insufficient-resource
outcomes in each engine. Median modeled incident ETA was 179.557 seconds for
both. Mean post-dispatch joint coverage was 0.918452 for the baseline and
0.920198 for SirenGrid. These are fixture-set measurements, not universal
claims. The benchmark report contains the full dimensions and trade-offs.

## Limitations / not measured

ASR WER/CER is `NOT_AVAILABLE` without configured credentials. Structured
extraction is `NOT_SELECTED` and default-disabled; vision is default-off. The
fixed traffic benchmark does not measure live TomTom variability. Wall-clock
timings are machine-specific. The scenario runner is a deterministic benchmark
orchestrator, not a second database-backed operational workflow. No composite
benchmark score, real hospital integration, signal preemption, frontend, or
Phase 09 behavior was implemented.

## Owner decisions

PD-049 through PD-061 are recorded in `docs/DECISIONS.md` and reflected in the
benchmark policy, runner, artifacts, tests, and report. The final hardening fix
restores approved deterministic replay behavior and does not change product
policy.

## Deviations

None from the approved Phase 08 policy. The report explicitly distinguishes
functional/model measurements from wall-clock measurements and unavailable AI
metrics.

## Blocking issues

None.
