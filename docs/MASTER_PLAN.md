# SirenGrid / City Emergency AI
## Master Product & System Behavior Plan — v1.2

> **Status:** Product concept locked for implementation planning  
> **Primary purpose of this file:** Single source of truth for humans and AI coding agents  
> **Scope of this file:** Product idea, behavior, flows, features, boundaries, data semantics, rules, acceptance criteria, and implementation discipline  
> **Explicitly NOT in scope:** Tech stack selection, framework selection, cloud/provider selection, database choice, model vendor choice, deployment architecture, detailed software architecture  
> **Primary geographic MVP scope:** Nasr City, Cairo  
> **Initial working/demo zone:** Rabaa → Tayaran → Abbas El Akkad → Makram Ebeid → El Nasr Road  
> **Long-term product vision:** Greater Cairo, then other cities  
> **Primary user:** Emergency Control Room Operator / Dispatcher  
> **Secondary users:** Incident Commander, ambulance/fire-response teams, receiving hospital staff  
> **Reference demo candidate:** Multi-casualty urban road incident (NOT locked; final demo scenario remains open)  
> **Bonus feature after core completion:** Social Media Intelligence
> **Revision v1.2:** Clarifies that SirenGrid intake begins on the control-room side through existing emergency communication channels; the MVP has no citizen-facing SirenGrid reporting app.

---

# 0. READ THIS FIRST — NON-NEGOTIABLE OPERATING CONTRACT

This document is intentionally detailed so that a human developer or AI coding agent can understand the product without inventing missing behavior.

## 0.1 This file is authoritative

When implementing the system, follow this priority order:

1. **This Master Plan**
2. A later explicitly approved Product Decision Log or Master Plan revision
3. Explicit instructions from the responsible human developer/user
4. Existing project code and tests, only when they do not conflict with the approved plan
5. Implementation convenience

Implementation convenience must **never** silently change product behavior.

---

## 0.2 AI agents must not improvise product decisions

If an AI agent encounters a product decision that is:

- undefined,
- ambiguous,
- contradictory,
- safety-sensitive,
- likely to change user-visible behavior,
- likely to add a new feature,
- likely to remove or weaken an approved feature,
- likely to change the meaning of a metric,
- likely to change the authority of the AI,
- likely to change what is real vs simulated,
- likely to change the scope of Nasr City / Greater Cairo,
- or likely to materially change the demo story,

the AI **must stop and ask the human developer for clarification**.

It must **not** choose what “seems best” on its own.

### Required behavior when blocked

Use a concise clarification format:

> **Decision needed:** [exact decision]  
> **Why it is not defined:** [one sentence]  
> **Options:** A / B / C, only if useful  
> **Current implementation is paused only for this decision.**

Do not use the ambiguity as permission to redesign the product.

---

## 0.3 No scope creep

An implementation agent may not add any new major product feature unless it is explicitly approved.

Examples of forbidden spontaneous additions:

- predictive crime,
- predictive accidents,
- drones,
- IoT hardware,
- blockchain,
- facial recognition,
- autonomous emergency dispatch,
- a generic chatbot,
- a citywide surveillance system,
- earthquake simulation,
- flood prediction,
- citizen scoring,
- insurance workflows,
- police automation,
- emergency medical diagnosis,
- complex hospital electronic records,
- new disaster types purely for presentation,
- additional agent roles solely because “multi-agent looks impressive.”

If a developer sees an attractive extra idea, record it in **Future / Parking Lot**, do not silently implement it.

---

## 0.4 No fake capability claims

The prototype may simulate integrations that require government, telecom, traffic-control, hospital, or emergency-service access.

The system must clearly distinguish:

### Real prototype logic
Actual logic executed by our software, such as:

- incident creation and updates,
- multimodal evidence interpretation,
- report fusion,
- incident severity/confidence representation,
- route calculation,
- traffic-aware route comparison,
- resource availability reasoning,
- coverage impact calculation,
- hospital ranking,
- response-plan simulation,
- replanning,
- human approval flow,
- explanation,
- status tracking,
- benchmark/evaluation runs.

### Simulated external integrations
Interfaces demonstrated as if connected, but not connected to live Egyptian government infrastructure, such as:

- physical traffic-light control,
- actual Civil Defense dispatch,
- actual Egyptian Ambulance Authority dispatch,
- actual hospital admission/capacity systems,
- mobile-network geofenced alerts,
- live navigation-app alerts to real drivers,
- official emergency-number call handling,
- direct telecom SMS broadcast.

Simulated integrations must be labeled **Simulated / Demo Integration** in implementation notes and, where appropriate, in the UI.

---

# 1. PRODUCT IN ONE SENTENCE

**SirenGrid is an AI-assisted city emergency response network that turns incoming emergency information into a coordinated, explainable, continuously updated response plan across responders, roads, city coverage, and receiving hospitals while keeping critical operational actions under human control.**

---

# 2. THE CORE PROBLEM

Urban emergency response is not merely a “find the nearest ambulance” problem.

A serious incident can create several simultaneous operational problems:

- The caller may describe the situation incompletely.
- Different reports may refer to the same incident.
- Roads may be congested or blocked.
- The nearest responder may not be the best responder.
- Sending too many resources from one zone may leave another zone under-covered.
- The nearest hospital may be overloaded or unsuitable.
- Responders may need traffic priority.
- Drivers ahead of the emergency vehicle may not know that they need to clear a path.
- The receiving hospital may lose valuable preparation time if it is notified too late.
- Conditions may change after dispatch.
- The control-room operator must understand *why* a recommendation changed.

SirenGrid is built around this operational chain.

---

# 3. WHAT THE PRODUCT IS NOT

SirenGrid is NOT:

- a replacement for emergency operators,
- an autonomous emergency commander,
- a medical diagnosis system,
- a public “ask anything” chatbot,
- merely a map,
- merely an ambulance-routing app,
- merely a hospital finder,
- merely a fire-reporting app,
- a citizen-facing emergency-reporting app,
- merely an incident classifier,
- merely a traffic-light controller,
- a “smart city operating system for everything,”
- a system that waits for multiple reports before responding,
- a system that assumes AI-generated answers are ground truth.

The product’s value is the **closed-loop coordination** of emergency response.

---

# 4. LOCKED PRODUCT DECISIONS

The following decisions are locked unless explicitly reopened by the project owner.

## 4.1 Geographic scope

### Product vision
Greater Cairo.

### MVP
Nasr City, Cairo.

### Initial operational/demo zone
Rabaa → Tayaran → Abbas El Akkad → Makram Ebeid → El Nasr Road.

The software should avoid hardcoding itself in a way that makes later expansion impossible, but implementation should be optimized first for a reliable Nasr City prototype.

---

## 4.2 Primary user

**Emergency Control Room Operator / Dispatcher**

This person:

- sees incoming incidents,
- reviews AI interpretation,
- reviews resource recommendations,
- reviews route/coverage/hospital consequences,
- approves or rejects critical actions,
- monitors live response,
- receives replanning suggestions.

---

## 4.3 Secondary users

### Incident Commander
Needs a high-level operational view and status.

### Ambulance / Fire Response Crew
Needs assigned incident, route, navigation/corridor status, and operational updates.

### Receiving Hospital
Needs a structured incoming-case pre-alert and ETA.

### Public / Drivers
Only receive narrow, location-relevant “clear the way” alerts in the simulated integration.

---

## 4.4 AI authority boundary

AI may:

- understand,
- classify,
- extract,
- correlate,
- simulate,
- calculate through approved tools,
- compare,
- recommend,
- explain,
- re-evaluate.

AI must not independently execute critical real-world emergency actions.

For the prototype, critical actions are presented for **human approval**.

---

## 4.5 Immediate response rule

**A credible first report must be sufficient to create an incident and start the response workflow.**

The system must never require multiple independent reports before an emergency can be acted upon.

Additional reports may:

- increase confidence,
- decrease confidence,
- change severity,
- add evidence,
- add casualty information,
- update road conditions,
- merge into the existing incident.

They are **not a dispatch prerequisite**.

---

## 4.6 Product name

**Locked working name: SirenGrid**

Meaning:
- **Siren** = urgent emergency signal / response.
- **Grid** = the coordinated network of incidents, responders, roads, city coverage, hospitals, and alerts.

Naming rule:
- Use **SirenGrid** as the product name in product-facing text and documentation.
- “City Emergency AI” may remain as an explanatory subtitle/descriptor, not the primary product name.
- Do not introduce alternative product names in code, UI, or documentation without explicit approval.

