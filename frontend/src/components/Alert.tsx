import type { ReactNode } from 'react';

/**
 * Ported from components/feedback/Alert.jsx.
 * `tone="simulated"` exists specifically to satisfy the rule that simulated integrations / data
 * must be labelled, never presented as live.
 */
export type AlertTone = 'info' | 'attention' | 'simulated';

const ICON: Record<AlertTone, string> = { info: 'ⓘ', attention: '!', simulated: '◆' };

const TONE: Record<AlertTone, { bg: string; fg: string; ic: string }> = {
  info: { bg: 'var(--color-accent-soft)', fg: 'var(--blue-700)', ic: 'var(--color-accent)' },
  attention: { bg: 'var(--color-attention-soft)', fg: 'var(--red-700)', ic: 'var(--color-attention)' },
  simulated: { bg: 'var(--gray-100)', fg: 'var(--gray-700)', ic: 'var(--gray-700)' },
};

export interface AlertProps {
  tone?: AlertTone;
  title?: string;
  children?: ReactNode;
}

export function Alert({ tone = 'info', title, children }: AlertProps) {
  const t = TONE[tone] ?? TONE.info;
  return (
    <div role="status" style={{ display: 'flex', gap: 10, alignItems: 'flex-start', padding: '10px 14px', borderRadius: 'var(--radius-md)', background: t.bg, fontFamily: 'var(--font-en)' }}>
      <span aria-hidden style={{ color: t.ic, fontWeight: 700, fontSize: 13, lineHeight: '18px' }}>{ICON[tone] ?? 'ⓘ'}</span>
      <div>
        {title && <div style={{ fontSize: 'var(--fs-caption)', fontWeight: 600, color: t.fg }}>{title}</div>}
        {children && <div style={{ fontSize: 'var(--fs-caption)', color: 'var(--color-text-secondary)' }}>{children}</div>}
      </div>
    </div>
  );
}
