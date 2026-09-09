/**
 * SirenGrid human-authority command request and response types.
 * Strictly typed against canonical FastAPI Pydantic schemas (SG-INT-06A).
 *
 * Transports versioned operational commands only.
 * Does NOT maintain state, infer versions, or implement optimistic logic.
 */

import type {
  CorridorRead,
  CorridorSignalState,
  HospitalAcceptingState,
  HospitalDestinationRead,
  HospitalOptionsResponse,
  HospitalPreAlertRead,
  IncidentRead,
  IncidentStatus,
  ReplanEvaluationRead,
  ResourceRead,
  ResourceStatus,
  ResponsePlanRead,
  SimulationStatusRead,
} from '../api/types';

// Re-export shared read types used directly as command returns
export type {
  CorridorRead,
  CorridorSignalState,
  HospitalDestinationRead,
  HospitalOptionsResponse,
  HospitalPreAlertRead,
  IncidentRead,
  IncidentStatus,
  ReplanEvaluationRead,
  ResourceRead,
  ResourceStatus,
  ResponsePlanRead,
  SimulationStatusRead,
};

// ---------------------------------------------------------------------------
// Common Operator Version Payloads & Planning Commands
// ---------------------------------------------------------------------------

export interface PlanVersionCommand {
  expected_incident_version: number;
  expected_plan_version: number;
  operator_reference: string;
}

export type SelectAlternativePlanRequest = PlanVersionCommand;
export type ApprovePlanRequest = PlanVersionCommand;

export interface PlanIncidentSummary {
  id: string;
  status: IncidentStatus;
  version: number;
}

export interface ApprovalRecordRead {
  id: string;
  plan_id: string;
  incident_id: string;
  action: string;
  operator_reference: string;
  expected_incident_version: number;
  expected_plan_version: number;
  created_at: string | null;
}

export type ApprovalResult = ResponsePlanRead & {
  incident_status: IncidentStatus;
  incident: PlanIncidentSummary;
  resources: ResourceRead[];
  approval: ApprovalRecordRead;
};

// ---------------------------------------------------------------------------
// Incident Lifecycle Commands
// ---------------------------------------------------------------------------

export interface IncidentTransitionRequest {
  target_status: IncidentStatus;
  expected_incident_version: number;
  operator_reference: string;
  reason?: string | null;
}

export interface IncidentCloseRequest {
  expected_incident_version: number;
  operator_reference: string;
  reason?: string | null;
}

export interface IncidentCancelRequest {
  expected_incident_version: number;
  operator_reference: string;
  reason_code: string;
  reason?: string | null;
}

// ---------------------------------------------------------------------------
// Resource State Command
// ---------------------------------------------------------------------------

export interface ResourceStatePatchRequest {
  expected_resource_version: number;
  status: ResourceStatus;
  operator_reference: string;
  incident_id?: string | null;
}

// ---------------------------------------------------------------------------
// Hospital Selection & Pre-Alert Commands
// ---------------------------------------------------------------------------

export interface SelectHospitalDestinationRequest {
  expected_incident_version: number;
  expected_plan_version: number;
  expected_option_set_version: number;
  hospital_id: string;
  operator_reference: string;
}

export interface HospitalPreAlertRequest {
  expected_incident_version: number;
  expected_plan_version: number;
  operator_reference: string;
  simulate_failure?: boolean;
}

// ---------------------------------------------------------------------------
// Corridor Priority Commands
// ---------------------------------------------------------------------------

export interface CorridorGenerateRequest {
  resource_id: string;
}

export interface CorridorPriorityRequest {
  expected_incident_version: number;
  expected_plan_version: number;
  operator_reference: string;
  state?: CorridorSignalState;
}

// ---------------------------------------------------------------------------
// Replan Evaluation Command
// ---------------------------------------------------------------------------

export interface ReplanEvaluateRequest {
  expected_incident_version: number;
}

export interface ReplanEvaluationResponse {
  incident_id: string;
  incident_version: number;
  active_plan_id: string;
  pending_plan_id: string | null;
  status: string;
  material: boolean;
  idempotent: boolean;
  trigger_reasons: string[];
  input_fingerprint: string | null;
  explanation: Record<string, unknown>;
  evaluation: ReplanEvaluationRead | null;
  plans: ResponsePlanRead[];
}

// ---------------------------------------------------------------------------
// Simulation Controller Commands
// ---------------------------------------------------------------------------

export interface SimulationResetResponse {
  status: string;
  simulation: SimulationStatusRead;
  reality: string;
}

export interface SimulationLoadResponse {
  status: string;
  scenario_id: string;
  seed: number;
  master_plan_case: string;
  simulation: SimulationStatusRead;
  reality: string;
}

export interface ResourceStateEventPayload {
  resource_id: string;
  status: ResourceStatus;
  expected_resource_version?: number | null;
  incident_id?: string | null;
}

export interface HospitalStateEventPayload {
  hospital_id: string;
  accepting_state?: HospitalAcceptingState | null;
  simulated_load_ratio?: number | null;
  simulated_free_capacity?: number | null;
  expected_version?: number | null;
}

export type SimulationResourceEvent = {
  event_type: 'RESOURCE_STATE';
  resource_payload: ResourceStateEventPayload;
  hospital_payload?: never;
};

export type SimulationHospitalEvent = {
  event_type: 'HOSPITAL_STATE';
  hospital_payload: HospitalStateEventPayload;
  resource_payload?: never;
};

export type SimulationEventRequest = SimulationResourceEvent | SimulationHospitalEvent;

export interface SimulationEventResponse {
  status: string;
  event_index: number;
  event_type: string;
  simulation: SimulationStatusRead;
  reality: string;
  details: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Command Failure Classification
// ---------------------------------------------------------------------------

export type CommandFailureKind =
  | 'NETWORK'
  | 'FORBIDDEN'
  | 'NOT_FOUND'
  | 'CONFLICT'
  | 'VALIDATION'
  | 'SERVER'
  | 'UNKNOWN';
