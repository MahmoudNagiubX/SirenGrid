/**
 * TEMPORARY frontend mock data.
 *
 * Every value here is coherent demo/prototype data that stands in for the SirenGrid backend
 * API until the dedicated backend-integration phase. It is deliberately isolated in this one
 * module so presentation components never hardcode operational values and this file can be
 * swapped for real API responses without touching the UI.
 *
 * The frontend only DISPLAYS these numbers. It must not compute ETA, routing, plan ranking,
 * coverage, hospital suitability, replan materiality or confidence — those belong to the backend.
 */
import type { ConfidenceLevel, Severity, Tone } from '../components';

/* ---- Operational states of the single Operations workspace -------------------------------- */

export type OpsState = 'idle' | 'incident' | 'plan' | 'active' | 'replan' | 'hospital' | 'coverage';
export type MapView = 'city' | 'incident' | 'hospital';
export type DecisionTab = 'overview' | 'plan' | 'hospital' | 'evidence' | 'history';

export const DEC_TABS: [DecisionTab, string][] = [
  ['overview', 'Overview'],
  ['plan', 'Plan'],
  ['hospital', 'Hospital'],
  ['evidence', 'Evidence'],
  ['history', 'History'],
];
export type RouteMode = 'plan' | 'replan' | 'none';

export interface StateMeta {
  map: { view: MapView; route: RouteMode; overlays: Partial<Record<OverlayKey, boolean>> };
  tab: DecisionTab;
}

export type OverlayKey = 'traffic' | 'coverage' | 'corridor' | 'closure';

export const STATE_META: Record<OpsState, StateMeta> = {
  idle: { map: { view: 'city', route: 'plan', overlays: { traffic: true } }, tab: 'overview' },
  incident: { map: { view: 'incident', route: 'plan', overlays: { traffic: true } }, tab: 'overview' },
  plan: { map: { view: 'incident', route: 'plan', overlays: { traffic: true, coverage: true } }, tab: 'plan' },
  active: { map: { view: 'incident', route: 'plan', overlays: { traffic: true, corridor: true } }, tab: 'overview' },
  replan: { map: { view: 'incident', route: 'replan', overlays: { traffic: true, closure: true } }, tab: 'plan' },
  hospital: { map: { view: 'hospital', route: 'plan', overlays: { traffic: true } }, tab: 'hospital' },
  coverage: { map: { view: 'city', route: 'none', overlays: { traffic: false, coverage: true } }, tab: 'overview' },
};

export const STATES: [OpsState, string, string][] = [
  ['idle', 'Overview', 'layout-grid'],
  ['incident', 'Incident Focus', 'siren'],
  ['plan', 'Plan Review', 'brain'],
  ['active', 'Active Response', 'ambulance'],
  ['replan', 'Replan', 'refresh-cw'],
  ['hospital', 'Hospital', 'hospital'],
  ['coverage', 'Coverage', 'shield-check'],
];

export type TopNav = 'landing' | 'operations' | 'resources' | 'benchmark' | 'demo';
export const TOP_NAV: [Exclude<TopNav, 'demo'>, string, string][] = [
  ['landing', 'Landing', 'sparkles'],
  ['operations', 'Operations', 'map'],
  ['resources', 'Resources', 'truck'],
  ['benchmark', 'Benchmark', 'gauge'],
];

/* ---- Status strip KPIs ------------------------------------------------------------------- */

export const STATUS_KPIS: [string, string][] = [
  ['4', 'open incidents'],
  ['94%', 'city coverage'],
  ['6.4 min', 'avg ETA'],
];

export const OPERATOR = { name: 'M. Nagiub', shift: 'Shift 20:00 – 04:00' };

/* ---- Incident rail --------------------------------------------------------------------- */

export interface Incident {
  id: string;
  title: string;
  loc: string;
  ar: string;
  sev: Severity;
  state: string;
  conf: ConfidenceLevel;
  t: string;
  icon: string;
}

export const INCIDENTS: Incident[] = [
  { id: 'INC-2418', title: 'Road Traffic Accident', loc: 'Abbas El Akkad × Makram Ebeid', ar: 'حادث مروري', sev: 'critical', state: 'Awaiting approval', conf: 'high', t: '20:58', icon: 'triangle-alert' },
  { id: 'INC-2417', title: 'Structure Fire', loc: 'Makram Ebeid St.', ar: 'حريق مبنى', sev: 'high', state: 'Response active', conf: 'medium', t: '20:41', icon: 'flame' },
  { id: 'INC-2415', title: 'Minor Collision', loc: 'El Nasr Rd.', ar: 'تصادم بسيط', sev: 'moderate', state: 'On scene', conf: 'high', t: '20:12', icon: 'car' },
  { id: 'INC-2412', title: 'Medical — Chest Pain', loc: 'Tayaran St.', ar: 'حالة طبية', sev: 'low', state: 'Transport', conf: 'medium', t: '19:47', icon: 'heart-pulse' },
];

