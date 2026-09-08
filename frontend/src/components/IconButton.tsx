import type { ReactNode } from 'react';

/** Ported from components/core/IconButton.jsx. Square control with an active state. */
export interface IconButtonProps {
  icon: ReactNode;
  label: string;
  active?: boolean;
  size?: number;
  onClick?: () => void;
}

export function IconButton({ icon, label, active, size = 40, onClick }: IconButtonProps) {
  return (
    <button
      aria-label={label}
      title={label}
      onClick={onClick}
      style={{
        width: size,
        height: size,
        borderRadius: 'var(--radius-md)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        border: active ? '1px solid var(--color-accent)' : '1px solid var(--color-border-hairline)',
        background: active ? 'var(--color-accent-soft)' : 'var(--color-bg-surface)',
        color: active ? 'var(--color-accent)' : 'var(--color-text-secondary)',
        cursor: 'pointer',
        transition: 'background var(--dur-fast), border-color var(--dur-fast)',
      }}
    >
      <span style={{ width: size * 0.42, height: size * 0.42, display: 'flex' }}>{icon}</span>
    </button>
  );
}
