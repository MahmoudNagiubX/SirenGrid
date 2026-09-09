import type { ReactNode } from 'react';

/** Ported from components/data/StatTile.jsx — dashboard header metric. */
export interface StatTileProps {
  label: string;
  value: ReactNode;
  delta?: string;
  deltaTone?: 'up' | 'down';
  icon?: ReactNode;
}

export function StatTile({ label, value, delta, deltaTone = 'up', icon }: StatTileProps) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, fontFamily: 'var(--font-en)' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--color-text-secondary)', fontSize: 'var(--fs-caption)' }}>
        {icon}
        <span>{label}</span>
      </div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 8 }}>
        <span style={{ fontSize: 'var(--fs-h1)', fontWeight: 600, color: 'var(--color-text-primary)' }}>{value}</span>
        {delta && (
          <span style={{ fontSize: 'var(--fs-micro)', fontWeight: 500, color: deltaTone === 'up' ? 'var(--color-confirmed)' : 'var(--color-critical)' }}>{delta}</span>
        )}
      </div>
    </div>
  );
}
