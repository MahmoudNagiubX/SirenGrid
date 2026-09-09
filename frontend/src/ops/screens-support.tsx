import { useState } from 'react';
import { Alert, Badge, Button, Card, GlassPanel } from '../components';
import { Ico } from '../lib/icon';
import { useOperationsData } from '../state/OperationsContext';
import type { BenchmarkEngineAggregate, BenchmarkMetricSummary } from '../api/types';
import { PanelHeader, Screen, SubHead } from './primitives';

const DEMO_SCENARIOS = [
  ['T01_urgent_activation', 'Urgent activation / canonical planning'],
  ['X07_valid_closure', 'Validated closure / material replan'],
  ['X19_two_incidents_available', 'Two incidents / committed resources'],
];

function scalar(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'object') return 'See backend artifact';
  return String(value);
}

function SocialPanel() {
  const { socialSignals, selectedIncident, actionBusy, runSocialRefresh, runSocialDismiss, runSocialAssociate } = useOperationsData();
  const signals = socialSignals.data ?? [];
  return <GlassPanel padding={14}><PanelHeader icon="radio" title="Social intelligence" right={<Badge tone="neutral">UNVERIFIED</Badge>} /><div style={{ display: 'flex', gap: 8, marginBottom: 10 }}><Button size="sm" variant="secondary" onClick={() => void runSocialRefresh('synthetic')} disabled={actionBusy !== null}>Refresh demo feed</Button><Button size="sm" variant="ghost" onClick={() => void runSocialRefresh('bluesky')} disabled={actionBusy !== null}>Refresh Bluesky</Button></div>{socialSignals.error && <Alert tone="attention" title="Social provider unavailable">{socialSignals.error}</Alert>}{!signals.length && !socialSignals.loading && <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)' }}>No public signals returned. Provider failure does not affect manual operations.</div>}{signals.slice(0, 6).map((signal) => <Card key={signal.id} padding={10} style={{ marginBottom: 8 }}><div style={{ display: 'flex', justifyContent: 'space-between', gap: 8 }}><span style={{ fontSize: 12.5, fontWeight: 600 }}>{signal.source_reference}</span><Badge tone="simulated">{signal.data_reality}</Badge></div><div style={{ fontSize: 12.5, marginTop: 4 }}>{signal.raw_text || 'No text retained'}</div><div style={{ fontSize: 11.5, color: 'var(--color-text-muted)', marginTop: 4 }}>{signal.association_outcome ?? signal.processing_status}</div><div style={{ display: 'flex', gap: 6, marginTop: 8 }}>{!signal.incident_id && <><Button size="sm" variant="secondary" onClick={() => void runSocialAssociate(signal.id)} disabled={actionBusy !== null || !selectedIncident.data}>Associate to selected incident</Button><Button size="sm" variant="ghost" onClick={() => void runSocialDismiss(signal.id)} disabled={actionBusy !== null}>Dismiss</Button></>}</div></Card>)}</GlassPanel>;
}

export function DemoScreen() {
  const { simulation, actionBusy, runSimulationLoad, runSimulationReset, runSimulationEvent } = useOperationsData();
  const [loadedScenario, setLoadedScenario] = useState<string | null>(null);
  const enabled = simulation.data?.enabled === true;
  return <Screen><Alert tone="simulated" title="Demo & simulation controls">These controls mutate backend simulation state only. They are disabled by default and never represent live city infrastructure.</Alert>{simulation.error && <Alert tone="attention" title="Simulation controls unavailable">{simulation.error}</Alert>}<div style={{ flex: 1, display: 'flex', gap: 14, minHeight: 0 }}><div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 12, overflowY: 'auto', minWidth: 0 }}><SubHead>Backend scenarios</SubHead>{DEMO_SCENARIOS.map(([id, label]) => <Card key={id} padding={14} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}><div><div style={{ fontSize: 13, fontWeight: 600 }}>{label}</div><div style={{ fontSize: 12, color: 'var(--color-text-muted)' }}>{id} · SYNTHETIC fixture</div></div><Button size="sm" variant="secondary" disabled={!enabled || actionBusy !== null} onClick={() => { setLoadedScenario(id); void runSimulationLoad(id); }}>{loadedScenario === id ? 'Loaded' : 'Load'}</Button></Card>)}<SubHead>Explicit event advancement</SubHead><Card padding={14}><div style={{ display: 'flex', alignItems: 'center', gap: 10 }}><Ico n="clock" /><div style={{ flex: 1, fontSize: 13 }}>No background scheduler. Advance the loaded manifest in order.</div><Button size="sm" variant="secondary" disabled={!enabled || actionBusy !== null || !simulation.data?.scenario_id} onClick={() => void runSimulationEvent()}>Next event</Button></div></Card></div><div style={{ width: 340, display: 'flex', flexDirection: 'column', gap: 12 }}><GlassPanel padding={14}><PanelHeader icon="sliders-horizontal" title="Simulation status" /><div style={{ fontSize: 14, fontWeight: 600 }}>{enabled ? 'Enabled for demo' : 'Disabled by backend configuration'}</div><div style={{ fontSize: 12.5, color: 'var(--color-text-secondary)', marginTop: 5 }}>Scenario: {simulation.data?.scenario_id ?? 'None'}</div><div style={{ fontSize: 12.5, color: 'var(--color-text-secondary)' }}>Next event: {simulation.data?.next_event_index ?? '—'}</div><Badge tone="simulated">SIMULATED / DEMO ONLY</Badge></GlassPanel><Button variant="critical" size="md" disabled={!enabled || actionBusy !== null} onClick={() => void runSimulationReset()}>Reset demo state</Button></div></div><SocialPanel /></Screen>;
}

