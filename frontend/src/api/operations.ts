import { ApiError, request, requireArray, requireObject } from './client';
import type {
  HealthRead,
  HospitalRead,
  IncidentOperationalStateRead,
  IncidentRead,
  MapLayerResponse,
  ReplanEvaluationRead,
  ReportRead,
  ResourceRead,
  ResponsePlanRead,
  SimulationStatusRead,
  TimelineEventRead,
  TrafficSnapshotRead,
} from './types';

const id = (value: string) => encodeURIComponent(value);

export async function getHealth(): Promise<HealthRead> {
  return requireObject<HealthRead>(await request('/health'), 'health');
}

export async function listIncidents(): Promise<IncidentRead[]> {
  return requireArray<IncidentRead>(await request('/incidents'), 'incidents');
}

export async function getIncident(incidentId: string): Promise<IncidentRead> {
  return requireObject<IncidentRead>(await request(`/incidents/${id(incidentId)}`), 'incident');
}

export async function listResources(): Promise<ResourceRead[]> {
  return requireArray<ResourceRead>(await request('/resources'), 'resources');
}

export async function listHospitals(): Promise<HospitalRead[]> {
  return requireArray<HospitalRead>(await request('/hospitals'), 'hospitals');
}

export async function getTrafficSnapshot(): Promise<TrafficSnapshotRead> {
  return requireObject<TrafficSnapshotRead>(await request('/traffic/snapshot'), 'traffic snapshot');
}

export async function getSimulationStatus(): Promise<SimulationStatusRead> {
  return requireObject<SimulationStatusRead>(await request('/simulation/status'), 'simulation status');
}

export async function listReports(incidentId: string): Promise<ReportRead[]> {
  return requireArray<ReportRead>(await request(`/incidents/${id(incidentId)}/reports`), 'reports');
}

export async function listTimeline(incidentId: string): Promise<TimelineEventRead[]> {
  return requireArray<TimelineEventRead>(await request(`/incidents/${id(incidentId)}/timeline`), 'timeline');
}

export async function listPlans(incidentId: string): Promise<ResponsePlanRead[]> {
  return requireArray<ResponsePlanRead>(await request(`/incidents/${id(incidentId)}/plans`), 'plans');
}

export async function getOperationalState(incidentId: string): Promise<IncidentOperationalStateRead> {
  return requireObject<IncidentOperationalStateRead>(
    await request(`/incidents/${id(incidentId)}/operational-state`),
    'operational state',
  );
}

export async function getMapBoundary(): Promise<MapLayerResponse> {
  return requireObject<MapLayerResponse>(await request('/map/boundary'), 'map boundary');
}

export async function getMapRoads(): Promise<MapLayerResponse> {
  return requireObject<MapLayerResponse>(await request('/map/roads'), 'map roads');
}

export async function getMapZones(): Promise<MapLayerResponse> {
  return requireObject<MapLayerResponse>(await request('/map/zones'), 'map zones');
}

export async function getReplan(incidentId: string): Promise<ReplanEvaluationRead | null> {
  try {
    const raw = await request<ReplanEvaluationRead | null>(`/incidents/${id(incidentId)}/replan`);
    if (raw === null || raw === undefined) return null;
    return requireObject<ReplanEvaluationRead>(raw, 'replan evaluation');
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}
