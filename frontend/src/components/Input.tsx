import type { ChangeEvent, ReactNode } from 'react';

/** Ported from components/forms/Input.jsx. */
export interface InputProps {
  label?: string;
  placeholder?: string;
  value?: string;
  onChange?: (e: ChangeEvent<HTMLInputElement>) => void;
  icon?: ReactNode;
  type?: string;
}

export function Input({ label, placeholder, value, onChange, icon, type = 'text' }: InputProps) {
  return (
    <label style={{ display: 'flex', flexDirection: 'column', gap: 6, fontFamily: 'var(--font-en)' }}>
      {label && <span style={{ fontSize: 'var(--fs-caption)', color: 'var(--color-text-secondary)', fontWeight: 500 }}>{label}</span>}
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, height: 40, padding: '0 12px', borderRadius: 'var(--radius-md)', background: 'var(--color-bg-surface)', border: '1px solid var(--color-border-hairline)' }}>
        {icon}
        <input
          type={type}
          placeholder={placeholder}
          value={value}
          onChange={onChange}
          aria-label={label ?? placeholder}
          style={{ border: 'none', outline: 'none', flex: 1, minWidth: 0, fontSize: 'var(--fs-body)', fontFamily: 'var(--font-en)', color: 'var(--color-text-primary)', background: 'transparent' }}
        />
      </div>
    </label>
  );
}
