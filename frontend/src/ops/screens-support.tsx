import { useState } from 'react';
import { Alert, Badge, Button, Card, GlassPanel, IconTile } from '../components';
import { Ico } from '../lib/icon';
import { PanelHeader, Screen, SubHead } from './primitives';
import {
  BENCHMARK_METRICS,
  BENCHMARK_METRICS_PLANNED,
  DEMO_DATA_REALITY,
  DEMO_INJECTS,
  DEMO_SCENARIOS,
} from '../data/mock';

/** Ported from ui_kits/operations_center/screens-support.jsx. */

function ScenarioRow({
  icon,
  title,
  sub,
  action,
  tone = 'slate',
  onFire,
  fired,
}: {
  icon: string;
  title: string;
  sub: string;
  action: string;
  tone?: 'red' | 'navy' | 'blue' | 'slate';
  onFire: () => void;
  fired?: boolean;
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px', borderRadius: 'var(--radius-md)', background: 'var(--color-bg-surface)', border: '1px solid var(--color-border-hairline)' }}>
      <IconTile icon={<Ico n={icon} />} tint={tone} size={34} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 600 }}>{title}</div>
        <div style={{ fontSize: 12.5, color: 'var(--color-text-secondary)' }}>{sub}</div>
      </div>
      {fired ? (
        <Badge tone="confirmed">Injected</Badge>
      ) : (
        <Button variant="secondary" size="sm" onClick={onFire}>
          {action}
        </Button>
      )}
    </div>
  );
}

