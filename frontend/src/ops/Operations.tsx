import { useCallback, useEffect, useMemo, useState, type CSSProperties } from 'react';
import { DecisionWorkspace } from './DecisionWorkspace';
import { MapControls, MapLegend, MapScale } from './DenseMap';
import { IncidentRail, TimelineDock } from './workspace';
import {
  LEGEND,
  STATE_META,
  type DecisionTab,
  type OpsState,
  type OverlayKey,
} from '../data/mock';

/**
 * P08-PRE-001: only the `coverage` map control is bound to a canonical production
 * layer (zones). Traffic / Corridor / Closures stay visible but disabled + OFF
 * with a truthful reason; they never activate legacy DenseMap SVG graphics.
 */
const MAP_CONTROL_NOT_BOUND = 'Not connected to a canonical map layer in this build';
const MAP_CONTROL_DISABLED: Partial<Record<OverlayKey, string>> = {
  traffic: MAP_CONTROL_NOT_BOUND,
  corridor: MAP_CONTROL_NOT_BOUND,
  closure: MAP_CONTROL_NOT_BOUND,
};

import { useOperations } from '../state/OperationsContext';
import { RealMapCanvas } from '../map/RealMapCanvas';
import type { RealMapMarker, RealMapOverlayState } from '../map/mapTypes';
import {
  buildRouteSet,
  resolveMapCenter,
  toHospitalMarkers,
  toIncidentMarker,
  toMapFeatureCollection,
  toResourceMarkers,
} from '../map/mapAdapters';
import { RecoveryNotice } from '../recovery/RecoveryNotice';
import { deriveRealtimeNotice } from '../recovery/recoveryTypes';

/**
 * Ported from the `Operations` component in ui_kits/operations_center/index.html.
 *
 * One integrated workspace: incident rail + map hero + history dock + decision workspace.
 * Phase 04B replaces the `DenseMap` SVG surface with the real MapLibre `RealMapCanvas`
 * bound to canonical backend map layers, markers and persisted plan route geometry. The
 * approved Operations Center chrome (controls / legend / scale, rail and workspace widths)
 * is preserved.
 */
