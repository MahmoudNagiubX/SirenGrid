import { Fragment, useState } from 'react';
import { Alert, Badge, Button, Card, GlassPanel, IconTile } from '../components';
import { Ico } from '../lib/icon';
import { useOperationsData } from '../state/OperationsContext';
import type { HospitalOption, JsonRecord, Report, ResponsePlan } from '../api/types';
import { DEC_TABS, type DecisionTab, type OpsState } from '../data/mock';
import { AiBlock, ApprovalBar, Fact, Prov, SubHead } from './primitives';

const unknownText = 'Unknown';

function display(value: unknown, fallback = unknownText): string {
  if (value === null || value === undefined || value === '') return fallback;
  if (typeof value === 'boolean') return value ? 'Yes' : 'No';
  return String(value);
}

function eta(route: JsonRecord | undefined): string {
  const value = route?.eta_seconds;
  return typeof value === 'number' ? `${Math.round(value)} s` : unknownText;
}

function routeFor(plan: ResponsePlan): JsonRecord | undefined {
  return plan.routes.find((route) => route.resource_id) ?? plan.routes[0];
}

function realityTone(reality: string | undefined): 'neutral' | 'info' | 'confirmed' | 'simulated' {
  if (reality === 'REAL_LIVE' || reality === 'REAL_PUBLIC') return 'confirmed';
  if (reality === 'REAL_DERIVED') return 'info';
  if (reality === 'SIMULATED' || reality === 'SYNTHETIC') return 'simulated';
  return 'neutral';
}

function Reality({ value }: { value?: string }) {
  return <Badge tone={realityTone(value)}>{value ?? 'UNKNOWN'}</Badge>;
}

function StateBanner({ state }: { state: OpsState }) {
  const { selectedIncident, replan } = useOperationsData();
  const incident = selectedIncident.data;
  if (!incident) return null;
  const pending = replan.data?.pending_plan_id ?? incident.pending_replan_plan_id;
  const content = state === 'replan' && pending
    ? ['refresh-cw', 'Replacement recommendation awaiting approval', `Active plan ${incident.current_plan_id ?? 'Unknown'} remains operational · pending ${pending}`]
    : ['circle-check', `Incident ${incident.status.replaceAll('_', ' ')}`, `Version ${incident.version} · ${incident.current_plan_id ? `active plan ${incident.current_plan_id}` : 'no approved plan'}`];
  return <div style={{ display: 'flex', alignItems: 'center', gap: 11, padding: 12, borderRadius: 'var(--radius-md)', background: state === 'replan' ? 'var(--color-critical-soft)' : 'var(--color-confirmed-soft)', border: '1px solid var(--color-border-hairline)' }}><IconTile icon={<Ico n={content[0]} />} tint={state === 'replan' ? 'red' : 'navy'} size={32} /><div><div style={{ fontSize: 14, fontWeight: 600 }}>{content[1]}</div><div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>{content[2]}</div></div></div>;
}

function OverviewTab() {
  const { selectedIncident, operationalState, resources, reports } = useOperationsData();
  const incident = selectedIncident.data;
  if (!incident) return <Alert tone="attention" title="Incident unavailable">Select an incident returned by the backend.</Alert>;
  const assigned = resources.data?.filter((resource) => resource.assigned_incident_id === incident.id) ?? [];
  const latestReport = reports.data?.[0];
  return <Fragment>
    <div style={{ display: 'flex', gap: 14, padding: '2px 0 8px' }}><div style={{ flex: 1 }}><SubHead>Severity</SubHead><div style={{ fontSize: 18, fontWeight: 600, color: 'var(--color-critical)', marginTop: 5 }}>{display(incident.severity)}</div></div><span style={{ width: 1, background: 'var(--color-border-hairline)' }} /><div style={{ flex: 1.1 }}><SubHead>Evidence confidence</SubHead><div style={{ marginTop: 7 }}><Badge tone="info">{display(incident.confidence_level)}</Badge></div></div></div>
    <SubHead>Confirmed / known fields</SubHead>
    <Fact label="Incident type" value={incident.incident_type.replaceAll('_', ' ')} prov="source" />
    <Fact label="Location" value={incident.location_text ?? 'Unresolved'} unknown={!incident.location_text} prov="source" />
    <Fact label="Casualties" value={incident.casualty_count ?? incident.casualty_range ?? unknownText} unknown={incident.casualty_count === null && !incident.casualty_range} prov="source" />
    <Fact label="Trapped person" value={display(incident.trapped_person)} unknown={incident.trapped_person === null} prov="source" />
    <Fact label="Road blockage" value={display(incident.road_blockage)} unknown={incident.road_blockage === null} prov="source" />
    <Fact label="Transport required" value={display(incident.transport_required)} unknown={incident.transport_required === null} prov="source" />
    <SubHead>Current operational state</SubHead>
    <Fact label="Assigned resources" value={assigned.length ? assigned.map((resource) => resource.id).join(', ') : unknownText} unknown={!assigned.length} prov="operator" />
    <Fact label="Active plan" value={incident.current_plan_id ?? unknownText} unknown={!incident.current_plan_id} prov="operator" />
    <Fact label="Selected destination" value={display(operationalState.data?.selected_destination?.hospital_id)} unknown={!operationalState.data?.selected_destination} prov="operator" />
    {latestReport && <AiBlock title="Latest evidence interpretation"><span>{latestReport.raw_text}</span><div style={{ marginTop: 8 }}><Reality value={latestReport.data_reality} /></div></AiBlock>}
  </Fragment>;
}

