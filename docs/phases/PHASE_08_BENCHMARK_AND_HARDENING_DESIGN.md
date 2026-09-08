# SirenGrid Phase 08 - Benchmark and Hardening Design

## Boundary

Phase 08 measures the existing Phase 00-07 operational core and fixes only
concrete defects that violate already-approved behavior. It adds a simple
baseline, a deterministic scenario runner, reproducible benchmark artifacts,
T01-T15 validation, recovery tests, and gated local simulation controls. It
does not add operational product policy or Phase 09 behavior.

## Fair comparison

The baseline and production SirenGrid path receive the same scenario facts,
resource state, graph, fixed traffic fixture/fallback, hospital registry and
simulated hospital state, coverage assets, event order, closures, and seed.
The baseline greedily chooses the most-constrained eligible cohorts by route
ETA, distance, and resource ID. Coverage is measured after selection using
the existing joint Phase 04 engine but never feeds baseline selection.

Hospital comparison uses the existing truthful hard filters and UNKNOWN
semantics, then minimum route ETA/distance/ID. No Phase 04 score is reused as
a neutral benchmark score.

## Scenario and runner model

The committed fixture contains 36 scenarios: dedicated executable T01-T15
cases plus 21 non-filler cross-cutting cases. Each scenario has a stable ID,
seed, provenance, initial state, event sequence, expected outcomes, and asset
references. Each run starts from an isolated deterministic state. The runner
orchestrates production routing, coverage, candidate, hospital, and replan
modules; it does not clone their decision logic.

The official benchmark uses fixed traffic fixtures and no provider refresh.
Wall-clock performance is measured only for ten representative scenarios,
with one excluded warm-up and three isolated repetitions per engine.

## Outputs

Machine-readable outputs retain the policy version, dataset version, commit,
asset hashes, scenario seed, traffic fixture reference, reality/provenance,
raw per-engine results, aggregate results, performance samples, and the
T01-T15 mapping. Reports separate measured findings, limitations, and
unavailable metrics. No composite benchmark score or unsupported improvement
claim is generated.

## Simulation controls

Local demo controls provide reset, scenario load, explicit event triggering,
and status. They are configuration-gated and disabled by default. There is no
background scheduler; scheduled events are advanced explicitly in manifest
order. Responses and mutations are labeled SIMULATED.

## Safety and hardening

Expected failures remain visible. The runner verifies no resource double
assignment, no unavailable-resource fallback, no live-state mutation during
hypothetical comparison, deterministic replay, provenance preservation, and
scenario isolation. Any discovered fix must preserve the approved Phase
00-07 contracts.
