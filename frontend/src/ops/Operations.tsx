import { useState } from 'react';
import { Alert, Badge } from '../components';
import { useOperationsData } from '../state/OperationsContext';
import { DenseMap, MapControls, MapLegend, MapMarker, MapScale, projectCoordinate } from './DenseMap';
import { DecisionWorkspace } from './DecisionWorkspace';
import { IncidentRail, TimelineDock } from './workspace';
import { LEGEND, STATE_META, type DecisionTab, type OpsState, type OverlayKey } from '../data/mock';
import type { Incident } from '../api/types';

function incidentLocation(incident: Incident): string {
  const text = incident.location_text?.trim();
  if (text) return text;
  const latitude = incident.latitude;
  const longitude = incident.longitude;
  if (typeof latitude === 'number' && Number.isFinite(latitude) && typeof longitude === 'number' && Number.isFinite(longitude)) {
    return `${latitude.toFixed(4)}, ${longitude.toFixed(4)}`;
  }
  return 'Location unresolved';
}

function routeGeometry(plan: { routes: Record<string, unknown>[] } | null): Record<string, unknown> | null {
  const route = plan?.routes.find((item) => item.geometry || item.route_geometry);
  if (!route) return null;
  return (route.geometry || route.route_geometry) as Record<string, unknown>;
}

export function Operations({ initialState = 'idle' }: { initialState?: OpsState }) {
  const data = useOperationsData();
  const [state, setStateRaw] = useState<OpsState>(STATE_META[initialState] ? initialState : 'idle');
  const [tab, setTab] = useState<DecisionTab>(STATE_META[STATE_META[initialState] ? initialState : 'idle'].tab);
  const [dock, setDock] = useState(false);
  const [userOverlays, setUserOverlays] = useState<Partial<Record<OverlayKey, boolean>>>({});
  const incident = data.selectedIncident.data;
  const plans = data.plans.data ?? [];
  const activePlan = incident?.current_plan_id ? plans.find((plan) => plan.id === incident.current_plan_id) ?? null : null;
  const route = routeGeometry(activePlan);
  const overlays = { ...STATE_META[state].map.overlays, ...userOverlays };
  const setState = (next: OpsState) => { setStateRaw(next); setTab(STATE_META[next].tab); setUserOverlays({}); };
  const markerIncident = incident?.location ? projectCoordinate(incident.location) : null;
  const markerResources = (data.resources.data ?? []).filter((resource) => resource.assigned_incident_id === incident?.id || state === 'idle').slice(0, 8);
  const markerHospitals = data.operationalState.data?.hospital_options?.options.slice(0, 4) ?? [];

  return (
    <div style={{ flex: 1, display: 'flex', gap: 14, padding: 16, minHeight: 0 }}>
      <IncidentRail selected={data.selectedIncidentId ?? ''} setSelected={data.setSelectedIncidentId} state={state} setState={setState} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 }}>
        {data.incidents.error && <Alert tone="attention" title="Backend unavailable">{data.incidents.error}</Alert>}
        {data.actionError && <Alert tone="attention" title="Action not completed">{data.actionError}</Alert>}
        <div style={{ flex: 1, position: 'relative', borderRadius: 'var(--radius-lg)', overflow: 'hidden', border: '1px solid var(--color-border-hairline)', minHeight: 0 }}>
          <DenseMap view={STATE_META[state].map.view} overlays={overlays} route={STATE_META[state].map.route} backendMode routeGeometry={route}>
            {markerIncident && <MapMarker icon="triangle-alert" label={incident?.id ?? 'Incident'} sub={incident ? incidentLocation(incident) : 'Location unresolved'} tone="red" left={markerIncident.left} top={markerIncident.top} />}
            {markerResources.map((resource) => {
              const point = projectCoordinate({ lat: resource.latitude, lon: resource.longitude });
              return <MapMarker key={resource.id} icon={resource.resource_type === 'FIRE_RESCUE' ? 'truck' : 'ambulance'} label={resource.id} sub={resource.status.replaceAll('_', ' ')} tone="blue" left={point.left} top={point.top} />;
            })}
            {markerHospitals.map((option) => {
              const point = projectCoordinate({ lat: option.hospital.latitude, lon: option.hospital.longitude });
              return <MapMarker key={option.hospital.id} icon="hospital" label={option.hospital.name ?? option.hospital.id} sub={`Rank ${option.rank}`} tone="navy" left={point.left} top={point.top} />;
            })}
            <MapControls overlays={overlays} setOverlay={(key, value) => setUserOverlays((current) => ({ ...current, [key]: value }))} />
            <MapLegend items={LEGEND[state] ?? LEGEND.default} />
            <MapScale />
          </DenseMap>
          {!incident?.location && <div style={{ position: 'absolute', left: 18, bottom: 18 }}><Badge tone="neutral">Location unresolved · backend truth</Badge></div>}
        </div>
        <TimelineDock open={dock} setOpen={setDock} />
      </div>
      <DecisionWorkspace state={state} tab={tab} setTab={setTab} />
    </div>
  );
}
