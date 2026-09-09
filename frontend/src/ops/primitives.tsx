import type { CSSProperties, ReactNode } from 'react';
import { Badge, Button, GlassPanel, IconTile } from '../components';
import { Ico } from '../lib/icon';
import type { ProvKind } from '../data/mock';

/**
 * Shared Operations-shell primitives — ported from ui_kits/operations_center/shell.jsx.
 * (The prototype's `Rail` / `TopBar` are intentionally not ported: the canonical workspace
 * uses `StatusStrip` from workspace.jsx instead.)
 */

export function PanelHeader({
  icon,
  title,
  right,
  tint = 'glass',
}: {
  icon?: string;
  title: string;
  right?: ReactNode;
  tint?: 'blue' | 'navy' | 'red' | 'slate' | 'glass';
}) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 9 }}>
        {icon && <IconTile icon={<Ico n={icon} />} tint={tint} size={28} />}
        <span style={{ fontSize: 14, fontWeight: 600 }}>{title}</span>
      </div>
      {right}
    </div>
  );
}

export function Kpi({
  icon,
  label,
  value,
  sub,
  tint = 'blue',
}: {
  icon: string;
  label: string;
  value: ReactNode;
  sub?: string;
  tint?: 'blue' | 'navy' | 'red' | 'slate' | 'glass';
}) {
  return (
    <GlassPanel padding={14} style={{ flex: 1, minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 10 }}>
        <IconTile icon={<Ico n={icon} />} tint={tint} size={30} />
        <span style={{ fontSize: 12.5, color: 'var(--color-text-secondary)', fontWeight: 500 }}>{label}</span>
      </div>
      <div style={{ fontSize: 26, fontWeight: 600, letterSpacing: '-0.01em' }}>{value}</div>
      {sub && <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)', marginTop: 2 }}>{sub}</div>}
    </GlassPanel>
  );
}

const PROV_MAP: Record<ProvKind, [string, 'info' | 'confirmed' | 'neutral' | 'simulated']> = {
  ai: ['AI-extracted', 'info'],
  operator: ['Operator-corrected', 'confirmed'],
  responder: ['Responder-confirmed', 'confirmed'],
  source: ['Source-reported', 'neutral'],
  sim: ['Simulated', 'simulated'],
  stale: ['Stale', 'neutral'],
};

export function Prov({ kind }: { kind: ProvKind }) {
  const [label, tone] = PROV_MAP[kind] ?? PROV_MAP.source;
  return <Badge tone={tone}>{label}</Badge>;
}

export function Fact({
  label,
  value,
  prov,
  unknown,
}: {
  label: string;
  value?: ReactNode;
  prov?: ProvKind;
  unknown?: boolean;
}) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 10, padding: '8px 0', borderBottom: '1px solid var(--color-border-hairline)' }}>
      <span style={{ fontSize: 13.5, color: 'var(--color-text-muted)' }}>{label}</span>
      <span style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <span style={{ fontSize: 14, fontWeight: 500, color: unknown ? 'var(--color-text-muted)' : 'var(--color-text-primary)' }}>{unknown ? 'Unknown' : value}</span>
        {prov && <Prov kind={prov} />}
      </span>
    </div>
  );
}

export function AiBlock({ title, children, footer }: { title: string; children: ReactNode; footer?: ReactNode }) {
  return (
    <div style={{ borderRadius: 'var(--radius-md)', border: '1px dashed var(--blue-300)', background: 'var(--blue-50)', padding: 14 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8, flexWrap: 'wrap' }}>
        <IconTile icon={<Ico n="brain" />} tint="blue" size={26} />
        <span style={{ fontSize: 13.5, fontWeight: 600, color: 'var(--blue-700)' }}>{title}</span>
        <Badge tone="info">Recommendation · not executed</Badge>
      </div>
      <div style={{ fontSize: 13.5, color: 'var(--gray-700)', lineHeight: 1.55 }}>{children}</div>
      {footer && <div style={{ marginTop: 10 }}>{footer}</div>}
    </div>
  );
}

