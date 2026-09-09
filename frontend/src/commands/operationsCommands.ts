/**
 * SirenGrid human-authority command client.
 * Strictly typed against canonical FastAPI operational endpoints (SG-INT-06A).
 *
 * Transports versioned commands to the backend.
 * Does NOT maintain state, infer versions, re-attempt 409s, or apply optimistic UI updates.
 */

import { ApiError, request, requireArray, requireObject } from '../api/client';
import type {
  ApprovePlanRequest,
  ApprovalResult,
  CommandFailureKind,
  CorridorGenerateRequest,
  CorridorPriorityRequest,
  CorridorRead,
  HospitalDestinationRead,
  HospitalOptionsResponse,
  HospitalPreAlertRead,
  HospitalPreAlertRequest,
  IncidentCancelRequest,
  IncidentCloseRequest,
  IncidentRead,
  IncidentTransitionRequest,
  ReplanEvaluateRequest,
  ReplanEvaluationResponse,
  ResourceRead,
  ResourceStatePatchRequest,
  ResponsePlanRead,
  SelectAlternativePlanRequest,
  SelectHospitalDestinationRequest,
  SimulationEventRequest,
  SimulationEventResponse,
  SimulationLoadResponse,
  SimulationResetResponse,
} from './types';

const id = (value: string): string => encodeURIComponent(value);

const body = (payload: unknown): RequestInit => ({
  method: 'POST',
  body: JSON.stringify(payload),
});

const patchBody = (payload: unknown): RequestInit => ({
  method: 'PATCH',
  body: JSON.stringify(payload),
});

/**
 * Classifies command execution errors into standardized operational failure categories.
 * Preserves the underlying ApiError without mutation or suppression.
 */
export function classifyCommandError(error: unknown): CommandFailureKind {
  if (error instanceof ApiError) {
    const status = error.status;
    if (status === 0) return 'NETWORK';
    if (status === 403) return 'FORBIDDEN';
    if (status === 404) return 'NOT_FOUND';
    if (status === 409) return 'CONFLICT';
    if (status === 422) return 'VALIDATION';
    if (status >= 500 && status <= 599) return 'SERVER';
    return 'UNKNOWN';
  }
  return 'UNKNOWN';
}

// ---------------------------------------------------------------------------
// Planning Commands
// ---------------------------------------------------------------------------

export async function generateCandidates(incidentId: string): Promise<ResponsePlanRead[]> {
  const res = await request<unknown>(`/incidents/${id(incidentId)}/plans/generate-candidates`, {
    method: 'POST',
  });
  return requireArray<ResponsePlanRead>(res, 'candidates');
}

export async function selectAlternativePlan(
  planId: string,
  payload: SelectAlternativePlanRequest,
): Promise<ResponsePlanRead> {
  const res = await request<unknown>(`/plans/${id(planId)}/select`, body(payload));
  return requireObject<ResponsePlanRead>(res, 'plan');
}

export async function approvePlan(
  planId: string,
  payload: ApprovePlanRequest,
): Promise<ApprovalResult> {
  const res = await request<unknown>(`/plans/${id(planId)}/approve`, body(payload));
  return requireObject<ApprovalResult>(res, 'approval result');
}

// ---------------------------------------------------------------------------
// Incident Lifecycle Commands
// ---------------------------------------------------------------------------

export async function transitionIncident(
  incidentId: string,
  payload: IncidentTransitionRequest,
): Promise<IncidentRead> {
  const res = await request<unknown>(`/incidents/${id(incidentId)}/transition`, body(payload));
  return requireObject<IncidentRead>(res, 'incident');
}

export async function closeIncident(
  incidentId: string,
  payload: IncidentCloseRequest,
): Promise<IncidentRead> {
  const res = await request<unknown>(`/incidents/${id(incidentId)}/close`, body(payload));
  return requireObject<IncidentRead>(res, 'incident');
}

