/**
 * SG-MAP-04B — canonical data → renderer adapters.
 *
 * Pure translation layer between Phase 03 backend read models and the Phase 04A
 * `RealMapCanvas` renderer contract. This module:
 *
 *  - does NOT use React,
 *  - does NOT fetch,
 *  - does NOT mutate backend state,
 *  - does NOT compute routes, ETA, coverage, ranking, suitability or materiality.
 *
 * Every value it produces is a direct, explicit projection of backend truth.
 * When truth is missing (no coordinates, no route geometry, wrong candidate
 * set) the adapter returns nothing rather than inventing a placeholder.
 */

import type {
  HospitalRead,
  IncidentRead,
  OperationalResponderTrackingRead,
  PlanRoute,
  ReplanEvaluationRead,
  ResourceRead,
  ResponsePlanRead,
} from '../api/types';
import type {
  LngLatTuple,
  MapGeoJsonFeatureCollection,
  RealMapMarker,
  RealMapRoute,
  RealMapRouteRole,
} from './mapTypes';

/** Operations workspace states that drive route rendering (structural match of `OpsState`). */
export type MapRouteOpsState =
  | 'idle'
  | 'incident'
  | 'plan'
  | 'active'
  | 'replan'
  | 'hospital'
  | 'coverage';

/* --------------------------------------------------------- geojson validation -- */

/**
 * Runtime guard for a GeoJSON FeatureCollection coming from `/map/*`.
 * Returns a typed renderer collection only when the payload is structurally a
 * FeatureCollection; returns `null` for anything else. It never fabricates an
 * empty collection to mask invalid input.
 */
export function toMapFeatureCollection(
  value: unknown,
): MapGeoJsonFeatureCollection | null {
  if (!value || typeof value !== 'object') return null;
  const record = value as Record<string, unknown>;
  if (record.type !== 'FeatureCollection') return null;
  if (!Array.isArray(record.features)) return null;
  return {
    type: 'FeatureCollection',
    features: record.features as MapGeoJsonFeatureCollection['features'],
  };
}

/* ------------------------------------------------------------------ helpers -- */

function finiteNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

/** Exact incident coordinate from `longitude`/`latitude` or `location.lon`/`location.lat`. */
function incidentLngLat(incident: IncidentRead | null | undefined): LngLatTuple | null {
  if (!incident) return null;
  const directLon = finiteNumber(incident.longitude);
  const directLat = finiteNumber(incident.latitude);
  if (directLon !== null && directLat !== null) return [directLon, directLat];
  const loc = incident.location;
  if (loc) {
    const lon = finiteNumber(loc.lon);
    const lat = finiteNumber(loc.lat);
    if (lon !== null && lat !== null) return [lon, lat];
  }
  return null;
}

function humanizeType(raw: string): string {
  const cleaned = raw.replace(/[_-]+/g, ' ').trim().toLowerCase();
  if (!cleaned) return raw;
  return cleaned.replace(/\b\w/g, (c) => c.toUpperCase());
}

function isSimulatedProvenance(provenance: Record<string, unknown> | undefined): boolean {
  if (!provenance) return false;
  const candidates = [provenance.data_reality, provenance.reality, provenance.mode];
  return candidates.some(
    (v) => typeof v === 'string' && v.toUpperCase() === 'SIMULATED',
  );
}

/* ------------------------------------------------------------------ markers -- */

/** Selected incident marker — only when exact backend coordinates exist. */
export function toIncidentMarker(
  incident: IncidentRead | null | undefined,
): RealMapMarker | null {
  const coordinate = incidentLngLat(incident);
  if (!incident || !coordinate) return null;
  const severe = incident.severity === 'HIGH' || incident.severity === 'CRITICAL';
  return {
    id: incident.id,
    coordinate,
    kind: 'incident',
    label: humanizeType(incident.incident_type),
    sublabel: incident.location_text ?? undefined,
    tone: severe ? 'critical' : 'primary',
    icon: 'incident',
    selected: true,
  };
}