const APPROVAL_STATUS_COLOR: Record<string, string> = {
  success: 'var(--color-confirmed)',
  conflict: 'var(--color-attention)',
  error: 'var(--color-critical)',
  neutral: 'var(--color-text-muted)',
};

export function ApprovalBar({
  note,
  onApprove,
  approved,
  disabled,
  busy,
  approveLabel,
  onReject,
  rejectDisabled,
  rejectNote,
  onRevise,
  reviseDisabled,
  statusText,
  statusTone = 'neutral',
}: {
  note: string;
  onApprove?: () => void;
  approved?: boolean;
  disabled?: boolean;
  busy?: boolean;
  approveLabel?: string;
  onReject?: () => void;
  rejectDisabled?: boolean;
  rejectNote?: string;
  onRevise?: () => void;
  reviseDisabled?: boolean;
  statusText?: string | null;
  statusTone?: 'success' | 'conflict' | 'error' | 'neutral';
}) {
  // Reject / Revise default to disabled so existing callers are unaffected.
  const rejectOff = rejectDisabled !== false;
  const reviseOff = reviseDisabled !== false;
  return (
    <div
      style={{
        borderRadius: 'var(--radius-md)',
        background: approved ? 'var(--color-confirmed-soft)' : 'var(--color-bg-surface)',
        border: `1px solid ${approved ? 'var(--blue-300)' : 'var(--color-border-strong)'}`,
        padding: 14,
        display: 'flex',
        flexDirection: 'column',
        gap: 12,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <IconTile icon={<Ico n={approved ? 'check' : 'user-round-check'} />} tint="navy" size={32} />
        <div style={{ minWidth: 0 }}>
          <div style={{ fontSize: 14, fontWeight: 600 }}>{approved ? 'Approved by operator' : 'Human approval required'}</div>
          <div style={{ fontSize: 13, color: 'var(--color-text-muted)' }}>{note}</div>
        </div>
      </div>
      {!approved && (
        <div style={{ display: 'flex', gap: 8 }}>
          <div style={{ flex: 1 }}>
            <Button variant="primary" size="md" onClick={onApprove} disabled={disabled || busy} full>
              {busy ? 'Working…' : approveLabel ?? 'Approve'}
            </Button>
          </div>
          <Button variant="critical" size="md" onClick={rejectOff ? undefined : onReject} disabled={rejectOff || busy}>Reject</Button>
          <Button variant="ghost" size="md" onClick={reviseOff ? undefined : onRevise} disabled={reviseOff || busy}>Revise</Button>
        </div>
      )}
      {!approved && rejectNote && (
        <div style={{ fontSize: 12.5, color: 'var(--color-text-muted)' }}>{rejectNote}</div>
      )}
      {statusText && (
        <div style={{ fontSize: 13, fontWeight: 500, color: APPROVAL_STATUS_COLOR[statusTone] ?? APPROVAL_STATUS_COLOR.neutral }}>
          {statusText}
        </div>
      )}
    </div>
  );
}

export function Drawer({ title, children, onClose }: { title: string; children: ReactNode; onClose: () => void }) {
  return (
    <GlassPanel padding={0} style={{ width: 320, flexShrink: 0, alignSelf: 'stretch' }}>
      <div style={{ padding: '14px 16px', borderBottom: '1px solid var(--color-border-hairline)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: 13, fontWeight: 600 }}>{title}</span>
        <button onClick={onClose} aria-label="Close" style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: 'var(--color-text-muted)', width: 16, height: 16, padding: 0 }}>
          <Ico n="x" />
        </button>
      </div>
      <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12 }}>{children}</div>
    </GlassPanel>
  );
}

export function Screen({ children, style = {} }: { children: ReactNode; style?: CSSProperties }) {
  return (
    <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: 14, padding: 18, overflow: 'hidden', ...style }}>
      {children}
    </div>
  );
}

export function SubHead({ children }: { children: ReactNode }) {
  return (
    <div style={{ fontSize: 12, fontWeight: 700, letterSpacing: '0.07em', color: 'var(--color-text-muted)', textTransform: 'uppercase' }}>
      {children}
    </div>
  );
}
