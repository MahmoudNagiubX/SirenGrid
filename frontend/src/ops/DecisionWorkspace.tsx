import { Fragment, useState } from 'react';
import { Alert, Badge, Button, Card, ConfidenceMeter, GlassPanel, IconTile } from '../components';
import { Ico } from '../lib/icon';
import { AiBlock, ApprovalBar, Prov, SubHead } from './primitives';
import {
  DEC_TABS,
  type DecisionTab,
  type OpsState,
  type ProvKind,
} from '../data/mock';
import { useCommandRunner, useOperations } from '../state/OperationsContext';
import {
  approvePlan,
  generateCandidates,
  generateHospitalOptions,
  selectAlternativePlan,
  selectHospitalDestination,
  sendHospitalPreAlert,
} from '../commands/operationsCommands';
import { RecoveryNotice } from '../recovery/RecoveryNotice';
import type { HospitalOptionRead, ResponsePlanRead, TimelineEventRead } from '../api/types';

/** Prototype audit reference for versioned human-authority commands (SG-INT-06B §11). */
const OPERATOR_REF = 'demo-operator';

/** Incident statuses on which no further candidate generation / approval is meaningful. */
const NON_ACTIONABLE_INCIDENT_STATUSES = new Set([
  'CLOSED',
  'CANCELLED_FALSE_REPORT',
  'DUPLICATE_MERGED',
  'REQUIRES_REVIEW',
]);

/** Ported from ui_kits/operations_center/decision.jsx — bound to canonical backend read state. */

function formatSeconds(secs: number | null | undefined): string {
  if (secs === null || secs === undefined || isNaN(secs)) return '—';
  const m = Math.floor(secs / 60);
  const s = Math.round(secs % 60);
  return `${m}:${s < 10 ? '0' : ''}${s}`;
}

function humanize(str: string): string {
  return str
    .replace(/_/g, ' ')
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

function StateBanner({ state }: { state: OpsState }) {
  const { selectedIncident, replan } = useOperations();
  const inc = selectedIncident.data;
  const rep = replan.data;

  if (state === 'replan') {
    const title = rep?.trigger_reasons && rep.trigger_reasons.length > 0
      ? rep.trigger_reasons.map(humanize).join(', ')
      : 'Replan evaluation';
    const sub = rep?.pending_plan_id
      ? `Pending replacement plan ${rep.pending_plan_id}`
      : rep?.status ? `Status: ${humanize(rep.status)}` : 'No active replan trigger';

    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 11, padding: 12, borderRadius: 'var(--radius-md)', background: 'var(--color-critical-soft)', border: '1px solid var(--red-200)' }}>
        <IconTile icon={<Ico n="octagon-x" />} tint="red" size={32} />
        <div>
          <div style={{ fontSize: 14, fontWeight: 600 }}>{title}</div>
          <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>{sub}</div>
        </div>
      </div>
    );
  }

  if (state === 'active') {
    const title = inc?.current_plan_id ? `Plan ${inc.current_plan_id} active · executing` : 'Active response executing';
    const sub = inc?.status ? `Incident status: ${humanize(inc.status)}` : 'No active incident';
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 11, padding: 12, borderRadius: 'var(--radius-md)', background: 'var(--color-confirmed-soft)', border: '1px solid var(--blue-300)' }}>
        <IconTile icon={<Ico n="check" />} tint="navy" size={32} />
        <div>
          <div style={{ fontSize: 14, fontWeight: 600 }}>{title}</div>
          <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>{sub}</div>
        </div>
      </div>
    );
  }

  if (state === 'coverage') {
    return (
      <div style={{ display: 'flex', alignItems: 'center', gap: 11, padding: 12, borderRadius: 'var(--radius-md)', background: 'var(--gray-100)', border: '1px solid var(--color-border-hairline)' }}>
        <IconTile icon={<Ico n="shield-check" />} tint="navy" size={32} />
        <div>
          <div style={{ fontSize: 14, fontWeight: 600 }}>Coverage impact</div>
          <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>Coverage detail available in Phase 04 map integration</div>
        </div>
      </div>
    );
  }

  return null;
}

function Row({ a, b, tone }: { a: string; b: string; tone?: string }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', borderBottom: '1px solid var(--color-border-hairline)', fontSize: 14 }}>
      <span style={{ color: 'var(--color-text-muted)' }}>{a}</span>
      <span style={{ fontWeight: 600, color: tone ?? 'var(--color-text-primary)' }}>{b}</span>
    </div>
  );
}