export function Operations({ initialState = 'idle' }: { initialState?: OpsState }) {
  const {
    selectedIncidentId,
    setSelectedIncidentId,
    selectedIncident,
    resources,
    hospitals,
    plans,
    operationalState,
    replan,
    traffic,
    mapBoundary,
    mapRoads,
    mapZones,
    realtimeState,
    realtimeRecoveryReason,
    refreshGlobal,
    refreshSelectedIncident,
    refreshMapLayers,
  } = useOperations();

  const [state, setStateRaw] = useState<OpsState>(STATE_META[initialState] ? initialState : 'idle');
  const [tab, setTab] = useState<DecisionTab>(STATE_META[STATE_META[initialState] ? initialState : 'idle'].tab);
  const [dock, setDock] = useState(false);
  const [userOverlays, setUserOverlays] = useState<Partial<Record<OverlayKey, boolean>>>({});
  const [mapError, setMapError] = useState<string | null>(null);
  const [mapReady, setMapReady] = useState(false);

  const setState = (s: OpsState) => {
    setStateRaw(s);
    setTab(STATE_META[s].tab);
    setUserOverlays({});
  };

  const meta = STATE_META[state];
  const overlays = { ...meta.map.overlays, ...userOverlays };
  const setOverlay = (k: OverlayKey, v: boolean) => setUserOverlays((o) => ({ ...o, [k]: v }));

  const incident = selectedIncident.data;

  const boundaryFc = useMemo(
    () => toMapFeatureCollection(mapBoundary.data?.geojson),
    [mapBoundary.data],
  );
  const roadsFc = useMemo(
    () => toMapFeatureCollection(mapRoads.data?.geojson),
    [mapRoads.data],
  );
  const zonesFc = useMemo(
    () => toMapFeatureCollection(mapZones.data?.geojson),
    [mapZones.data],
  );

  const markers = useMemo<RealMapMarker[]>(() => {
    const list: RealMapMarker[] = [];
    const incidentMarker = toIncidentMarker(incident);
    if (incidentMarker) list.push(incidentMarker);
    list.push(
      ...toResourceMarkers(
        resources.data ?? [],
        selectedIncidentId,
        operationalState.data?.responder_tracking ?? [],
      ),
    );
    list.push(...toHospitalMarkers(hospitals.data ?? []));
    return list;
  }, [incident, resources.data, hospitals.data, selectedIncidentId, operationalState.data]);

  const routes = useMemo(
    () =>
      buildRouteSet({
        opsState: state,
        incident: incident ?? null,
        plans: plans.data ?? [],
        replan: replan.data ?? null,
      }),
    [state, incident, plans.data, replan.data],
  );

  const center = useMemo(() => resolveMapCenter(incident), [incident]);

  // The backend owns the deterministic responder projection. Reconcile it at
  // a bounded interval while an approved response is active; no browser-side
  // route interpolation or ETA calculation is performed.
  useEffect(() => {
    if (!incident?.current_plan_id) return;
    const timer = window.setInterval(() => {
      void refreshSelectedIncident(incident.id);
    }, 15_000);
    return () => window.clearInterval(timer);
  }, [incident?.id, incident?.current_plan_id, refreshSelectedIncident]);

  // UI overlay keys → renderer layer visibility. `coverage` drives the zones layer;
  // boundary and roads stay visible whenever their backend layer is available. The
  // traffic / corridor / closure controls remain present but do not yet drive a
  // truthful real layer, so they are intentionally not mapped here.
  const rendererOverlays = useMemo<RealMapOverlayState>(
    () => ({
      zones: overlays.coverage === true,
      boundary: true,
      roads: true,
    }),
    [overlays.coverage],
  );

  const handleMapError = useCallback((message: string) => {
    setMapError(message);
  }, []);
  const handleMapReady = useCallback(() => {
    setMapReady(true);
  }, []);

  // §15–19: one truthful realtime/connectivity notice derived from transport state.
  const realtimeNotice = useMemo(
    () => deriveRealtimeNotice({ state: realtimeState, recoveryReason: realtimeRecoveryReason }),
    [realtimeState, realtimeRecoveryReason],
  );
  // §16 / P08-PRE-004: explicit REST reconciliation only — never touches the
  // socket, never writes. Deterministic order: global reads first (they can
  // resolve which incident is selected), then the selected incident's domains.
  const handleRefreshData = useCallback(async () => {
    await refreshGlobal({ includeSelected: false });
    if (selectedIncidentId) await refreshSelectedIncident(selectedIncidentId);
  }, [refreshGlobal, refreshSelectedIncident, selectedIncidentId]);
  const realtimeRetry =
    realtimeNotice && (realtimeNotice.kind === 'DISCONNECTED' || realtimeNotice.kind === 'RECONNECTING')
      ? handleRefreshData
      : undefined;

  // §33/§34: domain-specific traffic freshness truth — no local age calculation.
  const trafficFreshness = traffic.data?.freshness_status;
  const trafficNotice = traffic.error != null ? (
    <RecoveryNotice
      kind="UNAVAILABLE"
      title="Traffic snapshot unavailable"
      detail="Current routing is not labelled live. Backend routing policy still applies."
      compact
      onRetry={() => void refreshGlobal({ includeSelected: false })}
      retryLabel="Refresh data"
    />
  ) : trafficFreshness === 'STALE' ? (
    <RecoveryNotice
      kind="STALE"
      title="Traffic data stale"
      detail="Routing continues to use backend-authoritative fallback/freshness policy."
      compact
    />
  ) : trafficFreshness === 'UNKNOWN' ? (
    <RecoveryNotice kind="UNKNOWN" title="Traffic freshness unknown" compact />
  ) : null;

  // §35: a failed SirenGrid map layer does not fall back to DenseMap — the OSM
  // basemap and any layers that did load stay; one compact notice covers it.
  const mapLayerError =
    mapBoundary.error != null || mapRoads.error != null || mapZones.error != null;

  return (
    <div style={{ flex: 1, display: 'flex', gap: 14, padding: 16, minHeight: 0 }}>
      <IncidentRail selected={selectedIncidentId ?? ''} setSelected={(id) => setSelectedIncidentId(id)} state={state} setState={setState} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 }}>
        {(realtimeNotice || trafficNotice) && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {realtimeNotice && (
              <RecoveryNotice
                kind={realtimeNotice.kind}
                title={realtimeNotice.title}
                detail={realtimeNotice.detail}
                compact={realtimeNotice.compact}
                onRetry={realtimeRetry}
                retryLabel="Refresh data"
              />
            )}
            {trafficNotice}
          </div>
        )}
        <div style={{ flex: 1, position: 'relative', borderRadius: 'var(--radius-lg)', overflow: 'hidden', border: '1px solid var(--color-border-hairline)', minHeight: 0, background: 'var(--map-land)' }}>
          <RealMapCanvas
            boundary={boundaryFc}
            roads={roadsFc}
            zones={zonesFc}
            markers={markers}
            routes={routes}
            center={center}
            overlays={rendererOverlays}
            onReady={handleMapReady}
            onError={handleMapError}
          />
          {(!mapReady && !mapError) || mapError || mapLayerError ? (
            <div style={mapOverlayStackStyle}>
              {!mapReady && !mapError && (
                <RecoveryNotice kind="LOADING" title="Loading map…" compact />
              )}
              {mapError && (
                <RecoveryNotice
                  kind="UNAVAILABLE"
                  title="Map unavailable"
                  detail={mapError && mapError.length <= 120 ? mapError : undefined}
                  compact
                />
              )}
              {mapLayerError && (
                <RecoveryNotice
                  kind="UNAVAILABLE"
                  title="One or more SirenGrid map layers are unavailable"
                  detail="The base map and available layers still render."
                  compact
                  onRetry={() => void refreshMapLayers()}
                  retryLabel="Refresh data"
                />
              )}
            </div>
          ) : null}
          <MapControls overlays={overlays} setOverlay={setOverlay} disabledKeys={MAP_CONTROL_DISABLED} />
          <MapLegend items={LEGEND[state] ?? LEGEND.default} />
          <MapScale />
        </div>
        <TimelineDock open={dock} setOpen={setDock} />
      </div>
      <DecisionWorkspace state={state} tab={tab} setTab={setTab} setState={setState} />
    </div>
  );
}

const mapOverlayStackStyle: CSSProperties = {
  position: 'absolute',
  top: 12,
  left: 12,
  right: 12,
  display: 'flex',
  flexDirection: 'column',
  gap: 8,
  zIndex: 3,
};