---

## 4.7 Control-room-side intake / no citizen-facing reporting app

**SirenGrid is an operator/control-room system, not a citizen reporting application.**

For the MVP, citizens continue using normal existing emergency behavior, such as calling the relevant emergency service. SirenGrid begins on the **control-room side** when emergency information reaches the operator environment.

Primary intake may include:

- emergency-call audio or transcript received through an existing emergency communication channel,
- dispatcher/operator-entered text or structured information,
- caller location or location metadata made available to the control room,
- image/video evidence received or forwarded through an existing authorized operational channel,
- responder updates,
- hospital updates.

The MVP must **not** require citizens to discover, install, open, or submit reports through a SirenGrid application.

Social Media Intelligence remains a separate bonus source of **unverified external signals** and is not a citizen reporting workflow.

This decision changes the intake boundary, not the immediate-response rule: a single credible urgent report received by the control room is still enough to create an incident and begin response planning.

# 5. UNLOCKED / DEFERRED DECISIONS

These are intentionally not locked yet.

## 5.1 Final demo scenario

Current best reference candidate:

**Multi-casualty urban road incident**

Possible alternative:

**Major urban building fire**

The product must not become structurally dependent on one exact demo scenario.

The final demo scenario will be chosen after implementation maturity is known.

---

## 5.2 Tech stack

Not decided in this document.

Architecture/technical owners will decide separately.

No AI agent should infer a stack from examples in this file.

---

## 5.3 Exact live external data providers

Not locked.

The product behavior is defined independently of provider choice.

---

# 6. PRODUCT DESIGN PRINCIPLES

## P1 — Respond first, enrich while moving
For credible high-severity emergencies, do not delay response waiting for perfect information.

## P2 — One incident, many evidence sources
Many reports can represent one real event.

## P3 — AI explains; deterministic logic calculates where possible
Routing, scoring, optimization, coverage, and constraints should be calculated through reliable system logic/tools rather than invented in free-form text.

## P4 — Optimize the network, not one vehicle
Do not save one incident by unknowingly destroying emergency coverage elsewhere.

## P5 — The nearest option is not automatically the best option
Resources and hospitals are chosen using multiple constraints.

## P6 — Conditions change
A route or plan is not permanent. Replanning is a core product behavior.

## P7 — Humans remain operationally accountable
Critical actions require a human decision in the prototype.

## P8 — The system must expose uncertainty
Confidence and evidence matter.

## P9 — The system must be demonstrably useful
Every core feature should affect the response flow or a measurable result.

## P10 — Stable, coherent execution beats feature count
Do not sacrifice a reliable end-to-end experience for extra features.

---

# 7. CORE PRODUCT ENTITIES

This section defines conceptual entities, not database design.

## 7.1 Incident

An Incident represents one real emergency event.

Minimum conceptual fields:

- incident identifier
- incident type
- location
- timestamp
- lifecycle state
- severity
- confidence
- source count
- evidence list
- casualty information, if known
- affected roads, if known
- recommended responders
- assigned responders
- selected receiving hospital(s), if relevant
- operational notes
- current response plan
- previous response plans
- approval history
- last updated time

---

## 7.2 Report

A Report is one incoming piece of information.

Possible sources on the control-room side:

- emergency-call audio or transcript received through an existing emergency communication channel,
- dispatcher/operator-entered text or structured information,
- caller location or location metadata made available to the control room,
- image/video evidence received or forwarded through an existing authorized operational channel,
- responder update,
- hospital update,
- bonus: social-media signal treated as unverified external intelligence.

A report may create a new incident or be attached to an existing incident.

---

## 7.3 Evidence Item

An Evidence Item is a piece of information used to support or challenge an incident interpretation.

Examples:

- voice transcript,
- image,
- reported location,
- timestamp,
- second caller,
- responder confirmation,
- road-status input,
- hospital status.

Evidence must retain provenance: the system should know where it came from.

---

## 7.4 Emergency Resource

Examples:

- ambulance,
- fire/rescue unit.

Relevant conceptual attributes:

- type,
- current status,
- current location,
- home/base zone,
- capabilities if modeled,
- assignment,
- ETA,
- availability.

---

## 7.5 Hospital

Relevant conceptual attributes:

- location,
- currently modeled availability,
- modeled capacity,
- modeled specialties/capabilities,
- active incoming cases,
- ETA from incident,
- suitability score/explanation.

For the prototype, hospital operational capacity may be simulated.

---

## 7.6 Road Segment

Represents a routable portion of the city road network.

Possible state:

- normal,
- congested,
- highly congested,
- partially restricted,
- closed,
- emergency-priority corridor.

---

## 7.7 Coverage Zone

A geographic zone used to represent whether enough emergency-response capability remains available for nearby demand.

The exact mathematical definition is an architecture/analytics decision, but product behavior requires the concept.

---

## 7.8 Response Plan

A Response Plan is one candidate coordinated action set.

It may include:

- which responders to assign,
- which responder stays in reserve,
- routes,
- hospital destination(s),
- corridor request,
- public alert region,
- resource repositioning,
- expected ETA,
- expected coverage impact,
- expected hospital load impact.

---

# 8. INCIDENT LIFECYCLE

Recommended conceptual state machine:

1. **RECEIVED**
2. **INTERPRETING**
3. **ACTIVE / UNCONFIRMED DETAILS**
4. **RESPONSE PROPOSED**
5. **AWAITING HUMAN APPROVAL**
6. **DISPATCHED / RESPONSE ACTIVE**
7. **EN ROUTE**
8. **ON SCENE**
9. **TRANSPORT ACTIVE** if medical transport is required
10. **HOSPITAL PRE-ALERTED**
11. **HANDOVER / RESOLUTION**
12. **CLOSED**

Additional state:

- **REQUIRES REVIEW**
- **DUPLICATE / MERGED**
- **CANCELLED / FALSE REPORT**

Important:

An incident may become **ACTIVE** before every detail is verified.

---

# 9. END-TO-END GOLDEN FLOW

This is the main product behavior.

## Phase A — Emergency information reaches the control room

Citizens use normal existing emergency channels; they do **not** open SirenGrid to create a report.

SirenGrid receives information on the control-room side, such as:

- emergency-call audio or transcript,
- dispatcher/operator-entered text,
- caller location or available location metadata,
- image/video evidence received or forwarded through an existing authorized channel,
- responder or hospital updates.

The system immediately captures source and timestamp and preserves provenance.

---

## Phase B — Incident understanding

The system extracts, where possible:

- what happened,
- where,
- possible severity,
- possible casualties,
- possible trapped persons,
- road impact,
- needed response types,
- confidence.

If information is incomplete, the system clearly marks unknown fields.

It must not fabricate missing facts.

---

## Phase C — Immediate activation

If the report is credible and potentially urgent:

- create the incident,
- show it in the operator dashboard,
- begin response planning immediately.

Do NOT wait for a second independent report.

---

## Phase D — Continued information gathering

While response planning or movement has begun, the operator/AI intake can collect additional details.

Additional evidence updates the existing incident.

The response can be upgraded or adjusted.

---

## Phase E — Resource planning

The system evaluates available responders.

It considers:

- incident need,
- responder proximity/ETA,
- road conditions,
- responder status,
- effect of removing that resource from its current zone,
- other active incidents if modeled.

It creates one or more response plans.

---

## Phase F — Coverage impact

Before recommending a plan, estimate:

- what city/zone coverage remains,
- whether a zone becomes dangerously under-covered,
- whether repositioning another resource improves resilience.

This is one of the product’s defining features.

---

## Phase G — Human approval

The operator sees:

- recommended plan,
- key reasons,
- ETA,
- coverage impact,
- major constraints,
- alternative plan(s), if useful,
- confidence/uncertainty.

The operator:

- approves,
- rejects,
- or chooses an alternative.

---

## Phase H — Dynamic emergency routing

After approval:

- selected resources receive a route,
- the route reflects modeled traffic/closures,
- ETA is calculated,
- route status remains monitored.

---

## Phase I — Emergency corridor

For the approved emergency route:

- model which intersections/road segments need priority,
- show a corridor status,
- simulate traffic-priority requests,
- update route if conditions change.

Physical traffic-light control is an external integration and is simulated in the prototype unless a real permitted integration exists.

---

## Phase J — Clear-the-way public alert

The system determines a narrow geographic area ahead of the emergency vehicle.

A simulated location-based alert may be issued:

> Emergency vehicle approaching. Clear the route / move safely aside.

The alert must be:

- geographically relevant,
- temporary,
- tied to an active approved route.

