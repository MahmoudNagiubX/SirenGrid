# SirenGrid Frontend

Faithful implementation of the approved **SirenGrid Claude Design** system
(`claude.ai/design` project `be6b3892-1609-4aa6-b86a-49cdad7abadf`).

This is a **frontend-only, design-implementation phase**. It renders the complete
interface against isolated mock data and is ready for backend integration in a
later dedicated phase. No operational logic (ETA, routing, plan ranking, coverage,
hospital suitability, replan materiality, confidence) is computed here — the UI
only *displays* those values.

## Stack

- **Vite + React 18 + TypeScript** (owner-approved, see `docs/DECISIONS.md` PD-062)
- Plain CSS custom properties for the design tokens — no CSS framework
- `lucide-react` for icons (the design system's icon family is Lucide)

No other runtime dependencies.

## Commands

```bash
npm install
npm run dev        # dev server on http://localhost:5173
npm run build      # typecheck + production build
npm run typecheck
npm run lint
npm run preview    # serve the production build
```

## Design sources

| Area | Source in the Claude Design project |
| --- | --- |
| Tokens | `tokens/*.css`, `base.css` → `src/styles/{tokens,base}.css` |
| Core components | `components/**` → `src/components/*` |
| Operations shell primitives | `ui_kits/operations_center/shell.jsx` → `src/ops/primitives.tsx` |
| Status strip / incident rail / history dock | `ui_kits/operations_center/workspace.jsx` → `src/ops/workspace.tsx` |
| Map | `ui_kits/operations_center/map.jsx` → `src/ops/DenseMap.tsx` |
| Decision workspace + tabs | `ui_kits/operations_center/decision.jsx` → `src/ops/DecisionWorkspace.tsx` |
| Operations container + state routing | `ui_kits/operations_center/index.html` → `src/ops/Operations.tsx`, `src/App.tsx` |
| Resources / Timeline | `ui_kits/operations_center/screens-resources.jsx` → `src/ops/screens-resources.tsx` |
| Demo controls / Benchmark | `ui_kits/operations_center/screens-support.jsx` → `src/ops/screens-support.tsx` |
| Landing | `ui_kits/landing/index.html` → `src/pages/Landing.tsx` |

Screenshots used as visual acceptance references: `screenshots/{landing,landing2,01-ops,02-ops}.png`.

## Screens / states

- **Landing** — single-screen product landing over the Cairo map ground.
- **Operations Center** — one integrated workspace (incident rail + dense map hero +
  history dock + decision workspace) that flexes into seven operational states:
  Overview · Incident Focus · Plan Review · Active Response · Replan · Hospital · Coverage.
  Deep-linkable via `#<state>` (`#plan`, `#replan`, …), mirroring the design's `state-*.html`.
- **Resources** — unit table + detail drawer + hospital readiness.
- **Benchmark** — baseline vs SirenGrid-assisted, no invented performance numbers.
- **Scenario / Demo controls** — reached from the status-strip utility icon; clearly labelled simulated.

## Mock data — temporary

Every demo value lives in **`src/data/mock.ts`**, isolated so it can be replaced by
real API responses without touching presentation components. Nothing else in `src/`
hardcodes operational values.

## Product semantics preserved

- AI recommendations sit in a dashed `AiBlock` labelled "Recommendation · not executed";
  human-approved actions render separately with a confirmed badge and an `ApprovalBar`.
- Severity (red family, `Badge`) and AI confidence (blue `ConfidenceMeter`) are separate visual systems.
- Every material fact carries provenance (AI-extracted / source-reported / responder-confirmed /
  operator-corrected / simulated / stale).
- Simulated data and integrations are labelled throughout.
