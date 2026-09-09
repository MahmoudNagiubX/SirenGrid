import { Fragment, useState } from 'react';
import { Alert, Badge, Button, Card, ConfidenceMeter, GlassPanel, IconTile } from '../components';
import { Ico } from '../lib/icon';
import { AiBlock, ApprovalBar, Prov, SubHead } from './primitives';
import {
  ACTIVE_EXECUTED,
  ACTIVE_UNITS,
  COVERAGE_ZONES,
  DEC_TABS,
  EVIDENCE_ITEMS,
  EVIDENCE_TRANSCRIPT_AR,
  FOCUS_INCIDENT,
  HISTORY_EVENTS,
  HOSPITALS,
  PLANS,
  PLAN_COMPARE,
  REPLAN_ROUTES,
  type DecisionTab,
  type OpsState,
} from '../data/mock';

/** Ported from ui_kits/operations_center/decision.jsx. */

function StateBanner({ state }: { state: OpsState }) {
  const MAP: Partial<Record<OpsState, [string, 'red' | 'navy', string, string, string, string]>> = {
    replan: ['octagon-x', 'red', 'Abbas El Akkad eastbound closed', '21:06 · approved route invalid', 'var(--color-critical-soft)', 'var(--red-200)'],
    active: ['check', 'navy', 'Plan v2 approved · executing', 'A1 3:10 · F3 4:05 · corridor 4/6', 'var(--color-confirmed-soft)', 'var(--blue-300)'],
    coverage: ['shield-check', 'navy', 'Coverage impact', 'Zone C 92% → 78% after dispatch', 'var(--gray-100)', 'var(--color-border-hairline)'],
  };
  const m = MAP[state];
  if (!m) return null;
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 11, padding: 12, borderRadius: 'var(--radius-md)', background: m[4], border: `1px solid ${m[5]}` }}>
      <IconTile icon={<Ico n={m[0]} />} tint={m[1]} size={32} />
      <div>
        <div style={{ fontSize: 14, fontWeight: 600 }}>{m[2]}</div>
        <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>{m[3]}</div>
      </div>
    </div>
  );
}

function Row({ a, b, tone }: { a: string; b: string; tone?: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', borderBottom: '1px solid var(--color-border-hairline)', fontSize: 14 }}>
      <span style={{ color: 'var(--color-text-muted)' }}>{a}</span>
      <span style={{ fontWeight: 600, color: tone ?? 'var(--color-text-primary)' }}>{b}</span>
    </div>
  );
}

function OverviewTab({ state }: { state: OpsState }) {
  if (state === 'coverage') {
    return (
      <Fragment>
        <SubHead>Zone coverage · before → after</SubHead>
        {COVERAGE_ZONES.map(([z, b, a]) => (
          <div key={z} style={{ padding: '6px 0' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 14, marginBottom: 6 }}>
              <span>{z}</span>
              <span style={{ color: 'var(--color-text-muted)' }}>
                {b}% → <b style={{ color: a < 85 ? 'var(--color-critical)' : 'var(--color-text-primary)' }}>{a}%</b>
              </span>
            </div>
            <div style={{ height: 7, borderRadius: 4, background: 'var(--gray-200)' }}>
              <div style={{ width: a + '%', height: '100%', borderRadius: 4, background: a < 85 ? 'var(--color-critical)' : 'var(--color-accent)' }} />
            </div>
          </div>
        ))}
        <AiBlock title="Balance recommendation" footer={<Button variant="primary" size="sm">Send for approval</Button>}>
          Repositioning A5 into the Makram Ebeid corridor restores Zone C to ~92% without changing the INC-2418 response.
        </AiBlock>
      </Fragment>
    );
  }
  if (state === 'active') {
    return (
      <Fragment>
        <SubHead>Executed</SubHead>
        {ACTIVE_EXECUTED.map(([a, b]) => (
          <div key={a} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', borderBottom: '1px solid var(--color-border-hairline)' }}>
            <span style={{ fontSize: 14 }}>{a}</span>
            <span style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--color-text-muted)' }}>
              {b}
              <span style={{ width: 17, height: 17, display: 'flex', color: 'var(--color-confirmed)' }}>
                <Ico n="circle-check" />
              </span>
            </span>
          </div>
        ))}
        <SubHead>Units</SubHead>
        {ACTIVE_UNITS.map(([a, b]) => (
          <Row key={a} a={a} b={b} />
        ))}
      </Fragment>
    );
  }
  return (
    <Fragment>
      <div style={{ display: 'flex', gap: 14, padding: '2px 0 8px' }}>
        <div style={{ flex: 1 }}>
          <SubHead>Severity</SubHead>
          <div style={{ fontSize: 18, fontWeight: 600, color: 'var(--color-critical)', marginTop: 5 }}>Critical</div>
        </div>
        <span style={{ width: 1, background: 'var(--color-border-hairline)' }} />
        <div style={{ flex: 1.1 }}>
          <SubHead>AI confidence</SubHead>
          <div style={{ marginTop: 7 }}>
            <ConfidenceMeter level="high" label="High" />
          </div>
        </div>
      </div>
      <SubHead>Known</SubHead>
      <Row a="Type" b="Multi-vehicle crash" />
      <Row a="Trapped" b="1 person" />
      <Row a="Road" b="2 lanes blocked" />
      <SubHead>Unknown</SubHead>
      <Row a="Casualty count" b="Not stated" tone="var(--color-text-muted)" />
      <AiBlock title="AI interpretation">Major road crash with a trapped occupant. Routing avoids the eastbound carriageway.</AiBlock>
      <Button variant="ghost" size="sm" full>View full evidence</Button>
    </Fragment>
  );
}

