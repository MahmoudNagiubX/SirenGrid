import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { ApiError } from '../api/client';
import {
  approvePlan,
  associateSocial,
  dismissSocial,
  generateCandidates,
  generateHospitalOptions,
  getBenchmark,
  getIncident,
  getOperationalState,
  getReplan,
  getSimulationStatus,
  getTrafficSnapshot,
  listHospitals,
  listIncidents,
  listPlans,
  listReports,
  listResources,
  listSocialSignals,
  listTimeline,
  loadSimulation,
  markSocialPossibleNew,
  refreshSocial,
  requestHospitalPreAlert,
  resetSimulation,
  selectHospitalDestination,
  triggerSimulationEvent,
  websocketUrl,
} from '../api/operations';
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
} from '../api/types';

export interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

const empty = <T,>(): AsyncState<T> => ({ data: null, loading: false, error: null });

export interface OperationsContextValue {
  incidents: AsyncState<Incident[]>;
  selectedIncident: AsyncState<Incident>;
  reports: AsyncState<Report[]>;
  timeline: AsyncState<TimelineEvent[]>;
  plans: AsyncState<ResponsePlan[]>;
  operationalState: AsyncState<OperationalState>;
  replan: AsyncState<ReplanState | null>;
  resources: AsyncState<Resource[]>;
  hospitals: AsyncState<Hospital[]>;
  traffic: AsyncState<TrafficSnapshot>;
  socialSignals: AsyncState<SocialSignal[]>;
  benchmark: AsyncState<BenchmarkArtifact>;
  simulation: AsyncState<SimulationStatus>;
  selectedIncidentId: string | null;
  setSelectedIncidentId: (id: string) => void;
  refreshAll: () => Promise<void>;
  refreshIncident: (id: string) => Promise<void>;
  actionBusy: string | null;
  actionError: string | null;
  clearActionError: () => void;
  runGenerateCandidates: () => Promise<void>;
  runApprovePlan: (plan: ResponsePlan) => Promise<void>;
  runGenerateHospitalOptions: () => Promise<void>;
  runSelectHospital: (hospitalId: string) => Promise<void>;
  runPreAlert: () => Promise<void>;
  runSocialRefresh: (provider?: 'bluesky' | 'synthetic') => Promise<void>;
  runSocialDismiss: (signalId: string) => Promise<void>;
  runSocialPossibleNew: (signalId: string) => Promise<void>;
  runSocialAssociate: (signalId: string) => Promise<void>;
  runSimulationReset: () => Promise<void>;
  runSimulationLoad: (scenarioId: string) => Promise<void>;
  runSimulationEvent: () => Promise<void>;
}

const OperationsContext = createContext<OperationsContextValue | null>(null);

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.detail;
  if (error instanceof Error) return error.message;
  return 'The backend returned an unexpected error.';
}