Do not simulate blasting an entire city with alerts.

---

## Phase K — Scene updates

New information can arrive from:

- responders,
- operator,
- new caller,
- visual evidence,
- road-status update.

The incident model updates.

If the plan is no longer good enough, trigger replanning.

---

## Phase L — Hospital decision

For casualties requiring transport, select the most appropriate hospital using modeled factors such as:

- travel time,
- congestion,
- capacity,
- relevant capability/specialty,
- load from other incoming cases.

“Nearest” is not automatically “best.”

---

## Phase M — Hospital pre-alert

Once a destination is selected and approved, the hospital receives a structured simulated pre-alert.

Possible fields:

- incoming ambulance/unit,
- incident type,
- patient count,
- severity category,
- relevant known details,
- ETA,
- requested receiving capability.

Do not invent detailed clinical information that was never provided.

---

## Phase N — Continuous replanning

If:

- road closes,
- congestion increases,
- hospital becomes unavailable,
- incident severity changes,
- additional casualties are discovered,
- responder becomes unavailable,
- another serious incident affects coverage,

the system re-runs the plan comparison.

It must display:

- what changed,
- why the recommendation changed,
- old vs new consequences.

Human approval is required again for materially changed critical actions.

---

## Phase O — Resolution and audit trail

The incident can be closed after response completion.

Retain a clear event history:

- incoming reports,
- important evidence updates,
- recommendations,
- human decisions,
- route changes,
- hospital decisions,
- final state.

---

# 10. FEATURE SPECIFICATIONS

---

# F01 — CONTROL-ROOM MULTIMODAL EMERGENCY INTAKE

## Purpose
Turn messy emergency information reaching the control room into structured operational information quickly.

## Supported conceptual inputs

Core:

- emergency-call audio or transcript,
- dispatcher/operator-entered text or structured report,
- image/video evidence available to the control room,
- caller location or available location metadata.

Optional if implementation time permits:

- short video or extracted frame.

## Required behavior

The system should attempt to identify:

- incident category,
- location,
- urgency indicators,
- casualties,
- trapped people,
- road obstruction,
- fire/smoke,
- vehicle involvement,
- requested service if explicitly stated.

Unknown information remains unknown.

## Egyptian Arabic

Emergency-call intake should support natural Egyptian Arabic from callers.

Callers do not interact with a SirenGrid citizen application; their speech reaches SirenGrid through the existing emergency-call/control-room workflow.

The system should not require callers to speak formal Arabic or English.

## Output

Structured incident interpretation plus:

- confidence,
- evidence references,
- missing critical information.

## Must NOT do

- Wait for several reports.
- Invent casualty counts.
- Invent an address from vague input.
- Diagnose a medical condition.
- Automatically reject a report because there is no photo.
- Automatically treat low-confidence AI classification as “no emergency.”

## Acceptance examples

### Example A
Caller:
> “في حادثة كبيرة عند عباس العقاد وفي حد مش عارف يطلع من العربية.”

Expected:
- probable road crash,
- Abbas El Akkad approximate location,
- trapped-person indicator,
- urgent response,
- unknown casualty count.

### Example B
Caller sends photo but no text.

Expected:
- visual interpretation,
- location remains unknown unless metadata/operator supplies it,
- system asks/flags for location.

---

# F02 — IMMEDIATE INCIDENT ACTIVATION

## Purpose
Ensure AI never becomes a dangerous waiting gate.

## Rule

A single credible urgent report may activate the emergency workflow.

## Required behavior

When urgency threshold is met:

- create incident,
- mark uncertainty,
- begin response plan,
- continue asking/collecting information.

## Important distinction

**Verification is continuous, not a blocking ceremony.**

## Acceptance criterion

A demo incident can go from one caller report to an active response workflow without a second report.

---

# F03 — REPORT FUSION & DUPLICATE INCIDENT DETECTION

## Purpose
Avoid treating several reports of one emergency as separate unrelated incidents.

## Required behavior

When a new report arrives, compare:

- location proximity,
- time proximity,
- semantic incident similarity,
- visual/context clues if available.

Possible outcomes:

- likely same incident → attach/update,
- uncertain → operator review,
- clearly different → create separate incident.

## What report fusion may change

- confidence,
- severity,
- casualty count,
- road impact,
- exact location,
- required resources.

## Must NOT do

- delay initial response waiting for fusion,
- silently merge far-apart incidents,
- overwrite earlier evidence.

---

# F04 — CONFIDENCE, EVIDENCE & EXPLAINABILITY

## Purpose
Make the AI’s interpretation inspectable.

## Required UI/behavior concepts

For each important interpretation show:

- confidence level,
- evidence count,
- key evidence sources,
- known vs unknown facts.

Example:

> **Probable major road crash — High confidence**  
> Based on: caller voice + location + image  
> Unknown: exact casualty count

## Recommendation explanation

Each response recommendation should answer:

- Why this resource?
- Why this route?
- Why this hospital?
- What coverage consequence was considered?
- What major constraint caused this choice?

## Must NOT do

- show fake precision such as 96.384% unless the score actually has that meaning,
- present AI confidence as a probability of human survival,
- hide contradictory evidence.

---

# F05 — LIVE EMERGENCY MAP / OPERATIONAL DIGITAL TWIN

## Purpose
Provide one operational view of the city response.

## Core map objects

- active incident,
- ambulances,
- fire/rescue units,
- hospitals,
- active routes,
- congestion/road-state visualization,
- restricted/closed roads,
- emergency corridor,
- coverage zones,
- public-alert region if active.

## Required behavior

The map should visibly react to changes.

Examples:

- road becomes blocked → route changes,
- ambulance dispatched → status changes,
- hospital selected → destination highlighted,
- coverage drops → affected zone changes,
- replanning occurs → old/new plan visibly differ.

## What “digital twin” means in this prototype

A simplified operational digital representation of relevant emergency resources and road conditions.

It does NOT mean a photorealistic 3D model of Cairo.

Do not build 3D city visualization unless separately approved.

---

# F06 — TRAFFIC-AWARE DYNAMIC ROUTING

## Purpose
Get responders to the incident/hospital using the best currently available route, not merely shortest geometric distance.

## Required considerations

- road network,
- congestion,
- closures/restrictions,
- current resource location,
- incident/hospital destination.

## Required behavior

- calculate a preferred route,
- display ETA,
- maintain at least one alternative if useful,
- re-evaluate when a material road condition changes.

## Must NOT do

- label a static hardcoded route as “AI optimized,”
- ignore a known closed road,
- automatically route through physically impossible connections.

## Replanning trigger example

If the current route’s ETA worsens materially or a segment closes:
- mark current route degraded,
- calculate alternative,
- explain change,
- update corridor plan.

---

# F07 — EMERGENCY CORRIDOR / TRAFFIC PRIORITY

## Purpose
Reduce delay created by signalized intersections and congestion.

## Prototype behavior

For an approved emergency route:

- identify relevant intersections/segments,
- simulate a priority request,
- show which corridor segments are “prepared” or “priority requested,”
- estimate/reflect the corridor in the route plan if modeled.

## Real-world boundary

The prototype does not claim physical control of Cairo traffic signals.

Actual signal preemption requires authorized traffic infrastructure integration.

## Failure behavior

If priority cannot be obtained:
- route should remain valid,
- ETA may worsen,
- system may consider a different route.

---

# F08 — CLEAR-THE-WAY DRIVER ALERTS

## Purpose
Warn drivers ahead of emergency vehicles before the siren reaches them.

## Core concept

A temporary geofenced alert tied to:

- an active emergency vehicle,
- an approved route,
- a forward corridor.

## Example message

> Emergency ambulance approaching this corridor. Please clear the way safely.

## Important privacy/product rule

Do not assume the system knows every driver’s phone number.

The prototype should represent an **integration-ready geofenced alert**, not a mass SMS database.

## Optional simulated delivery channels

- navigation app,
- connected vehicle,
- emergency app,
- telecom alert.

## Must NOT do

- notify the whole city,
- expose patient identity,
- include graphic incident details,
- send public alerts after the emergency vehicle has passed.

---

# F09 — RESOURCE ASSIGNMENT & RESPONSE PLAN GENERATION

## Purpose
Select an effective resource combination rather than blindly sending the nearest unit.

## Required considerations

- incident severity,
- requested responder types,
- location,
- current resource availability,
- route/ETA,
- coverage impact,
- other modeled incidents.

## Output

One recommended coordinated response plan.

If useful, also show alternatives.

## Example

