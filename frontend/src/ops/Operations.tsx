import { useState } from 'react';
import { DecisionWorkspace } from './DecisionWorkspace';
import { DenseMap, FacilityPin, MapControls, MapLegend, MapMarker, MapScale } from './DenseMap';
import { IncidentRail, TimelineDock } from './workspace';
import {
  FACILITIES,
  LEGEND,
  MARKERS,
  STATE_META,
  type DecisionTab,
  type OpsState,
  type OverlayKey,
} from '../data/mock';

import { useOperations } from '../state/OperationsContext';

/**
 * Ported from the `Operations` component in ui_kits/operations_center/index.html.
 *
 * One integrated workspace: incident rail + dense map hero + history dock + decision workspace.
 * Each operational state drives the map view, overlays, route rendering, markers, legend and the
 * default decision tab together.
 */
export function Operations({ initialState = 'idle' }: { initialState?: OpsState }) {
  const { selectedIncidentId, setSelectedIncidentId } = useOperations();
  const [state, setStateRaw] = useState<OpsState>(STATE_META[initialState] ? initialState : 'idle');
  const [tab, setTab] = useState<DecisionTab>(STATE_META[STATE_META[initialState] ? initialState : 'idle'].tab);
  const [dock, setDock] = useState(false);
  const [userOverlays, setUserOverlays] = useState<Partial<Record<OverlayKey, boolean>>>({});

  const setState = (s: OpsState) => {
    setStateRaw(s);
    setTab(STATE_META[s].tab);
    setUserOverlays({});
  };

  const meta = STATE_META[state];
  const overlays = { ...meta.map.overlays, ...userOverlays };
  const setOverlay = (k: OverlayKey, v: boolean) => setUserOverlays((o) => ({ ...o, [k]: v }));

  return (
    <div style={{ flex: 1, display: 'flex', gap: 14, padding: 16, minHeight: 0 }}>
      <IncidentRail selected={selectedIncidentId ?? ''} setSelected={(id) => setSelectedIncidentId(id)} state={state} setState={setState} />
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 }}>
        <div style={{ flex: 1, position: 'relative', borderRadius: 'var(--radius-lg)', overflow: 'hidden', border: '1px solid var(--color-border-hairline)', minHeight: 0 }}>
          <DenseMap view={meta.map.view} overlays={overlays} route={meta.map.route}>
            {(FACILITIES[meta.map.view] ?? []).map(([i, l, t, left, top], k) => (
              <FacilityPin key={'f' + k} icon={i} label={l} tone={t} left={left} top={top} />
            ))}
            {(MARKERS[state] ?? []).map(([i, l, s, t, left, top], k) => (
              <MapMarker key={k} icon={i} label={l} sub={s} tone={t} left={left} top={top} />
            ))}
            <MapControls overlays={overlays} setOverlay={setOverlay} />
            <MapLegend items={LEGEND[state] ?? LEGEND.default} />
            <MapScale />
          </DenseMap>
        </div>
        <TimelineDock open={dock} setOpen={setDock} />
      </div>
      <DecisionWorkspace state={state} tab={tab} setTab={setTab} />
    </div>
  );
}
