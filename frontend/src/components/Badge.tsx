import type { ReactNode } from 'react';

/**
 * Ported from components/feedback/Badge.jsx.
 * Severity (red family) and tone are deliberately separate visual systems — Master Plan §20:
 * severity and AI confidence must never be visually conflated.
 */
export type Severity = 'low' | 'moderate' | 'high' | 'critical';
export type Tone = 'neutral' | 'info' | 'confirmed' | 'simulated';

const SEV: Record<Severity, { bg: string; fg: string; label: string }> = {
  low: { bg: 'var(--blue-50)', fg: 'var(--blue-600)', label: 'Low' },
  moderate: { bg: 'var(--blue-100)', fg: 'var(--blue-700)', label: 'Moderate' },
  high: { bg: 'var(--red-50)', fg: 'var(--red-700)', label: 'High' },
  critical: { bg: 'var(--red-600)', fg: '#fff', label: 'Critical' },
};

const TONE: Record<Tone, { bg: string; fg: string }> = {
  neutral: { bg: 'var(--gray-100)', fg: 'var(--gray-800)' },
  info: { bg: 'var(--color-accent-soft)', fg: 'var(--color-accent)' },
  confirmed: { bg: 'var(--color-confirmed-soft)', fg: 'var(--color-confirmed)' },
  simulated: { bg: 'var(--gray-100)', fg: 'var(--gray-800)' },
};

export interface BadgeProps {
  severity?: Severity;
  tone?: Tone;
  children?: ReactNode;
}

export function Badge({ severity, tone = 'neutral', children }: BadgeProps) {
  const s = severity ? SEV[severity] : null;
  const t = TONE[tone] ?? TONE.neutral;
  const bg = s ? s.bg : t.bg;
  const fg = s ? s.fg : t.fg;
  const label = children ?? (s ? s.label : '');
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '3px 10px',
        borderRadius: 'var(--radius-pill)',
        background: bg,
        color: fg,
        fontFamily: 'var(--font-en)',
        fontSize: 'var(--fs-micro)',
        fontWeight: 600,
        letterSpacing: 'var(--ls-wide)',
        textTransform: 'uppercase',
      }}
    >
      {label}
    </span>
  );
}
