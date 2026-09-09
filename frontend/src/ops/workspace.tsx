import { Fragment } from 'react';
import { Badge, GlassPanel, IconTile, Input } from '../components';
import { Ico } from '../lib/icon';
import { useOperationsData } from '../state/OperationsContext';
import type { Incident } from '../api/types';
import { STATES, TOP_NAV, type OpsState, type TopNav } from '../data/mock';
import { Prov } from './primitives';

function severity(value: string): 'low' | 'moderate' | 'high' | 'critical' {
  const normalized = value.toLowerCase();
  return normalized === 'critical' || normalized === 'high' || normalized === 'moderate' ? normalized : 'low';
}

function time(value: string | null): string {
  if (!value) return 'Unknown time';
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

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

export function StatusStrip({ nav, setNav }: { nav: TopNav; setNav: (n: TopNav) => void }) {
  const { incidents, resources, traffic } = useOperationsData();
  const openCount = incidents.data?.filter((incident) => !['CLOSED', 'CANCELLED_FALSE_REPORT', 'DUPLICATE_MERGED'].includes(incident.status)).length;
  const available = resources.data?.filter((resource) => resource.status === 'AVAILABLE').length;
  const trafficReality = traffic.data?.data_reality ?? 'UNKNOWN';
  return (
    <div style={{ height: 62, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 20px', background: 'var(--color-bg-surface)', borderBottom: '1px solid var(--color-border-hairline)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}><span style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--red-500)', boxShadow: '0 0 0 6px rgba(239,35,60,.16)' }} /><span style={{ fontWeight: 700, fontSize: 18 }}>SirenGrid</span></div>
        <div role="tablist" aria-label="Primary" style={{ display: 'flex', gap: 3, padding: 3, borderRadius: 'var(--radius-md)', background: 'var(--gray-100)' }}>
          {TOP_NAV.map(([id, label, icon]) => { const on = nav === id; return <button key={id} role="tab" aria-selected={on} onClick={() => setNav(id)} style={{ display: 'flex', alignItems: 'center', gap: 7, padding: '7px 14px', border: 'none', borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontFamily: 'var(--font-en)', fontSize: 13.5, fontWeight: on ? 600 : 500, whiteSpace: 'nowrap', background: on ? 'var(--color-bg-surface)' : 'transparent', color: on ? 'var(--color-text-primary)' : 'var(--color-text-secondary)', boxShadow: on ? 'var(--shadow-xs)' : 'none' }}><span style={{ width: 15, height: 15, display: 'flex', color: on ? 'var(--color-accent)' : 'var(--gray-500)' }}><Ico n={icon} /></span>{label}</button>; })}
        </div>
      </div>
      <div style={{ display: 'flex', gap: 22, alignItems: 'center', whiteSpace: 'nowrap' }}>
        {[{ value: openCount === undefined ? '—' : String(openCount), label: 'open incidents' }, { value: available === undefined ? '—' : String(available), label: 'available units' }, { value: traffic.data ? traffic.data.freshness_status : '—', label: 'traffic freshness' }].map((item, index) => <Fragment key={item.label}>{index > 0 && <span style={{ width: 1, height: 22, background: 'var(--color-border-hairline)' }} />}<div style={{ display: 'flex', alignItems: 'baseline', gap: 7 }}><span style={{ fontSize: 19, fontWeight: 600 }}>{item.value}</span><span style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>{item.label}</span></div></Fragment>)}
      </div>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
        <Badge tone={trafficReality === 'REAL_LIVE' ? 'confirmed' : 'simulated'}>{trafficReality === 'UNKNOWN' ? 'Backend data' : trafficReality.replace('_', ' ')}</Badge>
        <button onClick={() => setNav('demo')} title="Scenario controls" aria-label="Scenario controls" style={{ border: 'none', background: 'transparent', padding: 0, cursor: 'pointer' }}><IconTile icon={<Ico n="sliders-horizontal" />} tint={nav === 'demo' ? 'navy' : 'slate'} size={32} /></button>
        <IconTile icon={<Ico n="user-round" />} tint="navy" size={32} />
      </div>
    </div>
  );
}

function StateSwitch({ state, setState }: { state: OpsState; setState: (s: OpsState) => void }) {
  return <GlassPanel padding={5} style={{ display: 'flex', gap: 3, alignItems: 'center' }}>{STATES.map(([id, label, icon]) => { const on = state === id; return <button key={id} onClick={() => setState(id)} title={label} aria-label={label} aria-pressed={on} style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '7px 0', border: 'none', borderRadius: 'var(--radius-sm)', cursor: 'pointer', background: on ? 'var(--color-accent)' : 'transparent' }}><span style={{ width: 17, height: 17, display: 'flex', color: on ? '#fff' : 'var(--color-text-muted)' }}><Ico n={icon} /></span></button>; })}</GlassPanel>;
}

