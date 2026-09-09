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
  getMapBoundary,
  getMapRoads,
  getMapZones,
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
  MapLayerResponse,
  ReplanEvaluationRead,
  ReportRead,
  ResourceRead,
  ResponsePlanRead,
  SimulationStatusRead,
  TimelineEventRead,
  TrafficSnapshotRead,
} from '../api/types';
import { OperationsSocketClient } from '../realtime/operationsSocket';
import type {
  OperationsEventEnvelope,
  OperationsRecoveryNotice,
  OperationsRecoveryReason,
  OperationsSocketState,
} from '../realtime/types';

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

  mapBoundary: AsyncState<MapLayerResponse>;
  mapRoads: AsyncState<MapLayerResponse>;
  mapZones: AsyncState<MapLayerResponse>;

  selectedIncidentId: string | null;
  selectedIncident: AsyncState<IncidentRead>;
  reports: AsyncState<ReportRead[]>;
  timeline: AsyncState<TimelineEventRead[]>;
  plans: AsyncState<ResponsePlanRead[]>;
  operationalState: AsyncState<IncidentOperationalStateRead>;
  replan: AsyncState<ReplanEvaluationRead | null>;

  /**
   * Read-only realtime transport metadata for Phase 07 recovery UI.
   * The WebSocket is an invalidation signal only; REST/database state stays
   * canonical. The socket instance is intentionally not exposed.
   */
  realtimeState: OperationsSocketState;
  realtimeLastVersion: number | null;
  realtimeLastEventAt: string | null;
  realtimeRecoveryReason: OperationsRecoveryReason | null;

  setSelectedIncidentId: (id: string | null) => void;
  refreshGlobal: (options?: { includeSelected?: boolean }) => Promise<void>;
  refreshSelectedIncident: (id?: string) => Promise<void>;
  refreshMapLayers: () => Promise<void>;
}

/** Coalesced reconciliation intent accumulated between REST refresh runs. */
interface ReconcileNeed {
  /** A recovery event (reconnect / gap / reset / malformed) demands a full reconciliation. */
  recovery: boolean;
  /** The selected incident's detail domains should be refreshed as well. */
  selected: boolean;
}

/** Short window to fold a burst of envelopes into a single reconciliation run. */
const RECONCILE_DEBOUNCE_MS = 100;

const OperationsContext = createContext<OperationsContextValue | null>(null);