export const RAIL_RESOURCES: [string, string][] = [
  ['Ambulances', '6 / 10'],
  ['Rescue · Fire', '3 / 4'],
  ['Reserve held', 'A5 · Zone C'],
];

/* ---- Focused incident (decision workspace header) ------------------------------------- */

export const FOCUS_INCIDENT = { title: 'Road Traffic Accident', id: 'INC-2418', t: '20:58', sev: 'critical' as Severity };

/* ---- History / timeline dock -------------------------------------------------------- */

export type ProvKind = 'ai' | 'operator' | 'responder' | 'source' | 'sim' | 'stale';

export const DOCK_EVENTS: [string, string, ProvKind][] = [
  ['21:07', 'Replan v3 approved', 'operator'],
  ['21:06', 'Closure — Abbas El Akkad eastbound', 'responder'],
  ['21:04', 'Hospital pre-alert — El Nozha', 'sim'],
  ['21:03', 'Plan B approved', 'operator'],
  ['20:58', 'Emergency call received', 'source'],
];

/* ---- Map: facilities, markers, legends ------------------------------------------------ */

export type MapTone = 'navy' | 'red' | 'slate' | 'blue';
/** [icon, label, tone, left%, top%] */
export type FacilityTuple = [string, string, MapTone, string, string];
/** [icon, label, sub, tone, left%, top%] */
export type MarkerTuple = [string, string, string, MapTone, string, string];

export const FACILITIES: Record<MapView, FacilityTuple[]> = {
  city: [
    ['hospital', 'El Nozha', 'navy', '63%', '15%'],
    ['hospital', 'Dar Al Fouad', 'navy', '52%', '84%'],
    ['hospital', 'Nasr Specialised', 'navy', '20%', '66%'],
    ['flame', 'Fire Stn. 4', 'red', '44%', '73%'],
    ['flame', 'Fire Stn. 1', 'red', '82%', '30%'],
    ['shield', 'Police · Nasr 2', 'slate', '74%', '52%'],
    ['shield', 'Police · Rabaa', 'slate', '14%', '18%'],
  ],
  incident: [
    ['hospital', 'El Nozha', 'navy', '72%', '13%'],
    ['flame', 'Fire Stn. 4', 'red', '30%', '80%'],
    ['shield', 'Police · Nasr 2', 'slate', '86%', '58%'],
  ],
  hospital: [
    ['hospital', 'El Nozha', 'navy', '36%', '12%'],
    ['hospital', 'Nasr Specialised', 'navy', '16%', '68%'],
    ['flame', 'Fire Stn. 4', 'red', '10%', '86%'],
  ],
};

export const MARKERS: Record<OpsState, MarkerTuple[]> = {
  idle: [
    ['triangle-alert', 'INC-2418', 'Critical · awaiting approval', 'red', '35%', '46%'],
    ['ambulance', 'A1', 'En route · 6:20', 'blue', '20%', '70%'],
    ['truck', 'F3', 'En route · 7:05', 'blue', '9%', '35%'],
    ['ambulance', 'A2', 'Available', 'blue', '77%', '62%'],
  ],
  incident: [
    ['triangle-alert', 'INC-2418', '2 lanes blocked', 'red', '39%', '30%'],
    ['ambulance', 'A1', 'Nearest · 6:20', 'blue', '12%', '76%'],
    ['truck', 'F3', '7:05', 'blue', '3%', '40%'],
  ],
  plan: [
    ['triangle-alert', 'INC-2418', 'Critical', 'red', '39%', '30%'],
    ['ambulance', 'A1', 'Plan B · 6:20', 'blue', '12%', '76%'],
    ['ambulance', 'A5', 'Reposition', 'blue', '80%', '66%'],
  ],
  active: [
    ['ambulance', 'A1', 'ETA 3:10 · 62 km/h', 'blue', '24%', '54%'],
    ['truck', 'F3', 'ETA 4:05', 'blue', '4%', '42%'],
    ['triangle-alert', 'INC-2418', 'On scene: 0', 'red', '39%', '30%'],
  ],
  replan: [
    ['octagon-x', 'Closure', 'Eastbound · 21:06', 'red', '22%', '27%'],
    ['ambulance', 'A1', 'Rerouting · 7:05', 'blue', '10%', '72%'],
    ['triangle-alert', 'INC-2418', 'Critical', 'red', '39%', '30%'],
  ],
  hospital: [
    ['hospital', 'El Nozha · selected', '8 min · trauma', 'navy', '40%', '10%'],
    ['triangle-alert', 'INC-2418', 'Transport pending', 'red', '16%', '30%'],
  ],
  coverage: [
    ['ambulance', 'A5', 'Reposition → Zone C', 'blue', '70%', '61%'],
    ['triangle-alert', 'INC-2418', 'Critical', 'red', '35%', '46%'],
  ],
};