function PlanCard({ plan, selected, onSelect }: { plan: ResponsePlan; selected: boolean; onSelect: () => void }) {
  const route = routeFor(plan);
  return <button onClick={onSelect} style={{ width: '100%', textAlign: 'left', cursor: 'pointer', fontFamily: 'var(--font-en)', borderRadius: 'var(--radius-md)', padding: 12, border: selected ? '1.5px solid var(--color-accent)' : '1px solid var(--color-border-hairline)', background: selected ? 'var(--color-accent-soft)' : 'var(--color-bg-surface)' }}><div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}><span style={{ fontSize: 14, fontWeight: 600 }}>Plan {plan.candidate_rank ?? plan.plan_version} · {plan.status.replaceAll('_', ' ')}</span><Badge tone={plan.status === 'APPROVED' ? 'confirmed' : plan.status === 'RECOMMENDED' ? 'info' : 'neutral'}>{plan.status}</Badge></div><div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', fontSize: 13, color: 'var(--color-text-muted)', marginTop: 5 }}><span>Resources: {plan.resource_ids.join(', ') || unknownText}</span><span>ETA: {eta(route)}</span><span>Score: {typeof plan.score_breakdown.final_score === 'number' ? String(plan.score_breakdown.final_score) : unknownText}</span></div></button>;
}

function PlanTab({ state }: { state: OpsState }) {
  const { selectedIncident, plans, replan, actionBusy, runGenerateCandidates, runApprovePlan } = useOperationsData();
  const incident = selectedIncident.data;
  const [selectedPlanId, setSelectedPlanId] = useState<string | null>(null);
  if (!incident) return <Alert tone="attention" title="No incident selected">Planning requires a backend incident.</Alert>;
  const planList = plans.data ?? [];
  const active = incident.current_plan_id ? planList.find((plan) => plan.id === incident.current_plan_id) : undefined;
  const pending = incident.pending_replan_plan_id ? planList.find((plan) => plan.id === incident.pending_replan_plan_id) : undefined;
  const selected = planList.find((plan) => plan.id === selectedPlanId) ?? pending ?? planList.find((plan) => plan.status === 'RECOMMENDED') ?? planList[0];
  return <Fragment>
    {state === 'replan' && <AiBlock title="Deterministic replan explanation">{replan.data?.trigger_reasons?.join(', ') || 'No pending trigger reasons returned.'}<div style={{ marginTop: 8 }}><Reality value="REAL_DERIVED" /></div></AiBlock>}
    {active && state === 'replan' && <Card padding={12}><SubHead>Active approved plan</SubHead><div style={{ marginTop: 5 }}>{active.id} · remains operational while replacement awaits approval</div></Card>}
    {!planList.length && <Alert tone="attention" title="No candidate plans">Generate candidates from the canonical backend planner.</Alert>}
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>{planList.map((plan) => <PlanCard key={plan.id} plan={plan} selected={selected?.id === plan.id} onSelect={() => setSelectedPlanId(plan.id)} />)}</div>
    {selected?.score_breakdown && <AiBlock title="Backend explanation">{Object.entries(selected.score_breakdown).filter(([, value]) => ['string', 'number', 'boolean'].includes(typeof value)).map(([key, value]) => <div key={key}>{key.replaceAll('_', ' ')}: {String(value)}</div>)}</AiBlock>}
    {!planList.length && <Button full onClick={() => void runGenerateCandidates()} disabled={actionBusy !== null}>{actionBusy === 'generate-candidates' ? 'Generating…' : 'Generate canonical candidates'}</Button>}
    {selected && selected.status === 'RECOMMENDED' && <ApprovalBar approved={false} note={`Version-safe approval for incident v${incident.version}, plan v${selected.plan_version}.`} onApprove={() => void runApprovePlan(selected)} />}
    {selected?.status === 'APPROVED' && <ApprovalBar approved note="Backend confirms this plan is active." />}
  </Fragment>;
}