function OverviewTab({ state, onSelectTab }: { state: OpsState; onSelectTab: (t: DecisionTab) => void }) {
  const { selectedIncident, timeline, resources, plans } = useOperations();
  const inc = selectedIncident.data;

  if (state === 'coverage') {
    return (
      <Fragment>
        <SubHead>Zone coverage · before → after</SubHead>
        <div style={{ padding: '12px 0', fontSize: 13.5, color: 'var(--color-text-muted)', lineHeight: 1.6 }}>
          Coverage detail available in Phase 04 map integration.
        </div>
        <AiBlock title="Balance recommendation" footer={<Button variant="primary" size="sm" disabled>Send for approval</Button>}>
          Balancing and reposition recommendations are calculated by backend planning models when coverage drops. Command wiring arrives in Phase 06.
        </AiBlock>
      </Fragment>
    );
  }

  if (state === 'active') {
    const executedEvents = (timeline.data ?? []).slice(-3);
    const incidentId = inc?.id;
    const currentPlan = inc?.current_plan_id
      ? (plans.data ?? []).find((p) => p.id === inc.current_plan_id)
      : undefined;
    const currentPlanResourceIds = new Set(currentPlan?.resource_ids ?? []);
    const assignedResources = (resources.data ?? []).filter(
      (r) =>
        (incidentId && r.assigned_incident_id === incidentId) ||
        (currentPlanResourceIds.size > 0 && currentPlanResourceIds.has(r.id)),
    );

    return (
      <Fragment>
        <SubHead>Executed</SubHead>
        {executedEvents.length === 0 ? (
          <div style={{ padding: '8px 0', fontSize: 13, color: 'var(--color-text-muted)' }}>No execution events recorded.</div>
        ) : (
          executedEvents.map((evt) => (
            <div key={evt.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 0', borderBottom: '1px solid var(--color-border-hairline)' }}>
              <span style={{ fontSize: 14 }}>{humanize(evt.event_type)}</span>
              <span style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: 13, color: 'var(--color-text-muted)' }}>
                {evt.created_at ? new Date(evt.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}
                <span style={{ width: 17, height: 17, display: 'flex', color: 'var(--color-confirmed)' }}>
                  <Ico n="circle-check" />
                </span>
              </span>
            </div>
          ))
        )}
        <SubHead>Units</SubHead>
        {assignedResources.length === 0 ? (
          <div style={{ padding: '8px 0', fontSize: 13, color: 'var(--color-text-muted)' }}>No units currently assigned.</div>
        ) : (
          assignedResources.map((u) => (
            <Row key={u.id} a={u.name || u.id} b={humanize(u.status)} />
          ))
        )}
      </Fragment>
    );
  }

  const sev = inc?.severity ? humanize(inc.severity) : '—';
  const sevTone = inc?.severity?.toLowerCase() === 'critical' ? 'var(--color-critical)' : 'var(--color-text-primary)';
  const confLevel = inc?.confidence_level?.toLowerCase() as 'low' | 'medium' | 'high' | undefined;

  return (
    <Fragment>
      <div style={{ display: 'flex', gap: 14, padding: '2px 0 8px' }}>
        <div style={{ flex: 1 }}>
          <SubHead>Severity</SubHead>
          <div style={{ fontSize: 18, fontWeight: 600, color: sevTone, marginTop: 5 }}>{sev}</div>
        </div>
        <span style={{ width: 1, background: 'var(--color-border-hairline)' }} />
        <div style={{ flex: 1.1 }}>
          <SubHead>AI confidence</SubHead>
          <div style={{ marginTop: 7 }}>
            <ConfidenceMeter level={confLevel ?? 'low'} label={confLevel ? humanize(confLevel) : 'Unknown'} />
          </div>
        </div>
      </div>
      <SubHead>Known</SubHead>
      <Row a="Type" b={inc?.incident_type ? humanize(inc.incident_type) : 'Unknown'} />
      <Row a="Trapped" b={inc?.trapped_person === true ? 'Yes' : inc?.trapped_person === false ? 'No' : 'Unknown'} tone={inc?.trapped_person === null ? 'var(--color-text-muted)' : undefined} />
      <Row a="Road" b={inc?.road_blockage === true ? 'Blocked' : inc?.road_blockage === false ? 'Clear' : 'Unknown'} tone={inc?.road_blockage === null ? 'var(--color-text-muted)' : undefined} />
      <Row a="Location" b={inc?.location_text || 'Location unresolved'} />
      <SubHead>Casualties</SubHead>
      <Row
        a="Casualty count"
        b={inc?.casualty_count !== null && inc?.casualty_count !== undefined ? `${inc.casualty_count}` : inc?.casualty_range || 'Unknown'}
        tone={inc?.casualty_count === null && !inc?.casualty_range ? 'var(--color-text-muted)' : undefined}
      />
      <AiBlock title="Incident interpretation">
        Structured incident facts are available from the backend. No narrative AI explanation is provided by this read contract.
      </AiBlock>
      <Button variant="ghost" size="sm" full onClick={() => onSelectTab('evidence')}>View full evidence</Button>
    </Fragment>
  );
}

function getCandidateSetId(p: ResponsePlanRead): string | null {
  return (
    p.candidate_set_id ??
    p.metrics?.candidate_set_id ??
    (p.metrics?.phase04 as Record<string, unknown> | undefined)?.candidate_set_id as string | undefined ??
    null
  );
}

function sortCandidatePlans(plans: ResponsePlanRead[]): ResponsePlanRead[] {
  return [...plans].sort((a, b) => {
    const rankA = a.candidate_rank ?? a.metrics?.candidate_rank ?? 999;
    const rankB = b.candidate_rank ?? b.metrics?.candidate_rank ?? 999;
    if (rankA !== rankB) {
      return rankA - rankB;
    }
    const verA = a.plan_version ?? a.version ?? 0;
    const verB = b.plan_version ?? b.version ?? 0;
    return verA - verB;
  });
}

