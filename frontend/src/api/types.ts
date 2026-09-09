export type JsonRecord = Record<string, unknown>;

export interface Incident {
  id: string;
  version: number;
  status: string;
  incident_type: string;
  severity: string;
  confidence_level: string;
  location: { lat: number; lon: number } | null;
  latitude: number | null;
  longitude: number | null;
  location_text: string | null;
  casualty_count: number | null;
  casualty_range: string | null;
  trapped_person: boolean | null;
  road_blockage: boolean | null;
  transport_required: boolean | null;
  required_hospital_capabilities: string[];
  required_resources: JsonRecord[];
  current_plan_id: string | null;
  pending_replan_plan_id: string | null;
  created_at: string | null;
  updated_at: string | null;
  provenance: JsonRecord;
}

export interface Resource {
  id: string;
  version: number;
  name: string;
  resource_type: string;
  type: string;
  capabilities: string[];
  capability_tags: string[];
  status: string;
  operational_status: string;
  latitude: number;
  longitude: number;
  home_zone: string | null;
  assigned_incident_id: string | null;
  assignment: string | null;
  last_updated: string | null;
  provenance: JsonRecord;
  is_planner_eligible: boolean;
  route_progress: number | null;
}

export interface ResponsePlan {
  id: string;
  plan_id: string;
  incident_id: string;
  incident_version: number;
  plan_version: number;
  version: number;
  status: string;
  resource_ids: string[];
  routes: JsonRecord[];
  metrics: JsonRecord;
  score_breakdown: JsonRecord;
  created_at: string | null;
  candidate_set_id: string | null;
  candidate_rank: number | null;
  candidate_count: number | null;
}

export interface Report {
  id: string;
  incident_id: string | null;
  source_type: string;
  source_reference: string;
  raw_text: string;
  location_text: string | null;
  location: { lat: number; lon: number } | null;
  received_at: string;
  data_reality: string;
  provenance: JsonRecord;
  processing_status: string;
  evidence_items: JsonRecord[];
}

export interface TimelineEvent {
  id: string;
  incident_id: string;
  event_type: string;
  details: JsonRecord;
  created_at: string;
}

export interface Hospital {
  id: string;
  source_id: string;
  name: string | null;
  latitude: number;
  longitude: number;
  static_capabilities: string[];
  operational_version: number;
  accepting_state: string;
  simulated_load_ratio: number | null;
  simulated_free_capacity: number | null;
  incoming_cases: number | null;
  simulated_capability_tags: string[];
  operational_freshness_status: string;
  static_provenance: JsonRecord;
  operational_provenance: JsonRecord;
}

export interface HospitalOption {
  option_id: string;
  option_set_id: string;
  option_version: number;
  rank: number;
  hospital: Hospital;
  route: JsonRecord;
  score: number;
  score_breakdown: JsonRecord;
  provenance: JsonRecord;
}

export interface HospitalOptions {
  incident_id: string;
  plan_id: string;
  incident_version: number;
  plan_version: number;
  option_set_id: string;
  option_set_version: number;
  transport_required: boolean;
  required_hospital_capabilities: string[];
  options: HospitalOption[];
  excluded_hospitals: JsonRecord[];
  generated_at: string;
  provenance: JsonRecord;
}

export interface OperationalState {
  incident_id: string;
  incident_version: number;
  plan_id: string | null;
  hospital_options: HospitalOptions | null;
  selected_destination: JsonRecord | null;
  hospital_pre_alert: JsonRecord | null;
  corridor: JsonRecord | null;
  corridors: JsonRecord[];
  driver_alert: JsonRecord | null;
  driver_alerts: JsonRecord[];
}

export interface ReplanState {
  incident_id: string;
  incident_version: number;
  active_plan_id: string;
  pending_plan_id: string | null;
  status: string;
  material: boolean;
  idempotent: boolean;
  trigger_reasons: string[];
  explanation: JsonRecord;
  evaluation: JsonRecord | null;
  plans: ResponsePlan[];
}

export interface TrafficSnapshot {
  snapshot_id: string | null;
  provider_state: string | null;
  retrieved_at: string | null;
  provider_last_updated: string | null;
  freshness_status: string;
  source: string;
  data_reality: string | null;
  observation_count: number;
  match_count: number;
  failure_reason: string | null;
}

export interface SocialSignal extends Report {
  social_signal?: JsonRecord;
  association_evaluation?: JsonRecord[];
  association_outcome?: string | null;
}

export interface BenchmarkMetricSummary {
  availability_rate: number;
  available_count: number;
  max?: number;
  mean?: number;
  median?: number;
  min?: number;
  missing_count: number;
  total_count: number;
  p95?: number;
}

export interface BenchmarkEngineAggregate {
  count: number;
  outcome_counts: Record<string, number>;
  hospital_status_counts: Record<string, number>;
  incident_eta_seconds: BenchmarkMetricSummary;
  baseline_population_weighted_coverage: BenchmarkMetricSummary;
  post_dispatch_population_weighted_coverage: BenchmarkMetricSummary;
  post_dispatch_undercovered_zone_count: BenchmarkMetricSummary;
  post_dispatch_unreachable_zone_count: BenchmarkMetricSummary;
  hospital_eta_seconds: BenchmarkMetricSummary;
  replan_eta_delta_seconds: BenchmarkMetricSummary;
  replan_status_counts: Record<string, number>;
}

export interface BenchmarkValidation {
  actual: string;
  case_id: string;
  evidence: string;
  expected: string;
  passed: boolean;
  result: string;
  scenario_id: string;
}

export interface BenchmarkArtifact {
  aggregate: {
    baseline: BenchmarkEngineAggregate;
    sirengrid: BenchmarkEngineAggregate;
  };
  performance: JsonRecord;
  validation: BenchmarkValidation[];
  metadata: JsonRecord;
  provenance: JsonRecord;
}

export interface SimulationStatus {
  mode: string;
  scope: string;
  enabled: boolean;
  scenario_id: string | null;
  next_event_index: number;
  scheduler: string;
}

export interface OperationsEventEnvelope {
  event: string;
  incident_id: string | null;
  timestamp: string;
  version: number;
  payload: JsonRecord;
}