export interface LegendItem {
  color: string;
  label: string;
  dot?: boolean;
}

export const LEGEND: Record<string, LegendItem[]> = {
  coverage: [
    { color: 'var(--map-coverage-fill)', label: 'Covered' },
    { color: 'var(--map-gap-line)', label: 'Coverage gap' },
    { color: 'var(--map-responder)', label: 'Unit', dot: true },
  ],
  replan: [
    { color: 'var(--map-route-primary)', label: 'New v3' },
    { color: 'var(--map-route-alt)', label: 'Previous v2' },
    { color: 'var(--color-critical)', label: 'Closure', dot: true },
  ],
  active: [
    { color: 'var(--map-route-primary)', label: 'Active route' },
  ],
  default: [
    { color: 'var(--map-route-primary)', label: 'Primary route' },
    { color: 'var(--map-route-alt)', label: 'Alternate' },
    { color: 'var(--map-incident)', label: 'Incident', dot: true },
  ],
};

/* ---- Decision workspace: plans, hospitals, evidence -------------------------------- */

export interface Plan {
  id: string;
  name: string;
  units: string;
  eta: string;
  cov: string;
  bad?: boolean;
  rec?: boolean;
}

export const PLANS: Plan[] = [
  { id: 'A', name: 'Plan A · Fastest', units: 'A1 + A2 + F3', eta: '5:40', cov: '81%', bad: true },
  { id: 'B', name: 'Plan B · Recommended', units: 'A1 + F3, reposition A5', eta: '6:20', cov: '94%', rec: true },
  { id: 'C', name: 'Plan C · Coverage first', units: 'A1 only, F3 reserve', eta: '7:50', cov: '96%' },
];

export const PLAN_COMPARE: [string, [string, string, string]][] = [
  ['Scene ETA', ['5:40', '6:20', '7:50']],
  ['Coverage', ['81%', '94%', '96%']],
];

export const REPLAN_ROUTES: [string, string, string, boolean][] = [
  ['Previous v2', '6:20', 'Abbas El Akkad', false],
  ['New v3', '7:05', 'El Nasr Rd.', true],
];

export interface Hospital {
  n: string;
  ar: string;
  eta: string;
  load: number;
  cap: string;
  rec?: boolean;
  stale?: boolean;
}

export const HOSPITALS: Hospital[] = [
  { n: 'El Nozha Hospital', ar: 'مستشفى النزهة', eta: '8 min', load: 62, cap: 'Trauma · ICU', rec: true },
  { n: 'Dar Al Fouad', ar: 'مستشفى دار الفؤاد', eta: '11 min', load: 48, cap: 'Trauma · Cardiac' },
  { n: 'Nasr Specialised', ar: 'النصر التخصصي', eta: '6 min', load: 96, cap: 'No trauma bay', stale: true },
];

export const COVERAGE_ZONES: [string, number, number][] = [
  ['Zone A · Rabaa', 96, 96],
  ['Zone B · Tayaran', 91, 90],
  ['Zone C · Makram Ebeid', 92, 78],
  ['Zone D · El Nasr', 93, 93],
];

export const ACTIVE_EXECUTED: [string, string][] = [
  ['Dispatch A1 + F3', '21:03'],
  ['Reposition A5 → Zone C', '21:03'],
  ['Corridor priority', '21:04'],
  ['Hospital pre-alert', '21:04'],
];

export const ACTIVE_UNITS: [string, string][] = [
  ['A1 · en route', '3:10'],
  ['F3 · en route', '4:05'],
  ['A5 · reserve Zone C', 'held'],
  ['A2 · available', '—'],
];

