import { Fragment, useState } from 'react';
import { Badge, GlassPanel, IconTile, Input } from '../components';
import { Ico } from '../lib/icon';
import { Prov } from './primitives';
import {
  STATES,
  TOP_NAV,
  type OpsState,
  type ProvKind,
  type TopNav,
} from '../data/mock';
import { useOperations } from '../state/OperationsContext';
import { RecoveryNotice } from '../recovery/RecoveryNotice';
import {
  getMobileSourceSummary,
  isUnconfirmedMobileSeverity,
} from '../lib/mobileProvenance';
import type { TimelineEventRead } from '../api/types';

/** Ported from ui_kits/operations_center/workspace.jsx (StatusStrip, StateSwitch, IncidentRail, TimelineDock). */

export function StatusStrip({ nav, setNav }: { nav: TopNav; setNav: (n: TopNav) => void }) {
  const { incidents, resources } = useOperations();
  const terminalStatuses = new Set(['CLOSED', 'CANCELLED_FALSE_REPORT', 'DUPLICATE_MERGED']);
  const openCount = incidents.data
    ? incidents.data.filter((i) => !terminalStatuses.has(i.status)).length
    : null;
  const resList = resources.data ?? [];
  const availUnits = resList.filter((r) => r.status === 'AVAILABLE').length;
  const fleetLabel = resources.data
    ? `${availUnits} / ${resList.length}`
    : resources.loading
    ? '···'
    : '—';
  const incidentsLoading = incidents.loading && incidents.data == null;

  const kpis: [string, string][] = [
    [fleetLabel, 'units available'],
    [
      openCount !== null ? `${openCount}` : incidentsLoading ? '···' : '—',
      openCount === 1 ? 'active incident' : 'active incidents',
    ],
  ];

  return (
    <div style={{ height: 62, flexShrink: 0, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '0 20px', background: 'var(--color-bg-surface)', borderBottom: '1px solid var(--color-border-hairline)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 20 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <span style={{ width: 10, height: 10, borderRadius: '50%', background: 'var(--red-500)', boxShadow: '0 0 0 6px rgba(239,35,60,.16)' }} />
          <span style={{ fontWeight: 700, fontSize: 18, letterSpacing: '-0.015em' }}>SirenGrid</span>
        </div>
        <div role="tablist" aria-label="Primary" style={{ display: 'flex', gap: 3, padding: 3, borderRadius: 'var(--radius-md)', background: 'var(--gray-100)' }}>
          {TOP_NAV.map(([id, label, icon]) => {
            const on = nav === id;
            return (
              <button
                key={id}
                role="tab"
                aria-selected={on}
                onClick={() => setNav(id)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 7,
                  padding: '7px 14px',
                  border: 'none',
                  borderRadius: 'var(--radius-sm)',
                  cursor: 'pointer',
                  fontFamily: 'var(--font-en)',
                  fontSize: 13.5,
                  fontWeight: on ? 600 : 500,
                  whiteSpace: 'nowrap',
                  background: on ? 'var(--color-bg-surface)' : 'transparent',
                  color: on ? 'var(--color-text-primary)' : 'var(--color-text-secondary)',
                  boxShadow: on ? 'var(--shadow-xs)' : 'none',
                }}
              >
                <span style={{ width: 15, height: 15, display: 'flex', color: on ? 'var(--color-accent)' : 'var(--gray-500)' }}>
                  <Ico n={icon} />
                </span>
                {label}
              </button>
            );
          })}
        </div>
      </div>
      <div style={{ display: 'flex', gap: 22, alignItems: 'center', whiteSpace: 'nowrap' }}>
        {kpis.map(([v, l], i) => {
          const active = l.includes('incident') && openCount !== null && openCount > 0;
          return (
            <Fragment key={l}>
              {i > 0 && <span style={{ width: 1, height: 22, background: 'var(--color-border-hairline)' }} />}
              <div style={{ display: 'flex', alignItems: 'baseline', gap: 7 }}>
                {active && (
                  <span
                    style={{
                      width: 7,
                      height: 7,
                      borderRadius: '50%',
                      background: 'var(--color-siren)',
                      alignSelf: 'center',
                      boxShadow: '0 0 0 4px rgba(239,35,60,.16)',
                    }}
                  />
                )}
                <span style={{ fontSize: 21, fontWeight: 600, letterSpacing: '-0.015em', color: active ? 'var(--color-critical)' : undefined }}>{v}</span>
                <span style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>{l}</span>
              </div>
            </Fragment>
          );
        })}
      </div>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
        {/* Data-reality context lives in Demo controls, not a loud header pill. */}
        <button
          onClick={() => setNav('demo')}
          title="Demo data — open scenario &amp; simulation controls"
          aria-label="Demo data — open scenario and simulation controls"
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 7,
            padding: '5px 11px',
            border: '1px solid var(--color-border-hairline)',
            borderRadius: 'var(--radius-pill)',
            background: nav === 'demo' ? 'var(--color-accent-soft)' : 'transparent',
            color: nav === 'demo' ? 'var(--color-accent)' : 'var(--color-text-secondary)',
            cursor: 'pointer',
            fontFamily: 'var(--font-en)',
            fontSize: 12,
            fontWeight: 600,
            letterSpacing: '0.01em',
          }}
        >
          <span style={{ width: 13, height: 13, display: 'flex' }}>
            <Ico n="sliders-horizontal" />
          </span>
          Demo data
        </button>
        <IconTile icon={<Ico n="user-round" />} tint="navy" size={32} />
      </div>
    </div>
  );
}