export function OperationsProvider({ children }: { children: ReactNode }) {
  const [health, setHealth] = useState<AsyncState<HealthRead>>(emptyState);
  const [incidents, setIncidents] = useState<AsyncState<IncidentRead[]>>(emptyState);
  const [resources, setResources] = useState<AsyncState<ResourceRead[]>>(emptyState);
  const [hospitals, setHospitals] = useState<AsyncState<HospitalRead[]>>(emptyState);
  const [traffic, setTraffic] = useState<AsyncState<TrafficSnapshotRead>>(emptyState);
  const [simulation, setSimulation] = useState<AsyncState<SimulationStatusRead>>(emptyState);

  const [mapBoundary, setMapBoundary] = useState<AsyncState<MapLayerResponse>>(emptyState);
  const [mapRoads, setMapRoads] = useState<AsyncState<MapLayerResponse>>(emptyState);
  const [mapZones, setMapZones] = useState<AsyncState<MapLayerResponse>>(emptyState);

  const [selectedIncidentId, setSelectedIncidentId] = useState<string | null>(null);
  const [selectedIncident, setSelectedIncident] = useState<AsyncState<IncidentRead>>(emptyState);
  const [reports, setReports] = useState<AsyncState<ReportRead[]>>(emptyState);
  const [timeline, setTimeline] = useState<AsyncState<TimelineEventRead[]>>(emptyState);
  const [plans, setPlans] = useState<AsyncState<ResponsePlanRead[]>>(emptyState);
  const [operationalState, setOperationalState] = useState<AsyncState<IncidentOperationalStateRead>>(emptyState);
  const [replan, setReplan] = useState<AsyncState<ReplanEvaluationRead | null>>(emptyState);

  const [realtimeState, setRealtimeState] = useState<OperationsSocketState>('IDLE');
  const [realtimeLastVersion, setRealtimeLastVersion] = useState<number | null>(null);
  const [realtimeLastEventAt, setRealtimeLastEventAt] = useState<string | null>(null);
  const [realtimeRecoveryReason, setRealtimeRecoveryReason] =
    useState<OperationsRecoveryReason | null>(null);

  const selectedRef = useRef<string | null>(null);

  // Realtime reconciliation engine — refs only, never operational payload.
  const socketRef = useRef<OperationsSocketClient | null>(null);
  const realtimeStoppedRef = useRef(false);
  const reconcileRunningRef = useRef(false);
  const reconcilePendingRef = useRef<ReconcileNeed | null>(null);
  const reconcileDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const recoveryJustEmittedRef = useRef(false);
  const refreshGlobalRef = useRef<
    (options?: { includeSelected?: boolean }) => Promise<void>
  >(async () => {});
  const refreshSelectedRef = useRef<(id?: string) => Promise<void>>(async () => {});

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

  const refreshGlobal = useCallback(async (options?: { includeSelected?: boolean }) => {
    const includeSelected = options?.includeSelected !== false;
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
      if (includeSelected) {
        await refreshSelectedIncident(nextId);
      }
    } else {
      setSelectedIncident(emptyState());
      setReports(emptyState());
      setTimeline(emptyState());
      setPlans(emptyState());
      setOperationalState(emptyState());
      setReplan(emptyState());
    }
  }, [refreshSelectedIncident]);

  const refreshMapLayers = useCallback(async () => {
    setMapBoundary((s) => ({ ...s, loading: true, error: null }));
    setMapRoads((s) => ({ ...s, loading: true, error: null }));
    setMapZones((s) => ({ ...s, loading: true, error: null }));

    const [boundaryRes, roadsRes, zonesRes] = await Promise.allSettled([
      getMapBoundary(),
      getMapRoads(),
      getMapZones(),
    ]);

    setMapBoundary(
      boundaryRes.status === 'fulfilled'
        ? { data: boundaryRes.value, loading: false, error: null }
        : { data: null, loading: false, error: toApiError(boundaryRes.reason) },
    );
    setMapRoads(
      roadsRes.status === 'fulfilled'
        ? { data: roadsRes.value, loading: false, error: null }
        : { data: null, loading: false, error: toApiError(roadsRes.reason) },
    );
    setMapZones(
      zonesRes.status === 'fulfilled'
        ? { data: zonesRes.value, loading: false, error: null }
        : { data: null, loading: false, error: toApiError(zonesRes.reason) },
    );
  }, []);

  // Keep latest REST reconcilers reachable from the realtime engine without
  // re-subscribing the socket when the selected incident changes.
  refreshGlobalRef.current = refreshGlobal;
  refreshSelectedRef.current = refreshSelectedIncident;

  const runReconcileOnce = useCallback(async (need: ReconcileNeed) => {
    if (realtimeStoppedRef.current) return;
    if (need.recovery) {
      // Full operational REST reconciliation (section 18): global + selected.
      await refreshGlobalRef.current();
      if (realtimeStoppedRef.current) return;
      const current = selectedRef.current;
      if (current) await refreshSelectedRef.current(current);
      return;
    }
    // Normal envelope: always refresh global operational reads; refresh the
    // selected incident's detail domains only when the event targets it.
    await refreshGlobalRef.current({ includeSelected: need.selected });
  }, []);

  const drainReconcile = useCallback(async () => {
    if (reconcileRunningRef.current || realtimeStoppedRef.current) return;
    reconcileRunningRef.current = true;
    try {
      while (!realtimeStoppedRef.current && reconcilePendingRef.current) {
        const need = reconcilePendingRef.current;
        reconcilePendingRef.current = null;
        await runReconcileOnce(need);
      }
    } finally {
      reconcileRunningRef.current = false;
    }
  }, [runReconcileOnce]);

  // Coalesce a burst of realtime signals into a single reconciliation at a
  // time, with one "pending again" merge for events that arrive mid-run.
  const requestReconcile = useCallback(
    (need: ReconcileNeed) => {
      if (realtimeStoppedRef.current) return;
      const prev = reconcilePendingRef.current;
      reconcilePendingRef.current = prev
        ? { recovery: prev.recovery || need.recovery, selected: prev.selected || need.selected }
        : need;
      if (reconcileRunningRef.current || reconcileDebounceRef.current !== null) return;
      reconcileDebounceRef.current = setTimeout(() => {
        reconcileDebounceRef.current = null;
        void drainReconcile();
      }, RECONCILE_DEBOUNCE_MS);
    },
    [drainReconcile],
  );

  const handleRealtimeEnvelope = useCallback(
    (envelope: OperationsEventEnvelope) => {
      if (realtimeStoppedRef.current) return;
      setRealtimeLastVersion(envelope.version);
      setRealtimeLastEventAt(envelope.timestamp);
      // A contiguous normal envelope clears a stale recovery reason; an
      // envelope delivered alongside a gap/reset notice keeps it visible.
      if (recoveryJustEmittedRef.current) {
        recoveryJustEmittedRef.current = false;
      } else {
        setRealtimeRecoveryReason(null);
      }
      const current = selectedRef.current;
      const targetsSelected =
        current !== null &&
        (envelope.incident_id === null || envelope.incident_id === current);
      // Payload is never trusted as state — the event only schedules REST.
      requestReconcile({ recovery: false, selected: targetsSelected });
    },
    [requestReconcile],
  );

  const handleRealtimeRecovery = useCallback(
    (notice: OperationsRecoveryNotice) => {
      if (realtimeStoppedRef.current) return;
      recoveryJustEmittedRef.current = true;
      setRealtimeRecoveryReason(notice.reason);
      requestReconcile({ recovery: true, selected: true });
    },
    [requestReconcile],
  );

  // Exactly one OperationsSocketClient per mounted provider instance.
  useEffect(() => {
    realtimeStoppedRef.current = false;
    const client = new OperationsSocketClient({
      onStateChange: (next) => {
        if (!realtimeStoppedRef.current) setRealtimeState(next);
      },
      onEnvelope: handleRealtimeEnvelope,
      onRecoveryRequired: handleRealtimeRecovery,
    });
    socketRef.current = client;
    client.start();

    return () => {
      realtimeStoppedRef.current = true;
      client.stop();
      if (socketRef.current === client) socketRef.current = null;
      if (reconcileDebounceRef.current !== null) {
        clearTimeout(reconcileDebounceRef.current);
        reconcileDebounceRef.current = null;
      }
      reconcilePendingRef.current = null;
      recoveryJustEmittedRef.current = false;
    };
  }, [handleRealtimeEnvelope, handleRealtimeRecovery]);

  useEffect(() => {
    void refreshGlobal();
  }, [refreshGlobal]);

  // Static/derived map layers: fetch once on provider mount, independent of
  // incident selection. No polling, no automatic retry.
  useEffect(() => {
    void refreshMapLayers();
  }, [refreshMapLayers]);

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
      mapBoundary,
      mapRoads,
      mapZones,
      selectedIncidentId,
      selectedIncident,
      reports,
      timeline,
      plans,
      operationalState,
      replan,
      realtimeState,
      realtimeLastVersion,
      realtimeLastEventAt,
      realtimeRecoveryReason,
      setSelectedIncidentId,
      refreshGlobal,
      refreshSelectedIncident,
      refreshMapLayers,
    }),
    [
      health,
      incidents,
      resources,
      hospitals,
      traffic,
      simulation,
      mapBoundary,
      mapRoads,
      mapZones,
      selectedIncidentId,
      selectedIncident,
      reports,
      timeline,
      plans,
      operationalState,
      replan,
      realtimeState,
      realtimeLastVersion,
      realtimeLastEventAt,
      realtimeRecoveryReason,
      refreshGlobal,
      refreshSelectedIncident,
      refreshMapLayers,
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