export async function cancelIncident(
  incidentId: string,
  payload: IncidentCancelRequest,
): Promise<IncidentRead> {
  const res = await request<unknown>(`/incidents/${id(incidentId)}/cancel`, body(payload));
  return requireObject<IncidentRead>(res, 'incident');
}

// ---------------------------------------------------------------------------
// Resource State Command
// ---------------------------------------------------------------------------

export async function patchResourceState(
  resourceId: string,
  payload: ResourceStatePatchRequest,
): Promise<ResourceRead> {
  const res = await request<unknown>(`/resources/${id(resourceId)}/state`, patchBody(payload));
  return requireObject<ResourceRead>(res, 'resource');
}

// ---------------------------------------------------------------------------
// Hospital Selection & Pre-Alert Commands
// ---------------------------------------------------------------------------

export async function generateHospitalOptions(incidentId: string): Promise<HospitalOptionsResponse> {
  const res = await request<unknown>(`/incidents/${id(incidentId)}/hospital-options`, {
    method: 'POST',
  });
  return requireObject<HospitalOptionsResponse>(res, 'hospital options');
}

export async function selectHospitalDestination(
  incidentId: string,
  payload: SelectHospitalDestinationRequest,
): Promise<HospitalDestinationRead> {
  const res = await request<unknown>(
    `/incidents/${id(incidentId)}/hospital-destination/select`,
    body(payload),
  );
  return requireObject<HospitalDestinationRead>(res, 'hospital destination');
}

export async function sendHospitalPreAlert(
  incidentId: string,
  payload: HospitalPreAlertRequest,
): Promise<HospitalPreAlertRead> {
  const res = await request<unknown>(
    `/incidents/${id(incidentId)}/hospital-prealert`,
    body(payload),
  );
  return requireObject<HospitalPreAlertRead>(res, 'hospital pre-alert');
}

// ---------------------------------------------------------------------------
// Corridor Priority Commands
// ---------------------------------------------------------------------------

export async function generateCorridor(
  incidentId: string,
  payload: CorridorGenerateRequest,
): Promise<CorridorRead> {
  const res = await request<unknown>(`/incidents/${id(incidentId)}/corridor`, body(payload));
  return requireObject<CorridorRead>(res, 'corridor');
}

export async function requestCorridorPriority(
  incidentId: string,
  payload: CorridorPriorityRequest,
): Promise<CorridorRead> {
  const res = await request<unknown>(
    `/incidents/${id(incidentId)}/corridor/priority`,
    body(payload),
  );
  return requireObject<CorridorRead>(res, 'corridor');
}

// ---------------------------------------------------------------------------
// Replan Evaluation Command
// ---------------------------------------------------------------------------

export async function evaluateReplan(
  incidentId: string,
  payload: ReplanEvaluateRequest,
): Promise<ReplanEvaluationResponse> {
  const res = await request<unknown>(
    `/incidents/${id(incidentId)}/replan/evaluate`,
    body(payload),
  );
  return requireObject<ReplanEvaluationResponse>(res, 'replan evaluation');
}

// ---------------------------------------------------------------------------
// Simulation Controller Commands
// ---------------------------------------------------------------------------

export async function resetSimulation(): Promise<SimulationResetResponse> {
  const res = await request<unknown>('/simulation/reset', {
    method: 'POST',
  });
  return requireObject<SimulationResetResponse>(res, 'simulation reset');
}

export async function loadSimulationScenario(scenarioId: string): Promise<SimulationLoadResponse> {
  const res = await request<unknown>(`/simulation/load/${id(scenarioId)}`, {
    method: 'POST',
  });
  return requireObject<SimulationLoadResponse>(res, 'simulation load');
}

export async function applySimulationEvent(
  payload: SimulationEventRequest,
): Promise<SimulationEventResponse> {
  const res = await request<unknown>('/simulation/events', body(payload));
  return requireObject<SimulationEventResponse>(res, 'simulation event');
}