Plan A:
- Ambulance A1
- Ambulance A2
- Rescue Unit F3

Plan B:
- Ambulance A1
- Ambulance A4
- Rescue Unit F3
- Reposition Ambulance A5 to maintain Zone C

The system may recommend Plan B if city coverage is materially better.

---

# F10 — CITY EMERGENCY COVERAGE / RESOURCE RESILIENCE

## Purpose
Prevent the system from solving one emergency by creating an unacceptable coverage gap elsewhere.

## This is a defining feature

When resources leave their zones, calculate the effect on surrounding emergency coverage.

## Required behavior

Before recommendation:

- estimate baseline coverage,
- estimate post-dispatch coverage,
- flag materially under-covered zones,
- test resource repositioning if useful.

## Example explanation

> Sending Ambulances A1, A2, and A3 is faster for this incident by 40 seconds, but leaves Zone C below the target response coverage.  
> Recommended: A1 + A2, with A4 repositioned.

## Metrics may include

- percentage of modeled demand/population within target response time,
- worst-zone response time,
- number of zones below target.

Exact formula will be defined by architecture/analytics owner.

## Must NOT do

- invent population precision,
- present simulated coverage as an official government statistic.

---

# F11 — RESPONSE PLAN SIMULATION / WHAT-IF COMPARISON

## Purpose
Make the system a decision-support tool rather than a route calculator.

## Required behavior

Before recommending a response, compare reasonable candidate plans.

Each plan can differ in:

- responder selection,
- resource repositioning,
- route,
- hospital,
- corridor use.

## Compare on

At minimum where applicable:

- incident ETA,
- coverage preserved,
- hospital suitability/load,
- route feasibility.

## Output

Recommended plan + concise comparison.

## Operator question examples

> “What if we send Ambulance 4 instead?”

> “What if Hospital A becomes unavailable?”

The system should be able to re-run the scenario using the changed condition.

---

# F12 — HUMAN APPROVAL

## Purpose
Keep critical decisions accountable and safe.

## Actions requiring operator approval in the prototype

At minimum:

- final resource dispatch plan,
- material resource repositioning,
- hospital destination if operationally critical,
- materially changed replan,
- simulated corridor activation if presented as an operational command.

## Operator options

- Approve
- Reject
- Select alternative
- Request recalculation
- Manually modify allowed inputs, if product design supports it

## Audit

Record:

- recommendation,
- operator decision,
- timestamp,
- plan version.

---

# F13 — HOSPITAL SELECTION

## Purpose
Choose the best suitable receiving hospital, not necessarily the nearest.

## Factors

- travel ETA,
- modeled availability/capacity,
- relevant capability/specialty,
- current incoming load,
- incident/patient needs if known.

## Output

Ranked suitable hospitals or one recommended hospital plus alternatives.

## Explainability example

> Hospital B recommended despite being 2 minutes farther because Hospital A is modeled at capacity and Hospital B has the required trauma capability.

## Important boundary

Hospital capacity in the prototype may be simulated.

The UI/data model must not imply live official capacity unless truly connected.

---

# F14 — HOSPITAL PRE-ALERT

## Purpose
Give the hospital preparation time before the patient arrives.

## Trigger

After a transport destination is approved.

## Required content

Only known/approved information, such as:

- unit,
- incident category,
- patient count,
- severity/priority,
- major known needs,
- ETA.

## Example

> Incoming emergency case  
> Incident: Multi-vehicle crash  
> Priority: Critical  
> ETA: 8 min  
> Known: suspected severe trauma  
> Unit: Ambulance A2

## Must NOT do

- invent diagnosis,
- send patient-identifying information unless explicitly required and approved,
- claim the hospital acknowledged if it is simulated and no acknowledgement logic exists.

---

# F15 — DYNAMIC REPLANNING

## Purpose
Keep the plan valid after the situation changes.

## Triggers

Examples:

- route blocked,
- congestion spike,
- hospital unavailable,
- new casualty count,
- responder unavailable,
- new incident creates coverage pressure,
- operator changes a constraint.

## Required behavior

1. Detect material change.
2. Mark current plan affected.
3. Recalculate.
4. Compare old/new plan.
5. Explain why the recommendation changed.
6. Request approval for material changes.

## Example

> Road segment on El Nasr Road is now unavailable.  
> Previous ETA: 6:20  
> New ETA on current route: 10:10  
> Alternative route ETA: 7:05  
> Recommendation: reroute via X.

---

# F16 — INCIDENT HISTORY / AUDIT TIMELINE

## Purpose
Make the response traceable.

## Timeline events

- report received,
- incident created,
- evidence added,
- severity changed,
- resource recommended,
- plan approved/rejected,
- resource dispatched,
- route changed,
- hospital selected,
- hospital pre-alerted,
- incident closed.

The history is operational and explanatory, not a blockchain requirement.

---

# F17 — OPERATOR MANUAL CORRECTION & HUMAN DATA CONTROL

## Purpose
Ensure the human operator can correct AI interpretation errors without restarting the incident workflow.

## Why this is core
Emergency information is often incomplete, noisy, or misheard. Human-in-the-loop control is not complete if the operator can only approve/reject a plan but cannot correct the facts the plan is based on.

## Operator-editable incident facts
At minimum, the operator should be able to correct or confirm:

- incident type,
- location,
- severity,
- casualty count or casualty range,
- trapped-person indicator,
- affected/blocked road,
- responder requirement,
- hospital-related operational constraints where authorized.

## Required behavior

When an operator edits a material fact:

1. Preserve the previous value in history.
2. Record that the value was human-corrected.
3. Recalculate any affected response plan.
4. Recalculate affected routes, coverage, hospital ranking, or severity-dependent logic.
5. Explain when the correction materially changes the recommendation.

## Provenance rule

Every material fact should be distinguishable as one of:

- AI-extracted,
- source-reported,
- responder-confirmed,
- operator-corrected,
- externally provided,
- simulated.

## Must NOT do

- silently overwrite human corrections with later AI output,
- erase the original evidence,
- require creating a new incident just to fix a wrong location,
- present a corrected value as if the AI originally predicted it.

---

# F18 — DATA FRESHNESS / STALENESS AWARENESS

## Purpose
Prevent decisions from appearing “live” when their underlying operational data is old or simulated.

## Why this is core
Dynamic routing, hospital selection, resource availability, and replanning are only trustworthy when the operator knows how fresh the underlying data is.

## Data that should expose freshness where relevant

- traffic state,
- road closures,
- responder location,
- responder availability,
- hospital capacity/load,
- incident evidence,
- external/public signal,
- simulated integration status.

## Required behavior

Important operational data should carry:

- last-updated time,
- source/provenance,
- live / simulated / stale status where applicable.

## Staleness behavior

If data becomes older than an approved threshold:

- mark it stale,
- do not silently present it as current,
- reduce confidence in recommendations that depend on it when appropriate,
- request refresh/operator confirmation when the stale value is critical.

## Example

> Hospital B capacity status: **STALE — last updated 18 min ago**  
> Recommendation uses last known capacity and requires operator confirmation.

## Must NOT do

- invent a refresh,
- label simulated data as live,
- hide stale data because it makes the demo less attractive.

Exact staleness thresholds are a technical/operational configuration decision and may be decided later without changing this product rule.

---

# F19 — MINIMAL MULTI-INCIDENT AWARENESS & RESOURCE CONTENTION

## Purpose
Ensure the city-level resource optimizer does not behave as if only one emergency can exist at a time.

## Scope boundary
This is **not** a full citywide emergency scheduling engine.

The MVP only needs enough multi-incident awareness to model scarce-resource conflict realistically.

## Required behavior

The system should be capable of representing at least:

- one primary active incident,
- one additional active/competing incident or reserved emergency demand,
- shared responder availability,
- resulting coverage/resource conflict.

## Example

Incident A requires two ambulances.

A second serious Incident B becomes active while Incident A is still in progress.

The system should:

1. update which resources remain available,
2. recalculate city/zone coverage,
3. detect if the current plan is no longer resilient,
4. recommend reassignment/repositioning only if needed,
5. show the operator the trade-off,
6. require human approval for material changes.

## Prioritization rule

The system may rank incidents using severity/urgency and operational constraints, but it must not invent a complex ethical priority policy that is not explicitly defined.

If two incidents create an unresolved priority conflict, escalate to the human operator.

## Must NOT do

- assume resources assigned to another active incident are available,
- silently cancel one incident to serve another,
- create a fully autonomous citywide dispatch scheduler,
- invent ethical triage policies.