export function OperationsProvider({ children }: { children: ReactNode }) {
  const [incidents, setIncidents] = useState<AsyncState<Incident[]>>(empty);
  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(null);
  const [selectedIncident, setSelectedIncident] = useState<AsyncState<Incident>>(empty);
  const [reports, setReports] = useState<AsyncState<Report[]>>(empty);
  const [timeline, setTimeline] = useState<AsyncState<TimelineEvent[]>>(empty);
  const [plans, setPlans] = useState<AsyncState<ResponsePlan[]>>(empty);
  const [operationalState, setOperationalState] = useState<AsyncState<OperationalState>>(empty);
  const [replan, setReplan] = useState<AsyncState<ReplanState | null>>(empty);
  const [resources, setResources] = useState<AsyncState<Resource[]>>(empty);
  const [hospitals, setHospitals] = useState<AsyncState<Hospital[]>>(empty);
  const [traffic, setTraffic] = useState<AsyncState<TrafficSnapshot>>(empty);
  const [socialSignals, setSocialSignals] = useState<AsyncState<SocialSignal[]>>(empty);
  const [benchmark, setBenchmark] = useState<AsyncState<BenchmarkArtifact>>(empty);
  const [simulation, setSimulation] = useState<AsyncState<SimulationStatus>>(empty);
  const [actionBusy, setActionBusy] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const selectedRef = useRef<string | null>(null);

  const refreshIncident = useCallback(async (incidentId: string) => {
    selectedRef.current = incidentId;
    setSelectedIncident((state) => ({ ...state, loading: true, error: null }));
    setReports((state) => ({ ...state, loading: true, error: null }));
    setTimeline((state) => ({ ...state, loading: true, error: null }));
    setPlans((state) => ({ ...state, loading: true, error: null }));
    setOperationalState((state) => ({ ...state, loading: true, error: null }));
    setReplan((state) => ({ ...state, loading: true, error: null }));
    const [incidentResult, reportsResult, timelineResult, plansResult, stateResult, replanResult] = await Promise.allSettled([
      getIncident(incidentId),
      listReports(incidentId),
      listTimeline(incidentId),
      listPlans(incidentId),
      getOperationalState(incidentId),
      getReplan(incidentId),
    ]);
    if (selectedRef.current !== incidentId) return;
    setSelectedIncident(incidentResult.status === 'fulfilled' ? { data: incidentResult.value, loading: false, error: null } : { data: null, loading: false, error: errorMessage(incidentResult.reason) });
    setReports(reportsResult.status === 'fulfilled' ? { data: reportsResult.value, loading: false, error: null } : { data: null, loading: false, error: errorMessage(reportsResult.reason) });
    setTimeline(timelineResult.status === 'fulfilled' ? { data: timelineResult.value, loading: false, error: null } : { data: null, loading: false, error: errorMessage(timelineResult.reason) });
    setPlans(plansResult.status === 'fulfilled' ? { data: plansResult.value, loading: false, error: null } : { data: null, loading: false, error: errorMessage(plansResult.reason) });
    setOperationalState(stateResult.status === 'fulfilled' ? { data: stateResult.value, loading: false, error: null } : { data: null, loading: false, error: errorMessage(stateResult.reason) });
    setReplan(replanResult.status === 'fulfilled' ? { data: replanResult.value, loading: false, error: null } : { data: null, loading: false, error: errorMessage(replanResult.reason) });
  }, []);

  const refreshAll = useCallback(async () => {
    setIncidents((state) => ({ ...state, loading: true, error: null }));
    setResources((state) => ({ ...state, loading: true, error: null }));
    setHospitals((state) => ({ ...state, loading: true, error: null }));
    setTraffic((state) => ({ ...state, loading: true, error: null }));
    setSocialSignals((state) => ({ ...state, loading: true, error: null }));
    setBenchmark((state) => ({ ...state, loading: true, error: null }));
    setSimulation((state) => ({ ...state, loading: true, error: null }));
    const results = await Promise.allSettled([
      listIncidents(), listResources(), listHospitals(), getTrafficSnapshot(), listSocialSignals(), getBenchmark(), getSimulationStatus(),
    ]);
    const [incidentResult, resourceResult, hospitalResult, trafficResult, socialResult, benchmarkResult, simulationResult] = results;
    setIncidents(incidentResult.status === 'fulfilled' ? { data: incidentResult.value, loading: false, error: null } : { data: null, loading: false, error: errorMessage(incidentResult.reason) });
    setResources(resourceResult.status === 'fulfilled' ? { data: resourceResult.value, loading: false, error: null } : { data: null, loading: false, error: errorMessage(resourceResult.reason) });
    setHospitals(hospitalResult.status === 'fulfilled' ? { data: hospitalResult.value, loading: false, error: null } : { data: null, loading: false, error: errorMessage(hospitalResult.reason) });
    setTraffic(trafficResult.status === 'fulfilled' ? { data: trafficResult.value, loading: false, error: null } : { data: null, loading: false, error: errorMessage(trafficResult.reason) });
    setSocialSignals(socialResult.status === 'fulfilled' ? { data: socialResult.value, loading: false, error: null } : { data: null, loading: false, error: errorMessage(socialResult.reason) });
    setBenchmark(benchmarkResult.status === 'fulfilled' ? { data: benchmarkResult.value, loading: false, error: null } : { data: null, loading: false, error: errorMessage(benchmarkResult.reason) });
    setSimulation(simulationResult.status === 'fulfilled' ? { data: simulationResult.value, loading: false, error: null } : { data: null, loading: false, error: errorMessage(simulationResult.reason) });
    if (incidentResult.status === 'fulfilled') {
      const current = selectedRef.current;
      const next = current && incidentResult.value.some((incident) => incident.id === current) ? current : incidentResult.value[0]?.id ?? null;
      if (next !== selectedRef.current) setSelectedIncidentId(next);
      if (next) await refreshIncident(next);
    }
  }, [refreshIncident]);

  useEffect(() => { void refreshAll(); }, [refreshAll]);

  useEffect(() => {
    if (!selectedIncidentId) return;
    selectedRef.current = selectedIncidentId;
    void refreshIncident(selectedIncidentId);
  }, [refreshIncident, selectedIncidentId]);

  useEffect(() => {
    let socket: WebSocket | null = null;
    let reconnectTimer: number | undefined;
    let closed = false;
    const connect = () => {
      if (closed) return;
      try { socket = new WebSocket(websocketUrl()); } catch { return; }
      socket.onmessage = () => { void refreshAll(); };
      socket.onclose = () => { if (!closed) reconnectTimer = window.setTimeout(connect, 5000); };
    };
    connect();
    return () => { closed = true; if (reconnectTimer) window.clearTimeout(reconnectTimer); socket?.close(); };
  }, [refreshAll]);

  const run = useCallback(async (name: string, operation: () => Promise<void>) => {
    if (actionBusy) return;
    setActionBusy(name); setActionError(null);
    try { await operation(); } catch (error) { setActionError(errorMessage(error)); } finally { setActionBusy(null); }
  }, [actionBusy]);

  const runGenerateCandidates = useCallback(() => {
    if (!selectedIncidentId) return Promise.resolve();
    return run('generate-candidates', async () => { await generateCandidates(selectedIncidentId); await refreshAll(); });
  }, [refreshAll, run, selectedIncidentId]);
  const runApprovePlan = useCallback((plan: ResponsePlan) => {
    if (!selectedIncident.data) return Promise.resolve();
    return run('approve-plan', async () => { await approvePlan(plan, selectedIncident.data as Incident); await refreshAll(); });
  }, [refreshAll, run, selectedIncident.data]);
  const runGenerateHospitalOptions = useCallback(() => {
    if (!selectedIncidentId) return Promise.resolve();
    return run('hospital-options', async () => { await generateHospitalOptions(selectedIncidentId); await refreshIncident(selectedIncidentId); });
  }, [refreshIncident, run, selectedIncidentId]);
  const runSelectHospital = useCallback((hospitalId: string) => {
    if (!selectedIncident.data || !operationalState.data?.hospital_options) return Promise.resolve();
    return run('select-hospital', async () => { await selectHospitalDestination(selectedIncident.data as Incident, operationalState.data?.hospital_options as HospitalOptions, hospitalId); await refreshIncident((selectedIncident.data as Incident).id); });
  }, [operationalState.data, refreshIncident, run, selectedIncident.data]);
  const runPreAlert = useCallback(() => {
    if (!selectedIncident.data) return Promise.resolve();
    return run('pre-alert', async () => { await requestHospitalPreAlert(selectedIncident.data as Incident); await refreshIncident(selectedIncident.data?.id ?? ''); });
  }, [refreshIncident, run, selectedIncident.data]);
  const runSocialRefresh = useCallback((provider: 'bluesky' | 'synthetic' = 'synthetic') => run('social-refresh', async () => { await refreshSocial(provider); await refreshAll(); }), [refreshAll, run]);
  const runSocialDismiss = useCallback((signalId: string) => run('social-dismiss', async () => { await dismissSocial(signalId); await refreshAll(); }), [refreshAll, run]);
  const runSocialPossibleNew = useCallback((signalId: string) => run('social-possible-new', async () => { await markSocialPossibleNew(signalId); await refreshAll(); }), [refreshAll, run]);
  const runSocialAssociate = useCallback((signalId: string) => {
    if (!selectedIncident.data) return Promise.resolve();
    return run('social-associate', async () => { await associateSocial(signalId, selectedIncident.data as Incident); await refreshAll(); });
  }, [refreshAll, run, selectedIncident.data]);
  const runSimulationReset = useCallback(() => run('simulation-reset', async () => { await resetSimulation(); await refreshAll(); }), [refreshAll, run]);
  const runSimulationLoad = useCallback((scenarioId: string) => run('simulation-load', async () => { await loadSimulation(scenarioId); await refreshAll(); }), [refreshAll, run]);
  const runSimulationEvent = useCallback(() => run('simulation-event', async () => { await triggerSimulationEvent(); await refreshAll(); }), [refreshAll, run]);

  const value = useMemo<OperationsContextValue>(() => ({
    incidents, selectedIncident, reports, timeline, plans, operationalState, replan, resources, hospitals, traffic, socialSignals, benchmark, simulation,
    selectedIncidentId, setSelectedIncidentId: (id: string) => setSelectedIncidentId(id), refreshAll, refreshIncident,
    actionBusy, actionError, clearActionError: () => setActionError(null), runGenerateCandidates, runApprovePlan, runGenerateHospitalOptions,
    runSelectHospital, runPreAlert, runSocialRefresh, runSocialDismiss, runSocialPossibleNew, runSocialAssociate, runSimulationReset, runSimulationLoad, runSimulationEvent,
  }), [actionBusy, actionError, benchmark, hospitals, incidents, operationalState, plans, refreshAll, refreshIncident, replan, reports, resources, runApprovePlan, runGenerateCandidates, runGenerateHospitalOptions, runPreAlert, runSelectHospital, runSimulationEvent, runSimulationLoad, runSimulationReset, runSocialAssociate, runSocialDismiss, runSocialPossibleNew, runSocialRefresh, selectedIncident, selectedIncidentId, simulation, socialSignals, timeline, traffic]);

  return <OperationsContext.Provider value={value}>{children}</OperationsContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useOperationsData(): OperationsContextValue {
  const value = useContext(OperationsContext);
  if (!value) throw new Error('useOperationsData must be used inside OperationsProvider');
  return value;
}
