import { API_BASE_URL, request, requireArray, requireObject } from './client';
import type {
  BenchmarkArtifact,
  Hospital,
  HospitalOptions,
  Incident,
  OperationalState,
  ReplanState,
  Report,
  ResponsePlan,
  Resource,
  SimulationStatus,
  SocialSignal,
  TimelineEvent,
  TrafficSnapshot,
} from './types';

const id = (value: string) => encodeURIComponent(value);

export async function listIncidents(): Promise<Incident[]> {
  return requireArray<Incident>(await request('/incidents'), 'incidents');
}

export async function getIncident(incidentId: string): Promise<Incident> {
  return requireObject<Incident>(await request(`/incidents/${id(incidentId)}`), 'incident');
}

export async function listReports(incidentId: string): Promise<Report[]> {
  return requireArray<Report>(await request(`/incidents/${id(incidentId)}/reports`), 'reports');
}

export async function listTimeline(incidentId: string): Promise<TimelineEvent[]> {
  return requireArray<TimelineEvent>(await request(`/incidents/${id(incidentId)}/timeline`), 'timeline');
}

export async function listPlans(incidentId: string): Promise<ResponsePlan[]> {
  return requireArray<ResponsePlan>(await request(`/incidents/${id(incidentId)}/plans`), 'plans');
}

export async function generateCandidates(incidentId: string): Promise<ResponsePlan[]> {
  return requireArray<ResponsePlan>(await request(`/incidents/${id(incidentId)}/plans/generate-candidates`, { method: 'POST' }), 'candidate plans');
}

export async function approvePlan(plan: ResponsePlan, incident: Incident): Promise<ResponsePlan> {
  return requireObject<ResponsePlan>(await request(`/plans/${id(plan.id)}/approve`, {
    method: 'POST',
    body: JSON.stringify({
      expected_incident_version: incident.version,
      expected_plan_version: plan.plan_version,
      operator_reference: 'frontend-operator',
    }),
  }), 'approved plan');
}

export async function getOperationalState(incidentId: string): Promise<OperationalState> {
  return requireObject<OperationalState>(await request(`/incidents/${id(incidentId)}/operational-state`), 'operational state');
}

export async function listResources(): Promise<Resource[]> {
  return requireArray<Resource>(await request('/resources'), 'resources');
}

export async function listHospitals(): Promise<Hospital[]> {
  return requireArray<Hospital>(await request('/hospitals'), 'hospitals');
}

export async function getTrafficSnapshot(): Promise<TrafficSnapshot> {
  return requireObject<TrafficSnapshot>(await request('/traffic/snapshot'), 'traffic snapshot');
}

export async function getReplan(incidentId: string): Promise<ReplanState | null> {
  try {
    return requireObject<ReplanState>(await request(`/incidents/${id(incidentId)}/replan`), 'replan state');
  } catch (error) {
    if (error instanceof Error && 'status' in error && (error as { status: number }).status === 404) return null;
    throw error;
  }
}

export async function generateHospitalOptions(incidentId: string): Promise<HospitalOptions> {
  return requireObject<HospitalOptions>(await request(`/incidents/${id(incidentId)}/hospital-options`, { method: 'POST' }), 'hospital options');
}

export async function selectHospitalDestination(incident: Incident, options: HospitalOptions, hospitalId: string): Promise<Record<string, unknown>> {
  return requireObject(await request(`/incidents/${id(incident.id)}/hospital-destination/select`, {
    method: 'POST',
    body: JSON.stringify({
      expected_incident_version: incident.version,
      expected_plan_version: options.plan_version,
      expected_option_set_version: options.option_set_version,
      hospital_id: hospitalId,
      operator_reference: 'frontend-operator',
    }),
  }), 'hospital destination');
}

export async function requestHospitalPreAlert(incident: Incident): Promise<Record<string, unknown>> {
  const state = await getOperationalState(incident.id);
  const options = state.hospital_options;
  if (!options) throw new Error('Generate hospital options before requesting a pre-alert.');
  return requireObject(await request(`/incidents/${id(incident.id)}/hospital-prealert`, {
    method: 'POST',
    body: JSON.stringify({
      expected_incident_version: incident.version,
      expected_plan_version: options.plan_version,
      operator_reference: 'frontend-operator',
    }),
  }), 'hospital pre-alert');
}

export async function listSocialSignals(): Promise<SocialSignal[]> {
  const response = requireObject<{ signals?: SocialSignal[] }>(await request('/social/signals'), 'social signals');
  return Array.isArray(response.signals) ? response.signals : [];
}

export async function refreshSocial(provider: 'bluesky' | 'synthetic' = 'synthetic'): Promise<Record<string, unknown>> {
  return requireObject(await request('/social/refresh', {
    method: 'POST',
    body: JSON.stringify({ provider, limit: 25 }),
  }), 'social refresh');
}

export async function dismissSocial(signalId: string): Promise<SocialSignal> {
  return requireObject<SocialSignal>(await request(`/social/signals/${id(signalId)}/dismiss`, {
    method: 'POST',
    body: JSON.stringify({ operator_reference: 'frontend-operator' }),
  }), 'dismissed social signal');
}

export async function markSocialPossibleNew(signalId: string): Promise<SocialSignal> {
  return requireObject<SocialSignal>(await request(`/social/signals/${id(signalId)}/possible-new`, {
    method: 'POST',
    body: JSON.stringify({ operator_reference: 'frontend-operator' }),
  }), 'possible new incident signal');
}

export async function associateSocial(signalId: string, incident: Incident): Promise<Record<string, unknown>> {
  return requireObject(await request(`/social/signals/${id(signalId)}/associate`, {
    method: 'POST',
    body: JSON.stringify({ target_incident_id: incident.id, expected_incident_version: incident.version, operator_reference: 'frontend-operator' }),
  }), 'social association');
}

export async function getBenchmark(): Promise<BenchmarkArtifact> {
  return requireObject<BenchmarkArtifact>(await request('/benchmark/phase08'), 'benchmark artifact');
}

export async function getSimulationStatus(): Promise<SimulationStatus> {
  return requireObject<SimulationStatus>(await request('/simulation/status'), 'simulation status');
}

export async function resetSimulation(): Promise<Record<string, unknown>> {
  return requireObject(await request('/simulation/reset', { method: 'POST' }), 'simulation reset');
}

export async function loadSimulation(scenarioId: string): Promise<Record<string, unknown>> {
  return requireObject(await request(`/simulation/load/${id(scenarioId)}`, { method: 'POST' }), 'simulation load');
}

export async function triggerSimulationEvent(next = true): Promise<Record<string, unknown>> {
  return requireObject(await request('/simulation/events', { method: 'POST', body: JSON.stringify({ next }) }), 'simulation event');
}

export function websocketUrl(): string {
  return `${API_BASE_URL.replace(/^http/, 'ws')}/ws/operations`;
}