## Why this matters

City emergency coordination is only credible if resource and coverage logic understands that responders are shared across simultaneous demand.

---

# 11. BONUS FEATURE — SOCIAL MEDIA INTELLIGENCE

## Status

**BONUS ONLY. Implement only after the core system is stable and demo-ready.**

If the core has bugs or missing features, do not start this.

---

## Purpose

Use public social signals as an additional early-warning/evidence source.

Examples:

- multiple posts mention a crash on the same road,
- public post includes smoke/fire image and location,
- unusual cluster of reports suggests an incident before official confirmation.

---

## Safety rule

A social-media signal must **never automatically trigger critical dispatch solely because it exists**.

It may:

- create an “unverified signal,”
- increase/decrease confidence,
- attach evidence to an existing incident,
- ask operator to review,
- help detect a possible new incident.

---

## Fusion behavior

Compare social signals using:

- time,
- location,
- semantic similarity,
- visual similarity if available.

---

## UI concept

Display separately from confirmed emergency calls:

> **Social signal — Unverified**

Only upgrade its status when sufficient corroboration or operator review exists.

---

## Why this is bonus

It is valuable, but it must not distract from:

- immediate dispatch,
- routing,
- coverage,
- hospital coordination,
- replanning,
- human approval.

---

# 12. FEATURES EXPLICITLY DEFERRED

These are not part of MVP.

## Predictive accident risk

Potential future feature.

Do not implement unless:

- suitable data is found,
- training/evaluation methodology is defensible,
- product owner explicitly approves.

Reason: a risk prediction shown without appropriate local/geospatial data can look impressive but be scientifically weak.

---

## SOP / procedure RAG

Potential future enhancement after core.

Could ground operational guidance in approved documents.

Not a required MVP feature.

Do not turn the product into a RAG chatbot.

---

## Blockchain

Not approved.

Current audit/history requirements do not justify blockchain complexity.

---

## Drones / IoT sensors

Not approved.

---

## Automatic medical diagnosis

Not approved.

---

# 13. GEOGRAPHIC PRODUCT PLAN

## MVP city
Nasr City, Cairo.

## Initial map/demo zone

Primary working corridor:

- Rabaa area
- Tayaran Street
- Abbas El Akkad
- Makram Ebeid
- El Nasr Road

The exact bounding polygon may be chosen technically later.

---

## Why this scope

This area provides:

- dense road network,
- major corridors,
- plausible congestion,
- hospitals/medical POIs,
- realistic urban incidents,
- enough spatial complexity for routing and coverage simulation.

---

## Expansion

The product should conceptually extend to Greater Cairo later.

Do not spend MVP time building every Cairo district.

---

# 14. REFERENCE DEMO CANDIDATES

Final scenario is NOT locked.

## Candidate A — Multi-casualty road crash

A serious road crash blocks part of a major corridor.

Potentially demonstrates:

- Egyptian Arabic call,
- image/location,
- immediate response,
- several ambulances,
- rescue/fire support,
- congestion,
- dynamic route,
- corridor,
- driver alerts,
- coverage impact,
- hospital load balancing,
- multiple pre-alerts,
- replanning.

Current strongest candidate.

---

## Candidate B — Major building fire

Potentially demonstrates:

- fire/rescue + ambulance,
- trapped occupants,
- congestion,
- routing,
- several response resources,
- hospital coordination,
- changing severity.

---

## Demo selection rule

Pick the scenario that shows the complete system most clearly and reliably.

Do NOT choose a scenario merely because it sounds dramatic.

---

# 15. OPERATOR EXPERIENCE — REQUIRED INFORMATION ARCHITECTURE

This is not a visual design specification. It defines what the operator must be able to understand.

The operator needs:

## A. Incident queue
- new incidents,
- active incidents,
- severity,
- confidence,
- status.

## B. Incident detail
- summary,
- evidence,
- known/unknown fields,
- location,
- resources,
- current plan,
- operator correction/confirmation controls for material incident facts,
- provenance of material facts.

## C. Operational map
- resources,
- route,
- incident,
- hospitals,
- road conditions,
- coverage zones,
- corridor.

## D. Recommendation panel
- recommended plan,
- reason,
- alternatives,
- metrics,
- confidence,
- constraints.

## E. Approval controls
- approve,
- reject,
- choose alternative,
- recalculate.

## F. Live status
- responders en route,
- ETA,
- hospital status,
- replanning alerts,
- freshness/staleness indicators for critical operational data.

## G. Timeline
- what changed,
- who/what changed it,
- operator decisions.

---

# 16. RESPONDER EXPERIENCE

At minimum, a simulated responder view should understand:

- assigned incident,
- incident location,
- priority,
- route,
- ETA,
- route change,
- corridor status,
- relevant operational note.

Do not overload responders with control-room analytics.

---

# 17. HOSPITAL EXPERIENCE

A receiving hospital view/integration should receive:

- incoming unit,
- ETA,
- incident category,
- patient priority/count,
- known relevant preparation information.

The hospital may acknowledge receipt if implemented.

If acknowledgement is simulated, label it accordingly.

---

# 18. PUBLIC ALERT EXPERIENCE

A citizen/driver sees only what is necessary.

Example:

> Emergency vehicle approaching on this corridor. Please make way safely.

Must not expose:

- patient name,
- private medical information,
- graphic details,
- control-room strategy.

---

# 19. INCIDENT SEVERITY & TRIAGE PRODUCT RULES

Exact classification mathematics is not defined here.

But the product must distinguish at least conceptually:

- low,
- moderate,
- high,
- critical.

Severity influences:

- response urgency,
- resource requirement,
- operator prominence,
- hospital preparation.

### Important
Severity is not the same as AI confidence.

Example:

- Severity: Critical
- Confidence: Medium

This is valid.

---

# 20. CONFIDENCE MODEL PRODUCT RULES

Confidence communicates how strongly the system believes an interpretation is supported.

Possible presentation:

- low,
- medium,
- high,

or a clearly defined numeric score.

Use one consistent method.

Do not mix arbitrary “AI confidence” scales across screens.

Confidence can change when evidence arrives.

---

# 21. DATA REALITY RULES

Every data point used by the system belongs to one of these classes:

## A. Real public/geospatial data
Example:
- road geometry,
- public POIs,
- hospital locations.

## B. Real external live data
Only if truly accessed.

## C. Simulated operational data
Example:
- ambulance positions,
- hospital capacity,
- traffic-light status,
- hospital load.

## D. Synthetic evaluation data
Used for benchmark scenarios.

The system documentation and demo must know which class each important data source belongs to.

Do not intentionally blur simulated and live data.

---

# 22. CORE SUCCESS METRICS

Exact target numbers should be set after implementation/testing.

The system should measure where possible:

## Incident-processing metrics
- time from report to structured incident,
- time from report to first response recommendation.

## Mobility metrics
- responder ETA,
- travel-time improvement vs baseline,
- replanning latency.

## Resilience metrics
- emergency coverage before dispatch,
- coverage after dispatch,
- coverage after repositioning,
- worst-zone response time.

## Hospital metrics
- travel ETA to selected hospital,
- modeled load balance,
- preparation lead time from pre-alert.

## AI/quality metrics
- incident extraction correctness,
- duplicate-report fusion correctness,
- explanation consistency,
- confidence calibration if feasible.

## System metrics
- end-to-end workflow success rate,
- number of failed actions,
- response-plan generation latency.

---

# 23. BENCHMARK / EVALUATION MODE

This is not a flashy user feature. It is required for credibility if feasible.

## Goal

Compare a simple baseline against SirenGrid.

Possible baseline:

- nearest available resource,
- nearest hospital,
- no coverage-aware repositioning.

Compare across synthetic/simulated emergency scenarios.

## Suggested evaluation set

30–50 scenarios if time permits.

Vary:

- incident location,
- congestion,
- unavailable roads,
- responder positions,
- hospital capacity,
- second active incident.

## Output

Summarize actual measured results.

Never pre-write fake improvement percentages.

---

# 24. BASELINE VS SIRENGRID

A baseline should intentionally be simple and understandable.

### Baseline example
1. Send nearest available ambulance.
2. Send nearest appropriate rescue unit.
3. Route by shortest/current fastest path.
4. Choose nearest suitable hospital.

### SirenGrid
Adds network-level reasoning:

- coverage preservation,
- hospital load/capability,
- response-plan comparison,
- repositioning,
- continuous replanning.

The comparison is important because it proves why the product exists.

---

# 25. REAL VS SIMULATED INTEGRATION MATRIX

