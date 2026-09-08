/** Ported from components/forms/Switch.jsx. */
export interface SwitchProps {
  checked?: boolean;
  onChange?: (checked: boolean) => void;
  label?: string;
}

export function Switch({ checked = false, onChange, label }: SwitchProps) {
  return (
    <label style={{ display: 'flex', alignItems: 'center', gap: 10, fontFamily: 'var(--font-en)', cursor: 'pointer' }}>
      <button
        type="button"
        role="switch"
        aria-checked={checked}
        aria-label={label}
        onClick={() => onChange?.(!checked)}
        style={{ position: 'relative', width: 38, height: 22, borderRadius: 'var(--radius-pill)', border: 'none', padding: 0, background: checked ? 'var(--color-accent)' : 'var(--gray-300)', transition: 'background var(--dur-fast)', cursor: 'pointer' }}
      >
        <span style={{ position: 'absolute', top: 2, left: checked ? 18 : 2, width: 18, height: 18, borderRadius: '50%', background: '#fff', boxShadow: 'var(--shadow-xs)', transition: 'left var(--dur-fast) var(--ease-standard)' }} />
      </button>
      {label && <span style={{ fontSize: 'var(--fs-body)', color: 'var(--color-text-primary)' }}>{label}</span>}
    </label>
  );
}