function outcomeSummary(outcomes: Record<string, number> | undefined): string {
  if (!outcomes) return 'â€”';
  return Object.entries(outcomes).map(([name, count]) => `${name}: ${count}`).join(' · ');
}

function metricSummary(metric: BenchmarkMetricSummary | undefined): string {
  if (!metric) return 'â€”';
  const mean = typeof metric.mean === 'number' ? `${metric.mean.toFixed(1)} mean` : null;
  const range = typeof metric.min === 'number' && typeof metric.max === 'number' ? `${metric.min.toFixed(1)}–${metric.max.toFixed(1)}` : null;
  return [mean, range].filter(Boolean).join(' · ') || 'â€”';
}

function metricAvailability(metric: BenchmarkMetricSummary | undefined): string {
  if (!metric) return 'â€”';
  return `${metric.available_count} measured · ${metric.missing_count} unavailable`;
}

export function BenchmarkScreen() {
  const { benchmark } = useOperationsData();
  const aggregate = benchmark.data?.aggregate;
  const engineRows: [string, BenchmarkEngineAggregate | undefined][] = [['Baseline', aggregate?.baseline], ['SirenGrid', aggregate?.sirengrid]];
  return <Screen><Alert tone="attention" title="Committed Phase 08 benchmark artifact">This view displays backend-owned measured results. Missing measurements remain unavailable; no browser-side benchmark claim is calculated.</Alert>{benchmark.error && <Alert tone="attention" title="Benchmark artifact unavailable">{benchmark.error}</Alert>}<div style={{ display: 'flex', gap: 14, flex: 1, minHeight: 0 }}><div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 12, minWidth: 0, overflowY: 'auto' }}><GlassPanel padding={0} style={{ overflow: 'hidden' }}><div style={{ display: 'flex', padding: '11px 16px', borderBottom: '1px solid var(--color-border-hairline)', fontSize: 12, fontWeight: 600, color: 'var(--color-text-muted)', textTransform: 'uppercase' }}><span style={{ flex: 0.65 }}>Engine</span><span style={{ flex: 0.65 }}>Scenarios</span><span style={{ flex: 1.7 }}>Outcomes</span><span style={{ flex: 1.2 }}>Incident ETA</span><span style={{ flex: 1.3 }}>Measured / unavailable</span></div>{engineRows.map(([label, values]) => <div key={label} style={{ display: 'flex', padding: '13px 16px', borderBottom: '1px solid var(--color-border-hairline)', fontSize: 13 }}><span style={{ flex: 0.65, fontWeight: 600 }}>{label}</span><span style={{ flex: 0.65 }}>{scalar(values?.count)}</span><span style={{ flex: 1.7 }}>{outcomeSummary(values?.outcome_counts)}</span><span style={{ flex: 1.2 }}>{metricSummary(values?.incident_eta_seconds)}</span><span style={{ flex: 1.3 }}>{metricAvailability(values?.incident_eta_seconds)}</span></div>)}</GlassPanel><GlassPanel padding={14}><PanelHeader icon="file-check" title="Benchmark provenance" />{Object.entries(benchmark.data?.metadata ?? {}).slice(0, 8).map(([key, value]) => <div key={key} style={{ display: 'flex', justifyContent: 'space-between', gap: 12, padding: '6px 0', borderBottom: '1px solid var(--color-border-hairline)', fontSize: 12 }}><span style={{ color: 'var(--color-text-secondary)' }}>{key.replaceAll('_', ' ')}</span><span>{scalar(value)}</span></div>)}</GlassPanel></div><div style={{ width: 320, display: 'flex', flexDirection: 'column', gap: 12 }}><GlassPanel padding={14}><PanelHeader icon="shield-check" title="Reality" right={<Badge tone="simulated">SYNTHETIC</Badge>} /><div style={{ fontSize: 12.5, lineHeight: 1.6, color: 'var(--color-text-secondary)' }}>The artifact is a fixed Phase 08 benchmark fixture grounded in real-public/derived static assets. It is not a production SLA or a live traffic claim.</div></GlassPanel><GlassPanel padding={14}><PanelHeader icon="list-checks" title="Validation" />{(benchmark.data?.validation ?? []).slice(0, 15).map((item) => <div key={item.scenario_id} style={{ display: 'flex', justifyContent: 'space-between', padding: '5px 0', fontSize: 12 }}><span>{item.scenario_id}</span><Badge tone={item.passed ? 'confirmed' : 'neutral'}>{item.passed ? 'PASS' : 'FAIL'}</Badge></div>)}</GlassPanel></div></div></Screen>;
}
