import { useState } from 'react';

/** Ported from components/forms/Select.jsx — custom disclosure select. */
export interface SelectOption {
  value: string;
  label: string;
}

export interface SelectProps {
  label?: string;
  options?: SelectOption[];
  value?: string;
  onChange?: (value: string) => void;
}

export function Select({ label, options = [], value, onChange }: SelectProps) {
  const [open, setOpen] = useState(false);
  const current = options.find((o) => o.value === value) ?? options[0];
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6, fontFamily: 'var(--font-en)', position: 'relative' }}>
      {label && <span style={{ fontSize: 'var(--fs-caption)', color: 'var(--color-text-secondary)', fontWeight: 500 }}>{label}</span>}
      <button
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', height: 40, padding: '0 12px', borderRadius: 'var(--radius-md)', background: 'var(--color-bg-surface)', border: '1px solid var(--color-border-hairline)', fontSize: 'var(--fs-body)', color: 'var(--color-text-primary)', cursor: 'pointer' }}
      >
        <span>{current ? current.label : 'Select…'}</span>
        <span style={{ color: 'var(--color-text-muted)' }}>▾</span>
      </button>
      {open && (
        <div role="listbox" style={{ position: 'absolute', top: '100%', left: 0, right: 0, marginTop: 4, background: 'var(--color-bg-surface)', border: '1px solid var(--color-border-hairline)', borderRadius: 'var(--radius-md)', boxShadow: 'var(--shadow-md)', zIndex: 10, overflow: 'hidden' }}>
          {options.map((o) => (
            <div
              key={o.value}
              role="option"
              aria-selected={o.value === value}
              tabIndex={0}
              onClick={() => { onChange?.(o.value); setOpen(false); }}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { onChange?.(o.value); setOpen(false); } }}
              style={{ padding: '10px 12px', fontSize: 'var(--fs-body)', cursor: 'pointer', background: o.value === value ? 'var(--color-accent-soft)' : 'transparent' }}
            >
              {o.label}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
