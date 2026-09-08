/**
 * Ported from components/data/ConfidenceMeter.jsx.
 * The blue meter is the AI-confidence visual language — kept entirely separate from the
 * red severity Badge system (Master Plan §20).
 */
export type ConfidenceLevel = 'low' | 'medium' | 'high';

const LEVELS: Record<ConfidenceLevel, number> = { low: 0.25, medium: 0.6, high: 1 };

export interface ConfidenceMeterProps {
  level?: ConfidenceLevel;
  label?: string;
}

export function ConfidenceMeter({ level = 'medium', label }: ConfidenceMeterProps) {
  const pct = LEVELS[level] ?? 0.6;
  const color = level === 'high' ? 'var(--conf-high)' : level === 'low' ? 'var(--conf-low)' : 'var(--conf-medium)';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10, fontFamily: 'var(--font-en)' }}>
      <div style={{ width: 64, height: 6, borderRadius: 'var(--radius-pill)', background: 'var(--gray-200)', overflow: 'hidden' }}>
        <div style={{ width: `${pct * 100}%`, height: '100%', background: color, borderRadius: 'var(--radius-pill)' }} />
      </div>
      <span style={{ fontSize: 'var(--fs-caption)', color: 'var(--color-text-secondary)', textTransform: 'capitalize' }}>
        {label ?? `${level} confidence`}
      </span>
    </div>
  );
}
