export type DataReality =
  | 'REAL_PUBLIC'
  | 'REAL_LIVE'
  | 'REAL_DERIVED'
  | 'SIMULATED'
  | 'SYNTHETIC';

export type FreshnessStatus =
  | 'LIVE'
  | 'FRESH'
  | 'STALE'
  | 'STATIC'
  | 'UNKNOWN';

export type Severity =
  | 'LOW'
  | 'MODERATE'
  | 'HIGH'
  | 'CRITICAL';

export type ConfidenceLevel =
  | 'LOW'
  | 'MEDIUM'
  | 'HIGH';

export type IncidentStatus =
  | 'RECEIVED'
  | 'INTERPRETING'
  | 'ACTIVE_UNCONFIRMED'
  | 'RESPONSE_PROPOSED'
  | 'AWAITING_APPROVAL'
  | 'RESPONSE_ACTIVE'
  | 'EN_ROUTE'
  | 'ON_SCENE'
  | 'TRANSPORT_ACTIVE'
  | 'HANDOVER'
  | 'CLOSED'
  | 'REQUIRES_REVIEW'
  | 'DUPLICATE_MERGED'
  | 'CANCELLED_FALSE_REPORT';

export type ResourceType =
  | 'AMBULANCE'
  | 'FIRE_RESCUE';

export type ResourceStatus =
  | 'AVAILABLE'
  | 'RESERVED'
  | 'ASSIGNED'
  | 'EN_ROUTE'
  | 'ON_SCENE'
  | 'TRANSPORTING'
  | 'OUT_OF_SERVICE';

export type ResponsePlanStatus =
  | 'CANDIDATE'
  | 'RECOMMENDED'
  | 'ALTERNATIVE'
  | 'APPROVED'
  | 'REJECTED'
  | 'SUPERSEDED';

export type HospitalAcceptingState =
  | 'ACCEPTING'
  | 'NOT_ACCEPTING'
  | 'UNKNOWN';

export type HospitalPreAlertStatus =
  | 'REQUESTED'
  | 'SENT'
  | 'ACKNOWLEDGED'
  | 'FAILED';

export type CorridorSignalState =
  | 'NORMAL'
  | 'REQUESTED'
  | 'PREPARING'
  | 'PRIORITY_ACTIVE'
  | 'PASSED'
  | 'FAILED';

export type DriverAlertStatus =
  | 'ACTIVE'
  | 'EXPIRED';

export interface Coordinate {
  lat: number;
  lon: number;
}

export interface HealthRead {
  status: string;
  service: string;
  api_version: string;
}

export interface ResourceRequirement {
  resource_type: ResourceType;
  count: number;
}

export interface IncidentRead {
  id: string;
  version: number;
  status: IncidentStatus;
  incident_type: string;
  severity: Severity;
  confidence_level: ConfidenceLevel;
  location: Coordinate | null;
  latitude: number | null;
  longitude: number | null;
  location_text: string | null;
  casualty_count: number | null;
  casualty_range: string | null;
  trapped_person: boolean | null;
  road_blockage: boolean | null;
  transport_required: boolean | null;
  required_hospital_capabilities: string[];
  required_resources: ResourceRequirement[];
  required_resources_json?: ResourceRequirement[];
  current_plan_id: string | null;
  pending_replan_plan_id: string | null;
  created_at: string | null;
  updated_at: string | null;
  provenance: Record<string, unknown>;
  provenance_json?: Record<string, unknown>;
}

export interface ResourceRead {
  id: string;
  version: number;
  name: string;
  resource_type: ResourceType;
  type: ResourceType;
  capabilities: string[];
  capability_tags: string[];
  capability_tags_json?: string[];
  status: ResourceStatus;
  operational_status: ResourceStatus;
  latitude: number;
  longitude: number;
  location: Coordinate;
  home_zone: string | null;
  assigned_incident_id: string | null;
  assignment: string | null;
  last_updated: string | null;
  provenance: Record<string, unknown>;
  provenance_json?: Record<string, unknown>;
  is_planner_eligible: boolean;
  route_progress: number | null;
}

export interface PlanRoute {
  resource_id?: string;
  resource_type?: ResourceType;
  resource_name?: string;
  origin?: Coordinate;
  destination?: Coordinate;
  geometry?: Record<string, unknown>;
  distance_m?: number;
  eta_seconds?: number;
  origin_snap_distance_m?: number;
  destination_snap_distance_m?: number;
  routing_source?: string;
  nodes?: unknown[];
  [key: string]: unknown;
}