function HospitalTab() {
  const { selectedIncident, operationalState, actionBusy, runGenerateHospitalOptions, runSelectHospital, runPreAlert } = useOperationsData();
  const incident = selectedIncident.data;
  const options = operationalState.data?.hospital_options;
  const selectedDestination = operationalState.data?.selected_destination;
  if (!incident) return <Alert tone="attention" title="No incident selected">Hospital state is incident-scoped.</Alert>;
  if (incident.transport_required === false) return <Alert tone="info" title="Hospital not required">Backend says transport is not required for this incident.</Alert>;
  if (incident.transport_required === null) return <Alert tone="attention" title="Operator confirmation required">Transport requirement is UNKNOWN; the backend will not recommend a hospital until it is confirmed.</Alert>;
  return <Fragment><AiBlock title="Backend hospital ranking">Static OSM location, simulated operational state, and the approved Phase 05 score are returned by the backend. No score is calculated in the browser.</AiBlock>{!options && <Button full onClick={() => void runGenerateHospitalOptions()} disabled={actionBusy !== null}>{actionBusy === 'hospital-options' ? 'Loading options…' : 'Generate hospital options'}</Button>}{options && <><SubHead>Options · {options.options.length}</SubHead><div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>{options.options.map((option) => <HospitalOptionCard key={option.option_id} option={option} selected={selectedDestination?.hospital_id === option.hospital.id} onSelect={() => void runSelectHospital(option.hospital.id)} disabled={actionBusy !== null} />)}</div>{selectedDestination && !operationalState.data?.hospital_pre_alert && <Button full onClick={() => void runPreAlert()} disabled={actionBusy !== null}>{actionBusy === 'pre-alert' ? 'Requesting…' : 'Send simulated pre-alert'}</Button>}{operationalState.data?.hospital_pre_alert && <Alert tone="simulated" title="Simulated hospital gateway">Pre-alert state: {String(operationalState.data.hospital_pre_alert.status)}</Alert>}</>}</Fragment>;
}

function HospitalOptionCard({ option, selected, onSelect, disabled }: { option: HospitalOption; selected: boolean; onSelect: () => void; disabled: boolean }) {
  const route = option.route;
  const hospital = option.hospital;
  const capability = option.score_breakdown.capability_status ?? option.score_breakdown.capability_penalty ?? unknownText;
  const source = option.score_breakdown.capability_source ?? (hospital.simulated_capability_tags.length ? 'SIMULATED_OVERLAY' : 'UNKNOWN');
  return <button onClick={onSelect} disabled={disabled} style={{ textAlign: 'left', cursor: disabled ? 'not-allowed' : 'pointer', fontFamily: 'var(--font-en)', display: 'flex', gap: 12, alignItems: 'center', padding: 13, borderRadius: 'var(--radius-md)', border: selected ? '1.5px solid var(--color-accent)' : '1px solid var(--color-border-hairline)', background: selected ? 'var(--color-accent-soft)' : 'var(--color-bg-surface)', opacity: disabled ? 0.65 : 1 }}><IconTile icon={<Ico n="hospital" />} tint={hospital.accepting_state === 'NOT_ACCEPTING' ? 'red' : 'navy'} size={38} /><div style={{ flex: 1, minWidth: 0 }}><div style={{ display: 'flex', gap: 7, alignItems: 'center', flexWrap: 'wrap' }}><span style={{ fontSize: 14.5, fontWeight: 600 }}>{hospital.name ?? hospital.id}</span>{selected && <Badge tone="confirmed">Selected</Badge>}</div><div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', fontSize: 13, color: 'var(--color-text-muted)', marginTop: 3 }}><span>Rank {option.rank}</span><span>ETA {eta(route)}</span><span>Load {hospital.simulated_load_ratio === null ? unknownText : `${Math.round(hospital.simulated_load_ratio * 100)}%`}</span><Reality value={source === 'SIMULATED_OVERLAY' ? 'SIMULATED' : hospital.static_provenance.data_reality as string | undefined} /></div><div style={{ fontSize: 12.5, color: 'var(--color-text-secondary)', marginTop: 4 }}>Capability: {display(capability)} · source {String(source)}</div></div><div style={{ textAlign: 'right' }}><div style={{ fontSize: 18, fontWeight: 600 }}>{typeof option.score === 'number' ? option.score.toFixed(3) : unknownText}</div><div style={{ fontSize: 12.5, color: 'var(--color-text-muted)' }}>cost</div></div></button>;
}

