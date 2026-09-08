import { useState } from 'react';
import { Alert, Badge, Button, Card, GlassPanel, IconTile, Input, Tabs } from '../components';
import { Ico } from '../lib/icon';
import { Drawer, Fact, Kpi, PanelHeader, Prov, Screen } from './primitives';
import {
  AUDIT_EVENTS,
  AUDIT_EVIDENCE,
  HOSPITAL_READINESS,
  RESOURCE_KPIS,
  STATUS_TONE,
  UNITS,
  type Unit,
} from '../data/mock';

/** Ported from ui_kits/operations_center/screens-resources.jsx. */

type Filter = 'all' | 'avail' | 'committed';

export function ResourceScreen() {
  const [sel, setSel] = useState<Unit | null>(null);
  const [filter, setFilter] = useState<Filter>('all');
  const rows = UNITS.filter(
    (u) =>
      filter === 'all' ||
      (filter === 'avail' && u.status === 'AVAILABLE') ||
      (filter === 'committed' && ['EN_ROUTE', 'ASSIGNED', 'TRANSPORTING', 'ON_SCENE'].includes(u.status)),
  );
  return (
    <Screen>
      <div style={{ display: 'flex', gap: 12 }}>
        {RESOURCE_KPIS.map(([icon, label, value, sub]) => (
          <Kpi key={label} icon={icon} label={label} value={value} sub={sub} tint={icon === 'radio-tower' ? 'slate' : icon === 'hospital' ? 'blue' : 'navy'} />
        ))}
      </div>
      <div style={{ flex: 1, display: 'flex', gap: 14, minHeight: 0 }}>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0 }}>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
            <div style={{ width: 300 }}>
              <Input
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
              {rows.map((u) => (
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
                    <IconTile icon={<Ico n={u.type === 'Ambulance' ? 'ambulance' : 'truck'} />} tint={u.status === 'OUT_OF_SERVICE' ? 'slate' : 'navy'} size={26} />
                    <span>
                      <b>{u.id}</b>
                      <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>{u.type}</div>
                    </span>
                  </span>
                  <span style={{ width: 150 }}>
                    <Badge tone={STATUS_TONE[u.status]}>{u.status.replace('_', ' ')}</Badge>
                  </span>
                  <span style={{ width: 110, color: 'var(--color-text-secondary)' }}>{u.zone}</span>
                  <span style={{ flex: 1, color: 'var(--color-text-secondary)' }}>{u.base}</span>
                  <span style={{ width: 150, color: 'var(--color-text-secondary)' }}>{u.cap}</span>
                  <span style={{ width: 60, textAlign: 'right', fontWeight: 600 }}>{u.eta}</span>
                </button>
              ))}
            </div>
          </GlassPanel>
        </div>
        {sel ? (
          <Drawer title={`${sel.id} · ${sel.type}`} onClose={() => setSel(null)}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <IconTile icon={<Ico n={sel.type === 'Ambulance' ? 'ambulance' : 'truck'} />} tint="navy" size={42} />
              <div>
                <div style={{ fontSize: 15, fontWeight: 600 }}>{sel.id}</div>
                <Badge tone={STATUS_TONE[sel.status]}>{sel.status.replace('_', ' ')}</Badge>
              </div>
            </div>
            <div>
              <Fact label="Home base" value={sel.base} prov="source" />
              <Fact label="Current zone" value={sel.zone} prov="sim" />
              <Fact label="Capability" value={sel.cap} prov="source" />
              <Fact label="Assignment" value={sel.status === 'AVAILABLE' ? '—' : 'INC-2418'} prov="operator" />
              <Fact label="ETA" value={sel.eta} prov="sim" />
            </div>
            <Alert tone="simulated" title="Position simulated">
              Unit GPS comes from the prototype simulation gateway.
            </Alert>
            <div style={{ display: 'flex', gap: 8 }}>
              <Button variant="secondary" size="sm">Reposition</Button>
              <Button variant="critical" size="sm">Mark unavailable</Button>
            </div>
          </Drawer>
        ) : (
          <GlassPanel padding={14} style={{ width: 320, flexShrink: 0, alignSelf: 'flex-start' }}>
            <PanelHeader icon="hospital" title="Hospital readiness" right={<Badge tone="simulated">Simulated</Badge>} />
            {HOSPITAL_READINESS.map(([a, b]) => (
              <div key={a} style={{ display: 'flex', justifyContent: 'space-between', padding: '7px 0', borderBottom: '1px solid var(--color-border-hairline)', fontSize: 12.5 }}>
                <span>{a}</span>
                <span style={{ color: 'var(--color-text-secondary)' }}>{b}</span>
              </div>
            ))}
            <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)', marginTop: 10 }}>Select a unit to open its detail drawer.</div>
          </GlassPanel>
        )}
      </div>
    </Screen>
  );
}

export function TimelineScreen() {
  return (
    <Screen>
      <div style={{ flex: 1, display: 'flex', gap: 14, minHeight: 0 }}>
        <GlassPanel padding={16} style={{ flex: 1, minWidth: 0, overflowY: 'auto' }}>
          <PanelHeader icon="clock" title="INC-2418 · audit timeline" right={<Badge tone="neutral">Append-only</Badge>} />
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {AUDIT_EVENTS.map(([t, title, prov, detail], i) => (
              <div key={i} style={{ display: 'flex', gap: 14 }}>
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 52, flexShrink: 0 }}>
                  <span style={{ fontSize: 12.5, color: 'var(--color-text-muted)', fontWeight: 600 }}>{t}</span>
                  <span style={{ width: 1, flex: 1, background: 'var(--color-border-hairline)', marginTop: 4 }} />
                </div>
                <div style={{ paddingBottom: 18, flex: 1 }}>
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                    <span style={{ fontSize: 13, fontWeight: 600 }}>{title}</span>
                    <Prov kind={prov} />
                  </div>
                  <div style={{ fontSize: 12, color: 'var(--color-text-secondary)', marginTop: 3, lineHeight: 1.5 }}>{detail}</div>
                </div>
              </div>
            ))}
          </div>
        </GlassPanel>
        <div style={{ width: 360, display: 'flex', flexDirection: 'column', gap: 12, overflowY: 'auto' }}>
          <GlassPanel padding={14}>
            <PanelHeader icon="file-text" title="Evidence" />
            {AUDIT_EVIDENCE.map(([a, b, p]) => (
              <Card key={a} padding={11} style={{ marginBottom: 8 }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: 12.5, fontWeight: 600 }}>{a}</span>
                  <Prov kind={p} />
                </div>
                <div style={{ fontSize: 12.5, color: 'var(--color-text-secondary)', marginTop: 3 }}>{b}</div>
              </Card>
            ))}
          </GlassPanel>
          <GlassPanel padding={14}>
            <PanelHeader icon="git-compare" title="Conflicting evidence" />
            <div style={{ fontSize: 12.5, color: 'var(--color-text-secondary)', lineHeight: 1.6 }}>
              Caller stated “two cars”; scene image suggests three vehicles involved. Both records retained — operator review requested
              before casualty count is finalised.
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
              <Button variant="secondary" size="sm">Review conflict</Button>
            </div>
          </GlassPanel>
          <GlassPanel padding={14}>
            <PanelHeader icon="pencil" title="Operator notes" />
            <div style={{ fontSize: 12.5, lineHeight: 1.6 }}>
              Corrected location from “Abbas El Akkad” to the Tayaran intersection based on caller landmark. Previous value retained in
              history.
            </div>
          </GlassPanel>
        </div>
      </div>
    </Screen>
  );
}
