import { useCallback, useMemo, useState, type CSSProperties } from 'react';
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
    replan,
    mapBoundary,
    mapRoads,
    mapZones,
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
    list.push(...toResourceMarkers(resources.data ?? [], selectedIncidentId));
    list.push(...toHospitalMarkers(hospitals.data ?? []));
    return list;
  }, [incident, resources.data, hospitals.data, selectedIncidentId]);

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

  return (
    <div style={{ flex: 1, display: 'flex', gap: 14, padding: 16, minHeight: 0 }}>
      <IncidentRail selected={selectedIncidentId ?? ''} setSelected={(id) => setSelectedIncidentId(id)} state={state} setState={setState} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 }}>
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
          {!mapReady && !mapError && (
            <div style={mapNoticeStyle} role="status">Loading map…</div>
          )}
          {mapError && (
            <div style={mapNoticeStyle} role="status">Map unavailable</div>
          )}
          <MapControls overlays={overlays} setOverlay={setOverlay} />
          <MapLegend items={LEGEND[state] ?? LEGEND.default} />
          <MapScale />
        </div>
        <TimelineDock open={dock} setOpen={setDock} />
      </div>
      <DecisionWorkspace state={state} tab={tab} setTab={setTab} />
    </div>
  );
}

const mapNoticeStyle: CSSProperties = {
  position: 'absolute',
  top: 16,
  left: 16,
  padding: '5px 11px',
  borderRadius: 'var(--radius-pill)',
  fontFamily: 'var(--font-en)',
  fontSize: 12.5,
  fontWeight: 600,
  color: 'var(--color-text-secondary)',
  background: 'var(--color-bg-glass-strong)',
  border: '0.5px solid var(--color-border-hairline)',
  backdropFilter: 'blur(var(--blur-glass-light))',
  zIndex: 2,
};
