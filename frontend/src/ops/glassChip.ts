import type { CSSProperties } from 'react';

/**
 * Shared glass-chip surface style for map-adjacent floating chips (markers, controls, scale).
 * Ported from the `GLASS_CHIP` constant in ui_kits/operations_center/map.jsx — a slightly
 * stronger recipe than GlassPanel (saturate 1.9 / brightness 1.05) tuned for small pills.
 */
export const GLASS_CHIP: CSSProperties = {
  background: 'linear-gradient(180deg, rgba(255,255,255,.72), var(--color-bg-glass-strong) 46%, var(--color-glass-tint))',
  backdropFilter: 'blur(var(--blur-glass)) saturate(1.9) brightness(1.05)',
  WebkitBackdropFilter: 'blur(var(--blur-glass)) saturate(1.9) brightness(1.05)',
  border: '0.5px solid var(--color-border-glass)',
  boxShadow: 'var(--shadow-glass)',
};