## Expected real internal logic
- incident state machine
- report ingestion
- evidence association
- incident fusion
- response plan generation
- routing calculation
- coverage calculation
- hospital ranking
- plan comparison
- operator approval
- event timeline
- replanning
- benchmark scenarios

## Likely simulated integrations
- Egyptian emergency call infrastructure
- Civil Defense dispatch backend
- Egyptian Ambulance Authority backend
- live traffic-signal system
- hospital capacity backend
- telecom/navigation public alert backend

Simulated integrations should still have clean conceptual interfaces so that a future real integration could replace them.

---

# 26. SAFETY AND FAILURE BEHAVIOR

The product must behave sensibly when data is incomplete.

---

## 26.1 Missing location

If an emergency has no reliable location:

- mark location missing,
- request location/operator entry,
- do not pretend routing is possible.

---

## 26.2 Low-confidence incident type

If the incident clearly appears urgent but type is uncertain:

- keep it active,
- show uncertainty,
- recommend generic safe escalation/operator review.

Do not discard.

---

## 26.3 Conflicting reports

Keep both evidence items.

Show conflict.

Request operator review if it materially affects response.

---

## 26.4 No available ambulance

Show:

- unavailable constraint,
- next feasible resource,
- effect on coverage,
- operator alert.

Do not fabricate an ambulance.

---

## 26.5 No suitable hospital

Show that no modeled candidate satisfies requirements.

Escalate to operator.

Do not silently choose an unsuitable hospital.

---

## 26.6 Route failure

If no valid route exists:

- show failure,
- try allowed alternatives,
- flag operator.

Do not draw an impossible route.

---

## 26.7 AI service failure

Core system should fail transparently.

If structured inputs are already available, deterministic operational parts should continue where possible.

The product must never create a fake AI answer to hide an outage.

---

# 27. HUMAN OVERRIDE

The operator should be able to override an AI recommendation.

When overridden:

- retain original recommendation,
- record chosen action,
- continue tracking the selected plan.

The system may warn if the choice violates a modeled constraint, but it must not pretend the human chose the AI plan.

---

# 28. EXPLAINABILITY FORMAT

Keep explanations operational.

Good:

> Ambulance A2 recommended because its ETA is 5:40 and dispatching A1 would reduce Zone C coverage below the target. A4 is repositioned to preserve coverage.

Bad:

> The advanced AI neural architecture holistically analyzed all smart-city parameters.

Avoid marketing language inside operational explanations.

---

# 29. CORE “WOW” MOMENTS THE PRODUCT SHOULD ENABLE

The demo should ideally contain several of these, but reliability is more important than quantity.

1. Natural Egyptian Arabic emergency report becomes a structured incident.
2. Incident appears immediately on the live map.
3. Sending the “obvious nearest” resources creates a visible coverage problem.
4. System simulates alternatives and recommends a better coordinated plan.
5. Human approves.
6. Emergency corridor appears.
7. Driver alert region activates.
8. Route changes live when a road becomes unavailable.
9. Hospital recommendation changes based on modeled capacity/capability.
10. Hospital receives a pre-alert before arrival.
11. Operator asks “why?” and gets an evidence-based operational explanation.

---

# 30. MVP COMPLETION DEFINITION

The MVP is not complete because screens exist.

It is complete only when one incident can go through a coherent end-to-end workflow.

Minimum closed loop:

1. Input emergency.
2. Create incident immediately.
3. Interpret evidence.
4. Recommend responders.
5. Show coverage impact.
6. Human approves.
7. Produce route.
8. Activate simulated corridor.
9. Show simulated public alert.
10. Select hospital when transport applies.
11. Send simulated hospital pre-alert.
12. Trigger one meaningful replan.
13. Show updated explanation.
14. Close/log incident.

If this works reliably, the core is done.

---

# 31. FEATURE PRIORITY

## P0 — Must work before anything else
- incident intake
- immediate incident activation
- incident model/state
- live operator map
- responder availability
- operator manual correction of material incident facts
- dynamic route
- response plan
- human approval

## P1 — Core differentiators
- coverage optimizer
- response-plan simulation
- minimal multi-incident resource contention awareness
- hospital selection
- hospital pre-alert
- corridor
- replanning
- explainability/confidence
- data freshness/staleness awareness

## P2 — Important polish
- report fusion
- driver alert visualization
- timeline
- stronger evidence display
- benchmark dashboard

## P3 — Bonus
- Social Media Intelligence

Do not start P3 while P0/P1 is unstable.

---

# 32. OUT-OF-SCOPE LIST — HARD BOUNDARY

Unless product owner explicitly changes this plan:

- predictive accidents
- predictive crime
- flood prediction
- earthquake prediction
- drone control
- IoT hardware network
- blockchain
- facial recognition
- license-plate surveillance
- generic public chatbot
- automatic diagnosis
- autonomous real-world dispatch
- live Egyptian government integration claims
- whole-Egypt deployment
- every emergency type
- 3D city
- AR/VR
- citizen social scoring
- insurance
- payments
- donations
- emergency supply blockchain
- police suspect tracking

---

# 33. GITHUB RECONNAISSANCE & REUSE POLICY

## Rule

**Before implementing any non-trivial subsystem, the assigned developer/AI agent must first search public repositories and technical references for existing implementations that solve the same subproblem.**

Goal:

- avoid reinventing solved infrastructure,
- learn proven patterns,
- reuse understood code or patterns when technically useful and appropriate,
- accelerate hackathon development,
- compare architecture/algorithms,
- identify edge cases.

---

## 33.1 Search before building

Search specifically for the subsystem being built.

Examples:

### Incident / crisis platform
Search:
- `AI emergency response incident dispatch`
- `crisis map incident triage dispatch`
- `emergency operations dashboard`

### Emergency routing
Search:
- `ambulance routing traffic emergency`
- `emergency route optimization`
- `ambulance dispatch OpenStreetMap`
- `dynamic emergency routing`

### Hospital selection
Search:
- `ambulance hospital selection capacity`
- `emergency hospital routing optimization`

### Coverage
Search:
- `ambulance coverage relocation optimization`
- `EMS station coverage optimization`

### Multi-casualty
Search:
- `mass casualty dispatch simulation`
- `multi casualty ambulance routing`

### Public alerts
Search:
- `emergency vehicle geofenced alerts`
- `emergency corridor alert`

---

## 33.2 Verified reference repositories found during product research

These are **reference candidates**, not mandated dependencies.

### Emergency Routes
GitHub: `JorgeAcin/emergency-routes`

Useful to inspect for:
- route optimization,
- road restrictions,
- multi-casualty concepts,
- audio triage,
- evaluation structure.

### ResQRoute
GitHub: `Tasnim-Saidi/ResQRoute`

Useful to inspect for:
- hospital scoring,
- real-time emergency mobility,
- routing/hospital coordination,
- closed-loop decision concepts.

### ResQPath
GitHub: `ashwinnm13/ResQPath`

Useful to inspect for:
- nearest-resource querying,
- hospital ranking,
- route integration,
- dispatch transaction flow.

### CrisisMap
GitHub: `assaampuhel/CrisisMap`

Useful to inspect for:
- incident triage,
- rescue-team dispatch,
- live incident map,
- emergency-response workflow.

### Ambulance Routing and Dispatch System
GitHub: `nati-s-g/Ambulance-Routing-and-Dispatch-System`

Useful to inspect for:
- emergency dispatch,
- graph-based routing,
- traffic-weighted route concepts,
- operational visualization.

### GoldenRoute
GitHub: `LithkeshBalajiB/goldenroute`

Useful to inspect for:
- hospital availability/specialty ranking,
- emergency routing,
- ambulance-to-hospital decision flow.

---

## 33.3 Reuse rules

Before copying/reusing code:

1. Understand the code.
2. Verify it matches our product requirements.
3. Remove assumptions tied to another city/domain.
4. Write tests around reused critical behavior.
5. Never copy secrets or API keys.
6. Never inherit product scope from the repository.
7. Never force our design to match a repo simply because code already exists.
8. Never paste a large unknown codebase into the project without review.

Repository reconnaissance should prioritize technical usefulness, correctness, and product fit. Do not let licensing research slow down ordinary reference/reuse reconnaissance; avoid blindly copying large unfamiliar codebases without understanding and adapting them.

---

## 33.4 AI agent rule

An AI coding agent must report:

> **Repo reconnaissance performed:** [yes/no]  
> **Relevant references:** [repos]  
> **What was reused:** [if any]  
> **Why it fits our Master Plan:** [short explanation]