function PlanTab({ state }: { state: OpsState }) {
  const { plans, replan, resources, selectedIncident, refreshSelectedIncident, refreshGlobal } =
    useOperations();
  const { busyAction, message, run } = useCommandRunner();
  const planList = plans.data ?? [];
  const rep = replan.data;
  const inc = selectedIncident.data;

  const [selId, setSelId] = useState<string | null>(null);

  const rejectNote = 'Reject command unavailable in current backend contract.';

  // §25 safety: while the canonical plan read is errored, current versions cannot
  // be trusted — every plan mutation control is disabled until a good refresh.
  const plansErrored = plans.error != null;

  const plansNotice =
    plans.error != null ? (
      <RecoveryNotice
        kind="UNAVAILABLE"
        title="Response plans unavailable"
        detail={
          planList.length > 0
            ? 'Showing last-known plans. Authority actions are paused until refresh succeeds.'
            : undefined
        }
        compact
        onRetry={inc ? () => void refreshSelectedIncident(inc.id) : undefined}
        retryLabel="Retry"
      />
    ) : plans.loading && plans.data == null ? (
      <RecoveryNotice kind="LOADING" title="Loading response plans" compact />
    ) : null;

  // §13 hardening: committed global resource truth must not depend on the
  // best-effort WebSocket. Each plan authority action explicitly reconciles
  // global reads then the selected incident, once each.
  const reconcileAfterPlanCommand = (incidentId: string) => async () => {
    await refreshGlobal({ includeSelected: false });
    await refreshSelectedIncident(incidentId);
  };

  if (state === 'replan') {
    const pendingPlanId = inc?.pending_replan_plan_id ?? rep?.pending_plan_id ?? null;
    const pendingPlan = pendingPlanId ? planList.find((p) => p.id === pendingPlanId) : undefined;
    const pendingSetId = pendingPlan ? getCandidateSetId(pendingPlan) : null;
    const replanCandidates = pendingSetId
      ? planList.filter((p) => getCandidateSetId(p) === pendingSetId)
      : pendingPlan
      ? [pendingPlan]
      : [];
    const replanPlans = sortCandidatePlans(replanCandidates);
    const activeReplanPlan = replanPlans.find((p) => p.id === selId) ?? replanPlans[0] ?? null;
    const selectedReplanPlanId = activeReplanPlan?.id ?? null;

    // Only the EXACT backend-pending recommended replacement can be approved,
    // and only while it is the visually selected card (§25). Replan alternatives
    // stay view-only — no selectAlternativePlan wiring in replan (§26).
    const pendingIsApproved = pendingPlan?.status === 'APPROVED';
    const canApproveReplacement =
      !!inc &&
      !!pendingPlan &&
      !plansErrored &&
      pendingPlan.status === 'RECOMMENDED' &&
      selectedReplanPlanId === pendingPlan.id &&
      busyAction === null;

    const doApproveReplacement = () => {
      if (!inc || !pendingPlan) return;
      void run('approve-replacement', {
        command: () =>
          approvePlan(pendingPlan.id, {
            expected_incident_version: inc.version,
            expected_plan_version: pendingPlan.plan_version,
            operator_reference: OPERATOR_REF,
          }),
        refetch: reconcileAfterPlanCommand(inc.id),
        successText: 'Replacement plan approved. Canonical state reloaded.',
      });
    };

    return (
      <Fragment>
        {plansNotice}
        {plansNotice == null && replanPlans.length === 0 ? (
          <div style={{ padding: 16, textAlign: 'center', color: 'var(--color-text-muted)', fontSize: 13 }}>
            No pending replan evaluation for this incident.
          </div>
        ) : replanPlans.length === 0 ? null : (
          <div style={{ display: 'flex', gap: 10 }}>
            {replanPlans.map((p, idx) => {
              const etaSec = p.metrics?.max_arrival_eta_seconds;
              const routeRef = p.routes?.[0]?.routing_source || p.metrics?.routing_source || 'Standard route';
              const isSelected = p.id === selectedReplanPlanId;
              const isPending = p.id === pendingPlan?.id;
              return (
                <div key={p.id} style={{ flex: 1, cursor: 'pointer' }} onClick={() => setSelId(p.id)}>
                  <Card
                    padding={13}
                    style={{
                      borderColor: isSelected ? 'var(--color-accent)' : 'var(--color-border-hairline)',
                    }}
                  >
                    <SubHead>{isPending ? 'Pending replacement' : `Candidate ${idx + 1}`}</SubHead>
                    <div style={{ fontSize: 24, fontWeight: 600, marginTop: 4, color: isSelected ? 'var(--color-accent)' : 'var(--color-text-muted)' }}>
                      {formatSeconds(etaSec)}
                    </div>
                    <div style={{ fontSize: 13, color: 'var(--color-text-muted)', marginTop: 2 }}>
                      via {routeRef}
                    </div>
                  </Card>
                </div>
              );
            })}
          </div>
        )}
        <AiBlock title="Replan evaluation">
          {rep?.explanation && typeof rep.explanation === 'object' && Object.keys(rep.explanation).length > 0
            ? JSON.stringify(rep.explanation)
            : rep?.trigger_reasons && rep.trigger_reasons.length > 0
            ? `Replan triggered by: ${rep.trigger_reasons.map(humanize).join(', ')}.`
            : 'Replan evaluation is backend-authoritative. Materiality is determined by the server engine.'}
        </AiBlock>
        <ApprovalBar
          approved={!!pendingIsApproved}
          note={
            pendingIsApproved
              ? 'Replacement plan is recorded as approved in canonical backend state.'
              : pendingPlan
              ? 'Approve the exact backend-pending recommended replacement.'
              : 'No pending recommended replacement plan to approve.'
          }
          approveLabel="Approve Replacement"
          onApprove={canApproveReplacement ? doApproveReplacement : undefined}
          disabled={!canApproveReplacement}
          busy={busyAction === 'approve-replacement'}
          rejectNote={rejectNote}
          statusText={message?.text ?? null}
          statusTone={message?.kind ?? 'neutral'}
        />
      </Fragment>
    );
  }

  let normalCandidates: ResponsePlanRead[] = [];
  if (inc?.current_plan_id) {
    const currentPlan = planList.find((p) => p.id === inc.current_plan_id);
    const currentSetId = currentPlan ? getCandidateSetId(currentPlan) : null;
    if (currentSetId) {
      normalCandidates = planList.filter((p) => getCandidateSetId(p) === currentSetId);
    } else if (currentPlan) {
      normalCandidates = [currentPlan];
    } else {
      normalCandidates = [];
    }
  } else {
    // If no current plan exists on the incident, look for the newest recommended plan candidate set
    const recommendedPlans = planList.filter((p) => p.status === 'RECOMMENDED');
    const recommendedPlan = recommendedPlans[recommendedPlans.length - 1];
    const recSetId = recommendedPlan ? getCandidateSetId(recommendedPlan) : null;
    if (recSetId) {
      normalCandidates = planList.filter((p) => getCandidateSetId(p) === recSetId);
    } else if (recommendedPlan) {
      normalCandidates = [recommendedPlan];
    } else {
      normalCandidates = [];
    }
  }

  const sortedPlans = sortCandidatePlans(normalCandidates);
  const activePlan = sortedPlans.find((p) => p.id === selId) ?? sortedPlans[0] ?? null;
  const selectedPlanId = activePlan?.id ?? null;

  const resourceMap = new Map((resources.data ?? []).map((r) => [r.id, r.name || r.id]));

  // --- Human-authority derivations (all from canonical reads) ---------------
  const currentPlanId = inc?.current_plan_id ?? null;
  const currentPlan = currentPlanId ? planList.find((p) => p.id === currentPlanId) : undefined;
  const showApproved =
    activePlan?.status === 'APPROVED' || currentPlan?.status === 'APPROVED';
  const hasApprovedPlan = planList.some((p) => p.status === 'APPROVED');

  // Approve is offered only for the incident's current RECOMMENDED plan (§21),
  // and never while the canonical plan read is errored (§25).
  const canApprove =
    !!inc &&
    !!activePlan &&
    !plansErrored &&
    activePlan.status === 'RECOMMENDED' &&
    activePlan.id === currentPlanId &&
    busyAction === null;

  // An ALTERNATIVE card must be explicitly selected before it can be approved (§20).
  const canSelectAlternative =
    !!inc && !!activePlan && !plansErrored && activePlan.status === 'ALTERNATIVE' && busyAction === null;

  // Revise / recalculate only pre-approval on an actionable incident (§24).
  const canRevise =
    !!inc &&
    !plansErrored &&
    !hasApprovedPlan &&
    !NON_ACTIONABLE_INCIDENT_STATUSES.has(inc.status) &&
    busyAction === null;

  const doApprove = () => {
    if (!inc || !activePlan) return;
    void run('approve', {
      command: () =>
        approvePlan(activePlan.id, {
          expected_incident_version: inc.version,
          expected_plan_version: activePlan.plan_version,
          operator_reference: OPERATOR_REF,
        }),
      refetch: reconcileAfterPlanCommand(inc.id),
      successText: 'Plan approved. Canonical state reloaded.',
    });
  };

  const doSelectAlternative = () => {
    if (!inc || !activePlan) return;
    void run('select', {
      command: () =>
        selectAlternativePlan(activePlan.id, {
          expected_incident_version: inc.version,
          expected_plan_version: activePlan.plan_version,
          operator_reference: OPERATOR_REF,
        }),
      refetch: reconcileAfterPlanCommand(inc.id),
      successText: 'Plan selected. Review the updated recommendation and approve explicitly.',
    });
  };

  const doRevise = () => {
    if (!inc) return;
    void run('revise', {
      command: () => generateCandidates(inc.id),
      refetch: reconcileAfterPlanCommand(inc.id),
      successText: 'Candidate plans recalculated.',
    });
  };

  const renderApprovalBar = () => {
    if (showApproved) {
      return (
        <ApprovalBar approved={true} note="Approval is recorded in canonical backend state." />
      );
    }
    if (canSelectAlternative) {
      return (
        <ApprovalBar
          approved={false}
          note="Selected candidate is an alternative. Select it, then approve explicitly."
          approveLabel="Select Plan"
          onApprove={doSelectAlternative}
          disabled={busyAction !== null}
          busy={busyAction === 'select'}
          rejectNote={rejectNote}
          onRevise={canRevise ? doRevise : undefined}
          reviseDisabled={!canRevise}
          statusText={message?.text ?? null}
          statusTone={message?.kind ?? 'neutral'}
        />
      );
    }
    return (
      <ApprovalBar
        approved={false}
        note={
          canApprove
            ? 'Approve the current recommended plan with its exact canonical versions.'
            : 'Approve is available only for the incident’s current recommended plan.'
        }
        onApprove={canApprove ? doApprove : undefined}
        disabled={!canApprove}
        busy={busyAction === 'approve'}
        rejectNote={rejectNote}
        onRevise={canRevise ? doRevise : undefined}
        reviseDisabled={!canRevise}
        statusText={message?.text ?? null}
        statusTone={message?.kind ?? 'neutral'}
      />
    );
  };

  if (sortedPlans.length === 0) {
    return (
      <Fragment>
        {plansNotice}
        {/* §26: "No candidate plans" only once loading is done and there is no error. */}
        {plansNotice == null && (
          <div style={{ padding: 24, textAlign: 'center', color: 'var(--color-text-muted)', fontSize: 13.5 }}>
            No candidate response plans generated yet.
          </div>
        )}
        {renderApprovalBar()}
      </Fragment>
    );
  }

  const displayCandidates = sortedPlans.slice(0, 3);

  const getCoverageStr = (p: ResponsePlanRead): string => {
    const cov = p.score_breakdown?.post_dispatch_joint_population_weighted_coverage
      ?? p.metrics?.phase04?.post_dispatch_joint?.population_weighted_coverage;
    if (typeof cov === 'number') {
      return `${Math.round(cov * 100)}%`;
    }
    return '—';
  };

  const getEtaStr = (p: ResponsePlanRead): string => {
    const eta = p.metrics?.max_arrival_eta_seconds ?? p.routes?.[0]?.eta_seconds;
    return formatSeconds(eta);
  };

  const getUnitsCountStr = (p: ResponsePlanRead): string => {
    return `${p.resource_ids.length} units`;
  };

  const compareRows: [string, (p: ResponsePlanRead) => string][] = [
    ['ETA', getEtaStr],
    ['Coverage', getCoverageStr],
    ['Units', getUnitsCountStr],
  ];

  const candidateLabels = ['A', 'B', 'C'];

  return (
    <Fragment>
      {plansNotice}
      <div style={{ borderRadius: 'var(--radius-md)', border: '1px solid var(--color-border-hairline)', overflow: 'hidden' }}>
        <div style={{ display: 'grid', gridTemplateColumns: `78px repeat(${displayCandidates.length}, 1fr)`, background: 'var(--gray-100)', fontSize: 12, fontWeight: 700, letterSpacing: '0.06em', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>
          <div style={{ padding: '9px 10px', textAlign: 'left' }}></div>
          {displayCandidates.map((_, i) => (
            <div key={i} style={{ padding: '9px 10px', textAlign: 'center' }}>{candidateLabels[i]}</div>
          ))}
        </div>
        {compareRows.map(([label, getValue]) => (
          <div key={label} style={{ display: 'grid', gridTemplateColumns: `78px repeat(${displayCandidates.length}, 1fr)`, borderTop: '1px solid var(--color-border-hairline)', alignItems: 'center' }}>
            <div style={{ padding: '10px', fontSize: 13, color: 'var(--color-text-muted)' }}>{label}</div>
            {displayCandidates.map((p, i) => {
              const val = getValue(p);
              const isSelected = p.id === selectedPlanId;
              return (
                <div
                  key={i}
                  style={{
                    padding: '10px',
                    textAlign: 'center',
                    fontSize: 16,
                    fontWeight: 600,
                    color: isSelected ? 'var(--color-accent)' : 'var(--color-text-primary)',
                    background: isSelected ? 'var(--color-accent-soft)' : 'transparent',
                  }}
                >
                  {val}
                </div>
              );
            })}
          </div>
        ))}
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {sortedPlans.map((p, idx) => {
          const isSelected = p.id === selectedPlanId;
          const isRecommended = p.status === 'RECOMMENDED';
          const unitsLabel = p.resource_ids.map((id) => resourceMap.get(id) || id).join(', ') || 'No units specified';
          return (
            <button
              key={p.id}
              onClick={() => setSelId(p.id)}
              style={{
                textAlign: 'left',
                cursor: 'pointer',
                fontFamily: 'var(--font-en)',
                borderRadius: 'var(--radius-md)',
                padding: 12,
                border: isSelected ? '1.5px solid var(--color-accent)' : '1px solid var(--color-border-hairline)',
                background: isSelected ? 'var(--color-accent-soft)' : 'var(--color-bg-surface)',
              }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 14, fontWeight: 600 }}>
                  {`Plan ${candidateLabels[idx] ?? idx + 1}`} · {p.id}
                </span>
                {isRecommended && <Badge tone="info">Recommended</Badge>}
              </div>
              <div style={{ fontSize: 13, color: 'var(--color-text-muted)', marginTop: 3 }}>
                {unitsLabel}
              </div>
            </button>
          );
        })}
      </div>
      {activePlan && (
        <AiBlock title={`Plan evaluation · ${activePlan.id}`}>
          Backend candidate evaluation under policy {activePlan.score_breakdown?.policy_version || 'standard'}. Max ETA: {formatSeconds(activePlan.metrics?.max_arrival_eta_seconds)}. Post-dispatch joint coverage: {getCoverageStr(activePlan)}. Reserve exhausted: {activePlan.score_breakdown?.remaining_reserve_exhausted ? 'Yes' : 'No'}.
        </AiBlock>
      )}
      {renderApprovalBar()}
    </Fragment>
  );
}

function HospitalTab() {
  const { operationalState, selectedIncident, refreshSelectedIncident } = useOperations();
  const { busyAction, message, run } = useCommandRunner();
  const inc = selectedIncident.data;
  const opState = operationalState.data;
  const hospitalOptions = opState?.hospital_options ?? null;
  const options = hospitalOptions?.options ?? [];
  const destination = opState?.selected_destination ?? null;
  const preAlert = opState?.hospital_pre_alert ?? null;

  const [selectedOptionId, setSelectedOptionId] = useState<string | null>(null);

  // §27/§28: an errored operational-state read is NOT "no hospital options".
  // A 409 here specifically means this incident has no approved operational
  // state yet — a local neutral notice, never a global outage. Any error
  // disables hospital commands that need versions from that missing state.
  const opStateError = operationalState.error;
  const opStateNoApprovedPlan = opStateError?.status === 409;
  const opStateUnavailable = opStateError != null && !opStateNoApprovedPlan;
  const opStateBlocksCommands = opStateError != null;

  const opStateNotice = opStateNoApprovedPlan ? (
    <RecoveryNotice
      kind="UNAVAILABLE"
      title="Operational state not available for this incident yet"
      detail="Hospital and corridor state appear once a response plan is approved."
      compact
    />
  ) : opStateUnavailable ? (
    <RecoveryNotice
      kind="UNAVAILABLE"
      title="Operational state unavailable"
      detail={
        opState
          ? 'Showing last-known operational state. Hospital actions are paused until refresh succeeds.'
          : undefined
      }
      compact
      onRetry={inc ? () => void refreshSelectedIncident(inc.id) : undefined}
    />
  ) : null;

  // Once a destination is committed, visual selection follows canonical state (§30).
  const committedOptionId = destination
    ? options.find((o) => o.hospital.id === destination.hospital_id)?.option_id ?? null
    : null;
  const effectiveOptionId = committedOptionId ?? selectedOptionId;
  const selectedOption = options.find((o) => o.option_id === effectiveOptionId) ?? null;

  const doGenerateOptions = () => {
    if (!inc) return;
    void run('gen-options', {
      command: () => generateHospitalOptions(inc.id),
      refetch: () => refreshSelectedIncident(inc.id),
      successText: 'Hospital options generated. Canonical operational state reloaded.',
    });
  };

  const doSelectDestination = () => {
    if (!inc || !hospitalOptions || !selectedOption) return;
    void run('select-dest', {
      command: () =>
        selectHospitalDestination(inc.id, {
          expected_incident_version: hospitalOptions.incident_version,
          expected_plan_version: hospitalOptions.plan_version,
          expected_option_set_version: hospitalOptions.option_set_version,
          hospital_id: selectedOption.hospital.id,
          operator_reference: OPERATOR_REF,
        }),
      refetch: () => refreshSelectedIncident(inc.id),
      successText: 'Destination committed. Showing canonical selected destination.',
    });
  };

  const doPreAlert = () => {
    if (!inc || !destination) return;
    void run('prealert', {
      command: () =>
        sendHospitalPreAlert(inc.id, {
          expected_incident_version: inc.version,
          expected_plan_version: destination.plan_version,
          operator_reference: OPERATOR_REF,
          simulate_failure: false,
        }),
      refetch: () => refreshSelectedIncident(inc.id),
      successText: 'Pre-alert sent. Showing canonical pre-alert status.',
    });
  };

  const commandNotice = message ? (
    <Alert tone={message.kind === 'success' ? 'info' : 'attention'} title={message.kind === 'conflict' ? 'State changed' : message.kind === 'error' ? 'Command failed' : 'Done'}>
      {message.text}
    </Alert>
  ) : null;

  if (options.length === 0) {
    return (
      <Fragment>
        <AiBlock title="Destination rationale">
          Hospital options are ranked by the backend operational model.
        </AiBlock>
        {opStateNotice}
        <SubHead>Candidates</SubHead>
        {opStateBlocksCommands ? null : (
          <div style={{ padding: 24, textAlign: 'center', color: 'var(--color-text-muted)', fontSize: 13.5 }}>
            No hospital options evaluated for this incident.
          </div>
        )}
        {inc && !opStateBlocksCommands && (
          <Button
            variant="secondary"
            size="sm"
            disabled={busyAction !== null}
            onClick={doGenerateOptions}
          >
            {busyAction === 'gen-options' ? 'Working…' : 'Generate options'}
          </Button>
        )}
        {commandNotice}
      </Fragment>
    );
  }

  return (
    <Fragment>
      <AiBlock title="Destination rationale">
        Hospital options are ranked by the backend operational model.
      </AiBlock>
      {opStateNotice}
      <SubHead>{`Candidates · ${options.length} evaluated`}</SubHead>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 9 }}>
        {options.map((opt: HospitalOptionRead) => {
          const h = opt.hospital;
          const isSelected = opt.option_id === effectiveOptionId;
          const isRec = opt.rank === 1;
          const isStale = h.operational_freshness_status === 'STALE';
          const loadPct = h.simulated_load_ratio !== null ? Math.round(h.simulated_load_ratio * 100) : null;
          const etaSec = typeof opt.route?.eta_seconds === 'number' ? opt.route.eta_seconds : null;

          return (
            <button
              key={opt.option_id}
              onClick={() => {
                // Local visual focus only — never commits. Once a destination is
                // committed the selection follows canonical state.
                if (!destination) setSelectedOptionId(opt.option_id);
              }}
              style={{
                textAlign: 'left',
                cursor: destination ? 'default' : 'pointer',
                fontFamily: 'var(--font-en)',
                display: 'flex',
                gap: 12,
                alignItems: 'center',
                padding: 13,
                borderRadius: 'var(--radius-md)',
                border: isSelected ? '1.5px solid var(--color-accent)' : '1px solid var(--color-border-hairline)',
                background: isSelected ? 'var(--color-accent-soft)' : 'var(--color-bg-surface)',
              }}
            >
              <IconTile icon={<Ico n="hospital" />} tint={loadPct !== null && loadPct > 85 ? 'red' : 'navy'} size={38} />
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 7, flexWrap: 'wrap' }}>
                  <span style={{ fontSize: 14.5, fontWeight: 600 }}>{h.name || h.id}</span>
                  {isRec && <Badge tone="info">Recommended</Badge>}
                  {isStale && <Badge tone="neutral">Stale</Badge>}
                </div>
                <div style={{ display: 'flex', gap: 8, alignItems: 'center', fontSize: 13, color: 'var(--color-text-muted)', marginTop: 2 }}>
                  <span>{h.static_capabilities.join(', ') || 'General'}</span>
                  <span>· {humanize(h.accepting_state)}</span>
                </div>
                {loadPct !== null && (
                  <Fragment>
                    <div style={{ height: 7, borderRadius: 4, background: 'var(--gray-200)', marginTop: 8 }}>
                      <div style={{ width: loadPct + '%', height: '100%', borderRadius: 4, background: loadPct > 85 ? 'var(--color-critical)' : 'var(--color-accent)' }} />
                    </div>
                    <div style={{ fontSize: 13, color: loadPct > 85 ? 'var(--color-critical)' : 'var(--color-text-muted)', marginTop: 4 }}>
                      {loadPct}% modelled load
                    </div>
                  </Fragment>
                )}
              </div>
              <div style={{ textAlign: 'right' }}>
                <div style={{ fontSize: 18, fontWeight: 600 }}>{formatSeconds(etaSec)}</div>
                <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)' }}>ETA</div>
              </div>
            </button>
          );
        })}
      </div>

      {destination ? (
        <div style={{ borderRadius: 'var(--radius-md)', border: '1px solid var(--blue-300)', background: 'var(--color-confirmed-soft)', padding: 12 }}>
          <div style={{ fontSize: 13.5, fontWeight: 600 }}>
            Committed destination · {selectedOption?.hospital.name || destination.hospital_id}
          </div>
          <div style={{ fontSize: 13, color: 'var(--color-text-muted)', marginTop: 2 }}>
            Backend status: {humanize(destination.status)}
            {preAlert ? ` · Pre-alert: ${humanize(preAlert.status)}` : ''}
          </div>
          <div style={{ marginTop: 10 }}>
            <Button
              variant="secondary"
              size="sm"
              disabled={busyAction !== null || opStateBlocksCommands}
              onClick={doPreAlert}
            >
              {busyAction === 'prealert' ? 'Working…' : preAlert ? 'Re-send pre-alert' : 'Send pre-alert'}
            </Button>
          </div>
        </div>
      ) : (
        <Button
          variant="primary"
          size="sm"
          disabled={!selectedOption || busyAction !== null || opStateBlocksCommands}
          onClick={doSelectDestination}
        >
          {busyAction === 'select-dest' ? 'Working…' : 'Select destination'}
        </Button>
      )}
      {commandNotice}
    </Fragment>
  );
}