function PlanTab({ state }: { state: OpsState }) {
  const [sel, setSel] = useState('B');
  const [approved, setApproved] = useState(false);
  if (state === 'replan') {
    return (
      <Fragment>
        <div style={{ display: 'flex', gap: 10 }}>
          {REPLAN_ROUTES.map(([t, eta, via, on]) => (
            <Card key={t} padding={13} style={{ flex: 1, borderColor: on ? 'var(--color-accent)' : 'var(--color-border-hairline)' }}>
              <SubHead>{t}</SubHead>
              <div style={{ fontSize: 24, fontWeight: 600, marginTop: 4, color: on ? 'var(--color-accent)' : 'var(--color-text-muted)' }}>{eta}</div>
              <div style={{ fontSize: 13, color: 'var(--color-text-muted)', marginTop: 2 }}>via {via}</div>
            </Card>
          ))}
        </div>
        <AiBlock title="Why it changed">Closure invalidates v2. El Nasr Rd. adds 45 s but stays clear. Hospital unchanged.</AiBlock>
        <ApprovalBar approved={approved} note={approved ? 'Replan v3 active · v2 archived' : 'Re-approval required before reroute'} onApprove={() => setApproved(true)} />
      </Fragment>
    );
  }
  return (
    <Fragment>
      <div style={{ borderRadius: 'var(--radius-md)', border: '1px solid var(--color-border-hairline)', overflow: 'hidden' }}>
        <div style={{ display: 'grid', gridTemplateColumns: '78px 1fr 1fr 1fr', background: 'var(--gray-100)', fontSize: 12, fontWeight: 700, letterSpacing: '0.06em', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>
          {['', 'A', 'B', 'C'].map((h, i) => (
            <div key={i} style={{ padding: '9px 10px', textAlign: i ? 'center' : 'left' }}>{h}</div>
          ))}
        </div>
        {PLAN_COMPARE.map(([label, vals]) => (
          <div key={label} style={{ display: 'grid', gridTemplateColumns: '78px 1fr 1fr 1fr', borderTop: '1px solid var(--color-border-hairline)', alignItems: 'center' }}>
            <div style={{ padding: '10px', fontSize: 13, color: 'var(--color-text-muted)' }}>{label}</div>
            {vals.map((v, i) => {
              const bad = label === 'Coverage' && i === 0;
              return (
                <div
                  key={i}
                  style={{
                    padding: '10px',
                    textAlign: 'center',
                    fontSize: 16,
                    fontWeight: 600,
                    color: bad ? 'var(--color-critical)' : i === 1 ? 'var(--color-accent)' : 'var(--color-text-primary)',
                    background: i === 1 ? 'var(--color-accent-soft)' : 'transparent',
                  }}
                >
                  {v}
                </div>
              );
            })}
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {PLANS.map((p) => (
          <button
            key={p.id}
            onClick={() => setSel(p.id)}
            style={{
              textAlign: 'left',
              cursor: 'pointer',
              fontFamily: 'var(--font-en)',
              borderRadius: 'var(--radius-md)',
              padding: 12,
              border: sel === p.id ? '1.5px solid var(--color-accent)' : '1px solid var(--color-border-hairline)',
              background: sel === p.id ? 'var(--color-accent-soft)' : 'var(--color-bg-surface)',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 14, fontWeight: 600 }}>{p.name}</span>
              {p.rec && <Badge tone="info">AI pick</Badge>}
            </div>
            <div style={{ fontSize: 13, color: 'var(--color-text-muted)', marginTop: 3 }}>{p.units}</div>
          </button>
        ))}
      </div>
      <AiBlock title="Why Plan B">Plan A arrives 40 s sooner but drops Zone C to 81%. Plan B holds A2 and repositions A5.</AiBlock>
      <ApprovalBar approved={approved} note={approved ? 'Plan v2 locked · audit entry created' : 'Dispatch and repositioning need approval'} onApprove={() => setApproved(true)} />
    </Fragment>
  );
}

function HospitalTab() {
  const [sel, setSel] = useState('El Nozha Hospital');
  const [all, setAll] = useState(false);
  const list = all ? HOSPITALS : HOSPITALS.slice(0, 2);
  return (
    <Fragment>
      <AiBlock title="Destination rationale">
        Nasr Specialised is closer but at 96% load with no trauma bay. El Nozha has capacity for two casualties.
      </AiBlock>
      <SubHead>Candidates · 2 casualties</SubHead>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
        {list.map((h) => (
          <button
            key={h.n}
            onClick={() => setSel(h.n)}
            style={{
              textAlign: 'left',
              cursor: 'pointer',
              fontFamily: 'var(--font-en)',
              display: 'flex',
              gap: 12,
              alignItems: 'center',
              padding: 13,
              borderRadius: 'var(--radius-md)',
              border: sel === h.n ? '1.5px solid var(--color-accent)' : '1px solid var(--color-border-hairline)',
              background: sel === h.n ? 'var(--color-accent-soft)' : 'var(--color-bg-surface)',
            }}
          >
            <IconTile icon={<Ico n="hospital" />} tint={h.load > 85 ? 'red' : 'navy'} size={38} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap' }}>
                <span style={{ fontSize: 14.5, fontWeight: 600 }}>{h.n}</span>
                {h.rec && <Badge tone="info">Recommended</Badge>}
                {h.stale && <Badge tone="neutral">Stale</Badge>}
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 13, color: 'var(--color-text-muted)', marginTop: 2 }}>
                <span>{h.cap}</span>
                <span dir="rtl" style={{ fontFamily: 'var(--font-ar)' }}>{h.ar}</span>
              </div>
              <div style={{ height: 7, borderRadius: 4, background: 'var(--gray-200)', marginTop: 8 }}>
                <div style={{ width: h.load + '%', height: '100%', borderRadius: 4, background: h.load > 85 ? 'var(--color-critical)' : 'var(--color-accent)' }} />
              </div>
              <div style={{ fontSize: 13, color: h.load > 85 ? 'var(--color-critical)' : 'var(--color-text-muted)', marginTop: 4 }}>{h.load}% modelled load</div>
            </div>
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 18, fontWeight: 600 }}>{h.eta}</div>
              <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)' }}>ETA</div>
            </div>
          </button>
        ))}
      </div>
      {!all && (
        <Button variant="ghost" size="sm" full onClick={() => setAll(true)}>
          View all 3 candidates
        </Button>
      )}
    </Fragment>
  );
}

