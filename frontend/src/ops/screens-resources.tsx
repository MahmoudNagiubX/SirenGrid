import { useState } from 'react';
import { Alert, Badge, Button, Card, GlassPanel, IconTile, Input, Tabs } from '../components';
import { Ico } from '../lib/icon';
import { Drawer, Fact, Kpi, PanelHeader, Prov, Screen } from './primitives';
import {
  STATUS_TONE,
  type ProvKind,
} from '../data/mock';
import { useOperations } from '../state/OperationsContext';
import type { ResourceRead, TimelineEventRead } from '../api/types';

/** Ported from ui_kits/operations_center/screens-resources.jsx — bound to canonical backend read state. */

type Filter = 'all' | 'avail' | 'committed';

export function ResourceScreen() {
  const { resources, hospitals } = useOperations();
  const [sel, setSel] = useState<ResourceRead | null>(null);
  const [filter, setFilter] = useState<Filter>('all');
  const [search, setSearch] = useState('');

  const resList = resources.data ?? [];
  const rows = resList.filter((u) => {
    const matchesFilter =
      filter === 'all' ||
      (filter === 'avail' && u.status === 'AVAILABLE') ||
      (filter === 'committed' && ['EN_ROUTE', 'ASSIGNED', 'TRANSPORTING', 'ON_SCENE', 'RESERVED'].includes(u.status));
    if (!matchesFilter) return false;
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (
      u.id.toLowerCase().includes(q) ||
      u.name.toLowerCase().includes(q) ||
      (u.home_zone ?? '').toLowerCase().includes(q) ||
      u.capability_tags.some((c) => c.toLowerCase().includes(q))
    );
  });

  const total = resList.length;
  const avail = resList.filter((r) => r.status === 'AVAILABLE').length;
  const committed = resList.filter((r) =>
    ['RESERVED', 'ASSIGNED', 'EN_ROUTE', 'ON_SCENE', 'TRANSPORTING'].includes(r.status),
  ).length;
  const outOfService = resList.filter((r) => r.status === 'OUT_OF_SERVICE').length;

  const hospList = hospitals.data ?? [];
  const hospTotal = hospList.length;
  const hospAccepting = hospList.filter((h) => h.accepting_state === 'ACCEPTING').length;

  const kpis = [
    {
      icon: 'truck',
      label: 'Total fleet',
      value: resources.data ? `${total} units` : '—',
      sub: resources.data ? `${avail} available · ${committed} committed` : 'Awaiting fleet data',
      tint: 'navy' as const,
    },
    {
      icon: 'circle-check',
      label: 'Available now',
      value: resources.data ? `${avail} units` : '—',
      sub: total > 0 ? `${Math.round((avail / total) * 100)}% of total fleet` : '—',
      tint: 'navy' as const,
    },
    {
      icon: 'radio-tower',
      label: 'Committed',
      value: resources.data ? `${committed} units` : '—',
      sub: resources.data ? `${outOfService} out of service` : '—',
      tint: 'slate' as const,
    },
    {
      icon: 'hospital',
      label: 'Hospital readiness',
      value: hospitals.data ? `${hospAccepting} / ${hospTotal} open` : '—',
      sub: 'Operational status',
      tint: 'blue' as const,
    },
  ];

  return (
    <Screen>
      <div style={{ display: 'flex', gap: 12 }}>
        {kpis.map((kpi) => (
          <Kpi
            key={kpi.label}
            icon={kpi.icon}
            label={kpi.label}
            value={kpi.value}
            sub={kpi.sub}
            tint={kpi.tint}
          />
        ))}
      </div>
      <div style={{ flex: 1, display: 'flex', gap: 14, minHeight: 0 }}>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 }}>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <div style={{ width: 300 }}>
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search unit, base, capability…"
                icon={
                  <span style={{ width: 15, height: 15, display: 'flex', color: 'var(--color-text-muted)' }}>
                    <Ico n="search" />
                  </span>
                }
              />
            </div>
            <div style={{ paddingTop: 2 }}>
              <Tabs
                tabs={[
                  { value: 'all', label: 'All units' },
                  { value: 'avail', label: 'Available' },
                  { value: 'committed', label: 'Committed' },
                ]}
                defaultValue="all"
                onChange={(v) => setFilter(v as Filter)}
              />
            </div>
          </div>
          <GlassPanel padding={0} style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', padding: '11px 16px', borderBottom: '1px solid var(--color-border-hairline)', fontSize: 12, fontWeight: 600, letterSpacing: '.05em', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>
              <span style={{ width: 150 }}>Unit</span>
              <span style={{ width: 150 }}>Status</span>
              <span style={{ width: 110 }}>Zone</span>
              <span style={{ flex: 1 }}>Base</span>
              <span style={{ width: 150 }}>Capability</span>
              <span style={{ width: 60, textAlign: 'right' }}>ETA</span>
            </div>
            <div style={{ overflowY: 'auto' }}>
              {rows.length === 0 && (
                <div style={{ padding: 24, textAlign: 'center', color: 'var(--color-text-muted)', fontSize: 13 }}>
                  {resources.loading ? 'Loading resource fleet…' : 'No matching resources found'}
                </div>
              )}
              {rows.map((u) => {
                const isAmb = u.resource_type === 'AMBULANCE' || u.type === 'AMBULANCE';
                return (
                  <button
                    key={u.id}
                    onClick={() => setSel(u)}
                    style={{
                      width: '100%',
                      textAlign: 'left',
                      border: 'none',
                      borderBottom: '1px solid var(--color-border-hairline)',
                      background: sel && sel.id === u.id ? 'var(--color-accent-soft)' : 'transparent',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      padding: '11px 16px',
                      fontFamily: 'var(--font-en)',
                      fontSize: 12.5,
                    }}
                  >
                    <span style={{ width: 150, display: 'flex', alignItems: 'center', gap: 9 }}>
                      <IconTile icon={<Ico n={isAmb ? 'ambulance' : 'truck'} />} tint={u.status === 'OUT_OF_SERVICE' ? 'slate' : 'navy'} size={26} />
                      <span>
                        <b>{u.id}</b>
                        <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>{u.name || u.resource_type}</div>
                      </span>
                    </span>
                    <span style={{ width: 150 }}>
                      <Badge tone={STATUS_TONE[u.status] ?? 'neutral'}>{u.status.replace(/_/g, ' ')}</Badge>
                    </span>
                    <span style={{ width: 110, color: 'var(--color-text-secondary)' }}>{u.home_zone || '—'}</span>
                    <span style={{ flex: 1, color: 'var(--color-text-secondary)' }}>—</span>
                    <span style={{ width: 150, color: 'var(--color-text-secondary)' }}>{u.capability_tags.join(', ') || '—'}</span>
                    <span style={{ width: 60, textAlign: 'right', fontWeight: 600 }}>—</span>
                  </button>
                );
              })}
            </div>
          </GlassPanel>
        </div>
        {sel ? (
          <Drawer title={`${sel.id} · ${sel.name || sel.resource_type}`} onClose={() => setSel(null)}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <IconTile icon={<Ico n={sel.resource_type === 'AMBULANCE' || sel.type === 'AMBULANCE' ? 'ambulance' : 'truck'} />} tint="navy" size={42} />
              <div>
                <div style={{ fontSize: 15, fontWeight: 600 }}>{sel.name || sel.id}</div>
                <Badge tone={STATUS_TONE[sel.status] ?? 'neutral'}>{sel.status.replace(/_/g, ' ')}</Badge>
              </div>
            </div>
            <div>
              <Fact label="Home base" value="—" unknown />
              <Fact label="Current zone" value={sel.home_zone || '—'} prov="source" unknown={!sel.home_zone} />
              <Fact label="Capability" value={sel.capability_tags.join(', ') || '—'} prov="source" unknown={sel.capability_tags.length === 0} />
              <Fact label="Assignment" value={sel.assigned_incident_id || '—'} prov="operator" unknown={!sel.assigned_incident_id} />
              <Fact label="ETA" value="—" unknown />
            </div>
            <Alert tone="simulated" title="Position telemetry">
              Unit telemetry is supplied by the canonical operational backend.
            </Alert>
            <div style={{ display: 'flex', gap: 8 }}>
              <Button variant="secondary" size="sm" disabled>Reposition</Button>
              <Button variant="critical" size="sm" disabled>Mark unavailable</Button>
            </div>
          </Drawer>
        ) : (
          <GlassPanel padding={14} style={{ width: 320, flexShrink: 0, alignSelf: 'flex-start' }}>
            <PanelHeader icon="hospital" title="Hospital readiness" right={<Badge tone="simulated">Simulated</Badge>} />
            {hospList.length === 0 ? (
              <div style={{ padding: '8px 0', fontSize: 12.5, color: 'var(--color-text-muted)' }}>
                {hospitals.loading ? 'Loading hospitals…' : 'No hospital records available.'}
              </div>
            ) : (
              hospList.map((h) => (
                <div key={h.id} style={{ display: 'flex', justifyContent: 'space-between', padding: '7px 0', borderBottom: '1px solid var(--color-border-hairline)', fontSize: 12.5 }}>
                  <span>{h.name || h.id}</span>
                  <span style={{ color: 'var(--color-text-secondary)' }}>
                    {h.accepting_state === 'ACCEPTING'
                      ? h.simulated_load_ratio !== null
                        ? `${Math.round(h.simulated_load_ratio * 100)}% load`
                        : 'Accepting'
                      : h.accepting_state === 'NOT_ACCEPTING'
                      ? 'Not accepting'
                      : 'Unknown'}
                  </span>
                </div>
              ))
            )}
            <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)', marginTop: 10 }}>Select a unit to open its detail drawer.</div>
          </GlassPanel>
        )}
      </div>
    </Screen>
  );
}