export function IncidentRail({ selected, setSelected, state, setState }: { selected: string; setSelected: (id: string) => void; state: OpsState; setState: (s: OpsState) => void }) {
  const { incidents, resources } = useOperationsData();
  const list = incidents.data ?? [];
  const ambulanceCount = resources.data?.filter((resource) => resource.resource_type === 'AMBULANCE').length;
  return <div style={{ width: 312, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 11, minHeight: 0 }}>
    <Input placeholder="Search incident, street, unit" icon={<span style={{ width: 16, height: 16, display: 'flex', color: 'var(--color-text-muted)' }}><Ico n="search" /></span>} />
    <StateSwitch state={state} setState={setState} />
    <div style={{ display: 'flex', flexDirection: 'column', gap: 9, overflowY: 'auto', paddingRight: 2, flex: 1, minHeight: 0 }}>
      {incidents.loading && <GlassPanel padding={14}>Loading incidents…</GlassPanel>}
      {!incidents.loading && !list.length && <GlassPanel padding={14}><Badge tone="neutral">No incidents returned by backend</Badge></GlassPanel>}
      {list.map((incident) => <IncidentCard key={incident.id} incident={incident} selected={selected === incident.id} onSelect={() => { setSelected(incident.id); setState('incident'); }} />)}
    </div>
    <GlassPanel padding={14}><div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 10 }}><IconTile icon={<Ico n="truck" />} tint="navy" size={28} /><span style={{ fontSize: 14, fontWeight: 600 }}>Resources</span></div><div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13.5, padding: '5px 0' }}><span style={{ color: 'var(--color-text-muted)' }}>Ambulances</span><span style={{ fontWeight: 600 }}>{ambulanceCount === undefined ? '—' : ambulanceCount}</span></div><div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13.5, padding: '5px 0' }}><span style={{ color: 'var(--color-text-muted)' }}>Backend source</span><Badge tone="simulated">Operational API</Badge></div></GlassPanel>
  </div>;
}

function IncidentCard({ incident, selected, onSelect }: { incident: Incident; selected: boolean; onSelect: () => void }) {
  return <button onClick={onSelect} style={{ textAlign: 'left', cursor: 'pointer', fontFamily: 'var(--font-en)', borderRadius: 'var(--radius-md)', padding: 14, display: 'flex', gap: 12, alignItems: 'flex-start', border: selected ? '1.5px solid var(--color-accent)' : '1px solid var(--color-border-hairline)', background: selected ? 'var(--color-accent-soft)' : 'var(--color-bg-surface)', boxShadow: selected ? 'var(--shadow-sm)' : 'none' }}><IconTile icon={<Ico n="triangle-alert" />} tint={incident.severity === 'CRITICAL' || incident.severity === 'HIGH' ? 'red' : 'navy'} size={34} /><div style={{ flex: 1, minWidth: 0 }}><div style={{ fontSize: 14, fontWeight: 600, lineHeight: 1.25 }}>{incident.incident_type.replaceAll('_', ' ')}</div><div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}><Badge severity={severity(incident.severity)} /><span style={{ fontSize: 12.5, color: 'var(--color-text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{incidentLocation(incident)}</span></div><div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, marginTop: 5 }}><span style={{ fontSize: 12.5, color: 'var(--color-text-secondary)' }}>{incident.status.replaceAll('_', ' ')} · v{incident.version}</span><span style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>{time(incident.updated_at)}</span></div></div></button>;
}

export function TimelineDock({ open, setOpen }: { open: boolean; setOpen: (o: boolean) => void }) {
  const { selectedIncident, timeline } = useOperationsData();
  const events = timeline.data ?? [];
  const incidentId = selectedIncident.data?.id ?? 'incident';
  return <GlassPanel padding={0} style={{ flexShrink: 0 }}><button onClick={() => setOpen(!open)} aria-expanded={open} style={{ width: '100%', border: 'none', background: 'transparent', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '11px 16px', fontFamily: 'var(--font-en)' }}><span style={{ display: 'flex', alignItems: 'center', gap: 10 }}><IconTile icon={<Ico n="clock" />} tint="glass" size={28} /><span style={{ fontSize: 14, fontWeight: 600 }}>History · {incidentId}</span></span><span style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13, color: 'var(--color-text-secondary)' }}>{!open && events[0] && <span>{time(events[0].created_at)} · {events[0].event_type.replaceAll('_', ' ')}</span>}<span style={{ width: 16, height: 16, display: 'flex' }}><Ico n={open ? 'chevron-down' : 'chevron-up'} /></span></span></button>{open && <div style={{ display: 'flex', padding: '2px 16px 14px', overflowX: 'auto', gap: 20 }}>{events.length === 0 ? <span style={{ color: 'var(--color-text-muted)', fontSize: 13 }}>No timeline events returned by backend.</span> : events.map((event) => <div key={event.id} style={{ minWidth: 180 }}><div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>{time(event.created_at)}</div><div style={{ fontSize: 13, fontWeight: 600, marginTop: 4 }}>{event.event_type.replaceAll('_', ' ')}</div><Prov kind="operator" /></div>)}</div>}</GlassPanel>;
}