function StateSwitch({ state, setState }: { state: OpsState; setState: (s: OpsState) => void }) {
  return (
    <GlassPanel padding={5} style={{ display: 'flex', gap: 3, alignItems: 'center' }}>
      {STATES.map(([id, label, icon]) => {
        const on = state === id;
        return (
          <button
            key={id}
            onClick={() => setState(id)}
            title={label}
            aria-label={label}
            aria-pressed={on}
            style={{
              flex: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '7px 0',
              border: 'none',
              borderRadius: 'var(--radius-sm)',
              cursor: 'pointer',
              background: on ? 'var(--color-accent)' : 'transparent',
            }}
          >
            <span style={{ width: 17, height: 17, display: 'flex', color: on ? '#fff' : 'var(--color-text-muted)' }}>
              <Ico n={icon} />
            </span>
          </button>
        );
      })}
    </GlassPanel>
  );
}

const INCIDENT_TYPE_AR: Record<string, string> = {
  traffic_collision: 'تصادم مروري',
  structure_fire: 'حريق مبنى',
  medical_emergency: 'طوارئ طبية',
  hazardous_materials: 'مواد خطرة',
};

function humanizeType(type: string): string {
  return type
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function humanizeStatus(status: string): string {
  return status
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function incidentIcon(type: string): string {
  const lower = type.toLowerCase();
  if (lower.includes('fire')) return 'flame';
  if (lower.includes('medical') || lower.includes('ambulance')) return 'heart-pulse';
  return 'triangle-alert';
}

function formatIncidentTime(ts: string | null): string {
  if (!ts) return '—';
  try {
    return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return '—';
  }
}

export function IncidentRail({
  selected,
  setSelected,
  state,
  setState,
}: {
  selected: string;
  setSelected: (id: string) => void;
  state: OpsState;
  setState: (s: OpsState) => void;
}) {
  const [search, setSearch] = useState('');
  const { incidents, resources, refreshGlobal } = useOperations();

  const incidentList = incidents.data ?? [];
  const filtered = incidentList.filter((inc) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    return (
      inc.id.toLowerCase().includes(q) ||
      (inc.location_text ?? '').toLowerCase().includes(q) ||
      inc.incident_type.toLowerCase().includes(q)
    );
  });

  const resourcesList = resources.data ?? [];
  const ambTotal = resourcesList.filter((r) => r.resource_type === 'AMBULANCE' || r.type === 'AMBULANCE').length;
  const ambAvail = resourcesList.filter(
    (r) => (r.resource_type === 'AMBULANCE' || r.type === 'AMBULANCE') && r.status === 'AVAILABLE',
  ).length;
  const fireTotal = resourcesList.filter((r) => r.resource_type === 'FIRE_RESCUE' || r.type === 'FIRE_RESCUE').length;
  const fireAvail = resourcesList.filter(
    (r) => (r.resource_type === 'FIRE_RESCUE' || r.type === 'FIRE_RESCUE') && r.status === 'AVAILABLE',
  ).length;

  const railResources: [string, string][] = [
    ['Ambulances', resources.data ? `${ambAvail} / ${ambTotal}` : '—'],
    ['Fire & rescue', resources.data ? `${fireAvail} / ${fireTotal}` : '—'],
    ['Reserve held', '—'],
  ];

  return (
    <div style={{ width: 312, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 11, minHeight: 0 }}>
      <Input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Search incident, street, unit"
        icon={
          <span style={{ width: 16, height: 16, display: 'flex', color: 'var(--color-text-muted)' }}>
            <Ico n="search" />
          </span>
        }
      />
      <StateSwitch state={state} setState={setState} />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 9, overflowY: 'auto', paddingRight: 2, flex: 1, minHeight: 0 }}>
        {/* §20: incident-list refresh failure is distinct from "no incidents";
            the last-known list stays visible if it exists. */}
        {incidents.error != null && (
          <RecoveryNotice
            kind="UNAVAILABLE"
            title="Incident list refresh failed"
            detail={incidentList.length > 0 ? 'Showing last-known incidents.' : undefined}
            compact
            onRetry={() => void refreshGlobal({ includeSelected: false })}
          />
        )}
        {/* §21: a still-loading first fetch shows calm skeletons, never an empty list. */}
        {incidents.error == null && incidents.loading && incidents.data == null && (
          <Fragment>
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                className="sg-skeleton"
                style={{ height: 78, borderRadius: 'var(--radius-md)', opacity: 1 - i * 0.22 }}
              />
            ))}
          </Fragment>
        )}
        {filtered.length === 0 && incidents.error == null && !(incidents.loading && incidents.data == null) && (
          <div
            className="sg-rise"
            style={{
              padding: '28px 18px',
              textAlign: 'center',
              color: 'var(--color-text-muted)',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 8,
            }}
          >
            <span style={{ width: 26, height: 26, display: 'flex', color: 'var(--gray-400)' }}>
              <Ico n={incidentList.length === 0 ? 'siren' : 'search'} />
            </span>
            <div style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--color-text-secondary)' }}>
              {incidentList.length === 0 ? 'No active incidents yet' : 'No incidents match your search'}
            </div>
            <div style={{ fontSize: 12.5, lineHeight: 1.5, maxWidth: 220 }}>
              {incidentList.length === 0
                ? 'Citizen mobile requests and operator intake appear here automatically.'
                : 'Clear the search to see the full incident feed.'}
            </div>
          </div>
        )}
        {filtered.map((inc) => {
          const on = selected === inc.id;
          const sevTone = inc.severity.toLowerCase() as 'low' | 'moderate' | 'high' | 'critical';
          const severityPending = isUnconfirmedMobileSeverity(inc);
          const mobileSummary = getMobileSourceSummary(inc);
          const workflowLabel = inc.pending_replan_plan_id
            ? 'Replan required'
            : inc.current_plan_id
            ? 'Response active'
            : mobileSummary
            ? 'Pending operator review'
            : humanizeStatus(inc.status);
          const arLabel = INCIDENT_TYPE_AR[inc.incident_type.toLowerCase()] ?? '';
          return (
            <button
              key={inc.id}
              onClick={() => {
                setSelected(inc.id);
                setState('incident');
              }}
              style={{
                textAlign: 'left',
                cursor: 'pointer',
                fontFamily: 'var(--font-en)',
                borderRadius: 'var(--radius-md)',
                padding: 14,
                display: 'flex',
                gap: 12,
                alignItems: 'flex-start',
                border: on ? '1.5px solid var(--color-accent)' : '1px solid var(--color-border-hairline)',
                background: on ? 'var(--color-accent-soft)' : 'var(--color-bg-surface)',
                boxShadow: on ? 'var(--shadow-sm)' : 'none',
              }}
            >
              <IconTile icon={<Ico n={incidentIcon(inc.incident_type)} />} tint={sevTone === 'critical' || sevTone === 'high' ? 'red' : 'navy'} size={34} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 15, fontWeight: 600, letterSpacing: '-0.015em', lineHeight: 1.25 }}>
                  {humanizeType(inc.incident_type)}
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
                  {severityPending ? <Badge tone="neutral">Pending review</Badge> : <Badge severity={sevTone} />}
                  <span style={{ fontSize: 13, color: 'var(--color-text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {inc.location_text ||
                      (inc.latitude != null && inc.longitude != null
                        ? `${inc.latitude.toFixed(4)}, ${inc.longitude.toFixed(4)}`
                        : 'Location pending')}
                  </span>
                </div>
                {mobileSummary && (
                  <div style={{ marginTop: 5 }}>
                    <Badge tone="info">
                      New mobile request{mobileSummary.locationSource === 'DEVICE_GPS' ? ' · Device GPS' : ''}
                    </Badge>
                  </div>
                )}
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, marginTop: 4 }}>
                  <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--color-text-secondary)', whiteSpace: 'nowrap' }}>
                    {workflowLabel} · {formatIncidentTime(inc.created_at)}
                  </span>
                  {arLabel && (
                    <span dir="rtl" style={{ fontFamily: 'var(--font-ar)', fontSize: 13, color: 'var(--color-text-muted)', whiteSpace: 'nowrap' }}>
                      {arLabel}
                    </span>
                  )}
                </div>
              </div>
            </button>
          );
        })}
      </div>
      <GlassPanel padding={14}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 9, marginBottom: 10 }}>
          <IconTile icon={<Ico n="truck" />} tint="navy" size={28} />
          <span style={{ fontSize: 14, fontWeight: 600 }}>Resources</span>
        </div>
        {railResources.map(([a, b]) => (
          <div key={a} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13.5, padding: '5px 0' }}>
            <span style={{ color: 'var(--color-text-muted)' }}>{a}</span>
            <span style={{ fontWeight: 600 }}>{b}</span>
          </div>
        ))}
        {/* §22: keep last-known counts, flag that the refresh failed. */}
        {resources.error != null && (
          <div style={{ marginTop: 8 }}>
            <RecoveryNotice
              kind="UNAVAILABLE"
              title="Resource counts may be out of date"
              detail={resources.data != null ? 'Last successful fleet read shown.' : undefined}
              compact
              onRetry={() => void refreshGlobal({ includeSelected: false })}
            />
          </div>
        )}
      </GlassPanel>
    </div>
  );
}