export const EVIDENCE_ITEMS: [string, string, ProvKind, string][] = [
  ['Call transcript', 'ar-EG · 42 s', 'source', 'phone'],
  ['Caller location', '±80 m', 'source', 'map-pin'],
  ['Scene image', '21:00', 'ai', 'image'],
  ['Responder report', 'F3 · 2 lanes blocked', 'responder', 'clipboard-list'],
];

export const EVIDENCE_TRANSCRIPT_AR = '«حادثة كبيرة عند عباس العقاد وفي حد مش عارف يطلع من العربية»';

export const HISTORY_EVENTS: [string, string, ProvKind][] = [
  ['21:07', 'Replan v3 approved', 'operator'],
  ['21:06', 'Closure — Abbas El Akkad eastbound', 'responder'],
  ['21:04', 'Hospital pre-alert — El Nozha', 'sim'],
  ['21:03', 'Plan B approved', 'operator'],
  ['21:00', 'Scene image attached', 'ai'],
  ['20:58', 'Emergency call received', 'source'],
];

/* ---- Resources view ---------------------------------------------------------------- */

export type UnitStatus = 'AVAILABLE' | 'RESERVED' | 'ASSIGNED' | 'EN_ROUTE' | 'ON_SCENE' | 'TRANSPORTING' | 'OUT_OF_SERVICE';

export interface Unit {
  id: string;
  type: 'Ambulance' | 'Rescue / Fire';
  status: UnitStatus;
  zone: string;
  base: string;
  cap: string;
  eta: string;
}

export const UNITS: Unit[] = [
  { id: 'A1', type: 'Ambulance', status: 'EN_ROUTE', zone: 'Zone A', base: 'Rabaa Station', cap: 'ALS · 2 crew', eta: '3:10' },
  { id: 'A2', type: 'Ambulance', status: 'AVAILABLE', zone: 'Zone C', base: 'Makram Ebeid Post', cap: 'ALS · 2 crew', eta: '—' },
  { id: 'A4', type: 'Ambulance', status: 'ASSIGNED', zone: 'Zone B', base: 'Tayaran Post', cap: 'BLS · 2 crew', eta: '—' },
  { id: 'A5', type: 'Ambulance', status: 'RESERVED', zone: 'Zone D', base: 'El Nasr Station', cap: 'ALS · 2 crew', eta: '—' },
  { id: 'A7', type: 'Ambulance', status: 'TRANSPORTING', zone: 'Zone E', base: 'Al Nozha Post', cap: 'BLS · 2 crew', eta: '5:40' },
  { id: 'F3', type: 'Rescue / Fire', status: 'EN_ROUTE', zone: 'Zone B', base: 'Nasr City Civil Defense', cap: 'Extrication · 6 crew', eta: '4:05' },
  { id: 'F5', type: 'Rescue / Fire', status: 'AVAILABLE', zone: 'Zone D', base: 'El Nasr Depot', cap: 'Extrication · 6 crew', eta: '—' },
  { id: 'F6', type: 'Rescue / Fire', status: 'OUT_OF_SERVICE', zone: 'Zone A', base: 'Rabaa Station', cap: 'Maintenance', eta: '—' },
];

export const STATUS_TONE: Record<UnitStatus, Tone> = {
  AVAILABLE: 'confirmed',
  RESERVED: 'info',
  ASSIGNED: 'info',
  EN_ROUTE: 'info',
  ON_SCENE: 'info',
  TRANSPORTING: 'info',
  OUT_OF_SERVICE: 'neutral',
};

export const RESOURCE_KPIS: [string, string, string, string | undefined][] = [
  ['ambulance', 'Ambulances', '6 / 10', 'available / fleet'],
  ['truck', 'Rescue & Fire', '2 / 4', '1 out of service'],
  ['hospital', 'Hospitals Ready', '5 / 7', undefined],
  ['radio-tower', 'Comms Health', 'Nominal', 'Simulated gateway'],
];

export const HOSPITAL_READINESS: [string, string][] = [
  ['El Nozha', 'Ready · 62% load'],
  ['Dar Al Fouad', 'Ready · 48% load'],
  ['Nasr Specialised', 'At capacity · 96%'],
  ['Al Salam Intl.', 'Ready · 55% load'],
];

/* ---- Timeline (full audit) view -------------------------------------------------- */