function EvidenceTab() {
  const { reports } = useOperationsData();
  const list = reports.data ?? [];
  return <Fragment><SubHead>Reports · {list.length}</SubHead>{!list.length && <Alert tone="info" title="No reports">The backend has no reports attached to this incident.</Alert>}{list.map((report: Report) => <Card key={report.id} padding={12}><div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'center' }}><span style={{ fontSize: 14, fontWeight: 600 }}>{report.source_type}</span><Reality value={report.data_reality} /></div><div style={{ fontSize: 13, color: 'var(--color-text-secondary)', marginTop: 4 }}>{report.raw_text}</div><div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginTop: 5 }}>{report.location_text ?? 'Location unknown'} · {report.processing_status}</div></Card>)}<Alert tone="attention" title="Evidence is not operational authority">AI or external evidence remains review-oriented until an operator confirms material facts.</Alert></Fragment>;
}

function HistoryTab() {
  const { timeline } = useOperationsData();
  return <Fragment>{(timeline.data ?? []).map((event) => <div key={event.id} style={{ display: 'flex', gap: 13 }}><div style={{ width: 44, flexShrink: 0, fontSize: 12, color: 'var(--color-text-muted)' }}>{new Date(event.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</div><div style={{ paddingBottom: 15, flex: 1 }}><div style={{ fontSize: 14, fontWeight: 600 }}>{event.event_type.replaceAll('_', ' ')}</div><Prov kind="source" /></div></div>)}{!timeline.data?.length && <Alert tone="info" title="No timeline events">The backend returned an empty audit timeline.</Alert>}</Fragment>;
}

export function DecisionWorkspace({ state, tab, setTab }: { state: OpsState; tab: DecisionTab; setTab: (tab: DecisionTab) => void }) {
  const { selectedIncident } = useOperationsData();
  const incident = selectedIncident.data;
  return <GlassPanel padding={0} style={{ width: 400, flexShrink: 0, display: 'flex', flexDirection: 'column', minHeight: 0 }}><div style={{ padding: '15px 16px 12px', borderBottom: '1px solid var(--color-border-hairline)' }}><div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}><div><div style={{ fontSize: 18, fontWeight: 600 }}>{incident?.incident_type.replaceAll('_', ' ') ?? 'No incident selected'}</div><div style={{ fontSize: 13, color: 'var(--color-text-muted)', marginTop: 2 }}>{incident?.id ?? '—'} · v{incident?.version ?? '—'}</div></div>{incident && <Badge severity={incident.severity.toLowerCase() as 'low' | 'moderate' | 'high' | 'critical'} />}</div><div role="tablist" style={{ display: 'flex', gap: 3, padding: 3, borderRadius: 'var(--radius-md)', background: 'var(--gray-100)' }}>{DEC_TABS.map(([id, label]) => <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)} style={{ flex: 1, padding: '7px 4px', border: 'none', borderRadius: 'var(--radius-sm)', cursor: 'pointer', fontFamily: 'var(--font-en)', fontSize: 13, fontWeight: tab === id ? 600 : 500, background: tab === id ? 'var(--color-bg-surface)' : 'transparent', color: tab === id ? 'var(--color-text-primary)' : 'var(--color-text-muted)' }}>{label}</button>)}</div></div><div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12, overflowY: 'auto', minHeight: 0 }}><StateBanner state={state} />{tab === 'overview' && <OverviewTab />}{tab === 'plan' && <PlanTab state={state} />}{tab === 'hospital' && <HospitalTab />}{tab === 'evidence' && <EvidenceTab />}{tab === 'history' && <HistoryTab />}</div></GlassPanel>;
}