/** Resource markers from explicit backend coordinates. All valid resources shown. */
export function toResourceMarkers(
  resources: readonly ResourceRead[],
  selectedIncidentId: string | null,
  tracking: readonly OperationalResponderTrackingRead[] = [],
): RealMapMarker[] {
  const markers: RealMapMarker[] = [];
  const trackingByResource = new Map(tracking.map((item) => [item.resource_id, item]));
  for (const resource of resources) {
    const snapshot = trackingByResource.get(resource.id);
    const lon = finiteNumber(snapshot?.location.lon ?? resource.longitude);
    const lat = finiteNumber(snapshot?.location.lat ?? resource.latitude);
    if (lon === null || lat === null) continue;

    const assignedToSelected =
      selectedIncidentId !== null &&
      resource.assigned_incident_id === selectedIncidentId;

    let tone: RealMapMarker['tone'] = 'neutral';
    if (assignedToSelected) tone = 'primary';
    else if (isSimulatedProvenance(resource.provenance)) tone = 'simulated';

    const rtype = (resource.resource_type ?? resource.type ?? '').toUpperCase();
    const icon: RealMapMarker['icon'] =
      rtype === 'AMBULANCE'
        ? 'ambulance'
        : rtype.includes('FIRE')
        ? 'fire'
        : rtype.includes('POLICE')
        ? 'police'
        : 'unit';

    markers.push({
      id: resource.id,
      coordinate: [lon, lat],
      kind: 'resource',
      label: resource.name || humanizeType(rtype || 'response unit'),
      sublabel: humanizeType(snapshot?.status ?? resource.status),
      tone,
      icon,
    });
  }
  return markers;
}

/** Hospital markers from explicit backend coordinates. Accepting state is shown verbatim. */
export function toHospitalMarkers(hospitals: readonly HospitalRead[]): RealMapMarker[] {
  const markers: RealMapMarker[] = [];
  for (const hospital of hospitals) {
    const lon = finiteNumber(hospital.longitude);
    const lat = finiteNumber(hospital.latitude);
    if (lon === null || lat === null) continue;
    markers.push({
      id: hospital.id,
      coordinate: [lon, lat],
      kind: 'hospital',
      label: hospital.name || 'Hospital',
      sublabel: humanizeType(hospital.accepting_state),
      tone: 'neutral',
      icon: 'hospital',
    });
  }
  return markers;
}

/* -------------------------------------------------------------- plan routing -- */

/** Exact candidate-set identity for a plan. No fuzzy matching. */
export function resolveCandidateSetId(
  plan: ResponsePlanRead | null | undefined,
): string | null {
  if (!plan) return null;
  if (typeof plan.candidate_set_id === 'string' && plan.candidate_set_id) {
    return plan.candidate_set_id;
  }
  const metrics = plan.metrics as Record<string, unknown> | undefined;
  if (metrics && typeof metrics === 'object') {
    const direct = metrics.candidate_set_id;
    if (typeof direct === 'string' && direct) return direct;
    const phase04 = metrics.phase04 as Record<string, unknown> | undefined;
    if (phase04 && typeof phase04 === 'object') {
      const nested = phase04.candidate_set_id;
      if (typeof nested === 'string' && nested) return nested;
    }
  }
  return null;
}

function planMatchesId(plan: ResponsePlanRead, id: string): boolean {
  return plan.plan_id === id || plan.id === id;
}

/** Current plan via the corrected Phase 03 rule: exact `current_plan_id` match only. */
export function resolveCurrentPlan(
  incident: IncidentRead | null | undefined,
  plans: readonly ResponsePlanRead[],
): ResponsePlanRead | null {
  const currentId = incident?.current_plan_id;
  if (!currentId) return null;
  return plans.find((plan) => planMatchesId(plan, currentId)) ?? null;
}

/** Pending replacement plan: exact `pending_replan_plan_id`, else exact `replan.pending_plan_id`. */
export function resolvePendingReplanPlan(
  incident: IncidentRead | null | undefined,
  plans: readonly ResponsePlanRead[],
  replan: ReplanEvaluationRead | null | undefined,
): ResponsePlanRead | null {
  const directId = incident?.pending_replan_plan_id;
  if (directId) {
    const found = plans.find((plan) => planMatchesId(plan, directId));
    if (found) return found;
  }
  const fallbackId = replan?.pending_plan_id;
  if (fallbackId) {
    const found = plans.find((plan) => planMatchesId(plan, fallbackId));
    if (found) return found;
  }
  return null;
}

/** Newest backend `RECOMMENDED` plan by deterministic plan version. */
export function resolveReviewPlan(
  plans: readonly ResponsePlanRead[],
): ResponsePlanRead | null {
  let review: ResponsePlanRead | null = null;
  for (const plan of plans) {
    if (plan.status !== 'RECOMMENDED') continue;
    if (review === null || plan.plan_version > review.plan_version) review = plan;
  }
  return review;
}

