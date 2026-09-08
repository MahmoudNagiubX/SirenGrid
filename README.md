# SirenGrid 🚨

**AI-powered emergency response coordination for Cairo — built for IMPACT ECU 2026.**

SirenGrid helps an emergency control-room dispatcher turn a real-world incident report into a coordinated response across responders, roads, emergency coverage, and receiving hospitals.

## Core Flow

**Report → Understand → Activate → Coordinate → Approve → Route → Preserve Coverage → Prepare Hospital → Replan**

A single credible urgent report can activate the response workflow immediately. The system does **not** wait for multiple independent reports before beginning response planning.

## What SirenGrid Coordinates

- Egyptian Arabic voice/text emergency intake with optional image and location
- Immediate incident activation and continuous evidence updates
- Ambulance and fire/rescue resource coordination
- Traffic-aware dynamic routing
- Emergency corridor / traffic-priority simulation
- Location-relevant clear-the-way driver alert simulation
- City emergency coverage and resource-resilience analysis
- Response-plan simulation and comparison
- Human approval for critical operational actions
- Hospital selection using ETA + modeled capacity/capability
- Hospital pre-alert before arrival
- Dynamic replanning when roads, resources, hospitals, or incident conditions change
- Confidence, evidence provenance, explainability, and data freshness
- Minimal multi-incident resource contention awareness

### Bonus after the core is stable

- Social Media Intelligence for unverified public emergency signals and evidence fusion

## Scope

- **MVP:** Nasr City, Cairo
- **Initial working/demo zone:** Rabaa → Tayaran → Abbas El Akkad → Makram Ebeid → El Nasr Road
- **Long-term vision:** Greater Cairo
- **Primary user:** Emergency Control Room Operator / Dispatcher
- **Final demo scenario:** not locked yet

## Product Boundary

SirenGrid is a **decision-support and coordination system**, not an autonomous emergency commander.

The AI can understand, correlate, simulate, compare, recommend, and explain. Critical operational actions remain under **human approval**.

Government dispatch systems, physical traffic-light control, live hospital-capacity systems, and citywide public alerts are treated as **simulated integrations** unless a real authorized connection is available.

## Architecture & Operational Hardening

- **Single-Worker FastAPI Backend:** Local in-memory graph state and WebSocket coordination are owned by a single-process runtime.
- **SQLite Concurrency Safeguards:** Explicit 5000ms busy timeout and `BEGIN IMMEDIATE` write serialization prevent lock contention under concurrent operations.
- **Referential Integrity:** Domain relationships and state transitions are strictly enforced via application validations and lifecycle guards.
- **Non-Blocking Operations Stream:** WebSocket broadcasts are fire-and-forget; stalled client sockets never block API transactions, and REST serves as the canonical state recovery path.
- **Strict Security Fences:** Explicit credentialed CORS allowlists (wildcards rejected) and media file signature validation.

## Evaluation Architecture

The system features a decoupled, two-layer evaluation suite:
- **Layer A (Comparative Benchmark):** 36 deterministic scenarios comparing greedy baseline dispatch against SirenGrid's joint coverage-aware optimization. Evaluated across multi-dimensional metrics (ETA, coverage preservation, reserve resilience, hospital outcomes, replan response, failure handling).
- **Layer B (Production Acceptance):** 10 end-to-end integration scenarios verifying REST API lifecycle transitions, optimistic concurrency versioning, and database persistence.

## Gated Simulation Controls

For demonstration and testing, minimal gated controls exist under `/api/v1/simulation` (`/reset`, `/load/{scenario_id}`, `/events`, `/status`).
- Disabled by default via `SIMULATION_CONTROLS_ENABLED=false` (returns `403 SIMULATION_DISABLED` when disabled).
- Local demo use only; contains no background scheduler, worker loop, or external side effects.
- All simulation outputs are explicitly labeled `SYNTHETIC` or `SIMULATED`.

## Repository Structure

```text
SirenGrid/
├── frontend/               # Operator-facing application
├── backend/                # APIs, AI/decision logic, routing and optimization
├── data/                   # Public, simulated and synthetic project data
├── docs/
│   ├── MASTER_PLAN.md      # Product source of truth
│   └── DECISIONS.md        # Approved project/architecture decisions
├── .github/
│   └── PULL_REQUEST_TEMPLATE.md
├── CONTRIBUTING.md
├── .gitignore
└── README.md
```

The detailed product contract lives in [`docs/MASTER_PLAN.md`](docs/MASTER_PLAN.md). Contributors must not silently change product scope or behavior.

## Development Rules

- Keep the implementation focused on the approved Master Plan.
- Do not add features just because they are technically interesting.
- Search relevant public repositories before rebuilding solved subsystems from scratch.
- Reuse useful code/reference implementations when they are understood and clearly fit SirenGrid.
- Never present simulated data or integrations as live/official.
- Work in focused branches and keep unrelated changes out of the same task.

## Hackathon

Built by **Code Titans** for **IMPACT ECU 2026** at the Egyptian Chinese University.
