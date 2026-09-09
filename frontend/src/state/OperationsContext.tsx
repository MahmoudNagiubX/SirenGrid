import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { ApiError } from '../api/client';
import {
  getHealth,
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
  listTimeline,
} from '../api/operations';
import type {
  HealthRead,
  HospitalRead,
  IncidentOperationalStateRead,
  IncidentRead,
  ReplanEvaluationRead,
  ReportRead,
  ResourceRead,
  ResponsePlanRead,
  SimulationStatusRead,
  TimelineEventRead,
  TrafficSnapshotRead,
} from '../api/types';

export interface AsyncState<T> {
  data: T | null;
  loading: boolean;
  error: ApiError | null;
}

const emptyState = <T,>(): AsyncState<T> => ({
  data: null,
  loading: false,
  error: null,
});

function toApiError(reason: unknown): ApiError {
  if (reason instanceof ApiError) return reason;
  if (reason instanceof Error) return new ApiError(0, reason.message);
  return new ApiError(0, 'Unexpected error occurred.');
}

export interface OperationsContextValue {
  health: AsyncState<HealthRead>;
  incidents: AsyncState<IncidentRead[]>;
  resources: AsyncState<ResourceRead[]>;
  hospitals: AsyncState<HospitalRead[]>;
  traffic: AsyncState<TrafficSnapshotRead>;
  simulation: AsyncState<SimulationStatusRead>;

  selectedIncidentId: string | null;
  selectedIncident: AsyncState<IncidentRead>;
  reports: AsyncState<ReportRead[]>;
  timeline: AsyncState<TimelineEventRead[]>;
  plans: AsyncState<ResponsePlanRead[]>;
  operationalState: AsyncState<IncidentOperationalStateRead>;
  replan: AsyncState<ReplanEvaluationRead | null>;

  setSelectedIncidentId: (id: string | null) => void;
  refreshGlobal: () => Promise<void>;
  refreshSelectedIncident: (id?: string) => Promise<void>;
}

const OperationsContext = createContext<OperationsContextValue | null>(null);

