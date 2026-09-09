import type { CSSProperties, ReactNode } from 'react';

/**
 * Ported from components/surfaces/GlassPanel.jsx — the signature floating translucent panel
 * (iOS-18-grade glass: 40px blur + saturation/brightness boost, sheen band, specular glint,
 * gradient-masked hairline ring, layered glass shadow).
 *
 * Layout-related style keys passed in `style` are applied to the inner content wrapper so the
 * decorative layers stay behind the content; everything else stays on the outer element.
 */
const LAYOUT_KEYS = ['display', 'flexDirection', 'gap', 'rowGap', 'columnGap', 'alignItems', 'justifyContent', 'flexWrap', 'gridTemplateColumns', 'gridTemplateRows'] as const;

export interface GlassPanelProps {
  children: ReactNode;
  padding?: number;
  radius?: string;
  style?: CSSProperties;
  className?: string;
}

export function GlassPanel({ children, padding = 20, radius = 'var(--radius-lg)', style = {}, className }: GlassPanelProps) {
  const outer: CSSProperties = {};
  const inner: CSSProperties = {};
  (Object.keys(style) as (keyof CSSProperties)[]).forEach((k) => {
    const target = (LAYOUT_KEYS as readonly string[]).includes(k as string) ? inner : outer;
    // @ts-expect-error index assignment across CSSProperties union
    target[k] = style[k];
  });
  const isColumn = inner.flexDirection === 'column';
  return (
    <div
      className={className}
      style={{
        position: 'relative',
        background: 'linear-gradient(180deg, rgba(255,255,255,.86), var(--color-bg-glass) 42%, var(--color-glass-tint))',
        backdropFilter: 'blur(var(--blur-glass)) saturate(1.8) brightness(1.04)',
        WebkitBackdropFilter: 'blur(var(--blur-glass)) saturate(1.8) brightness(1.04)',
        border: '0.5px solid var(--color-border-glass)',
        boxShadow: 'var(--shadow-glass)',
        borderRadius: radius,
        padding,
        overflow: 'hidden',
        ...(inner.display ? { display: 'flex', flexDirection: 'column' } : null),
        ...outer,
      }}
    >
      <div style={{ position: 'absolute', inset: 0, borderRadius: radius, padding: 1, background: 'linear-gradient(160deg, rgba(255,255,255,.95), rgba(255,255,255,.15) 32%, transparent 62%, rgba(255,255,255,.55))', WebkitMask: 'linear-gradient(#fff,#fff) content-box, linear-gradient(#fff,#fff)', WebkitMaskComposite: 'xor', maskComposite: 'exclude', pointerEvents: 'none', zIndex: 1 }} />
      <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: '46%', background: 'linear-gradient(180deg, rgba(255,255,255,.5), transparent)', pointerEvents: 'none', zIndex: 0 }} />
      <div style={{ position: 'absolute', top: '-38%', left: '-10%', width: '58%', height: '78%', background: 'radial-gradient(closest-side, rgba(255,255,255,.6), transparent)', filter: 'blur(8px)', pointerEvents: 'none', zIndex: 0 }} />
      <div style={{ position: 'relative', zIndex: 2, minWidth: 0, ...(inner.display ? { flex: 1, minHeight: 0 } : null), ...(isColumn ? { display: 'flex', flexDirection: 'column' } : null), ...inner }}>{children}</div>
    </div>
  );
}