export interface PlanMetrics {
  max_arrival_eta_seconds?: number;
  mean_arrival_eta_seconds?: number;
  selected_resource_count?: number;
  routing_source?: string;
  candidate_set_id?: string;
  candidate_rank?: number;
  candidate_count?: number;
  phase04?: {
    coverage_delta?: number;
    affected_zone_ids?: string[];
    newly_undercovered_zone_ids?: string[];
    max_incident_eta_seconds?: number;
    post_dispatch_joint?: {
      population_weighted_coverage?: number;
      [key: string]: unknown;
    };
    [key: string]: unknown;
  };
  [key: string]: unknown;
}

export interface PlanScoreBreakdown {
  post_dispatch_joint_population_weighted_coverage?: number;
  remaining_reserve_exhausted?: boolean;
  final_score?: number;
  policy_version?: string;
  convention?: string;
  algorithm?: string;
  coverage_considered?: boolean;
  traffic_source?: string;
  note?: string;
  [key: string]: unknown;
}

export interface ResponsePlanRead {
  id: string;
  plan_id: string;
  incident_id: string;
  incident_version: number;
  plan_version: number;
  version: number;
  status: ResponsePlanStatus;
  resource_ids: string[];
  resource_ids_json?: string[];
  routes: PlanRoute[];
  routes_json?: PlanRoute[];
  metrics: PlanMetrics;
  metrics_json?: PlanMetrics;
  score_breakdown: PlanScoreBreakdown;
  score_breakdown_json?: PlanScoreBreakdown;
  created_at: string | null;
  candidate_set_id: string | null;
  candidate_rank: number | null;
  candidate_count: number | null;
}

export interface EvidenceItemRead {
  type: string;
  uri_or_reference: string | null;
  extracted_facts: Record<string, unknown>;
  provenance: Record<string, unknown>;
  confidence_support: string | null;
  created_at: string | null;
}

export interface ReportRead {
  id: string;
  incident_id: string | null;
  source_type: string;
  source_reference: string;
  raw_text: string;
  location_text: string | null;
  location: Coordinate | null;
  location_json?: Coordinate | null;
  received_at: string;
  data_reality: DataReality;
  provenance: Record<string, unknown>;
  provenance_json?: Record<string, unknown>;
  processing_status: string;
  evidence_items: EvidenceItemRead[] | Record<string, unknown>[];
  evidence_items_json?: EvidenceItemRead[] | Record<string, unknown>[];
  created_at: string;
}

export interface TimelineEventRead {
  id: string;
  incident_id: string;
  event_type: string;
  details: Record<string, unknown>;
  details_json?: Record<string, unknown>;
  created_at: string;
}

export interface HospitalRead {
  id: string;
  source_id: string;
  name: string | null;
  latitude: number;
  longitude: number;
  static_capabilities: string[];
  static_capacity: number | null;
  operational_version: number;
  accepting_state: HospitalAcceptingState;
  simulated_load_ratio: number | null;
  simulated_free_capacity: number | null;
  incoming_cases: number | null;
  operational_freshness_status: FreshnessStatus;
  static_provenance: Record<string, unknown>;
  operational_provenance: Record<string, unknown>;
}

export interface HospitalOptionRead {
  option_id: string;
  option_set_id: string;
  option_version: number;
  rank: number;
  hospital: HospitalRead;
  route: Record<string, unknown>;
  score: number;
  score_breakdown: Record<string, unknown>;
  provenance: Record<string, unknown>;
}

export interface HospitalOptionsResponse {
  incident_id: string;
  plan_id: string;
  incident_version: number;
  plan_version: number;
  option_set_id: string;
  option_set_version: number;
  transport_required: boolean;
  required_hospital_capabilities: string[];
  options: HospitalOptionRead[];
  excluded_hospitals: Record<string, unknown>[];
  generated_at: string;
  provenance: Record<string, unknown>;
}

export interface HospitalDestinationRead {
  id: string;
  incident_id: string;
  plan_id: string;
  option_set_id: string;
  hospital_id: string;
  status: string;
  incident_version: number;
  plan_version: number;
  selected_at: string;
  provenance: Record<string, unknown>;
}