If no suitable repository exists, proceed with implementation.

---

# 34. RESEARCH BASIS USED TO LOCK PRODUCT LOGIC

These sources influenced product behavior and feasibility assumptions.

## WHO — Prehospital Emergency Care Operational Guidance (2025)
Used to ground:
- dispatch-centre importance,
- matching emergency resources to patient needs,
- continuing structured emergency workflow.

## WHO — Mass Casualty Management
Used to ground:
- road crashes as legitimate mass-casualty scenarios,
- resource allocation as a core emergency challenge.

## FHWA — Emergency Vehicle / Signal Preemption Guidance
Used to ground:
- emergency traffic-signal priority,
- corridor/preemption concept,
- response-time benefit rationale.

## NHS England — Emergency Department / Ambulance Pre-alert
Used to ground:
- hospital pre-alert concept.

## Egypt Ambulance Authority public modernization announcements
Used to ground:
- smart fleet control,
- real-time communication between control rooms and ambulances,
- relevance of an intelligent coordination layer rather than a basic tracking app.

## TomTom Cairo Traffic Index 2025
Used to ground:
- Cairo congestion as a real operational factor.

---

# 35. PRODUCT CLAIMS WE MAY MAKE

Safe high-level claims:

- SirenGrid coordinates an emergency response workflow.
- It evaluates routes and network coverage.
- It can simulate external traffic/hospital/public-alert integrations.
- It keeps humans in control of critical decisions.
- It can compare response plans.
- It can replan when conditions change.
- It uses multimodal incident information.

---

# 36. PRODUCT CLAIMS WE MUST NOT MAKE WITHOUT EVIDENCE

Do not claim:

- “reduces deaths by X%,”
- “cuts Cairo ambulance response time by X%,”
- “connected to Egyptian Ambulance Authority,”
- “controls Cairo traffic lights,”
- “connected to all hospitals,”
- “alerts every driver in Cairo,”
- “predicts accidents,”
- “official government system,”
- “medical-grade certified,”
- “100% accurate,”
- “zero hallucinations,”
- “real-time live traffic” unless a real provider is actually integrated,
- “real hospital capacity” unless actually sourced live.

---

# 37. DEMO DATA RULES

Demo data may be synthetic/simulated, but must be internally coherent.

Examples:

- ambulance locations,
- fire-unit availability,
- hospital capacity,
- road congestion levels,
- patient counts.

If shown to judges, be able to say:

> “Operational resource/capacity values are simulated for the prototype; the routing and decision logic is real.”

This is acceptable and more credible than pretending.

---

# 38. DEMO SCENARIO DESIGN RULES

A good final scenario should:

- begin with one clear incident,
- use natural Egyptian Arabic,
- require more than one responder/resource,
- create a meaningful traffic constraint,
- create a coverage trade-off,
- need hospital coordination,
- include a visible route/corridor,
- allow a material mid-response change,
- end with a measurable improvement or clearly better plan.

Avoid a scenario that requires long explanation before the system becomes useful.

---

# 39. AI BEHAVIOR SPECIFICATION

## AI is allowed to
- summarize evidence,
- extract structured fields,
- identify missing information,
- correlate reports,
- call approved tools/functions,
- compare tool outputs,
- explain recommendations,
- translate/operator-friendly paraphrase,
- ask for clarification.

## AI is not allowed to
- manufacture unavailable operational data,
- invent hospital capacity,
- invent responder locations,
- invent casualties,
- invent successful external actions,
- override human approval,
- silently modify constraints,
- execute a new feature not described here,
- answer product ambiguity by “being creative.”

---

# 40. TOOL / FUNCTION BEHAVIOR RULE

Where the system has a deterministic tool for a value, the AI should use the tool rather than guess.

Examples:

- route → route calculation logic
- ETA → route/travel calculation
- coverage → coverage calculation
- hospital ranking → hospital-scoring logic
- resource availability → resource state
- incident history → event data

The natural-language AI should orchestrate/explain these values, not fabricate them.

---

# 41. CLARIFICATION PROTOCOL FOR CODING AGENTS

The following require human clarification if not already defined:

- new user role,
- new emergency type with new behavior,
- new critical action,
- change in approval policy,
- change in geographic MVP,
- change in feature priority,
- change in real/simulated status,
- change in benchmark definition,
- new sensitive data collection,
- removal of a P0/P1 feature,
- addition of a major bonus feature,
- final demo scenario if needed for product-specific behavior.

The agent may choose low-level implementation details without asking if they do not change product behavior.

---

# 42. WHAT DOES NOT REQUIRE PRODUCT CLARIFICATION

The responsible technical team may decide:

- file organization,
- naming conventions,
- framework/library choice,
- database,
- hosting,
- model/provider,
- caching,
- API style,
- component hierarchy,
- test framework,
- internal data structures,

as long as the resulting behavior complies with this Master Plan.

---

# 43. CHANGE CONTROL

Any future product change should be recorded explicitly.

Recommended format:

## Decision ID
`PD-###`

## Date
YYYY-MM-DD

## Change
What changed.

## Reason
Why.

## Impact
Features/flows affected.

## Approved by
Human product owner.

Then update this Master Plan if the change becomes permanent.

---

# 44. IMPLEMENTATION SEQUENCE — PRODUCT ORDER ONLY

This is not a technical architecture plan.

## Stage 1 — Skeleton operational loop
- incident input
- incident state
- resources
- map
- response plan
- approval
- route

## Stage 2 — Differentiation
- coverage
- plan simulation
- hospital selection
- pre-alert
- corridor

## Stage 3 — Intelligence quality
- multimodal evidence
- report fusion
- confidence/explainability
- dynamic replanning

## Stage 4 — Demo strength
- driver alerts
- timeline
- benchmark/evaluation
- polished end-to-end scenario

## Stage 5 — Bonus only
- Social Media Intelligence

---

# 45. DEFINITION OF “DONE” FOR EACH FEATURE

A feature is not done because:

- UI exists,
- button exists,
- mocked JSON exists,
- AI generated text describing the feature.

A feature is done when:

1. Input is defined.
2. Behavior executes.
3. Output is visible/consumable.
4. Failure behavior exists.
5. Important edge cases are handled.
6. It integrates with the golden flow.
7. It has a test/demo path.
8. It does not violate scope or safety boundaries.

---

# 46. REQUIRED TEST SCENARIOS

At minimum, test the following product behaviors.

## T01 — One urgent report
One caller → incident activates immediately.

## T02 — Duplicate caller
Second caller describes same event → report merges.

## T03 — Conflicting details
Two reports disagree → conflict visible.

## T04 — Blocked road
Current route becomes unavailable → replan.

## T05 — Coverage trade-off
Nearest responders create coverage gap → alternative plan recommended.

## T06 — Hospital overload
Nearest hospital unavailable/full in simulation → another hospital recommended.

## T07 — Human rejection
Operator rejects AI recommendation → alternative/manual path continues.

## T08 — Missing location
System cannot route and clearly requests location.

## T09 — Resource unavailable
Assigned responder becomes unavailable → replan.

## T10 — Public alert
Alert only affects forward corridor.

## T11 — Hospital pre-alert
Selected hospital receives only known data.

## T12 — AI failure
System does not fabricate output.

## T13 — Operator correction
AI extracts a wrong material value → operator corrects it → affected plan recalculates and history preserves both values.

## T14 — Stale operational data
Hospital/traffic/resource input becomes stale → system marks it clearly and does not silently present it as current.

## T15 — Competing incident
A second serious incident consumes/needs shared resources → availability and coverage recalculate; unresolved priority conflict escalates to operator.

---

# 47. REFERENCE USER STORY — MULTI-CASUALTY CRASH

This is an example, not the final locked demo.

### 00:00
An existing emergency call reaches the control room. Caller:
> “في حادثة كبيرة على طريق النصر، أتوبيس خبط في عربيتين وفي ناس جوه العربيات.”

### 00:05
System:
- creates incident,
- marks high/critical severity,
- captures location,
- identifies possible trapped occupants,
- begins response planning.

### 00:10
Operator sees:
- incident on map,
- nearest responders,
- initial confidence,
- known/unknown information.

### 00:15
System compares plans.

Plan A:
- fastest immediate resources,
- but Zone C coverage falls significantly.

Plan B:
- slightly different responder combination,
- preserves coverage,
- comparable incident ETA.

System recommends Plan B.

### 00:20
Operator approves.

### 00:25
Routes activate.
Emergency corridor simulated.
Forward driver alert appears.