function deriveReportProv(r: { data_reality: string; source_type: string }): ProvKind {
  if (r.source_type.includes('operator')) return 'operator';
  if (r.source_type.includes('responder')) return 'responder';
  if (r.data_reality === 'SIMULATED' || r.data_reality === 'SYNTHETIC') return 'sim';
  return 'source';
}

function EvidenceTab() {
  const { reports, selectedIncident } = useOperations();
  const reportList = reports.data ?? [];
  const requiresReview = selectedIncident.data?.status === 'REQUIRES_REVIEW';

  return (
    <Fragment>
      <SubHead>{`Evidence · ${reportList.length}`}</SubHead>
      {reportList.length === 0 ? (
        <div style={{ padding: 16, color: 'var(--color-text-muted)', fontSize: 13 }}>
          No evidence reports associated with this incident.
        </div>
      ) : (
        reportList.map((r) => (
          <Card key={r.id} padding={12} style={{ display: 'flex', gap: 11, alignItems: 'flex-start' }}>
            <IconTile icon={<Ico n="file-text" />} tint="slate" size={32} />
            <div style={{ flex: 1, minWidth: 0 }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
                <span style={{ fontSize: 14, fontWeight: 600 }}>{r.source_reference || r.source_type}</span>
                <Prov kind={deriveReportProv(r)} />
              </div>
              <div style={{ fontSize: 13, color: 'var(--color-text-secondary)', marginTop: 4, lineHeight: 1.5 }}>
                {r.raw_text}
              </div>
              <div style={{ fontSize: 12, color: 'var(--color-text-muted)', marginTop: 4 }}>
                Received {r.received_at ? new Date(r.received_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'} · {r.data_reality}
              </div>
            </div>
          </Card>
        ))
      )}
      {requiresReview && (
        <Alert tone="attention" title="Operator review required">
          Incident status indicates operator review is required before proceeding.
        </Alert>
      )}
    </Fragment>
  );
}

function deriveTimelineProv(evt: TimelineEventRead): ProvKind {
  const d = evt.details as Record<string, unknown> | undefined;
  if (d?.source === 'operator' || d?.operator_reference) return 'operator';
  if (d?.source === 'responder') return 'responder';
  if (d?.data_reality === 'SIMULATED' || d?.data_reality === 'SYNTHETIC') return 'sim';
  return 'source';
}

function HistoryTab() {
  const { timeline } = useOperations();
  const events = timeline.data ?? [];

  return (
    <Fragment>
      {events.length === 0 ? (
        <div style={{ padding: 16, color: 'var(--color-text-muted)', fontSize: 13 }}>
          No history events recorded for this incident.
        </div>
      ) : (
        events.map((evt, i) => (
          <div key={evt.id || i} style={{ display: 'flex', gap: 13 }}>
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', width: 44, flexShrink: 0 }}>
              <span style={{ fontSize: 13, color: 'var(--color-text-muted)', fontWeight: 600 }}>
                {evt.created_at ? new Date(evt.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}
              </span>
              <span style={{ width: 1, flex: 1, background: 'var(--color-border-hairline)', marginTop: 4 }} />
            </div>
            <div style={{ paddingBottom: 15, flex: 1 }}>
              <div style={{ fontSize: 14, fontWeight: 600 }}>{humanize(evt.event_type)}</div>
              <div style={{ marginTop: 5 }}>
                <Prov kind={deriveTimelineProv(evt)} />
              </div>
            </div>
          </div>
        ))
      )}
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
  const { selectedIncident, selectedIncidentId, refreshSelectedIncident } = useOperations();
  const inc = selectedIncident.data;

  // §23/§24: a failed selected-incident read is visible and retriable; a read
  // that is merely still loading shows "Loading incident", never "Unknown".
  const selectedIncidentNotice =
    selectedIncident.error != null ? (
      <RecoveryNotice
        kind="UNAVAILABLE"
        title="Selected incident unavailable"
        detail={inc ? 'Showing last-known incident facts.' : undefined}
        compact
        onRetry={
          selectedIncidentId
            ? () => void refreshSelectedIncident(selectedIncidentId)
            : undefined
        }
      />
    ) : selectedIncident.loading && selectedIncident.data == null && selectedIncidentId ? (
      <RecoveryNotice kind="LOADING" title="Loading incident" compact />
    ) : null;

  const headerTitle = inc ? humanize(inc.incident_type) : 'No incident selected';
  const headerSub = inc
    ? `${inc.id} · ${inc.created_at ? new Date(inc.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—'}`
    : '—';
  const headerSevTone = inc ? (inc.severity.toLowerCase() as 'low' | 'moderate' | 'high' | 'critical') : 'low';

  return (
    <GlassPanel padding={0} style={{ width: 400, flexShrink: 0, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
      <div style={{ padding: '15px 16px 12px', borderBottom: '1px solid var(--color-border-hairline)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 12 }}>
          <div>
            <div style={{ fontSize: 18, fontWeight: 600, letterSpacing: '-0.015em' }}>{headerTitle}</div>
            <div style={{ fontSize: 13, color: 'var(--color-text-muted)', marginTop: 2 }}>{headerSub}</div>
          </div>
          {inc && <Badge severity={headerSevTone} />}
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
        {selectedIncidentNotice}
        <StateBanner state={state} />
        {tab === 'overview' && <OverviewTab state={state} onSelectTab={setTab} />}
        {tab === 'plan' && <PlanTab state={state} />}
        {tab === 'hospital' && <HospitalTab />}
        {tab === 'evidence' && <EvidenceTab />}
        {tab === 'history' && <HistoryTab />}
      </div>
    </GlassPanel>
  );
}