function deriveTimelineProv(evt: TimelineEventRead): ProvKind {
  const d = evt.details as Record<string, unknown> | undefined;
  if (d?.source === 'operator' || d?.operator_reference) return 'operator';
  if (d?.source === 'responder') return 'responder';
  if (d?.data_reality === 'SIMULATED' || d?.data_reality === 'SYNTHETIC') return 'sim';
  return 'source';
}

export function TimelineScreen() {
  const { selectedIncidentId, timeline, reports, selectedIncident } = useOperations();
  const events = timeline.data ?? [];
  const repList = reports.data ?? [];
  const inc = selectedIncident.data;

  return (
    <Screen>
      <div style={{ flex: 1, display: 'flex', gap: 14, minHeight: 0 }}>
        <GlassPanel padding={16} style={{ flex: 1, minWidth: 0, overflowY: 'auto' }}>
          <PanelHeader
            icon="clock"
            title={`${selectedIncidentId ?? 'No incident'} · audit timeline`}
            right={<Badge tone="neutral">Append-only</Badge>}
          />
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {events.length === 0 ? (
              <div style={{ padding: 16, color: 'var(--color-text-muted)', fontSize: 13 }}>
                No audit events recorded for this incident.
              </div>
            ) : (
              events.map((evt, i) => (
                <div key={evt.id || i} style={{ display: 'flex', gap: 14 }}>
                  <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 52, flexShrink: 0 }}>
                    <span style={{ fontSize: 12.5, color: 'var(--color-text-muted)', fontWeight: 600 }}>
                      {evt.created_at ? new Date(evt.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}
                    </span>
                    <span style={{ width: 1, flex: 1, background: 'var(--color-border-hairline)', marginTop: 4 }} />
                  </div>
                  <div style={{ paddingBottom: 18, flex: 1 }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                      <span style={{ fontSize: 13, fontWeight: 600 }}>{evt.event_type.replace(/_/g, ' ')}</span>
                      <Prov kind={deriveTimelineProv(evt)} />
                    </div>
                    <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 3, lineHeight: 1.5 }}>
                      {typeof evt.details === 'object' ? JSON.stringify(evt.details) : String(evt.details)}
                    </div>
                  </div>
                </div>
              ))
            )}
          </div>
        </GlassPanel>
        <div style={{ width: 360, display: 'flex', flexDirection: 'column', gap: 12, overflowY: 'auto' }}>
          <GlassPanel padding={14}>
            <PanelHeader icon="file-text" title="Evidence" />
            {repList.length === 0 ? (
              <div style={{ padding: '8px 0', fontSize: 12.5, color: 'var(--color-text-muted)' }}>
                No evidence reports available.
              </div>
            ) : (
              repList.map((r) => (
                <Card key={r.id} padding={11} style={{ marginBottom: 8 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                    <span style={{ fontSize: 12.5, fontWeight: 600 }}>{r.source_reference || r.source_type}</span>
                    <Badge tone="neutral">{r.data_reality}</Badge>
                  </div>
                  <div style={{ fontSize: 12.5, color: 'var(--color-text-secondary)', marginTop: 3 }}>{r.raw_text}</div>
                </Card>
              ))
            )}
          </GlassPanel>
          {inc?.status === 'REQUIRES_REVIEW' && (
            <GlassPanel padding={14}>
              <PanelHeader icon="git-compare" title="Conflicting evidence" />
              <div style={{ fontSize: 12.5, color: 'var(--color-text-secondary)', lineHeight: 1.6 }}>
                Incident status indicates operator review is required before state progression.
              </div>
              <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
                <Button variant="secondary" size="sm" disabled>Review conflict</Button>
              </div>
            </GlassPanel>
          )}
        </div>
      </div>
    </Screen>
  );
}