### 00:40
A second report reaches the control room through an existing operational channel with image evidence and more casualty information.
System merges it and updates severity.

### 00:50
One road becomes unavailable.
System replans.

### 01:00
Casualties require hospital transport.
Hospitals are ranked by ETA + modeled capacity/capability.
Hospital B selected.

### 01:10
Hospital B receives pre-alert.

### 01:20
Operator asks:
> “Why did the route change?”

System explains the closed segment and old/new ETA.

### 01:30
Demo ends with operational view and preserved coverage.

---

# 48. REFERENCE USER STORY — BUILDING FIRE

Alternative example.

An existing emergency call reaches the control room. Caller reports:
> “في حريق في عمارة ومفيش ناس عارفة تنزل.”

System:
- activates immediately,
- routes fire/rescue and ambulance resources,
- models traffic corridor,
- checks coverage,
- receives a later report that more people are trapped,
- adjusts plan,
- routes medical transport,
- pre-alerts hospital.

This scenario remains valid but is not currently preferred over the multi-casualty crash candidate.

---

# 49. COMMUNICATION STYLE OF THE PRODUCT

Operator-facing language should be:

- concise,
- operational,
- clear,
- non-marketing,
- uncertainty-aware.

Good:
> Two ambulances recommended. A third nearby ambulance is retained to preserve Zone C coverage.

Bad:
> Our revolutionary AI has intelligently revolutionized resource orchestration.

---

# 50. PRIVACY / SENSITIVE INFORMATION PRINCIPLES

For the prototype:

- minimize personal data,
- do not require names to demonstrate routing,
- avoid exposing patient details in public alerts,
- keep hospital alerts limited to necessary operational information,
- avoid facial recognition,
- avoid scraping private social-media content.

---

# 51. SOCIAL MEDIA INTELLIGENCE — IMPLEMENTATION GATE

Do not start the bonus until all are true:

- P0 complete,
- P1 complete or stable,
- main golden flow works,
- one replan works,
- hospital pre-alert works,
- no critical demo blocker,
- core demo can be run repeatedly.

Then product owner may approve starting Social Media Intelligence.

---

# 52. “NO SURPRISES” RULE FOR AI AGENTS

Before completing a major task, an AI agent should report:

### Implemented
What exact Master Plan requirements were implemented.

### Not implemented
What requirements were intentionally left for later.

### Assumptions
Only low-level technical assumptions, not product assumptions.

### Deviations
Any deviation requires explicit human approval.

### Tests
How behavior was verified.

This prevents silent scope drift.

---

# 53. PRODUCT REVIEW CHECKLIST

Before calling the whole system demo-ready:

- [ ] Single urgent report activates incident.
- [ ] Natural Egyptian Arabic input works sufficiently for demo.
- [ ] Location is captured/represented.
- [ ] Incident appears on operational map.
- [ ] Multiple reports can merge.
- [ ] Confidence/evidence visible.
- [ ] Resource plan generated.
- [ ] Coverage impact shown.
- [ ] Alternative plans can be compared.
- [ ] Operator approval exists.
- [ ] Traffic-aware route shown.
- [ ] Emergency corridor shown as simulated integration.
- [ ] Clear-the-way alert shown as simulated integration.
- [ ] Hospital selection works.
- [ ] Hospital pre-alert works.
- [ ] Material condition change triggers replan.
- [ ] AI explains why plan changed.
- [ ] Incident timeline records major events.
- [ ] Demo data is labeled appropriately.
- [ ] No fake live-government integration claim.
- [ ] Benchmark/baseline exists if time permits.
- [ ] Social Media Intelligence is only added after core stability.

---

# 54. FINAL PRODUCT BOUNDARY

If a feature does not directly improve one of these, it probably does not belong in the MVP:

1. **Understand the emergency**
2. **Activate response quickly**
3. **Coordinate the right resources**
4. **Move them through the city efficiently**
5. **Preserve emergency coverage elsewhere**
6. **Choose and prepare the right hospital**
7. **Adapt when conditions change**
8. **Keep the human operator informed and in control**
9. **Preserve data provenance and freshness**
10. **Remain aware of competing active demand for shared resources**

This is the product.

---

# 55. FINAL LOCKED SUMMARY FOR ANY AI READING ONLY ONE SECTION

**Build SirenGrid / City Emergency AI as a focused emergency-response coordination system for Nasr City, Cairo.**

SirenGrid is a control-room-side system, not a citizen reporting application. Citizens continue using normal existing emergency channels, such as calling the relevant emergency service. SirenGrid receives emergency-call audio/transcripts, operator-entered information, available location metadata, and evidence forwarded through existing authorized operational channels. A single credible urgent report received by the control room is enough to create and activate an incident; the system must never wait for multiple independent reports before beginning response planning.

Additional reports can later merge into the incident, update confidence/severity, or add evidence.

The primary user is the emergency control-room dispatcher. The AI interprets evidence and coordinates approved calculation/simulation tools, but does not independently execute critical real-world actions. The dispatcher approves response plans.

The system must coordinate ambulances and fire/rescue resources, calculate traffic-aware routes, simulate an emergency-priority corridor, simulate location-relevant clear-the-way alerts, measure the effect of dispatch on remaining city emergency coverage, compare alternative response plans, select a suitable hospital using ETA plus modeled capacity/capability, pre-alert the receiving hospital, and continuously replan when conditions change. The operator must be able to correct material AI-extracted incident facts, critical operational data must expose provenance/freshness, and resource planning must have minimal awareness of competing active incidents so shared responders are not treated as magically available.

The MVP geography is Nasr City. The initial working/demo corridor is Rabaa → Tayaran → Abbas El Akkad → Makram Ebeid → El Nasr Road. Product vision may later expand to Greater Cairo.

The final demo scenario is not locked. The current preferred reference candidate is a multi-casualty urban road incident; a major building fire remains an alternative.

Physical traffic-light control, government dispatch systems, hospital live-capacity systems, and citywide public alerts are simulated integrations unless real authorized connections exist.

Social Media Intelligence is a bonus feature and may only be started after the core end-to-end workflow is stable.

Do not add predictive accidents, blockchain, drones, IoT hardware, generic chatbot behavior, autonomous emergency dispatch, 3D city visualization, or other new scope without explicit human approval.

Before implementing any non-trivial subsystem, search relevant public GitHub repositories and technical references for reusable or proven implementations. Reuse only when the implementation is understood and clearly fits SirenGrid. Never let an existing repository change the product scope.

If this Master Plan does not define a product decision that affects user-visible behavior, safety, scope, authority, real-vs-simulated status, or feature meaning, **ask the human developer instead of inventing an answer.**

---

# 56.1 v1.1 CHANGE SUMMARY

Changes from v1.0:

1. Product renamed from **ResQGrid** to **SirenGrid**.
2. Added **F17 — Operator Manual Correction & Human Data Control**.
3. Added **F18 — Data Freshness / Staleness Awareness**.
4. Added **F19 — Minimal Multi-Incident Awareness & Resource Contention**.
5. Updated priorities, operator information requirements, completion criteria, tests, and final locked summary to reflect these product-safety requirements.

No tech stack or implementation architecture was selected by this revision.

---

# 56.2 v1.2 CHANGE SUMMARY

Changes from v1.1:

1. Locked SirenGrid as a **control-room-side system**, not a citizen-facing reporting application.
2. Clarified that citizens continue using existing emergency channels, such as normal emergency calls.
3. Updated the Report entity, Golden Flow, multimodal intake feature, reference demo stories, and final locked summary to reflect control-room-side intake.
4. Clarified that caller audio/transcripts, operator-entered information, location metadata, and forwarded evidence enter through existing operational channels.
5. Preserved the immediate-response rule: one credible urgent report received by the control room is sufficient to begin response planning.
6. Preserved Social Media Intelligence as a separate bonus source of unverified external signals, not a citizen reporting workflow.
7. Aligned repository-reuse wording with the current project workflow: technical usefulness, understanding, and product fit are the primary reconnaissance criteria.

No tech stack or implementation architecture was selected by this revision.

# 56. END STATE

When the core system is complete, a judge should be able to watch one emergency move through this story:

> **Report → understand → activate → coordinate → compare → approve → route → clear corridor → preserve coverage → prepare hospital → replan → explain**

That closed loop is the center of SirenGrid.

Everything else is secondary.

---

## Document Version
**v1.2 — Locked Product Master Plan**

## Next document
A separate architecture/technical plan should later translate this behavior into software architecture and a tech stack without changing the product contract defined here.