function EvidenceTab() {
  return (
    <Fragment>
      <SubHead>Evidence · 4</SubHead>
      {EVIDENCE_ITEMS.map(([a, b, p, i]) => (
        <Card key={a} padding={12} style={{ display: 'flex', gap: 11, alignItems: 'center' }}>
          <IconTile icon={<Ico n={i} />} tint="slate" size={32} />
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
              <span style={{ fontSize: 14, fontWeight: 600 }}>{a}</span>
              <Prov kind={p} />
            </div>
            <div style={{ fontSize: 13, color: 'var(--color-text-muted)', marginTop: 2 }}>{b}</div>
          </div>
        </Card>
      ))}
      <div
        dir="rtl"
        style={{ fontFamily: 'var(--font-ar)', fontSize: 15, background: 'var(--gray-50)', borderRadius: 'var(--radius-md)', padding: 14, lineHeight: 1.9, border: '1px solid var(--color-border-hairline)' }}
      >
        {EVIDENCE_TRANSCRIPT_AR}
      </div>
      <Alert tone="attention" title="Conflicting evidence">
        Caller said two cars; the image suggests three. Operator review requested.
      </Alert>
    </Fragment>
  );
}

function HistoryTab() {
  return (
    <Fragment>
      {HISTORY_EVENTS.map(([t, title, prov], i) => (
        <div key={i} style={{ display: 'flex', gap: 13 }}>
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 44, flexShrink: 0 }}>
            <span style={{ fontSize: 13, color: 'var(--color-text-muted)', fontWeight: 600 }}>{t}</span>
            <span style={{ width: 1, flex: 1, background: 'var(--color-border-hairline)', marginTop: 4 }} />
          </div>
          <div style={{ paddingBottom: 15, flex: 1 }}>
            <div style={{ fontSize: 14, fontWeight: 600 }}>{title}</div>
            <div style={{ marginTop: 5 }}>
              <Prov kind={prov} />
            </div>
          </div>
        </div>
      ))}
    </Fragment>
  );
}