function lineStringCoordinates(geometry: unknown): [number, number][] | null {
  if (!geometry || typeof geometry !== 'object') return null;
  const geom = geometry as Record<string, unknown>;
  if (geom.type !== 'LineString') return null;
  if (!Array.isArray(geom.coordinates) || geom.coordinates.length < 2) return null;
  const coordinates: [number, number][] = [];
  for (const pair of geom.coordinates) {
    if (!Array.isArray(pair) || pair.length < 2) return null;
    const lon = finiteNumber(pair[0]);
    const lat = finiteNumber(pair[1]);
    if (lon === null || lat === null) return null;
    coordinates.push([lon, lat]);
  }
  return coordinates;
}

/**
 * Translate a plan's persisted per-resource route geometries into renderer
 * routes. One `RealMapRoute` per valid `LineString`; stable id `plan:resource:index`.
 * Routes without explicit valid geometry are skipped, never reconstructed.
 */
export function planToRealMapRoutes(
  plan: ResponsePlanRead,
  role: RealMapRouteRole,
): RealMapRoute[] {
  const routes: RealMapRoute[] = [];
  const routeRecords = Array.isArray(plan.routes) && plan.routes.length > 0
    ? plan.routes
    : Array.isArray(plan.routes_json)
    ? plan.routes_json
    : [];
  routeRecords.forEach((route: PlanRoute, index: number) => {
    const coordinates = lineStringCoordinates(route.geometry);
    if (!coordinates) return;
    const resourceId =
      typeof route.resource_id === 'string' && route.resource_id
        ? route.resource_id
        : `route-${index}`;
    routes.push({
      id: `${plan.plan_id}:${resourceId}:${index}`,
      role,
      label: role,
      geometry: {
        type: 'FeatureCollection',
        features: [
          {
            type: 'Feature',
            geometry: { type: 'LineString', coordinates },
            properties: { plan_id: plan.plan_id, resource_id: resourceId },
          },
        ],
      },
    });
  });
  return routes;
}

export interface RouteResolutionInput {
  opsState: MapRouteOpsState;
  incident: IncidentRead | null;
  plans: readonly ResponsePlanRead[];
  replan: ReplanEvaluationRead | null;
}

function sameCandidateSetAlternatives(
  plans: readonly ResponsePlanRead[],
  primary: ResponsePlanRead,
  excludeIds: readonly string[],
): RealMapRoute[] {
  const setId = resolveCandidateSetId(primary);
  if (!setId) return [];
  const excluded = new Set<string>([primary.id, primary.plan_id, ...excludeIds]);
  return plans
    .filter((plan) => !excluded.has(plan.id) && !excluded.has(plan.plan_id))
    .filter((plan) => resolveCandidateSetId(plan) === setId)
    .flatMap((plan) => planToRealMapRoutes(plan, 'alternative'));
}

/**
 * Resolve which route lines the real map shows, per corrected Phase 03 truth
 * rules and the Operations state. Never leaks historical candidate sets and
 * never fabricates a route.
 */
export function buildRouteSet(input: RouteResolutionInput): RealMapRoute[] {
  const { opsState, incident, plans, replan } = input;
  if (!incident) return [];

  const currentPlan = resolveCurrentPlan(incident, plans);

  switch (opsState) {
    case 'idle':
    case 'incident':
    case 'active':
    case 'hospital':
      return currentPlan ? planToRealMapRoutes(currentPlan, 'primary') : [];

    case 'plan': {
      const reviewPlan = currentPlan ?? resolveReviewPlan(plans);
      if (!reviewPlan) return [];
      return [
        ...planToRealMapRoutes(reviewPlan, 'primary'),
        ...sameCandidateSetAlternatives(plans, reviewPlan, []),
      ];
    }

    case 'replan': {
      const pendingPlan = resolvePendingReplanPlan(incident, plans, replan);
      const routes: RealMapRoute[] = [];
      if (currentPlan) routes.push(...planToRealMapRoutes(currentPlan, 'previous'));
      if (pendingPlan) {
        routes.push(...planToRealMapRoutes(pendingPlan, 'primary'));
        routes.push(
          ...sameCandidateSetAlternatives(
            plans,
            pendingPlan,
            currentPlan ? [currentPlan.id, currentPlan.plan_id] : [],
          ),
        );
      }
      return routes;
    }

    case 'coverage':
    default:
      return [];
  }
}

/* ------------------------------------------------------------------ viewport -- */

/** Map centre preference: exact selected-incident coordinate, else undefined (renderer default). */
export function resolveMapCenter(
  incident: IncidentRead | null | undefined,
): LngLatTuple | undefined {
  return incidentLngLat(incident) ?? undefined;
}