export function DemoScreen() {
  const [fired, setFired] = useState<Record<string, boolean>>({});
  const fire = (k: string) => setFired((f) => ({ ...f, [k]: true }));
  return (
    <Screen>
      <Alert tone="simulated" title="Demo & simulation controls">
        These controls exist only to drive the prototype demonstration. They inject simulated conditions into the operational model —
        they never represent live city infrastructure.
      </Alert>
      <div style={{ flex: 1, display: 'flex', gap: 14, minHeight: 0 }}>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 12, overflowY: 'auto', minWidth: 0 }}>
          <SubHead>Scenarios</SubHead>
          <div style={{ display: 'flex', gap: 12 }}>
            {DEMO_SCENARIOS.map(([t, s, active]) => (
              <Card key={t} padding={14} style={{ flex: 1, border: active ? '1.5px solid var(--color-accent)' : '1px solid var(--color-border-hairline)' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>{t}</span>
                  {active ? <Badge tone="confirmed">Loaded</Badge> : <Button variant="ghost" size="sm">Load</Button>}
                </div>
                <div style={{ fontSize: 12.5, color: 'var(--color-text-secondary)', marginTop: 4 }}>{s}</div>
              </Card>
            ))}
          </div>
          <SubHead>Inject conditions</SubHead>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {DEMO_INJECTS.map((row) => (
              <ScenarioRow
                key={row.key}
                icon={row.icon}
                tone={row.tone}
                title={row.title}
                sub={row.sub}
                action={row.action}
                fired={fired[row.key]}
                onFire={() => fire(row.key)}
              />
            ))}
          </div>
        </div>
        <div style={{ width: 340, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <GlassPanel padding={14}>
            <PanelHeader icon="sliders-horizontal" title="Simulation clock" />
            <div style={{ fontSize: 30, fontWeight: 600, letterSpacing: '-0.01em' }}>21:07:42</div>
            <div style={{ fontSize: 12.5, color: 'var(--color-text-secondary)', marginTop: 2 }}>Scenario elapsed 9 min 42 s</div>
            <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
              <Button variant="secondary" size="sm">Pause</Button>
              <Button variant="secondary" size="sm">×2 speed</Button>
            </div>
          </GlassPanel>
          <GlassPanel padding={14}>
            <PanelHeader icon="database" title="Data reality" />
            {DEMO_DATA_REALITY.map(([a, b]) => (
              <div key={a} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--color-border-hairline)', fontSize: 12 }}>
                <span style={{ color: 'var(--color-text-secondary)' }}>{a}</span>
                <span style={{ fontWeight: 500 }}>{b}</span>
              </div>
            ))}
          </GlassPanel>
          <Button variant="critical" size="md">Reset demo state</Button>
        </div>
      </div>
    </Screen>
  );
}

export function BenchmarkScreen() {
  return (
    <Screen>
      <Alert tone="attention" title="No performance claims yet">
        Benchmark scenarios have not been run for this prototype. Structural differences are described below; numeric improvements are
        intentionally left as “awaiting measured benchmark” rather than estimated.
      </Alert>
      <div style={{ display: 'flex', gap: 14, flex: 1, minHeight: 0 }}>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0, overflowY: 'auto' }}>
          <div style={{ display: 'flex', gap: 12 }}>
            <GlassPanel padding={16} style={{ flex: 1 }}>
              <PanelHeader icon="circle-dot" title="Baseline dispatch" tint="slate" />
              <div style={{ fontSize: 12.5, color: 'var(--color-text-secondary)', lineHeight: 1.7 }}>
                Send the nearest available ambulance and rescue unit, route by current fastest path, transport to the nearest suitable
                hospital. No coverage modelling, no plan comparison, no automatic re-evaluation when conditions change.
              </div>
            </GlassPanel>
            <GlassPanel padding={16} style={{ flex: 1, border: '1px solid var(--blue-300)' }}>
              <PanelHeader icon="shield-check" title="SirenGrid-assisted" tint="navy" />
              <div style={{ fontSize: 12.5, color: 'var(--color-text-secondary)', lineHeight: 1.7 }}>
                Interpret the call into structured facts, generate and compare candidate plans, model city coverage impact, rank hospitals
                by ETA + capability + modelled load, and re-evaluate on every material change — each critical action explicitly approved
                by the operator.
              </div>
            </GlassPanel>
          </div>
          <GlassPanel padding={0} style={{ overflow: 'hidden' }}>
            <div style={{ display: 'flex', padding: '11px 16px', borderBottom: '1px solid var(--color-border-hairline)', fontSize: 12, fontWeight: 600, letterSpacing: '.05em', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>
              <span style={{ flex: 1.5 }}>Metric</span>
              <span style={{ flex: 1 }}>Baseline</span>
              <span style={{ flex: 1 }}>SirenGrid</span>
              <span style={{ width: 210 }}>Result</span>
            </div>
            {BENCHMARK_METRICS.map(([m, b, s, r], i) => (
              <div key={i} style={{ display: 'flex', padding: '12px 16px', borderBottom: '1px solid var(--color-border-hairline)', fontSize: 12.5, alignItems: 'center' }}>
                <span style={{ flex: 1.5, fontWeight: 500 }}>{m}</span>
                <span style={{ flex: 1, color: 'var(--color-text-secondary)' }}>{b}</span>
                <span style={{ flex: 1, color: 'var(--color-text-secondary)' }}>{s}</span>
                <span style={{ width: 210 }}>
                  <Badge tone={r === 'Structural difference' ? 'info' : 'neutral'}>{r}</Badge>
                </span>
              </div>
            ))}
          </GlassPanel>
        </div>
        <div style={{ width: 320, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <GlassPanel padding={14}>
            <PanelHeader icon="list-checks" title="Planned evaluation set" />
            <div style={{ fontSize: 12.5, color: 'var(--color-text-secondary)', lineHeight: 1.7 }}>
              30–50 synthetic scenarios varying incident location, congestion, closed roads, unit positions, hospital capacity and a second
              active incident.
            </div>
          </GlassPanel>
          <GlassPanel padding={14}>
            <PanelHeader icon="gauge" title="Metrics to be measured" />
            {BENCHMARK_METRICS_PLANNED.map((m) => (
              <div key={m} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--color-border-hairline)', fontSize: 12 }}>
                <span>{m}</span>
                <span style={{ color: 'var(--color-text-muted)' }}>—</span>
              </div>
            ))}
          </GlassPanel>
        </div>
      </div>
    </Screen>
  );
}