export function DecisionWorkspace({
  state,
  tab,
  setTab,
}: {
  state: OpsState;
  tab: DecisionTab;
  setTab: (t: DecisionTab) => void;
}) {
  return (
    <GlassPanel padding={0} style={{ width: 400, flexShrink: 0, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <div style={{ padding: '15px 16px 12px', borderBottom: '1px solid var(--color-border-hairline)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
          <div>
            <div style={{ fontSize: 18, fontWeight: 600, letterSpacing: '-0.015em' }}>{FOCUS_INCIDENT.title}</div>
            <div style={{ fontSize: 13, color: 'var(--color-text-muted)', marginTop: 2 }}>
              {FOCUS_INCIDENT.id} · {FOCUS_INCIDENT.t}
            </div>
          </div>
          <Badge severity="critical" />
        </div>
        <div role="tablist" style={{ display: 'flex', gap: 3, padding: 3, borderRadius: 'var(--radius-md)', background: 'var(--gray-100)' }}>
          {DEC_TABS.map(([id, label]) => {
            const on = tab === id;
            return (
              <button
                key={id}
                role="tab"
                aria-selected={on}
                onClick={() => setTab(id)}
                style={{
                  flex: 1,
                  padding: '7px 4px',
                  border: 'none',
                  borderRadius: 'var(--radius-sm)',
                  cursor: 'pointer',
                  fontFamily: 'var(--font-en)',
                  fontSize: 13,
                  fontWeight: on ? 600 : 500,
                  background: on ? 'var(--color-bg-surface)' : 'transparent',
                  color: on ? 'var(--color-text-primary)' : 'var(--color-text-muted)',
                  boxShadow: on ? 'var(--shadow-xs)' : 'none',
                }}
              >
                {label}
              </button>
            );
          })}
        </div>
      </div>
      <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12, overflowY: 'auto', minHeight: 0 }}>
        <StateBanner state={state} />
        {tab === 'overview' && <OverviewTab state={state} />}
        {tab === 'plan' && <PlanTab state={state} />}
        {tab === 'hospital' && <HospitalTab />}
        {tab === 'evidence' && <EvidenceTab />}
        {tab === 'history' && <HistoryTab />}
      </div>
    </GlassPanel>
  );
}
