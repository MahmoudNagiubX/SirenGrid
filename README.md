# SirenGrid 🚨

**AI-powered emergency response coordination for Cairo — built for IMPACT ECU 2026.**

SirenGrid is a **two-sided digital emergency-response platform** for Egypt:

1. **Citizen Mobile App** — a citizen-facing **Flutter** app for one-tap **Ambulance / Fire / Police / General Emergency** requests. A pre-registered citizen confirms once; the app sends the requested service plus **fresh Device GPS**, which is the emergency operational location. The registered address is **account context only**, never a dispatch location. The app shows tracking / status / ETA when the backend has valid data and receives **FCM** notifications (including citizen-facing Clear-the-Way where applicable).
2. **Institutional Command Center** — the government / authorized-facility web application (this repo's `frontend/`), **preserved and upgraded**. It turns an incident report — from the Citizen App, an operator, or an emergency-call channel — into a coordinated response across responders, roads, emergency coverage, and receiving hospitals.

The **FastAPI backend is the single operational source of truth** for both surfaces; critical response changes remain **human-approved**. Citizen identity is synthetic/demo for the hackathon (no real National-ID/KYC and no real emergency-service integration). See `docs/MASTER_PLAN.md` §4.7 and PD-081 / PD-082 / PD-083 in `docs/DECISIONS.md`.

## Business Positioning

SirenGrid is a **B2G platform with a citizen-facing access layer**: citizens are free end users / beneficiaries; government, city authorities, and authorized emergency institutions are the payer / customer. Value model: deployment / integration + annual platform licensing / support + optional modules / integrations. No official Egyptian government partnership is claimed.

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
- **Users:** citizens (Mobile App — end users / beneficiaries) and the Emergency Control Room Operator / Dispatcher + authorized institutional staff (Command Center — customer/payer side)
- **Final demo scenario:** not locked yet

## Product Boundary

SirenGrid is a **decision-support and coordination system**, not an autonomous emergency commander.

The AI can understand, correlate, simulate, compare, recommend, and explain. Critical operational actions remain under **human approval**.

Government dispatch systems, physical traffic-light control, live hospital-capacity systems, and citywide public alerts are treated as **simulated integrations** unless a real authorized connection is available.

The Citizen Mobile App request flow is a **real prototype flow** against this backend, but citizen identity is **synthetic/demo** (no real National-ID/KYC), Police/General requests are **operator handoff/review** (no invented police optimizer), and Device GPS and registered address remain **separate** concepts. **Firebase/FCM is citizen notification transport only** — not operational truth and not an authentication replacement.

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
├── frontend/               # Institutional Command Center (web); the Citizen Mobile App is a separate Flutter surface
├── backend/                # APIs (institutional + mobile), AI/decision logic, routing and optimization
├── data/                   # Public, simulated and synthetic project data
├── docs/
│   ├── MASTER_PLAN.md      # Product source of truth (v1.3 — two-sided platform)
│   └── DECISIONS.md        # Approved project/architecture decisions (through PD-083)
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
