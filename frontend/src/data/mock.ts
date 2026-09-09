/**
 * Presentation-only configuration retained from the approved design source.
 *
 * Operational facts deliberately do not live here. Incidents, resources, routes,
 * plans, hospitals, benchmark results, simulation state, and social signals are
 * loaded from the backend through OperationsContext.
 */
export type OpsState = 'idle' | 'incident' | 'plan' | 'active' | 'replan' | 'hospital' | 'coverage';
export type MapView = 'city' | 'incident' | 'hospital';
export type DecisionTab = 'overview' | 'plan' | 'hospital' | 'evidence' | 'history';
export type RouteMode = 'plan' | 'replan' | 'none';
export type OverlayKey = 'traffic' | 'coverage' | 'corridor' | 'closure';
export type MapTone = 'navy' | 'red' | 'slate' | 'blue';
export type ProvKind = 'ai' | 'operator' | 'responder' | 'source' | 'sim' | 'stale';

export const DEC_TABS: [DecisionTab, string][] = [
  ['overview', 'Overview'],
  ['plan', 'Plan'],
  ['hospital', 'Hospital'],
  ['evidence', 'Evidence'],
  ['history', 'History'],
];

export interface StateMeta {
  map: { view: MapView; route: RouteMode; overlays: Partial<Record<OverlayKey, boolean>> };
  tab: DecisionTab;
}

export const STATE_META: Record<OpsState, StateMeta> = {
  idle: { map: { view: 'city', route: 'none', overlays: { traffic: true } }, tab: 'overview' },
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

export interface LegendItem { color: string; label: string; dot?: boolean }
export const LEGEND: Record<string, LegendItem[]> = {
  coverage: [
    { color: 'var(--map-coverage-fill)', label: 'Covered' },
    { color: 'var(--map-gap-line)', label: 'Coverage gap' },
    { color: 'var(--map-responder)', label: 'Unit', dot: true },
  ],
  replan: [
    { color: 'var(--map-route-primary)', label: 'Proposed route' },
    { color: 'var(--map-route-alt)', label: 'Active route' },
    { color: 'var(--color-critical)', label: 'Closure', dot: true },
  ],
  active: [
    { color: 'var(--map-corridor)', label: 'Corridor' },
    { color: 'var(--map-route-primary)', label: 'Active route' },
    { color: 'var(--map-congestion-high)', label: 'Traffic' },
  ],
  default: [
    { color: 'var(--map-route-primary)', label: 'Backend route' },
    { color: 'var(--map-congestion-high)', label: 'Traffic' },
    { color: 'var(--map-incident)', label: 'Incident', dot: true },
  ],
};

export const LANDING_STEPS: [string, string][] = [
  ['Understand', 'radar'],
  ['Coordinate', 'route'],
  ['Approve', 'user-round-check'],
  ['Adapt', 'refresh-cw'],
];