export function OperationsProvider({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<AsyncState<HealthRead>>(emptyState);
  const [incidents, setIncidents] = useState<AsyncState<IncidentRead[]>>(emptyState);
  const [resources, setResources] = useState<AsyncState<ResourceRead[]>>(emptyState);
  const [hospitals, setHospitals] = useState<AsyncState<HospitalRead[]>>(emptyState);
  const [traffic, setTraffic] = useState<AsyncState<TrafficSnapshotRead>>(emptyState);
  const [simulation, setSimulation] = useState<AsyncState<SimulationStatusRead>>(emptyState);

  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(null);
  const [selectedIncident, setSelectedIncident] = useState<AsyncState<IncidentRead>>(emptyState);
  const [reports, setReports] = useState<AsyncState<ReportRead[]>>(emptyState);
  const [timeline, setTimeline] = useState<AsyncState<TimelineEventRead[]>>(emptyState);
  const [plans, setPlans] = useState<AsyncState<ResponsePlanRead[]>>(emptyState);
  const [operationalState, setOperationalState] = useState<AsyncState<IncidentOperationalStateRead>>(emptyState);
  const [replan, setReplan] = useState<AsyncState<ReplanEvaluationRead | null>>(emptyState);

  const selectedRef = useRef<string | null>(null);

  const refreshSelectedIncident = useCallback(async (targetId?: string) => {
    const incidentId = targetId ?? selectedIncidentId;
    if (!incidentId) {
      selectedRef.current = null;
      setSelectedIncident(emptyState());
      setReports(emptyState());
      setTimeline(emptyState());
      setPlans(emptyState());
      setOperationalState(emptyState());
      setReplan(emptyState());
      return;
    }

    selectedRef.current = incidentId;
    setSelectedIncident((s) => ({ ...s, loading: true, error: null }));
    setReports((s) => ({ ...s, loading: true, error: null }));
    setTimeline((s) => ({ ...s, loading: true, error: null }));
    setPlans((s) => ({ ...s, loading: true, error: null }));
    setOperationalState((s) => ({ ...s, loading: true, error: null }));
    setReplan((s) => ({ ...s, loading: true, error: null }));

    const [incRes, repRes, timeRes, planRes, opRes, replanRes] = await Promise.allSettled([
      getIncident(incidentId),
      listReports(incidentId),
      listTimeline(incidentId),
      listPlans(incidentId),
      getOperationalState(incidentId),
      getReplan(incidentId),
    ]);

    if (selectedRef.current !== incidentId) return;

    setSelectedIncident(
      incRes.status === 'fulfilled'
        ? { data: incRes.value, loading: false, error: null }
        : { data: null, loading: false, error: toApiError(incRes.reason) },
    );
    setReports(
      repRes.status === 'fulfilled'
        ? { data: repRes.value, loading: false, error: null }
        : { data: null, loading: false, error: toApiError(repRes.reason) },
    );
    setTimeline(
      timeRes.status === 'fulfilled'
        ? { data: timeRes.value, loading: false, error: null }
        : { data: null, loading: false, error: toApiError(timeRes.reason) },
    );
    setPlans(
      planRes.status === 'fulfilled'
        ? { data: planRes.value, loading: false, error: null }
        : { data: null, loading: false, error: toApiError(planRes.reason) },
    );
    setOperationalState(
      opRes.status === 'fulfilled'
        ? { data: opRes.value, loading: false, error: null }
        : { data: null, loading: false, error: toApiError(opRes.reason) },
    );
    setReplan(
      replanRes.status === 'fulfilled'
        ? { data: replanRes.value, loading: false, error: null }
        : { data: null, loading: false, error: toApiError(replanRes.reason) },
    );
  }, [selectedIncidentId]);

  const refreshGlobal = useCallback(async () => {
    setHealth((s) => ({ ...s, loading: true, error: null }));
    setIncidents((s) => ({ ...s, loading: true, error: null }));
    setResources((s) => ({ ...s, loading: true, error: null }));
    setHospitals((s) => ({ ...s, loading: true, error: null }));
    setTraffic((s) => ({ ...s, loading: true, error: null }));
    setSimulation((s) => ({ ...s, loading: true, error: null }));

    const [hRes, incRes, resRes, hospRes, trafRes, simRes] = await Promise.allSettled([
      getHealth(),
      listIncidents(),
      listResources(),
      listHospitals(),
      getTrafficSnapshot(),
      getSimulationStatus(),
    ]);

    setHealth(
      hRes.status === 'fulfilled'
        ? { data: hRes.value, loading: false, error: null }
        : { data: null, loading: false, error: toApiError(hRes.reason) },
    );
    setIncidents(
      incRes.status === 'fulfilled'
        ? { data: incRes.value, loading: false, error: null }
        : { data: null, loading: false, error: toApiError(incRes.reason) },
    );
    setResources(
      resRes.status === 'fulfilled'
        ? { data: resRes.value, loading: false, error: null }
        : { data: null, loading: false, error: toApiError(resRes.reason) },
    );
    setHospitals(
      hospRes.status === 'fulfilled'
        ? { data: hospRes.value, loading: false, error: null }
        : { data: null, loading: false, error: toApiError(hospRes.reason) },
    );
    setTraffic(
      trafRes.status === 'fulfilled'
        ? { data: trafRes.value, loading: false, error: null }
        : { data: null, loading: false, error: toApiError(trafRes.reason) },
    );
    setSimulation(
      simRes.status === 'fulfilled'
        ? { data: simRes.value, loading: false, error: null }
        : { data: null, loading: false, error: toApiError(simRes.reason) },
    );

    let nextId: string | null = null;
    if (incRes.status === 'fulfilled') {
      const list = incRes.value;
      const cur = selectedRef.current;
      if (cur && list.some((i) => i.id === cur)) {
        nextId = cur;
      } else {
        nextId = list[0]?.id ?? null;
      }
    }
    setSelectedIncidentId(nextId);
    selectedRef.current = nextId;
    if (nextId) {
      await refreshSelectedIncident(nextId);
    } else {
      setSelectedIncident(emptyState());
      setReports(emptyState());
      setTimeline(emptyState());
      setPlans(emptyState());
      setOperationalState(emptyState());
      setReplan(emptyState());
    }
  }, [refreshSelectedIncident]);

  useEffect(() => {
    void refreshGlobal();
  }, [refreshGlobal]);

  useEffect(() => {
    if (selectedIncidentId && selectedIncidentId !== selectedRef.current) {
      selectedRef.current = selectedIncidentId;
      void refreshSelectedIncident(selectedIncidentId);
    }
  }, [selectedIncidentId, refreshSelectedIncident]);

  const value = useMemo<OperationsContextValue>(
    () => ({
      health,
      incidents,
      resources,
      hospitals,
      traffic,
      simulation,
      selectedIncidentId,
      selectedIncident,
      reports,
      timeline,
      plans,
      operationalState,
      replan,
      setSelectedIncidentId,
      refreshGlobal,
      refreshSelectedIncident,
    }),
    [
      health,
      incidents,
      resources,
      hospitals,
      traffic,
      simulation,
      selectedIncidentId,
      selectedIncident,
      reports,
      timeline,
      plans,
      operationalState,
      replan,
      refreshGlobal,
      refreshSelectedIncident,
    ],
  );

  return <OperationsContext.Provider value={value}>{children}</OperationsContext.Provider>;
}

// eslint-disable-next-line react-refresh/only-export-components
export function useOperations(): OperationsContextValue {
  const context = useContext(OperationsContext);
  if (!context) {
    throw new Error('useOperations must be used within an OperationsProvider');
  }
  return context;
}
