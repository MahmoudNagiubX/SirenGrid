import type { ReactNode } from 'react';

/** Ported from components/core/IconTile.jsx — the duotone glass icon tile (one coherent iOS-style family). */
type Tint = 'blue' | 'navy' | 'red' | 'slate' | 'glass';

const TINTS: Record<Tint, { top: string; mid: string; deep: string; glow: string }> = {
  blue: { top: '#7FB0EC', mid: '#3F86DE', deep: '#1E5CAF', glow: 'rgba(47,125,225,.45)' },
  navy: { top: '#5B84BE', mid: '#2E5389', deep: '#16294A', glow: 'rgba(22,41,74,.45)' },
  red: { top: '#F4707F', mid: '#DE2038', deep: '#8C0B22', glow: 'rgba(165,8,31,.45)' },
  slate: { top: '#AFBBCD', mid: '#7C8CA3', deep: '#4C5A6E', glow: 'rgba(76,90,110,.36)' },
  glass: { top: 'rgba(255,255,255,.95)', mid: 'rgba(255,255,255,.6)', deep: 'rgba(214,226,242,.55)', glow: 'rgba(120,150,190,.28)' },
};

export interface IconTileProps {
  icon: ReactNode;
  tint?: Tint;
  size?: number;
  shape?: 'rounded' | 'circle';
}

export function IconTile({ icon, tint = 'blue', size = 34, shape = 'rounded' }: IconTileProps) {
  const t = TINTS[tint] ?? TINTS.blue;
  const radius = shape === 'circle' ? '50%' : Math.round(size * 0.32);
  const isGlass = tint === 'glass';
  return (
    <div
      style={{
        width: size,
        height: size,
        borderRadius: radius,
        flexShrink: 0,
        position: 'relative',
        overflow: 'hidden',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: `linear-gradient(180deg, ${t.top} 0%, ${t.mid} 46%, ${t.deep} 100%)`,
        boxShadow: `0 1px 1px rgba(16,24,40,.10), 0 ${Math.max(2, size * 0.09)}px ${Math.max(5, size * 0.22)}px -2px ${t.glow}, inset 0 1px 0 rgba(255,255,255,${isGlass ? 0.95 : 0.6}), inset 0 -1px 1px rgba(9,17,33,${isGlass ? 0.06 : 0.28}), inset 0 0 0 .5px rgba(255,255,255,.35)`,
      }}
    >
      <div style={{ position: 'absolute', inset: 0, background: `radial-gradient(120% 80% at 28% -14%, rgba(255,255,255,${isGlass ? 0.8 : 0.55}), transparent 62%)` }} />
      <div style={{ position: 'absolute', left: '-14%', right: '-14%', top: '-52%', height: '72%', borderRadius: '50%', background: `rgba(255,255,255,${isGlass ? 0.5 : 0.26})`, filter: 'blur(2px)' }} />
      <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(180deg, transparent 52%, rgba(9,17,33,.14))' }} />
      <span
        style={{
          position: 'relative',
          display: 'flex',
          width: Math.round(size * 0.54),
          height: Math.round(size * 0.54),
          color: isGlass ? 'var(--color-accent)' : '#fff',
          filter: isGlass ? 'none' : 'drop-shadow(0 1px 1px rgba(9,17,33,.35))',
        }}
      >
        {icon}
      </span>
    </div>
  );
}