function deriveProv(evt: TimelineEventRead): ProvKind {
  const d = evt.details as Record<string, unknown> | undefined;
  if (d?.source === 'operator' || d?.operator_reference) return 'operator';
  if (d?.source === 'responder') return 'responder';
  if (d?.data_reality === 'SIMULATED' || d?.data_reality === 'SYNTHETIC') return 'sim';
  return 'source';
}

export function TimelineDock({ open, setOpen }: { open: boolean; setOpen: (o: boolean) => void }) {
  const { selectedIncidentId, timeline } = useOperations();
  const events = timeline.data ?? [];
  const latestEvent = events.length > 0 ? events[events.length - 1] : null;

  return (
    <GlassPanel padding={0} style={{ flexShrink: 0 }}>
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        style={{ width: '100%', border: 'none', background: 'transparent', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '11px 16px', fontFamily: 'var(--font-en)' }}
      >
        <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <IconTile icon={<Ico n="clock" />} tint="glass" size={28} />
          <span style={{ fontSize: 14, fontWeight: 600 }}>
            {selectedIncidentId ? 'Incident history' : 'No incident selected'}
          </span>
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13, color: 'var(--color-text-secondary)' }}>
          {!open && latestEvent && (
            <span>
              {formatIncidentTime(latestEvent.created_at)} · {humanizeStatus(latestEvent.event_type)}
            </span>
          )}
          <span style={{ width: 16, height: 16, display: 'flex' }}>
            <Ico n={open ? 'chevron-down' : 'chevron-up'} />
          </span>
        </span>
      </button>
      {open && (
        <div style={{ display: 'flex', padding: '2px 16px 14px', overflowX: 'auto' }}>
          {events.length === 0 ? (
            <div style={{ padding: '8px 0', fontSize: 13, color: 'var(--color-text-muted)' }}>
              No timeline events recorded for this incident.
            </div>
          ) : (
            events.map((evt, i) => (
              <div
                key={evt.id || i}
                style={{
                  minWidth: 226,
                  paddingRight: 18,
                  marginRight: 18,
                  borderRight: i < events.length - 1 ? '1px solid var(--color-border-hairline)' : 'none',
                }}
              >
                <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--color-accent)' }}>
                  {formatIncidentTime(evt.created_at)}
                </div>
                <div style={{ fontSize: 13.5, lineHeight: 1.45, margin: '3px 0 6px' }}>
                  {humanizeStatus(evt.event_type)}
                </div>
                <Prov kind={deriveProv(evt)} />
              </div>
            ))
          )}
        </div>
      )}
    </GlassPanel>
  );
}
