import type { CSSProperties, ReactNode } from 'react';

/** Ported from components/core/Button.jsx. Primary / secondary / ghost / critical, three sizes. */
type Variant = 'primary' | 'secondary' | 'ghost' | 'critical';
type Size = 'sm' | 'md' | 'lg';

const VARIANTS: Record<Variant, CSSProperties> = {
  primary: { background: 'var(--color-accent)', color: 'var(--color-text-on-accent)', border: '1px solid transparent' },
  secondary: { background: 'var(--color-bg-surface)', color: 'var(--color-text-primary)', border: '1px solid var(--color-border-strong)' },
  ghost: { background: 'transparent', color: 'var(--color-text-primary)', border: '1px solid transparent' },
  critical: { background: 'var(--color-critical)', color: '#fff', border: '1px solid transparent' },
};

const SIZES: Record<Size, CSSProperties> = {
  sm: { padding: '6px 12px', fontSize: 'var(--fs-caption)', height: 32 },
  md: { padding: '9px 16px', fontSize: 'var(--fs-body)', height: 40 },
  lg: { padding: '12px 20px', fontSize: 'var(--fs-body-lg)', height: 48 },
};

export interface ButtonProps {
  variant?: Variant;
  size?: Size;
  icon?: ReactNode;
  disabled?: boolean;
  full?: boolean;
  children?: ReactNode;
  onClick?: () => void;
  type?: 'button' | 'submit';
}

export function Button({ variant = 'primary', size = 'md', icon, disabled, full, children, onClick, type = 'button' }: ButtonProps) {
  const v = VARIANTS[variant] ?? VARIANTS.primary;
  const s = SIZES[size] ?? SIZES.md;
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      style={{
        display: full ? 'flex' : 'inline-flex',
        width: full ? '100%' : undefined,
        alignItems: 'center',
        gap: 8,
        justifyContent: 'center',
        fontFamily: 'var(--font-en)',
        fontWeight: 500,
        letterSpacing: 'var(--ls-normal)',
        borderRadius: 'var(--radius-md)',
        cursor: disabled ? 'not-allowed' : 'pointer',
        transition: 'background var(--dur-fast) var(--ease-standard), transform var(--dur-fast) var(--ease-standard), opacity var(--dur-fast)',
        opacity: disabled ? 0.45 : 1,
        height: s.height,
        padding: s.padding,
        fontSize: s.fontSize,
        ...v,
      }}
      onMouseDown={(e) => { if (!disabled) e.currentTarget.style.transform = 'scale(0.97)'; }}
      onMouseUp={(e) => { e.currentTarget.style.transform = 'scale(1)'; }}
      onMouseLeave={(e) => { e.currentTarget.style.transform = 'scale(1)'; }}
    >
      {icon}
      {children}
    </button>
  );
}
