# SirenGrid Decision Log

This file records approved product and architecture decisions that materially affect the project.

The detailed product behavior remains defined by `docs/MASTER_PLAN.md`.

## How to Record a Decision

Use the following format:

```markdown
## PD-### — Short Decision Title

**Date:** YYYY-MM-DD  
**Status:** Approved / Superseded  
**Owner:** Name or role

### Decision
What was decided.

### Reason
Why this option was selected.

### Impact
Which flows, files, interfaces, or features are affected.

### Notes
Any constraints or follow-up work.
```

---

## PD-001 — Product Name

**Date:** 2026-09-06  
**Status:** Approved

### Decision
The project name is **SirenGrid**.

### Reason
The name represents an emergency signal (`Siren`) and the coordinated network of incidents, responders, roads, coverage, hospitals, and alerts (`Grid`).

### Impact
Use `SirenGrid` as the primary product name across the repository and product-facing interfaces.

---

## PD-002 — MVP Geography

**Date:** 2026-09-06  
**Status:** Approved

### Decision
The MVP targets **Nasr City, Cairo**.

Initial working/demo zone:
**Rabaa → Tayaran → Abbas El Akkad → Makram Ebeid → El Nasr Road**.

Long-term product vision may expand to Greater Cairo.

---

## PD-003 — Final Demo Scenario

**Date:** 2026-09-06  
**Status:** Open / Not Locked

### Decision
Do not hardcode the product around one final demo incident yet.

Current leading reference candidate: **multi-casualty urban road incident**.
A major urban building fire remains an alternative.

### Impact
Implementation must support the approved product workflow without depending structurally on one exact demo story.

---

## PD-004 — Bonus Feature Gate

**Date:** 2026-09-06  
**Status:** Approved

### Decision
**Social Media Intelligence** is the only currently approved bonus feature.

It should begin only after the core end-to-end workflow is stable and demo-ready.
