import { Fragment } from 'react';
import { Badge, GlassPanel, IconTile, Input } from '../components';
import { Ico } from '../lib/icon';
import { Prov } from './primitives';
import {
  DOCK_EVENTS,
  INCIDENTS,
  RAIL_RESOURCES,
  STATES,
  STATUS_KPIS,
  TOP_NAV,
  type OpsState,
  type TopNav,
} from '../data/mock';

/** Ported from ui_kits/operations_center/workspace.jsx (StatusStrip, StateSwitch, IncidentRail, TimelineDock). */

export function StatusStrip({ nav, setNav }: { nav: TopNav; setNav: (n: TopNav) => void }) {
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
        {STATUS_KPIS.map(([v, l], i) => (
          <Fragment key={l}>
            {i > 0 && <span style={{ width: 1, height: 22, background: 'var(--color-border-hairline)' }} />}
            <div style={{ display: 'flex', alignItems: 'baseline', gap: 7 }}>
              <span style={{ fontSize: 21, fontWeight: 600, letterSpacing: '-0.015em' }}>{v}</span>
              <span style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>{l}</span>
            </div>
          </Fragment>
        ))}
      </div>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
        <Badge tone="simulated">Simulated data</Badge>
        <button
          onClick={() => setNav('demo')}
          title="Scenario controls"
          aria-label="Scenario controls"
          style={{ border: 'none', background: 'transparent', padding: 0, cursor: 'pointer' }}
        >
          <IconTile icon={<Ico n="sliders-horizontal" />} tint={nav === 'demo' ? 'navy' : 'slate'} size={32} />
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
  return (
    <div style={{ width: 312, flexShrink: 0, display: 'flex', flexDirection: 'column', gap: 11, minHeight: 0 }}>
      <Input
        placeholder="Search incident, street, unit"
        icon={
          <span style={{ width: 16, height: 16, display: 'flex', color: 'var(--color-text-muted)' }}>
            <Ico n="search" />
          </span>
        }
      />
      <StateSwitch state={state} setState={setState} />
      <div style={{ display: 'flex', flexDirection: 'column', gap: 9, overflowY: 'auto', paddingRight: 2, flex: 1, minHeight: 0 }}>
        {INCIDENTS.map((inc) => {
          const on = selected === inc.id;
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
              <IconTile icon={<Ico n={inc.icon} />} tint={inc.sev === 'critical' || inc.sev === 'high' ? 'red' : 'navy'} size={34} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: 15, fontWeight: 600, letterSpacing: '-0.015em', lineHeight: 1.25 }}>{inc.title}</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginTop: 4 }}>
                  <Badge severity={inc.sev} />
                  <span style={{ fontSize: 13, color: 'var(--color-text-muted)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{inc.loc}</span>
                </div>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, marginTop: 4 }}>
                  <span style={{ fontSize: 13, fontWeight: 500, color: 'var(--color-text-secondary)', whiteSpace: 'nowrap' }}>
                    {inc.state} · {inc.t}
                  </span>
                  <span dir="rtl" style={{ fontFamily: 'var(--font-ar)', fontSize: 13, color: 'var(--color-text-muted)', whiteSpace: 'nowrap' }}>
                    {inc.ar}
                  </span>
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
        {RAIL_RESOURCES.map(([a, b]) => (
          <div key={a} style={{ display: 'flex', justifyContent: 'space-between', fontSize: 13.5, padding: '5px 0' }}>
            <span style={{ color: 'var(--color-text-muted)' }}>{a}</span>
            <span style={{ fontWeight: 600 }}>{b}</span>
          </div>
        ))}
      </GlassPanel>
    </div>
  );
}

export function TimelineDock({ open, setOpen }: { open: boolean; setOpen: (o: boolean) => void }) {
  return (
    <GlassPanel padding={0} style={{ flexShrink: 0 }}>
      <button
        onClick={() => setOpen(!open)}
        aria-expanded={open}
        style={{ width: '100%', border: 'none', background: 'transparent', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '11px 16px', fontFamily: 'var(--font-en)' }}
      >
        <span style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
          <IconTile icon={<Ico n="clock" />} tint="glass" size={28} />
          <span style={{ fontSize: 14, fontWeight: 600 }}>History · INC-2418</span>
        </span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 10, fontSize: 13, color: 'var(--color-text-secondary)' }}>
          {!open && (
            <span>
              {DOCK_EVENTS[0][0]} · {DOCK_EVENTS[0][1]}
            </span>
          )}
          <span style={{ width: 16, height: 16, display: 'flex' }}>
            <Ico n={open ? 'chevron-down' : 'chevron-up'} />
          </span>
        </span>
      </button>
      {open && (
        <div style={{ display: 'flex', padding: '2px 16px 14px', overflowX: 'auto' }}>
          {DOCK_EVENTS.map(([t, e, p], i) => (
            <div
              key={i}
              style={{
                minWidth: 226,
                paddingRight: 18,
                marginRight: 18,
                borderRight: i < DOCK_EVENTS.length - 1 ? '1px solid var(--color-border-hairline)' : 'none',
              }}
            >
              <div style={{ fontSize: 13, fontWeight: 700, color: 'var(--color-accent)' }}>{t}</div>
              <div style={{ fontSize: 13.5, lineHeight: 1.45, margin: '3px 0 6px' }}>{e}</div>
              <Prov kind={p} />
            </div>
          ))}
        </div>
      )}
    </GlassPanel>
  );
}
