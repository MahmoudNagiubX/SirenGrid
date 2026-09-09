import { Alert, Badge, Button, Card, GlassPanel, IconTile } from '../components';
import { Ico } from '../lib/icon';
import { PanelHeader, Screen, SubHead } from './primitives';
import {
  BENCHMARK_METRICS,
  BENCHMARK_METRICS_PLANNED,
  DEMO_INJECTS,
  DEMO_SCENARIOS,
} from '../data/mock';
import { useCommandRunner, useOperations } from '../state/OperationsContext';
import { resetSimulation } from '../commands/operationsCommands';
import { RecoveryNotice } from '../recovery/RecoveryNotice';

/** Ported from ui_kits/operations_center/screens-support.jsx — bound to canonical simulation read state. */

function ScenarioRow({
  icon,
  title,
  sub,
  action,
  tone = 'slate',
}: {
  icon: string;
  title: string;
  sub: string;
  action: string;
  tone?: 'red' | 'navy' | 'blue' | 'slate';
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '12px 14px', borderRadius: 'var(--radius-md)', background: 'var(--color-bg-surface)', border: '1px solid var(--color-border-hairline)' }}>
      <IconTile icon={<Ico n={icon} />} tint={tone} size={34} />
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 600 }}>{title}</div>
        <div style={{ fontSize: 12.5, color: 'var(--color-text-secondary)' }}>{sub}</div>
      </div>
      <Button variant="secondary" size="sm" disabled>
        {action}
      </Button>
    </div>
  );
}

export function DemoScreen() {
  const { simulation, refreshGlobal } = useOperations();
  const { busyAction, message, run } = useCommandRunner();
  const sim = simulation.data;
  // Simulation mutations require the backend controller to be enabled (§37).
  const simEnabled = sim?.enabled === true;

  const simStatusRows: [string, string][] = [
    ['Simulation enabled', sim ? (sim.enabled ? 'Yes' : 'No') : '—'],
    ['Loaded scenario', sim ? (sim.loaded_scenario_id ?? 'None') : '—'],
    ['Random seed', sim && sim.seed !== null && sim.seed !== undefined ? `${sim.seed}` : '—'],
    ['Runtime version', sim ? `${sim.runtime_version}` : '—'],
    ['Event index', sim ? `${sim.event_index}` : '—'],
    ['Last event type', sim ? (sim.last_event_type ?? 'None') : '—'],
    ['Data reality', sim ? sim.reality : '—'],
  ];

  return (
    <Screen>
      <Alert tone="simulated" title="Demo & simulation controls">
        These controls drive prototype demonstration scenarios. Simulation status is read from the canonical backend. Mutation controls are wired in Phase 06.
      </Alert>
      {/* §37: canonical `enabled` truth is unavailable — do not imply a known state. */}
      {simulation.error != null ? (
        <RecoveryNotice
          kind="UNAVAILABLE"
          title="Simulation status unavailable"
          detail="Mutation controls stay disabled until canonical status is read."
          compact
          onRetry={() => void refreshGlobal({ includeSelected: false })}
          retryLabel="Refresh data"
        />
      ) : simulation.loading && sim == null ? (
        <RecoveryNotice kind="LOADING" title="Loading simulation status" compact />
      ) : null}
      <div style={{ flex: 1, display: 'flex', gap: 14, minHeight: 0 }}>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 12, overflowY: 'auto', minWidth: 0 }}>
          <SubHead>Scenarios</SubHead>
          <div style={{ display: 'flex', gap: 12 }}>
            {DEMO_SCENARIOS.map(([t, s]) => (
              <Card
                key={t}
                padding={14}
                style={{
                  flex: 1,
                  border: '1px solid var(--color-border-hairline)',
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                  <span style={{ fontSize: 13, fontWeight: 600 }}>{t}</span>
                  <Button variant="ghost" size="sm" disabled>
                    Load
                  </Button>
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
              />
            ))}
          </div>
        </div>
        <div style={{ width: 340, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <GlassPanel padding={14}>
            <PanelHeader icon="sliders-horizontal" title="Simulation clock" />
            <div style={{ fontSize: 30, fontWeight: 600, letterSpacing: '-0.01em' }}>
              {sim ? `Event #${sim.event_index}` : '—'}
            </div>
            <div style={{ fontSize: 12.5, color: 'var(--color-text-secondary)', marginTop: 2 }}>
              Runtime version: {sim ? `${sim.runtime_version}` : '—'}
            </div>
            <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
              <Button variant="secondary" size="sm" disabled>Pause</Button>
              <Button variant="secondary" size="sm" disabled>×2 speed</Button>
            </div>
          </GlassPanel>
          <GlassPanel padding={14}>
            <PanelHeader icon="database" title="Data reality & status" />
            {simStatusRows.map(([a, b]) => (
              <div key={a} style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid var(--color-border-hairline)', fontSize: 12 }}>
                <span style={{ color: 'var(--color-text-secondary)' }}>{a}</span>
                <span style={{ fontWeight: 500 }}>{b}</span>
              </div>
            ))}
          </GlassPanel>
          <Button
            variant="critical"
            size="md"
            disabled={!simEnabled || busyAction !== null}
            onClick={() => {
              void run('sim-reset', {
                command: () => resetSimulation(),
                refetch: () => refreshGlobal(),
                successText: 'Simulation reset. Canonical status reloaded.',
              });
            }}
          >
            {busyAction === 'sim-reset' ? 'Working…' : 'Reset demo state'}
          </Button>
          {!simEnabled && (
            <div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>
              Simulation controller is disabled in the backend. Mutation controls stay inactive.
            </div>
          )}
          {message && (
            <Alert
              tone={message.kind === 'success' ? 'info' : 'attention'}
              title={message.kind === 'conflict' ? 'State changed' : message.kind === 'error' ? 'Command failed' : 'Done'}
            >
              {message.text}
            </Alert>
          )}
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