export const AUDIT_EVENTS: [string, string, ProvKind, string][] = [
  ['21:07', 'Replan v3 approved by operator', 'operator', 'Route switched to El Nasr Rd. after closure.'],
  ['21:06', 'Road closure reported — Makram Ebeid northbound', 'responder', 'Reported by Rescue F3 on approach.'],
  ['21:04', 'Hospital pre-alert sent — El Nozha', 'sim', 'Simulated integration; acknowledgement generated by gateway.'],
  ['21:03', 'Plan B approved — dispatch A1 + F3, reposition A5', 'operator', 'Coverage preserved at 94%.'],
  ['21:00', 'Scene image attached', 'ai', 'Visual interpretation: multi-vehicle, one vehicle on side.'],
  ['20:59', 'Incident activated on single credible report', 'operator', 'No second report required.'],
  ['20:58', 'Emergency call received (voice, ar-EG)', 'source', 'Caller reports trapped occupant.'],
];

export const AUDIT_EVIDENCE: [string, string, ProvKind][] = [
  ['Emergency call transcript', 'ar-EG · 42 s · high clarity', 'source'],
  ['Caller location metadata', '±80 m accuracy', 'source'],
  ['Scene image', 'Forwarded via operational channel', 'ai'],
  ['Responder road report', 'F3 · 2 lanes blocked', 'responder'],
];

/* ---- Demo / scenario controls -------------------------------------------------- */

export const DEMO_SCENARIOS: [string, string, boolean][] = [
  ['Multi-casualty road crash', 'Abbas El Akkad × Tayaran · 2 units + rescue', true],
  ['Major building fire', 'Makram Ebeid · rescue-led response', false],
];

export interface InjectRow {
  key: string;
  icon: string;
  tone: 'red' | 'navy' | 'blue';
  title: string;
  sub: string;
  action: string;
}

export const DEMO_INJECTS: InjectRow[] = [
  { key: 'close', icon: 'octagon-x', tone: 'red', title: 'Close road segment', sub: 'Makram Ebeid northbound — triggers route replan', action: 'Trigger' },
  { key: 'second', icon: 'siren', tone: 'red', title: 'Add second incident', sub: 'Structure fire, Zone C — creates resource contention', action: 'Trigger' },
  { key: 'unit', icon: 'ambulance', tone: 'navy', title: 'Mark unit unavailable', sub: 'Ambulance A2 → OUT_OF_SERVICE', action: 'Apply' },
  { key: 'hosp', icon: 'hospital', tone: 'navy', title: 'Change hospital status', sub: 'Nasr Specialised → at capacity', action: 'Apply' },
  { key: 'ev', icon: 'file-text', tone: 'blue', title: 'Inject new evidence', sub: 'Second caller reports 3 vehicles involved', action: 'Inject' },
  { key: 'traffic', icon: 'gauge', tone: 'blue', title: 'Congestion spike', sub: 'El Nasr Rd. +180% travel time', action: 'Trigger' },
];

export const DEMO_DATA_REALITY: [string, string][] = [
  ['Road network', 'Real · OSM derived'],
  ['Population coverage', 'Real derived · WorldPop'],
  ['Hospital registry', 'Real locations'],
  ['Hospital load', 'Simulated'],
  ['Unit positions', 'Simulated'],
  ['Traffic', 'Simulated in prototype'],
];

/* ---- Benchmark view --------------------------------------------------------- */

export const BENCHMARK_METRICS: [string, string, string, string][] = [
  ['Time from report to structured incident', 'Manual entry', 'Automated interpretation', 'Awaiting measured benchmark'],
  ['Time to first response recommendation', 'Operator judgement', 'Plan comparison', 'Awaiting measured benchmark'],
  ['Coverage-aware dispatch', 'Not considered', 'Modelled per plan', 'Structural difference'],
  ['Hospital selection basis', 'Nearest suitable', 'ETA + capability + load', 'Structural difference'],
  ['Replanning on disruption', 'Manual re-decision', 'Event-driven re-evaluation', 'Awaiting measured benchmark'],
];

export const BENCHMARK_METRICS_PLANNED: string[] = [
  'Report → structured incident',
  'Report → first recommendation',
  'Responder ETA vs baseline',
  'Coverage before / after dispatch',
  'Worst-zone response time',
  'Replanning latency',
];

/* ---- Landing ------------------------------------------------------------- */

export const LANDING_STEPS: [string, string][] = [
  ['Understand', 'radar'],
  ['Coordinate', 'route'],
  ['Approve', 'user-round-check'],
  ['Adapt', 'refresh-cw'],
];

export const LANDING_INCIDENT_STATS: [string, string][] = [
  ['6:20', 'scene ETA'],
  ['94%', 'city coverage'],
  ['El Nozha', 'destination'],
];