export interface HospitalPreAlertRead {
  id: string;
  incident_id: string;
  plan_id: string;
  destination_id: string;
  status: HospitalPreAlertStatus;
  payload: Record<string, unknown>;
  requested_at: string;
  sent_at: string | null;
  acknowledged_at: string | null;
  failed_at: string | null;
  failure_reason: string | null;
  data_reality: DataReality;
  provenance: Record<string, unknown>;
}

export interface CorridorSignalRead {
  signal_id: string;
  latitude: number;
  longitude: number;
  distance_along_route_m: number;
  estimated_arrival_seconds: number;
  request_time: string | null;
  state: CorridorSignalState;
  provenance: Record<string, unknown>;
}

export interface CorridorRead {
  id: string;
  incident_id: string;
  plan_id: string;
  route_reference: string;
  route_geometry: Record<string, unknown>;
  signals: CorridorSignalRead[];
  state: CorridorSignalState;
  safety_lead_time_seconds: number;
  data_reality: DataReality;
  provenance: Record<string, unknown>;
  updated_at: string;
}

export interface DriverAlertRead {
  id: string;
  incident_id: string;
  plan_id: string;
  resource_id: string;
  route_reference: string;
  route_progress: number;
  geometry: Record<string, unknown> | null;
  created_at: string;
  expires_at: string;
  status: DriverAlertStatus;
  data_reality: DataReality;
  provenance: Record<string, unknown>;
}

export interface IncidentOperationalStateRead {
  incident_id: string;
  incident_version: number;
  plan_id: string | null;
  hospital_options: HospitalOptionsResponse | null;
  selected_destination: HospitalDestinationRead | null;
  hospital_pre_alert: HospitalPreAlertRead | null;
  corridor: CorridorRead | null;
  corridors: CorridorRead[];
  driver_alert: DriverAlertRead | null;
  driver_alerts: DriverAlertRead[];
}

export interface TrafficPrototypePolicyRead {
  refresh_interval_seconds: number;
  fresh_max_age_seconds: number;
  refresh_timeout_seconds: number;
  min_provider_confidence: number;
  max_geometry_separation_m: number;
  max_direction_difference_degrees: number;
}

export interface TrafficSnapshotRead {
  snapshot_id: string | null;
  version: number | null;
  provider_state: string | null;
  refresh_attempted_at: string | null;
  retrieved_at: string | null;
  provider_last_updated: string | null;
  freshness_status: FreshnessStatus;
  source: string;
  source_reference: string | null;
  data_reality: DataReality | null;
  flow_style: string;
  flow_zoom: number;
  units: string;
  observation_count: number;
  match_count: number;
  matched_edge_count: number;
  failure_reason: string | null;
  prototype_policy: TrafficPrototypePolicyRead;
}

export interface BenchmarkMetricSummary {
  total_count: number;
  available_count: number;
  missing_count: number;
  availability_rate: number;
  mean?: number;
  median?: number;
}

export interface BenchmarkEngineAggregate {
  count: number;
  outcome_counts: Record<string, number>;
  incident_eta_seconds: BenchmarkMetricSummary;
}

export interface BenchmarkValidationRead {
  case_id: string;
  scenario_id: string;
  passed: boolean;
}

export interface BenchmarkArtifactRead {
  aggregate: {
    baseline: BenchmarkEngineAggregate;
    sirengrid: BenchmarkEngineAggregate;
  };
  validation: BenchmarkValidationRead[];
  metadata: Record<string, unknown>;
  provenance: Record<string, unknown>;
}

export interface ReplanEvaluationRead {
  id: string;
  incident_id: string;
  active_plan_id: string;
  pending_plan_id: string | null;
  input_fingerprint: string;
  status: string;
  trigger_reasons: string[];
  input_references: Record<string, unknown>;
  explanation: Record<string, unknown>;
  first_triggered_at: string | null;
  last_triggered_at: string | null;
  debounce_until: string | null;
  evaluated_at: string | null;
  incident_version: number;
  idempotent: boolean;
}

export interface SimulationStatusRead {
  enabled: boolean;
  loaded_scenario_id: string | null;
  seed: number | null;
  runtime_version: number;
  event_index: number;
  last_event_type: string | null;
  reality: string;
}

export interface MapLayerResponse {
  layer: string;
  geojson: Record<string, unknown>;
  provenance: Record<string, unknown>;
}
